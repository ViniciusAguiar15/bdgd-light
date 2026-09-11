---
title: "twin: paridade do gpkg2dss contra o bdgd2opendss de referência"
labels: area:twin, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
O `twin/gpkg2dss.py` é nosso; o `bdgd2opendss` (EPRI/Paulo Radatz) é a referência da comunidade.
Ele foi usado como oráculo pontualmente, mas não há uma comparação sistemática — e a validade de
todo o gêmeo depende disso.

## Tarefa
- Rodar os dois conversores sobre os mesmos K alimentadores (5 é suficiente, incluindo um dos que
  passaram na #29) e comparar, no fluxo base: tensões por barra (erro máximo e médio em pu), perdas
  totais (kW), corrente no disjuntor da saída e nº de elementos por tipo.
- Onde divergir, **explicar a causa** (modelagem de regulador, curva de carga, conexão de fase,
  trecho agregado) em vez de só reportar o número.
- `docs/paridade-twin.md` com a tabela por alimentador, as divergências explicadas e o veredito:
  onde o nosso conversor pode ser usado com confiança e onde não.
- Se o `bdgd2opendss` não instalar no ambiente, registrar o erro exato e seguir com as demais issues
  — não passar a noite lutando com dependência.

## Critérios de aceite
- [ ] Comparação numérica versionada para pelo menos 3 alimentadores.
- [ ] Cada divergência acima de 1 % em tensão tem causa nomeada.
- [ ] Veredito escrito, inclusive se for "não dá para afirmar paridade ainda".
