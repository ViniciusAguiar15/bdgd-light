"""Testes de ``bdgd_light.ingest.recorte`` e do comando ``bdgd-light recortar``.

O essencial: nada de outro CTMT vaza para o recorte de um alimentador.
"""

from __future__ import annotations

import json
import re

import geopandas as gpd
import pandas as pd
import pyogrio
import pytest
from rich.console import Console
from typer.testing import CliRunner

from bdgd_light.cli import app
from bdgd_light.ingest.export import exportar
from bdgd_light.ingest.parquet import CamadaAusenteError, DiretorioParquet
from bdgd_light.ingest.recorte import (
    CAMADA_INTERLIGACOES,
    CAMADAS_POR_CTMT,
    CAMADAS_POR_TRAFO,
    FOLGA_BBOX_M,
    CtmtInexistenteError,
    FonteMemoria,
    bbox_rede,
    recortar,
    selecionar,
)

runner = CliRunner()
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
CLUSTER = ["RJO001", "RJO002"]
# camadas exigidas pela issue #3 que existem na fixture (UCMT/UGMT/UGBT não têm geometria na Light)
EXIGIDAS = [
    "CTMT",
    "SSDMT",
    "SSDBT",
    "UNTRMT",
    "UNSEMT",
    "UNSEBT",
    "UNREMT",
    "UNCRMT",
    "UCBT",
    "UCBT_tab",
    "UCMT_tab",
    "UGBT_tab",
    "UGMT_tab",
    "PONNOT",
    "RAMLIG",
    "UNTRAT",
]


def saida(resultado) -> str:
    return _ANSI.sub("", resultado.output)


def ler_gpkg(gpkg) -> dict[str, pd.DataFrame]:
    return {nome: pyogrio.read_dataframe(gpkg, layer=nome) for nome, _ in pyogrio.list_layers(gpkg)}


@pytest.fixture(scope="module")
def recorte_cluster(parquet_mini, tmp_path_factory):
    out = tmp_path_factory.mktemp("feeders")
    resultado = recortar(parquet_mini, CLUSTER, out, console=Console(quiet=True))
    return resultado


@pytest.fixture(scope="module")
def trafo_ctmt(bdgd_mini) -> pd.Series:
    trafos = pyogrio.read_dataframe(bdgd_mini, layer="UNTRMT", read_geometry=False)
    return trafos.set_index("COD_ID")["CTMT"]


def test_gera_gpkg_e_meta_por_ctmt_e_do_cluster(recorte_cluster):
    assert [r.nome for r in recorte_cluster.recortes] == CLUSTER
    assert recorte_cluster.cluster is not None
    assert recorte_cluster.cluster.nome == "cluster_RJO001-RJO002"
    for recorte in [*recorte_cluster.recortes, recorte_cluster.cluster]:
        assert recorte.gpkg.exists() and recorte.meta.exists()
        assert recorte.gpkg.name == f"{recorte.nome}.gpkg"
        assert recorte.meta.name == f"{recorte.nome}.meta.json"
        assert set(EXIGIDAS) <= set(recorte.camadas)
        gravadas = {nome for nome, _ in pyogrio.list_layers(recorte.gpkg)}
        # camadas vazias não são gravadas, mas aparecem com 0 no meta
        assert gravadas == {c for c, n in recorte.contagens.items() if n > 0}
        for camada in gravadas:
            info = pyogrio.read_info(recorte.gpkg, layer=camada)
            assert info["features"] == recorte.contagens[camada]
            if info["geometry_type"] is not None:
                assert info["crs"] == "EPSG:4674"
    assert sorted(p.name for p in recorte_cluster.recortes[0].gpkg.parent.iterdir()) == [
        "RJO001.gpkg",
        "RJO001.meta.json",
        "RJO002.gpkg",
        "RJO002.meta.json",
        "cluster_RJO001-RJO002.gpkg",
        "cluster_RJO001-RJO002.meta.json",
    ]


