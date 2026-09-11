# Rodada 4 — fechamento (11/09/2026)

Fila `docs/backlog/19–23` (issues #61–#65) **concluída**, mais 5 PRs de correção pedidos nas
revisões. 13 PRs mergeados em `main` entre 14:55 e 17:34 (horário de Brasília).

## O que a rodada entregou

| # | Entrega | PRs |
|---|---|---|
| 19 | Rejeitar com motivo faz o agente **replanejar**, com restrição virando estado da sessão e gate no verificador | #66, #74 |
| 20 | **Impacto estimado** da manobra: consumidor-minutos evitados e DEC do conjunto, sempre rotulado como estimativa sob premissa de reparo | #67, #75 |
| 21 | **Painel de detalhes elétricos** da proposta: tensões com a barra, perdas, trechos mais carregados, convergência, perfil de tensão | #68, #76 |
| 22 | Benchmark **OpenAI**, **A/B dos exemplos anotados** (n=55 por braço) e quitação da dívida técnica | #69, #70, #71, #77, #78 |
| 23 | Cenários de **pico de carga** e **chave indisponível** no console, com "sem manobra" explícito | #72 |

## Os três resultados que mudam a conversa

**1. O verificador ficou mais forte que o modelo em mais um eixo.** A restrição que o operador
impõe ao rejeitar uma proposta não depende de o LLM lembrar dela: vira estado da sessão e é
checada por código determinístico (`restricoes_operacionais`). E toda rejeição agora proíbe, no
mínimo, a chave rejeitada — mesmo quando o motivo é vago demais para estruturar. É o mesmo padrão
do `chave_indisponivel`, que entra direto no conjunto de chaves bloqueadas do verificador.

**2. O A/B dos exemplos anotados achou uma interação, não um efeito geral.** Com n=55 por braço:
no Gemini 2.5 Flash, tirar os exemplos leva 47/55 → 55/55 e zera o `MALFORMED_FUNCTION_CALL`; no
`gpt-4.1-mini`, 55/55 com e sem exemplos, zero malformadas. O gatilho é o texto dos exemplos, mas o
componente que quebra é o parser de *tool call* do Flash. **Não há evidência de que exemplos
anotados degradem o planejamento** — e também não há, nesta rodada, evidência de que ajudem: nenhum
braço isola ganho de ordenação/precisão com n comparável. A premissa do PowerChain não foi testada
aqui, e `docs/bench.md` agora diz isso com todas as letras.

**3. Custo medido em dois provedores.** `gpt-4.1-mini` a **US$ 0,0041/execução** e 100 % nas *hard*;
Gemini Flash a US$ 0,0051 e 85 % nas *hard* (100 % em pass@5). A demo roda em **OpenAI** por padrão
(`cliente_do_ambiente` para em `OPENAI_API_KEY` quando as duas chaves estão no ambiente) — dito
explicitamente na doc para ninguém ler o "85 % hard" do Gemini como taxa de erro do que está na tela.

## Dois bugs de conta/lógica pegos na revisão e corrigidos

- **DEC inflado** (#67 → corrigido em #75): o DEC de um conjunto era calculado com os
  consumidor-minutos do evento **inteiro**, não só dos clientes daquele conjunto. Com restauração
  atravessando dois conjuntos, o número do maior saía inflado (no exemplo 200/300, +50 %). Número
  que iria para slide.
- **Rejeição que não restringia nada** (#66 → corrigido em #74): motivo vago → extração vazia →
  o agente podia repropor exatamente a chave recusada. O operador rejeitaria, esperaria e receberia
  a mesma coisa de volta.

## Pendências

**Do repositório:**
- Consolidar as três cópias do parser de `line.smt_<id>` (`twin/score.py`, `mcp_server/sessao.py`,
  `console/api.py`) — pedido em `PR-25.md`.
- Bloco 4 da #64 (`COR_NOM`) segue **pulado**: falta o PDF do Manual da BDGD para a tabela de domínio.

**Tuas, fora do código:**
- Perguntar à Light se `FAS_CON = AN` em massa é fase real ou padrão de cadastro; e sobre `RAMLIG`
  > 300 m e o trecho `11051956`.
- Obter o Manual da BDGD (tabela de domínio de `COR_NOM`).
- `gh secret set OPENAI_API_KEY` / `GEMINI_API_KEY` para o job `llm-smoke` do CI.
- `gifski` (opcional) para o GIF da demo.

## Processo — uma nota

As revisões PR-20 a PR-24 e o diário `NOITE-4.md` foram escritos sem commit e sumiram da árvore de
trabalho antes de serem versionados. **Nada se perdeu**: o Copilot recuperou os seis arquivos e os
versionou no PR #73 (`8765d5b`). Ainda assim, a recuperação dependeu de ele ter os textos em
contexto — regra para a rodada 5: **revisão escrita é revisão commitada**, no mesmo passo.
