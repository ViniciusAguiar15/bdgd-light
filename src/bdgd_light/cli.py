"""Interface de linha de comando ``bdgd-light``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pyogrio.errors import DataSourceError
from rich.console import Console

from bdgd_light import __version__
from bdgd_light.ingest.export import TAMANHO_LOTE_PADRAO, CamadaInexistenteError, exportar

app = typer.Typer(
    help="Ferramentas do COD agêntico sobre a BDGD da Light (ANEEL).",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


def _versao(mostrar: bool) -> None:
    if mostrar:
        console.print(f"bdgd-light {__version__}")
        raise typer.Exit()


@app.callback()
def principal(
    versao: Annotated[
        bool,
        typer.Option("--version", callback=_versao, is_eager=True, help="Mostra a versão e sai."),
    ] = False,
) -> None:
    """Ferramentas do COD agêntico sobre a BDGD da Light (ANEEL)."""


@app.command()
def export(
    gdb: Annotated[Path, typer.Option("--gdb", help="Caminho da BDGD (.gdb) ou de um GeoPackage.")],
    layers: Annotated[
        str | None,
        typer.Option(
            "--layers",
            help="Camadas separadas por vírgula (ex.: CTMT,SSDMT,UNSEMT). "
            "Padrão: todas as CAMADAS_CHAVE do catálogo que existirem na base.",
        ),
    ] = None,
    out: Annotated[
        Path, typer.Option("--out", help="Diretório de saída (um .parquet por camada).")
    ] = Path("data/parquet"),
    gpkg: Annotated[
        Path | None,
        typer.Option(
            "--gpkg", help="Também grava todas as camadas exportadas num GeoPackage único."
        ),
    ] = None,
    batch_size: Annotated[
        int, typer.Option("--batch-size", min=1, help="Feições lidas/gravadas por lote.")
    ] = TAMANHO_LOTE_PADRAO,
) -> None:
    """Exporta camadas da BDGD para GeoParquet (geográficas) e Parquet (tabelas).

    O CRS original (SIRGAS 2000, EPSG:4674) é preservado.

    Camadas grandes são processadas em lotes para não estourar a memória.
    """
    camadas = [c for c in layers.split(",") if c.strip()] if layers else None
    try:
        exportar(gdb, camadas, out, gpkg=gpkg, batch_size=batch_size, console=console)
    except (CamadaInexistenteError, FileNotFoundError) as erro:
        console.print(f"[bold red]Erro:[/] {erro}")
        raise typer.Exit(code=1) from None
    except DataSourceError as erro:
        console.print(f"[bold red]Erro:[/] não foi possível abrir a base [bold]{gdb}[/]: {erro}")
        raise typer.Exit(code=1) from None


if __name__ == "__main__":
    app()
