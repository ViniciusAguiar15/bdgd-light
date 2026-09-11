---
title: "twin: geração distribuída no gêmeo — sobretensão e fluxo reverso"
labels: area:twin, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
Com a GD mapeada (#35), o gêmeo pode responder o que hoje ele ignora: em alimentador com alta
penetração, a geração no meio do dia eleva a tensão e pode inverter o fluxo — o que muda margem de
disjuntor, perdas e violação de tensão.

## Tarefa
- Modelar a GD no `gpkg2dss.py` como `PVSystem` (ou `Generator` quando a fonte não for solar),
  alocada no PAC/transformador da UC quando houver chave, e distribuída proporcionalmente à carga
  quando só houver agregado — deixando **explícito no código e na doc** qual dos dois foi usado.
- Rodar o fluxo em 3 instantes representativos (madrugada sem geração, meio-dia com geração plena,
  ponta da noite) para os três clusters e para os alimentadores de maior penetração encontrados na #35.
- Medir: Vmax MT e onde ocorre, nº de barras acima de 1,05 pu, sentido do fluxo no disjuntor de
  saída, perdas, e a diferença com o caso sem GD.
- `docs/gd-gemeo.md` com as tabelas e a leitura: em quais alimentadores a GD já importa hoje.
- Flag para ligar/desligar GD na simulação, com o padrão **desligado** enquanto não houver validação
  — mudança de padrão só com evidência.

## Critérios de aceite
- [ ] Comparação com/sem GD versionada para pelo menos 5 alimentadores.
- [ ] Premissa de alocação da GD documentada e visível em quem lê o resultado.
- [ ] Suíte verde; nenhuma mudança de comportamento padrão do agente.
