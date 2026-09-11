# Resumo da rodada 3 — 11/09/2026 (para o Vinicius)

**Fila esgotada: 6 issues, PRs #54–#60, CI verde na primeira tentativa em todos, `main` em `e54aa9b`, 292 testes.**
Diário em `NOITE-3.md`; revisões `PR-17` (demo), `PR-18` (benchmark), `PR-19` (dívida técnica), todas aprovadas.
**O MVP está pronto para você testar e para apresentar.**

## O que mudou nesta rodada
- **Demo/aula**: modo passo a passo no console (uma manobra por clique, mapa recolorindo a cada uma), 3 capturas no
  README e `docs/demo-roteiro.md` — roteiro de 15 min testado do zero num clone limpo, com tempos reais e plano B.
- **Benchmark**: 34 tarefas, 284 execuções com Gemini por US$ 1,69, custo em US$ por execução, eventos sem manobra.
- **Dívida técnica fechada**: OpenDSS em subprocesso isolado (fim dos crashes), postes fantasmas fora do recorte e
  dos tiles, inventário regerado, e a não convergência da Tijuca diagnosticada até a causa.

## Três achados que valem para a aula (e talvez para um artigo)
1. **Ipanema era artefato de cadastro.** Com a folga de 50 m no polígono da subestação, Ipanema/Leblon cai de 109
   para 4 interligações telecomandadas de campo, e o LDS 9210 de 31 para 0. A escolha inicial do cenário B veio de um
   número inflado por barras de pátio não modeladas — e virou o cenário negativo da demo. Contar isso é honesto e é
   uma aula inteira sobre qualidade de dado.
2. **A não convergência da Tijuca é um ciclo-limite**, causado por circuitos BT com quase toda a carga monofásica na
   mesma fase (`FAS_CON`); um único transformador derruba a solução. Rebalancear foi testado e rejeitado por razão
   física.
3. **Exemplos anotados podem não ajudar** o Gemini Flash: 8/55 falhas de chamada com exemplos, 0/22 sem. Isso
   contraria a premissa do PowerChain. Antes de afirmar, falta o A/B `hard --k 5 --sem-exemplos` e o benchmark com
   OpenAI (PR-18).

## Checklist de teste (30 min, `main` limpo)
```bash
cd /Users/vinicius/repos/bdgd-light && git checkout main && git pull   # árvore limpa agora
uv sync --extra dev --extra twin --extra agent --extra console
(cd console && npm ci && npm run build)
uv run pytest -q                                   # 292 verdes
export OPENAI_API_KEY="..."                        # confira: echo ${#OPENAI_API_KEY} → ~164
BDGD_CONSOLE_TOKEN=demo uv run bdgd-light serve --cluster tijuca --provider openai --porta 8010 --estado /tmp/aula/estado
```
Abra `http://127.0.0.1:8010/?cenario=tijuca` e siga `docs/demo-roteiro.md` §3: injetar falta → proposta (veja as
alternativas com o motivo de descarte, inclusive AMALIA a 180 %) → aprovar manobra por manobra. Depois §4.1 (Ipanema,
cenário negativo) e §4.2 (recusa forçada do verificador). Se algo travar, o §"Plano B" usa `--provider fake`.

## Pendências suas
1. **Benchmark com OpenAI** (≈US$ 0,55): `uv run bdgd-light bench --provider openai --nivel simple --k 3 --seed 42`
   e depois `--nivel medium,hard --acrescentar`. É o que falta para a tabela comparativa final.
2. **Perguntas para a Light**: `FAS_CON = AN` em massa é fase real ou padrão de cadastro? Ramais `RAMLIG` de 300–988 m
   são reais? E o trecho `11051956` (20 m, 132 A) no tronco de AMALIA, cadastro ou restrição?
3. **Opcional**: `brew install gifski` se quiser o GIF da demo no lugar das 3 capturas; `gh secret set OPENAI_API_KEY`
   para o `llm-smoke` do CI; tabela `COR_NOM` do Manual da BDGD (PDF) para a corrente nominal real das chaves.

## Próxima fila, quando você quiser
Depois do seu teste: correções do que aparecer, benchmark OpenAI incorporado, e então as frentes maiores — cenário C
(Centro, rede reticulada, exige modelar network protectors), multi-operador/SSE no console, e o artigo (o benchmark
já produz os números).
