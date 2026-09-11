# Resumo da rodada 2 — 10/09/2026 (para o Vinicius)

**Fila esgotada: 9 issues, PRs #37–#49 mergeados, 275 testes (eram 162), diário em `NOITE-2.md`, revisões
PR-08…PR-16 todas aprovadas.** O MVP da fase 3 existe e foi validado com LLM real:

- **Agente ponta a ponta**: nos 3 cenários, OpenAI (gpt-4.1-mini) e Gemini (2.5 Flash) produzem a proposta certa, com
  o verificador determinístico aprovando (11 checagens + fluxo OpenDSS). OpenAI: 4–5 rodadas, 33–38 k tokens, 10–15 s
  de LLM; Gemini: 5 rodadas, 53–65 k tokens (antes da compactação, que cortou 74 % dos chars de ferramenta).
- **Console**: injetar falta → proposta com alternativas e motivos de descarte → aprovar com identidade do operador →
  mapa recolore; 17–20 s com operador fake, 41–58 s com Gemini. Auditoria JSONL encadeada e verificável.
- **Benchmark**: 30 tarefas (simple/medium/hard); fake 150/150; Gemini 100 % simple+medium, 95 % hard
  (o único erro é resposta implícita). Achado: um erro intermitente do Gemini era causado pela compactação — corrigido.
- **Momento didático já pronto**: AMALIA (URG29983) é descartada porque um trecho de 20 m vai a 180 % — o grafo não vê,
  o gêmeo vê; e a recusa forçada (`--vmin 1.01`) mostra o verificador barrando o LLM.

## O que falta para apresentar (rodada 3 — `docs/backlog/16`, `17`, `18`)
1. Modo passo a passo no console + capturas/GIF no README + **roteiro da aula** (`docs/demo-roteiro.md`).
2. Benchmark completo com OpenAI (exportar `OPENAI_API_KEY` antes de abrir o Copilot), Gemini k=5, novas tarefas.
3. Dívida técnica: #48 OpenDSS em subprocesso, #40 postes por bbox, #39 inventário regerado, #44 convergência.

## Decisões/pendências suas
- Gargalo `11051956` (20 m, 132 A) no tronco de AMALIA: cadastro ou restrição real? Muda como contar a história.
- Tabela `COR_NOM` do Manual da BDGD (PDF) para corrente nominal real das chaves.
- `gh secret set OPENAI_API_KEY` / `GEMINI_API_KEY` para o `llm-smoke` do CI.
- Cenário C (Centro, reticulado) fica para depois da aula.
