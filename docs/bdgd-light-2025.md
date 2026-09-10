# BDGD Light 2025-12-31 V11 — notas de referência

Descobertas sobre a base `Light_382_2025-12-31_V11_20260824-0926.gdb` (ANEEL, distribuidora 382),
levantadas em 2026-09-09 ao implementar o `bdgd-light export` (issue #1). Complementam o
[Manual da BDGD](https://dadosabertos-aneel.opendata.arcgis.com/documents/f0d5c43ac67d4f5eb2ddffa4589501b2)
(Módulo 10 do PRODIST) com o que **vale para esta base**, que nem sempre coincide com o modelo genérico.

## Arquivo

- File Geodatabase (driver `OpenFileGDB` do GDAL), 1,14 GB zipado, **43 camadas**.
- CRS de todas as camadas geográficas: **SIRGAS 2000 (EPSG:4674)**; coluna de geometria `Shape`
  (o `export` renomeia para `geometry`).
- Identificador universal `COD_ID`; chave de alimentador `CTMT`; código da distribuidora `DIST = 382`.

## Camadas e contagens

| camada | geometria | feições |
|---|---|---|
| `ARAT` | MultiPolygon | 1 |
| `BAR` | tabela | 5.851 |
| `BASE` | tabela | 1 |
| `BAY` | tabela | 373 |
| `BE` | tabela | 15 |
| `CONJ` | MultiPolygon | 109 |
| `CRVCRG` | tabela | 132 |
| `CTAT` | tabela | 189 |
| `CTMT` | **tabela** | 1.802 |
| `EP` | tabela | 5 |
| `EQCR` | tabela | 795 |
| `EQME` | tabela | 5.400.627 |
| `EQRE` | tabela | 74 |
| `EQSE` | tabela | 189.980 |
| `EQTRAT` | tabela | 321 |
| `EQTRM` | tabela | 33.527 |
| `EQTRMT` | tabela | 101.064 |
| `PIP` | tabela | 835.142 |
| `PNT` | tabela | 2 |
| `PONNOT` | Point | 882.200 |
| `PT` | tabela | 9 |
| `RAMLIG` | **tabela** | 3.818.151 |
| `SEGCON` | tabela | 1.223 |
| `SSDAT` | MultiLineString | 7.952 |
| `SSDBT` | MultiLineString | 1.789.778 |
| `SSDMT` | MultiLineString | 1.000.817 |
| `SUB` | MultiPolygon | 238 |
| `UCAT_tab` | tabela | 52 |
| `UCBT_tab` | tabela | 5.041.346 |
| `UCMT_tab` | tabela | 7.660 |
| `UGAT_tab` | tabela | 12 |
| `UGBT_tab` | tabela | 57.523 |
| `UGMT_tab` | tabela | 670 |
| `UNCRAT` | Point | 17 |
| `UNCRBT` | Point | 0 |
| `UNCRMT` | Point | 778 |
| `UNREAT` | Point | 0 |
| `UNREMT` | Point | 26 |
| `UNSEAT` | Point | 2.216 |
| `UNSEBT` | Point | 26.432 |
| `UNSEMT` | Point | 64.745 |
| `UNTRAT` | Point | 311 |
| `UNTRMT` | Point | 99.490 |

## Diferenças em relação ao modelo "de manual"

1. **`CTMT` é uma tabela** (sem geometria). O traçado do alimentador é a união dos `SSDMT` com
   `CTMT = <COD_ID>`; o inventário calcula o *bbox* a partir deles.
2. **Não existem as camadas geográficas `UCBT`, `UCMT`, `UGBT`, `UGMT`** (nem `UCAT`/`UGAT`): unidades
   consumidoras e geradoras vêm só como tabelas `*_tab`, sem ponto. A localização aproximada de uma UC é
   o poste `PN_CON` (→ `PONNOT`) ou o transformador `UNI_TR_MT` (→ `UNTRMT`). Por isso o modo padrão do
   `export` avisa e pula essas quatro camadas de `CAMADAS_CHAVE`.
3. **`RAMLIG` (ramais de ligação) também é tabela**, com 3,8 M de linhas; liga-se à rede por
   `PAC_1/PAC_2`, `PN_CON_1/PN_CON_2` e `UNI_TR_MT`.
4. **`PONNOT` não tem coluna `CTMT`**: postes de um alimentador são obtidos pelos `PN_CON*` de
   `SSDMT`/`SSDBT`/`RAMLIG`/`UC*_tab` (100 % dos `PN_CON` da base resolvem em `PONNOT.COD_ID`).
5. **Subestação**: a camada **`SUB` existe** (238 polígonos, com `NOME`, ex.: `10385916` =
   "SETD PORTA DAGUA"); `CTMT.SUB` e `UNTRAT.SUB` apontam para `SUB.COD_ID` em 100 % dos casos e
   `CTMT.UNI_TR_AT` → `UNTRAT.COD_ID` também em 100 %. `UNTRAT` **não** tem nome — o nome da SE vem de
   `SUB.NOME`. `UNTRAT.TIP_UNID` é sempre `41` (transformador de força AT/MT).
6. **`PAC` é numerado por alimentador**: `<CTMT>_MT_<n>` na rede MT (`BRI003_MT_535472`) e
   `<UNTRMT>_BT_<n>` na BT (`11106463_BT_3327115`). 99,95 % dos `PAC` de `SSDMT` têm o prefixo do próprio
   `CTMT` e **nenhum `PAC` de `SSDMT` aparece em dois CTMT**. Consequência: a interligação entre
   alimentadores (chave NA de *tie*) **não** aparece como PAC compartilhado — só geometricamente (ponto da
   `UNSEMT` a ≤ 2 m de uma extremidade de `SSDMT` de outro CTMT), ver
   [`escopo-alimentadores.md`](escopo-alimentadores.md) e [`bdgd-relacoes.md`](bdgd-relacoes.md). Nas
   NA, 177 de 12.754 têm `PAC_1`/`PAC_2` com prefixo de outro CTMT (a chave está cadastrada num
   alimentador e seus PAC no vizinho).
7. `UCBT_tab` traz **`CTMT` e `UNI_TR_MT`**; em 4.444 linhas (0,09 %) o `CTMT` da UC difere do `CTMT` do
   transformador. O projeto segue o transformador (`UNI_TR_MT` → `UNTRMT.CTMT`), que é a ligação física.
   `RAMLIG` tem `PN_CON_2 = " "` (espaço) em algumas linhas — referência em branco, não a um poste.
8. `CTMT.TEN_OPE` está em **pu** (1,000–1,045); `ATIP = 1` em 561 alimentadores e `RECONFIG = 1` em 290.

## Domínios usados no projeto

### `TEN_NOM` (tabela de domínio *TEN* do Manual)

Códigos presentes em `CTMT`: **`46` (1.665 alimentadores) e `67` (137)**. Segundo a tabela de domínio
*TEN* (replicada, entre outros, pelo `bdgd2opendss`): `46` = **13,2 kV**, `49` = 13,8 kV, `67` = **25 kV**
(`37` = 6,6 kV, `72` = 34,5 kV). Observações:

- A hipótese inicial "46 = 13,8 kV" **não bate com o domínio** e foi descartada: a rede que a Light
  divulga como "13,8 kV" aparece na BDGD como `46`, e o projeto adota o domínio — **`TEN_NOM = 46` →
  13,2 kV** (`catalogo.TENSAO_KV`, inventário, escopo). Nos transformadores desses alimentadores
  `EQTRMT.TEN_PRI` mistura `46` (13,2) e `49` (13,8). Para o gêmeo OpenDSS, usar a tensão do domínio e
  `TEN_OPE` (pu) do `CTMT`.
- Prefixo do `NOME` × `TEN_NOM`: `LDA` (1.011, rede aérea) e `LDS` (653, rede subterrânea) são todos
  `46`; `LSA` (121) e `LSS` (16) são `67` (25 kV, Zona Oeste), salvo um `LSA` em `46`; há um `TRAFO`.

### `TIP_UNID` de `UNSEMT` (tabela de domínio *TIP_UNID* do Manual)

Contagens na Light 2025 (`P_N_OPE = "A"` = normalmente aberta; `TLCD = 1` = telecomandada):

| código | descrição (Manual da BDGD) | chaves | NA | telecomandadas |
|---|---|---|---|---|
| `19` | Chave faca | 34.184 | 10.717 | 0 |
| `22` | Chave fusível | 14.440 | 177 | 2 |
| `16` | Chave a gás | 4.545 | 115 | 1.304 |
| `32` | Religador | 3.787 | 1.101 | 3.625 |
| `29` | Disjuntor | 3.377 | 416 | 2.715 |
| `35` | Seccionalizador | 2.969 | 96 | 80 |
| `27` | Chave fusível religadora (três operações) | 735 | 0 | 0 |
| `33` | Seccionadora tripolar de subestação | 495 | 105 | 0 |
| `20` | Chave faca tripolar com abertura em carga | 181 | 27 | 0 |
| `18` | Chave de transferência automática | 30 | 0 | 0 |
| `17` | Chave a óleo | 2 | 0 | 0 |

Outros códigos do mesmo domínio (não ocorrem em `UNSEMT` da Light 2025): `21` chave faca unipolar com
abertura em carga, `23`–`26` variantes de chave fusível, `28` chave motorizada, `30` disjuntor de
interligação de barra, `31` lâmina desligadora, `34` seccionadora unipolar de subestação,
`36` seccionalizador monofásico, `38` transformador de distribuição MT/BT (`UNTRMT`),
`41` transformador de força AT/MT (`UNTRAT`), `46` fusível (`UNSEBT`).

Totais: 64.745 chaves MT, 12.754 NA (`P_N_OPE = "A"`), 7.726 telecomandadas. Das NA, **5.144** são
interligação entre alimentadores pelo critério geométrico de 2 m implementado em
`ingest/interligacoes.py` (5.833 pares chave × CTMT vizinho; 896 telecomandadas; 393 dentro do polígono
de uma `SUB`, quase todas disjuntores `29` de saída de alimentadores da mesma SE; 296 chaves tocam 2
CTMT e 139 tocam ≥ 3 — barramentos). 1.403 dos 1.802 CTMT têm ao menos uma interligação. Os números da
análise preliminar em [`escopo-alimentadores.md`](escopo-alimentadores.md) (5.031 / 875) vieram de um
script anterior; os de referência são os do comando `inventario`. Quase todo o telecomando está em
religadores, disjuntores e chaves a gás. Regras de junção e ressalvas em
[`bdgd-relacoes.md`](bdgd-relacoes.md).

### Outros

- `P_N_OPE`: `F` = normalmente fechada (NF), `A` = normalmente aberta (NA).
- `SIT_ATIV`: `AT` ativada, `DS` desativada (todas as `UNSEMT` da Light 2025 são `AT`).
- `TIP_INST` de `SSDMT`/`SSDBT`: `RD_AER_URB` (542 k trechos MT), `RD_SUBT_URB` (371 k), `RD_AER_RUR`
  (86 k), `RD_SUBT_RUR` (2 k) — é o que distingue rede aérea de subterrânea trecho a trecho.
- `MUN`: código IBGE de 7 dígitos (`3304557` = Rio de Janeiro); `CTMT` não tem `MUN`, o inventário usa o
  município majoritário dos `UNTRMT` do alimentador.
- Energia mensal `ENE_01..ENE_12` em **kWh** (`CTMT`, `UC*_tab`, `UG*_tab`); `POT_NOM` de `UNTRMT` em
  kVA (5 a 8.000, mediana 112,5); `COMP` de `SSDMT`/`SSDBT` em metros.
