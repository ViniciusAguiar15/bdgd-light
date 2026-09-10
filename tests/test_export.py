"""Testes de ``bdgd_light.ingest.export`` e do comando ``bdgd-light export``.

Usam a BDGD sintética ``tests/fixtures/bdgd_mini.gpkg`` (ver ``gerar_fixture.py``).
"""

from __future__ import annotations

import io
import json
import re

import geopandas as gpd
import pandas as pd
import pyarrow.parquet as pq
import pyogrio
import pytest
from geopandas.testing import assert_geodataframe_equal
from rich.console import Console
from typer.testing import CliRunner

from bdgd_light.catalogo import CAMADAS_CHAVE
from bdgd_light.cli import app
from bdgd_light.ingest.export import (
    CamadaInexistenteError,
    exportar,
    exportar_camada,
    listar_camadas,
    resolver_camadas,
)

CAMADAS_FIXTURE = {"CTMT": 3, "SSDMT": 5, "UNSEMT": 4, "UCBT": 5, "UCBT_tab": 5}
GEOGRAFICAS = {"SSDMT": "MultiLineString", "UNSEMT": "Point", "UCBT": "Point"}
TABELAS = ("CTMT", "UCBT_tab")
ENE = [f"ENE_{m:02d}" for m in range(1, 13)]

runner = CliRunner()
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def console_silenciosa() -> Console:
    return Console(file=io.StringIO(), width=200)


def saida(resultado) -> str:
    """Saída da CLI sem códigos ANSI (no GitHub Actions o typer força cores no rich)."""
    return _ANSI.sub("", resultado.output)


# --- fixture sintética -------------------------------------------------------------------------


def test_fixture_reproduz_estrutura_da_bdgd(bdgd_mini):
    camadas = listar_camadas(bdgd_mini)
    assert set(camadas) == set(CAMADAS_FIXTURE)
    for camada, geom in GEOGRAFICAS.items():
        assert camadas[camada] == geom
        assert pyogrio.read_info(bdgd_mini, layer=camada)["crs"] == "EPSG:4674"
    for camada in TABELAS:
        assert camadas[camada] is None
    for camada, n in CAMADAS_FIXTURE.items():
        assert pyogrio.read_info(bdgd_mini, layer=camada)["features"] == n
    chaves = gpd.read_file(bdgd_mini, layer="UNSEMT", engine="pyogrio")
    assert {"COD_ID", "CTMT", "PAC_1", "PAC_2", "P_N_OPE"} <= set(chaves.columns)
    assert chaves["P_N_OPE"].value_counts().to_dict() == {"F": 3, "A": 1}


def test_fixture_commitada_em_sincronia_com_o_gerador(bdgd_mini, gerador, tmp_path):
    regenerada = gerador.gerar(tmp_path / "regenerada.gpkg")
    assert listar_camadas(regenerada) == listar_camadas(bdgd_mini)
    for camada in CAMADAS_FIXTURE:
        atual = pyogrio.read_dataframe(bdgd_mini, layer=camada)
        nova = pyogrio.read_dataframe(regenerada, layer=camada)
        if camada in GEOGRAFICAS:
            assert_geodataframe_equal(atual, nova)
        else:
            pd.testing.assert_frame_equal(atual, nova)


# --- módulo export ------------------------------------------------------------------------------


def test_exporta_geograficas_como_geoparquet_em_epsg4674(bdgd_mini, tmp_path):
    resultados = exportar(bdgd_mini, list(CAMADAS_FIXTURE), tmp_path, console=console_silenciosa())
    assert [r.camada for r in resultados] == list(CAMADAS_FIXTURE)
    assert {r.camada: r.feicoes for r in resultados} == CAMADAS_FIXTURE
    assert {r.camada: r.geometria for r in resultados if not r.eh_tabela} == GEOGRAFICAS
    for camada, tipo in GEOGRAFICAS.items():
        arquivo = tmp_path / f"{camada}.parquet"
        gdf = gpd.read_parquet(arquivo)
        assert len(gdf) == CAMADAS_FIXTURE[camada]
        assert gdf.crs.to_epsg() == 4674
        assert gdf.geometry.name == "geometry"
        assert set(gdf.geom_type) == {tipo}
        geo = json.loads(pq.read_metadata(arquivo).metadata[b"geo"])
        assert geo["primary_column"] == "geometry"
        assert geo["columns"]["geometry"]["encoding"] == "WKB"
        assert geo["columns"]["geometry"]["geometry_types"] == [tipo]
        assert geo["columns"]["geometry"]["crs"]["name"] == "SIRGAS 2000"
        assert gdf.total_bounds.tolist() == pytest.approx(geo["columns"]["geometry"]["bbox"])


