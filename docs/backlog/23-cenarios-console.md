---
title: "sim+console: cenários de pico de carga e chave indisponível na interface"
labels: area:console, area:agent, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
O simulador já gera `pico_carga` e `chave_indisponivel`, e o benchmark já os cobre, mas a demonstração
só mostra falta permanente.

## Tarefa
- Botão/menu no console para injetar os três tipos de evento (não só a falta do cenário).
- Pico de carga: o agente roda fluxo com `loadmult` e responde com as violações previstas, sem manobra
  (ou com manobra de alívio, se houver); o console mostra os trechos violados no mapa.
- Chave indisponível: o agente informa quantos clientes ficam a jusante sem alternativa e **não** propõe
  manobra.
- Ambos entram no `docs/demo-roteiro.md` e no `docs/demo-profissional.md` como variações de 1 minuto.

## Critérios de aceite
- [ ] Smoke cobre os três tipos; o veredito "sem manobra" aparece claramente na interface.
