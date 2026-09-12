# GD na restauração

Relatório gerado por `scripts/gd_na_restauracao.py` para a issue #99.

## 1. Premissas

- Dia/mês dos Masters: **DU09**.
- Comparação pedida nesta issue: **meio-dia com GD plena** (`mode=daily`, `hour=12`, Master com `--gd`) versus **ponta da noite sem GD** (`hour=19`, Master base).
- **Ilhamento não entra como hipótese de restauração**: a GD **não** é contada como fonte durante a falta, porque o inversor desconecta na ausência de tensão da rede. Ela só pode alterar o carregamento do **socorredor** no instante da manobra.
- A comparação usa a própria ordenação do `restore_options(score=true)`: **viável → maior margem no disjuntor → clientes**.
- Nos alimentadores reais fora da demo, o recorte foi montado como **CTMT principal + vizinhos diretos do inventário**; a falta foi fixada no **maior trecho do tronco** do CTMT principal, reaproveitando a heurística da #91.

## 2. Casos rodados

- Cenários fixos da demo:
  - `tijuca_cabofrio_tronco` — ALC9925, falta `11304252` em `tijuca`
  - `ipanema_9210` — PTS0001, falta `11409068` em `ipanema`
  - `taquara_bocari` — TQR33862, falta `11798327` em `taquara`
- Alimentadores reais de alta penetração escolhidos a partir de `docs/dados/gd-gemeo-alocacao.csv`:
  - `SRD002` — segunda maior penetração da #97/#35; GD total considerada = **19860.200 kW**
  - `BRI001` — maior penetração da #97/#35; GD total considerada = **13809.282 kW**
  - `TRS003` — alta penetração convergente na #97; GD total considerada = **2146.005 kW**

## 3. Resumo por caso e instante

| grupo | caso | instante | opções | viáveis | vencedora | melhor viável | margem da vencedora | Vmin MT | Vmax MT | observação |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| alimentador | BRI001 | meio-dia com GD | 0 | 0 | — | — | — | — | — | sem opções de restauração |
| alimentador | BRI001 | ponta da noite sem GD | 0 | 0 | — | — | — | — | — | sem opções de restauração |
| alimentador | SRD002 | meio-dia com GD | 3 | 1 | 20729022 | 20729022 | 99.8% | 1.045 | 1.045 | — |
| alimentador | SRD002 | ponta da noite sem GD | 3 | 0 | 20729022 | — | 69.2% | 1.032 | 1.045 | fluxo não convergiu |
| alimentador | TRS003 | meio-dia com GD | 0 | 0 | — | — | — | — | — | sem opções de restauração |
| alimentador | TRS003 | ponta da noite sem GD | 0 | 0 | — | — | — | — | — | sem opções de restauração |
| cenario | ipanema_9210 | meio-dia com GD | 0 | 0 | — | — | — | — | — | sem opções de restauração |
| cenario | ipanema_9210 | ponta da noite sem GD | 0 | 0 | — | — | — | — | — | sem opções de restauração |
| cenario | taquara_bocari | meio-dia com GD | 10 | 0 | 1007642983 | — | — | — | — | fluxo não convergiu |
| cenario | taquara_bocari | ponta da noite sem GD | 10 | 10 | 11056672 | 11056672 | 77.9% | 1.017 | 1.045 | — |
| cenario | tijuca_cabofrio_tronco | meio-dia com GD | 10 | 7 | 974020904 | 974020904 | 78.7% | 1.037 | 1.045 | — |
| cenario | tijuca_cabofrio_tronco | ponta da noite sem GD | 10 | 7 | 974020904 | 974020904 | 73.7% | 1.036 | 1.045 | — |

## 4. Comparação entre meio-dia com GD e ponta da noite sem GD

| grupo | caso | vencedora meio-dia | vencedora noite | mudou vencedora | melhor viável meio-dia | melhor viável noite | mudou melhor viável |
| --- | --- | --- | --- | --- | --- | --- | --- |
| alimentador | BRI001 | — | — | não | — | — | não |
| alimentador | SRD002 | 20729022 | 20729022 | não | 20729022 | — | sim |
| alimentador | TRS003 | — | — | não | — | — | não |
| cenario | ipanema_9210 | — | — | não | — | — | não |
| cenario | taquara_bocari | 1007642983 | 11056672 | sim | — | 11056672 | sim |
| cenario | tijuca_cabofrio_tronco | 974020904 | 974020904 | não | 974020904 | 974020904 | não |