@pytest.mark.parametrize("cod", CLUSTER)
def test_nada_de_outro_ctmt_vaza_para_o_recorte(recorte_cluster, trafo_ctmt, bdgd_mini, cod):
    recorte = next(r for r in recorte_cluster.recortes if r.nome == cod)
    camadas = ler_gpkg(recorte.gpkg)
    assert camadas["CTMT"]["COD_ID"].tolist() == [cod]
    for camada in CAMADAS_POR_CTMT:
        if camada in camadas:
            assert set(camadas[camada]["CTMT"]) == {cod}, camada
    for camada in CAMADAS_POR_TRAFO:
        if camada in camadas:
            # BT liga pelo transformador; a coluna CTMT da própria camada pode divergir (UC00007)
            assert set(camadas[camada]["UNI_TR_MT"].map(trafo_ctmt)) == {cod}, camada
    # postes: os PN_CON* das feições do recorte dentro do bbox da rede — nunca o órfão PN999 nem
    # PN107, poste de UC00007 a ~40 km da rede (issue #40)
    pns: set[str] = set()
    for dados in camadas.values():
        for coluna in ("PN_CON", "PN_CON_1", "PN_CON_2"):
            if coluna in dados.columns:
                pns |= set(dados[coluna].dropna()) - {""}
    assert set(camadas["PONNOT"]["COD_ID"]) == pns - {"PN107"} and "PN999" not in pns
    assert ("PN107" in pns) == (cod == "RJO001")  # referenciado por UCBT_tab, mas fora do bbox
    # subestação inteira do CTMT (SUB + todos os UNTRAT dela), e só ela
    assert camadas["SUB"]["COD_ID"].tolist() == ["SE001"]
    assert sorted(camadas["UNTRAT"]["COD_ID"]) == ["TRAT001", "TRAT003"]
    # equipamentos e catálogos só das unidades/códigos usados
    assert set(camadas["EQTRMT"]["UNI_TR_MT"]) == set(camadas["UNTRMT"]["COD_ID"])
    unsebt = camadas.get("UNSEBT", pd.DataFrame({"COD_ID": []}))  # RJO002 não tem chave BT
    chaves = set(camadas["UNSEMT"]["COD_ID"]) | set(unsebt["COD_ID"])
    assert set(camadas["EQSE"]["UN_SE"]) <= chaves and len(camadas["EQSE"]) == len(
        camadas["UNSEMT"]
    )
    cabos = set(camadas["SSDMT"]["TIP_CND"]) | set(camadas["SSDBT"]["TIP_CND"])
    cabos |= set(camadas["RAMLIG"]["TIP_CND"])
    assert set(camadas["SEGCON"]["COD_ID"]) == cabos and "CAB003" not in cabos
    curvas = set(camadas["UCBT_tab"]["TIP_CC"]) | set(
        camadas.get("UCMT_tab", pd.DataFrame({"TIP_CC": []}))["TIP_CC"]
    )
    assert set(camadas["CRVCRG"]["COD_ID"]) == curvas
    # interligações: dos dois lados, mas sempre envolvendo o CTMT
    ties = camadas[CAMADA_INTERLIGACOES]
    assert ((ties["CTMT"] == cod) | (ties["CTMT_VIZ"] == cod)).all() and len(ties) == 3
    # geometria preservada
    original = gpd.read_file(bdgd_mini, layer="SSDMT", engine="pyogrio").set_index("COD_ID")
    trechos = camadas["SSDMT"].set_index("COD_ID")
    assert trechos.geometry.geom_equals(original.loc[trechos.index].geometry).all()


