#!/usr/bin/env python3
"""Gera `docs/gd-light.md` e agregados CSV da MMGD ANEEL cruzados com a BDGD Light."""

from __future__ import annotations

import argparse
from pathlib import Path

from bdgd_light.ingest.gd import ConfiguracaoGd, analisar_gd, escrever_resultado

RAIZ = Path(__file__).resolve().parents[1]
PARQUET_PADRAO = RAIZ / "data" / "parquet"
MMGD_PADRAO = RAIZ / "data" / "gd" / "empreendimento-geracao-distribuida.parquet"
DOC_PADRAO = RAIZ / "docs" / "gd-light.md"
DADOS_PADRAO = RAIZ / "docs" / "dados"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet-dir", type=Path, default=PARQUET_PADRAO)
    parser.add_argument("--mmgd", type=Path, default=MMGD_PADRAO)
    parser.add_argument("--out", type=Path, default=DOC_PADRAO)
    parser.add_argument(
        "--out-alimentadores", type=Path, default=DADOS_PADRAO / "gd-light-alimentadores.csv"
    )
    parser.add_argument(
        "--out-conjuntos", type=Path, default=DADOS_PADRAO / "gd-light-conjuntos.csv"
    )
    parser.add_argument(
        "--out-evolucao", type=Path, default=DADOS_PADRAO / "gd-light-evolucao-anual.csv"
    )
    parser.add_argument(
        "--out-municipios-sem-chave",
        type=Path,
        default=DADOS_PADRAO / "gd-light-municipios-sem-chave.csv",
    )
    parser.add_argument(
        "--out-divergencias", type=Path, default=DADOS_PADRAO / "gd-light-divergencias.csv"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    resultado = analisar_gd(
        ConfiguracaoGd(
            parquet_dir=args.parquet_dir,
            mmgd_path=args.mmgd,
        )
    )
    escrever_resultado(
        resultado,
        out_markdown=args.out,
        out_alimentadores_csv=args.out_alimentadores,
        out_conjuntos_csv=args.out_conjuntos,
        out_evolucao_csv=args.out_evolucao,
        out_municipios_sem_chave_csv=args.out_municipios_sem_chave,
        out_divergencias_csv=args.out_divergencias,
    )


if __name__ == "__main__":
    main()