## 5. Tabelas detalhadas por caso

### `tijuca_cabofrio_tronco`

- Grupo: **cenario**.
- Origem: cenário tijuca.
- Cluster analisado: `tijuca` (ALC9925, RCP9882, ALC9946, URG29983).
- Falta: trecho `11304252` (cenário nomeado).

#### meio-dia com GD (12:00)

| ordem | chave | socorredor | viável | margem | Vmin MT | barra Vmin | Vmax MT | barra Vmax | carreg. máx. MT % | motivos |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 974020904 | ALC9946 | sim | 78.7% | 1.037 | alc9925_mt_876330 | 1.045 | alc9946_mt_50518 | 35.940 | — |
| 2 | 529355823 | ALC9946 | sim | 78.7% | 1.037 | alc9925_mt_876330 | 1.045 | alc9946_mt_50518 | 35.940 | — |
| 3 | 977361689 | URG29983 | sim | 77.1% | 1.032 | alc9925_mt_453329 | 1.045 | urg29983_mt_50724 | 70.565 | — |
| 4 | 11006808 | URG29983 | sim | 77.1% | 1.033 | alc9925_mt_453329 | 1.045 | urg29983_mt_50724 | 70.580 | — |
| 5 | 11006815 | URG29983 | sim | 77.1% | 1.032 | alc9925_mt_453329 | 1.045 | urg29983_mt_50724 | 70.565 | — |
| 6 | 746851189 | RCP9882 | sim | 67.0% | 1.034 | alc9925_mt_453329 | 1.045 | rcp9882_mt_50508 | 33.190 | — |
| 7 | 23313112 | RCP9882 | sim | 67.0% | 1.034 | alc9925_mt_876330 | 1.045 | rcp9882_mt_50508 | 33.188 | — |
| 8 | 1009901594 | URG29706 | não | — | — | — | — | — | — | fonte URG29706 fora do cluster (sem modelo) |
| 9 | 11035887 | URG29706 | não | — | — | — | — | — | — | fonte URG29706 fora do cluster (sem modelo) |
| 10 | 494303815 | ALC740 | não | — | — | — | — | — | — | fonte ALC740 fora do cluster (sem modelo) |

#### ponta da noite sem GD (19:00)

| ordem | chave | socorredor | viável | margem | Vmin MT | barra Vmin | Vmax MT | barra Vmax | carreg. máx. MT % | motivos |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 974020904 | ALC9946 | sim | 73.7% | 1.036 | alc9925_mt_876330 | 1.045 | alc9946_mt_50518 | 41.966 | — |
| 2 | 529355823 | ALC9946 | sim | 73.7% | 1.036 | alc9925_mt_876330 | 1.045 | alc9946_mt_50518 | 41.966 | — |
| 3 | 977361689 | URG29983 | sim | 71.2% | 1.030 | alc9925_mt_453329 | 1.045 | urg29983_mt_50724 | 88.550 | — |
| 4 | 11006808 | URG29983 | sim | 71.2% | 1.031 | alc9925_mt_453329 | 1.045 | urg29983_mt_50724 | 88.559 | — |
| 5 | 11006815 | URG29983 | sim | 71.2% | 1.030 | alc9925_mt_453329 | 1.045 | urg29983_mt_50724 | 88.550 | — |
| 6 | 746851189 | RCP9882 | sim | 58.8% | 1.032 | alc9925_mt_453329 | 1.045 | rcp9882_mt_50508 | 41.405 | — |
| 7 | 23313112 | RCP9882 | sim | 58.8% | 1.032 | alc9925_mt_876330 | 1.045 | rcp9882_mt_50508 | 41.402 | — |
| 8 | 1009901594 | URG29706 | não | — | — | — | — | — | — | fonte URG29706 fora do cluster (sem modelo) |
| 9 | 11035887 | URG29706 | não | — | — | — | — | — | — | fonte URG29706 fora do cluster (sem modelo) |
| 10 | 494303815 | ALC740 | não | — | — | — | — | — | — | fonte ALC740 fora do cluster (sem modelo) |

### `ipanema_9210`

- Grupo: **cenario**.
- Origem: cenário ipanema.
- Cluster analisado: `ipanema` (PTS4022, PTS9088, PTS9924, PTS0001).
- Falta: trecho `11409068` (cenário nomeado).

