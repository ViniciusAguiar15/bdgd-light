# Diário do modo noturno — 2026-09-09

Trabalho autônomo sobre a fila combinada (merges pendentes → ajustes da PR-02 → #6 → #5 → #8 → #7 →
#4). Regras: uma branch e um PR por issue, Conventional Commits, `uv run ruff check . && uv run ruff
format . && uv run pytest` verdes antes de cada push, CI verde → `gh pr merge --squash
--delete-branch`, nada de `data/` no git, nunca force-push, nunca direto em `main`. Horários em BRT.

## 0. Merges pendentes (21:00–21:05)

| | |
|---|---|
| PRs | #9 (`feat/export-camadas`) → `main` `315351d`; #11 (`feat/inventario-recorte`) → `main` `00576bb` |
| Issues fechadas | #1, #2, #3 |

Decisões:

- O PR #10 (`feat/inventario-recorte` → `feat/export-camadas`) estava empilhado sobre o #9. Ao fazer
  squash-merge do #9 e apagar a branch, o GitHub **fechou o #10** sem retargetar (PR fechado não
  aceita mudança de base nem reabertura). Abri o **#11** com o mesmo corpo, base `main`, e deixei um
  comentário no #10 apontando para ele.
- O squash reescreveu a história, então `main` × `feat/inventario-recorte` tinha 9 conflitos add/add.
  Resolvi com `git merge --no-ff origin/main` mantendo a árvore da branch (ela já continha todo o #9:
  `git diff 315351d <branch>` vazio nos arquivos em conflito; árvore final igual a `ed29763`, o último
  commit do mantenedor). Commit de merge `390ebb5`, sem force-push.

Pendente: nada.

## 1. Ajustes da revisão PR-02 (21:05–21:30)

| | |
|---|---|
| Branch | `fix/ajustes-pr-02` |
| PR | #12 — CI verde, squash-merge → `main` `2196a77` |
| Origem | `docs/review/PR-02.md`, seção "Ajustes pedidos" |

O que foi feito:

1. **Score sem ties de SE.** `contar_por_ctmt` ganhou `NA_interligacao_campo` e
   `NA_interligacao_campo_telecomandada` (chaves distintas com `EM_SUB = False`); o inventário passou
   a ter 36 colunas e `score = NA_interligacao_campo × (n_UCBT + n_UCMT)`. A tabela `--top` mostra
   "Tie campo", "Tie TLCD" (campo telecomandadas) e "Tie SE". Ordenação: score, `NA_interligacao_campo`,
   `n_UCBT`.
2. **`bdgd-light vizinhos --sem-se`** (padrão; `--com-se` restaura o comportamento anterior). Com
   `--sem-se`, chaves dentro do polígono `SUB` saem de todas as contagens e da lista de `COD_ID`; a
   coluna "Na SE" mostra quantas foram descontadas e um vizinho ligado só pela SE continua listado com
   0 ties (para não "sumir" com a relação). Título: "N CTMT, K chaves NA de interligação de campo (T
   telecomandadas), P pares chave×vizinho; S chaves na SE descontadas".
3. **`meta.json` do recorte**: cada par em `interligacoes` traz também `ties_campo`,
   `ties_campo_telecomandadas` e `chaves_campo`.
4. **13,2 kV**: nenhum texto diz "13,8 kV" para `TEN_NOM = 46`; a única menção a 13,8 fora do domínio
   (`docs/bdgd-light-2025.md`) é o registro de que a hipótese foi descartada — reescrita para deixar
   explícito que o projeto adota `46 → 13,2 kV`.
5. README (tabela de colunas, `vizinhos`, `recortar`, `meta.json`, exemplos com o cluster TQR) e
   `docs/bdgd-relacoes.md` (contagens, motivo da troca PDG → TQR) atualizados.

Decisões:

- Preferi **adicionar colunas** a trocar a semântica de `NA_interligacao`: a detecção continua
  puramente geométrica (regra do backlog) e o filtro "campo" é uma visão sobre ela. Quem quiser o
  número antigo continua tendo.
- `--sem-se` é o padrão do `vizinhos` porque o comando existe para escolher com quem restaurar carga;
  disjuntores da SE nunca são opção.

Validação com dados reais (Light 2025):

```bash
uv run bdgd-light inventario --parquet data/parquet --out data/inventario_ctmt.csv --top 15
uv run bdgd-light vizinhos --ctmt TQR0007 --parquet data/parquet          # e --com-se
uv run bdgd-light recortar --parquet data/parquet --ctmt TQR0007,TQR33859,TQR33862 --out data/feeders
uv run bdgd-light recortar --parquet data/parquet --ctmt BMT0001,BMT29737,CBI33798 --out data/feeders
python -c "import json;[print(i) for i in json.load(open('data/feeders/cluster_TQR0007-TQR33859-TQR33862.meta.json'))['interligacoes']]"
```

Resultados:

- Inventário: 1.802 CTMT, 36 colunas, 4,7 s. Top do score agora é dominado por `LSA` de 25 kV com
  20–25 mil UCBT (BARBARIO, EUFRASIA, CAMBARA…). Cluster TQR: CURUMAU rank 86 (18 ties de campo, 3
  TLCD, score 106.020), BOCARI 114 (22 / 3), PARNAIBA 156 (13 / 3) — **nenhuma tie na SE**. Cluster
  BMT/CBI: AVEMAR 301, DEPAIVA 479, RABELO 539.
- `vizinhos --ctmt TQR0007`: BOCARI 8 ties (2 telecomandadas), TQR33830 3 (0), CURUMAU 2 (1); 0 na SE
  — bate com o escopo v2.
- Recorte TQR: PARNAIBA 14.146 feições, CURUMAU 14.608, BOCARI 10.853, cluster 39.185 (23 camadas, 7,5 s
  no total). Pares do cluster no `meta.json`: PARNAIBA–BOCARI `ties_campo 8 / TLCD 2`, CURUMAU–BOCARI
  `7 / 1`, PARNAIBA–CURUMAU `2 / 1` — todos com ≥ 1 telecomandada de campo.
- Recorte BMT/CBI: DEPAIVA 6.549, AVEMAR 7.809, RABELO 7.981, cluster 22.039 (2 SUB, 6 UNTRAT). Pares:
  DEPAIVA–AVEMAR `6 / 1` (mais 1 na SE), AVEMAR–RABELO `3 / 1`, DEPAIVA–RABELO `1 / 1`.
- Os seis CTMT têm `TEN_NOM = 46` (13,2 kV).

Pendente: nada. `data/feeders/` agora contém os três clusters (PDG, TQR, BMT/CBI); é ignorado pelo git.

## 2. Issue #6 — grafo do alimentador (21:30–21:50)

| | |
|---|---|
| Branch | `feat/grafo-alimentador` (de `main` `2196a77`) |
| PR | #13 → `main` `34eab7a` (squash, CI verde em 3.11/3.12) |
| Origem | `docs/backlog/06-grafo-alimentador.md` + "Próximo passo" de `docs/review/PR-02.md` |

O que foi feito:

1. **Fixture.** `gerar_fixture.py` ganhou o barramento `PAC_INI` real: `RJO001_MT_0`/`RJO002_MT_0` com
   disjuntores NF `CH008`/`CH009` (TIP 29, TLCD) saindo deles; `CH006` virou um anel interno de
   verdade (`MT_5`—`MT_6`; antes repetia o par de PAC de `SEG006`). `RJO003` ficou sem disjuntor de
   propósito, para testar o fallback da fonte. Contagens ajustadas nos testes existentes.
2. **`bdgd_light.grid`** (`rede.py`, `geojson.py`): `Rede` / `Feeder` (1 CTMT) / `Cluster` (n CTMT,
   `from_gpkg` ou `from_gpkgs`), `Camadas`, `ler_camadas`, `Clientes`, `Isolamento`,
   `OpcaoRestauracao`, `estado_geojson`. Métodos pedidos: `energized_nodes`, `energized_by`,
   `downstream`, `customers_downstream`, `open_switch`/`close_switch`/`reset_switches`,
   `tie_switches`, `isolate_segment`, `restore_options`, `copy`, `resumo`.
3. **CLI** `bdgd-light grafo --gpkg … [--falha SEG] [--abrir] [--fechar] [--geojson] [--ties-na-se]`.
4. **Docs**: `docs/grid-modelo.md` (mapeamento, medições na Light, decisões, limitações), README
   (seção do comando + estrutura), `docs/bdgd-relacoes.md` (nota do `PAC_INI` corrigida: ele **é** o
   `PAC_1` do disjuntor).
5. **Testes**: `tests/test_grid.py` — 18 testes (topologia, ties com/sem SE, clientes, fallback de
   fonte, energização e manobras, downstream em anel, isolamento com e sem desligados, restauração
   pela tie própria e pela chave do vizinho, cluster com PAC reais e `clientes_fonte`, GeoJSON, CLI,
   fumaça com `data/feeders/TQR0007.gpkg` marcado `skipif`). Suite: 81 verdes.

Decisões (detalhe em `docs/grid-modelo.md`):

- **Nó-fonte = `CTMT.PAC_INI`.** Medi na Light: `PAC_INI` é o `PAC_1` de uma `UNSEMT` em 1.802/1.802
  CTMT e nunca um PAC de SSDMT — é o barramento da SE, e a chave que sai dele é o disjuntor
  (`TIP_UNID 29`). Então o disjuntor entra no grafo e o `PAC_INI` é a fonte; se não estiver no grafo,
  fallback para o PAC de SSDMT do CTMT mais próximo do polígono da `SUB`, com aviso.
- **Só rede MT.** O backlog original citava SSDBT/UNSEBT; o "Próximo passo" da PR-02 restringiu a MT
  (`UNTRMT.PAC_1`). Clientes (`UCBT_tab` via `UNI_TR_MT`, `UCMT_tab` via `PAC`) ficam no nó MT do
  transformador. BT é radial por trafo e não muda manobra MT; entra no OpenDSS como carga agregada.
- **Ties**: aresta `tie` (impedância zero, sempre passável) da **ponta de fora** da chave (PAC que não
  está na rede do CTMT dono; ambíguo → `PAC_2`, pois `PAC_1` é o lado fonte) até o `PAC_VIZ` real se o
  vizinho está carregado (`Cluster`), senão até um nó externo `EXT:<CTMT>` tratado como fonte sempre
  energizada. Chaves NA do vizinho que encostam na nossa rede entram como aresta `chave` `externa`.
  Assim `restore_options` funciona no `Feeder` sozinho (sem saber a carga do vizinho — CLI mostra `?`)
  e no `Cluster` com transferência real (`clientes_fonte` diz quanto a fonte já atende).
- **Ties dentro da SE ignoradas por padrão** (`ties_na_se=False`), mesma regra do inventário/vizinhos.
- `isolate_segment`: zona = fecho do trecho por arestas que não são chave; abre as chaves fechadas da
  fronteira (mínimas, a primeira em cada direção). `restore_options`: chaves abertas com uma ponta nos
  desligados e a outra energizada, agrupadas por componente; ordem clientes ↓, TLCD ↓, código.
- Chave externa que toca vários PAC nossos: fica com o mais próximo (`DIST_M`), com aviso.
- GeoJSON: coordenadas em listas (não tuplas) para o dicionário em memória ser igual ao gravado.

Validação com dados reais (Light 2025):

```bash
uv run bdgd-light grafo --gpkg data/feeders/TQR0007.gpkg --falha 310743928 --geojson /tmp/tqr0007.geojson
uv run bdgd-light grafo --gpkg data/feeders/cluster_TQR0007-TQR33859-TQR33862.gpkg --falha 11798327 \
    --geojson /tmp/cluster_tqr.geojson
uv run pytest tests/test_grid.py -q     # inclui a fumaça em data/feeders/TQR0007.gpkg
```

Resultados:

- **TQR0007**: 719 nós, 675 trechos (16,474 km), 50 chaves (40 NF, 10 NA), 13 ties (10 de chaves de
  TQR33830/TQR33859/TQR33862), 82 trafos, 6.268 UCBT + 4 UCMT, **719/719 energizados**, 0 avisos, 0,13 s.
  Fonte `TQR0007_MT_52737` = `PAC_1` do disjuntor `358368825`. Falta no trecho do disjuntor
  (`310743928`): abrir `310744064` + `358368825`, 677 nós / 6.268 UCBT desligados, 13 opções
  (TLCD primeiro: `1007642983` e `625884927` externas, `752622332` própria).
- **Cluster TQR**: 2.069 nós, 1.924 trechos (46,65 km), 162 chaves, 35 ties (12 externas, 7 CTMT
  externos), 263 trafos, 16.504 UCBT, 2.068/2.069 energizados (1 PAC solto de chave), 0,11 s. Cada
  CTMT alimentado só pela própria fonte no estado normal (723 / 731 / 608 nós). Falta no tronco de
  BOCARI (`11798327`): abrir 4 chaves, zona 43 nós / 516 UCBT, 295 nós / 2.023 UCBT desligados, 10
  opções restauram 287 nós / 1.984 UCBT via PARNAIBA (já com 6.272 UC; 2 TLCD) ou CURUMAU (5.889 UC;
  1 TLCD) — o cenário FLISR do escopo v2. 8 nós / 39 UCBT sem NA para nenhuma fonte.
- GeoJSON do cluster: 2.361 feições (1.924 SSDMT, 174 UNSEMT, 263 UNTRMT), 314 trechos desenergizados
  após a manobra.

Pendente: nada para a issue. Fica anotado para o #5: o gêmeo OpenDSS deve ler o estado das chaves
deste grafo (`aberta`) em vez de `P_N_OPE` direto.

## 3. Issue #5 — spike bdgd2opendss + OpenDSSDirect (21:50–22:36)

| | |
|---|---|
| Branch | `feat/twin-opendss` (de `main` `34eab7a`) |
| PR | ver seção "PRs abertos/mergeados" no fim |
| Origem | `docs/backlog/05-spike-opendss.md` + item 3 do "Próximo passo" de `docs/review/PR-02.md` + observação sobre o #5 em `docs/review/PR-03.md` |

**`docs/review/PR-03.md` apareceu às 22:01** (revisão do #13, aprovado): os três ajustes pedidos
(`to_dict()` serializável em `Isolamento`/`OpcaoRestauracao`/`Rede.resumo()`; sequência explícita
`manobras` em cada `OpcaoRestauracao`; nota em `grid-modelo.md` de que o grafo não checa capacidade)
foram aplicados **num commit próprio nesta branch** (`9872e86 fix(grid): ajustes da revisão PR-03`),
com teste `test_to_dict_serializavel_e_sequencia_de_manobras`; o CLI `grafo` passou a ler
`Clientes.from_dict`. A observação sobre o #5 (registrar o fluxo **depois** da manobra FLISR) foi
atendida abaixo; a sugestão de gerar o Master a partir do GPKG do recorte ficou documentada como
decisão 9 de `docs/spike-opendss.md` (o bdgd2opendss só lê o `.gdb` inteiro).

O que foi feito:

1. **Instalação**: `uv sync --extra dev --extra twin` (extras já declarados no `pyproject.toml`; lock
   inalterado) → bdgd2opendss 1.2.5, opendssdirect-py 0.9.4, dss-python 0.15.7. CI passa a instalar
   `--extra twin` para rodar os testes do IEEE 13.
2. **bdgd2opendss em TQR0007**: `bdgd2opendss.run(gdb, out, all_feeders=False, lst_feeders=["TQR0007"])`
   converteu em **179,9 s** sem nenhum ajuste na BDGD → `data/dss/sub__10385871/TQR0007/` (122
   arquivos, 116 MB, 36 Masters DU/SA/DO × mês). Como funcionou, **não** escrevi o conversor mínimo
   próprio previsto como plano B.
3. **`bdgd_light.twin`**: `convert.py` (`converter` idempotente, `localizar_pasta`, `listar_masters`,
   `escolher_master(dia, mes)`) e `powerflow.py` (`run_powerflow(master, vmin, vmax, modo,
   estabilizar, comandos_extra) -> PowerFlowResult` com `tensoes`, `correntes`, `violacoes`,
   `sobrecargas`, `piores_barras`, `resumo()`; cascata `ESTABILIZADORES` registrada em `ajustes`).
4. **CLI** `bdgd-light dss --gdb … --ctmt … [--out data/dss] [--dia DU --mes 1] [--master X.dss]
   [--sem-fluxo] [--vmin/--vmax] [--sem-estabilizar] [--comando …] [--json] [--top]`; código de saída 2
   se não convergir.
5. **Fixture IEEE 13 barras** (`tests/fixtures/dss/ieee13/`, escrita a partir dos dados públicos do
   IEEE Test Feeder) e `tests/test_twin.py` — 19 testes (convergência, tensões/perdas de referência,
   violações, sobrecargas, cwd restaurado, `comandos_extra`, cascata de estabilizadores, erro claro de
   comando inválido, `escolher_master`/`localizar_pasta`/`converter`, CLI com `--master`, `--json`,
   não convergência → exit 2, `--sem-fluxo` reaproveitando conversão, fumaça em `data/dss` com
   `skipif`). O módulo inteiro é pulado (`importorskip`) sem o extra `twin`. Suite: 100 verdes.
6. **Docs**: `docs/spike-opendss.md`, README (estrutura + seção do comando), `docs/grid-modelo.md`
   (referências ao #5 atualizadas).
7. **Cluster TQR no gêmeo** (`twin/cluster.py`): converti TQR33859 e TQR33862 de uma vez
   (`lst_feeders`, 310,4 s) para `data/dss/sub__10385871/`; `montar_master_cluster(pastas, out,
   comandos)` escreve um Master único (Circuit no 1º CTMT + `Vsource.<CTMT>` nos demais + Redirects
   de todos) e `comandos_manobras(rede, manobras)` traduz a sequência do grafo em DSS (`open
   line.cmt_X`; NA → `New Line.CMT_X` + jumper `Line.TIE_X_n` até o `PAC_VIZ`). CLI `dss` ganhou
   `--ctmt A,B,C` (cluster), `--gpkg`, `--falha`, `--restaurar`, `--abrir`, `--fechar`, linha "Por
   fonte" e tabela "Tensão MT por alimentador"; `PowerFlowResult` ganhou `fontes` e `tensoes_mt()`.
8. **Fixture `tests/fixtures/dss/cluster_mini/`** gerada por `gerar_cluster_mini.py`: RJO001+RJO002
   no layout do bdgd2opendss com os mesmos PAC do grafo sintético, o que permite testar a manobra
   FLISR ponta a ponta (grafo → DSS → fluxo) sem dados reais. +4 testes (23 no módulo; suite 104).

Decisões:

- **Snapshot de pico** (`set mode=snapshot` antes do `Solve`) em vez do `mode=daily` do Master; o
  `kw` das cargas já é o pico da CRVCRG. Outros patamares via `--comando "set loadmult=…"`.
- **O modelo bruto não converge** (nem em 100 iterações): barras BT < 0,5 pu fazem as cargas
  `model=3` oscilar com `vminpu=0.5`. Em vez de mascarar, `run_powerflow` aplica em cascata e
  **registra** `maxiterations=100` → `batchedit load..* vminpu=0.9` → `model=2`. TQR0007 converge no
  2º degrau em 5 iterações / 0,5 s.
- **Causa raiz das tensões baixas é dado da BDGD**: `RAMLIG.COMP` de 943 / 783 / 727 / 714 m para
  ramais de 220 V com 34–65 UCBT (mediana dos ramais: 17 m; 142 > 100 m em TQR0007). `RAMLIG` não tem
  geometria na Light, então não há como conferir pelo traçado. Documentado; não "corrigi" o dado.
- Nós de neutro (`.4`, aterrados por reator) ficam a 0 pu e não contam como violação; só condutores
  1–3 entram em `fases`/`violacoes`.
- Chaves NA saem **comentadas** do bdgd2opendss e cada CTMT é um circuito próprio → resolvido com o
  Master do cluster (`Vsource` por CTMT) e `comandos_manobras` (decisão 7 do spike).
- **`GD_BT` fora do Master do cluster por padrão** (`gd=False`): o próprio bdgd2opendss não o inclui
  no Master, e com ele TQR33859/TQR33862 divergem (NaN). E a Light tem GD com `COD_ID` em branco
  (`New "generator. "`) em mais de um CTMT → "duplicate definition" (#266) vira exceção no
  dss-python; `Set AllowDuplicates=yes` logo após a `Circuit` resolve (também cobre
  linecodes/loadshapes idênticos repetidos entre CTMT).
- `CargasMT_*` é opcional no cluster (TQR33862/BOCARI não tem UCMT e o bdgd2opendss não gera o
  arquivo); `CargasBT_*` do dia/mês pedido é obrigatório.
- Reorganizei a saída para `data/dss/sub__10385871/TQR0007/` (padrão `--out data/dss`) — tudo em
  `data/`, fora do git.

Validação com dados reais:

```bash
uv sync --extra dev --extra twin
uv run bdgd-light dss --gdb data/Light_382_2025-12-31_V11_20260824-0926.gdb --ctmt TQR0007 \
    --out data/dss --json data/dss/TQR0007_fluxo_DU01.json          # ≈3 min na 1ª vez
uv run bdgd-light dss --master "data/dss/sub__10385871/TQR0007/Master_DU01_202608382_TQR0007_------1-----.dss" \
    --sem-estabilizar                                                 # mostra a não convergência bruta (exit 2)
uv run pytest tests/test_twin.py -q
```

```bash
# FLISR no gêmeo (cluster TQR já convertido; ≈1,2 s cada): base, falta isolada, via PARNAIBA, via CURUMAU
G=data/feeders/cluster_TQR0007-TQR33859-TQR33862.gpkg
uv run bdgd-light dss --ctmt TQR0007,TQR33859,TQR33862 --out data/dss --gpkg $G
uv run bdgd-light dss --ctmt TQR0007,TQR33859,TQR33862 --out data/dss --gpkg $G --falha 11798327
uv run bdgd-light dss --ctmt TQR0007,TQR33859,TQR33862 --out data/dss --gpkg $G --falha 11798327 --restaurar 1007642983
uv run bdgd-light dss --ctmt TQR0007,TQR33859,TQR33862 --out data/dss --gpkg $G --falha 11798327 --restaurar 789941518
```

Resultados (TQR0007, DU01): converge em 5 iterações (0,53 s) com `vminpu=0.9`; 6.334 barras, 20.313
nós, 6.251 linhas, 82 trafos, 12.312 cargas; 3.077 kW / 1.395 kvar na fonte; perdas 264 kW (8,6 %);
**MT 1,016–1,045 pu** (2.148 nós); BT: 988 nós < 0,93 pu (pior 0,369 pu em `567952367_2`, ponta do
ramal de 943 m), 0 sobretensão; 17 sobrecargas (ramais/segmentos BT até 250 %, trafos `11071479a`
148 % e `34450955a` 125 %). IEEE 13: 4 iterações, 0,961–1,056 pu, 112,4 kW de perdas.

Resultados do FLISR no cluster (tabela completa em `docs/spike-opendss.md`): base 9.470 kW (PARNAIBA
3.077 / CURUMAU 3.369 / BOCARI 3.024; disjuntores 149 / 190 / 144 A), 9 iterações; falta isolada →
BOCARI cai a 1.258 kW e 60 A, 9.092 nós de fase a 0 pu; **via PARNAIBA** (tie TLCD `1007642983`) →
PARNAIBA 4.603 kW / 221 A, MT transferida ≥ 1,004 pu, tronco a 76 %, 0 sobrecargas MT; **via
CURUMAU** (tie TLCD `789941518`) → CURUMAU 4.900 kW / 262 A, MT transferida ≥ 1,010 pu, 0
sobrecargas MT. As duas opções são viáveis no gêmeo; o critério de escolha (I no disjuntor × TLCD ×
UC) fica para o score elétrico (próximo passo sugerido).

Pendente: nada para a issue. Não implementado (documentado): Master a partir do GPKG do recorte
(decisão 9 do spike) e score elétrico das opções de restauração.

## 4. Issue #8 — ADR-001 stack e arquitetura (22:36–22:42)

| | |
|---|---|
| Branch | `docs/adr-001` (de `main` `283a368`) |
| PR | ver seção "PRs abertos/mergeados" no fim |
| Origem | `docs/backlog/08-adr-stack.md` |

`docs/review/` sem arquivo novo depois de `PR-03.md` (nada a aplicar antes desta issue).

Entregue: `docs/adr/ADR-001-stack.md` (uma ADR curta por decisão — contexto → decisão →
consequências — e tabela de alternativas descartadas), linkada no README (introdução e estrutura de
`docs/`). Sem código; a tríade `ruff check / ruff format / pytest` foi rodada mesmo assim.

Decisões tomadas:
- Uma única ADR numerada (ADR-001) cobrindo toda a stack, como pede o backlog, em vez de uma ADR por
  tema; futuras mudanças ganham ADR-002+ em `docs/adr/`.
- Separei **decisões aceitas** (1–7: uv + CLI typer; GeoParquet/Parquet + GPKG; ties geométricas
  ≤ 2 m em EPSG:31983 e cluster TQR; OpenDSS via bdgd2opendss + OpenDSSDirect; networkx separado
  do gêmeo; HITL nível 2 com verificador determinístico e log só de acréscimo; Conventional
  Commits/PR por issue) de **decisões propostas** (8–11: MapLibre + PMTiles, MCP, GitHub Models
  atrás de `LLMClient`, benchmark/simulador), porque as últimas ainda não foram exercitadas — as
  issues #4 e #7 as confirmam ou revisam.
- Incorporei os números que justificaram cada decisão (43 camadas, SSDMT 1,0 M, UCBT_tab 5,0 M,
  TQR0007 em 180 s / 0,5 s, cluster em 1,2 s, raio de 2 m vs 50 m) para a ADR ser verificável
  contra `docs/spike-opendss.md`, `docs/bdgd-relacoes.md` e `docs/bdgd-light-2025.md`.
- Registrei o formato do log de auditoria (JSON Lines com hash do registro anterior) e a regra "nada
  de `set_switch` sem token de aprovação" como decisão, não como implementação — ainda não há
  código de agente.

Pendente: nada. Para validar: ler `docs/adr/ADR-001-stack.md` e conferir se as decisões propostas
8–11 refletem o que o mantenedor quer para F1/F3 (as issues #4 e #7 desta fila seguem a ADR).

## 5. Issue #7 — spike GitHub Models / `LLMClient` (22:42–22:58)

| | |
|---|---|
| Branch | `feat/llm-client` (de `main` `6c763e1`) |
| PR | ver seção "PRs abertos/mergeados" no fim |
| Origem | `docs/backlog/07-spike-github-models.md` |

`docs/review/` sem arquivo novo depois de `PR-03.md`.

**Achado principal: o GitHub Models não existe mais.** Não havia `GITHUB_TOKEN` no ambiente; usei o
token OAuth do `gh` (`gho_…`) para a spike e tanto `GET /catalog/models` quanto
`POST /inference/chat/completions` responderam `410 github_models_retirement_brownout`. A
documentação oficial confirma a aposentadoria completa em **30/07/2026** (playground, catálogo,
inferência, BYOK), apontando para Azure AI Foundry ou Copilot. Portanto não há limites de taxa/tokens
a observar nem modelo do catálogo a recomendar.

Entregue: `bdgd_light.agent` (`llm.py`) com `LLMClient` (Protocol), `Message`/`ToolSpec`/`ToolCall`/
`Text`/`ToolCalls`/`Uso`, `interpretar_resposta`, `FakeLLMClient` + `fake_soma()`,
`OpenAICompatClient` (httpx, 429 com `Retry-After`, `listar_modelos`), `GitHubModelsClient`
(*preset*), `cliente_do_ambiente`, laço `conversar` com `Conversa.to_dict()`, ferramenta `soma`;
CLI `bdgd-light llm` (`--fake`, `--endpoint`, `--modelo`, `--json`); `scripts/listar_modelos.py`;
28 testes sem rede (`FakeLLMClient` + `httpx.MockTransport`); `docs/spike-llm.md`; README; CI passa
a instalar `--extra agent`; ADR-001 decisão 10 marcada como **alterada**.

Decisões tomadas:
- **Interface preservada, provedor trocado**: o cliente real é `OpenAICompatClient` (qualquer API
  `chat/completions` compatível com a OpenAI — Azure AI Foundry, OpenAI, Ollama/LM Studio locais),
  configurado só por `BDGD_LLM_ENDPOINT`/`BDGD_LLM_TOKEN`/`BDGD_LLM_MODEL`. Sem SDK de provedor.
- `GitHubModelsClient` **fica** (subclasse de 30 linhas com endpoint/catálogo/cabeçalhos do GitHub e
  `GITHUB_TOKEN`) porque backlog, plano e ADR o citam; ao receber 410 lança
  `ServicoIndisponivelError` com a explicação e a orientação de migrar. Sai quando a F3 escolher o
  provedor.
- Erros tipados (`TokenAusenteError`, `LimiteDeTaxaError(retry_after)`, `ServicoIndisponivelError`,
  `RespostaInvalidaError`); laço tolerante (ferramenta desconhecida/exceção → `{"erro": …}` para o
  modelo; `max_rodadas=5`); `temperature=0` por padrão.
- Modelo padrão `gpt-4.1-mini` (OpenAI/Azure, *tool calling* nativo); recomendação F3: Azure AI
  Foundry ou Ollama local (`llama3.1:8b`, `qwen2.5:7b`) para desenvolvimento offline.
- Testes garantem "segredos só por ambiente": fixture `autouse` limpa `GITHUB_TOKEN`/`BDGD_LLM_*` e
  um teste varre `llm.py` contra padrões de token.
- Não adicionei dependência nova: `httpx` já estava no extra `agent`.

Pendente: escolher o provedor real e cadastrar `BDGD_LLM_TOKEN` como *secret* (F3). Para validar:

```bash
uv sync --extra agent
uv run bdgd-light llm --fake "Quanto é 2 + 3?"                 # ⚙ soma({"a": 2.0, "b": 3.0}) → 5.0 / O resultado é 5.
GITHUB_TOKEN=$(gh auth token) uv run bdgd-light llm "Quanto é 2 + 3?"   # exit 1: 410 … aposentado em 30/07/2026
uv run pytest tests/test_llm.py -q                             # 28 passed, sem rede
# com um provedor compatível com a OpenAI (ex.: Ollama local)
BDGD_LLM_ENDPOINT=http://localhost:11434/v1/chat/completions BDGD_LLM_TOKEN=ollama \
  BDGD_LLM_MODEL=llama3.1:8b uv run bdgd-light llm "Quanto é 2 + 3?"
```

## 6a. Ajustes das revisões PR-04, PR-05 e PR-06 (23:03–23:45)

| | |
|---|---|
| Branch | `fix/review-pr04-pr06` |
| PR | #19 |
| Origem | `docs/review/PR-04.md`, `PR-05.md`, `PR-06.md` (apareceram às 23:03, durante a issue #4) |

Os três arquivos chegaram com a issue #4 já em andamento (comando `tiles` pronto, console em
construção). Guardei o trabalho do console num *stash*, voltei a `main` e apliquei os pedidos em PR
próprio antes de retomar.

O que foi feito:

1. **PR-06 — log de auditoria (pedido pequeno).** `bdgd_light.agent.audit`: `AuditLog` só de
   acréscimo em JSON Lines; cada registro tem `seq`, `ts` (UTC, ms), `tipo`, `dados`, `hash_anterior`
   e `hash` SHA-256 do JSON canônico (chaves ordenadas), primeiro elo = `GENESIS` (64 zeros). Reabrir
   um arquivo continua a cadeia; `verificar`/`verificar_arquivo` recalculam tudo e apontam a linha
   alterada, removida ou reordenada (`AuditError`). `conversar(..., audit=log)` grava um `llm.rodada`
   por rodada (mensagens **novas** daquela rodada, resposta com `tool_calls`, execuções com argumentos e
   resultados, `uso`) e `conversa.fim` (rodadas, ferramentas executadas, `uso_total`) ou
   `conversa.erro`. `Conversa` ganhou `hash_auditoria` e `uso_total`. CLI: `bdgd-light llm --audit`
   (padrão `data/audit/llm.jsonl`, `--sem-audit` desliga) e novo `bdgd-light audit ARQUIVO
   [--mostrar N]` (exit 1 se a cadeia quebrar). `fake_soma()` passou a devolver `Uso` estimado e
   `finish_reason` para o log ter números. 13 testes novos (`tests/test_audit.py`) + CLI.
2. **PR-04 item 3 — nota "métricas MT".** README (seção `dss`) e `docs/escopo-alimentadores.md`
   registram que a BT do modelo herda ramais `RAMLIG.COMP` suspeitos e que o veredito do MVP é MT
   (tensão MT 0,93–1,05 pu, corrente no disjuntor/tronco).
3. **PR-04 itens 1 e 2 — fase 3, não bloqueiam.** Abertas as issues **#17** (Master do gêmeo a partir
   do GPKG do recorte) e **#18** (`twin.score_eletrico`, verificador elétrico das opções) com critérios
   de aceite; não implementadas hoje porque a revisão as classifica como fase 3.
4. **PR-05 — regra para ADRs.** Anotada: decisões novas vão em ADR-002+ (não editar a 001). A issue #4
   (console) sairá com `docs/adr/ADR-002-console-maplibre-pmtiles.md` em vez de alterar a decisão 8.

Decisões tomadas:
- Hash cobre `{seq, ts, tipo, dados, hash_anterior}` serializados com `sort_keys`, sem espaços e
  `ensure_ascii=False`; `dados` passa por `json.loads(json.dumps(..., default=str))` antes de entrar
  na cadeia, para que o que se verifica seja exatamente o que está no disco.
- Um registro por rodada (e não um por mensagem) — mantém o log legível e alinhado ao que o benchmark
  precisa (rodadas, tokens, ferramentas); a aprovação/rejeição humana entra como tipo novo quando
  existir HITL de verdade.
- O padrão `data/audit/llm.jsonl` fica fora do git (`data/` ignorado); os testes passam `--audit
  tmp_path`.

Para validar:

```bash
uv run bdgd-light llm --fake "Quanto é 2 + 3?"          # … auditoria: 3 registro(s) em data/audit/llm.jsonl · hash …
uv run bdgd-light llm --fake "Quanto é 10 + 32?"        # … 6 registro(s) (a cadeia continua)
uv run bdgd-light audit data/audit/llm.jsonl --mostrar 3  # ✔ 6 registro(s), cadeia íntegra
sed -i '' '2s/"a":2.0/"a":9.0/' data/audit/llm.jsonl && uv run bdgd-light audit   # exit 1: seq=2: hash não bate
uv run pytest tests/test_audit.py tests/test_llm.py -q  # 41 passed
```
