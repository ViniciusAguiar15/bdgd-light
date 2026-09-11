"""Testes de ``bdgd_light.ingest.inventario`` e do comando ``bdgd-light inventario``."""

from __future__ import annotations

import io
import re

import pandas as pd
import pytest
from rich.console import Console
from typer.testing import CliRunner

from bdgd_light.cli import app
from bdgd_light.ingest.export import exportar
from bdgd_light.ingest.inventario import (
    COLUNAS_INVENTARIO,
    carregar_bairro,
    gravar_csv,
    inventariar,
    tabela_top,
)
from bdgd_light.ingest.parquet import CamadaAusenteError

runner = CliRunner()
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def saida(resultado) -> str:
    return _ANSI.sub("", resultado.output)


def compacto(resultado) -> str:
    """Saída sem espaços, quebras e bordas de tabela — o rich dobra células nos 80 colunas do
    CliRunner, então strings só são comparáveis depois de "compactadas"."""
    return "".join(c for c in saida(resultado) if not c.isspace() and not "\u2500" <= c <= "\u259f")


@pytest.fixture(scope="module")
def inventario(parquet_mini) -> pd.DataFrame:
    return inventariar(parquet_mini).tabela.set_index("COD_ID")


def test_uma_linha_por_ctmt_com_todas_as_colunas_e_ordem_por_score(parquet_mini):
    resultado = inventariar(parquet_mini)
    tabela = resultado.tabela
    assert list(tabela.columns) == COLUNAS_INVENTARIO
    assert tabela["COD_ID"].tolist() == ["RJO001", "RJO002", "RJO003"]  # score decrescente
    # score = ties de campo (NA_interligacao_campo, sem os disjuntores da SE) × (UCBT + UCMT)
    assert tabela["score"].tolist() == [10, 4, 0]
    assert resultado.camadas_ausentes == [] and len(resultado.interligacoes) == 3


def test_identificacao_do_alimentador(inventario):
    rjo1, rjo3 = inventario.loc["RJO001"], inventario.loc["RJO003"]
    assert (rjo1["NOME"], rjo1["tipo"], rjo1["SUB"], rjo1["SUB_NOME"], rjo1["UNI_TR_AT"]) == (
        "LDA SINTETICO 01",
        "LDA",
        "SE001",
        "SETD SINTETICA 01",
        "TRAT001",
    )
    assert (rjo1["TEN_NOM"], rjo1["TEN_NOM_kV"], rjo1["MUN"]) == ("46", 13.2, "3304557")
    assert (rjo3["tipo"], rjo3["TEN_NOM"], rjo3["TEN_NOM_kV"], rjo3["MUN"]) == (
        "LSA",
        "67",
        25.0,
        "3303500",
    )


def test_rede_carga_e_clientes(inventario):
    rjo1, rjo2, rjo3 = (inventario.loc[c] for c in ("RJO001", "RJO002", "RJO003"))
    # km_MT = soma de COMP dos trechos SSDMT do CTMT
    assert rjo1["km_MT"] == pytest.approx(0.374, abs=0.002)
    assert rjo3["km_MT"] == pytest.approx(0.0205, abs=0.001)
    # ENE_MWh_ano vem de ENE_01..12 do CTMT (1,5 GWh × i)
    assert rjo1["ENE_MWh_ano"] == pytest.approx(18_000.0)
    assert rjo3["ENE_MWh_ano"] == pytest.approx(54_000.0)
    # transformadores e kVA
    assert (rjo1["n_UNTRMT"], rjo1["kVA_instalado"]) == (2, 120.0)
    assert (rjo2["n_UNTRMT"], rjo2["kVA_instalado"]) == (1, 112.5)
    # UCBT ligam pelo transformador (UNI_TR_MT → UNTRMT.CTMT): UC00007 tem CTMT="RJO002" na tabela,
    # mas o trafo TR003 é de RJO001
    assert (rjo1["n_UCBT"], rjo2["n_UCBT"], rjo3["n_UCBT"]) == (4, 2, 1)
    assert (rjo1["n_UCMT"], rjo2["n_UCMT"], rjo3["n_UCMT"]) == (1, 0, 1)
    ene_uc = 12 * (120.0 * (1 + 2 + 3 + 7) + 60_000.0) / 1000.0  # ENE_01..12 das UCs (kWh → MWh)
    assert rjo1["ENE_UC_MWh_ano"] == pytest.approx(ene_uc, rel=1e-6)
    # DER: UGBT_tab pelo trafo + UGMT_tab pelo CTMT
    assert (rjo1["n_DER"], rjo1["kW_DER"]) == (2, 505.0)
    assert (rjo2["n_DER"], rjo2["kW_DER"]) == (1, 10.0)
    assert (rjo3["n_DER"], rjo3["kW_DER"]) == (0, 0.0)
    assert (rjo1["n_UNCRMT"], rjo3["n_UNREMT"], rjo2["n_UNREMT"]) == (1, 1, 0)


