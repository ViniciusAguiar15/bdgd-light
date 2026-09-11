---
title: "bench: OpenAI completo, Gemini k=5 nas hard, novas tarefas e eventos, prompt de resposta explícita"
labels: area:agent, phase:F4, copilot
milestone: F4 Benchmark + governança
---
## Tarefa
- Rodar `bench --provider openai` simple/medium k=3 e hard k=3 (`--acrescentar`), e os 3 cenários do agente com OpenAI
  (tokens/tempo em `docs/agent.md`); Gemini hard k=5.
- Prompt do orquestrador: a resposta final deve conter explicitamente o número pedido (H09/H03).
- +4 tarefas medium/hard de Ipanema; harness aceita `falta_transitoria` e `chave_indisponivel`.
- `docs/bench.md`: tabela comparativa final fake × Gemini × OpenAI, com custo em US$ por execução, e leitura
  para a apresentação (o que a compactação e os exemplos anotados mudam).
## Critérios de aceite
- [ ] Relatórios versionados em `docs/bench/`; CI continua só com fake.
