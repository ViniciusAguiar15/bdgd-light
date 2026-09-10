"""Detecção geométrica de interligações (chaves *tie*) entre alimentadores.

Na BDGD da Light os ``PAC`` são numerados por alimentador (``<CTMT>_MT_<n>``) e **nenhum PAC é
compartilhado** entre CTMT, logo a topologia não revela onde dois alimentadores se encostam. A regra
usada aqui (ver ``docs/escopo-alimentadores.md`` e ``docs/bdgd-relacoes.md``) é geométrica:

    chave ``UNSEMT`` normalmente aberta (``P_N_OPE = "A"``) cujo ponto está a até ``raio_m``
    (padrão 2 m) de uma **extremidade** de trecho ``SSDMT`` de **outro** CTMT.

Uma chave pode estar a 2 m de extremidades de vários CTMT (postes compartilhados, pátio de
subestação); todos os candidatos são devolvidos, um por par (chave, CTMT vizinho), com a extremidade
mais próxima. As contagens por CTMT (``contar_por_ctmt``) usam chaves distintas e são simétricas:
a tie conta para o CTMT dono da chave e para o vizinho.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import shapely
from geopandas import GeoDataFrame, GeoSeries
from pyproj import CRS

RAIO_PADRAO_M = 2.0
# o polígono de ``SUB`` na Light costuma ser só a casa de comando/edifício (SE Posto Seis: 492 m²);
# as chaves do pátio ficam a 10–40 m dele, por isso ``EM_SUB`` usa uma folga ao redor do polígono
RAIO_SUB_PADRAO_M = 50.0
CRS_METRICO_PADRAO = "EPSG:31983"  # SIRGAS 2000 / UTM 23S (área da Light)

COLUNAS_INTERLIGACAO = [
    "COD_ID",
    "CTMT",
    "CTMT_VIZ",
    "SSDMT_VIZ",
    "PAC_VIZ",
    "DIST_M",
    "P_N_OPE",
    "TLCD",
    "TIP_UNID",
    "EM_SUB",
]


def crs_metrico(gdf: GeoDataFrame) -> CRS:
    """CRS métrico para medir distâncias: o próprio, se projetado, senão a zona UTM estimada."""
    if gdf.crs is None:
        return CRS.from_user_input(CRS_METRICO_PADRAO)
    if gdf.crs.is_projected:
        return gdf.crs
    try:
        return gdf.estimate_utm_crs(datum_name="SIRGAS 2000")
    except (RuntimeError, ValueError):
        return CRS.from_user_input(CRS_METRICO_PADRAO)


def extremidades(ssdmt: GeoDataFrame) -> tuple[np.ndarray, pd.DataFrame]:
    """Pontos inicial e final de cada parte de cada trecho e seus atributos (CTMT, PAC, COD_ID).

    ``PAC_1`` é atribuído ao ponto inicial e ``PAC_2`` ao final (convenção da BDGD).
    """
    geoms = ssdmt.geometry.values
    partes, indice = shapely.get_parts(geoms, return_index=True)
    pontos = np.concatenate([shapely.get_point(partes, 0), shapely.get_point(partes, -1)])
    indice2 = np.concatenate([indice, indice])
    pac = np.concatenate([ssdmt["PAC_1"].to_numpy()[indice], ssdmt["PAC_2"].to_numpy()[indice]])
    atributos = pd.DataFrame(
        {
            "SSDMT_VIZ": ssdmt["COD_ID"].to_numpy()[indice2],
            "CTMT_VIZ": ssdmt["CTMT"].to_numpy()[indice2],
            "PAC_VIZ": pac,
        }
    )
    return pontos, atributos


def detectar_interligacoes(
    unsemt: GeoDataFrame,
    ssdmt: GeoDataFrame,
    *,
    raio_m: float = RAIO_PADRAO_M,
    sub: GeoDataFrame | None = None,
    apenas_na: bool = True,
    raio_sub_m: float = RAIO_SUB_PADRAO_M,
) -> GeoDataFrame:
    """Chaves de ``unsemt`` a até ``raio_m`` de extremidades de ``ssdmt`` de **outro** CTMT.

    Devolve um GeoDataFrame (CRS de ``unsemt``) com uma linha por par (chave, CTMT vizinho) e as
    colunas ``COLUNAS_INTERLIGACAO``: ``CTMT`` é o dono da chave, ``CTMT_VIZ``/``SSDMT_VIZ``/
    ``PAC_VIZ`` identificam a extremidade vizinha mais próxima, ``DIST_M`` a distância em metros e
    ``EM_SUB`` se a chave está dentro de um polígono de ``sub`` ou a até ``raio_sub_m`` dele (pátio
    de subestação — bays de transferência entre alimentadores da mesma SE, não ties de campo; o
    polígono da BDGD costuma cobrir só o edifício). Com ``apenas_na`` só chaves ``P_N_OPE == "A"``
    são consideradas.
    """
    chaves = unsemt
    if apenas_na and "P_N_OPE" in chaves.columns:
        chaves = chaves[chaves["P_N_OPE"] == "A"]
    chaves = chaves[~chaves.geometry.isna() & ~chaves.geometry.is_empty]
    vazio = GeoDataFrame(
        {c: pd.Series(dtype=t) for c, t in _TIPOS.items()}, geometry=[], crs=unsemt.crs
    )
    if chaves.empty or ssdmt.empty:
        return vazio

    crs = crs_metrico(ssdmt)
    trechos = ssdmt.to_crs(crs)
    pontos_chave = chaves.geometry.to_crs(crs).values
    pontos_ext, atributos = extremidades(trechos)
    arvore = shapely.STRtree(pontos_ext)
    i_chave, j_ext = arvore.query(pontos_chave, predicate="dwithin", distance=raio_m)
    if len(i_chave) == 0:
        return vazio

    pares = atributos.iloc[j_ext].reset_index(drop=True)
    pares.insert(0, "COD_ID", chaves["COD_ID"].to_numpy()[i_chave])
    pares.insert(1, "CTMT", chaves["CTMT"].to_numpy()[i_chave])
    pares["DIST_M"] = shapely.distance(pontos_chave[i_chave], pontos_ext[j_ext])
    for coluna in ("P_N_OPE", "TLCD", "TIP_UNID"):
        pares[coluna] = chaves[coluna].to_numpy()[i_chave] if coluna in chaves.columns else pd.NA
    pares["_i"] = i_chave
    pares = pares[pares["CTMT"] != pares["CTMT_VIZ"]]
    pares = pares.sort_values(["COD_ID", "CTMT_VIZ", "DIST_M"]).drop_duplicates(
        ["COD_ID", "CTMT_VIZ"]
    )
    if pares.empty:
        return vazio

    em_sub = np.zeros(len(chaves), dtype=bool)
    if sub is not None and not sub.empty:
        poligonos = sub.geometry.to_crs(crs).values
        arvore_sub = shapely.STRtree(poligonos)
        if raio_sub_m > 0:
            dentro = arvore_sub.query(pontos_chave, predicate="dwithin", distance=raio_sub_m)[0]
        else:
            dentro = arvore_sub.query(pontos_chave, predicate="within")[0]
        em_sub[np.unique(dentro)] = True
    pares["EM_SUB"] = em_sub[pares["_i"].to_numpy()]
    pares["DIST_M"] = pares["DIST_M"].round(3)
    pares["TLCD"] = pd.to_numeric(pares["TLCD"], errors="coerce").fillna(0).astype("int32")
    geometria = GeoSeries(chaves.geometry.values[pares["_i"].to_numpy()], crs=unsemt.crs)
    resultado = GeoDataFrame(
        pares[COLUNAS_INTERLIGACAO].reset_index(drop=True),
        geometry=geometria.values,
        crs=unsemt.crs,
    )
    return resultado


_TIPOS = {
    "COD_ID": "object",
    "CTMT": "object",
    "CTMT_VIZ": "object",
    "SSDMT_VIZ": "object",
    "PAC_VIZ": "object",
    "DIST_M": "float64",
    "P_N_OPE": "object",
    "TLCD": "int32",
    "TIP_UNID": "object",
    "EM_SUB": "bool",
}


def _pares_simetricos(interligacoes: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por (CTMT, vizinho, chave) vista dos dois lados da interligação."""
    ida = interligacoes[["CTMT", "CTMT_VIZ", "COD_ID", "TLCD", "EM_SUB"]].copy()
    ida["DONO"] = True
    volta = ida.rename(columns={"CTMT": "CTMT_VIZ", "CTMT_VIZ": "CTMT"})
    volta["DONO"] = False
    return pd.concat([ida, volta], ignore_index=True)


