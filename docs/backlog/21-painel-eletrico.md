---
title: "console: painel de detalhes elétricos (o que o OpenDSS viu)"
labels: area:console, area:twin, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
Pergunta recorrente de quem é da área na demonstração: "onde eu vejo o OpenDSS?". Hoje o resultado
aparece só como veredito de uma linha.

## Tarefa
- `GET /api/propostas/{id}/eletrico` devolve, por opção simulada: corrente e margem no disjuntor,
  tensão mínima/máxima de MT com a barra onde ocorre, perdas, trechos mais carregados (top 5 com
  percentual) e convergência (iterações, ajustes aplicados).
- Console: expansor **"detalhes elétricos"** no cartão da proposta, com tabela comparando as opções
  simuladas e, para a escolhida, o perfil de tensão MT da fonte até a ponta (lista ou sparkline
  simples em SVG; sem biblioteca nova).
- Clicar num trecho sobrecarregado da tabela destaca o trecho no mapa.

## Critérios de aceite
- [ ] Smoke cobre abrir o expansor e conferir que a rota inviável aparece com o trecho a 180 %.
- [ ] Sem dependência nova no front-end; funciona também com `--provider fake`.