def test_chaves_e_interligacoes_geometricas(inventario):
    rjo1, rjo2, rjo3 = (inventario.loc[c] for c in ("RJO001", "RJO002", "RJO003"))
    chaves = ["chaves_total", "chaves_NA", "chaves_NF", "chaves_telecomandadas"]
    assert rjo1[chaves].tolist() == [4, 2, 2, 3]
    assert rjo2[chaves].tolist() == [4, 2, 2, 2]
    assert rjo3[chaves].tolist() == [1, 0, 1, 0]
    ties = [
        "NA_interligacao",
        "NA_interligacao_telecomandada",
        "NA_interligacao_SE",
        "NA_interligacao_campo",
        "NA_interligacao_campo_telecomandada",
        "n_vizinhos",
        "vizinhos",
    ]
    assert rjo1[ties].tolist() == [3, 2, 1, 2, 1, 1, "RJO002"]
    assert rjo2[ties].tolist() == [3, 2, 1, 2, 1, 1, "RJO001"]
    assert rjo3[ties].tolist() == [0, 0, 0, 0, 0, 0, ""]


def test_bbox_em_epsg4326(inventario):
    rjo1 = inventario.loc["RJO001"]
    assert rjo1[["lon_min", "lat_min", "lon_max", "lat_max"]].tolist() == pytest.approx(
        [-43.2, -22.9106, -43.1968, -22.91], abs=1e-5
    )
    rjo3 = inventario.loc["RJO003"]
    assert rjo3["lon_min"] == pytest.approx(-43.21, abs=1e-5)
    assert rjo3["lon_max"] == pytest.approx(-43.2098, abs=1e-5)


def test_filtro_por_bairro_mantem_interligacoes_com_fora_do_poligono(parquet_mini, bairro_mini):
    resultado = inventariar(parquet_mini, bairro=carregar_bairro(bairro_mini))
    assert resultado.tabela["COD_ID"].tolist() == ["RJO001", "RJO002"]
    assert resultado.tabela.set_index("COD_ID").loc["RJO001", "NA_interligacao"] == 3


def test_camadas_opcionais_ausentes_zeram_colunas_com_aviso(bdgd_mini, tmp_path):
    parcial = tmp_path / "parcial"
    exportar(bdgd_mini, ["CTMT", "SSDMT"], parcial, console=Console(quiet=True))
    log = io.StringIO()
    resultado = inventariar(parcial, console=Console(file=log, width=200))
    assert "UNSEMT" in resultado.camadas_ausentes and "UCBT_tab" in resultado.camadas_ausentes
    assert "Aviso" in log.getvalue() and "UNTRMT" in log.getvalue()
    tabela = resultado.tabela.set_index("COD_ID")
    assert list(resultado.tabela.columns) == COLUNAS_INVENTARIO
    assert tabela.loc["RJO001", "km_MT"] == pytest.approx(0.374, abs=0.002)
    assert tabela["chaves_total"].tolist() == [0, 0, 0] and tabela["n_UCBT"].tolist() == [0, 0, 0]
    assert tabela["SUB_NOME"].isna().all() and tabela["MUN"].isna().all()
    assert tabela["vizinhos"].tolist() == ["", "", ""]


