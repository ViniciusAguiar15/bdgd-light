---
title: "grid+console: cargas prioritárias na restauração (CLAS_SUB da própria BDGD)"
labels: area:grid, area:console, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
Num COD real, nem todo cliente pesa igual: hospital, saneamento, segurança pública e semáforo têm
prioridade sobre carga residencial. A BDGD já traz isso em `CLAS_SUB` (classe e subclasse de
consumo) nas camadas de UC — ou seja, dá para fazer sem nenhuma base externa.

## Tarefa
- Mapear as subclasses de `CLAS_SUB` que caracterizam carga prioritária (serviço público, poder
  público, saúde, saneamento, iluminação pública) conforme o dicionário da BDGD, e documentar a
  escolha — é uma decisão de projeto, não um fato, e precisa estar visível.
- Contar clientes prioritários por zona de falta e por opção de restauração, ao lado do total.
- Expor em `restore_options`, `propose_plan` e no cartão do console: "restaura 1.240 clientes,
  entre eles 3 de serviço público (saúde)".
- **Não** mudar automaticamente a ordenação das opções: a prioridade é informação para o operador
  decidir, não critério escondido no score. Se for para entrar no score, vira issue própria com
  justificativa — mudança silenciosa de critério de restauração é exatamente o que não se faz.
- `docs/grid-modelo.md` com a definição de carga prioritária adotada.

## Critérios de aceite
- [ ] Contagem de prioritários por opção, exposta nas três superfícies.
- [ ] Ordenação das opções inalterada; a prioridade aparece como informação.
- [ ] A lista de subclasses consideradas prioritárias está documentada e é fácil de revisar.
