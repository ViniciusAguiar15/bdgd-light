#!/usr/bin/env python3
"""Gera ``tests/fixtures/bdgd_mini.gpkg``: uma BDGD sintética mínima para os testes.

Reproduz a estrutura da BDGD da Light 2025 V11 (nomes de camadas, colunas e tipos reais, CRS
SIRGAS 2000 — EPSG:4674), com poucas feições por camada e valores inventados. Três alimentadores:

- ``RJO001`` e ``RJO002`` (LDA, 13,2 kV) saem da mesma subestação ``SE001`` e são **interligados
  geometricamente**, como na BDGD real: os ``PAC`` são numerados por alimentador e **nenhum PAC é
  compartilhado**; a interligação aparece porque uma chave NA (``P_N_OPE = "A"``) de um CTMT está
  a ~1 m de uma extremidade de trecho ``SSDMT`` do outro. São três ties: ``CH003`` (religador
  telecomandado de RJO001 junto ao fim de ``SEG007`` de RJO002), ``CH005`` (chave faca manual de
  RJO002 junto ao fim de ``SEG006`` de RJO001) e ``CH007`` (disjuntor de RJO002 dentro do pátio
  da ``SE001``, junto ao início de ``SEG001`` de RJO001 — o caso "tie de subestação").
  ``CH006`` é NA telecomandada de RJO001 que **não** é interligação (longe de outro CTMT): fecha
  um anel interno entre ``RJO001_MT_5`` e ``RJO001_MT_6``.
- Como na Light 2025, ``CTMT.PAC_INI`` é o ``PAC_1`` do disjuntor de saída (``CH008`` em RJO001,
  ``CH009`` em RJO002, ``TIP_UNID = 29``, NF) e não aparece em nenhum ``SSDMT``; RJO003 não tem
  disjuntor cadastrado, para exercitar o fallback do grafo (issue #6).
- ``RJO003`` (LSA, 25 kV) sai de ``SE002``, em outro município, e não tem interligação.

Também há uma UCBT (``UC00007``) cuja coluna ``CTMT`` diverge do CTMT do transformador (como em
0,09 % da base real): o inventário/recorte seguem o transformador (``UNI_TR_MT``). O poste dela
(``PN107``) fica a ~40 km da rede, como os ``PN_CON`` errados da base real (issue #40): o recorte
o descarta pelo *bbox* da rede, e ``UC00007`` segue em ``UCBT_tab`` sem poste.

Uso: ``uv run tests/fixtures/gerar_fixture.py [destino.gpkg]``
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely.geometry import MultiLineString, MultiPolygon, Point, box

CRS_BDGD = "EPSG:4674"
CAMINHO_PADRAO = Path(__file__).with_name("bdgd_mini.gpkg")
CAMINHO_BAIRRO = Path(__file__).with_name("bairro_sintetico.geojson")
DIST = 382  # código ANEEL da Light
MUN_RIO = "3304557"  # código IBGE do Rio de Janeiro
MUN_NOVA_IGUACU = "3303500"

# Pontos de acoplamento (PAC) da rede MT sintética, em graus (lon, lat), zona norte do Rio.
# 0,00001° ≈ 1,0 m em longitude e 1,1 m em latitude nesta latitude.
PACS = {
    "RJO001_MT_0": (-43.20003, -22.9100),  # PAC_INI: barra da SE001, lado fonte do disjuntor CH008
    "RJO001_MT_1": (-43.2000, -22.9100),
    "RJO001_MT_2": (-43.1990, -22.9100),
    "RJO001_MT_3": (-43.1988, -22.9100),
    "RJO001_MT_4": (-43.1978, -22.9100),
    "RJO001_MT_5": (-43.1968, -22.9100),
    "RJO001_MT_6": (-43.1978, -22.9106),
    "RJO001_MT_7": (-43.1968, -22.9100),  # lado "aberto" de CH003 (sem trecho)
    "RJO002_MT_0": (-43.19297, -22.9110),  # PAC_INI: lado fonte do disjuntor CH009
    "RJO002_MT_1": (-43.1930, -22.9110),
    "RJO002_MT_2": (-43.1940, -22.9110),
    "RJO002_MT_3": (-43.1942, -22.9110),
    "RJO002_MT_4": (-43.1952, -22.9110),
    "RJO002_MT_5": (-43.19681, -22.9100),  # ~1,0 m de RJO001_MT_5
    "RJO002_MT_6": (-43.1978, -22.91061),  # ~1,1 m de RJO001_MT_6
    "RJO002_MT_7": (-43.1978, -22.91061),  # lado "aberto" de CH005 (sem trecho)
    "RJO002_MT_8": (-43.20001, -22.9100),  # ~1,0 m de RJO001_MT_1, dentro da SE001
    "RJO002_MT_9": (-43.20001, -22.9100),  # lado "aberto" de CH007 (sem trecho)
    "RJO003_MT_1": (-43.2100, -22.9200),
    "RJO003_MT_2": (-43.2098, -22.9200),
    "RJO003_MT_3": (-43.2096, -22.9200),
}
# alimentador → (subestação, transformador AT/MT, tensão nominal (código TEN), nome, município)
ALIMENTADORES = {
    "RJO001": ("SE001", "TRAT001", "46", "LDA SINTETICO 01", MUN_RIO),
    "RJO002": ("SE001", "TRAT001", "46", "LDA SINTETICO 02", MUN_RIO),
    "RJO003": ("SE002", "TRAT002", "67", "LSA SINTETICO 03", MUN_NOVA_IGUACU),
}
SUBESTACOES = {
    "SE001": ("SETD SINTETICA 01", PACS["RJO001_MT_1"]),
    "SE002": ("SETD SINTETICA 02", PACS["RJO003_MT_1"]),
}
# transformador MT/BT → (alimentador, PAC MT, kVA)
TRAFOS = {
    "TR001": ("RJO001", "RJO001_MT_4", 75.0),
    "TR003": ("RJO001", "RJO001_MT_2", 45.0),
    "TR002": ("RJO002", "RJO002_MT_4", 112.5),
    "TR004": ("RJO003", "RJO003_MT_2", 150.0),
}
CODIGO_KVA = {45.0: "13", 75.0: "16", 112.5: "20", 150.0: "24"}  # domínio TPOTAPRT (EQTRMT.POT_NOM)


def _energia_mensal(base: float) -> dict[str, float]:
    """Energia (kWh) de janeiro a dezembro com leve sazonalidade, colunas ENE_01..ENE_12."""
    fator = 1 + 0.10 * np.cos(np.arange(12) * np.pi / 6)
    return {f"ENE_{m + 1:02d}": round(base * fator[m], 2) for m in range(12)}


def _int32(df: pd.DataFrame, colunas: list[str]) -> pd.DataFrame:
    df[colunas] = df[colunas].astype("int32")
    return df


def _geo(linhas: list[dict], inteiras: list[str]) -> gpd.GeoDataFrame:
    gdf = gpd.GeoDataFrame(linhas, geometry="geometry", crs=CRS_BDGD)
    return _int32(gdf, inteiras)


def _metros(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return float(np.hypot((p2[0] - p1[0]) * 102_500, (p2[1] - p1[1]) * 111_300))


def _comum(ctmt_id: str) -> dict:
    sub, trat, _, _, mun = ALIMENTADORES[ctmt_id]
    return {"CTMT": ctmt_id, "UNI_TR_AT": trat, "SUB": sub, "CONJ": 1, "MUN": mun}


# --- alimentadores e subestações ----------------------------------------------------------------


def ctmt() -> pd.DataFrame:
    linhas = []
    for i, (cod, (sub, trat, ten, nome, _)) in enumerate(ALIMENTADORES.items(), start=1):
        linhas.append(
            {
                "COD_ID": cod,
                "NOME": nome,
                "BARR": f"BAR00{i}",
                "SUB": sub,
                "PAC_INI": f"{cod}_MT_0",
                "TEN_NOM": ten,  # códigos BDGD: 46 = 13,2 kV; 67 = 25 kV
                "TEN_OPE": 1.045,
                "ATIP": 0,
                "RECONFIG": 0,
                "DIST": DIST,
                "UNI_TR_AT": trat,
                **_energia_mensal(1_500_000.0 * i),
                "DESCR": nome,
            }
        )
    return _int32(pd.DataFrame(linhas), ["ATIP", "RECONFIG", "DIST"])


def sub() -> gpd.GeoDataFrame:
    linhas = []
    for cod, (nome, (x, y)) in SUBESTACOES.items():
        # pátio de ~40 m × 40 m em torno do ponto inicial do alimentador
        poligono = MultiPolygon([box(x - 0.0002, y - 0.0002, x + 0.0002, y + 0.0002)])
        linhas.append(
            {
                "COD_ID": cod,
                "DIST": DIST,
                "POS": "PD",
                "NOME": nome,
                "DESCR": "",
                "geometry": poligono,
            }
        )
    return _geo(linhas, ["DIST"])


def untrat() -> gpd.GeoDataFrame:
    linhas = []
    for cod, se, pot in [("TRAT001", "SE001", 40_000.0), ("TRAT003", "SE001", 25_000.0),
                         ("TRAT002", "SE002", 20_000.0)]:  # fmt: skip
        x, y = SUBESTACOES[se][1]
        linhas.append(
            {
                "COD_ID": cod,
                "SUB": se,
                "BARR_1": f"BAR_AT_{cod}",
                "BARR_2": f"BAR_MT_{cod}",
                "BARR_3": "",
                "PAC_1": f"{cod}_AT_1",
                "PAC_2": f"{cod}_MT_1",
                "PAC_3": "",
                "DIST": DIST,
                "FAS_CON_P": "ABC",
                "FAS_CON_S": "ABC",
                "FAS_CON_T": "",
                "SIT_ATIV": "AT",
                "TIP_UNID": "41",
                "POS": "PD",
                "POT_NOM": pot,
                "PER_FER": 20.0,
                "PER_TOT": 150.0,
                "BANC": 0,
                "DAT_CON": "2000-01-01",
                "CONJ": 1,
                "MUN": MUN_RIO if se == "SE001" else MUN_NOVA_IGUACU,
                "TIP_TRAFO": "T",
                "DESCR": "",
                "geometry": Point(x + 0.00005, y + 0.00005),
            }
        )
    return _geo(linhas, ["DIST", "BANC", "CONJ"])


# --- rede MT ----------------------------------------------------------------------------------


def _trecho(cod: str, ctmt_id: str, pac_1: str, pac_2: str, pn: int) -> dict:
    p1, p2 = PACS[pac_1], PACS[pac_2]
    comum = _comum(ctmt_id)
    comum.pop("MUN")
    return {
        "COD_ID": cod,
        "PN_CON_1": f"PN{pn:03d}",
        "PN_CON_2": f"PN{pn + 1:03d}",
        **comum,
        "DIST": DIST,
        "PAC_1": pac_1,
        "PAC_2": pac_2,
        "FAS_CON": "ABC",
        "TIP_INST": "RD_AER_URB",
        "TIP_CND": "CAB001",
        "POS": "PD",
        "COMP": round(_metros(p1, p2), 2),
        "DESCR": "",
        "geometry": MultiLineString([[p1, p2]]),
    }


def ssdmt() -> gpd.GeoDataFrame:
    linhas = [
        _trecho("SEG001", "RJO001", "RJO001_MT_1", "RJO001_MT_2", 1),
        _trecho("SEG002", "RJO001", "RJO001_MT_3", "RJO001_MT_4", 3),
        _trecho("SEG003", "RJO001", "RJO001_MT_4", "RJO001_MT_5", 4),
        _trecho("SEG006", "RJO001", "RJO001_MT_4", "RJO001_MT_6", 5),
        _trecho("SEG004", "RJO002", "RJO002_MT_1", "RJO002_MT_2", 11),
        _trecho("SEG005", "RJO002", "RJO002_MT_3", "RJO002_MT_4", 13),
        _trecho("SEG007", "RJO002", "RJO002_MT_4", "RJO002_MT_5", 14),
        _trecho("SEG008", "RJO002", "RJO002_MT_4", "RJO002_MT_6", 15),
        _trecho("SEG009", "RJO003", "RJO003_MT_1", "RJO003_MT_2", 21),
    ]
    return _geo(linhas, ["CONJ", "DIST"])


def _chave(
    cod: str,
    ctmt_id: str,
    pac_1: str,
    pac_2: str,
    estado: str,
    *,
    fas_con: str = "ABC",
    tip_unid: str = "19",
    tlcd: int = 0,
    ponto: tuple[float, float] | None = None,
) -> dict:
    p1, p2 = PACS[pac_1], PACS[pac_2]
    if ponto is None:
        ponto = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    return {
        "COD_ID": cod,
        "DIST": DIST,
        "PAC_1": pac_1,
        "PAC_2": pac_2,
        "FAS_CON": fas_con,
        "SIT_ATIV": "AT",
        "TIP_UNID": tip_unid,  # 19 faca, 22 fusível, 29 disjuntor, 32 religador
        "P_N_OPE": estado,  # F = normalmente fechada (NF); A = normalmente aberta (NA)
        "CAP_ELO": "",
        "TLCD": tlcd,  # 1 = telecomandada
        "DAT_CON": "2010-01-01",
        "POS": "PD",
        **_comum(ctmt_id),
        "DESCR": "",
        "geometry": Point(ponto),
    }


def unsemt() -> gpd.GeoDataFrame:
    linhas = [
        _chave("CH001", "RJO001", "RJO001_MT_2", "RJO001_MT_3", "F", tip_unid="22"),
        _chave("CH002", "RJO002", "RJO002_MT_2", "RJO002_MT_3", "F"),
        # NA de interligação telecomandada de RJO001, junto ao fim de SEG007 (RJO002)
        _chave("CH003", "RJO001", "RJO001_MT_5", "RJO001_MT_7", "A", tip_unid="32", tlcd=1),
        _chave("CH004", "RJO003", "RJO003_MT_2", "RJO003_MT_3", "F", fas_con="AB", tip_unid="22"),
        # NA de interligação manual de RJO002, junto ao fim de SEG006 (RJO001)
        _chave("CH005", "RJO002", "RJO002_MT_6", "RJO002_MT_7", "A"),
        # NA telecomandada de RJO001 que NÃO é interligação (nenhum trecho de outro CTMT a 2 m);
        # fecha um anel interno SEG003 + SEG006 (pares de PAC nunca se repetem, como na base real)
        _chave(
            "CH006",
            "RJO001",
            "RJO001_MT_5",
            "RJO001_MT_6",
            "A",
            tip_unid="32",
            tlcd=1,
            ponto=(-43.1978, -22.9104),
        ),  # fmt: skip
        # NA (disjuntor) de RJO002 dentro do pátio da SE001, junto ao início de SEG001 (RJO001)
        _chave("CH007", "RJO002", "RJO002_MT_8", "RJO002_MT_9", "A", tip_unid="29", tlcd=1),
        # disjuntores de saída (NF): PAC_1 = CTMT.PAC_INI, PAC_2 = início do primeiro trecho
        _chave("CH008", "RJO001", "RJO001_MT_0", "RJO001_MT_1", "F", tip_unid="29", tlcd=1),
        _chave("CH009", "RJO002", "RJO002_MT_0", "RJO002_MT_1", "F", tip_unid="29", tlcd=1),
    ]
    return _geo(linhas, ["DIST", "TLCD", "CONJ"])


def untrmt() -> gpd.GeoDataFrame:
    linhas = []
    for cod, (ctmt_id, pac_mt, kva) in TRAFOS.items():
        x, y = PACS[pac_mt]
        linhas.append(
            {
                "COD_ID": cod,
                "DIST": DIST,
                "PAC_1": pac_mt,
                "PAC_2": f"{cod}_BT_0",
                "PAC_3": "",
                "FAS_CON_P": "ABC",
                "FAS_CON_S": "ABCN",
                "FAS_CON_T": "",
                "SIT_ATIV": "AT",
                "TIP_UNID": "38",
                "POS": "PD",
                "TEN_LIN_SE": 0.22,
                "TAP": 1.0,
                "POT_NOM": kva,
                "PER_FER": kva * 3.0,  # W (≈ NBR 5440: 0,3 % em vazio, 1,1 % em carga)
                "PER_TOT": kva * 14.0,
                "DAT_CON": "2012-03-01",
                **_comum(ctmt_id),
                "BANC": 0,
                "TIP_TRAFO": "T",
                "MRT": 0,
                "DESCR": "",
                "geometry": Point(x, y - 0.00003),
            }
        )
    return _geo(linhas, ["DIST", "CONJ", "BANC", "MRT"])


def unremt() -> gpd.GeoDataFrame:
    x, y = PACS["RJO003_MT_2"]
    linhas = [
        {
            "COD_ID": "RT001",
            "DIST": DIST,
            "FAS_CON": "ABC",
            "SIT_ATIV": "AT",
            "TIP_UNID": "40",
            "TIP_REGU": "1",
            "PAC_1": "RJO003_MT_2",
            "PAC_2": "RJO003_MT_3",
            **_comum("RJO003"),
            "DAT_CON": "2018-01-01",
            "BANC": 0,
            "POS": "PD",
            "DESCR": "",
            "geometry": Point(x + 0.0001, y),
        }
    ]
    return _geo(linhas, ["DIST", "CONJ", "BANC"])


def uncrmt() -> gpd.GeoDataFrame:
    x, y = PACS["RJO001_MT_3"]
    linhas = [
        {
            "COD_ID": "BC001",
            "DIST": DIST,
            "FAS_CON": "ABC",
            "SIT_ATIV": "AT",
            "TIP_UNID": "37",
            "POT_NOM": "600",
            "PAC_1": "RJO001_MT_3",
            "PAC_2": "",
            **_comum("RJO001"),
            "DAT_CON": "2016-01-01",
            "BANC": 0,
            "POS": "PD",
            "DESCR": "",
            "geometry": Point(x, y + 0.00002),
        }
    ]
    return _geo(linhas, ["DIST", "CONJ", "BANC"])


# --- rede BT ----------------------------------------------------------------------------------


def _trecho_bt(cod: str, trafo: str, n: int, pn: int) -> dict:
    ctmt_id, pac_mt, _ = TRAFOS[trafo]
    x, y = PACS[pac_mt]
    p1 = (x + 0.0001 * (n - 1), y - 0.0002)
    p2 = (x + 0.0001 * n, y - 0.0002)
    comum = _comum(ctmt_id)
    comum.pop("MUN")
    return {
        "COD_ID": cod,
        "PN_CON_1": f"PN{pn:03d}",
        "PN_CON_2": f"PN{pn + 1:03d}",
        "UNI_TR_MT": trafo,
        **comum,
        "FAS_CON": "ABCN",
        "DIST": DIST,
        "PAC_1": f"{trafo}_BT_{n - 1}",
        "PAC_2": f"{trafo}_BT_{n}",
        "TIP_INST": "RD_AER_URB",
        "TIP_CND": "CAB002",
        "POS": "PD",
        "COMP": round(_metros(p1, p2), 2),
        "DESCR": "",
        "geometry": MultiLineString([[p1, p2]]),
    }


def ssdbt() -> gpd.GeoDataFrame:
    linhas = [
        _trecho_bt("SBT001", "TR001", 1, 31),
        _trecho_bt("SBT002", "TR001", 2, 32),
        _trecho_bt("SBT003", "TR002", 1, 41),
        _trecho_bt("SBT004", "TR004", 1, 51),
    ]
    return _geo(linhas, ["CONJ", "DIST"])


def unsebt() -> gpd.GeoDataFrame:
    ctmt_id, pac_mt, _ = TRAFOS["TR001"]
    x, y = PACS[pac_mt]
    linhas = [
        {
            "COD_ID": "CHBT001",
            "DIST": DIST,
            "PAC_1": "TR001_BT_0",
            "PAC_2": "TR001_BT_1",
            "FAS_CON": "ABCN",
            "SIT_ATIV": "AT",
            "TIP_UNID": "46",
            "P_N_OPE": "F",
            "CAP_ELO": "",
            "COR_NOM": "",
            "TLCD": 0,
            "DAT_CON": "2012-03-01",
            "POS": "PD",
            "UNI_TR_MT": "TR001",
            **_comum(ctmt_id),
            "DESCR": "",
            "geometry": Point(x + 0.00005, y - 0.0002),
        }
    ]
    return _geo(linhas, ["DIST", "TLCD", "CONJ"])


def ramlig() -> pd.DataFrame:
    linhas = []
    for i, (trafo, n) in enumerate([("TR001", 1), ("TR002", 1), ("TR004", 1)], start=1):
        ctmt_id, _, _ = TRAFOS[trafo]
        comum = _comum(ctmt_id)
        comum.pop("MUN")
        linhas.append(
            {
                "COD_ID": f"RM{i:03d}",
                "PN_CON_1": f"PN{60 + i:03d}",
                "PN_CON_2": f"PN{100 + i:03d}",
                "DIST": DIST,
                "PAC_1": f"{trafo}_BT_{n}",
                "PAC_2": f"{trafo}_BT_{n}_UC",
                "UNI_TR_MT": trafo,
                **comum,
                "FAS_CON": "AN",
                "TIP_INST": "RD_AER_URB",
                "TIP_CND": "CAB002",
                "POS": "PD",
                "COMP": 15.0,
                "DESCR": "",
            }
        )
    return _int32(pd.DataFrame(linhas), ["CONJ", "DIST"])


def ponnot() -> gpd.GeoDataFrame:
    """Um poste (ponto notável) por PN_CON usado nos trechos MT/BT, ramais e UCs, mais um órfão."""
    pontos: dict[str, tuple[float, float]] = {}
    for camada in (ssdmt(), ssdbt()):
        for _, t in camada.iterrows():
            (x1, y1), (x2, y2) = t.geometry.geoms[0].coords[0], t.geometry.geoms[0].coords[-1]
            pontos.setdefault(t.PN_CON_1, (x1, y1))
            pontos.setdefault(t.PN_CON_2, (x2, y2))
    for _, r in ramlig().iterrows():
        pontos.setdefault(r.PN_CON_1, pontos.get(r.PN_CON_1, (-43.2, -22.91)))
    for tabela in (ucbt_tab(), ucmt_tab(), ugbt_tab(), ugmt_tab()):
        for _, u in tabela.iterrows():
            pontos.setdefault(u.PN_CON, (-43.2, -22.91))
    # poste de UC00007 a ~40 km da rede, como os PN_CON errados da Light 2025 (issue #40): o
    # recorte deve descartá-lo pelo bbox da rede
    pontos["PN107"] = (-43.6000, -23.0000)
    pontos["PN999"] = (-43.2300, -22.9500)  # poste sem nada ligado (não deve entrar em recortes)
    linhas = [
        {
            "COD_ID": pn,
            "DIST": DIST,
            "TIP_PN": "1",
            "TIP_INST": "RD_AER_URB",
            "POS": "PD",
            "ESTR": "",
            "MAT": "CO",
            "ESF": "",
            "ALT": "11",
            "CONJ": 1,
            "MUN": MUN_RIO,
            "DESCR": "",
            "geometry": Point(xy),
        }
        for pn, xy in sorted(pontos.items())
    ]
    return _geo(linhas, ["DIST", "CONJ"])


# --- consumidores e geração -----------------------------------------------------------------------


def _uc(n: int, trafo: str, pac_mt: str, fas_con: str, car_inst: float, ctmt_id: str) -> dict:
    x, y = PACS[pac_mt]
    return {
        "COD_ID": f"UC{n:05d}",
        "DIST": DIST,
        "PAC": f"{trafo}_BT_{n}",
        "RAMAL": f"RM{n:03d}",
        "PN_CON": f"PN{100 + n:03d}",
        "UNI_TR_MT": trafo,
        **_comum(ctmt_id),
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
        _uc(1, "TR001", "RJO001_MT_4", "AN", 0.216, "RJO001"),
        _uc(2, "TR001", "RJO001_MT_4", "AN", 0.248, "RJO001"),
        _uc(3, "TR001", "RJO001_MT_4", "ABN", 0.615, "RJO001"),
        _uc(4, "TR002", "RJO002_MT_4", "AN", 0.288, "RJO002"),
        _uc(5, "TR002", "RJO002_MT_4", "ABCN", 1.100, "RJO002"),
        _uc(6, "TR004", "RJO003_MT_2", "AN", 0.300, "RJO003"),
        # coluna CTMT divergente do CTMT do transformador TR003 (RJO001), como na base real
        _uc(7, "TR003", "RJO001_MT_2", "AN", 0.200, "RJO002"),
    ]
    return _geo(linhas, ["DIST", "CONJ", "LIV", "SEMRED"])


def ucbt_tab() -> pd.DataFrame:
    return pd.DataFrame(ucbt().drop(columns=["geometry"]))


def ucmt_tab() -> pd.DataFrame:
    linhas = []
    for n, (ctmt_id, pac_mt, ene) in enumerate(
        [("RJO001", "RJO001_MT_3", 60_000.0), ("RJO003", "RJO003_MT_2", 45_000.0)], start=1
    ):
        linhas.append(
            {
                "PN_CON": f"PN{200 + n:03d}",
                "DIST": DIST,
                "PAC": pac_mt,
                **_comum(ctmt_id),
                "CEG_GD": "",
                "BRR": "CENTRO",
                "CEP": "20000000",
                "CLAS_SUB": "CO1",
                "CNAE": "4711302",
                "TIP_CC": "COM-Tipo1",
                "FAS_CON": "ABC",
                "GRU_TEN": "MT",
                "TEN_FORN": "46",
                "GRU_TAR": "A4",
                "SIT_ATIV": "AT",
                "DAT_CON": "2014-01-01",
                "CAR_INST": 300.0,
                "LIV": 0,
                "TIP_SIST": "",
                **_energia_mensal(ene),
                "SEMRED": 0,
                "DESCR": "",
                "COD_ID": f"UCMT{n:03d}",
            }
        )
    return _int32(pd.DataFrame(linhas), ["DIST", "CONJ", "LIV", "SEMRED"])


def _ug(cod: str, ctmt_id: str, pn: str, pac: str, pot_kw: float, trafo: str | None) -> dict:
    linha = {
        "PN_CON": pn,
        "DIST": DIST,
        "PAC": pac,
        "CEG_GD": f"GD.RJ.{cod}",
        **({"UNI_TR_MT": trafo} if trafo else {}),
        **_comum(ctmt_id),
        "BRR": "CENTRO",
        "CEP": "20000000",
        "CNAE": "",
        "FAS_CON": "ABCN" if trafo else "ABC",
        "GRU_TEN": "BT" if trafo else "MT",
        "TEN_CON": "11" if trafo else "46",
        "SIT_ATIV": "AT",
        "DAT_CON": "2022-05-01",
        "POT_INST": pot_kw,
        "TIP_SIST": "UFV",
        **_energia_mensal(pot_kw * 110.0),
        "DESCR": "",
        "COD_ID": cod,
    }
    return linha


def ugbt_tab() -> pd.DataFrame:
    linhas = [
        _ug("UGBT001", "RJO001", "PN101", "TR001_BT_1", 5.0, "TR001"),
        _ug("UGBT002", "RJO002", "PN104", "TR002_BT_4", 10.0, "TR002"),
    ]
    return _int32(pd.DataFrame(linhas), ["DIST", "CONJ"])


def ugmt_tab() -> pd.DataFrame:
    linhas = [_ug("UGMT001", "RJO001", "PN201", "RJO001_MT_3", 500.0, None)]
    return _int32(pd.DataFrame(linhas), ["DIST", "CONJ"])


# --- tabelas auxiliares ---------------------------------------------------------------------------


def crvcrg() -> pd.DataFrame:
    linhas = []
    for cod in ("RES-Tipo3", "COM-Tipo1"):
        for dia in ("DU", "SA", "DO"):
            perfil = 0.5 + 0.5 * np.sin(np.linspace(0, np.pi, 96))
            linhas.append(
                {
                    "COD_ID": cod,
                    "DIST": DIST,
                    "TIP_DIA": dia,
                    **{f"POT_{i + 1:02d}": round(float(p), 4) for i, p in enumerate(perfil)},
                    "GRU_TEN": "BT" if cod.startswith("RES") else "MT",
                    "DESCR": "",
                }
            )
    return _int32(pd.DataFrame(linhas), ["DIST"])


def segcon() -> pd.DataFrame:
    linhas = [
        {"COD_ID": "CAB001", "DIST": DIST, "GEOM_CAB": "1", "FORM_CAB": "1", "BIT_FAS_1": "336.4",
         "MAT_FAS_1": "AL", "ISO_FAS_1": "NU", "CND_FAS": 3, "R1": 0.19, "X1": 0.38,
         "CNOM": 530.0, "CMAX": 600.0, "DESCR": "CAA 336,4 MCM"},
        {"COD_ID": "CAB002", "DIST": DIST, "GEOM_CAB": "1", "FORM_CAB": "1", "BIT_FAS_1": "70",
         "MAT_FAS_1": "AL", "ISO_FAS_1": "XLPE", "CND_FAS": 3, "R1": 0.44, "X1": 0.09,
         "CNOM": 190.0, "CMAX": 220.0, "DESCR": "multiplexado 3x70+70 mm²"},
        {"COD_ID": "CAB003", "DIST": DIST, "GEOM_CAB": "1", "FORM_CAB": "1", "BIT_FAS_1": "4",
         "MAT_FAS_1": "CU", "ISO_FAS_1": "NU", "CND_FAS": 3, "R1": 1.50, "X1": 0.45,
         "CNOM": 100.0, "CMAX": 120.0, "DESCR": "cabo não usado em nenhum trecho"},
    ]  # fmt: skip
    return _int32(pd.DataFrame(linhas), ["DIST", "CND_FAS"])


def eqtrmt() -> pd.DataFrame:
    linhas = [
        {
            "COD_ID": f"EQ{cod}",
            "DIST": DIST,
            "TIP_INST": "RD_AER_URB",
            "UNI_TR_MT": cod,
            "CLAS_TEN": "1",
            "POT_NOM": CODIGO_KVA[kva],  # código TPOTAPRT do Manual (não o valor em kVA)
            "LIG": "1",
            "FAS_CON": "ABC",
            "TEN_PRI": "46",
            "TEN_SEC": "11",
            "PER_FER": kva * 3.0,
            "PER_TOT": kva * 14.0,
            "R": 1.0,
            "XHL": 3.5,
            "DESCR": "",
        }
        for cod, (_, _, kva) in TRAFOS.items()
    ]
    return _int32(pd.DataFrame(linhas), ["DIST"])


def eqse() -> pd.DataFrame:
    linhas = [
        {
            "COD_ID": f"EQ{cod}",
            "DIST": DIST,
            "TIP_INST": "RD_AER_URB",
            "UN_SE": cod,
            "CLAS_TEN": "1",
            "ELO_FSV": "",
            "MEI_ISO": "AR",
            "FAS_CON": "ABC",
            "COR_NOM": "400",
            "ABER_CRG": 1,
            "GRU_TEN": "MT",
            "DESCR": "",
        }
        for cod in unsemt().COD_ID
    ]
    return _int32(pd.DataFrame(linhas), ["DIST", "ABER_CRG"])


CAMADAS = {
    "CTMT": ctmt,
    "SUB": sub,
    "UNTRAT": untrat,
    "SSDMT": ssdmt,
    "UNSEMT": unsemt,
    "UNTRMT": untrmt,
    "UNREMT": unremt,
    "UNCRMT": uncrmt,
    "SSDBT": ssdbt,
    "UNSEBT": unsebt,
    "RAMLIG": ramlig,
    "PONNOT": ponnot,
    "UCBT": ucbt,
    "UCBT_tab": ucbt_tab,
    "UCMT_tab": ucmt_tab,
    "UGBT_tab": ugbt_tab,
    "UGMT_tab": ugmt_tab,
    "CRVCRG": crvcrg,
    "SEGCON": segcon,
    "EQTRMT": eqtrmt,
    "EQSE": eqse,
}


def bairro() -> gpd.GeoDataFrame:
    """Polígono (EPSG:4326) que cobre RJO001 e RJO002, mas não RJO003 — para ``--bairro``."""
    poligono = box(-43.2010, -22.9130, -43.1920, -22.9090)
    return gpd.GeoDataFrame({"nome": ["Bairro Sintético"]}, geometry=[poligono], crs="EPSG:4326")


def gerar(caminho: Path = CAMINHO_PADRAO, bairro_geojson: Path | None = None) -> Path:
    """(Re)cria o GeoPackage sintético em ``caminho`` (e o GeoJSON do bairro); devolve o caminho."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.unlink(missing_ok=True)
    for nome, fabrica in CAMADAS.items():
        dados = fabrica()
        if isinstance(dados, gpd.GeoDataFrame):
            dados.to_file(caminho, layer=nome, driver="GPKG", engine="pyogrio")
        else:
            pyogrio.write_dataframe(dados, caminho, layer=nome, driver="GPKG")
    if bairro_geojson is None:
        bairro_geojson = caminho.with_name(CAMINHO_BAIRRO.name)
    bairro().to_file(bairro_geojson, driver="GeoJSON", engine="pyogrio")
    return caminho


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else CAMINHO_PADRAO
    print(f"Fixture gerada em {gerar(destino)}")