def test_exporta_tabelas_sem_geometria_como_parquet(bdgd_mini, tmp_path):
    resultados = exportar(bdgd_mini, TABELAS, tmp_path, console=console_silenciosa())
    assert all(r.eh_tabela for r in resultados)

    ctmt = pd.read_parquet(tmp_path / "CTMT.parquet")
    assert "geometry" not in ctmt.columns
    assert b"geo" not in (pq.read_metadata(tmp_path / "CTMT.parquet").metadata or {})
    assert ctmt["COD_ID"].tolist() == ["RJO001", "RJO002", "RJO003"]
    assert {"NOME", "SUB", "PAC_INI", "TEN_NOM", "UNI_TR_AT", *ENE} <= set(ctmt.columns)
    assert ctmt["DIST"].dtype == "int32"
    assert ctmt.set_index("COD_ID").loc["RJO001", "SUB"] == "SE001"

    ucbt = pd.read_parquet(tmp_path / "UCBT_tab.parquet")
    assert len(ucbt) == 5 and "geometry" not in ucbt.columns
    assert {"COD_ID", "CTMT", "PAC", "UNI_TR_MT", "CLAS_SUB", "CAR_INST", *ENE} <= set(ucbt.columns)
    assert ucbt["CTMT"].value_counts().to_dict() == {"RJO001": 3, "RJO002": 2}
    assert (ucbt[ENE] > 0).all().all()


def test_chaves_preservam_atributos_e_geometria(bdgd_mini, tmp_path):
    resultado = exportar_camada(bdgd_mini, "UNSEMT", tmp_path)
    assert resultado.feicoes == 4 and resultado.geometria == "Point"
    assert resultado.parquet == tmp_path / "UNSEMT.parquet" and resultado.gpkg is None

    chaves = gpd.read_parquet(resultado.parquet)
    original = gpd.read_file(bdgd_mini, layer="UNSEMT", engine="pyogrio")
    assert set(chaves.columns) == set(original.columns)
    assert chaves.geometry.geom_equals(original.geometry).all()
    assert chaves["P_N_OPE"].value_counts().to_dict() == {"F": 3, "A": 1}
    na = chaves[chaves["P_N_OPE"] == "A"].iloc[0]
    assert (na["PAC_1"], na["PAC_2"]) == ("RJO001_MT_5", "RJO002_MT_4")
    assert na.geometry.x == pytest.approx(-43.196) and na.geometry.y == pytest.approx(-22.9105)


def test_lotes_pequenos_gravam_todas_as_feicoes(bdgd_mini, tmp_path):
    inteiro = exportar_camada(bdgd_mini, "UCBT", tmp_path / "inteiro")
    em_lotes = exportar_camada(bdgd_mini, "UCBT", tmp_path / "lotes", batch_size=2)
    assert inteiro.feicoes == em_lotes.feicoes == 5
    assert pq.read_metadata(inteiro.parquet).num_row_groups == 1
    assert pq.read_metadata(em_lotes.parquet).num_row_groups == 3
    assert_geodataframe_equal(gpd.read_parquet(inteiro.parquet), gpd.read_parquet(em_lotes.parquet))

    avancos: list[int] = []
    exportar_camada(bdgd_mini, "UCBT", tmp_path / "prog", batch_size=2, ao_avancar=avancos.append)
    assert avancos == [2, 2, 1]


def test_gpkg_unico_com_camadas_geograficas_e_tabelas(bdgd_mini, tmp_path):
    gpkg = tmp_path / "saida" / "bdgd.gpkg"
    resultados = exportar(
        bdgd_mini,
        list(CAMADAS_FIXTURE),
        tmp_path / "parquet",
        gpkg=gpkg,
        batch_size=2,
        console=console_silenciosa(),
    )
    assert all(r.gpkg == gpkg for r in resultados)
    camadas = listar_camadas(gpkg)
    assert set(camadas) == set(CAMADAS_FIXTURE)
    assert camadas["SSDMT"] == "MultiLineString" and camadas["CTMT"] is None
    for camada, n in CAMADAS_FIXTURE.items():
        assert pyogrio.read_info(gpkg, layer=camada)["features"] == n
    ssdmt = gpd.read_file(gpkg, layer="SSDMT", engine="pyogrio")
    original = gpd.read_file(bdgd_mini, layer="SSDMT", engine="pyogrio")
    assert ssdmt.crs.to_epsg() == 4674
    assert ssdmt["COMP"].sum() == pytest.approx(original["COMP"].sum())
    assert ssdmt.geometry.geom_equals(original.geometry).all()

    # reexportar substitui a camada no GeoPackage em vez de duplicar feições
    exportar(bdgd_mini, ["UNSEMT"], tmp_path / "parquet", gpkg=gpkg, console=console_silenciosa())
    assert pyogrio.read_info(gpkg, layer="UNSEMT")["features"] == 4
    assert set(listar_camadas(gpkg)) == set(CAMADAS_FIXTURE)


