#!/usr/bin/env python3
"""Gera ``tests/fixtures/bdgd_mini.gpkg``: uma BDGD sintética mínima para os testes.

Reproduz a estrutura da BDGD da Light 2025 V11 (nomes de camadas, colunas e tipos reais, CRS
SIRGAS 2000 — EPSG:4674), com 3–5 feições por camada e valores inventados:

- ``CTMT`` (tabela, sem geometria — como na BDGD real): 3 alimentadores; RJO001 e RJO002 saem da
  mesma subestação (SE001) e RJO003 de outra (SE002).
- ``SSDMT`` (MultiLineString): 5 trechos MT encadeados por ``PAC_1``/``PAC_2``.
- ``UNSEMT`` (Point): 4 chaves — 3 NF (``P_N_OPE = "F"``) e 1 NA (``"A"``) que interliga
  RJO001 e RJO002 (cenário de transferência de carga/FLISR).
- ``UCBT`` (Point) e ``UCBT_tab`` (tabela): 5 unidades consumidoras BT com energia mensal
  ``ENE_01..ENE_12``.

Uso: ``uv run tests/fixtures/gerar_fixture.py [destino.gpkg]``
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely.geometry import MultiLineString, Point

CRS_BDGD = "EPSG:4674"
CAMINHO_PADRAO = Path(__file__).with_name("bdgd_mini.gpkg")
DIST = 382  # código ANEEL da Light
MUN_RIO = "3304557"  # código IBGE do Rio de Janeiro

# Pontos de acoplamento (PAC) da rede MT sintética, em graus (lon, lat), zona norte do Rio.
PACS = {
    "RJO001_MT_1": (-43.2000, -22.9100),
    "RJO001_MT_2": (-43.1990, -22.9100),
    "RJO001_MT_3": (-43.1988, -22.9100),
    "RJO001_MT_4": (-43.1978, -22.9100),
    "RJO001_MT_5": (-43.1968, -22.9100),
    "RJO002_MT_1": (-43.1930, -22.9110),
    "RJO002_MT_2": (-43.1940, -22.9110),
    "RJO002_MT_3": (-43.1942, -22.9110),
    "RJO002_MT_4": (-43.1952, -22.9110),
    "RJO003_MT_1": (-43.2100, -22.9200),
    "RJO003_MT_2": (-43.2098, -22.9200),
}
# subestação e transformador AT/MT (UNTRAT) de cada alimentador
ALIMENTADORES = {
    "RJO001": ("SE001", "TRAT001"),
    "RJO002": ("SE001", "TRAT001"),
    "RJO003": ("SE002", "TRAT002"),
}


def _energia_mensal(base: float) -> dict[str, float]:
    """Energia (kWh) de janeiro a dezembro com leve sazonalidade, colunas ENE_01..ENE_12."""
    fator = 1 + 0.10 * np.cos(np.arange(12) * np.pi / 6)
    return {f"ENE_{m + 1:02d}": round(base * fator[m], 2) for m in range(12)}


def _int32(df: pd.DataFrame, colunas: list[str]) -> pd.DataFrame:
    df[colunas] = df[colunas].astype("int32")
    return df


def ctmt() -> pd.DataFrame:
    linhas = []
    for i, (cod, (sub, trat)) in enumerate(ALIMENTADORES.items(), start=1):
        linhas.append(
            {
                "COD_ID": cod,
                "NOME": f"AL SINTETICO {i:02d}",
                "BARR": f"BAR00{i}",
                "SUB": sub,
                "PAC_INI": f"{cod}_MT_1",
                "TEN_NOM": "46",  # código BDGD para 13,8 kV
                "TEN_OPE": 1.045,
                "ATIP": 0,
                "RECONFIG": 0,
                "DIST": DIST,
                "UNI_TR_AT": trat,
                **_energia_mensal(1_500_000.0 * i),
                "DESCR": f"AL SINTETICO {i:02d}",
            }
        )
    return _int32(pd.DataFrame(linhas), ["ATIP", "RECONFIG", "DIST"])


def _trecho(cod: str, ctmt_id: str, pac_1: str, pac_2: str, pn: int) -> dict:
    sub, trat = ALIMENTADORES[ctmt_id]
    p1, p2 = PACS[pac_1], PACS[pac_2]
    comp = float(np.hypot((p2[0] - p1[0]) * 102_500, (p2[1] - p1[1]) * 111_300))  # ~metros
    return {
        "COD_ID": cod,
        "PN_CON_1": f"PN{pn:03d}",
        "PN_CON_2": f"PN{pn + 1:03d}",
        "CTMT": ctmt_id,
        "UNI_TR_AT": trat,
        "SUB": sub,
        "CONJ": 1,
        "DIST": DIST,
        "PAC_1": pac_1,
        "PAC_2": pac_2,
        "FAS_CON": "ABC",
        "TIP_CND": "CAB001",
        "POS": "PD",
        "COMP": round(comp, 2),
        "DESCR": "",
        "geometry": MultiLineString([[p1, p2]]),
    }


def ssdmt() -> gpd.GeoDataFrame:
    linhas = [
        _trecho("SEG001", "RJO001", "RJO001_MT_1", "RJO001_MT_2", 1),
        _trecho("SEG002", "RJO001", "RJO001_MT_3", "RJO001_MT_4", 3),
        _trecho("SEG003", "RJO001", "RJO001_MT_4", "RJO001_MT_5", 4),
        _trecho("SEG004", "RJO002", "RJO002_MT_1", "RJO002_MT_2", 11),
        _trecho("SEG005", "RJO002", "RJO002_MT_3", "RJO002_MT_4", 13),
    ]
    gdf = gpd.GeoDataFrame(linhas, geometry="geometry", crs=CRS_BDGD)
    return _int32(gdf, ["CONJ", "DIST"])


def _chave(cod: str, ctmt_id: str, pac_1: str, pac_2: str, estado: str, fas_con: str) -> dict:
    sub, trat = ALIMENTADORES[ctmt_id]
    p1, p2 = PACS[pac_1], PACS[pac_2]
    return {
        "COD_ID": cod,
        "DIST": DIST,
        "PAC_1": pac_1,
        "PAC_2": pac_2,
        "FAS_CON": fas_con,
        "SIT_ATIV": "AT",
        "TIP_UNID": "22",
        "P_N_OPE": estado,  # F = normalmente fechada (NF); A = normalmente aberta (NA)
        "CAP_ELO": "",
        "TLCD": 0,
        "DAT_CON": "2010-01-01",
        "POS": "PD",
        "CTMT": ctmt_id,
        "UNI_TR_AT": trat,
        "SUB": sub,
        "CONJ": 1,
        "MUN": MUN_RIO,
        "DESCR": "",
        "geometry": Point((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2),
    }


def unsemt() -> gpd.GeoDataFrame:
    linhas = [
        _chave("CH001", "RJO001", "RJO001_MT_2", "RJO001_MT_3", "F", "ABC"),
        _chave("CH002", "RJO002", "RJO002_MT_2", "RJO002_MT_3", "F", "ABC"),
        _chave("CH003", "RJO001", "RJO001_MT_5", "RJO002_MT_4", "A", "ABC"),  # NA de interligação
        _chave("CH004", "RJO003", "RJO003_MT_1", "RJO003_MT_2", "F", "AB"),
    ]
    gdf = gpd.GeoDataFrame(linhas, geometry="geometry", crs=CRS_BDGD)
    return _int32(gdf, ["DIST", "TLCD", "CONJ"])


def _uc(n: int, ctmt_id: str, trafo: str, pac_mt: str, fas_con: str, car_inst: float) -> dict:
    sub, trat = ALIMENTADORES[ctmt_id]
    x, y = PACS[pac_mt]
    return {
        "COD_ID": f"UC{n:05d}",
        "DIST": DIST,
        "PAC": f"{trafo}_BT_{n}",
        "RAMAL": f"RM{n:03d}",
        "PN_CON": f"PN{100 + n:03d}",
        "UNI_TR_MT": trafo,
        "CTMT": ctmt_id,
        "UNI_TR_AT": trat,
        "SUB": sub,
        "CONJ": 1,
        "MUN": MUN_RIO,
        "BRR": "CENTRO",
        "CEP": "20000000",
        "CLAS_SUB": "RE1",
        "TIP_CC": "RES-Tipo3",
        "FAS_CON": fas_con,
        "GRU_TEN": "BT",
        "TEN_FORN": "11",
        "GRU_TAR": "B1",
        "SIT_ATIV": "AT",
        "DAT_CON": "2015-06-01",
        "CAR_INST": car_inst,
        "LIV": 0,
        **_energia_mensal(120.0 * n),
        "SEMRED": 0,
        "DESCR": "",
        "geometry": Point(x + 0.00005 * n, y - 0.00010),
    }


def ucbt() -> gpd.GeoDataFrame:
    linhas = [
        _uc(1, "RJO001", "TR001", "RJO001_MT_4", "AN", 0.216),
        _uc(2, "RJO001", "TR001", "RJO001_MT_4", "AN", 0.248),
        _uc(3, "RJO001", "TR001", "RJO001_MT_4", "ABN", 0.615),
        _uc(4, "RJO002", "TR002", "RJO002_MT_4", "AN", 0.288),
        _uc(5, "RJO002", "TR002", "RJO002_MT_4", "ABCN", 1.100),
    ]
    gdf = gpd.GeoDataFrame(linhas, geometry="geometry", crs=CRS_BDGD)
    return _int32(gdf, ["DIST", "CONJ", "LIV", "SEMRED"])


def ucbt_tab() -> pd.DataFrame:
    return pd.DataFrame(ucbt().drop(columns="geometry"))


CAMADAS = {"CTMT": ctmt, "SSDMT": ssdmt, "UNSEMT": unsemt, "UCBT": ucbt, "UCBT_tab": ucbt_tab}


def gerar(caminho: Path = CAMINHO_PADRAO) -> Path:
    """(Re)cria o GeoPackage sintético em ``caminho`` e devolve o caminho."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.unlink(missing_ok=True)
    for nome, fabrica in CAMADAS.items():
        dados = fabrica()
        if isinstance(dados, gpd.GeoDataFrame):
            dados.to_file(caminho, layer=nome, driver="GPKG", engine="pyogrio")
        else:
            pyogrio.write_dataframe(dados, caminho, layer=nome, driver="GPKG")
    return caminho


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else CAMINHO_PADRAO
    print(f"Fixture gerada em {gerar(destino)}")
