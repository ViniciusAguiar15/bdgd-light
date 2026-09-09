#!/usr/bin/env python3
"""Baixa o File Geodatabase da BDGD CEMIG-D (ANEEL) e extrai em data/.

Uso:
    python3 scripts/baixar_bdgd.py

O arquivo é grande (vários GB) — o download mostra progresso e pode ser
retomado rodando de novo (usa o .zip parcial se o servidor permitir).
"""
import os
import sys
import zipfile
import urllib.request

# Item da CEMIG-D no portal de dados abertos da ANEEL (ArcGIS Hub)
ITEM_ID = "52904205104349d19142c5892ec50844"
URL = f"https://www.arcgis.com/sharing/rest/content/items/{ITEM_ID}/data"

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
ZIP_PATH = os.path.join(DATA, "cemig-d_bdgd.zip")


def baixar():
    os.makedirs(DATA, exist_ok=True)
    print(f"Baixando BDGD CEMIG-D de:\n  {URL}")
    print(f"Destino: {ZIP_PATH}\n")

    def progresso(blocos, tam_bloco, total):
        baixado = blocos * tam_bloco
        if total > 0:
            pct = min(100, baixado * 100 / total)
            sys.stdout.write(f"\r  {baixado/1e9:.2f} GB / {total/1e9:.2f} GB ({pct:.1f}%)")
        else:
            sys.stdout.write(f"\r  {baixado/1e9:.2f} GB baixados")
        sys.stdout.flush()

    urllib.request.urlretrieve(URL, ZIP_PATH, reporthook=progresso)
    print("\nDownload concluído.")


def extrair():
    print("Extraindo…")
    with zipfile.ZipFile(ZIP_PATH) as z:
        z.extractall(DATA)
    gdbs = [d for d in os.listdir(DATA) if d.lower().endswith(".gdb")]
    if gdbs:
        print(f"Geodatabase extraído: data/{gdbs[0]}")
        print("\nPróximo passo — listar as camadas:")
        print(f"  python3 scripts/listar_camadas.py data/{gdbs[0]}")
    else:
        print("Extração concluída — verifique o conteúdo de data/.")


if __name__ == "__main__":
    if not os.path.exists(ZIP_PATH):
        baixar()
    else:
        print(f"{ZIP_PATH} já existe — pulando download (apague-o para baixar de novo).")
    extrair()
