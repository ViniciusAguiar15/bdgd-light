---
title: "console: fila de eventos, proposta do agente e aprovação humana"
labels: area:console, phase:F3, copilot
milestone: F3 Agente
---
## Tarefa
Backend leve (`bdgd-light serve`: FastAPI/uvicorn, extra `console`) que expõe eventos (#23), estado do grafo
(GeoJSON), propostas pendentes (#24) e `POST /aprovar|/rejeitar` (chama `approve` do MCP e aplica `set_switch`
com token). Console: painel de eventos, cartão da proposta (sequência de manobras, clientes recuperados, veredito
elétrico, raciocínio resumido, alternativas), botões Aprovar/Rejeitar, mapa recolorindo após aprovação, trilha de
auditoria da sessão. Modo demo: botão "injetar falta" que dispara o simulador.

## Critérios de aceite
- [ ] Demo ponta a ponta local: injetar falta em CABOFRIO → proposta → aprovar → mapa atualizado, em < 30 s.
- [ ] Smoke headless cobre o fluxo; README do console atualizado.
