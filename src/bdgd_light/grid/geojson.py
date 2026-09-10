"""Estado da rede (energizado/desenergizado por trecho, chave e trafo) como GeoJSON EPSG:4326."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from shapely.geometry import mapping

if TYPE_CHECKING:
    from bdgd_light.grid.rede import Rede

CRS_SAIDA = "EPSG:4326"


def _py(valor):
    """Converte escalares numpy/pandas em tipos JSON."""
    if isinstance(valor, np.generic):
        valor = valor.item()
    if pd.api.types.is_scalar(valor) and pd.isna(valor):
        return None
    return valor


def _listas(coords):
    """``mapping`` devolve tuplas; em listas o dicionário fica igual ao JSON gravado."""
    return [_listas(c) for c in coords] if isinstance(coords, (tuple, list)) else coords


def _feature(geom, props: dict) -> dict:
    geometria = None
    if geom is not None and not geom.is_empty:
        geometria = dict(mapping(geom))
        geometria["coordinates"] = _listas(geometria["coordinates"])
    return {
        "type": "Feature",
        "geometry": geometria,
        "properties": {k: _py(v) for k, v in props.items()},
    }


def estado_geojson(rede: Rede, caminho: str | Path | None = None) -> dict:
    """``FeatureCollection`` (EPSG:4326) com trechos, chaves e transformadores e seu estado.

    Propriedades comuns: ``camada`` (``SSDMT``/``UNSEMT``/``UNTRMT``), ``COD_ID``, ``CTMT``,
    ``energizado`` e ``fonte`` (CTMT que alimenta). Trechos trazem ``COMP`` e ``TIP_CND``; chaves
    ``normal`` (NA/NF), ``aberta`` (estado atual), ``TLCD``, ``TIP_UNID``, ``tie`` e ``externa``
    (chave de vizinho fora do grafo, vinda de ``INTERLIGACOES``); trafos ``POT_NOM`` e ``n_UCBT``.
    """
    energia = rede._energizacao()
    ties = {t["chave"] for t in rede._ties}
    feicoes: list[dict] = []

    ssdmt = rede.camadas.ssdmt
    if "geometry" in ssdmt and ssdmt.crs is not None:
        ssdmt = ssdmt.to_crs(CRS_SAIDA)
    for r in ssdmt.itertuples(index=False):
        cod = str(r.COD_ID).strip()
        u = rede.trechos.get(cod, (None,))[0]
        feicoes.append(
            _feature(
                getattr(r, "geometry", None),
                {
                    "camada": "SSDMT",
                    "COD_ID": cod,
                    "CTMT": r.CTMT,
                    "COMP": getattr(r, "COMP", None),
                    "TIP_CND": getattr(r, "TIP_CND", None),
                    "energizado": u in energia,
                    "fonte": energia.get(u),
                },
            )
        )

    unsemt = rede.camadas.unsemt
    if "geometry" in unsemt and unsemt.crs is not None:
        unsemt = unsemt.to_crs(CRS_SAIDA)
    for r in unsemt.itertuples(index=False):
        cod = str(r.COD_ID).strip()
        if cod not in rede.chaves:
            continue
        u, v = rede.chaves[cod]
        d = rede.grafo.edges[u, v]
        feicoes.append(
            _feature(
                getattr(r, "geometry", None),
                _props_chave(
                    cod, r.CTMT, d, u in energia or v in energia, energia, u, v, cod in ties
                ),
            )
        )

    inter = rede.camadas.interligacoes
    if inter is not None and not inter.empty and "geometry" in inter:
        inter = inter.to_crs(CRS_SAIDA) if inter.crs is not None else inter
        vistas: set[str] = set()
        for r in inter.itertuples(index=False):
            cod = str(r.COD_ID).strip()
            if cod in vistas or cod not in rede.chaves:
                continue
            u, v = rede.chaves[cod]
            d = rede.grafo.edges[u, v]
            if not d.get("externa"):
                continue
            vistas.add(cod)
            feicoes.append(
                _feature(
                    getattr(r, "geometry", None),
                    _props_chave(cod, r.CTMT, d, u in energia, energia, u, v, True),
                )
            )

    untrmt = rede.camadas.untrmt
    if untrmt is not None and "geometry" in untrmt:
        if untrmt.crs is not None:
            untrmt = untrmt.to_crs(CRS_SAIDA)
        por_trafo = _ucbt_por_trafo(rede)
        for r in untrmt.itertuples(index=False):
            cod = str(r.COD_ID).strip()
            no = rede.trafos.get(cod)
            if no is None:
                continue
            feicoes.append(
                _feature(
                    getattr(r, "geometry", None),
                    {
                        "camada": "UNTRMT",
                        "COD_ID": cod,
                        "CTMT": r.CTMT,
                        "PAC": no,
                        "POT_NOM": getattr(r, "POT_NOM", None),
                        "n_UCBT": int(por_trafo.get(cod, 0)),
                        "energizado": no in energia,
                        "fonte": energia.get(no),
                    },
                )
            )

    colecao = {"type": "FeatureCollection", "features": feicoes}
    if caminho is not None:
        Path(caminho).write_text(json.dumps(colecao, ensure_ascii=False))
    return colecao


def _props_chave(cod, ctmt, d, energizado, energia, u, v, tie) -> dict:
    return {
        "camada": "UNSEMT",
        "COD_ID": cod,
        "CTMT": ctmt,
        "PAC_1": u,
        "PAC_2": v,
        "normal": d["normal"],
        "aberta": bool(d["aberta"]),
        "TLCD": bool(d["tlcd"]),
        "TIP_UNID": d["tip_unid"],
        "tie": bool(tie),
        "externa": bool(d.get("externa", False)),
        "energizado": bool(energizado),
        "fonte": energia.get(u) or energia.get(v),
    }


def _ucbt_por_trafo(rede: Rede) -> pd.Series:
    tab = rede.camadas.ucbt_tab
    if tab is None or "UNI_TR_MT" not in tab:
        return pd.Series(dtype="int64")
    return tab["UNI_TR_MT"].astype(str).str.strip().value_counts()
