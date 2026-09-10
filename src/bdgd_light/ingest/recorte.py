"""Recorte de todas as camadas da BDGD por alimentador (CTMT) → GeoPackage + ``meta.json``.

Cada camada é filtrada pela regra de junção documentada em ``docs/bdgd-relacoes.md``:

- ``CTMT``: ``COD_ID``.
- Camadas MT com coluna ``CTMT`` (SSDMT, UNSEMT, UNTRMT, UNREMT, UNCRMT, UCMT/UCMT_tab,
  UGMT/UGMT_tab).
- Camadas BT (SSDBT, UNSEBT, RAMLIG, UCBT/UCBT_tab, UGBT/UGBT_tab, PIP): pelo transformador
  (``UNI_TR_MT`` ∈ UNTRMT selecionados), que é quem define o alimentador; a coluna ``CTMT`` dessas
  camadas só é usada se não houver UNTRMT.
- ``PONNOT`` (postes): ``COD_ID`` ∈ ``PN_CON``/``PN_CON_1``/``PN_CON_2`` das feições selecionadas.
- ``UNTRAT`` e ``SUB``: toda a subestação do CTMT (``SUB`` ∈ ``CTMT.SUB``).
- Equipamentos (EQTRMT, EQSE, EQRE, EQCR): ``UNI_TR_MT``/``UN_SE``/``UN_RE``/``UN_CR`` das unidades.
- Catálogos (SEGCON, CRVCRG): só os códigos usados (``TIP_CND``, ``TIP_CC``).
- ``INTERLIGACOES`` (camada calculada): chaves NA de interligação envolvendo o CTMT, dos dois lados.

Com vários CTMT gera um GPKG por CTMT e um GPKG do cluster (união), cada um com seu ``meta.json``.
As camadas do cluster são lidas do Parquet uma única vez (filtros empurrados ao pyarrow) e os
recortes individuais são derivados em memória com as mesmas regras.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import geopandas as gpd
import pandas as pd
import pyogrio
from rich.console import Console
from rich.table import Table

from bdgd_light import __version__
from bdgd_light.ingest.interligacoes import (
    RAIO_PADRAO_M,
    detectar_interligacoes,
    vizinhos_de,
)
from bdgd_light.ingest.parquet import DiretorioParquet, Filtro, filtro_in

CAMADA_INTERLIGACOES = "INTERLIGACOES"
CAMADAS_POR_CTMT = [
    "SSDMT",
    "UNSEMT",
    "UNTRMT",
    "UNREMT",
    "UNCRMT",
    "UCMT",
    "UCMT_tab",
    "UGMT",
    "UGMT_tab",
]
CAMADAS_POR_TRAFO = ["SSDBT", "UNSEBT", "RAMLIG", "UCBT", "UCBT_tab", "UGBT", "UGBT_tab", "PIP"]
EQUIPAMENTOS = {  # camada de equipamento → (coluna de ligação, camadas de unidades)
    "EQTRMT": ("UNI_TR_MT", ["UNTRMT"]),
    "EQSE": ("UN_SE", ["UNSEMT", "UNSEBT"]),
    "EQRE": ("UN_RE", ["UNREMT"]),
    "EQCR": ("UN_CR", ["UNCRMT"]),
}
CATALOGOS = {  # catálogo → (coluna que o referencia, camadas que a têm)
    "SEGCON": ("TIP_CND", ["SSDMT", "SSDBT", "RAMLIG"]),
    "CRVCRG": ("TIP_CC", ["UCBT_tab", "UCMT_tab", "UCBT", "UCMT", "PIP"]),
}
COLUNAS_PN = ["PN_CON", "PN_CON_1", "PN_CON_2"]
# ordem de gravação no GeoPackage
ORDEM_CAMADAS = [
    "CTMT",
    "SUB",
    "UNTRAT",
    *CAMADAS_POR_CTMT,
    *CAMADAS_POR_TRAFO,
    "PONNOT",
    *EQUIPAMENTOS,
    *CATALOGOS,
    CAMADA_INTERLIGACOES,
]


class CtmtInexistenteError(ValueError):
    def __init__(self, ausentes: Iterable[str]):
        self.ausentes = list(ausentes)
        super().__init__(f"CTMT inexistente(s) na base: {', '.join(self.ausentes)}")


class Fonte(Protocol):
    def tem(self, camada: str) -> bool: ...

    def colunas(self, camada: str) -> list[str]: ...

    def ler(
        self,
        camada: str,
        colunas: Iterable[str] | None = None,
        filtros: list[Filtro] | None = None,
    ) -> gpd.GeoDataFrame | pd.DataFrame: ...


class FonteMemoria:
    """Interface de ``DiretorioParquet`` sobre DataFrames já carregados (só filtros ``in``)."""

    def __init__(self, camadas: dict[str, pd.DataFrame]):
        self._camadas = camadas

    def tem(self, camada: str) -> bool:
        return camada in self._camadas

    def colunas(self, camada: str) -> list[str]:
        return list(self._camadas[camada].columns)

    def ler(
        self,
        camada: str,
        colunas: Iterable[str] | None = None,
        filtros: list[Filtro] | None = None,
    ) -> gpd.GeoDataFrame | pd.DataFrame:
        dados = self._camadas[camada]
        for coluna, operador, valores in filtros or []:
            if operador != "in":
                raise ValueError(f"operador não suportado em memória: {operador}")
            dados = dados[dados[coluna].isin(set(valores))]
        if colunas is not None:
            cols = [c for c in colunas if c in dados.columns]
            if isinstance(dados, gpd.GeoDataFrame) and "geometry" not in cols:
                cols.append("geometry")
            dados = dados[cols]
        return dados


@dataclass
class Recorte:
    ctmts: list[str]
    nome: str
    camadas: dict[str, pd.DataFrame]
    gpkg: Path | None = None
    meta: Path | None = None
    segundos: float = 0.0

    @property
    def contagens(self) -> dict[str, int]:
        return {c: int(len(df)) for c, df in self.camadas.items()}


@dataclass
class ResultadoRecorte:
    recortes: list[Recorte]
    cluster: Recorte | None
    camadas_ausentes: list[str] = field(default_factory=list)
    segundos: float = 0.0


def _valores(
    camadas: dict[str, pd.DataFrame], nomes: Iterable[str], colunas: Iterable[str]
) -> list:
    valores: set = set()
    for nome in nomes:
        df = camadas.get(nome)
        if df is None:
            continue
        for coluna in colunas:
            if coluna in df.columns:
                valores.update(df[coluna].dropna().unique().tolist())
    # strings em branco (há PN_CON_2 = " " em RAMLIG na Light 2025) não referenciam nada
    return sorted((v for v in valores if not (isinstance(v, str) and not v.strip())), key=str)


def selecionar(
    fonte: Fonte,
    ctmts: Iterable[str],
    *,
    interligacoes: gpd.GeoDataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """Aplica as regras de junção e devolve ``{camada: feições}`` para o conjunto de CTMT.

    Só camadas existentes na fonte entram (a ausência é decidida pelo chamador). Levanta
    ``CtmtInexistenteError`` se algum CTMT pedido não existe na tabela CTMT.
    """
    ctmts = list(dict.fromkeys(ctmts))
    sel: dict[str, pd.DataFrame] = {}
    ctmt = fonte.ler("CTMT", filtros=filtro_in("COD_ID", ctmts))
    ausentes = [c for c in ctmts if c not in set(ctmt["COD_ID"])]
    if ausentes:
        raise CtmtInexistenteError(ausentes)
    sel["CTMT"] = ctmt

    subs = _valores(sel, ["CTMT"], ["SUB"])
    if fonte.tem("SUB"):
        sel["SUB"] = fonte.ler("SUB", filtros=filtro_in("COD_ID", subs))
    if fonte.tem("UNTRAT"):
        if "SUB" in fonte.colunas("UNTRAT") and subs:
            sel["UNTRAT"] = fonte.ler("UNTRAT", filtros=filtro_in("SUB", subs))
        else:
            sel["UNTRAT"] = fonte.ler(
                "UNTRAT", filtros=filtro_in("COD_ID", _valores(sel, ["CTMT"], ["UNI_TR_AT"]))
            )

    for camada in CAMADAS_POR_CTMT:
        if fonte.tem(camada):
            sel[camada] = fonte.ler(camada, filtros=filtro_in("CTMT", ctmts))

    trafos = _valores(sel, ["UNTRMT"], ["COD_ID"]) if "UNTRMT" in sel else None
    for camada in CAMADAS_POR_TRAFO:
        if not fonte.tem(camada):
            continue
        if trafos is not None and "UNI_TR_MT" in fonte.colunas(camada):
            sel[camada] = fonte.ler(camada, filtros=filtro_in("UNI_TR_MT", trafos))
        else:
            sel[camada] = fonte.ler(camada, filtros=filtro_in("CTMT", ctmts))

    if fonte.tem("PONNOT"):
        postes = _valores(sel, list(sel), COLUNAS_PN)
        sel["PONNOT"] = fonte.ler("PONNOT", filtros=filtro_in("COD_ID", postes))

    for camada, (coluna, unidades) in EQUIPAMENTOS.items():
        if fonte.tem(camada):
            codigos = _valores(sel, unidades, ["COD_ID"])
            sel[camada] = fonte.ler(camada, filtros=filtro_in(coluna, codigos))

    for camada, (coluna, usuarias) in CATALOGOS.items():
        if fonte.tem(camada):
            codigos = _valores(sel, usuarias, [coluna])
            sel[camada] = fonte.ler(camada, filtros=filtro_in("COD_ID", codigos))

    if interligacoes is not None:
        alvo = set(ctmts)
        mascara = interligacoes["CTMT"].isin(alvo) | interligacoes["CTMT_VIZ"].isin(alvo)
        sel[CAMADA_INTERLIGACOES] = interligacoes[mascara].reset_index(drop=True)

    return {c: sel[c].reset_index(drop=True) for c in ORDEM_CAMADAS if c in sel}


def nome_cluster(ctmts: Iterable[str]) -> str:
    return "cluster_" + "-".join(ctmts)


def recortar(
    parquet: str | Path | DiretorioParquet,
    ctmts: Iterable[str],
    out_dir: str | Path,
    *,
    nome_cluster_: str | None = None,
    raio_tie_m: float = RAIO_PADRAO_M,
    console: Console | None = None,
) -> ResultadoRecorte:
    """Gera ``<out_dir>/<CTMT>.gpkg`` (+ ``.meta.json``) por CTMT e, com vários, o GPKG do cluster.

    Camadas ausentes do diretório Parquet são puladas com aviso; ``CTMT`` é obrigatória e
    ``SSDMT``/``UNSEMT`` são necessárias para a camada ``INTERLIGACOES``.
    """
    inicio = time.perf_counter()
    fonte = parquet if isinstance(parquet, DiretorioParquet) else DiretorioParquet(parquet)
    console = console or Console(quiet=True)
    ctmts = [c.strip() for c in ctmts if c.strip()]
    ctmts = list(dict.fromkeys(ctmts))
    if not ctmts:
        raise ValueError("informe ao menos um CTMT")
    out_dir = Path(out_dir)

    esperadas = [c for c in ORDEM_CAMADAS if c != CAMADA_INTERLIGACOES]
    ausentes = [c for c in esperadas if not fonte.tem(c)]
    if ausentes:
        console.print(
            f"[yellow]Aviso:[/] camada(s) ausente(s) em {fonte.caminho} e pulada(s): "
            f"{', '.join(ausentes)}"
        )

    interligacoes = None
    if fonte.tem("SSDMT") and fonte.tem("UNSEMT"):
        interligacoes = detectar_interligacoes(
            fonte.ler("UNSEMT"),
            fonte.ler("SSDMT", ["COD_ID", "CTMT", "PAC_1", "PAC_2", "geometry"]),
            raio_m=raio_tie_m,
            sub=fonte.ler_se_existir("SUB"),
        )

    console.print(f"Recortando {len(ctmts)} CTMT de [bold]{fonte.caminho}[/] → [bold]{out_dir}[/]")
    t0 = time.perf_counter()
    camadas_cluster = selecionar(fonte, ctmts, interligacoes=interligacoes)
    memoria = FonteMemoria(camadas_cluster)

    recortes: list[Recorte] = []
    for cod in ctmts:
        t1 = time.perf_counter()
        camadas = selecionar(memoria, [cod], interligacoes=interligacoes)
        recorte = Recorte([cod], cod, camadas)
        _gravar(recorte, out_dir / f"{cod}.gpkg", fonte, interligacoes)
        recorte.segundos = time.perf_counter() - t1
        recortes.append(recorte)
        console.print(_linha_log(recorte))

    cluster = None
    if len(ctmts) > 1:
        cluster = Recorte(ctmts, nome_cluster_ or nome_cluster(ctmts), camadas_cluster)
        _gravar(cluster, out_dir / f"{cluster.nome}.gpkg", fonte, interligacoes)
        cluster.segundos = time.perf_counter() - t0
        console.print(_linha_log(cluster))

    total = time.perf_counter() - inicio
    console.print(_tabela_resumo(recortes, cluster))
    return ResultadoRecorte(recortes, cluster, ausentes, segundos=total)


def _gravar(
    recorte: Recorte,
    gpkg: Path,
    fonte: DiretorioParquet,
    interligacoes: gpd.GeoDataFrame | None,
) -> None:
    gpkg.parent.mkdir(parents=True, exist_ok=True)
    gpkg.unlink(missing_ok=True)
    for camada, dados in recorte.camadas.items():
        if dados.empty:
            continue  # camada vazia não é gravada (fica com 0 no meta.json)
        if isinstance(dados, gpd.GeoDataFrame):
            dados.to_file(gpkg, layer=camada, driver="GPKG", engine="pyogrio")
        else:
            pyogrio.write_dataframe(dados, gpkg, layer=camada, driver="GPKG")
    recorte.gpkg = gpkg
    recorte.meta = gpkg.with_suffix(".meta.json")
    recorte.meta.write_text(
        json.dumps(_meta(recorte, fonte, interligacoes), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _meta(
    recorte: Recorte, fonte: DiretorioParquet, interligacoes: gpd.GeoDataFrame | None
) -> dict:
    ctmt = recorte.camadas["CTMT"].set_index("COD_ID").reindex(recorte.ctmts).reset_index()
    ssdmt = recorte.camadas.get("SSDMT")
    bbox = None
    if isinstance(ssdmt, gpd.GeoDataFrame) and not ssdmt.empty:
        bbox = [round(float(v), 6) for v in ssdmt.to_crs("EPSG:4326").total_bounds]
    vizinhos: list[dict] = []
    if interligacoes is not None:
        for cod in recorte.ctmts:
            todas = vizinhos_de(interligacoes, cod).set_index("CTMT_VIZ")
            campo = vizinhos_de(interligacoes, cod, sem_se=True).set_index("CTMT_VIZ")
            for viz, v in todas.iterrows():
                if viz in recorte.ctmts and len(recorte.ctmts) > 1 and cod > viz:
                    continue  # par interno ao cluster já listado do outro lado
                c = campo.loc[viz]
                vizinhos.append(
                    {
                        "ctmt": cod,
                        "vizinho": viz,
                        "ties": int(v["ties"]),
                        "ties_telecomandadas": int(v["ties_telecomandadas"]),
                        "ties_em_SE": int(v["ties_em_SE"]),
                        "ties_campo": int(c["ties"]),
                        "ties_campo_telecomandadas": int(c["ties_telecomandadas"]),
                        "chaves": v["chaves"].split(";"),
                        "chaves_campo": [x for x in c["chaves"].split(";") if x],
                    }
                )
    return {
        "nome": recorte.nome,
        "ctmt": [
            {"COD_ID": r["COD_ID"], "NOME": r.get("NOME"), "SUB": r.get("SUB")}
            for _, r in ctmt.iterrows()
        ],
        "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "bdgd_light": __version__,
        "parquet": str(fonte.caminho),
        "crs": "EPSG:4674",
        "bbox_4326": bbox,
        "camadas": recorte.contagens,
        "interligacoes": vizinhos,
    }


def _linha_log(recorte: Recorte) -> str:
    n = recorte.contagens
    partes = [f"{c} {_fmt_int(n[c])}" for c in ("SSDMT", "UNTRMT", "UNSEMT", "UCBT_tab") if c in n]
    return (
        f"[green]✔[/] {recorte.nome:<32} {len(n):>2} camadas  "
        f"{_fmt_int(sum(n.values())):>9} feições  {_fmt_seg(recorte.segundos):>8}  "
        f"({', '.join(partes)}) → {recorte.gpkg.name if recorte.gpkg else ''}"
    )


def _tabela_resumo(recortes: list[Recorte], cluster: Recorte | None) -> Table:
    todos = [*recortes, *([cluster] if cluster else [])]
    tabela = Table(title="Feições por camada e recorte")
    tabela.add_column("Camada", style="bold")
    for r in todos:
        tabela.add_column(r.nome, justify="right", overflow="fold")
    camadas = [c for c in ORDEM_CAMADAS if any(c in r.camadas for r in todos)]
    for camada in camadas:
        tabela.add_row(camada, *(_fmt_int(r.contagens.get(camada, 0)) for r in todos))
    tabela.add_row("total", *(f"[bold]{_fmt_int(sum(r.contagens.values()))}[/]" for r in todos))
    return tabela


def _fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _fmt_seg(segundos: float) -> str:
    return f"{segundos:.1f} s".replace(".", ",")