def test_contagens_esperadas_por_alimentador(recorte_cluster):
    contagens = {r.nome: r.contagens for r in recorte_cluster.recortes}
    assert contagens["RJO001"] == {
        "CTMT": 1,
        "SUB": 1,
        "UNTRAT": 2,
        "SSDMT": 4,
        "UNSEMT": 4,
        "UNTRMT": 2,
        "UNREMT": 0,
        "UNCRMT": 1,
        "UCMT_tab": 1,
        "UGMT_tab": 1,
        "SSDBT": 2,
        "UNSEBT": 1,
        "RAMLIG": 1,
        "UCBT": 4,
        "UCBT_tab": 4,
        "UGBT_tab": 1,
        "PONNOT": 14,  # 15 referenciados, PN107 fora do bbox da rede (issue #40)
        "EQTRMT": 2,
        "EQSE": 4,
        "SEGCON": 2,
        "CRVCRG": 6,
        "INTERLIGACOES": 3,
    }
    assert contagens["RJO002"]["UCBT_tab"] == 2  # UC00007 (CTMT="RJO002" na tabela) fica em RJO001
    assert contagens["RJO002"]["UNSEMT"] == 4 and contagens["RJO002"]["UNCRMT"] == 0
    ucbt_1 = pyogrio.read_dataframe(recorte_cluster.recortes[0].gpkg, layer="UCBT_tab")
    assert sorted(ucbt_1["COD_ID"]) == ["UC00001", "UC00002", "UC00003", "UC00007"]


def test_cluster_e_a_uniao_dos_recortes(recorte_cluster):
    cluster = recorte_cluster.cluster
    individuais = {r.nome: r.camadas for r in recorte_cluster.recortes}
    for camada, dados in cluster.camadas.items():
        uniao = pd.concat([individuais[c][camada] for c in CLUSTER])
        chave = "COD_ID" if "COD_ID" in dados.columns else dados.columns[0]
        assert set(dados[chave]) == set(uniao[chave]), camada
    assert cluster.contagens["CTMT"] == 2 and cluster.contagens["SSDMT"] == 8
    assert cluster.contagens["SUB"] == 1 and cluster.contagens["UNTRAT"] == 2  # sem duplicar
    assert cluster.contagens["INTERLIGACOES"] == 3


def test_meta_json(recorte_cluster):
    meta = json.loads(recorte_cluster.recortes[0].meta.read_text(encoding="utf-8"))
    assert meta["nome"] == "RJO001" and meta["crs"] == "EPSG:4674"
    assert meta["ctmt"] == [{"COD_ID": "RJO001", "NOME": "LDA SINTETICO 01", "SUB": "SE001"}]
    assert meta["camadas"] == recorte_cluster.recortes[0].contagens
    assert meta["bbox_4326"] == pytest.approx([-43.2, -22.9106, -43.1968, -22.91], abs=1e-5)
    assert meta["interligacoes"] == [
        {
            "ctmt": "RJO001",
            "vizinho": "RJO002",
            "ties": 3,
            "ties_telecomandadas": 2,
            "ties_em_SE": 1,
            "ties_campo": 2,
            "ties_campo_telecomandadas": 1,
            "chaves": ["CH003", "CH005", "CH007"],
            "chaves_campo": ["CH003", "CH005"],
        }
    ]
    assert "gerado_em" in meta and meta["bdgd_light"]
    assert meta["bbox_folga_m"] == FOLGA_BBOX_M == 500.0
    assert meta["avisos"] == [
        "PONNOT: 1 feição(ões) fora do bbox da rede (folga 500 m) descartada(s)"
    ]
    meta_cluster = json.loads(recorte_cluster.cluster.meta.read_text(encoding="utf-8"))
    assert [c["COD_ID"] for c in meta_cluster["ctmt"]] == CLUSTER
    assert len(meta_cluster["interligacoes"]) == 1  # o par interno ao cluster aparece uma vez


