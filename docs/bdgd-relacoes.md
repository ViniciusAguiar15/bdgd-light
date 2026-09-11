# Relações entre camadas da BDGD (regras de junção)

Como o projeto liga as camadas da BDGD entre si — as regras que `bdgd-light inventario`, `vizinhos` e
`recortar` (`src/bdgd_light/ingest/{inventario,interligacoes,recorte}.py`) aplicam. Tudo foi verificado
na Light 2025-12-31 V11 (particularidades da base em [`bdgd-light-2025.md`](bdgd-light-2025.md)) e
reproduzido na fixture sintética `tests/fixtures/bdgd_mini.gpkg`.

## Visão geral

```
SUB ──COD_ID──┐
              ├── CTMT.SUB / UNTRAT.SUB          (subestação inteira → CTMT)
UNTRAT ───────┘   CTMT.UNI_TR_AT → UNTRAT.COD_ID

CTMT.COD_ID ── coluna CTMT ──> SSDMT, UNSEMT, UNTRMT, UNREMT, UNCRMT, UCMT_tab, UGMT_tab
                                  │
UNTRMT.COD_ID ── UNI_TR_MT ──> SSDBT, UNSEBT, RAMLIG, UCBT_tab, UGBT_tab       (rede BT)
                                  │
PN_CON / PN_CON_1 / PN_CON_2 ──> PONNOT.COD_ID                                  (postes)
UNI_TR_MT / UN_SE / UN_RE / UN_CR ──> EQTRMT / EQSE / EQRE / EQCR              (equipamentos)
TIP_CND ──> SEGCON.COD_ID ; TIP_CC ──> CRVCRG.COD_ID                           (catálogos)

interligação entre CTMT: UNSEMT (NA) ≤ 2 m de extremidade de SSDMT de outro CTMT (geométrica)
```

## Tabela de junção por camada

Regra usada pelo recorte (`recortar`) para decidir o que pertence a um CTMT, e colunas envolvidas.

| camada | tipo (Light 2025) | pertence ao CTMT quando… | colunas usadas |
|---|---|---|---|
| `CTMT` | tabela | `COD_ID` é o alimentador | `COD_ID`, `NOME`, `SUB`, `UNI_TR_AT`, `TEN_NOM`, `ENE_01..12`, `PAC_INI` |
| `SUB` | polígono | `COD_ID = CTMT.SUB` (**subestação inteira**, não só o CTMT) | `COD_ID`, `NOME` |
| `UNTRAT` | ponto | `SUB = CTMT.SUB` (todos os trafos AT/MT da SE; `CTMT.UNI_TR_AT` diz qual alimenta o CTMT) | `COD_ID`, `SUB` |
| `SSDMT` | linha | `CTMT` | `CTMT`, `PAC_1`, `PAC_2`, `PN_CON_1`, `PN_CON_2`, `COMP`, `TIP_CND` |
| `UNSEMT` | ponto | `CTMT` (só as chaves **do** CTMT; as do vizinho ficam em `INTERLIGACOES`) | `CTMT`, `PAC_1`, `PAC_2`, `P_N_OPE`, `TLCD`, `TIP_UNID`, `PN_CON` |
| `UNTRMT` | ponto | `CTMT` | `COD_ID`, `CTMT`, `POT_NOM`, `MUN`, `PAC_1..3`, `PN_CON` |
| `UNREMT`, `UNCRMT` | ponto | `CTMT` | `COD_ID`, `CTMT` |
| `UCMT_tab`, `UGMT_tab` | tabela | `CTMT` (unidades ligadas direto na MT) | `CTMT`, `PAC`, `PN_CON`, `TIP_CC`, `ENE_01..12` / `POT_INST` |
| `SSDBT` | linha | `UNI_TR_MT` ∈ UNTRMT do CTMT | `UNI_TR_MT`, `PAC_1`, `PAC_2`, `PN_CON_1`, `PN_CON_2`, `TIP_CND` |
| `UNSEBT` | ponto | `UNI_TR_MT` ∈ UNTRMT do CTMT | `UNI_TR_MT`, `PN_CON` |
| `RAMLIG` | tabela (Light) | `UNI_TR_MT` ∈ UNTRMT do CTMT | `UNI_TR_MT`, `PAC_1`, `PAC_2`, `PN_CON_1`, `PN_CON_2`, `TIP_CND` |
| `UCBT_tab`, `UGBT_tab` | tabela | `UNI_TR_MT` ∈ UNTRMT do CTMT (**não** pela coluna `CTMT` da tabela, ver abaixo) | `UNI_TR_MT`, `CTMT`, `PAC`, `PN_CON`, `TIP_CC`, `ENE_01..12` / `POT_INST` |
| `PIP` | tabela (Light) | `UNI_TR_MT` ∈ UNTRMT do CTMT (iluminação pública; o bdgd2opendss a modela como carga `BT_IP<COD_ID>`) | `UNI_TR_MT`, `CTMT`, `PAC`, `PN_CON`, `TIP_CC`, `ENE_01..12` |
| `UCBT`, `UCMT`, `UGBT`, `UGMT` | (inexistentes na Light 2025) | mesmas regras das `*_tab`, se existirem | — |
| `PONNOT` | ponto | `COD_ID` ∈ união de `PN_CON`, `PN_CON_1`, `PN_CON_2` de todas as camadas já selecionadas (não tem `CTMT`); quando a referência vem de `UCBT`/`UCBT_tab`, o poste precisa ficar a até 2 km do transformador da UC; o *bbox* da rede + 500 m segue como rede de segurança | `COD_ID` |
| `EQTRMT` | tabela | `UNI_TR_MT` ∈ UNTRMT do CTMT | `UNI_TR_MT`, `POT_NOM`, `TEN_PRI` |
| `EQSE` | tabela | `UN_SE` ∈ UNSEMT ∪ UNSEBT do CTMT | `UN_SE` |
| `EQRE`, `EQCR` | tabela | `UN_RE` ∈ UNREMT / `UN_CR` ∈ UNCRMT | `UN_RE`, `UN_CR` |
| `SEGCON` | tabela (catálogo de cabos) | `COD_ID` ∈ `TIP_CND` de SSDMT ∪ SSDBT ∪ RAMLIG selecionados | `COD_ID` |
| `CRVCRG` | tabela (curvas de carga) | `COD_ID` ∈ `TIP_CC` de UCBT_tab ∪ UCMT_tab ∪ PIP selecionadas | `COD_ID` |
| `INTERLIGACOES` | ponto (**calculada**) | `CTMT` **ou** `CTMT_VIZ` é o alimentador | ver "Interligação entre alimentadores" |

