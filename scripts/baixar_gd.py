#!/usr/bin/env python3
"""Baixa a MMGD da ANEEL para `data/gd/`, com retomada e registro da extração."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

PACKAGE_SHOW_URL = (
    "https://dadosabertos.aneel.gov.br/api/3/action/package_show"
    "?id=relacao-de-empreendimentos-de-geracao-distribuida"
)
NOMES_RECURSO = {
    "parquet": "empreendimento-geracao-distribuida.parquet",
    "zip": "empreendimento-geracao-distribuida.zip",
    "pdf": "Dicionário de dados",
}

RAIZ = Path(__file__).resolve().parents[1]
DESTINO_PADRAO = RAIZ / "data" / "gd"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destino", type=Path, default=DESTINO_PADRAO)
    parser.add_argument(
        "--prefer",
        choices=("parquet", "zip"),
        default="parquet",
        help="Formato preferido para o dado principal.",
    )
    parser.add_argument(
        "--sem-pdf",
        action="store_true",
        help="Não baixa o PDF do dicionário.",
    )
    return parser.parse_args()


def obter_recursos() -> dict[str, dict[str, object]]:
    with urllib.request.urlopen(PACKAGE_SHOW_URL) as resposta:
        conteudo = json.load(resposta)
    recursos = {}
    for recurso in conteudo["result"]["resources"]:
        nome = str(recurso.get("name", "")).strip()
        if nome == NOMES_RECURSO["parquet"]:
            recursos["parquet"] = recurso
        elif nome == NOMES_RECURSO["zip"]:
            recursos["zip"] = recurso
        elif nome == NOMES_RECURSO["pdf"] or nome.lower().startswith("dicionário de dados"):
            recursos["pdf"] = recurso
    if "parquet" not in recursos:
        for recurso in conteudo["result"]["resources"]:
            if str(recurso.get("format", "")).lower() == "parquet":
                recursos["parquet"] = recurso
                break
    if "zip" not in recursos:
        for recurso in conteudo["result"]["resources"]:
            if str(recurso.get("format", "")).lower() == "zip":
                recursos["zip"] = recurso
                break
    return recursos


def baixar(url: str, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.stat().st_size if destino.exists() else 0
    requisicao = urllib.request.Request(url)
    if parcial:
        requisicao.add_header("Range", f"bytes={parcial}-")
    try:
        contexto = urllib.request.urlopen(requisicao)
    except urllib.error.HTTPError as erro:
        if erro.code == 416 and parcial:
            print(f"{destino.name}: arquivo já completo ({parcial / 1e6:.1f} MB).")
            return
        raise
    with contexto as resposta:
        if parcial and resposta.status != 206:
            print(f"{destino.name}: servidor não retomou; reiniciando do zero.")
            parcial = 0
        total = int(resposta.headers.get("Content-Length", 0)) + parcial
        modo = "ab" if parcial else "wb"
        baixado = parcial
        with destino.open(modo) as arquivo:
            while True:
                bloco = resposta.read(1 << 20)
                if not bloco:
                    break
                arquivo.write(bloco)
                baixado += len(bloco)
                if total:
                    pct = baixado * 100.0 / total
                    sys.stdout.write(
                        f"\r{destino.name}: {baixado / 1e6:.1f} MB / {total / 1e6:.1f} MB "
                        f"({pct:.1f}%)"
                    )
                else:
                    sys.stdout.write(f"\r{destino.name}: {baixado / 1e6:.1f} MB")
                sys.stdout.flush()
    print(f"\n{destino.name}: download concluído.")


def coletar_metadados_dado(caminho: Path) -> dict[str, object]:
    info: dict[str, object] = {}
    if caminho.suffix.lower() != ".parquet":
        return info
    df = pd.read_parquet(
        caminho,
        columns=[
            "DatGeracaoConjuntoDados",
            "AnmPeriodoReferencia",
            "NomAgente",
            "SigUF",
        ],
    )
    info["data_geracao_conjunto"] = sorted(
        {str(valor) for valor in df["DatGeracaoConjuntoDados"].dropna().unique()}
    )
    info["periodo_referencia"] = sorted(
        {str(valor) for valor in df["AnmPeriodoReferencia"].dropna().unique()}
    )
    info["distribuidoras_rj"] = int(
        df.loc[df["SigUF"].astype(str).eq("RJ"), "NomAgente"].dropna().nunique()
    )
    return info


def main() -> None:
    args = parse_args()
    recursos = obter_recursos()
    if args.prefer not in recursos:
        raise SystemExit(f"recurso {args.prefer!r} não encontrado no catálogo da ANEEL")

    baixados: list[Path] = []
    principal = recursos[args.prefer]
    caminho_principal = args.destino / str(principal["name"])
    print(f"Baixando {principal['name']} → {caminho_principal}")
    baixar(str(principal["url"]), caminho_principal)
    baixados.append(caminho_principal)

    if not args.sem_pdf and "pdf" in recursos:
        pdf = recursos["pdf"]
        caminho_pdf = args.destino / Path(str(pdf["url"])).name
        print(f"Baixando {pdf['name']} → {caminho_pdf}")
        baixar(str(pdf["url"]), caminho_pdf)
        baixados.append(caminho_pdf)

    metadados = {
        "extraido_em": datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
        "package_show_url": PACKAGE_SHOW_URL,
        "formato_principal": args.prefer,
        "arquivos": [
            {
                "nome": caminho.name,
                "caminho": os.fspath(caminho.relative_to(RAIZ)),
                "bytes": caminho.stat().st_size,
            }
            for caminho in baixados
        ],
        "recurso_principal": principal,
        "metadados_dado": coletar_metadados_dado(caminho_principal),
    }
    caminho_meta = args.destino / "metadata.json"
    caminho_meta.write_text(
        json.dumps(metadados, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Metadados gravados em {caminho_meta}")


if __name__ == "__main__":
    main()
