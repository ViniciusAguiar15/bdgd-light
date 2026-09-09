# Escopo geográfico: alimentadores escolhidos

Análise preliminar feita sobre `data/parquet/{CTMT,SSDMT,UNSEMT}.parquet` (Light 2025-12-31 V11) em 2026-09-09.
Inventário completo (1.802 alimentadores) em `data/inventario_ctmt_preliminar.csv` (fora do git).

## Método
- Chave de **interligação** (tie) = chave `UNSEMT` normalmente aberta (`P_N_OPE = "A"`) cujo ponto coincide
  (raio de 2 m) com a extremidade de um segmento `SSDMT` de **outro** CTMT. Na BDGD da Light os `PAC` são
  numerados por alimentador (`<CTMT>_MT_<n>`), então **a interligação não aparece por PAC compartilhado** —
  só geometricamente. Isso vale para o grafo (issue #6) e o inventário (issue #2).
- Priorizado: município do Rio (`MUN = 3304557`), rede aérea (`LDA`), 13,8 kV (`TEN_NOM = 46`), muitas
  interligações **telecomandadas** (`TLCD = 1`), alimentadores da mesma subestação e mutuamente interligados.

## Números gerais
1.802 CTMT (1.405 no município do Rio); 64.745 chaves MT, 12.754 NA, das quais 5.031 são interligação entre
alimentadores e 875 dessas telecomandadas. Nome `LDS` = rede subterrânea (reticulada, Centro/Zona Sul),
`LDA` = aérea, `LSA` = 25 kV (`TEN_NOM = 67`, Zona Oeste, 45–90 km).

## Escolha: cluster PDG (Jacarepaguá — Freguesia / Pechincha / Anil), SE `10385916`

| CTMT | nome | km MT | MWh/ano | NA | NA tie telecomandadas |
|---|---|---|---|---|---|
| **PDG29724** | LDA MENEZES | 12,9 | 34.044 | 16 | 8 |
| **PDG33499** | LDA XINGU | 8,2 | 20.868 | — | 3 (com MENEZES) |
| **PDG29731** | LDA DANTAS | 8,7 | 30.497 | — | 3 (com MENEZES) + 1 manual com XINGU |

Bbox aproximado (EPSG:4326): lon −43,354 a −43,316; lat −22,950 a −22,922.
Motivos: três alimentadores aéreos radiais da mesma subestação, tamanho tratável em OpenDSS, e MENEZES tem
transferência de carga telecomandada para os dois vizinhos — cenário FLISR completo (isolar trecho de MENEZES,
reenergizar a jusante por XINGU ou DANTAS).

## Alternativa (Tijuca / Rio Comprido): FCN604 LDA SERTORIO (6 km), FCN929 LDA SILVESTRE, FCN1438 (LDS/LDA CAVALITO)
Menor e mais denso, mas menos interligações telecomandadas (1 por par) e um dos três é parcialmente subterrâneo.
