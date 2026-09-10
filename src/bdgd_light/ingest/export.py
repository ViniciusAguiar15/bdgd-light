"""Exportação de camadas da BDGD (.gdb) para GeoParquet/Parquet e, opcionalmente, GeoPackage.

A leitura é feita em lotes via o *stream* Arrow do GDAL (``pyogrio.raw.open_arrow``), de modo que
camadas grandes (SSDBT, UCBT_tab, PONNOT…) nunca ficam inteiras em memória: cada lote vira um
*row group* do Parquet e, se pedido, é anexado ao GeoPackage.

- Camadas geográficas → GeoParquet (geometria em WKB, CRS original da BDGD — SIRGAS 2000,
  EPSG:4674 — preservado nos metadados ``geo``).
- Tabelas sem geometria (CTMT, CRVCRG, UCBT_tab…) → Parquet comum.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pyogrio
import shapely
from pyogrio.raw import open_arrow, write_arrow
from pyproj import CRS
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from bdgd_light import __version__
from bdgd_light.catalogo import CAMADAS_CHAVE

COLUNA_GEOMETRIA = "geometry"
TAMANHO_LOTE_PADRAO = 100_000
VERSAO_GEOPARQUET = "1.0.0"

_NOMES_GEOMETRIA = {
    0: "Point",
    1: "LineString",
    2: "LinearRing",
    3: "Polygon",
    4: "MultiPoint",
    5: "MultiLineString",
    6: "MultiPolygon",
    7: "GeometryCollection",
}


class CamadaInexistenteError(ValueError):
    """Alguma camada pedida explicitamente não existe na base."""

    def __init__(self, ausentes: Iterable[str], disponiveis: Iterable[str]):
        self.ausentes = list(ausentes)
        self.disponiveis = list(disponiveis)
        super().__init__(
            f"camada(s) inexistente(s) na base: {', '.join(self.ausentes)}. "
            f"Camadas disponíveis ({len(self.disponiveis)}): {', '.join(self.disponiveis)}"
        )


@dataclass(frozen=True)
class ResultadoCamada:
    """Resumo da exportação de uma camada."""

    camada: str
    geometria: str | None  # None quando a camada é uma tabela sem geometria
    feicoes: int
    segundos: float
    parquet: Path
    gpkg: Path | None = None

    @property
    def eh_tabela(self) -> bool:
        return self.geometria is None


def listar_camadas(gdb: str | Path) -> dict[str, str | None]:
    """Mapeia nome da camada → tipo de geometria (``None`` para tabelas sem geometria)."""
    return {nome: geom for nome, geom in pyogrio.list_layers(str(gdb))}


def resolver_camadas(
    disponiveis: Iterable[str], pedidas: Iterable[str] | None = None
) -> tuple[list[str], list[str]]:
    """Decide quais camadas exportar.

    Sem ``pedidas`` usa ``CAMADAS_CHAVE`` e devolve as ausentes apenas para aviso (a BDGD da
    Light 2025, por exemplo, não traz UCBT/UCMT geográficas, só as tabelas ``*_tab``). Com
    ``pedidas`` explícitas, qualquer ausência é erro (``CamadaInexistenteError``). A comparação de
    nomes ignora maiúsculas/minúsculas e devolve o nome como está na base.
    """
    disponiveis = list(disponiveis)
    indice = {nome.upper(): nome for nome in disponiveis}
    alvo = list(CAMADAS_CHAVE) if pedidas is None else [p.strip() for p in pedidas if p.strip()]

    encontradas: list[str] = []
    ausentes: list[str] = []
    vistas: set[str] = set()
    for nome in alvo:
        chave = nome.upper()
        if chave in vistas:
            continue
        vistas.add(chave)
        real = indice.get(chave)
        if real is None:
            ausentes.append(nome)
        else:
            encontradas.append(real)

    if pedidas is not None and ausentes:
        raise CamadaInexistenteError(ausentes, disponiveis)
    return encontradas, ausentes


def contar_feicoes(gdb: str | Path, camada: str) -> int:
    """Número de feições segundo o driver (``-1`` quando não é possível saber rápido)."""
    return int(pyogrio.read_info(str(gdb), layer=camada)["features"])


def _schema_saida(schema: pa.Schema, nome_geometria: str | None) -> pa.Schema:
    """Renomeia a coluna de geometria para ``geometry`` e remove metadados de campo."""
    campos = []
    for campo in schema:
        if nome_geometria and campo.name == nome_geometria:
            campos.append(pa.field(COLUNA_GEOMETRIA, campo.type, nullable=True))
        else:
            campos.append(pa.field(campo.name, campo.type, nullable=campo.nullable))
    return pa.schema(campos)


def _metadados_geo(crs: str | None, tipos: set[str], bbox: list[float]) -> dict:
    """Metadados ``geo`` do GeoParquet para uma única coluna WKB."""
    coluna: dict = {
        "encoding": "WKB",
        "geometry_types": sorted(tipos),
        "crs": CRS.from_user_input(crs).to_json_dict() if crs else None,
    }
    if all(math.isfinite(v) for v in bbox):
        coluna["bbox"] = bbox
    return {
        "version": VERSAO_GEOPARQUET,
        "primary_column": COLUNA_GEOMETRIA,
        "columns": {COLUNA_GEOMETRIA: coluna},
        "creator": {"library": "bdgd-light", "version": __version__},
    }


def _atualizar_extensao(
    wkb: pa.Array, tipos: set[str], bbox: list[float]
) -> tuple[set[str], list[float]]:
    """Acumula tipos de geometria e *bounding box* de um lote de geometrias em WKB."""
    geoms = shapely.from_wkb(wkb.to_numpy(zero_copy_only=False))
    validas = geoms[~shapely.is_missing(geoms)]
    if len(validas) == 0:
        return tipos, bbox
    # código = 2*tipo + Z, para obter os pares (tipo, Z) presentes sem laço em Python
    codigos = shapely.get_type_id(validas).astype(np.int64) * 2 + shapely.has_z(validas)
    for codigo in np.unique(codigos):
        nome = _NOMES_GEOMETRIA.get(int(codigo // 2), "Unknown")
        tipos.add(nome + (" Z" if codigo % 2 else ""))
    limites = shapely.bounds(validas)
    if not np.isnan(limites).all():
        bbox = [
            min(bbox[0], float(np.nanmin(limites[:, 0]))),
            min(bbox[1], float(np.nanmin(limites[:, 1]))),
            max(bbox[2], float(np.nanmax(limites[:, 2]))),
            max(bbox[3], float(np.nanmax(limites[:, 3]))),
        ]
    return tipos, bbox


def exportar_camada(
    gdb: str | Path,
    camada: str,
    out_dir: str | Path,
    *,
    gpkg: str | Path | None = None,
    batch_size: int = TAMANHO_LOTE_PADRAO,
    ao_avancar: Callable[[int], None] | None = None,
) -> ResultadoCamada:
    """Exporta uma camada em lotes para ``<out_dir>/<camada>.parquet`` (e para ``gpkg``, se dado).

    ``ao_avancar`` é chamado com o número de feições de cada lote gravado (para barras de
    progresso). Em caso de erro, o Parquet parcial é removido.
    """
    inicio = time.perf_counter()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    destino = out_dir / f"{camada}.parquet"
    caminho_gpkg = Path(gpkg) if gpkg else None
    if caminho_gpkg:
        caminho_gpkg.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    tipos: set[str] = set()
    bbox = [math.inf, math.inf, -math.inf, -math.inf]

    with open_arrow(str(gdb), layer=camada, batch_size=batch_size, use_pyarrow=True) as (
        meta,
        leitor,
    ):
        nome_geometria = meta["geometry_name"] or None
        tipo_geometria = meta["geometry_type"] if nome_geometria else None
        crs = meta["crs"]
        schema = _schema_saida(leitor.schema, nome_geometria)
        indice_geometria = schema.get_field_index(COLUNA_GEOMETRIA) if nome_geometria else -1
        escritor = pq.ParquetWriter(destino, schema)
        anexar = False
        try:
            for lote in leitor:
                lote = pa.RecordBatch.from_arrays(lote.columns, schema=schema)
                escritor.write_batch(lote)
                if nome_geometria:
                    tipos, bbox = _atualizar_extensao(lote.column(indice_geometria), tipos, bbox)
                if caminho_gpkg:
                    _gravar_gpkg(lote, caminho_gpkg, camada, tipo_geometria, crs, anexar)
                    anexar = True
                total += lote.num_rows
                if ao_avancar:
                    ao_avancar(lote.num_rows)
            if nome_geometria:
                escritor.add_key_value_metadata(
                    {"geo": json.dumps(_metadados_geo(crs, tipos, bbox))}
                )
            if caminho_gpkg and total == 0:
                _gravar_gpkg(schema.empty_table(), caminho_gpkg, camada, tipo_geometria, crs, False)
        except BaseException:
            escritor.close()
            destino.unlink(missing_ok=True)
            raise
        escritor.close()

    return ResultadoCamada(
        camada=camada,
        geometria=tipo_geometria,
        feicoes=total,
        segundos=time.perf_counter() - inicio,
        parquet=destino,
        gpkg=caminho_gpkg,
    )


def _gravar_gpkg(
    dados: pa.RecordBatch | pa.Table,
    gpkg: Path,
    camada: str,
    tipo_geometria: str | None,
    crs: str | None,
    anexar: bool,
) -> None:
    if isinstance(dados, pa.RecordBatch):
        dados = pa.Table.from_batches([dados])
    write_arrow(
        dados,
        str(gpkg),
        layer=camada,
        driver="GPKG",
        geometry_name=COLUNA_GEOMETRIA if tipo_geometria else None,
        geometry_type=tipo_geometria,
        crs=crs if tipo_geometria else None,
        append=anexar,
    )


def exportar(
    gdb: str | Path,
    camadas: Iterable[str] | None = None,
    out_dir: str | Path = "data/parquet",
    *,
    gpkg: str | Path | None = None,
    batch_size: int = TAMANHO_LOTE_PADRAO,
    console: Console | None = None,
) -> list[ResultadoCamada]:
    """Exporta ``camadas`` (padrão: ``CAMADAS_CHAVE``) da base ``gdb`` para ``out_dir``.

    Registra no ``console`` (rich) a contagem de feições e o tempo de cada camada e um resumo ao
    final. Levanta ``FileNotFoundError`` se a base não existe e ``CamadaInexistenteError`` se uma
    camada pedida explicitamente não existe.
    """
    gdb = Path(gdb)
    if not gdb.exists():
        raise FileNotFoundError(f"base não encontrada: {gdb}")
    console = console or Console()
    out_dir = Path(out_dir)

    disponiveis = listar_camadas(gdb)
    selecionadas, ausentes = resolver_camadas(disponiveis, camadas)
    if ausentes:
        console.print(
            f"[yellow]Aviso:[/] {len(ausentes)} camada(s) de CAMADAS_CHAVE não existe(m) em "
            f"{gdb.name} e será(ão) pulada(s): {', '.join(ausentes)}"
        )
    if not selecionadas:
        console.print("[yellow]Nenhuma camada para exportar.[/]")
        return []

    console.print(
        f"Exportando {len(selecionadas)} camada(s) de [bold]{gdb}[/] para [bold]{out_dir}[/]"
        + (f" e [bold]{gpkg}[/]" if gpkg else "")
    )
    resultados: list[ResultadoCamada] = []
    inicio = time.perf_counter()
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progresso:
        for camada in selecionadas:
            previsto = contar_feicoes(gdb, camada)
            tarefa = progresso.add_task(camada, total=previsto if previsto >= 0 else None)
            resultado = exportar_camada(
                gdb,
                camada,
                out_dir,
                gpkg=gpkg,
                batch_size=batch_size,
                ao_avancar=lambda n, t=tarefa: progresso.advance(t, n),
            )
            progresso.remove_task(tarefa)
            resultados.append(resultado)
            console.print(
                f"[green]✔[/] {camada:<10} {resultado.geometria or 'tabela':<16} "
                f"{_fmt_int(resultado.feicoes):>12} feições  {_fmt_seg(resultado.segundos):>8}  "
                f"→ {resultado.parquet.name}"
            )

    console.print(_tabela_resumo(resultados, time.perf_counter() - inicio))
    return resultados


def _tabela_resumo(resultados: list[ResultadoCamada], segundos_total: float) -> Table:
    tabela = Table(title="Resumo da exportação", show_footer=True)
    tabela.add_column("Camada", footer="total", style="bold")
    tabela.add_column("Geometria")
    tabela.add_column(
        "Feições", justify="right", footer=_fmt_int(sum(r.feicoes for r in resultados))
    )
    tabela.add_column("Tempo", justify="right", footer=_fmt_seg(segundos_total))
    tabela.add_column("Arquivo", overflow="fold")
    for r in resultados:
        tabela.add_row(
            r.camada,
            r.geometria or "tabela",
            _fmt_int(r.feicoes),
            _fmt_seg(r.segundos),
            r.parquet.name,
        )
    return tabela


def _fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _fmt_seg(segundos: float) -> str:
    return f"{segundos:.1f} s".replace(".", ",")