#### meio-dia com GD (12:00)

Sem opções de restauração neste caso.

#### ponta da noite sem GD (19:00)

Sem opções de restauração neste caso.

### `taquara_bocari`

- Grupo: **cenario**.
- Origem: cenário taquara.
- Cluster analisado: `taquara` (TQR0007, TQR33859, TQR33862).
- Falta: trecho `11798327` (cenário nomeado).

#### meio-dia com GD (12:00)

| ordem | chave | socorredor | viável | margem | Vmin MT | barra Vmin | Vmax MT | barra Vmax | carreg. máx. MT % | motivos |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1007642983 | TQR0007 | não | — | — | — | — | — | — | fluxo não convergiu |
| 2 | 752622332 | TQR0007 | não | — | — | — | — | — | — | fluxo não convergiu |
| 3 | 789941518 | TQR33859 | não | — | — | — | — | — | — | fluxo não convergiu |
| 4 | 11026494 | TQR0007 | não | — | — | — | — | — | — | fluxo não convergiu |
| 5 | 11053522 | TQR33859 | não | — | — | — | — | — | — | fluxo não convergiu |
| 6 | 11053620 | TQR33859 | não | — | — | — | — | — | — | fluxo não convergiu |
| 7 | 11053627 | TQR33859 | não | — | — | — | — | — | — | fluxo não convergiu |
| 8 | 11056672 | TQR33859 | não | — | — | — | — | — | — | fluxo não convergiu |
| 9 | 134733185 | TQR0007 | não | — | — | — | — | — | — | fluxo não convergiu |
| 10 | 258481641 | TQR0007 | não | — | — | — | — | — | — | fluxo não convergiu |

#### ponta da noite sem GD (19:00)

| ordem | chave | socorredor | viável | margem | Vmin MT | barra Vmin | Vmax MT | barra Vmax | carreg. máx. MT % | motivos |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 11056672 | TQR33859 | sim | 77.9% | 1.017 | tqr33862_mt_360100 | 1.045 | tqr33859_mt_50380 | 27.174 | — |
| 2 | 789941518 | TQR33859 | sim | 77.8% | 1.027 | tqr33859_mt_395491 | 1.045 | tqr33859_mt_50380 | 22.183 | — |
| 3 | 11053522 | TQR33859 | sim | 77.8% | 1.025 | tqr33859_mt_395491 | 1.045 | tqr33859_mt_50380 | 22.174 | — |
| 4 | 11053620 | TQR33859 | sim | 77.8% | 1.023 | tqr33859_mt_395491 | 1.045 | tqr33859_mt_50380 | 22.159 | — |
| 5 | 11053627 | TQR33859 | sim | 77.8% | 1.027 | tqr33859_mt_395491 | 1.045 | tqr33859_mt_50380 | 22.183 | — |
| 6 | 1007642983 | TQR0007 | sim | 75.3% | 1.017 | tqr0007_mt_360037 | 1.045 | tqr0007_mt_52737 | 47.772 | — |
| 7 | 752622332 | TQR0007 | sim | 75.3% | 1.016 | tqr0007_mt_360037 | 1.045 | tqr0007_mt_52737 | 47.743 | — |
| 8 | 11026494 | TQR0007 | sim | 75.3% | 1.017 | tqr0007_mt_360037 | 1.045 | tqr0007_mt_52737 | 47.772 | — |
| 9 | 134733185 | TQR0007 | sim | 75.3% | 1.016 | tqr0007_mt_360037 | 1.045 | tqr0007_mt_52737 | 47.743 | — |
| 10 | 258481641 | TQR0007 | sim | 75.3% | 1.016 | tqr0007_mt_360037 | 1.045 | tqr0007_mt_52737 | 47.751 | — |

### `SRD002`

- Grupo: **alimentador**.
- Origem: segunda maior penetração da #97/#35.
- Cluster analisado: `cluster_SRD002-BRI00005-BRI001-ESP018-ESP020-SRD0005-SRD003` (BRI00005, ESP020, SRD0005, SRD002, SRD003, BRI001, ESP018).
- Falta: trecho `363664978` (maior trecho do tronco do CTMT principal).

#### meio-dia com GD (12:00)

