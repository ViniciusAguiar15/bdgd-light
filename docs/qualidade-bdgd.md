# Qualidade do cadastro BDGD Light 2025

_Arquivo gerado por `uv run python scripts/qualidade_bdgd.py`._

## Fontes

- diretório analisado: `data/parquet`
- distribuidora: `382`
- data-base informada em `BASE`: `01/01/2025` a `31/12/2025`
- data de extração informada em `BASE`: `18/08/2026`
- descrição da base: EXTRACAO AUTOMATICA BDGD MODULO 10

## 1. `FAS_CON` por camada e por alimentador

- contagem: **5.466.508**
- universo: **11.807.122**
- percentual: **46,30%**

| camada | registros | FAS_CON informado | monofásicos | % mono | top 5 valores |
|---|---|---|---|---|---|
| RAMLIG | 3.818.151 | 3.818.151 | 1.860.994 | 48,74% | ABCN=1677734, AN=777650, BN=584297, CN=499047, ABN=219223 |
| SSDBT | 1.789.778 | 1.789.778 | 141.078 | 7,88% | ABCN=1568379, AN=110258, ABN=64686, BN=18358, CN=12462 |
| SSDMT | 1.000.817 | 1.000.817 | 27.993 | 2,80% | ABC=967223, AN=26781, CA=3192, AB=2364, A=928 |
| UCBT_tab | 5.041.346 | 5.041.346 | 3.412.881 | 67,70% | AN=1779557, ABCN=1284805, BN=947618, CN=685706, ABN=189052 |
| UCMT_tab | 7.660 | 7.660 | 21 | 0,27% | ABC=7638, A=13, AN=5, CN=2, ABCN=1 |
| UGBT_tab | 57.523 | 57.523 | 21.613 | 37,57% | ABCN=30177, AN=17074, ABN=4686, BN=2831, CN=1708 |
| UGMT_tab | 670 | 670 | 6 | 0,90% | ABC=664, AN=5, BN=1 |
| UNSEBT | 26.432 | 26.432 | 0 | 0,00% | ABCN=26428, ABN=4 |
| UNSEMT | 64.745 | 64.745 | 1.922 | 2,97% | ABC=62003, A=1741, CA=578, AB=239, AN=155 |

### Alimentadores com maior concentração monofásica

| camada | CTMT | registros | monofásicos | % mono |
|---|---|---|---|---|
| UCBT_tab | SCO33654 | 3.244 | 3.199 | 98,61% |
| UCBT_tab | CLG0002 | 2.762 | 2.720 | 98,48% |
| UCBT_tab | FCN1169 | 1.929 | 1.898 | 98,39% |
| UCBT_tab | SCO33618 | 3.803 | 3.732 | 98,13% |
| UCBT_tab | GDL0005 | 2.063 | 2.021 | 97,96% |

- exemplos: `SCO33654`, `CLG0002`, `FCN1169`, `SCO33618`, `GDL0005`

Impacto no pipeline: Concentração monofásica elevada pressiona o equilíbrio de fases e foi um dos gatilhos para estabilizações específicas no OpenDSS (ex.: vminpu=0.9 em circuitos BT).

## 2. `RAMLIG` acima de 300 m

- contagem: **2.069**
- universo: **3.818.151**
- percentual: **0,05%**

- percentil 99 de `COMP`: **81,83 m**
- exemplos: `588728623`, `314123833`, `262904851`, `415710762`, `312790613`

| COD_ID | CTMT | comprimento (m) |
|---|---|---|
| 588728623 | JAB00021 | 1000,00 |
| 314123833 | GNB29528 | 996,54 |
| 262904851 | REC00004 | 996,42 |
| 415710762 | HMT3022 | 995,41 |
| 312790613 | PDG29023 | 991,89 |

Impacto no pipeline: Ramais muito longos tendem a indicar circuito BT modelado como RAMLIG, o que distorce comprimento, perdas e o gêmeo elétrico BT.

## 3. `PN_CON` de UCBT/UCMT a mais de 2 km do transformador da UC

- contagem: **6.412**
- universo: **5.041.346**
- percentual: **0,13%**

