---
title: "tech+bench: dívida da rodada 3 e as medições que faltam"
labels: area:twin, area:ingest, area:agent, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Tarefa (um PR por bloco)
1. **Benchmark OpenAI** (`OPENAI_API_KEY` no ambiente): `--nivel simple --k 3`, depois
   `--nivel medium,hard --k 3 --acrescentar`; os 3 cenários do agente com `--provider openai`;
   tabela comparativa final fake × Gemini × OpenAI em `docs/bench.md`, com custo em US$.
2. **A/B dos exemplos anotados**: `--nivel hard --k 5 --sem-exemplos` com Gemini (e com OpenAI, se o
   orçamento permitir) para confirmar ou derrubar a correlação com `MALFORMED_FUNCTION_CALL`.
   Escrever a conclusão em `docs/bench.md` com os n de cada braço — se o efeito for do provedor, dizer
   isso; **não** desligar os exemplos por padrão sem evidência.
3. **Dívida**: `ReadTimeout` deve repetir a chamada como já se faz com resposta vazia; remover
   `BDGD_MOTOR=thread` e `encerrar_processo`; filtro de postes topológico (distância ao trafo da UC)
   em vez de só bbox, mantendo o bbox como rede de segurança.
4. **`COR_NOM`**: se `docs/` receber o PDF do Manual da BDGD, transcrever a tabela de domínio para
   `catalogo.py` e usá-la como `i_nominal_a` primário no `score_eletrico`, com a ampacidade do tronco
   como fallback. Se o PDF não estiver lá, pular e registrar.

## Critérios de aceite
- [ ] Relatórios versionados em `docs/bench/`; suíte verde; CI continua só com fake.
