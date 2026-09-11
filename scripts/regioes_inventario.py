#!/usr/bin/env python3
"""Tabela por região (bairros de referência) a partir de ``data/inventario_ctmt.csv``.

Reproduz a tabela de ``docs/escopo-cidade.md``: cada alimentador do município do Rio (``MUN``
3304557) vai para o bairro de referência mais próximo do centro do seu *bbox*, desde que a até
``raio_km`` dele; alimentadores longe de todos os pontos ficam de fora. Por região: n, LDA/LDS,
mediana de km MT e de UCBT, ties de campo telecomandadas (``NA_interligacao_campo_telecomandada``)
e ties em SE (``NA_interligacao_SE``).

Uso:
    uv run scripts/regioes_inventario.py [data/inventario_ctmt.csv] [--antes ANTIGO.csv]

Com ``--antes``, acrescenta as colunas do CSV antigo para comparar (issue #39: folga ``EM_SUB``).
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

MUN_RIO = "3304557"

# (região, lat, lon, raio km) — centro aproximado do bairro; raio maior onde a malha é esparsa
REFERENCIAS: list[tuple[str, float, float, float]] = [
    ("Centro", -22.905, -43.182, 1.8),
    ("Lapa/Glória", -22.917, -43.178, 1.0),
    ("Flamengo/Catete", -22.932, -43.176, 1.0),
    ("Laranjeiras/Cosme Velho", -22.937, -43.195, 1.2),
    ("Botafogo/Humaitá", -22.953, -43.188, 1.5),
    ("Copacabana/Leme", -22.970, -43.184, 1.6),
    ("Ipanema/Leblon", -22.984, -43.203, 1.4),
    ("Ipanema/Leblon", -22.984, -43.224, 1.4),
    ("Tijuca", -22.925, -43.235, 2.0),
    ("Vila Isabel/Grajaú", -22.917, -43.255, 1.8),
    ("Méier", -22.902, -43.280, 2.5),
    ("Jacarepaguá/Taquara", -22.925, -43.375, 3.5),
    ("Barra/Recreio", -23.003, -43.350, 4.0),
    ("Barra/Recreio", -23.022, -43.460, 4.0),
]
ORDEM = list(dict.fromkeys(r for r, *_ in REFERENCIAS))


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dy = (lat2 - lat1) * 111.32
    dx = (lon2 - lon1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def classificar(inventario: pd.DataFrame) -> pd.Series:
    """Região de cada CTMT (``None`` se longe de todas as referências)."""
    rio = inventario[inventario["MUN"] == MUN_RIO]
    lat = (rio["lat_min"] + rio["lat_max"]) / 2
    lon = (rio["lon_min"] + rio["lon_max"]) / 2
    regioes: list[str | None] = []
    for y, x in zip(lat, lon, strict=True):
        melhor, menor = None, math.inf
        for regiao, ry, rx, raio in REFERENCIAS:
            d = distancia_km(y, x, ry, rx)
            if d <= raio and d < menor:
                melhor, menor = regiao, d
        regioes.append(melhor)
    return pd.Series(regioes, index=rio.index, dtype="object")


def resumo(inventario: pd.DataFrame) -> pd.DataFrame:
    inv = inventario.copy()
    inv["regiao"] = classificar(inv)
    inv = inv[inv["regiao"].notna()]
    g = inv.groupby("regiao")
    tabela = pd.DataFrame(
        {
            "n": g.size(),
            "LDA": g["tipo"].apply(lambda s: int((s == "LDA").sum())),
            "LDS": g["tipo"].apply(lambda s: int((s == "LDS").sum())),
            "km_mediana": g["km_MT"].median(),
            "UCBT_mediana": g["n_UCBT"].median(),
            "ties_TLCD": g["NA_interligacao_campo_telecomandada"].sum(),
            "ties_campo": g["NA_interligacao_campo"].sum(),
            "ties_SE": g["NA_interligacao_SE"].sum(),
        }
    )
    return tabela.reindex([r for r in ORDEM if r in tabela.index]).astype(
        {c: int for c in ("n", "LDA", "LDS", "ties_TLCD", "ties_campo", "ties_SE")}
    )


def _fmt(v: float, casas: int = 0) -> str:
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _antes_depois(antes: pd.Series | None, depois: pd.Series, coluna: str) -> str:
    valor = int(depois[coluna])
    return f"{int(antes[coluna])} → {valor}" if antes is not None else f"? → {valor}"


def markdown(atual: pd.DataFrame, antes: pd.DataFrame | None = None) -> str:
    if antes is None:
        linhas = ["| região | n | LDA | LDS | km mediana | UCBT mediana | ties TLCD | ties em SE |"]
        linhas.append("|---|---|---|---|---|---|---|---|")
        for regiao, r in atual.iterrows():
            celulas = [
                regiao, int(r.n), int(r.LDA), int(r.LDS), _fmt(r.km_mediana, 1),
                _fmt(r.UCBT_mediana), int(r.ties_TLCD), int(r.ties_SE),
            ]  # fmt: skip
            linhas.append("| " + " | ".join(str(c) for c in celulas) + " |")
        return "\n".join(linhas)
    linhas = ["| região | n | ties TLCD antes → depois | ties de campo | ties em SE |"]
    linhas.append("|---|---|---|---|---|")
    for regiao, r in atual.iterrows():
        a = antes.loc[regiao] if regiao in antes.index else None
        celulas = [regiao, int(r.n)] + [
            _antes_depois(a, r, c) for c in ("ties_TLCD", "ties_campo", "ties_SE")
        ]
        linhas.append("| " + " | ".join(str(c) for c in celulas) + " |")
    return "\n".join(linhas)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("csv", nargs="?", default="data/inventario_ctmt.csv", type=Path)
    parser.add_argument("--antes", type=Path, help="CSV antigo para comparar ties por região")
    args = parser.parse_args()
    atual = resumo(pd.read_csv(args.csv, dtype={"MUN": str}))
    print(markdown(atual))
    if args.antes:
        antes = resumo(pd.read_csv(args.antes, dtype={"MUN": str}))
        print()
        print(markdown(atual, antes))
        print()
        colunas = (("ties TLCD", "ties_TLCD"), ("de campo", "ties_campo"), ("em SE", "ties_SE"))
        totais = [f"{nome} {int(antes[c].sum())} → {int(atual[c].sum())}" for nome, c in colunas]
        print("total nas regiões: " + ", ".join(totais))


if __name__ == "__main__":
    main()
