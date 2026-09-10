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
| PR | ver seção "PRs abertos/mergeados" no fim |
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
