"""Runner da issue #96: sensibilidade de premissas do gêmeo/restauração."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from bdgd_light.sensibilidade import ConfiguracaoSensibilidade, executar_sensibilidade


def main() -> None:
    console = Console()
    config = ConfiguracaoSensibilidade(
        feeders_dir=Path("data/feeders"),
        parquet_dir=Path("data/parquet"),
        inventario_csv=Path("data/inventario_ctmt.csv"),
        generalizacao_csv=Path("docs/bench/2026-09-11-generalizacao.csv"),
        workdir=Path("scratch/issue-96-sensibilidade"),
        out_csv=Path("docs/bench/2026-09-12-sensibilidade-premissas.csv"),
        out_md=Path("docs/sensibilidade.md"),
    )
    resultados, resumo, casos = executar_sensibilidade(config, console=console)
    console.print(
        f"[green]✔[/] {len(casos)} casos, {len(resultados)} combinações; resumo em {config.out_md}"
    )
    virou = int(resultados["virou_decisao"].sum())
    console.print(f"[cyan]Decisões que mudaram em relação ao caso base:[/] {virou}")
    if not resumo.empty:
        for item in resumo.itertuples(index=False):
            console.print(f"- {item.caso}: {item.conclusao}")


if __name__ == "__main__":
    main()
