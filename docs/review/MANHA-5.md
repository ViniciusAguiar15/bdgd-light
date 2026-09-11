# Rodada 5 — fechamento (11–12/09/2026)

Fila `docs/backlog/24–28` (issues #80–#84) concluída: PRs #85–#89, `main` em `a55e30d`.
Nenhuma issue aberta. A regra nova — diário commitado no mesmo passo — foi cumprida em todas.

## PR #85 (#80) — parser único de elemento OpenDSS · **aprovado**

Dívida quitada como pedido: prefixo em um lugar só, ao lado de onde o nome é gerado, com teste de
round-trip. É o tipo de correção que ninguém vê e que evita um bug silencioso quando o conversor mudar.

## PR #86 (#81) — suíte adversarial do verificador · **aprovado, é o melhor PR da rodada**

Os 8 casos estão lá, montados à mão, **sem LLM**, e cada um assertando o **nome do gate** — não só
que falhou. `primeiro_gate_reprovado(veredito) == caso.gate` é a asserção certa: prova qual checagem
pegou, não que alguma pegou.

O que eu não tinha pedido e ficou melhor do que eu pedi: `docs/verificador.md` é **gerado** pela
mesma matriz (`scripts/gerar_verificador_doc.py`) e existe um teste que falha se a doc sair de
sincronia com o teste. Documento e teste não podem divergir — é a forma correta de fazer isso.

Esta é a evidência central para a banca: a tabela responde "e se o modelo alucinar?" com oito linhas
concretas, incluindo a rota da AMALIA (`11051956` a ~180 %) que é o caso real onde a topologia
engana e a física reprova.

## PR #87 (#82) — ganho dos exemplos anotados · **aprovado, com 2 pedidos**

Fez o certo no ponto difícil: como o `pass@1` saturou em 100 % nos dois braços do *hard*, **não
forçou conclusão** — reaproveitou os dois braços de n=55 para medir ordem/precisão/rodadas e montou
um *hard+* (H12–H15: restrição ativa, chave indisponível, duas rejeições prévias) para pressionar
escolha e ordem. O gabarito do *hard+* continua recalculável em tempo de execução, não congelado.
Achou e corrigiu de passagem um bug real: `--seed` ia para o construtor do cliente OpenAI, não para
o payload da API — ou seja, as rodadas anteriores **não estavam semeadas de fato**.

### Pedido 1 — dizer o tamanho da diferença, não só a porcentagem

O sinal mais próximo de positivo para os exemplos é **ordem 100 % vs 96,4 %** no *hard* (n=55).
Em 55 execuções, isso é diferença de ~2 execuções — dentro do ruído. O texto diz que poder
estatístico não foi medido, o que é honesto, mas quem lê "100 % vs 96,4 %" numa tabela conclui
efeito. Pedido: pôr o **número absoluto** ao lado (ex.: "55/55 vs 53/55") nas linhas de ordem e
precisão, no `docs/bench.md` e no `docs/resultados.md`. Porcentagem com n pequeno mente sozinha.

### Pedido 2 — a queda de precisão no *hard+* merece investigação, não só registro

Precisão cai de ~97 % (*hard*) para **~68 %** (*hard+*) nos **dois** braços, com 1,3–1,4 chamadas
desnecessárias por execução. Isso não é sobre exemplos: é o agente trabalhando mal quando há
restrição ativa, chave indisponível ou rejeição prévia — exatamente os casos que a rodada 4
introduziu. Vale uma análise curta das sequências de H12–H15 (quais chamadas sobram) e uma frase em
`docs/bench.md`. É o achado mais interessante da rodada e está registrado como nota de rodapé.

## PR #88 (#83) — `bdgd-light replay` · **aprovado**

Timeline completa (evento → ferramentas → veredito com gates → rejeição/replanejamento → aprovação
→ execução), `--json`, e o teste negativo obrigatório está lá: adultera o registro `restore_options`
e confirma que `--verificar-cadeia` aponta a primeira divergência (`seq=8: hash não bate`). Sem esse
teste, a cadeia de hash seria decoração. Entrou em `docs/demo-profissional.md` como a resposta a
"como vocês provam o que o agente fez?" — é onde ele vale mais.

## PR #89 (#84) — resultados consolidados · **aprovado, 1 pedido**

`scripts/gerar_resultados.py` gera `docs/resultados.md` a partir dos CSVs, cada número com
arquivo + data. A decisão de usar a **data-base das fontes** em vez de `datetime.now()` é a certa e
é o que torna a saída determinística (teste compara byte a byte em duas execuções). Onde o dado não
existe de forma estruturada (trechos MT de Ipanema), deixa em branco e registra a limitação em vez
de inferir — exatamente o comportamento desejado.

### Pedido — o agrupamento por "família" esconde o modo

A linha **`gemini-hard-k5`** da tabela reporta `pass@1 hard 100 %`, mas a fonte é
`...-hard-k5-sem-exemplos.csv`: o arquivo mais recente da família venceu, e o modo **sem exemplos**
— que não é a configuração padrão — ficou rotulado com o nome genérico. Quem lê a tabela conclui que
o Gemini acerta 100 % nas *hard* na configuração do produto, quando na configuração padrão são 85 %.
Pedido: a chave de família precisa incluir o modo (`-sem-exemplos`, `-sem-compactar`) e a tabela
precisa de uma coluna **modo**, com a configuração padrão marcada.

## O que ficou pendente da rodada

- Os 3 pedidos acima (dois em `bench.md`/`resultados.md`, um no script de consolidação).
- Do lado de fora do código: perguntas à Light (`FAS_CON = AN`, `RAMLIG` > 300 m, trecho `11051956`),
  Manual da BDGD para `COR_NOM`, `gh secret set` das duas chaves para o job `llm-smoke`, `gifski`.
