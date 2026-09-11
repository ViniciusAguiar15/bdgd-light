---
title: "grid: atlas de interligações da Light — quem pode socorrer quem"
labels: area:grid, area:docs, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
A detecção geométrica de ties (chave NA a ≤ 2 m do PAC de outro CTMT, com a folga `EM_SUB` para
excluir pátio de subestação) já roda na base inteira, mas o resultado só foi usado para escolher os
clusters. Ele é, por si, um resultado: **quantos alimentadores da Light têm alternativa de socorro,
e quantos dependem de manobra em campo**.

## Tarefa
- Consolidar, para todos os alimentadores: nº de ties de campo, quantos telecomandados, para quais
  alimentadores/subestações/conjuntos eles levam, e o grau do alimentador no **grafo de socorro**
  (alimentador como nó, tie como aresta).
- Métricas do grafo de socorro: distribuição de grau, quantos alimentadores têm grau 0 (ilhados,
  sem socorro possível), componentes conexas, e o percentual de clientes em alimentadores de grau 0.
- `docs/atlas-interligacoes.md` com as tabelas e, se for barato, um histograma em SVG puro.
- Exportar o grafo de socorro em um formato aberto (GraphML ou CSV de arestas) em `docs/dados/`.

## Critérios de aceite
- [ ] Números por alimentador e agregados, gerados por script e rastreáveis.
- [ ] Percentual de clientes sem socorro possível declarado explicitamente.
- [ ] Nada em `data/` entra no git; os agregados sim.
