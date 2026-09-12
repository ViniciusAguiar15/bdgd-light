---
title: "Diário — Modo noturno, rodada 6"
---

# Modo noturno — rodada 6

## 0. Ambiente (20:54)

- `main` em `f0b4ee3` (docs(backlog): rodada 6 — generalização, qualidade do cadastro e geração
  distribuída), após `4d88f80` (MANHA-5) e `a55e30d` (fechamento da rodada 5).
- Árvore de trabalho limpa, nenhuma pendência solta.
- `OPENAI_API_KEY` (164 caracteres) e `GEMINI_API_KEY` (53 caracteres) presentes via `zsh -lic`
  (persistidas em `~/.zshrc` desde a rodada 4). Nenhuma chave faltando no início da rodada.
- Fila desta rodada (ordem definida pelo usuário, backlog → issue):
  1. backlog 38 → #100 — pedidos da revisão MANHA-5 (rápido)
  2. backlog 29 → #91 — generalização: pipeline em alimentador nunca visto
  3. backlog 30 → #92 — agente fora do treino
  4. backlog 31 → #93 — qualidade do cadastro BDGD Light 2025
  5. backlog 32 → #94 — atlas de interligações
  6. backlog 35 → #97 — ingest GD (MMGD ANEEL)
  7. backlog 36 → #98 — GD no gêmeo
  8. backlog 37 → #99 — GD na restauração
  9. backlog 34 → #96 — sensibilidade de premissas
  10. backlog 33 → #95 — paridade gpkg2dss × bdgd2opendss
- Regra desta rodada: diário commitado no mesmo passo/PR de cada issue (mantida da rodada 5).
- Regra de honestidade das medições (29-37): resultado negativo é resultado — se o pipeline falhar
  em X% dos alimentadores sorteados, o número e as causas vão para o relatório; recorte não é
  ajustado para melhorar o número (ajuste, se necessário, vira issue nova).
- Nota: issue #90 (título "cli: bdgd-light replay...") é uma duplicata da #83, já implementada e
  mergeada na rodada 5 (PR #88). Não faz parte da fila desta rodada — não foi tocada.

## 1. Issue #100 — pedidos da revisão MANHA-5 (21:01)

- Corrigi `scripts/gerar_resultados.py` para distinguir família por modo (com/sem exemplos e com/sem compactação), acrescentar a coluna **modo** no consolidado, marcar a configuração padrão com `★ padrão` e mostrar frações brutas ao lado de **ordem**/**precisão** em `docs/resultados.md`.
- Estendi `tests/test_gerar_resultados.py` para cobrir a nova coluna, o marcador da configuração padrão, as frações e a saída determinística em duas gerações consecutivas.
- Investiguei H12–H15 nos CSVs `openai-hardplus-k3*`: H14/H15 rederivam `locate_fault → isolate_fault → restore_options → propose_plan` em 6/6 execuções, o que os dados sustentam como sequência válida de replanejamento; por isso corrigi a `referencia` dessas tarefas em `bench/tarefas.yaml` e reescrevi a análise em `docs/bench.md`.
- O desperdício residual ficou concentrado em H13: `propose_plan` extra em 6/6 execuções, `get_topology` extra em 1/3 do braço com exemplos e salto de `isolate_fault` em 2/3 do braço sem exemplos; documentei isso no bench.
- Regenerei `docs/resultados.md`, validei `uv run bdgd-light --help`, rodei a suíte de testes completa e deixei a árvore pronta para lint final, commit, push e PR da #100.


## 2. Issue #91 — generalização: pipeline em alimentador nunca visto (21:21)

- Li a issue #91, o backlog canônico (`docs/backlog/29-generalizacao-alimentadores.md`) e o
  pipeline relacionado: inventário/recorte por CTMT, grafo (`grid/rede.py`), `gpkg2dss`, score
  elétrico e as ferramentas `inject_fault`/`restore_options` do servidor MCP.
- Confirmei que o ambiente tinha dados reais da Light (`data/parquet/`, `data/inventario_ctmt.csv`
  e `data/Light_382_2025-12-31_V11_20260824-0926.gdb`), então rodei a execução real pedida, sem
  recorrer a mocks para o relatório final.
- Implementei `src/bdgd_light/generalizacao.py` e o runner `scripts/generalizacao.py`: amostragem
  determinística estratificada por região × porte, recorte automático de `CTMT + vizinhos diretos`
  quando há tie, execução do pipeline completo por etapa e exportação de um CSV por `CTMT × etapa`.
- Adicionei `tests/test_generalizacao.py` cobrindo o sorteio determinístico, a normalização do CSV
  (sucesso/falha/não executada) e uma rodada real pequena sobre a fixture sintética do projeto.
- Rodei a amostra real de 30 alimentadores com semente 91 e gerei
  `docs/bench/2026-09-11-generalizacao.csv`: 30/30 sucesso em todas as etapas, 18/30 sem tie,
  12/30 com tie, 7/30 com opções de restauração e 39 opções viáveis entre 42 avaliadas no score.
- Documentei os números e os limites de interpretação em `docs/generalizacao.md`, incluindo o
  comando exato de reprodução e o resultado negativo relevante (tie não implica restauração útil).
- Abri a follow-up issue #102 para separar, em rodadas futuras, “fluxo convergiu” de “caso base
  eletricamente saudável”, porque vários casos-base convergiram com `Vmin` muito baixa.