- cobertura mensurável em `UCBT_tab`: **5.041.346** de **5.041.346** registros
- exemplos: `1a17a6fbb2bda8fdc239b897c89a3e6eca9809389743dd838851124eb6b9a4db`, `fd8c54545407e2007af49c7897bf984162d227009cf9093129109258c2660b0f`, `81e2bee92b68c80504755e9516f04ad8086c5b01ac4164bbc084a9ada515c367`, `52d290ef507111cbec8b1f787c6e7426dad325b43fae2fdcbd07beb80c6a9388`, `9011585459dda7255b60b8e04bb0ecf46a039aafb3c97003c3e1b88c96aba9c7`

| COD_ID | CTMT | distância (m) |
|---|---|---|
| 1a17a6fbb2bda8fdc239b897c89a3e6eca9809389743dd838851124eb6b9a4db | INF0004 | 183415,78 |
| fd8c54545407e2007af49c7897bf984162d227009cf9093129109258c2660b0f | INF0003 | 155912,42 |
| 81e2bee92b68c80504755e9516f04ad8086c5b01ac4164bbc084a9ada515c367 | INF0003 | 155702,61 |
| 52d290ef507111cbec8b1f787c6e7426dad325b43fae2fdcbd07beb80c6a9388 | INF0003 | 155682,83 |
| 9011585459dda7255b60b8e04bb0ecf46a039aafb3c97003c3e1b88c96aba9c7 | INF0003 | 155682,83 |

Limitações/adaptações:
- UCMT_tab não traz UNI_TR_MT nem outro vínculo direto com transformador de distribuição; a checagem de 2 km ficou restrita a UCBT_tab na Light 2025.

Impacto no pipeline: PN_CON distante infla bbox de recortes e tiles e já motivou filtro geográfico para evitar postes a dezenas de km do alimentador.

## 4. Trechos sem `TIP_CND` correspondente em `SEGCON`

- contagem: **0**
- universo: **6.608.746**
- percentual: **0,00%**

| camada | registros | problemas | vazios | sem catálogo | % problema |
|---|---|---|---|---|---|
| RAMLIG | 3.818.151 | 0 | 0 | 0 | 0,00% |
| SSDBT | 1.789.778 | 0 | 0 | 0 | 0,00% |
| SSDMT | 1.000.817 | 0 | 0 | 0 | 0,00% |

- exemplos: —
| COD_ID | camada | TIP_CND |
|---|---|---|
| — | — | — |

Impacto no pipeline: nenhum — não houve ocorrência nessa checagem.

## 5. `CTMT` referenciado por feições mas ausente da camada `CTMT` (e o inverso)

- contagem: **0**
- universo: **12.742.558**
- percentual: **0,00%**

| camada | referências | ausentes | % ausente |
|---|---|---|---|
| PIP | 835.142 | 0 | 0,00% |
| RAMLIG | 3.818.151 | 0 | 0,00% |
| SSDBT | 1.789.778 | 0 | 0,00% |
| SSDMT | 1.000.817 | 0 | 0,00% |
| UCBT_tab | 5.041.346 | 0 | 0,00% |
| UCMT_tab | 7.660 | 0 | 0,00% |
| UGBT_tab | 57.523 | 0 | 0,00% |
| UGMT_tab | 670 | 0 | 0,00% |
| UNCRMT | 778 | 0 | 0,00% |
| UNREMT | 26 | 0 | 0,00% |
| UNSEBT | 26.432 | 0 | 0,00% |
| UNSEMT | 64.745 | 0 | 0,00% |
| UNTRMT | 99.490 | 0 | 0,00% |

- `CTMT` presentes em `CTMT` mas sem nenhuma referência nas camadas verificadas: **0** de **1.802** (0,00%)
- exemplos de feições com `CTMT` ausente: —
- exemplos de `CTMT` sem referência: —
| COD_ID | camada | CTMT |
|---|---|---|
| — | — | — |

Impacto no pipeline: nenhum — não houve ocorrência nessa checagem.

## 6. PACs que aparecem em mais de um alimentador

- contagem: **0**
- universo: **1.161.877**
- percentual: **0,00%**

- exemplos: —
| COD_ID | camada | PAC | CTMTs |
|---|---|---|---|
| — | — | — | — |

