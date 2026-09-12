#!/usr/bin/env python3
"""Gera o atlas de interligações da Light (issue #94)."""

from __future__ import annotations

import argparse
from pathlib import Path

from bdgd_light.atlas_interligacoes import consolidar_atlas, escrever_resultado

RAIZ = Path(__file__).resolve().parents[1]
PARQUET_PADRAO = RAIZ / "data" / "parquet"
DOC_PADRAO = RAIZ / "docs" / "atlas-interligacoes.md"
DADOS_PADRAO = RAIZ / "docs" / "dados"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet-dir", type=Path, default=PARQUET_PADRAO)
    parser.add_argument("--out", type=Path, default=DOC_PADRAO)
    parser.add_argument(
        "--out-alimentadores",
        type=Path,
        default=DADOS_PADRAO / "atlas-interligacoes-alimentadores.csv",
    )
    parser.add_argument(
        "--out-arestas",
        type=Path,
        default=DADOS_PADRAO / "grafo-socorro-arestas.csv",
    )
    parser.add_argument(
        "--out-graphml",
        type=Path,
        default=DADOS_PADRAO / "grafo-socorro.graphml",
    )
    parser.add_argument(
        "--out-svg",
        type=Path,
        default=DADOS_PADRAO / "grau-socorro-histograma.svg",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    resultado = consolidar_atlas(args.parquet_dir)
    escrever_resultado(
        resultado,
        out_markdown=args.out,
        out_alimentadores_csv=args.out_alimentadores,
        out_arestas_csv=args.out_arestas,
        out_graphml=args.out_graphml,
        out_svg=args.out_svg,
    )


if __name__ == "__main__":
    main()
