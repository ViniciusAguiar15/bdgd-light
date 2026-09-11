---
title: "bench: generalização — o pipeline num alimentador nunca visto"
labels: area:ingest, area:twin, area:agent, area:bench, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
Todo número do projeto vem de três clusters escolhidos a dedo (Tijuca, Ipanema, Taquara) entre os
1.802 alimentadores da Light. A pergunta mais provável de uma banca — "isso funciona só onde vocês
ajustaram?" — hoje não tem resposta. Esta é a lacuna mais importante em aberto.

## Tarefa
- `scripts/generalizacao.py`: sorteia **N alimentadores** (padrão 30) com semente fixa a partir do
  inventário, estratificando por porte (nº de trechos) e região, e roda o pipeline **inteiro sem
  nenhum ajuste manual**: recorte → grafo → `gpkg2dss` → fluxo base → detecção de ties → injeção de
  falta no maior trecho tronco → `restore_options(score=true)`.
- Medir **taxa de sucesso por etapa** e, para cada falha, gravar alimentador, etapa, exceção/motivo
  em CSV — a falha é o resultado, não um problema a esconder.
- Relatório `docs/generalizacao.md`: tabela por etapa (n, sucesso, falha, motivo mais comum), os
  casos que falharam com link para o CSV, e uma seção "o que isso permite e não permite afirmar".
- Limitar custo: nada de LLM nesta issue (o agente entra na #30); só pipeline determinístico.

## Critérios de aceite
- [ ] CSV versionado em `docs/bench/` com uma linha por alimentador e etapa.
- [ ] `docs/generalizacao.md` com as taxas por etapa e os motivos de falha agrupados.
- [ ] Rodar duas vezes com a mesma semente dá o mesmo conjunto de alimentadores.