| ordem | chave | socorredor | viável | margem | Vmin MT | barra Vmin | Vmax MT | barra Vmax | carreg. máx. MT % | motivos |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 20729022 | SRD003 | sim | 99.8% | 1.045 | srd002_mt_525788 | 1.045 | srd002_mt_466772 | 0.465 | — |
| 2 | 915570991 | SRD0005 | não | 99.5% | 0.000 | srd0005_mt_362252_tr | 1.046 | srd0005_mt_94934 | 0.515 | Vmin MT 0,000 pu < 0,93 |
| 3 | 977979996 | BRI001 | não | 99.5% | 0.000 | bri001_mt_389223_tr | 1.046 | bri001_mt_617176 | 0.662 | Vmin MT 0,000 pu < 0,93 |

#### ponta da noite sem GD (19:00)

| ordem | chave | socorredor | viável | margem | Vmin MT | barra Vmin | Vmax MT | barra Vmax | carreg. máx. MT % | motivos |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 20729022 | SRD003 | não | 69.2% | 1.032 | srd002_mt_1348606 | 1.045 | srd003_mt_51567 | 39.088 | fluxo não convergiu |
| 2 | 977979996 | BRI001 | não | 52.7% | 0.000 | bri001_mt_389223_tr | 1.045 | bri001_mt_51575 | 59.431 | fluxo não convergiu; Vmin MT 0,000 pu < 0,93 |
| 3 | 915570991 | SRD0005 | não | — | — | srd0005_mt_52770 | — | srd0005_mt_52770 | — | fluxo não convergiu; Vmax MT inf pu > 1,05; 7492 trecho(s) MT acima de 100 % (Line.smt_25440125 inf %, Line.smt_260474046 inf %, Line.smt_20942364 inf %); I disjuntor inf A > 663 A nominal |

### `BRI001`

- Grupo: **alimentador**.
- Origem: maior penetração da #97/#35.
- Cluster analisado: `cluster_BRI001-BRI00005-BRI002-BRI003-ESP019-ITG0007-ITG0010-SRD0005-SRD002` (BRI00005, BRI002, BRI003, ESP019, ITG0007, ITG0010, SRD0005, SRD002, BRI001).
- Falta: trecho `27774260` (maior trecho do tronco do CTMT principal).

#### meio-dia com GD (12:00)

Sem opções de restauração neste caso.

#### ponta da noite sem GD (19:00)

Sem opções de restauração neste caso.

### `TRS003`

- Grupo: **alimentador**.
- Origem: alta penetração convergente na #97.
- Cluster analisado: `cluster_TRS003-TRS004-TRS005-TRS008-TRS013` (TRS005, TRS003, TRS004, TRS013, TRS008).
- Falta: trecho `491040446` (maior trecho do tronco do CTMT principal).

#### meio-dia com GD (12:00)

Sem opções de restauração neste caso.

#### ponta da noite sem GD (19:00)

Sem opções de restauração neste caso.

## 6. Conclusão

- **Resultado desta base:** a GD **mudou a opção vencedora** em `taquara_bocari`.
- Houve mudança na **melhor opção viável** em `SRD002`, `taquara_bocari`.
- Casos sem alternativa topológica de restauração neste recorte: `BRI001`, `TRS003`, `ipanema_9210`.
- Na base atual, a troca de vencedora apareceu em `taquara_bocari`, mas com uma **limitação relevante**: o meio-dia com GD não convergiu para nenhuma das 10 opções, enquanto a ponta da noite sem GD convergiu com 10 opções viáveis.
- Em `SRD002`, a chave vencedora permaneceu `20729022`, mas a viabilidade mudou: ao meio-dia com GD ela ficou viável; na ponta da noite sem GD, nenhuma das 3 opções convergiu como viável.
- A formulação operacional correta permanece: **a GD não restaura durante a falta**, mas pode reduzir a carga absorvida pelo socorredor no instante da transferência e, por consequência, alterar a margem do disjuntor, a tensão MT e a viabilidade do socorro.
- Se algum caso mudou de vencedora, a recomendação é tratar o **horário do evento** como premissa explícita do score em issue separada, sem alterar o comportamento nesta #99.

## 7. Artefatos versionados

- Detalhe por opção: `docs/dados/gd-restauracao-opcoes.csv`.
- Resumo por caso/instante: `docs/dados/gd-restauracao-resumo.csv`.

## 8. Reprodução

```bash
uv run python scripts/gd_na_restauracao.py \
  --parquet-dir data/parquet \
  --mmgd data/gd/empreendimento-geracao-distribuida.parquet \
  --out docs/gd-restauracao.md
```
