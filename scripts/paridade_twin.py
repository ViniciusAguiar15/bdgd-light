"""Runner da issue #95: paridade gpkg2dss × bdgd2opendss."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from bdgd_light.paridade_twin import ConfiguracaoParidadeTwin, executar_paridade


def main() -> None:
    console = Console()
    config = ConfiguracaoParidadeTwin(
        gdb=Path("data/Light_382_2025-12-31_V11_20260824-0926.gdb"),
        feeders_dir=Path("data/feeders"),
        workdir=Path("scratch/issue-95-paridade"),
        out_csv=Path("docs/dados/paridade-twin.csv"),
        out_md=Path("docs/paridade-twin.md"),
    )
    tabela, _markdown = executar_paridade(config, console=console)
    console.print(
        f"[green]✔[/] {len(tabela)} alimentadores comparados; relatório em {config.out_md}"
    )


if __name__ == "__main__":
    main()