Camadas ausentes no Parquet são puladas com aviso (a Light 2025 não tem `UCBT`/`UCMT`/`UGBT`/`UGMT`
geográficas nem `EQRE`/`EQCR` em `CAMADAS_CHAVE`); camadas presentes mas sem feição para o CTMT não
são gravadas no GPKG, mas aparecem com `0` no `meta.json`.

## Detalhes e justificativas

### `PAC` — ponto de acoplamento

- `PAC_1`/`PAC_2` (e `PAC_3` em UNTRMT trifásicos, `PAC` em UC/UG) identificam os nós elétricos. Na Light
  são numerados **por alimentador**: `<CTMT>_MT_<n>` na MT e `<UNTRMT>_BT_<n>` na BT.
- **Nenhum `PAC` de `SSDMT` aparece em dois CTMT** (verificado nas 1,0 M de linhas). Por isso o `PAC`
  serve para montar o grafo **dentro** de um alimentador (issue #6), mas **não** para achar a
  interligação entre alimentadores — daí a regra geométrica abaixo.
- `CTMT.PAC_INI` (ponto inicial do alimentador) nunca coincide com um PAC de SSDMT na Light 2025: é
  **sempre o `PAC_1` de uma `UNSEMT`** (1.802 de 1.802) — o barramento da SE, de onde sai o disjuntor
  (`TIP_UNID = 29`) cujo `PAC_2` já é um PAC de SSDMT. O grafo (`docs/grid-modelo.md`) usa `PAC_INI`
  como nó-fonte.
- Nas chaves NA, 177 de 12.754 têm `PAC_1`/`PAC_2` com prefixo de outro CTMT (a chave está cadastrada
  num alimentador e seus PAC no vizinho). O recorte mantém a chave em quem a cadastrou (coluna `CTMT`).

### Rede BT: pelo transformador, não pela coluna `CTMT`

`UCBT_tab` (e `UGBT_tab`) trazem `CTMT` **e** `UNI_TR_MT`. Em 4.444 linhas (0,09 %) o `CTMT` da UC
difere do `CTMT` do transformador `UNI_TR_MT`. O projeto segue **o transformador** (`UNI_TR_MT →
UNTRMT.CTMT`), que é a ligação física: quem alimenta a UC é o trafo, e é ele que muda de alimentador
numa transferência de carga. Consequência: `SSDBT`, `UNSEBT`, `RAMLIG`, `UCBT_tab` e `UGBT_tab` de um
recorte referenciam apenas `UNTRMT` do próprio recorte (os testes garantem isso). Só quando `UNTRMT`
não está disponível a coluna `CTMT` dessas camadas é usada como *fallback*.

Na fixture sintética a UC `UC00007` tem `CTMT = "RJO002"` mas `UNI_TR_MT = TR003` (de `RJO001`):
ela é contada e recortada em `RJO001`.

### Subestação (`SUB`, `UNTRAT`)

`CTMT.SUB` → `SUB.COD_ID` e `CTMT.UNI_TR_AT` → `UNTRAT.COD_ID` resolvem em 100 % dos casos.
`UNTRAT` não tem `NOME`; o nome da SE vem de `SUB.NOME`. O recorte leva **toda a subestação** (polígono
`SUB` e todos os `UNTRAT` com `SUB = CTMT.SUB`), porque a modelagem em OpenDSS precisa da fonte
equivalente e os alimentadores de um cluster costumam partir da mesma SE.

### Postes (`PONNOT`)

`PONNOT` não tem `CTMT`. Os postes de um alimentador são os `COD_ID` referenciados por `PN_CON`
(UNSEMT, UNTRMT, UNSEBT, UC*/UG*_tab), `PN_CON_1`/`PN_CON_2` (SSDMT, SSDBT, RAMLIG) das feições
selecionadas — 100 % dos `PN_CON` da base resolvem em `PONNOT.COD_ID`. Postes sem nenhuma referência
(órfãos) nunca entram num recorte.

Resolver não quer dizer estar perto: na Light 2025 parte dos `UCBT_tab.PN_CON` aponta para postes a
dezenas de km do alimentador (22 dos 1.908 postes do cluster Tijuca, a 5–84 km da rede — sete em
Paraíba do Sul e um em Nova Iguaçu, pelo `MUN`; 5 em Ipanema, um deles em Paracambi, referenciado por
149 UCs; 13 em TQR), o que fazia o *bbox* do recorte e dos tiles cobrir meia região metropolitana
(issue #40). Agora o recorte trata isso primeiro pela **ligação topológica** da UC: um poste puxado
só por `UCBT`/`UCBT_tab` precisa ficar a até **2 km do transformador `UNI_TR_MT`**; se não houver
dados suficientes para medir, entra a rede de segurança geométrica anterior (`--folga-bbox`, 500 m,
sobre a união de `SSDMT`, `SSDBT`, `UNSEMT`, `UNSEBT`, `UNTRMT`, `UNREMT`, `UNCRMT` e `RAMLIG`). A
UC continua em `UCBT_tab` (é carga do transformador), e o `meta.json` registra em `avisos` quantos
postes saíram. `bdgd-light tiles` aplica o mesmo filtro por *bbox* ao ler o GPKG, para recortes
gerados antes.

### Equipamentos e catálogos

- `EQTRMT.UNI_TR_MT` → `UNTRMT.COD_ID` (dados elétricos do trafo: `POT_NOM`, `TEN_PRI`, `TEN_SEC`,
  perdas); `EQSE.UN_SE` → `UNSEMT`/`UNSEBT`; `EQRE.UN_RE` → `UNREMT`; `EQCR.UN_CR` → `UNCRMT`.
- `SEGCON` (cabos) é referenciado por `TIP_CND` de SSDMT/SSDBT/RAMLIG; `CRVCRG` (curvas de carga
  típicas) por `TIP_CC` de UC*_tab. O recorte leva só os códigos efetivamente usados.

### Interligação entre alimentadores (chave NA de *tie*)

Regra (`ingest/interligacoes.py::detectar_interligacoes`, parâmetro `--raio-tie`, padrão **2 m**):

1. candidatas = `UNSEMT` com `P_N_OPE = "A"` (normalmente abertas; NF nunca contam);
2. extremidades = primeiro e último vértice de cada `SSDMT` (`PAC_1`/`PAC_2`);
3. reprojeta chaves e extremidades para um CRS métrico (UTM SIRGAS 2000; EPSG:31983 para o Rio) e
   consulta um STRtree: chave e extremidade a ≤ raio **e** `SSDMT.CTMT ≠ UNSEMT.CTMT`;
4. uma linha por par (chave, CTMT vizinho), com a extremidade mais próxima (`SSDMT_VIZ`, `PAC_VIZ`,
   `DIST_M`); `EM_SUB = True` quando o ponto da chave está dentro de um polígono `SUB`.

Colunas da camada `INTERLIGACOES`: `COD_ID` (chave), `CTMT` (dono da chave), `CTMT_VIZ`, `SSDMT_VIZ`,
`PAC_VIZ`, `DIST_M`, `P_N_OPE`, `TLCD`, `TIP_UNID`, `EM_SUB`, geometria (ponto, CRS da base).

Contagens (`contar_por_ctmt`): `NA_interligacao` = nº de **chaves distintas** que interligam o CTMT a
qualquer outro, contando dos dois lados (a chave cadastrada em A que toca B conta para A e para B);
`NA_interligacao_telecomandada` = as com `TLCD = 1`; `NA_interligacao_SE` = as com `EM_SUB`;
`NA_interligacao_campo` e `NA_interligacao_campo_telecomandada` = as **sem** `EM_SUB` (ties de campo,
as que um FLISR pode usar); `vizinhos` = CTMT distintos. O `score` do inventário usa só as de campo
(`NA_interligacao_campo × (n_UCBT + n_UCMT)`), e `bdgd-light vizinhos` desconta as da SE por padrão
(`--sem-se`; `--com-se` mostra tudo). No `meta.json` do recorte cada par CTMT–vizinho traz as duas
visões (`ties*`/`chaves` e `ties_campo*`/`chaves_campo`).

Ressalvas medidas na Light 2025 (5.833 pares, 5.144 chaves, 896 telecomandadas):

- **Chaves dentro da SE** (393, quase todas `TIP_UNID = 29` disjuntores, `EM_SUB = True`): são os
  disjuntores de saída dos alimentadores da mesma subestação, cujas extremidades de `SSDMT` se
  encostam no barramento. Elétrica e operacionalmente não são *ties* de campo; ficam contadas em
  `NA_interligacao` (a regra pedida é puramente geométrica) e descontadas em
  `NA_interligacao_campo`. Em MENEZES (`PDG29724`), 7 das 11 chaves próprias detectadas estão na SE
  Porta d'Água — e a relação com XINGU/DANTAS era toda via esses disjuntores, motivo pelo qual o
  [`escopo-alimentadores.md`](escopo-alimentadores.md) (v2) trocou para o cluster TQR (PARNAIBA /
  CURUMAU / BOCARI), cujas 17 ties entre os três são todas de campo (4 telecomandadas).
- **Vários vizinhos no raio**: 296 chaves têm 2 CTMT vizinhos a ≤ 2 m e 139 têm ≥ 3 (máximo 9, em
  barramentos de SE). Cada par vira uma linha; as contagens por CTMT são de chaves distintas.
- `PAC_INI` do CTMT e PAC compartilhado não ajudam (ver "PAC"); a única ligação entre CTMT é geométrica.

Na fixture: `CH003` (RJO001, religador telecomandado) toca `SEG007` de RJO002; `CH005` (RJO002, faca
manual) toca `SEG006` de RJO001; `CH007` (RJO002, disjuntor dentro de `SE001`) toca `SEG001` de RJO001
(`EM_SUB`); `CH006` (RJO001, NA a 22 m de RJO002) **não** é tie com 2 m — vira com 50 m.

### Unidades e códigos

- `ENE_01..ENE_12` em **kWh** (`CTMT`, `UC*_tab`, `UG*_tab`); o inventário converte para MWh/ano.
- `COMP` em metros; `POT_NOM` (UNTRMT) em kVA; `POT_INST` (UG*_tab) em kW.
- `TEN_NOM` é código do domínio *TEN* (`46` = 13,2 kV, `49` = 13,8 kV, `67` = 25 kV; tabela completa em
  `catalogo.TENSAO_KV`); `TIP_UNID` de UNSEMT em `catalogo.TIPOS_CHAVE_MT`; `MUN` = IBGE de 7 dígitos.
