---
title: "demo: modo passo a passo, capturas/GIF no README e roteiro da apresentação"
labels: area:console, area:docs, phase:F4, copilot
milestone: F4 Benchmark + governança
---
## Tarefa
- Console: botão **"Executar próxima manobra"** (uma chave por clique, usando o passo único do MCP) ao lado de
  "Aprovar e executar"; a lista da sequência marca o passo atual; o mapa recolore a cada passo.
- README: 3 capturas do painel (evento → proposta com alternativas e motivos → aprovado/mapa) ou um GIF ≤ 2 MB
  gerado pelo smoke (`smoke.mjs` já salva PNG; para GIF usar capturas sequenciais + `ffmpeg`/`gifski` se houver).
- `docs/demo-roteiro.md`: roteiro de 15 min para aula — contexto (BDGD, COD, PowerChain), arquitetura (5 camadas),
  demo ao vivo Tijuca com OpenAI (falta → 3 rotas → AMALIA descartada a 180 % → aprovação humana → mapa), cenário
  negativo Ipanema, momento "o LLM errou e o verificador pegou" (recusa forçada `--vmin 1.01`), números do benchmark,
  limitações e próximos passos. Incluir os comandos exatos e o que dizer em cada tela.
## Critérios de aceite
- [ ] Smoke cobre o modo passo a passo (n cliques = n manobras).
- [ ] Roteiro testado do zero em `main` limpo (`uv sync` + `npm ci`) com os tempos reais anotados.