def test_regras_identicas_em_parquet_e_em_memoria(parquet_mini):
    fonte = DiretorioParquet(parquet_mini)
    direto = selecionar(fonte, ["RJO002"])
    cluster = selecionar(fonte, CLUSTER)
    derivado = selecionar(FonteMemoria(cluster), ["RJO002"])
    assert set(direto) == set(derivado)
    for camada in direto:
        pd.testing.assert_frame_equal(
            direto[camada].sort_values(direto[camada].columns[0]).reset_index(drop=True),
            derivado[camada].sort_values(derivado[camada].columns[0]).reset_index(drop=True),
        )


def test_ordem_dos_ctmt_e_a_pedida(parquet_mini, tmp_path):
    resultado = recortar(parquet_mini, ["RJO002", "RJO001"], tmp_path, console=Console(quiet=True))
    assert resultado.cluster.nome == "cluster_RJO002-RJO001"
    meta = json.loads(resultado.cluster.meta.read_text(encoding="utf-8"))
    assert [c["COD_ID"] for c in meta["ctmt"]] == ["RJO002", "RJO001"]
    assert meta["ctmt"][0]["NOME"] == "LDA SINTETICO 02"


def test_referencias_em_branco_nao_puxam_postes(parquet_mini):
    # na Light 2025 há RAMLIG com PN_CON_2 = " "; não é referência a poste algum
    camadas = selecionar(DiretorioParquet(parquet_mini), CLUSTER)
    camadas["RAMLIG"] = camadas["RAMLIG"].copy()
    camadas["RAMLIG"].loc[camadas["RAMLIG"].index[0], "PN_CON_2"] = " "
    esperado = selecionar(DiretorioParquet(parquet_mini), ["RJO001"])["PONNOT"]
    derivado = selecionar(FonteMemoria(camadas), ["RJO001"])["PONNOT"]
    assert set(derivado["COD_ID"]) <= set(esperado["COD_ID"])
    assert " " not in set(derivado["COD_ID"]) and not derivado["COD_ID"].str.strip().eq("").any()


def test_postes_longe_da_rede_ficam_fora_do_recorte(parquet_mini):
    # UCBT_tab.PN_CON de UC00007 aponta para PN107, a ~40 km da rede (como na Light 2025)
    fonte = DiretorioParquet(parquet_mini)
    avisos: list[str] = []
    com_filtro = selecionar(fonte, ["RJO001"], avisos=avisos)
    sem_filtro = selecionar(fonte, ["RJO001"], folga_bbox_m=None)
    assert "PN107" in set(sem_filtro["PONNOT"]["COD_ID"])
    assert set(sem_filtro["PONNOT"]["COD_ID"]) - set(com_filtro["PONNOT"]["COD_ID"]) == {"PN107"}
    assert avisos == ["PONNOT: 1 feição(ões) fora do bbox da rede (folga 500 m) descartada(s)"]
    # a UC continua em UCBT_tab (carga do trafo), só o poste sai
    assert "UC00007" in set(com_filtro["UCBT_tab"]["COD_ID"])
    # folga enorme mantém o poste; UCBT com geometria também passa pelo filtro
    assert "PN107" in set(selecionar(fonte, ["RJO001"], folga_bbox_m=100_000)["PONNOT"]["COD_ID"])
    ucbt = com_filtro["UCBT"].copy()
    ucbt.loc[ucbt["COD_ID"] == "UC00007", "geometry"] = gpd.points_from_xy([-43.6], [-23.0])[0]
    ucbt.loc[ucbt["COD_ID"] == "UC00001", "geometry"] = None
    camadas = dict(com_filtro, UCBT=ucbt)
    avisos.clear()
    filtrado = selecionar(FonteMemoria(camadas), ["RJO001"], avisos=avisos)["UCBT"]
    assert sorted(filtrado["COD_ID"]) == ["UC00001", "UC00002", "UC00003"]  # sem geometria fica
    assert avisos == ["UCBT: 1 feição(ões) fora do bbox da rede (folga 500 m) descartada(s)"]


