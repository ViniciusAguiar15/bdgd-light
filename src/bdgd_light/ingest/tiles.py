"""Tiles vetoriais (PMTiles) de um recorte da BDGD para o console MapLibre.

Lê o GeoPackage do ``bdgd-light recortar`` (um CTMT ou cluster), escreve um GeoJSON por camada em
EPSG:4326 (uma feição por linha — *GeoJSONSeq*, que o tippecanoe lê em paralelo) com os atributos
que o estilo do console usa e o zoom mínimo por camada, e chama o ``tippecanoe`` para gerar um
único ``.pmtiles`` com uma *source-layer* por camada da BDGD.

Camadas derivadas: ``UCBT`` (a Light 2025 não tem a camada geográfica; agregamos ``UCBT_tab`` por
poste ``PN_CON`` sobre ``PONNOT``) e, em ``UNSEMT``, ``TIE``/``EM_SUB`` vindos de ``INTERLIGACOES``;
``SSDMT`` ganha ``TEN_KV`` e ``NOME_CTMT`` do ``CTMT``; ``UNTRMT`` ganha ``N_UCBT``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely

from bdgd_light.catalogo import TENSAO_KV, TIPOS_CHAVE_MT

CRS_TILES = "EPSG:4326"
ZOOM_MIN_PADRAO = 9
ZOOM_MAX_PADRAO = 16
TIPPECANOE = "tippecanoe"
INSTALAR_TIPPECANOE = (
    "tippecanoe não encontrado no PATH. Instale: macOS `brew install tippecanoe`; Debian/Ubuntu "
    "`sudo apt install tippecanoe` (ou compile de github.com/felt/tippecanoe); depois repita o "
    "comando — ou use --geojson-only para ficar só com os GeoJSON."
)


@dataclass(frozen=True)
class CamadaTiles:
    """Como uma camada do recorte vira uma *source-layer* do PMTiles."""

    nome: str
    minzoom: int
    colunas: tuple[str, ...]
    origem: str | None = None  # camada do GPKG (padrão: o próprio nome)

    @property
    def camada_gpkg(self) -> str:
        return self.origem or self.nome


CAMADAS_TILES: tuple[CamadaTiles, ...] = (
    CamadaTiles("SUB", 9, ("COD_ID", "NOME")),
    CamadaTiles("UNTRAT", 9, ("COD_ID", "SUB", "POT_NOM", "TIP_TRAFO", "PAC_1", "PAC_2", "PAC_3")),
    CamadaTiles(
        "SSDMT",
        9,
        (
            "COD_ID",
            "CTMT",
            "PAC_1",
            "PAC_2",
            "COMP",
            "TIP_CND",
            "FAS_CON",
            "POS",
            "TEN_KV",
            "NOME_CTMT",
        ),
    ),  # fmt: skip
    CamadaTiles(
        "INTERLIGACOES",
        10,
        (
            "COD_ID",
            "CTMT",
            "CTMT_VIZ",
            "SSDMT_VIZ",
            "PAC_VIZ",
            "DIST_M",
            "P_N_OPE",
            "TLCD",
            "EM_SUB",
        ),
    ),  # fmt: skip
    CamadaTiles(
        "UNSEMT",
        11,
        (
            "COD_ID",
            "CTMT",
            "P_N_OPE",
            "TLCD",
            "TIP_UNID",
            "TIPO",
            "COR_NOM",
            "PAC_1",
            "PAC_2",
            "TIE",
            "CTMT_VIZ",
            "EM_SUB",
        ),
    ),  # fmt: skip
    CamadaTiles(
        "UNTRMT",
        12,
        ("COD_ID", "CTMT", "POT_NOM", "TIP_TRAFO", "FAS_CON_P", "PAC_1", "PAC_2", "MUN", "N_UCBT"),
    ),
    CamadaTiles("UNCRMT", 12, ("COD_ID", "CTMT", "POT_NOM", "PAC_1", "PAC_2")),
    CamadaTiles("SSDBT", 13, ("COD_ID", "CTMT", "UNI_TR_MT", "COMP", "TIP_CND", "FAS_CON")),
    CamadaTiles("UNSEBT", 14, ("COD_ID", "UNI_TR_MT", "P_N_OPE", "TIP_UNID", "PAC_1", "PAC_2")),
    CamadaTiles("UCBT", 14, ("PN_CON", "N_UC", "CTMT", "UNI_TR_MT", "CLAS_SUB"), origem="PONNOT"),
    CamadaTiles("PONNOT", 15, ("COD_ID", "TIP_PN", "ALT", "MAT", "MUN")),
)


class TippecanoeAusenteError(RuntimeError):
    """``tippecanoe`` não está no PATH."""


class TippecanoeError(RuntimeError):
    """``tippecanoe`` terminou com erro."""


@dataclass
class ResultadoTiles:
    pmtiles: Path | None
    geojson: dict[str, Path]
    feicoes: dict[str, int]
    bounds: tuple[float, float, float, float] | None
    segundos: float = 0.0
    bytes: int = 0
    avisos: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------------------------
# GeoJSON por camada
# ---------------------------------------------------------------------------------------------


def _py(valor):
    if isinstance(valor, np.generic):
        valor = valor.item()
    if pd.api.types.is_scalar(valor) and pd.isna(valor):
        return None
    return valor


def _texto(serie: pd.Series) -> pd.Series:
    return serie.astype("string").str.strip()


def _ler(gpkg: Path, camada: str, camadas: set[str]) -> gpd.GeoDataFrame | pd.DataFrame | None:
    if camada not in camadas:
        return None
    return pyogrio.read_dataframe(gpkg, layer=camada)


def _derivar(
    nome: str, gdf: gpd.GeoDataFrame, gpkg: Path, camadas: set[str], avisos: list[str]
) -> gpd.GeoDataFrame:
    """Acrescenta as colunas derivadas que o estilo usa (junções com tabelas do recorte)."""
    if nome == "SSDMT":
        ctmt = _ler(gpkg, "CTMT", camadas)
        gdf["TEN_KV"] = None
        gdf["NOME_CTMT"] = None
        if ctmt is not None and "TEN_NOM" in ctmt:
            ten = dict(zip(_texto(ctmt["COD_ID"]), _texto(ctmt["TEN_NOM"]), strict=False))
            nomes = dict(zip(_texto(ctmt["COD_ID"]), ctmt.get("NOME", ""), strict=False))
            cod = _texto(gdf["CTMT"])
            gdf["TEN_KV"] = cod.map(lambda c: TENSAO_KV.get(ten.get(c, ""), None))
            gdf["NOME_CTMT"] = cod.map(nomes)
        else:
            avisos.append("SSDMT sem CTMT.TEN_NOM no recorte: TEN_KV vazio")
    elif nome == "UNSEMT":
        gdf["TIPO"] = _texto(gdf["TIP_UNID"]).map(TIPOS_CHAVE_MT) if "TIP_UNID" in gdf else None
        inter = _ler(gpkg, "INTERLIGACOES", camadas)
        gdf["TIE"] = False
        gdf["CTMT_VIZ"] = None
        gdf["EM_SUB"] = None
        if inter is not None and len(inter):
            por_chave = inter.assign(_cod=_texto(inter["COD_ID"])).drop_duplicates("_cod")
            por_chave = por_chave.set_index("_cod")
            cod = _texto(gdf["COD_ID"])
            gdf["TIE"] = cod.isin(por_chave.index).astype(bool)
            gdf["CTMT_VIZ"] = cod.map(por_chave["CTMT_VIZ"]) if "CTMT_VIZ" in por_chave else None
            if "EM_SUB" in por_chave:
                gdf["EM_SUB"] = cod.map(por_chave["EM_SUB"])
    elif nome == "UNTRMT":
        ucbt = _ler(gpkg, "UCBT_tab", camadas)
        gdf["N_UCBT"] = 0
        if ucbt is not None and "UNI_TR_MT" in ucbt:
            n = _texto(ucbt["UNI_TR_MT"]).value_counts()
            gdf["N_UCBT"] = _texto(gdf["COD_ID"]).map(n).fillna(0).astype(int)
    return gdf


def _ucbt_por_poste(
    ponnot: gpd.GeoDataFrame, gpkg: Path, camadas: set[str], avisos: list[str]
) -> gpd.GeoDataFrame | None:
    """Camada derivada ``UCBT``: unidades de ``UCBT_tab`` agregadas por poste (``PN_CON`` →
    ``PONNOT.COD_ID``), com contagem e classe predominante."""
    ucbt = _ler(gpkg, "UCBT_tab", camadas)
    if ucbt is None or "PN_CON" not in ucbt or not len(ucbt):
        avisos.append("UCBT_tab ausente ou sem PN_CON: camada UCBT não gerada")
        return None
    u = pd.DataFrame(
        {
            "PN_CON": _texto(ucbt["PN_CON"]),
            "CTMT": _texto(ucbt["CTMT"]) if "CTMT" in ucbt else None,
            "UNI_TR_MT": _texto(ucbt["UNI_TR_MT"]) if "UNI_TR_MT" in ucbt else None,
            "CLAS_SUB": _texto(ucbt["CLAS_SUB"]) if "CLAS_SUB" in ucbt else None,
        }
    )
    u = u[u["PN_CON"].notna() & (u["PN_CON"] != "")]
    if not len(u):
        return None
    moda = u.groupby("PN_CON").agg(
        N_UC=("PN_CON", "size"),
        CTMT=("CTMT", lambda s: s.mode().iat[0] if len(s.mode()) else None),
        UNI_TR_MT=("UNI_TR_MT", lambda s: s.mode().iat[0] if len(s.mode()) else None),
        CLAS_SUB=("CLAS_SUB", lambda s: s.mode().iat[0] if len(s.mode()) else None),
    )
    postes = ponnot[["COD_ID", "geometry"]].copy()
    postes["PN_CON"] = _texto(postes["COD_ID"])
    saida = postes.merge(moda, left_on="PN_CON", right_index=True, how="inner")
    perdidos = len(moda) - len(saida)
    if perdidos:
        avisos.append(f"UCBT: {perdidos} postes de UCBT_tab.PN_CON sem PONNOT no recorte")
    return gpd.GeoDataFrame(saida.drop(columns=["COD_ID"]), geometry="geometry", crs=ponnot.crs)


def escrever_geojson(
    gpkg: str | Path,
    pasta: str | Path,
    camadas: Iterable[CamadaTiles] = CAMADAS_TILES,
    *,
    avisos: list[str] | None = None,
) -> tuple[dict[str, Path], dict[str, int], tuple[float, float, float, float] | None]:
    """Escreve ``<pasta>/<CAMADA>.geojsonl`` (EPSG:4326, uma feição por linha, com o membro
    ``tippecanoe.minzoom``) para cada camada geográfica do recorte. Devolve caminhos, contagem de
    feições e o *bbox* geral."""
    gpkg = Path(gpkg)
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    avisos = avisos if avisos is not None else []
    existentes = {nome for nome, _ in pyogrio.list_layers(gpkg)}
    arquivos: dict[str, Path] = {}
    contagem: dict[str, int] = {}
    bounds: list[float] | None = None
    for cam in camadas:
        if cam.camada_gpkg not in existentes:
            continue
        gdf = pyogrio.read_dataframe(gpkg, layer=cam.camada_gpkg)
        if not isinstance(gdf, gpd.GeoDataFrame) or gdf.geometry.isna().all():
            continue
        if cam.nome == "UCBT":
            gdf = _ucbt_por_poste(gdf, gpkg, existentes, avisos)
            if gdf is None:
                continue
        else:
            gdf = _derivar(cam.nome, gdf, gpkg, existentes, avisos)
        gdf = gdf[gdf.geometry.notna()]
        if gdf.crs is None:
            avisos.append(f"{cam.nome} sem CRS: assumindo EPSG:4674")
            gdf = gdf.set_crs("EPSG:4674")
        gdf = gdf.to_crs(CRS_TILES)
        colunas = [c for c in cam.colunas if c in gdf.columns]
        caminho = pasta / f"{cam.nome}.geojsonl"
        n = _escrever_geojsonl(gdf, colunas, cam, caminho)
        arquivos[cam.nome] = caminho
        contagem[cam.nome] = n
        b = [float(x) for x in gdf.total_bounds]
        if bounds is None:
            bounds = b
        else:
            bounds = [min(bounds[0], b[0]), min(bounds[1], b[1])] + [
                max(bounds[2], b[2]),
                max(bounds[3], b[3]),
            ]
    bbox = None if bounds is None else (bounds[0], bounds[1], bounds[2], bounds[3])
    return arquivos, contagem, bbox


def _escrever_geojsonl(
    gdf: gpd.GeoDataFrame, colunas: list[str], cam: CamadaTiles, caminho: Path
) -> int:
    props = gdf[colunas].to_dict("records") if colunas else [{} for _ in range(len(gdf))]
    geoms = shapely.to_geojson(gdf.geometry.values)
    n = 0
    with caminho.open("w", encoding="utf-8") as f:
        for geom, p in zip(geoms, props, strict=True):
            feicao = {
                "type": "Feature",
                "tippecanoe": {"minzoom": cam.minzoom, "layer": cam.nome},
                "properties": {k: _py(v) for k, v in p.items()},
                "geometry": json.loads(geom),
            }
            f.write(json.dumps(feicao, ensure_ascii=False, separators=(",", ":")))
            f.write("\n")
            n += 1
    return n


# ---------------------------------------------------------------------------------------------
# tippecanoe
# ---------------------------------------------------------------------------------------------


def tippecanoe_disponivel() -> str | None:
    return shutil.which(TIPPECANOE)


def comando_tippecanoe(
    saida: Path,
    arquivos: Mapping[str, Path],
    *,
    nome: str,
    zoom_min: int = ZOOM_MIN_PADRAO,
    zoom_max: int = ZOOM_MAX_PADRAO,
    atribuicao: str = "ANEEL/BDGD · Light",
    executavel: str = TIPPECANOE,
) -> list[str]:
    cmd = [
        executavel,
        "-o",
        str(saida),
        "--force",
        "--read-parallel",
        f"--name={nome}",
        f"--attribution={atribuicao}",
        f"--minimum-zoom={zoom_min}",
        f"--maximum-zoom={zoom_max}",
        "--drop-densest-as-needed",
        "--extend-zooms-if-still-dropping",
        "--generate-ids",
        "--no-progress-indicator",
    ]
    for camada, caminho in arquivos.items():
        cmd += ["-L", f"{camada}:{caminho}"]
    return cmd


def gerar_tiles(
    gpkg: str | Path,
    saida: str | Path,
    *,
    pasta_geojson: str | Path | None = None,
    zoom_min: int = ZOOM_MIN_PADRAO,
    zoom_max: int = ZOOM_MAX_PADRAO,
    camadas: Iterable[CamadaTiles] = CAMADAS_TILES,
    apenas_geojson: bool = False,
    executavel: str | None = None,
) -> ResultadoTiles:
    """Recorte GPKG → GeoJSONSeq por camada → ``tippecanoe`` → ``saida`` (``.pmtiles``).

    ``pasta_geojson`` (padrão ``<saida sem extensão>_geojson/``) guarda os GeoJSON intermediários,
    que também servem de *fallback* quando ``apenas_geojson=True`` ou o tippecanoe não existe.
    Lança ``TippecanoeAusenteError`` com instruções de instalação se ele não estiver no PATH.
    """
    inicio = time.perf_counter()
    saida = Path(saida)
    pasta = Path(pasta_geojson) if pasta_geojson else saida.with_name(saida.stem + "_geojson")
    avisos: list[str] = []
    executavel = executavel or TIPPECANOE
    caminho_exec = shutil.which(executavel)
    if not apenas_geojson and caminho_exec is None:
        raise TippecanoeAusenteError(INSTALAR_TIPPECANOE)
    arquivos, contagem, bounds = escrever_geojson(gpkg, pasta, camadas, avisos=avisos)
    if not arquivos:
        raise ValueError(f"nenhuma camada geográfica em {gpkg}")
    resultado = ResultadoTiles(None, arquivos, contagem, bounds, avisos=avisos)
    if apenas_geojson:
        resultado.segundos = time.perf_counter() - inicio
        return resultado
    saida.parent.mkdir(parents=True, exist_ok=True)
    cmd = comando_tippecanoe(
        saida, arquivos, nome=saida.stem, zoom_min=zoom_min, zoom_max=zoom_max,
        executavel=caminho_exec or executavel,
    )  # fmt: skip
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise TippecanoeError(
            f"tippecanoe falhou ({proc.returncode}): {proc.stderr.strip()[-2000:]}"
        )
    resultado.pmtiles = saida
    resultado.bytes = saida.stat().st_size
    resultado.segundos = time.perf_counter() - inicio
    return resultado
