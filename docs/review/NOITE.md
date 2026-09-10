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
| PR | ver seção "PRs abertos/mergeados" no fim |
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