def contar_por_ctmt(interligacoes: pd.DataFrame) -> pd.DataFrame:
    """Contagens simétricas por CTMT: ties (chaves distintas), telecomandadas, em SE e vizinhos.

    Colunas: ``NA_interligacao``, ``NA_interligacao_telecomandada``, ``NA_interligacao_SE``,
    ``NA_interligacao_campo`` (fora de polígono ``SUB``), ``NA_interligacao_campo_telecomandada``,
    ``n_vizinhos``, ``vizinhos`` (códigos separados por ``;``), indexadas por ``CTMT``.
    """
    colunas = {
        "NA_interligacao": "int64",
        "NA_interligacao_telecomandada": "int64",
        "NA_interligacao_SE": "int64",
        "NA_interligacao_campo": "int64",
        "NA_interligacao_campo_telecomandada": "int64",
        "n_vizinhos": "int64",
        "vizinhos": "object",
    }
    if interligacoes.empty:
        return pd.DataFrame({c: pd.Series(dtype=t) for c, t in colunas.items()}).rename_axis("CTMT")
    pares = _pares_simetricos(interligacoes)
    grupos = pares.groupby("CTMT")
    campo = pares[~pares["EM_SUB"]]
    resumo = pd.DataFrame(
        {
            "NA_interligacao": grupos["COD_ID"].nunique(),
            "NA_interligacao_telecomandada": pares[pares["TLCD"] == 1]
            .groupby("CTMT")["COD_ID"]
            .nunique(),
            "NA_interligacao_SE": pares[pares["EM_SUB"]].groupby("CTMT")["COD_ID"].nunique(),
            "NA_interligacao_campo": campo.groupby("CTMT")["COD_ID"].nunique(),
            "NA_interligacao_campo_telecomandada": campo[campo["TLCD"] == 1]
            .groupby("CTMT")["COD_ID"]
            .nunique(),
            "n_vizinhos": grupos["CTMT_VIZ"].nunique(),
            "vizinhos": grupos["CTMT_VIZ"].agg(lambda s: ";".join(sorted(set(s)))),
        }
    )
    for coluna, tipo in colunas.items():
        if tipo == "int64":
            resumo[coluna] = resumo[coluna].fillna(0).astype("int64")
    return resumo


