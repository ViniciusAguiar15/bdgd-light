#!/usr/bin/env python3
"""Gera `docs/gd-restauracao.md` com a comparação da issue #99."""

from __future__ import annotations

import argparse
from pathlib import Path

from bdgd_light.gd_restauracao import (
    materializar_casos_alimentadores,
    montar_casos_cenarios,
    renderizar_relatorio,
    rodar_analise,
    selecionar_alimentadores_alta_penetracao,
)
from bdgd_light.twin import ConfiguracaoGd

RAIZ = Path(__file__).resolve().parents[1]
PARQUET_PADRAO = RAIZ / "data" / "parquet"
MMGD_PADRAO = RAIZ / "data" / "gd" / "empreendimento-geracao-distribuida.parquet"
FEEDERS_PADRAO = RAIZ / "data" / "feeders"
INVENTARIO_PADRAO = RAIZ / "data" / "inventario_ctmt.csv"
ALOCACAO_PADRAO = RAIZ / "docs" / "dados" / "gd-gemeo-alocacao.csv"
DSS_PADRAO = RAIZ / "data" / "dss" / "gpkg_issue99"
OUT_PADRAO = RAIZ / "docs" / "gd-restauracao.md"
OUT_OPCOES_PADRAO = RAIZ / "docs" / "dados" / "gd-restauracao-opcoes.csv"
OUT_RESUMO_PADRAO = RAIZ / "docs" / "dados" / "gd-restauracao-resumo.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet-dir", type=Path, default=PARQUET_PADRAO)
    parser.add_argument("--mmgd", type=Path, default=MMGD_PADRAO)
    parser.add_argument("--feeders-dir", type=Path, default=FEEDERS_PADRAO)
    parser.add_argument("--inventario-csv", type=Path, default=INVENTARIO_PADRAO)
    parser.add_argument("--alocacao-csv", type=Path, default=ALOCACAO_PADRAO)
    parser.add_argument("--dss-out", type=Path, default=DSS_PADRAO)
    parser.add_argument("--dia", default="DU")
    parser.add_argument("--mes", type=int, default=9)
    parser.add_argument("--out", type=Path, default=OUT_PADRAO)
    parser.add_argument("--out-opcoes", type=Path, default=OUT_OPCOES_PADRAO)
    parser.add_argument("--out-resumo", type=Path, default=OUT_RESUMO_PADRAO)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out_opcoes.parent.mkdir(parents=True, exist_ok=True)
    args.out_resumo.parent.mkdir(parents=True, exist_ok=True)
    args.dss_out.mkdir(parents=True, exist_ok=True)

    selecionados = selecionar_alimentadores_alta_penetracao(args.alocacao_csv)
    casos = montar_casos_cenarios(args.feeders_dir)
    casos += materializar_casos_alimentadores(
        selecionados,
        parquet_dir=args.parquet_dir,
        inventario_csv=args.inventario_csv,
        feeders_dir=args.feeders_dir,
    )
    gd_cfg = ConfiguracaoGd(parquet_dir=args.parquet_dir, mmgd_path=args.mmgd)
    opcoes, resumo, comparacao = rodar_analise(
        casos,
        dss_out=args.dss_out,
        dia=args.dia,
        mes=args.mes,
        gd_cfg=gd_cfg,
    )
    opcoes.to_csv(args.out_opcoes, index=False)
    resumo.to_csv(args.out_resumo, index=False)
    args.out.write_text(
        renderizar_relatorio(
            opcoes=opcoes,
            resumo=resumo,
            comparacao=comparacao,
            casos=casos,
            alimentadores_selecionados=selecionados,
            dia=args.dia,
            mes=args.mes,
            out_opcoes_csv=args.out_opcoes.relative_to(RAIZ),
            out_resumo_csv=args.out_resumo.relative_to(RAIZ),
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
