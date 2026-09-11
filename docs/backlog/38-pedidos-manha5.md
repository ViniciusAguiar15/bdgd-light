---
title: "docs+bench: pedidos da revisão MANHA-5"
labels: area:bench, area:docs, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
Três pedidos abertos da revisão da rodada 5 (`docs/review/MANHA-5.md`).

## Tarefa
1. **Número absoluto ao lado da porcentagem.** Em `docs/bench.md` e `docs/resultados.md`, as colunas
   de ordem e precisão passam a trazer também a fração (ex.: "100 % (55/55)" e "96,4 % (53/55)").
   Porcentagem com n pequeno faz diferença de 2 execuções parecer efeito.
2. **Investigar a queda de precisão no *hard+*.** Precisão cai de ~97 % para ~68 % nos **dois**
   braços, com 1,3–1,4 chamadas desnecessárias por execução. Analisar as sequências de H12–H15,
   identificar quais chamadas sobram (e se são realmente supérfluas ou se o gabarito é que está
   estreito demais para casos com replanejamento) e escrever o achado em `docs/bench.md`. Se o
   gabarito estiver errado, corrigir o gabarito — não a métrica.
3. **Modo na chave de família do consolidado.** Em `scripts/gerar_resultados.py`, a família ignora o
   sufixo do modo: a linha `gemini-hard-k5` reporta hoje os números do arquivo *sem exemplos* (100 %)
   quando a configuração padrão é 85 %. Incluir o modo na chave, acrescentar coluna **modo** na
   tabela e marcar qual é a configuração padrão do agente.

## Critérios de aceite
- [ ] As três correções aplicadas, com a saída do consolidado ainda determinística (teste byte a byte).
- [ ] O achado do item 2 escrito, com a conclusão que os dados sustentarem.