def test_ctmt_obrigatoria(bdgd_mini, tmp_path):
    so_ssdmt = tmp_path / "so_ssdmt"
    exportar(bdgd_mini, ["SSDMT"], so_ssdmt, console=Console(quiet=True))
    with pytest.raises(CamadaAusenteError, match="CTMT"):
        inventariar(so_ssdmt)
    with pytest.raises(FileNotFoundError, match="não encontrado"):
        inventariar(tmp_path / "nada")


def test_csv_e_tabela_rich(inventario, tmp_path):
    tabela = inventario.reset_index()
    csv = gravar_csv(tabela, tmp_path / "sub" / "inventario.csv")
    relido = pd.read_csv(csv, dtype={"COD_ID": str, "TEN_NOM": str, "MUN": str, "SUB": str})
    assert list(relido.columns) == COLUNAS_INVENTARIO and len(relido) == 3
    assert relido.set_index("COD_ID").loc["RJO001", "NA_interligacao"] == 3
    console = Console(file=io.StringIO(), width=250)
    console.print(tabela_top(tabela, 2))
    texto = console.file.getvalue()
    assert "Top 2" in texto and "RJO001" in texto and "RJO002" in texto and "RJO003" not in texto
    assert "SETD SINTETICA 01" in texto and "13,2" in texto


# --- CLI ----------------------------------------------------------------------------------------


def test_cli_inventario_gera_csv_e_tabela(parquet_mini, tmp_path):
    csv = tmp_path / "inv.csv"
    resultado = runner.invoke(
        app, ["inventario", "--parquet", str(parquet_mini), "--out", str(csv), "--top", "2"]
    )
    assert resultado.exit_code == 0, saida(resultado)
    assert "3 CTMT inventariados" in saida(resultado) and "Top 2" in saida(resultado)
    relido = pd.read_csv(csv)
    assert len(relido) == 3 and list(relido.columns) == COLUNAS_INVENTARIO


def test_cli_inventario_bairro_e_top_zero(parquet_mini, bairro_mini, tmp_path):
    csv = tmp_path / "inv.csv"
    resultado = runner.invoke(
        app,
        [
            "inventario",
            "--parquet",
            str(parquet_mini),
            "--out",
            str(csv),
            "--top",
            "0",
            "--bairro",
            str(bairro_mini),
        ],
    )
    assert resultado.exit_code == 0, saida(resultado)
    assert "Filtro por bairro: 2 CTMT" in saida(resultado) and "Top" not in saida(resultado)
    assert pd.read_csv(csv)["COD_ID"].tolist() == ["RJO001", "RJO002"]


def test_cli_inventario_erros_claros(tmp_path, parquet_mini):
    resultado = runner.invoke(app, ["inventario", "--parquet", str(tmp_path / "nada")])
    assert resultado.exit_code == 1 and "Erro" in saida(resultado)
    assert "não encontrado" in saida(resultado) and "Traceback" not in saida(resultado)
    resultado = runner.invoke(
        app,
        ["inventario", "--parquet", str(parquet_mini), "--bairro", str(tmp_path / "x.geojson")],
    )
    assert resultado.exit_code == 1 and "Erro" in saida(resultado)
    assert "não foi possível ler o polígono" in saida(resultado)