COLUNAS_VIZINHOS = [
    "CTMT_VIZ",
    "ties",
    "ties_telecomandadas",
    "ties_manuais",
    "ties_em_SE",
    "ties_proprias",
    "ties_do_vizinho",
    "chaves",
]


def vizinhos_de(interligacoes: pd.DataFrame, ctmt: str, *, sem_se: bool = False) -> pd.DataFrame:
    """CTMT interligados a ``ctmt`` e quantas ties há com cada um (dos dois lados).

    Colunas: ``CTMT_VIZ``, ``ties``, ``ties_telecomandadas``, ``ties_manuais``, ``ties_em_SE``,
    ``ties_proprias`` (chave pertence a ``ctmt``), ``ties_do_vizinho``, ``chaves`` (códigos).
    Com ``sem_se=True`` as chaves dentro de polígono ``SUB`` (disjuntores de saída, não são ties de
    campo) saem de todas as contagens e ficam só em ``ties_em_SE``; vizinhos ligados apenas por elas
    continuam listados, com ``ties = 0``. Ordenado por ``ties`` decrescente.
    """
    pares = _pares_simetricos(interligacoes) if not interligacoes.empty else pd.DataFrame()
    pares = pares[pares["CTMT"] == ctmt] if not pares.empty else pares
    if pares.empty:
        return pd.DataFrame(columns=COLUNAS_VIZINHOS)
    pares = pares.drop_duplicates(["CTMT_VIZ", "COD_ID"])
    em_se = pares[pares["EM_SUB"]].groupby("CTMT_VIZ").size()
    campo = pares[~pares["EM_SUB"]] if sem_se else pares
    grupos = campo.groupby("CTMT_VIZ")
    resumo = pd.DataFrame(
        {
            "ties": grupos.size(),
            "ties_telecomandadas": grupos["TLCD"].apply(lambda s: int((s == 1).sum())),
            "ties_proprias": grupos["DONO"].sum().astype(int),
            "chaves": grupos["COD_ID"].agg(lambda s: ";".join(sorted(s.astype(str)))),
        }
    )
    resumo = resumo.reindex(sorted(set(pares["CTMT_VIZ"])))
    resumo["ties_em_SE"] = em_se
    for coluna in ("ties", "ties_telecomandadas", "ties_proprias", "ties_em_SE"):
        resumo[coluna] = resumo[coluna].fillna(0).astype(int)
    resumo["chaves"] = resumo["chaves"].fillna("")
    resumo["ties_manuais"] = resumo["ties"] - resumo["ties_telecomandadas"]
    resumo["ties_do_vizinho"] = resumo["ties"] - resumo["ties_proprias"]
    resumo = resumo.rename_axis("CTMT_VIZ").reset_index()
    resumo = resumo.sort_values(["ties", "ties_em_SE", "CTMT_VIZ"], ascending=[False, False, True])
    return resumo[COLUNAS_VIZINHOS].reset_index(drop=True)