def test_bbox_rede_com_folga():
    rede = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy([-43.20, -43.19], [-22.92, -22.91]), crs="EPSG:4674"
    )
    assert bbox_rede({"SSDMT": rede}, 0.0) == pytest.approx((-43.20, -22.92, -43.19, -22.91))
    minx, miny, maxx, maxy = bbox_rede({"SSDMT": rede}, 500.0)
    assert miny == pytest.approx(-22.92 - 500 / 111_320, abs=1e-6)
    assert maxx - (-43.19) == pytest.approx(500 / 111_320 / 0.9215, rel=1e-2)  # cos(-22.915°)
    assert bbox_rede({"UCBT_tab": pd.DataFrame({"a": [1]})}) is None
    assert bbox_rede({"SSDMT": rede.iloc[0:0]}) is None


def test_regravar_substitui_o_gpkg(parquet_mini, tmp_path):
    for _ in range(2):
        resultado = recortar(parquet_mini, ["RJO003"], tmp_path, console=Console(quiet=True))
    recorte = resultado.recortes[0]
    assert resultado.cluster is None  # um só CTMT não gera cluster
    assert pyogrio.read_info(recorte.gpkg, layer="SSDMT")["features"] == 1
    assert recorte.contagens["INTERLIGACOES"] == 0 and recorte.contagens["UNREMT"] == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["RJO003.gpkg", "RJO003.meta.json"]


def test_camadas_ausentes_sao_puladas_com_aviso(bdgd_mini, tmp_path):
    parcial = tmp_path / "parcial"
    exportar(bdgd_mini, ["CTMT", "SSDMT", "UNTRMT", "SSDBT"], parcial, console=Console(quiet=True))
    log = Console(file=__import__("io").StringIO(), width=200)
    resultado = recortar(parcial, ["RJO001"], tmp_path / "out", console=log)
    assert "UNSEMT" in resultado.camadas_ausentes and "PONNOT" in resultado.camadas_ausentes
    assert "Aviso" in log.file.getvalue()
    camadas = resultado.recortes[0].camadas
    assert set(camadas) == {"CTMT", "SSDMT", "UNTRMT", "SSDBT"}  # sem SSDMT+UNSEMT não há ties
    assert camadas["SSDBT"]["UNI_TR_MT"].isin(camadas["UNTRMT"]["COD_ID"]).all()


def test_bt_usa_coluna_ctmt_quando_nao_ha_untrmt(bdgd_mini, tmp_path):
    parcial = tmp_path / "parcial"
    exportar(bdgd_mini, ["CTMT", "UCBT_tab"], parcial, console=Console(quiet=True))
    camadas = selecionar(DiretorioParquet(parcial), ["RJO002"])
    assert sorted(camadas["UCBT_tab"]["COD_ID"]) == ["UC00004", "UC00005", "UC00007"]


def test_erros(parquet_mini, tmp_path, bdgd_mini):
    with pytest.raises(CtmtInexistenteError, match="NAOEXISTE"):
        recortar(parquet_mini, ["RJO001", "NAOEXISTE"], tmp_path, console=Console(quiet=True))
    with pytest.raises(ValueError, match="ao menos um CTMT"):
        recortar(parquet_mini, [" "], tmp_path, console=Console(quiet=True))
    sem_ctmt = tmp_path / "sem_ctmt"
    exportar(bdgd_mini, ["SSDMT"], sem_ctmt, console=Console(quiet=True))
    with pytest.raises(CamadaAusenteError, match="CTMT"):
        recortar(sem_ctmt, ["RJO001"], tmp_path, console=Console(quiet=True))


# --- CLI ----------------------------------------------------------------------------------------


