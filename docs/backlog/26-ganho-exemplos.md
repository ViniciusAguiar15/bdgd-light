---
title: "bench: medir o ganho dos exemplos anotados (ordenação e precisão), não só o custo"
labels: area:agent, area:bench, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
O A/B da rodada 4 (n=55 por braço) mostrou que tirar os exemplos anotados **não custa acerto** no
provedor padrão. Ele **não** mede se os exemplos **rendem** alguma coisa — que é exatamente a
premissa do PowerChain (pares tarefa↔workflow anotados ajudam o planejamento). Sem essa medição, a
dissertação não pode afirmar nem negar a premissa.

## Tarefa
- Rodar, com `--provider openai` (o padrão da demo) e `k=5`, o conjunto *hard* **com** e **sem**
  exemplos, registrando não só `pass@1` mas as métricas em que o efeito apareceria:
  **precisão de ordenação**, número de rodadas até a proposta, chamadas de ferramenta
  desnecessárias e tokens. Mesma seed, mesmo n nos dois braços.
- Se `pass@1` saturar em 100 % nos dois (provável), acrescentar um conjunto **hard+**: tarefas com
  restrição ativa, chave indisponível e rejeição prévia — ou seja, onde a ordem e a escolha da
  ferramenta importam mais. Documentar como as tarefas novas foram construídas.
- Escrever a conclusão em `docs/bench.md` com a forma correta: efeito medido, tamanho da amostra,
  e o que **não** foi medido. Se o resultado for "nenhum efeito detectável com n=55", escrever isso
  — resultado nulo bem medido vale mais que alegação.

## Critérios de aceite
- [ ] CSV e relatório versionados em `docs/bench/` para cada braço novo.
- [ ] Seção em `docs/bench.md` com a comparação e a leitura honesta (inclui poder da amostra).
- [ ] Nenhuma mudança de comportamento padrão do agente sem evidência nesta seção.