def test_cli_vizinhos(parquet_mini):
    resultado = runner.invoke(app, ["vizinhos", "--ctmt", "RJO001", "--parquet", str(parquet_mini)])
    assert resultado.exit_code == 0, saida(resultado)
    texto = compacto(resultado)
    # padrão --sem-se: CH007 (disjuntor dentro da SE001) fica fora das contagens
    assert "VizinhosdeRJO001:1CTMT,2chavesNAdeinterligaçãodecampo" in texto
    assert "(1telecomandadas),2pareschave×vizinho;1chavesnaSEdescontadas" in texto
    assert "RJO002" in texto and "CH003" in texto and "CH007" not in texto
    com_se = runner.invoke(
        app, ["vizinhos", "--ctmt", "RJO001", "--parquet", str(parquet_mini), "--com-se"]
    )
    texto = compacto(com_se)
    assert "3chavesNAdeinterligação(2telecomandadas,1naSE),3pares" in texto
    assert "CH007" in texto
    nenhum = runner.invoke(app, ["vizinhos", "--ctmt", "RJO003", "--parquet", str(parquet_mini)])
    assert nenhum.exit_code == 0 and "nenhuma interligação" in saida(nenhum)
    erro = runner.invoke(app, ["vizinhos", "--ctmt", "XXX", "--parquet", str(parquet_mini)])
    assert erro.exit_code == 1 and "Erro" in saida(erro) and "XXX" in saida(erro)


def _carregar_script_regioes():
    import importlib.util
    from pathlib import Path

    caminho = Path("scripts/regioes_inventario.py")
    spec = importlib.util.spec_from_file_location("regioes_inventario", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_script_regioes_inventario_agrupa_por_bairro_e_compara(tmp_path, capsys, monkeypatch):
    modulo = _carregar_script_regioes()

    def linha(cod, lat, lon, tipo, campo_tlcd, se, mun="3304557"):
        return {
            "COD_ID": cod,
            "tipo": tipo,
            "MUN": mun,
            "km_MT": 3.0,
            "n_UCBT": 1000,
            "NA_interligacao_campo_telecomandada": campo_tlcd,
            "NA_interligacao_campo": campo_tlcd + 1,
            "NA_interligacao_SE": se,
            "lat_min": lat - 0.001,
            "lat_max": lat + 0.001,
            "lon_min": lon - 0.001,
            "lon_max": lon + 0.001,
        }

    antes = pd.DataFrame(
        [
            linha("PTS0001", -22.984, -43.205, "LDS", 31, 0),  # Ipanema: ties no pátio da SE
            linha("ALC9925", -22.925, -43.235, "LDA", 4, 0),  # Tijuca
            linha("LONGE", -22.80, -43.60, "LDA", 9, 0),  # fora de todas as referências
            linha("OUTRO", -22.984, -43.205, "LDS", 5, 0, mun="3303500"),  # outro município
        ]
    )
    depois = antes.copy()
    depois.loc[depois["COD_ID"] == "PTS0001", ["NA_interligacao_campo_telecomandada"]] = 0
    depois.loc[depois["COD_ID"] == "PTS0001", ["NA_interligacao_campo"]] = 0
    depois.loc[depois["COD_ID"] == "PTS0001", ["NA_interligacao_SE"]] = 31
    antes.to_csv(tmp_path / "antes.csv", index=False)
    depois.to_csv(tmp_path / "depois.csv", index=False)

    regioes = modulo.classificar(depois)
    assert regioes.to_dict() == {0: "Ipanema/Leblon", 1: "Tijuca", 2: None}  # OUTRO nem entra
    tabela = modulo.resumo(depois)
    assert tabela.index.tolist() == ["Ipanema/Leblon", "Tijuca"]  # ordem das referências
    assert tabela.loc["Ipanema/Leblon", ["n", "LDS", "ties_TLCD", "ties_SE"]].tolist() == [
        1,
        1,
        0,
        31,
    ]
    assert tabela.loc["Tijuca", ["n", "LDA", "ties_TLCD", "ties_SE"]].tolist() == [1, 1, 4, 0]

    monkeypatch.setattr(
        "sys.argv",
        [
            "regioes_inventario.py",
            str(tmp_path / "depois.csv"),
            "--antes",
            str(tmp_path / "antes.csv"),
        ],
    )
    modulo.main()
    texto = capsys.readouterr().out
    assert "| Ipanema/Leblon | 1 | 0 | 1 | 3,0 | 1.000 | 0 | 31 |" in texto
    assert "| Ipanema/Leblon | 1 | 31 → 0 | 32 → 0 | 0 → 31 |" in texto
    assert "total nas regiões: ties TLCD 35 → 4, de campo 37 → 5, em SE 0 → 31" in texto