Limitações/adaptações:
- A contagem cobre PACs de MT usados pelo pipeline elétrico (CTMT, SSDMT, UNSEMT, UNTRMT, UCMT_tab e UGMT_tab), não os PACs BT por transformador.

Impacto no pipeline: nenhum — não houve ocorrência nessa checagem.

## 7. Geometria inválida ou vazia, por camada

- contagem: **0**
- universo: **3.872.877**
- percentual: **0,00%**

| camada | registros | problemas | % problema |
|---|---|---|---|
| ARAT | 1 | 0 | 0,00% |
| CONJ | 109 | 0 | 0,00% |
| PONNOT | 882.200 | 0 | 0,00% |
| SSDAT | 7.952 | 0 | 0,00% |
| SSDBT | 1.789.778 | 0 | 0,00% |
| SSDMT | 1.000.817 | 0 | 0,00% |
| SUB | 238 | 0 | 0,00% |
| UNCRMT | 778 | 0 | 0,00% |
| UNREMT | 26 | 0 | 0,00% |
| UNSEBT | 26.432 | 0 | 0,00% |
| UNSEMT | 64.745 | 0 | 0,00% |
| UNTRAT | 311 | 0 | 0,00% |
| UNTRMT | 99.490 | 0 | 0,00% |

- exemplos: —
| COD_ID | camada |
|---|---|
| — | — |

Impacto no pipeline: nenhum — não houve ocorrência nessa checagem.

## 8. Coordenadas fora da bbox da área de concessão

- contagem: **164**
- universo: **3.872.877**
- percentual: **0,0042%**

- bbox de `ARAT`: `[-44,345468, -23,076314, -42,431343, -21,781877]`
| camada | registros mensuráveis | fora da bbox | % fora |
|---|---|---|---|
| ARAT | 1 | 0 | 0,00% |
| CONJ | 109 | 3 | 2,75% |
| PONNOT | 882.200 | 54 | 0,0061% |
| SSDAT | 7.952 | 106 | 1,33% |
| SSDBT | 1.789.778 | 0 | 0,00% |
| SSDMT | 1.000.817 | 0 | 0,00% |
| SUB | 238 | 1 | 0,42% |
| UNCRMT | 778 | 0 | 0,00% |
| UNREMT | 26 | 0 | 0,00% |
| UNSEBT | 26.432 | 0 | 0,00% |
| UNSEMT | 64.745 | 0 | 0,00% |
| UNTRAT | 311 | 0 | 0,00% |
| UNTRMT | 99.490 | 0 | 0,00% |

- exemplos: `15001`, `15091`, `16898`, `276830629`, `276830635`
| COD_ID | camada |
|---|---|
| 15001 | CONJ |
| 15091 | CONJ |
| 16898 | CONJ |
| 276830629 | PONNOT |
| 276830635 | PONNOT |

Impacto no pipeline: Coordenadas fora da bbox da concessão puxam mapa, bbox de recorte e verificações espaciais para fora do território esperado.

## 9. Chaves com `TLCD` nulo/indefinido

- contagem: **0**
- universo: **91.177**
- percentual: **0,00%**

| camada | registros | problemas | nulos | indefinidos | % problema |
|---|---|---|---|---|---|
| UNSEBT | 26.432 | 0 | 0 | 0 | 0,00% |
| UNSEMT | 64.745 | 0 | 0 | 0 | 0,00% |

- exemplos: —
| COD_ID | camada | TLCD |
|---|---|---|
| — | — | — |

Impacto no pipeline: nenhum — não houve ocorrência nessa checagem.

## Perguntas para a distribuidora

- A concentração massiva de `FAS_CON` monofásico em alguns alimentadores representa rede bifilar real ou convenção de cadastro usada como default?
- Os `RAMLIG` acima de 300 m são de fato ramais de ligação ou trechos de circuito BT classificados na camada errada?
- Qual é a regra oficial para o `PN_CON` de UCs BT quando o poste cadastrado fica a quilômetros do transformador? Há um campo mais confiável para o ponto de conexão físico?
- Para `UCMT_tab`, qual campo liga a UC ao equipamento/localização física que deve ser usado para validar a coerência do `PN_CON`?
