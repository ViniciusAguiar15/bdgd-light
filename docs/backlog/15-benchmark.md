---
title: "bench: benchmark estilo PowerChain (tarefas, pass@k, precisão, tokens/pass@1, OpenAI × Gemini)"
labels: area:agent, area:docs, phase:F4, copilot
milestone: F4 Benchmark + governança
---
## Tarefa
`bench/`: 30 tarefas (10 simple / 10 medium / 10 hard) sobre os clusters Tijuca, Ipanema e Taquara, cada uma com
resposta numérica esperada e sequência de ferramentas de referência (anotadas); `bdgd-light bench --provider X
--k 5` executa n vezes, calcula pass@k, precisão de ordenação e tokens por pass@1, grava CSV + relatório
`docs/bench/<data>-<provider>.md` com tabela comparativa entre provedores e entre modos (com/sem exemplos anotados).

## Observação do mantenedor (validação real, `docs/review/RESULTADOS-OPENAI.md`)
No cenário `ipanema_9210` o resumo do `gpt-4.1-mini` citou "1.730 clientes sem tensão" (total do CTMT PTS0001) em
vez dos **479** não restauráveis presentes no retorno de `isolate_fault`/`restore_options` — a proposta estava
certa, o texto não. O benchmark pontua também a **correção numérica do resumo/resposta** (a resposta final tem de
conter o número esperado, dentro da tolerância), e não só a proposta e a sequência de ferramentas. Tarefas M08/M09
(clientes na zona; UCBT que continuam sem tensão após isolar) e H07 (Ipanema, 479) cobrem exatamente esse ponto.

## Critérios de aceite
- [ ] Roda com `FakeLLMClient` no CI (tarefas simple) e com provedores reais localmente.
- [ ] Relatório reproduzível por semente.
