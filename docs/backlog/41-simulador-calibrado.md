---
title: "sim+bench: calibrar o simulador de eventos com o histórico real e conferir o DEC estimado"
labels: area:bench, area:agent, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
O simulador sorteia eventos com pesos escritos à mão (`PESOS_TIPO = {falta_permanente: 5,
falta_transitoria: 3, pico_carga: 2, chave_indisponivel: 1}`). Com o histórico da #39 dá para
calibrar isso com o mix real de causas e durações da Light — e, melhor, para **conferir a cadeia
inteira**: o DEC que o sistema estima bate com o DEC coletivo que a ANEEL publica para aquele
conjunto?

**Depende da #39.** Se ela não tiver concluído, pule esta.

## Tarefa
- Recalibrar os pesos do simulador a partir do mix real (tipo e causa), documentando o antes e o
  depois. Manter os pesos antigos acessíveis por flag para as comparações históricas não quebrarem.
- Amostrar a duração dos eventos simulados da distribuição medida, em vez de valor fixo.
- **Teste de sanidade da cadeia**: para um conjunto do recorte, somar o impacto estimado dos eventos
  de um ano simulado e comparar com o DEC coletivo publicado pela ANEEL para aquele conjunto
  (`https://dadosabertos.aneel.gov.br/dataset/indicadores-coletivos-de-continuidade-dec-e-fec`).
  Não se espera igualdade — espera-se **ordem de grandeza**. Se estiver a um fator de 10, algo está
  errado na cadeia e isso precisa ser investigado e escrito.
- `docs/calibracao-simulador.md` com os pesos novos, a origem de cada um e o resultado da conferência.

## Critérios de aceite
- [ ] Pesos e durações derivados do histórico, com fonte.
- [ ] Comparação com o DEC coletivo publicado, com a conclusão escrita mesmo se for desfavorável.
- [ ] Benchmarks antigos continuam reproduzíveis (flag para os pesos anteriores).