def test_cli_recortar_varios_ctmt(parquet_mini, tmp_path):
    out = tmp_path / "feeders"
    resultado = runner.invoke(
        app,
        [
            "recortar",
            "--parquet",
            str(parquet_mini),
            "--ctmt",
            "RJO001, RJO002",
            "--out",
            str(out),
            "--nome-cluster",
            "meu_cluster",
        ],
    )
    assert resultado.exit_code == 0, saida(resultado)
    assert sorted(p.name for p in out.iterdir()) == [
        "RJO001.gpkg",
        "RJO001.meta.json",
        "RJO002.gpkg",
        "RJO002.meta.json",
        "meu_cluster.gpkg",
        "meu_cluster.meta.json",
    ]
    texto = saida(resultado)
    assert "Feições por camada e recorte" in texto and "meu_cluster" in texto
    assert "INTERLIGACOES" in texto
    assert "⚠ RJO001: PONNOT: 1 feição(ões) fora do bbox da rede" in texto
    assert pyogrio.read_info(out / "RJO001.gpkg", layer="PONNOT")["features"] == 14

    # --folga-bbox negativo desliga o filtro (comportamento anterior à issue #40)
    out2 = tmp_path / "sem_filtro"
    resultado = runner.invoke(
        app,
        ["recortar", "--parquet", str(parquet_mini), "--ctmt", "RJO001", "--out", str(out2)]
        + ["--folga-bbox", "-1"],
    )
    assert resultado.exit_code == 0, saida(resultado)
    assert "fora do bbox" not in saida(resultado)
    assert pyogrio.read_info(out2 / "RJO001.gpkg", layer="PONNOT")["features"] == 15
    meta = json.loads((out2 / "RJO001.meta.json").read_text(encoding="utf-8"))
    assert meta["bbox_folga_m"] is None and meta["avisos"] == []


def test_cli_recortar_um_ctmt_com_out_gpkg(parquet_mini, tmp_path):
    destino = tmp_path / "saida" / "rjo3.gpkg"
    resultado = runner.invoke(
        app,
        ["recortar", "--parquet", str(parquet_mini), "--ctmt", "RJO003", "--out", str(destino)],
    )
    assert resultado.exit_code == 0, saida(resultado)
    assert destino.exists() and destino.with_suffix(".meta.json").exists()
    assert sorted(p.name for p in destino.parent.iterdir()) == ["rjo3.gpkg", "rjo3.meta.json"]
    assert pyogrio.read_info(destino, layer="CTMT")["features"] == 1


def test_cli_recortar_erros_claros(parquet_mini, tmp_path):
    erro = runner.invoke(
        app, ["recortar", "--parquet", str(parquet_mini), "--ctmt", "XPTO", "--out", str(tmp_path)]
    )
    assert erro.exit_code == 1 and "Erro" in saida(erro) and "XPTO" in saida(erro)
    assert "Traceback" not in saida(erro)
    varios = runner.invoke(
        app,
        [
            "recortar",
            "--parquet",
            str(parquet_mini),
            "--ctmt",
            "RJO001,RJO002",
            "--out",
            str(tmp_path / "x.gpkg"),
        ],
    )
    assert varios.exit_code == 1 and "deve ser um diretório" in saida(varios)
    sem_parquet = runner.invoke(
        app, ["recortar", "--parquet", str(tmp_path / "nada"), "--ctmt", "RJO001"]
    )
    assert sem_parquet.exit_code == 1 and "não encontrado" in saida(sem_parquet)


def test_cli_help_lista_novos_comandos():
    ajuda = runner.invoke(app, ["--help"])
    for comando in ("export", "inventario", "vizinhos", "recortar"):
        assert comando in saida(ajuda)
    for comando, opcoes in (
        ("inventario", ("--parquet", "--out", "--top", "--bairro", "--raio-tie")),
        ("vizinhos", ("--ctmt", "--parquet", "--raio-tie")),
        ("recortar", ("--ctmt", "--parquet", "--out", "--nome-cluster", "--raio-tie")),
    ):
        texto = saida(runner.invoke(app, [comando, "--help"]))
        for opcao in opcoes:
            assert opcao in texto, (comando, opcao)
