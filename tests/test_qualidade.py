"""Testes do perfil de qualidade da BDGD."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point, Polygon

from bdgd_light.qualidade import ConfiguracaoQualidade, analisar_qualidade, renderizar_markdown

# coordenadas em EPSG:4674; a distância P2 ↔ TRA1 passa de 2 km e cai fora da bbox de ARAT.


def escrever_base_sintetica(destino: Path) -> Path:
    destino.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        [
            {
                "DIST": 382,
                "DAT_INC": "01/01/2025",
                "DAT_FNL": "31/12/2025",
                "DAT_EXT": "18/08/2026",
                "DESCR": "BASE SINTETICA",
            }
        ]
    ).to_parquet(destino / "BASE.parquet", index=False)

    pd.DataFrame([{"COD_ID": "A"}, {"COD_ID": "B"}, {"COD_ID": "C"}]).to_parquet(
        destino / "CTMT.parquet", index=False
    )

    pd.DataFrame([{"COD_ID": "CAB1"}]).to_parquet(destino / "SEGCON.parquet", index=False)

    gpd.GeoDataFrame(
        [{"COD_ID": "ARAT1"}],
        geometry=[
            Polygon([(-43.02, -22.02), (-42.98, -22.02), (-42.98, -21.98), (-43.02, -21.98)])
        ],
        crs="EPSG:4674",
    ).to_parquet(destino / "ARAT.parquet", index=False)

    gpd.GeoDataFrame(
        [
            {"COD_ID": "TRA1", "CTMT": "A"},
            {"COD_ID": "TRB1", "CTMT": "B"},
        ],
        geometry=[Point(-43.0, -22.0), Point(-43.005, -22.005)],
        crs="EPSG:4674",
    ).to_parquet(destino / "UNTRMT.parquet", index=False)

    gpd.GeoDataFrame(
        [
            {"COD_ID": "P1"},
            {"COD_ID": "P2"},
            {"COD_ID": "P3"},
        ],
        geometry=[Point(-43.0005, -22.0), Point(-43.04, -22.0), Point(-43.0045, -22.0045)],
        crs="EPSG:4674",
    ).to_parquet(destino / "PONNOT.parquet", index=False)

    pd.DataFrame(
        [
            {"COD_ID": "UC1", "PN_CON": "P1", "UNI_TR_MT": "TRA1", "CTMT": "A", "FAS_CON": "AN"},
            {"COD_ID": "UC2", "PN_CON": "P2", "UNI_TR_MT": "TRA1", "CTMT": "A", "FAS_CON": "AN"},
            {"COD_ID": "UC3", "PN_CON": "P3", "UNI_TR_MT": "TRB1", "CTMT": "B", "FAS_CON": "ABCN"},
            {"COD_ID": "UC4", "PN_CON": "P1", "UNI_TR_MT": "TRA1", "CTMT": "Z", "FAS_CON": "AN"},
        ]
    ).to_parquet(destino / "UCBT_tab.parquet", index=False)

    pd.DataFrame(
        [{"COD_ID": "UM1", "PAC": "PAC_SHARED", "CTMT": "B", "PN_CON": "P3", "FAS_CON": "AN"}]
    ).to_parquet(destino / "UCMT_tab.parquet", index=False)

    pd.DataFrame([{"COD_ID": "UG1", "PAC": "PAC_SHARED", "CTMT": "A", "FAS_CON": "AN"}]).to_parquet(
        destino / "UGMT_tab.parquet", index=False
    )

    pd.DataFrame(
        [
            {
                "COD_ID": "RM1",
                "CTMT": "A",
                "UNI_TR_MT": "TRA1",
                "TIP_CND": "CAB1",
                "COMP": 100,
                "FAS_CON": "AN",
            },
            {
                "COD_ID": "RM2",
                "CTMT": "A",
                "UNI_TR_MT": "TRA1",
                "TIP_CND": "CABX",
                "COMP": 450,
                "FAS_CON": "AN",
            },
            {
                "COD_ID": "RM3",
                "CTMT": "Z",
                "UNI_TR_MT": "TRA1",
                "TIP_CND": "CABX",
                "COMP": 350,
                "FAS_CON": "AN",
            },
        ]
    ).to_parquet(destino / "RAMLIG.parquet", index=False)

    gpd.GeoDataFrame(
        [
            {
                "COD_ID": "SEG_A",
                "CTMT": "A",
                "PAC_1": "A_MT_1",
                "PAC_2": "PAC_SHARED",
                "TIP_CND": "CAB1",
                "FAS_CON": "ABC",
            },
            {
                "COD_ID": "SEG_B",
                "CTMT": "B",
                "PAC_1": "PAC_SHARED",
                "PAC_2": "B_MT_2",
                "TIP_CND": "CABX",
                "FAS_CON": "ABC",
            },
        ],
        geometry=[
            LineString([(-43.001, -22.001), (-43.0002, -22.0004)]),
            LineString([(-43.0048, -22.0048), (-43.004, -22.004)]),
        ],
        crs="EPSG:4674",
    ).to_parquet(destino / "SSDMT.parquet", index=False)

    gpd.GeoDataFrame(
        [{"COD_ID": "BT1", "CTMT": "A", "UNI_TR_MT": "TRA1", "TIP_CND": "", "FAS_CON": "AN"}],
        geometry=[LineString([(-43.0002, -22.0001), (-43.0001, -22.0)])],
        crs="EPSG:4674",
    ).to_parquet(destino / "SSDBT.parquet", index=False)

    gpd.GeoDataFrame(
        [
            {
                "COD_ID": "CH1",
                "CTMT": "A",
                "PAC_1": "A_MT_0",
                "PAC_2": "A_MT_1",
                "FAS_CON": "ABC",
                "TLCD": 1,
            },
            {
                "COD_ID": "CH2",
                "CTMT": "B",
                "PAC_1": "PAC_SHARED",
                "PAC_2": "B_MT_1",
                "FAS_CON": "ABC",
                "TLCD": 2,
            },
        ],
        geometry=[Point(-43.0008, -22.0002), Point(-43.0046, -22.0046)],
        crs="EPSG:4674",
    ).to_parquet(destino / "UNSEMT.parquet", index=False)

    gpd.GeoDataFrame(
        [{"COD_ID": "CHBT1", "CTMT": "A", "UNI_TR_MT": "TRA1", "FAS_CON": "AN", "TLCD": None}],
        geometry=[Point()],
        crs="EPSG:4674",
    ).to_parquet(destino / "UNSEBT.parquet", index=False)

    return destino


def carregar_script() -> object:
    spec = importlib.util.spec_from_file_location(
        "qualidade_script", Path("scripts/qualidade_bdgd.py")
    )
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_analisa_as_nove_verificacoes(tmp_path):
    base = escrever_base_sintetica(tmp_path / "parquet")
    resultado = analisar_qualidade(ConfiguracaoQualidade(parquet_dir=base))

    assert resultado.fonte.data_inicio == "01/01/2025"
    assert resultado.ramlig["contagem"] == 2
    assert resultado.ramlig["universo"] == 3
    assert resultado.pn_con["contagem"] == 1
    assert resultado.pn_con["universo"] == 4
    assert resultado.tip_cnd["contagem"] == 4
    assert resultado.ctmt["contagem"] == 2
    assert resultado.ctmt["ctmt_sem_referencia"]["contagem"] == 1
    assert resultado.pac["contagem"] == 1
    assert resultado.geometria["contagem"] == 1
    assert resultado.bbox["contagem"] == 1
    assert resultado.tlcd["contagem"] == 2
    assert "UCMT_tab não traz UNI_TR_MT" in resultado.pn_con["limitacoes"][0]
    assert resultado.pac["exemplos_detalhados"][0]["pac"] == "PAC_SHARED"


def test_renderizacao_deterministica_e_com_perguntas(tmp_path):
    base = escrever_base_sintetica(tmp_path / "parquet")
    resultado = analisar_qualidade(ConfiguracaoQualidade(parquet_dir=base))

    md1 = renderizar_markdown(resultado)
    md2 = renderizar_markdown(resultado)

    assert md1 == md2
    assert "# Qualidade do cadastro BDGD Light 2025" in md1
    assert "## Perguntas para a distribuidora" in md1
    assert "UCMT_tab não traz UNI_TR_MT" in md1
    assert "`UC2`" in md1
    assert "PAC_SHARED" in md1


def test_script_gera_o_mesmo_markdown_do_modulo(tmp_path, monkeypatch):
    base = escrever_base_sintetica(tmp_path / "parquet")
    saida = tmp_path / "qualidade.md"
    modulo = carregar_script()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qualidade_bdgd.py",
            "--parquet-dir",
            str(base),
            "--out",
            str(saida),
        ],
    )
    caminho = modulo.main()

    esperado = renderizar_markdown(analisar_qualidade(ConfiguracaoQualidade(parquet_dir=base)))
    assert caminho == saida
    assert saida.read_text(encoding="utf-8") == esperado
