#!/usr/bin/env python3
"""Converte uma camada da BDGD (.gdb) para GeoJSON em WGS84 (EPSG:4326),
com recorte opcional por área (bbox), pronto para abrir no index.html.

Exemplos:
    # Camada inteira (cuidado: CEMIG cobre MG inteira, pode ficar gigante)
    python3 scripts/converter.py data/Cemig.gdb UNTRD

    # Recortando por área — ex.: região central de Belo Horizonte
    python3 scripts/converter.py data/Cemig.gdb UNTRD --bbox -44.02 -19.95 -43.90 -19.88

    # Limitando o número de feições (para testar rápido)
    python3 scripts/converter.py data/Cemig.gdb UCBT --bbox -44.02 -19.95 -43.90 -19.88 --max 50000

Dica: pegue o bbox desenhando no site https://boundingbox.klokantech.com
(formato CSV: min_lon, min_lat, max_lon, max_lat).
"""
import argparse
import os

import geopandas as gpd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("gdb", help="caminho do .gdb (ou .gpkg)")
    ap.add_argument("camada", help="nome da camada, ex.: UNTRD, SSDMT, UCBT")
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
                    help="recorte por área em graus (lon/lat)")
    ap.add_argument("--max", type=int, default=None, help="máximo de feições")
    ap.add_argument("-o", "--saida", default=None, help="arquivo de saída (.geojson)")
    args = ap.parse_args()

    kwargs = {"layer": args.camada, "engine": "pyogrio"}
    if args.bbox:
        # BDGD usa SIRGAS 2000 (EPSG:4674), em graus — bbox lon/lat funciona direto
        kwargs["bbox"] = tuple(args.bbox)
    if args.max:
        kwargs["max_features"] = args.max

    print(f"Lendo {args.camada} de {args.gdb}…")
    gdf = gpd.read_file(args.gdb, **kwargs)
    print(f"  {len(gdf):,} feições lidas.")

    if len(gdf) == 0:
        print("Nada dentro do filtro — confira o nome da camada e o bbox.")
        return

    if gdf.crs is None:
        gdf = gdf.set_crs(4674)  # SIRGAS 2000, padrão da BDGD
    gdf = gdf.to_crs(4326)

    # Datas/tipos não serializáveis viram texto
    for col in gdf.columns:
        if col != gdf.geometry.name and gdf[col].dtype == "object":
            continue
        if str(gdf[col].dtype).startswith("datetime"):
            gdf[col] = gdf[col].astype(str)

    saida = args.saida or os.path.join(BASE, "data", f"{args.camada.lower()}.geojson")
    gdf.to_file(saida, driver="GeoJSON")
    tam = os.path.getsize(saida) / 1e6
    print(f"OK → {saida} ({tam:.1f} MB)")
    print("Abra o index.html no navegador e arraste esse arquivo para o mapa.")
    if tam > 80:
        print("AVISO: arquivo grande — o navegador pode ficar lento. "
              "Use --bbox menor ou --max para reduzir.")


if __name__ == "__main__":
    main()
