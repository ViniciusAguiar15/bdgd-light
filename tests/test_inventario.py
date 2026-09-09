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


@pytest.fixture(scope="module")
def inventario(parquet_mini) -> pd.DataFrame:
    return inventariar(parquet_mini).tabela.set_index("COD_ID")


def test_uma_linha_por_ctmt_com_todas_as_colunas_e_ordem_por_score(parquet_mini):
    resultado = inventariar(parquet_mini)
    tabela = resultado.tabela
    assert list(tabela.columns) == COLUNAS_INVENTARIO
    assert tabela["COD_ID"].tolist() == ["RJO001", "RJO002", "RJO003"]  # score decrescente
    assert tabela["score"].tolist() == [15, 6, 0]  # NA_interligacao × (UCBT + UCMT)
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
    assert rjo1[chaves].tolist() == [3, 2, 1, 2]
    assert rjo2[chaves].tolist() == [3, 2, 1, 1]
    assert rjo3[chaves].tolist() == [1, 0, 1, 0]
    ties = [
        "NA_interligacao",
        "NA_interligacao_telecomandada",
        "NA_interligacao_SE",
        "n_vizinhos",
        "vizinhos",
    ]
    assert rjo1[ties].tolist() == [3, 2, 1, 1, "RJO002"]
    assert rjo2[ties].tolist() == [3, 2, 1, 1, "RJO001"]
    assert rjo3[ties].tolist() == [0, 0, 0, 0, ""]


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
    texto = saida(resultado)
    titulo = " ".join(texto.split())  # o título quebra linha nos 80 colunas do CliRunner
    assert "Vizinhos de RJO001: 1 CTMT, 3 chaves NA de interligação" in titulo
    assert "(2 telecomandadas, 1 na SE), 3 pares chave×vizinho" in titulo
    assert "RJO002" in texto and "CH003" in texto
    nenhum = runner.invoke(app, ["vizinhos", "--ctmt", "RJO003", "--parquet", str(parquet_mini)])
    assert nenhum.exit_code == 0 and "nenhuma interligação" in saida(nenhum)
    erro = runner.invoke(app, ["vizinhos", "--ctmt", "XXX", "--parquet", str(parquet_mini)])
    assert erro.exit_code == 1 and "Erro" in saida(erro) and "XXX" in saida(erro)