def test_sem_layers_usa_camadas_chave_e_pula_ausentes_com_aviso(bdgd_mini, tmp_path):
    saida = io.StringIO()
    resultados = exportar(bdgd_mini, None, tmp_path, console=Console(file=saida, width=200))
    assert [r.camada for r in resultados] == [c for c in CAMADAS_CHAVE if c in CAMADAS_FIXTURE]
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        f"{c}.parquet" for c in CAMADAS_FIXTURE
    )
    log = saida.getvalue()
    assert "Aviso" in log and "SSDBT" in log and "pulada" in log
    assert "3 feições" in log and "Resumo da exportação" in log


def test_resolver_camadas_ignora_caixa_e_duplicatas():
    disponiveis = ["CTMT", "UCBT_tab"]
    assert resolver_camadas(disponiveis, ["ctmt", " CTMT ", "ucbt_TAB"]) == (
        ["CTMT", "UCBT_tab"],
        [],
    )
    assert resolver_camadas(disponiveis, None) == (
        ["CTMT", "UCBT_tab"],
        [c for c in CAMADAS_CHAVE if c not in disponiveis],
    )
    with pytest.raises(CamadaInexistenteError, match="SUB") as info:
        resolver_camadas(disponiveis, ["CTMT", "SUB"])
    assert info.value.ausentes == ["SUB"]
    assert "UCBT_tab" in str(info.value)  # lista as camadas disponíveis para ajudar


def test_base_inexistente_levanta_erro_claro(tmp_path):
    with pytest.raises(FileNotFoundError, match="não encontrada"):
        exportar(tmp_path / "nada.gdb", ["CTMT"], tmp_path, console=console_silenciosa())


# --- CLI ----------------------------------------------------------------------------------------


def test_cli_camada_inexistente_da_erro_claro_sem_traceback(bdgd_mini, tmp_path):
    resultado = runner.invoke(
        app,
        [
            "export",
            "--gdb",
            str(bdgd_mini),
            "--layers",
            "CTMT,NAOEXISTE",
            "--out",
            str(tmp_path / "p"),
        ],
    )
    assert resultado.exit_code == 1
    assert isinstance(resultado.exception, SystemExit)  # saída limpa, não exceção não tratada
    assert "Erro" in saida(resultado) and "NAOEXISTE" in saida(resultado)
    assert "Traceback" not in saida(resultado)
    assert not (tmp_path / "p").exists()  # falha antes de gravar qualquer coisa


def test_cli_base_inexistente_da_erro_claro(tmp_path):
    resultado = runner.invoke(
        app, ["export", "--gdb", str(tmp_path / "nada.gdb"), "--out", str(tmp_path / "p")]
    )
    assert resultado.exit_code == 1 and isinstance(resultado.exception, SystemExit)
    assert "Erro" in saida(resultado) and "não encontrada" in saida(resultado)


def test_cli_arquivo_invalido_da_erro_claro(tmp_path):
    invalido = tmp_path / "x.gdb"
    invalido.write_text("não sou uma geodatabase")
    resultado = runner.invoke(app, ["export", "--gdb", str(invalido), "--out", str(tmp_path / "p")])
    assert resultado.exit_code == 1 and isinstance(resultado.exception, SystemExit)
    assert "Erro" in saida(resultado) and "não foi possível abrir" in saida(resultado)


def test_cli_exporta_com_layers_out_e_gpkg(bdgd_mini, tmp_path):
    gpkg = tmp_path / "bdgd.gpkg"
    resultado = runner.invoke(
        app,
        [
            "export",
            "--gdb",
            str(bdgd_mini),
            "--layers",
            "ctmt,UNSEMT",
            "--out",
            str(tmp_path / "parquet"),
            "--gpkg",
            str(gpkg),
            "--batch-size",
            "2",
        ],
    )
    assert resultado.exit_code == 0, saida(resultado)
    assert sorted(p.name for p in (tmp_path / "parquet").iterdir()) == [
        "CTMT.parquet",
        "UNSEMT.parquet",
    ]
    assert set(listar_camadas(gpkg)) == {"CTMT", "UNSEMT"}
    assert "4 feições" in saida(resultado) and "Resumo da exportação" in saida(resultado)


def test_cli_help_e_versao():
    ajuda = runner.invoke(app, ["--help"])
    assert ajuda.exit_code == 0 and "export" in saida(ajuda)
    ajuda_export = runner.invoke(app, ["export", "--help"])
    assert ajuda_export.exit_code == 0
    for opcao in ("--gdb", "--layers", "--out", "--gpkg", "--batch-size"):
        assert opcao in saida(ajuda_export)
    versao = runner.invoke(app, ["--version"])
    assert versao.exit_code == 0 and "bdgd-light" in saida(versao)
