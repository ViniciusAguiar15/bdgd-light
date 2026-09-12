#!/usr/bin/env python3
"""Roda a generalização do pipeline em alimentadores nunca vistos (issue #91)."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from rich.console import Console

from bdgd_light.generalizacao import (
    ConfiguracaoGeneralizacao,
    agrupar_falhas,
    descrever_amostra,
    executar_generalizacao,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventario", type=Path, default=Path("data/inventario_ctmt.csv"))
    parser.add_argument("--parquet", type=Path, default=Path("data/parquet"))
    parser.add_argument("--out", type=Path, default=Path("docs/bench/2026-09-11-generalizacao.csv"))
    parser.add_argument("--workdir", type=Path, default=Path("scratch/issue-91-generalizacao"))
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--seed", type=int, default=91)
    parser.add_argument("--dia", default="DU")
    parser.add_argument("--mes", type=int, default=1)
    parser.add_argument(
        "--manter-workdir",
        action="store_true",
        help="Não remove o diretório de trabalho no início/fim da execução.",
    )
    args = parser.parse_args()
    console = Console()
    config = ConfiguracaoGeneralizacao(
        inventario_csv=args.inventario,
        parquet_dir=args.parquet,
        workdir=args.workdir,
        out_csv=args.out,
        n=args.n,
        seed=args.seed,
        dia=args.dia.upper(),
        mes=args.mes,
        limpar_workdir=not args.manter_workdir,
    )
    amostra, resultados, resumo = executar_generalizacao(config, console=console)
    console.print("[bold green]Amostra sorteada[/]")
    console.print(descrever_amostra(amostra))
    console.print()
    console.print(resumo.to_string(index=False))
    falhas = agrupar_falhas(resultados)
    if not falhas.empty:
        console.print()
        console.print("[bold yellow]Falhas agrupadas[/]")
        console.print(falhas.to_string(index=False))
    console.print(f"\n[green]CSV gravado em[/] {args.out}")
    if not args.manter_workdir and args.workdir.exists():
        shutil.rmtree(args.workdir)


if __name__ == "__main__":
    main()
