#!/usr/bin/env python3
"""Lista as camadas de um File Geodatabase (.gdb) ou GeoPackage da BDGD.

Uso:
    python3 scripts/listar_camadas.py data/NOME_DO_ARQUIVO.gdb
"""

import sys

import pyogrio

if len(sys.argv) < 2:
    sys.exit("Uso: python3 scripts/listar_camadas.py data/ARQUIVO.gdb")

caminho = sys.argv[1]
camadas = pyogrio.list_layers(caminho)

print(f"{'CAMADA':<20} GEOMETRIA")
print("-" * 40)
for nome, geom in camadas:
    print(f"{nome:<20} {geom or '(tabela sem geometria)'}")

print(f"\n{len(camadas)} camadas.")
print("\nCamadas geográficas mais úteis da BDGD:")
print("  UNTRD  - transformadores de distribuição (pontos)")
print("  SSDMT  - segmentos de rede de média tensão (linhas)")
print("  SSDBT  - segmentos de rede de baixa tensão (linhas)")
print("  UCBT   - unidades consumidoras de baixa tensão (pontos)")
print("  UCMT   - unidades consumidoras de média tensão (pontos)")
print("  PONNOT - postes / pontos notáveis (pontos)")
print("  SUB    - subestações (polígonos)")
print("  ARAT   - área de atuação da distribuidora (polígono)")
