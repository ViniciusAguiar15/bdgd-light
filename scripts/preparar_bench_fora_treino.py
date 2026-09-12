"""Prepara a suíte fora do treino da issue #92.

Escreve:

- ``bench/tarefas_fora_treino.yaml`` com 10 tarefas hard;
- ``docs/bench/2026-09-11-fora-treino-casos.csv`` com os CTMTs escolhidos e o gabarito real;
- recortes temporários em ``scratch/issue-92-fora-treino/`` para a corrida do benchmark.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from bdgd_light.bench_fora_treino import preparar_benchmark_fora_treino


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generalizacao-csv",
        type=Path,
        default=Path("docs/bench/2026-09-11-generalizacao.csv"),
    )
    parser.add_argument("--inventario", type=Path, default=Path("data/inventario_ctmt.csv"))
    parser.add_argument("--parquet", type=Path, default=Path("data/parquet"))
    parser.add_argument(
        "--feeders-out", type=Path, default=Path("scratch/issue-92-fora-treino/feeders")
    )
    parser.add_argument("--dss-out", type=Path, default=Path("scratch/issue-92-fora-treino/dss"))
    parser.add_argument("--estado", type=Path, default=Path("scratch/issue-92-fora-treino/estado"))
    parser.add_argument("--tarefas-out", type=Path, default=Path("bench/tarefas_fora_treino.yaml"))
    parser.add_argument(
        "--casos-out",
        type=Path,
        default=Path("docs/bench/2026-09-11-fora-treino-casos.csv"),
    )
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--dia", default="DU")
    parser.add_argument("--mes", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    console = Console()
    casos = preparar_benchmark_fora_treino(
        generalizacao_csv=args.generalizacao_csv,
        inventario_csv=args.inventario,
        parquet_dir=args.parquet,
        feeders_dir=args.feeders_out,
        dss_out=args.dss_out,
        estado_dir=args.estado,
        tarefas_out=args.tarefas_out,
        casos_out=args.casos_out,
        n=args.n,
        dia=args.dia,
        mes=args.mes,
        console=console,
    )
    console.print(
        f"[green]{len(casos)} caso(s) preparados[/] · tarefas em {args.tarefas_out} · "
        f"casos em {args.casos_out}"
    )


if __name__ == "__main__":
    main()
