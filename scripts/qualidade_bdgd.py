"""Gera ``docs/qualidade-bdgd.md`` a partir das camadas Parquet da BDGD."""

from __future__ import annotations

import argparse
from pathlib import Path

from bdgd_light.qualidade import ConfiguracaoQualidade, analisar_qualidade, renderizar_markdown

RAIZ = Path(__file__).resolve().parents[1]
PARQUET_PADRAO = RAIZ / "data" / "parquet"
DESTINO_PADRAO = RAIZ / "docs" / "qualidade-bdgd.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet-dir", type=Path, default=PARQUET_PADRAO)
    parser.add_argument("--out", type=Path, default=DESTINO_PADRAO)
    parser.add_argument("--limite-ramal-m", type=float, default=300.0)
    parser.add_argument("--limite-pn-con-m", type=float, default=2000.0)
    parser.add_argument("--max-exemplos", type=int, default=5)
    return parser.parse_args()


def main() -> Path:
    args = parse_args()
    resultado = analisar_qualidade(
        ConfiguracaoQualidade(
            parquet_dir=args.parquet_dir,
            limite_ramal_m=args.limite_ramal_m,
            limite_pn_con_m=args.limite_pn_con_m,
            max_exemplos=args.max_exemplos,
        )
    )
    markdown = renderizar_markdown(resultado)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markdown, encoding="utf-8")
    return args.out


if __name__ == "__main__":
    main()
