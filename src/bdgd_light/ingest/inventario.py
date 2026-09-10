"""Inventário de alimentadores (CTMT) a partir das camadas exportadas em Parquet.

Uma linha por CTMT com extensão, carga, clientes, chaves (NA/NF, telecomandadas, interligações
geométricas com outros alimentadores), DER, equipamentos e *bbox*, para escolher o escopo de um
cenário FLISR. Regras de junção entre camadas em ``docs/bdgd-relacoes.md``; significado das colunas
no README.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from rich.console import Console
from rich.table import Table

from bdgd_light.catalogo import TENSAO_KV
from bdgd_light.ingest.interligacoes import (
    RAIO_PADRAO_M,
    contar_por_ctmt,
    detectar_interligacoes,
)
from bdgd_light.ingest.parquet import DiretorioParquet

ENE = [f"ENE_{m:02d}" for m in range(1, 13)]

COLUNAS_INVENTARIO = [
    "COD_ID",
    "NOME",
    "tipo",
    "SUB",
    "SUB_NOME",
    "UNI_TR_AT",
    "TEN_NOM",
    "TEN_NOM_kV",
    "MUN",
    "km_MT",
    "ENE_MWh_ano",
    "ENE_UC_MWh_ano",
    "n_UNTRMT",
    "kVA_instalado",
    "n_UCBT",
    "n_UCMT",
    "n_DER",
    "kW_DER",
    "chaves_total",
    "chaves_NA",
    "chaves_NF",
    "chaves_telecomandadas",
    "NA_interligacao",
    "NA_interligacao_telecomandada",
    "NA_interligacao_SE",
    "n_vizinhos",
    "vizinhos",
    "n_UNREMT",
    "n_UNCRMT",
    "lon_min",
    "lat_min",
    "lon_max",
    "lat_max",
    "score",
]
_INTEIRAS = [
    "n_UNTRMT",
    "n_UCBT",
    "n_UCMT",
    "n_DER",
    "chaves_total",
    "chaves_NA",
    "chaves_NF",
    "chaves_telecomandadas",
    "NA_interligacao",
    "NA_interligacao_telecomandada",
    "NA_interligacao_SE",
    "n_vizinhos",
    "n_UNREMT",
    "n_UNCRMT",
    "score",
]
# camadas de que o inventário se beneficia; só CTMT e SSDMT são obrigatórias
CAMADAS_OPCIONAIS = [
    "UNSEMT",
    "UNTRMT",
    "UCBT_tab",
    "UCMT_tab",
    "UGBT_tab",
    "UGMT_tab",
    "UNREMT",
    "UNCRMT",
    "SUB",
]


@dataclass
class ResultadoInventario:
    tabela: pd.DataFrame
    interligacoes: gpd.GeoDataFrame
    camadas_ausentes: list[str] = field(default_factory=list)
    segundos: float = 0.0


def carregar_bairro(caminho: str | Path) -> gpd.GeoDataFrame:
    """Lê o polígono (GeoJSON/GPKG…) usado por ``--bairro``; assume EPSG:4326 se não houver CRS."""
    bairro = gpd.read_file(caminho, engine="pyogrio")
    if bairro.empty:
        raise ValueError(f"o arquivo de bairro não tem feições: {caminho}")
    if bairro.crs is None:
        bairro = bairro.set_crs("EPSG:4326")
    return bairro


def inventariar(
    parquet: str | Path | DiretorioParquet,
    *,
    raio_tie_m: float = RAIO_PADRAO_M,
    bairro: gpd.GeoDataFrame | None = None,
    console: Console | None = None,
) -> ResultadoInventario:
    """Monta o inventário de CTMT a partir do diretório de Parquet (ver ``COLUNAS_INVENTARIO``).

    Exige ``CTMT`` e ``SSDMT``; as demais camadas são opcionais (colunas ficam 0/NaN e a ausência é
    registrada em ``camadas_ausentes`` e avisada no ``console``). ``bairro`` restringe aos CTMT com
    algum trecho MT intersectando o(s) polígono(s).
    """
    inicio = time.perf_counter()
    fonte = parquet if isinstance(parquet, DiretorioParquet) else DiretorioParquet(parquet)
    console = console or Console(quiet=True)
    ausentes = [c for c in CAMADAS_OPCIONAIS if not fonte.tem(c)]
    if ausentes:
        console.print(
            f"[yellow]Aviso:[/] camada(s) ausente(s) em {fonte.caminho}, colunas correspondentes "
            f"ficam zeradas: {', '.join(ausentes)}"
        )

    ctmt = fonte.ler("CTMT", ["COD_ID", "NOME", "SUB", "UNI_TR_AT", "TEN_NOM", *ENE])
    ssdmt = fonte.ler("SSDMT", ["COD_ID", "CTMT", "PAC_1", "PAC_2", "COMP", "geometry"])
    ssdmt = ssdmt[ssdmt["CTMT"].isin(ctmt["COD_ID"])]
    console.print(
        f"Inventariando {_fmt_int(len(ctmt))} CTMT com {_fmt_int(len(ssdmt))} trechos MT "
        f"de [bold]{fonte.caminho}[/]"
    )

    if bairro is not None:
        selecionados = _ctmt_no_bairro(ssdmt, bairro)
        ctmt = ctmt[ctmt["COD_ID"].isin(selecionados)]
        ssdmt = ssdmt[ssdmt["CTMT"].isin(selecionados)]
        console.print(f"Filtro por bairro: {_fmt_int(len(ctmt))} CTMT com rede MT no polígono")

    tabela = ctmt[["COD_ID", "NOME", "SUB", "UNI_TR_AT", "TEN_NOM"]].copy()
    tabela["NOME"] = tabela["NOME"].fillna("")
    tabela["tipo"] = tabela["NOME"].str.strip().str.split().str[0].fillna("")
    tabela["TEN_NOM"] = tabela["TEN_NOM"].astype("string")
    tabela["TEN_NOM_kV"] = tabela["TEN_NOM"].map(TENSAO_KV).astype("float64")
    tabela["ENE_MWh_ano"] = ctmt[ENE].sum(axis=1, min_count=1).to_numpy() / 1000.0
    tabela = tabela.set_index("COD_ID")

    sub = fonte.ler_se_existir("SUB", ["COD_ID", "NOME", "geometry"])
    if sub is not None:
        tabela["SUB_NOME"] = tabela["SUB"].map(
            sub.drop_duplicates("COD_ID").set_index("COD_ID")["NOME"]
        )
    else:
        tabela["SUB_NOME"] = pd.NA

    por_ctmt = ssdmt.groupby("CTMT")
    tabela["km_MT"] = por_ctmt["COMP"].sum() / 1000.0
    tabela = tabela.join(_bbox_4326(ssdmt))

    untrmt = fonte.ler_se_existir("UNTRMT", ["COD_ID", "CTMT", "POT_NOM", "MUN"])
    trafo_ctmt: pd.Series | None = None
    if untrmt is not None:
        untrmt = untrmt[untrmt["CTMT"].isin(tabela.index)]
        trafo_ctmt = untrmt.drop_duplicates("COD_ID").set_index("COD_ID")["CTMT"]
        tabela["n_UNTRMT"] = untrmt.groupby("CTMT").size()
        tabela["kVA_instalado"] = untrmt.groupby("CTMT")["POT_NOM"].sum()
        tabela["MUN"] = _moda_por_ctmt(untrmt, "MUN")

    unsemt = fonte.ler_se_existir(
        "UNSEMT", ["COD_ID", "CTMT", "P_N_OPE", "TLCD", "TIP_UNID", "MUN", "geometry"]
    )
    interligacoes = gpd.GeoDataFrame(geometry=[], crs=ssdmt.crs)
    if unsemt is not None:
        proprias = unsemt[unsemt["CTMT"].isin(tabela.index)]
        grupos = proprias.groupby("CTMT")
        tabela["chaves_total"] = grupos.size()
        tabela["chaves_NA"] = grupos["P_N_OPE"].apply(lambda s: int((s == "A").sum()))
        tabela["chaves_NF"] = grupos["P_N_OPE"].apply(lambda s: int((s == "F").sum()))
        tabela["chaves_telecomandadas"] = grupos["TLCD"].apply(lambda s: int((s == 1).sum()))
        if "MUN" not in tabela.columns:
            tabela["MUN"] = _moda_por_ctmt(proprias, "MUN")
        else:
            tabela["MUN"] = tabela["MUN"].fillna(_moda_por_ctmt(proprias, "MUN"))
        # interligações usam TODAS as chaves e trechos (vizinhos podem estar fora do bairro)
        ssdmt_total = (
            ssdmt
            if bairro is None
            else fonte.ler("SSDMT", ["COD_ID", "CTMT", "PAC_1", "PAC_2", "geometry"])
        )
        interligacoes = detectar_interligacoes(unsemt, ssdmt_total, raio_m=raio_tie_m, sub=sub)
        tabela = tabela.join(contar_por_ctmt(interligacoes))

    uc_bt = _agregar_uc(fonte, "UCBT_tab", tabela.index, trafo_ctmt)
    uc_mt = _agregar_uc(fonte, "UCMT_tab", tabela.index, None)
    tabela["n_UCBT"] = uc_bt["n"]
    tabela["n_UCMT"] = uc_mt["n"]
    tabela["ENE_UC_MWh_ano"] = (uc_bt["ene"].add(uc_mt["ene"], fill_value=0)) / 1000.0

    ug_bt = _agregar_ug(fonte, "UGBT_tab", tabela.index, trafo_ctmt)
    ug_mt = _agregar_ug(fonte, "UGMT_tab", tabela.index, None)
    tabela["n_DER"] = ug_bt["n"].add(ug_mt["n"], fill_value=0)
    tabela["kW_DER"] = ug_bt["kw"].add(ug_mt["kw"], fill_value=0)

    for camada, coluna in (("UNREMT", "n_UNREMT"), ("UNCRMT", "n_UNCRMT")):
        dados = fonte.ler_se_existir(camada, ["COD_ID", "CTMT"])
        if dados is not None:
            tabela[coluna] = dados[dados["CTMT"].isin(tabela.index)].groupby("CTMT").size()

    for coluna in COLUNAS_INVENTARIO:
        if coluna not in tabela.columns and coluna != "COD_ID":
            tabela[coluna] = np.nan
    tabela["vizinhos"] = tabela["vizinhos"].fillna("")
    tabela["score"] = tabela["NA_interligacao"].fillna(0) * (
        tabela["n_UCBT"].fillna(0) + tabela["n_UCMT"].fillna(0)
    )
    for coluna in _INTEIRAS:
        tabela[coluna] = tabela[coluna].fillna(0).astype("int64")
    for coluna in ("km_MT", "kVA_instalado", "kW_DER", "ENE_UC_MWh_ano"):
        tabela[coluna] = tabela[coluna].astype("float64").fillna(0.0).round(3)
    tabela["ENE_MWh_ano"] = tabela["ENE_MWh_ano"].astype("float64").round(3)

    tabela = tabela.reset_index().sort_values(
        ["score", "NA_interligacao", "n_UCBT", "COD_ID"], ascending=[False, False, False, True]
    )
    tabela = tabela[COLUNAS_INVENTARIO].reset_index(drop=True)
    return ResultadoInventario(
        tabela, interligacoes, ausentes, segundos=time.perf_counter() - inicio
    )


def _ctmt_no_bairro(ssdmt: gpd.GeoDataFrame, bairro: gpd.GeoDataFrame) -> set[str]:
    poligono = shapely.union_all(bairro.to_crs(ssdmt.crs).geometry.values)
    indices = ssdmt.sindex.query(poligono, predicate="intersects")
    return set(ssdmt["CTMT"].to_numpy()[indices])


def _bbox_4326(ssdmt: gpd.GeoDataFrame) -> pd.DataFrame:
    """bbox por CTMT em EPSG:4326 (cantos transformados a partir dos limites no CRS da base)."""
    limites = pd.DataFrame(
        shapely.bounds(ssdmt.geometry.values),
        columns=["minx", "miny", "maxx", "maxy"],
        index=ssdmt.index,
    )
    limites["CTMT"] = ssdmt["CTMT"].to_numpy()
    grupos = limites.groupby("CTMT")
    bbox = pd.DataFrame(
        {
            "minx": grupos["minx"].min(),
            "miny": grupos["miny"].min(),
            "maxx": grupos["maxx"].max(),
            "maxy": grupos["maxy"].max(),
        }
    )
    if ssdmt.crs is not None and ssdmt.crs.to_epsg() != 4326:
        transformar = Transformer.from_crs(ssdmt.crs, "EPSG:4326", always_xy=True)
        bbox["minx"], bbox["miny"] = transformar.transform(bbox["minx"].values, bbox["miny"].values)
        bbox["maxx"], bbox["maxy"] = transformar.transform(bbox["maxx"].values, bbox["maxy"].values)
    return bbox.rename(
        columns={"minx": "lon_min", "miny": "lat_min", "maxx": "lon_max", "maxy": "lat_max"}
    ).round(6)


def _moda_por_ctmt(dados: pd.DataFrame, coluna: str) -> pd.Series:
    if coluna not in dados.columns:
        return pd.Series(dtype="object")
    validos = dados.dropna(subset=[coluna])
    contagem = validos.groupby(["CTMT", coluna]).size().reset_index(name="n")
    contagem = contagem.sort_values(["CTMT", "n", coluna], ascending=[True, False, True])
    return contagem.drop_duplicates("CTMT").set_index("CTMT")[coluna]


def _ctmt_efetivo(lote: pd.DataFrame, trafo_ctmt: pd.Series | None) -> pd.Series:
    """CTMT da linha: o do transformador (``UNI_TR_MT``) quando existe, senão a coluna ``CTMT``."""
    if trafo_ctmt is not None and "UNI_TR_MT" in lote.columns:
        via_trafo = lote["UNI_TR_MT"].map(trafo_ctmt)
        return via_trafo.fillna(lote["CTMT"]) if "CTMT" in lote.columns else via_trafo
    return lote["CTMT"]


def _agregar_uc(
    fonte: DiretorioParquet, camada: str, ctmts: Iterable[str], trafo_ctmt: pd.Series | None
) -> dict[str, pd.Series]:
    """Nº de UCs e energia anual (kWh) por CTMT, lendo a tabela em lotes."""
    vazio = {"n": pd.Series(dtype="float64"), "ene": pd.Series(dtype="float64")}
    if not fonte.tem(camada):
        return vazio
    alvo = set(ctmts)
    parciais: list[pd.DataFrame] = []
    for lote in fonte.iterar_lotes(camada, ["UNI_TR_MT", "CTMT", *ENE]):
        lote = lote.assign(_ctmt=_ctmt_efetivo(lote, trafo_ctmt))
        lote = lote[lote["_ctmt"].isin(alvo)]
        if lote.empty:
            continue
        energia = lote[[c for c in ENE if c in lote.columns]].sum(axis=1)
        parciais.append(
            pd.DataFrame({"n": 1, "ene": energia.to_numpy()}, index=lote["_ctmt"].to_numpy())
            .groupby(level=0)
            .sum()
        )
    if not parciais:
        return vazio
    total = pd.concat(parciais).groupby(level=0).sum()
    return {"n": total["n"], "ene": total["ene"]}


def _agregar_ug(
    fonte: DiretorioParquet, camada: str, ctmts: Iterable[str], trafo_ctmt: pd.Series | None
) -> dict[str, pd.Series]:
    """Nº de geradores (DER) e potência instalada (kW) por CTMT."""
    vazio = {"n": pd.Series(dtype="float64"), "kw": pd.Series(dtype="float64")}
    if not fonte.tem(camada):
        return vazio
    dados = fonte.ler(camada, ["COD_ID", "UNI_TR_MT", "CTMT", "POT_INST"])
    dados = dados.assign(_ctmt=_ctmt_efetivo(dados, trafo_ctmt))
    dados = dados[dados["_ctmt"].isin(set(ctmts))]
    if dados.empty:
        return vazio
    grupos = dados.groupby("_ctmt")
    potencia = grupos["POT_INST"].sum() if "POT_INST" in dados.columns else grupos.size() * np.nan
    return {"n": grupos.size().astype("float64"), "kw": potencia}


# --- apresentação -----------------------------------------------------------------------------


def gravar_csv(tabela: pd.DataFrame, destino: str | Path) -> Path:
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_csv(destino, index=False, encoding="utf-8")
    return destino


def tabela_top(tabela: pd.DataFrame, n: int = 20, titulo: str | None = None) -> Table:
    """Tabela rich com os ``n`` CTMT de maior ``score`` (chaves NA de interligação × clientes)."""
    colunas = [
        ("COD_ID", "CTMT", "left"),
        ("NOME", "Nome", "left"),
        ("SUB_NOME", "Subestação", "left"),
        ("TEN_NOM_kV", "kV", "right"),
        ("km_MT", "km MT", "right"),
        ("ENE_MWh_ano", "MWh/ano", "right"),
        ("n_UNTRMT", "Trafos", "right"),
        ("kVA_instalado", "kVA", "right"),
        ("n_UC", "UC", "right"),
        ("chaves_NA", "NA", "right"),
        ("NA_interligacao", "NA tie", "right"),
        ("NA_interligacao_telecomandada", "tie TLCD", "right"),
        ("n_DER", "DER", "right"),
        ("score", "Score", "right"),
    ]
    tabela = tabela.assign(n_UC=tabela["n_UCBT"] + tabela["n_UCMT"])
    rich_tabela = Table(
        title=titulo or f"Top {n} alimentadores por score (NA de interligação × clientes)"
    )
    for _, rotulo, alinhamento in colunas:
        rich_tabela.add_column(rotulo, justify=alinhamento, overflow="fold")
    for _, linha in tabela.head(n).iterrows():
        rich_tabela.add_row(*(_fmt(linha[c]) for c, _, _ in colunas))
    return rich_tabela


def _fmt(valor: object) -> str:
    if valor is None or (isinstance(valor, float) and np.isnan(valor)) or valor is pd.NA:
        return "-"
    if isinstance(valor, (int, np.integer)):
        return _fmt_int(int(valor))
    if isinstance(valor, (float, np.floating)):
        return f"{valor:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(valor)


def _fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")
