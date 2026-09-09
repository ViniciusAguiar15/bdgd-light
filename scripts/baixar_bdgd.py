#!/usr/bin/env python3
"""Baixa e extrai o File Geodatabase da BDGD de uma distribuidora (ANEEL / ArcGIS Hub).

Uso:
    python3 scripts/baixar_bdgd.py                      # Light 2025 (padrão)
    python3 scripts/baixar_bdgd.py --dist light --ano 2024
    python3 scripts/baixar_bdgd.py --id 430f90486174407aabe3b07f50ca6150

O download mostra progresso e é retomado (HTTP Range) se o .zip parcial existir.
"""
import argparse
import os
import sys
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from bdgd_light.catalogo import ARCGIS_DATA_URL, CATALOGO  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")


def baixar(url: str, destino: str) -> None:
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    parcial = os.path.getsize(destino) if os.path.exists(destino) else 0
    req = urllib.request.Request(url)
    if parcial:
        req.add_header("Range", f"bytes={parcial}-")
    try:
        resp_ctx = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        if e.code == 416 and parcial:
            print(f"Arquivo já completo ({parcial/1e9:.2f} GB) — pulando download.")
            return
        raise
    with resp_ctx as resp:
        if parcial and resp.status != 206:
            print("Servidor não aceitou retomada — baixando do zero.")
            parcial = 0
        total = int(resp.headers.get("Content-Length", 0)) + parcial
        modo = "ab" if parcial else "wb"
        baixado = parcial
        with open(destino, modo) as f:
            while True:
                bloco = resp.read(1 << 20)
                if not bloco:
                    break
                f.write(bloco)
                baixado += len(bloco)
                if total:
                    pct = baixado * 100 / total
                    sys.stdout.write(f"\r  {baixado/1e9:.2f} GB / {total/1e9:.2f} GB ({pct:.1f}%)")
                else:
                    sys.stdout.write(f"\r  {baixado/1e9:.2f} GB")
                sys.stdout.flush()
    print("\nDownload concluído.")


def extrair(zip_path: str) -> None:
    print("Extraindo…")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(DATA)
    gdbs = sorted(d for d in os.listdir(DATA) if d.lower().endswith(".gdb"))
    for g in gdbs:
        print(f"  Geodatabase disponível: data/{g}")
    if gdbs:
        print(f"\nPróximo passo: python3 scripts/listar_camadas.py data/{gdbs[-1]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dist", default="light", help="distribuidora (light, cemig)")
    ap.add_argument("--ano", type=int, default=2025, help="ano de referência da BDGD")
    ap.add_argument("--id", dest="item_id", default=None, help="item ID do ArcGIS (ignora --dist/--ano)")
    ap.add_argument("--so-extrair", action="store_true", help="não baixa, só extrai o zip existente")
    args = ap.parse_args()

    if args.item_id:
        item_id, nome = args.item_id, f"{args.dist}_{args.item_id[:8]}"
    else:
        try:
            item_id, nome, tam = CATALOGO[(args.dist, args.ano)]
        except KeyError:
            opcoes = ", ".join(f"{d} {a}" for d, a in sorted(CATALOGO))
            sys.exit(f"Combinação não catalogada. Opções: {opcoes}")
        print(f"BDGD {args.dist.upper()} {args.ano} — {nome} ({tam})")

    zip_path = os.path.join(DATA, f"{nome}.zip")
    url = ARCGIS_DATA_URL.format(item_id=item_id)
    if not args.so_extrair:
        print(f"URL: {url}\nDestino: {zip_path}\n")
        baixar(url, zip_path)
    extrair(zip_path)


if __name__ == "__main__":
    main()
