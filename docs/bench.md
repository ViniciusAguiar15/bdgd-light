# Benchmark do agente (`bdgd-light bench`, issues #36 e #52)

Mede, no estilo do PowerChain (arXiv 2508.17094), se o agente do COD **acerta** (resposta numérica ou
proposta de manobra), se **segue a sequência certa de ferramentas** e **quanto custa** (tokens por
acerto, tempo), comparando provedores (OpenAI × Gemini × operador fake) e modos (com/sem exemplos
anotados, com/sem compactação dos retornos). Tudo roda sobre os clusters da demo
([`docs/escopo-cidade.md`](escopo-cidade.md) v3) com o gêmeo OpenDSS de verdade — nada é simulado
no benchmark além do próprio evento de falta.

## Tarefas (`bench/tarefas.yaml`)

34 tarefas (10 *simple*, 13 *medium*, 11 *hard*) distribuídas entre Tijuca (ALC9925, ALC9946,
URG29983, RCP9882), Ipanema (PTS0001, PTS9088, PTS9924, PTS4022) e Taquara (TQR0007, TQR33859,
TQR33862 — regressão):

| nível | o que exige | ferramentas de referência | exemplos |
|---|---|---|---|
| **simple** (S01–S10) | ler uma grandeza de um alimentador | `get_topology` | km de rede MT do ALC9925 (4,246); UCBT do RCP9882 (5.824); chaves NA do PTS0001 (31); trafos do TQR0007 (82) |
| **medium** (M01–M13) | uma chave ou uma falta já registrada: clientes a jusante, zona de falta, fronteira, isolamento — e dois **eventos sem manobra** (chave indisponível, falta transitória) | `downstream_customers`; `locate_fault` [→ `isolate_fault`]; nenhuma (eventos) | UCBT a jusante da 1006470683 (1.307); nós da zona da falta 11304252 (35); UCBT que continuam sem tensão após isolar 11798327 e religar (2.023); religador do PTS9088 sem telecomando → 1.816 UCBT dependem de equipe |
| **hard** (H01–H11) | restauração com o gêmeo: opções viáveis, margem, clientes recuperados — e quatro **eventos completos** que terminam em `propose_plan` | `locate_fault → isolate_fault → restore_options(score) [→ propose_plan]` | margem da melhor opção em Tijuca (45,98 %); opções viáveis (4); Ipanema sem opção (∅, 479 UCBT ficam sem tensão); Taquara com 10 equivalentes; ponta do PTS9924 (proposta sem chave) |

Cada tarefa tem `id, nivel, cluster`, uma `pergunta` **ou** um `evento` (`falta_permanente` e
`falta_transitoria` com o `falta` — trecho — que o simulador injeta; `chave_indisponivel` com a
`chave`), a `referencia` (ferramentas na ordem esperada; vazia = nenhuma necessária), o
`gabarito` (ferramenta + argumentos + `campo` lido do retorno, com caminhos `a.b[0].c` e
`len(...)`) e `verificar: resposta | proposta | sem_manobra`. O valor `esperado` gravado no YAML é
**documental** (BDGD 2023 do recorte): o gabarito real é **recalculado em tempo de execução**
pelas próprias ferramentas da sessão, com a mesma falta injetada que o agente verá —
`uv run bdgd-light bench --gabarito` recalcula os 34 e acusa divergências (assim uma BDGD nova ou
um recorte diferente não invalidam o arquivo silenciosamente).

As quatro tarefas de Ipanema acrescentadas pela issue #52 (M11–M13, H11) exploram o que a rede
subterrânea tem de diferente — **nenhuma NA de campo** (as 31 NA do PTS0001 são de pátio de SE):
clientes a jusante de uma NF do PTS9088 (271); o religador telecomandado 10934177 do PTS9088
**indisponível** (1.816 UCBT passam a depender de equipe; nenhuma manobra); falta **transitória**
no tronco do PTS0001 (o religador 10933610 religa; 1.730 UCBT no tempo morto; nenhuma manobra);
e uma falta permanente na ponta do PTS9924 (zona de 163 UCBT a jusante da 449470191): isolar e
religar devolve os 1.011 restantes e não há chave para propor — proposta **sem chave**.

Para as tarefas de proposta o gabarito `melhor_opcao` é o **conjunto** de chaves eletricamente
equivalentes à melhor opção de `restore_options`: viáveis, mesmos clientes recuperados e margem do
disjuntor a menos de 2 p.p. da maior — o mesmo empate que o verificador tolera. Em Taquara as 10
opções são equivalentes (61–62 %), em Tijuca duas (974020904 e 529355823 → ALC9946), em Ipanema o
conjunto é vazio e a proposta certa é **sem chave** (isolar e despachar).

### Critério de acerto

- **resposta**: algum número da resposta final (formatos pt-BR: `4.036`, `45,98 %`, `1.234,5`)
  bate com o gabarito — contagens inteiras exigem o valor exato (±0,5); grandezas fracionárias
  aceitam ±2 % (ou o `tolerancia_abs`/`tolerancia_rel` da tarefa); `escala` aceita a fração e o
  percentual (0,46 ou 46 %). É o critério que pontua a observação da revisão
  ([`docs/review/RESULTADOS-OPENAI.md`](review/RESULTADOS-OPENAI.md)): um resumo que cite "1.730
  clientes" quando a ferramenta devolveu 479 **erra** a tarefa mesmo com a proposta certa.
- **proposta**: a chave de `Execucao.proposta` pertence ao conjunto do gabarito (ou não há chave
  quando o conjunto é vazio). A proposta só existe se o verificador aprovou — recusas e
  replanejamentos aparecem nas colunas `recusas`/`replanejamentos` do CSV.
- **sem_manobra** (eventos `falta_transitoria` e `chave_indisponivel`): **erra** se o agente criou
  proposta ou chamou `propose_plan`/`set_switch`/`inject_fault`; fora isso vale o critério
  **resposta** com o gabarito do evento (clientes sem tensão no tempo morto; clientes a jusante da
  chave indisponível). Consultar ferramentas é permitido, mas como a `referencia` é vazia cada
  chamada derruba a **precisão** (o número já vem nos detalhes do evento). A regra 7 do prompt
  (número explícito na resposta final) nasceu daqui e de H09/H03.

### Métricas

| métrica | definição |
|---|---|
| **pass@1** | fração de execuções certas (por nível e total) |
| **pass@k** | estimador não enviesado do Codex, `1 − C(n−c, k)/C(n, k)`, por tarefa (n execuções, c acertos), média entre tarefas; com n < k usa k = n |
| **ordem** | LCS(sequência executada, referência) / len(referência) — quanto da sequência certa apareceu, na ordem |
| **precisão** | LCS / len(sequência executada) — quanto do que o agente chamou era necessário (penaliza chamadas supérfluas) |
| **tokens/pass@1** | tokens médios por execução ÷ pass@1 — custo por acerto (PowerChain); `tokens médios` inclui as rodadas todas de uma execução |
| **US$/exec.** | custo estimado por execução: tokens informados pelo provedor × **preço de lista** do modelo (`bench.PRECOS_USD_MILHAO`: entrada e saída por milhão; raciocínio conta como saída; sem cache nem lote). Leitura de ordem de grandeza para a apresentação, não fatura — o `.md` de cada rodada registra o preço usado |
| **chars ferr.** | caracteres de JSON das respostas de ferramenta enviadas ao modelo — proxy de custo que existe também para o fake (0 tokens) e mede a compactação |
| **s/exec.** | segundos por execução (LLM + ferramentas; o gêmeo OpenDSS domina nas *hard*) |

## Como rodar

```bash
uv sync --extra dev --extra twin --extra agent
uv run bdgd-light bench --gabarito                                   # confere os 34 gabaritos (sem LLM, ~3 min)
uv run bdgd-light bench --provider fake --k 5 --seed 42              # baseline determinístico: 170 execuções
uv run bdgd-light bench --provider fake --k 5 --seed 42 --sem-compactar   # custo sem compactação (chars ferr.)
uv run bdgd-light bench --provider fake --k 5 --seed 42 --sem-exemplos    # sem exemplos anotados (top-k 0)
uv run bdgd-light bench --provider gemini --nivel hard --k 5 --seed 42           # GEMINI_API_KEY; ~18 min, ~US$ 0,50
uv run bdgd-light bench --provider gemini --nivel simple,medium --k 3 --seed 42 --acrescentar   # acumula no CSV do dia
uv run bdgd-light bench --provider gemini --k 2 --seed 42 --sem-exemplos          # A/B dos exemplos anotados
uv run bdgd-light bench --provider gemini --k 2 --seed 42 --sem-compactar         # A/B da compactação
uv run bdgd-light bench --provider openai --k 5 --seed 42            # OPENAI_API_KEY no ambiente
```

Opções: `--provider fake|openai|gemini|ollama`, `--modelo`, `--k` (do pass@k) e `--n` (repetições;
padrão k), `--seed` (ordem das execuções, semente do simulador e, no OpenAI, o parâmetro `seed`
da API), `--nivel`/`--ids`/`--cluster` (filtros), `--sem-exemplos`, `--sem-compactar`,
`--sem-score`, `--top-k`, `--max-rodadas`, `--replanejar`, `--gabarito`, `--saida docs/bench`,
`--acrescentar`, `--sem-relatorio`, `--json`, `--feeders`, `--dss-out`, `--estado data/bench/estado`
(auditoria própria, separada da sessão de demo), `--dia/--mes`.

Saída: `docs/bench/<AAAA-MM-DD>-<provedor>[-sem-exemplos][-sem-compactar].csv` (uma linha por
execução: acerto, obtido, esperado, sequência, referência, ordem, precisão, rodadas, tokens,
chars, tempos, recusas, replanejamentos, erro, resposta truncada, modelo, semente) e `.md` (métricas
por nível, por tarefa, erros e o **comparativo** com o CSV mais recente de cada provedor·modo da
pasta). Reprodutibilidade: mesma semente → mesma ordem e mesmas faltas; o fake é determinístico; nos
modelos reais a semente reduz mas não elimina a variação (o Gemini não expõe `seed`).

O CI roda o harness com o operador fake sobre o cluster de teste (`tests/fixtures/bench_mini.yaml`,
12 tarefas nos três níveis, inclusive um evento `chave_indisponivel` e um `falta_transitoria`;
`tests/test_bench.py`): pass@1 = 100 % em todas é pré-condição para o arquivo de tarefas real
fazer sentido.

## Resultados (2026-09-11, BDGD 2023, 34 tarefas — PR da issue #52)

Ambiente: macOS arm64, `uv run bdgd-light bench --seed 42`, gêmeo OpenDSS (`opendssdirect`),
recortes `data/feeders/cluster_*` da BDGD 2023, `gemini-2.5-flash` pelo endpoint compatível.
Relatórios completos (por nível, por tarefa, erros, comparativo) em [`docs/bench/`](bench/):
`2026-09-11-fake*.md` (k=5, 170 execuções cada) e `2026-09-11-gemini*.md`. Os de 2026-09-10 (30
tarefas, rodada da PR #36) ficam como histórico; o comparativo usa só o CSV mais recente de cada
provedor·modo. Custo total da noite em Gemini: 284 execuções, 3,9 M tokens, **US$ 1,69**.

### Comparativo

| provedor · modo | modelo | exec. | pass@1 simple | pass@1 medium | pass@1 hard | pass@1 total | pass@k total | ordem | precisão | tokens/exec. | **US$/exec.** | chars ferr./exec. | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fake | fake-operador | 170 (k=5) | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0 | — | 1.806 | 2,3 |
| fake · sem compactar | fake-operador | 170 (k=5) | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0 | — | 6.352 | 2,1 |
| fake · sem exemplos | fake-operador | 170 (k=5) | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0 | — | 1.806 | 1,9 |
| **gemini** (exemplos + compactação) | gemini-2.5-flash | 124 (k=3 simple/medium, **k=5 hard**) | 100 % | 100 % | 85 % | 94 % | **100 %** | 95 % | 99 % | 11.557 | **0,0051** | 2.366 | 8,6 |
| gemini · sem exemplos | gemini-2.5-flash | 68 (k=2) | 100 % | 100 % | 95 % | 99 % | 100 % | 98 % | 96 % | 9.290 | 0,0044 | 2.244 | 8,1 |
| gemini · sem compactar | gemini-2.5-flash | 68 (k=2) | 100 % | 100 % | 91 % | 97 % | 100 % | 96 % | 100 % | 18.858 | 0,0071 | 9.236 | 7,2 |
| openai | gpt-4.1-mini | — | — | — | — | — | — | — | — | — | — | — | — |

Por nível, Gemini com exemplos e compactação (a configuração padrão do agente):

| nível | exec. | pass@1 | pass@k | tokens/exec. | US$/exec. | s/exec. | erros |
|---|---|---|---|---|---|---|---|
| simple | 30 (k=3) | 30/30 | 100 % | 5.830 | 0,0021 | 1,9 | — |
| medium | 39 (k=3) | 39/39 | 100 % | 5.135 | 0,0019 | 2,0 | — |
| hard | 55 (k=5) | 47/55 = 85 % | 100 % (pass@5) | 19.234 | 0,0090 | 16,9 | 8 × `MALFORMED_FUNCTION_CALL` |

### Leitura para a apresentação

1. **Acerto.** O Gemini 2.5 Flash acertou **todas** as execuções que chegaram a uma resposta: 30/30
   *simple*, 39/39 *medium* (inclusive as 4 tarefas novas de Ipanema: 271 UCBT a jusante da
   504519384, chave 10934177 indisponível → 1.816, falta transitória → 1.730, ponta do PTS9924 →
   proposta sem chave 5/5) e 47/47 *hard* com resposta — inclusive H09 5/5 ("existem 10 opções"),
   que na rodada de 2026-09-10 errou 1 de 2 por resposta implícita e motivou a **regra 7** do
   prompt (número explícito), e H07 5/5 (479, o número que o gpt-4.1-mini trocou pelo total do
   CTMT). Os 8 erros das *hard* (15 %) são todos de infraestrutura — abaixo — e pass@5 = 100 % em
   todas as tarefas.
2. **Custo.** Uma execução *simple*/*medium* custa **US$ 0,002**; uma *hard* completa (falta →
   isolamento → score elétrico → proposta, ~19 k tokens, 4,4 rodadas) **US$ 0,009** — o evento
   inteiro da demo sai por menos de um centavo de dólar; o tempo (17 s) é dominado pelo gêmeo
   OpenDSS pontuando as opções, não pelo modelo (~2 s por rodada). Um dia de COD com 100 eventos
   ficaria em ~US$ 1 no Flash; no `gpt-4.1-mini` (US$ 0,40/1,60 por M) o cenário de Tijuca custa
   ~US$ 0,014 com os 32,7 k tokens medidos pelo mantenedor em `docs/agent.md`.
3. **Compactação dos retornos (PR-14): metade dos tokens nas *hard*, mesmo acerto.** Sem
   compactar, os JSON de ferramenta passam de 2,4 k para 9,2 k caracteres por execução (nas *hard*
   de 4,2 k para 15,8 k) e as *hard* vão de 19 k para **40 k tokens** (−52 % com compactação;
   US$ 0,0157 → 0,0090, −43 %); nas *simple* 11,1 k → 5,8 k (−47 %), nas *medium* 6,8 k → 5,1 k
   (−25 %). Acerto e ordem não mudam (precisão até sobe a 100 %) — é ganho puro de custo, e afasta
   o contexto de qualquer limite prático.
4. **Exemplos anotados: para o Gemini 2.5 Flash, não compram acerto.** Sem os 3 exemplos por
   afinidade a execução gasta ~550 tokens a menos nas *simple* (−9 %) e ~1,7 k nas *hard* (−7 %),
   o acerto fica igual (67/68; o único erro foi um `ReadTimeout` de 60 s da API) e a ordem sobe
   (98 % vs 95 %: com exemplos o modelo pulou `locate_fault` e chamou `isolate_fault` direto nas 6
   execuções de M07 e M09 — resposta certa, ordem 50 %; sem exemplos, 1 vez) — mas a precisão cai
   (96 % vs 99 %: em 4 das 22 *hard* ele fez `propose_plan` quando a pergunta só pedia um número;
   precisão *hard* 91 %). Os exemplos, portanto, servem hoje para **conter** o modelo (não propor
   sem pedido), não para ensiná-lo a sequência — que o prompt de regras já ensina. Com o Flash o
   custo dos exemplos (US$ 0,0002–0,0005/exec.) é irrelevante; a decisão fica para o OpenAI e para
   modelos menores (Ollama).
5. **O erro que restou é do provedor, não do agente.** Todos os 8 erros *hard* da configuração
   padrão (e os 2 da rodada sem compactar) são `finish_reason = function_call_filter:
   MALFORMED_FUNCTION_CALL` do Gemini na chamada seguinte a `isolate_fault` (a de
   `restore_options(score=true)`), com as 3 tentativas do cliente falhando igual — tokens cobrados
   (~3,5 k por tentativa), resposta nenhuma. Taxa de 15 % nas *hard* com exemplos (8/55), 9 % sem
   compactar (2/22) e **0/22 sem exemplos** — o prompt com exemplos é o único fator comum aos
   casos com erro (p ≈ 0,03 para 0/22 se a taxa fosse 15 %), o que aponta para o modelo imitar o
   formato textual dos exemplos (`restore_options(score=true)`) na hora de montar a chamada. É a
   sugestão da rodada de 2026-09-10 (compactação) revista com mais dados: a compactação não é a
   causa. Mitigação aplicada: o pedido repetido após resposta vazia sobe a temperatura (0 → 0,5 →
   1,0) além do lembrete — a temperatura 0 tende a reproduzir a mesma chamada malformada; numa
   validação de 24 execuções nas 6 tarefas que falharam (H01, H02, H04, H06, H08, H10, k=4, com
   exemplos) sobrou **1 erro (4 %)** contra 15 % — melhora, mas com n pequeno; a tentativa repetida
   ainda falhou nesse caso. Próximo passo é a comparação k=5 *hard* sem exemplos (pendências).
6. **Sem manobra é tão importante quanto manobrar.** Nos dois eventos novos (`chave_indisponivel`,
   `falta_transitoria`) o agente não propôs nada em nenhuma das 14 execuções do Gemini (nem nas 30
   do fake) e citou o número certo de clientes; numa execução de M12 o Gemini consultou
   `get_switch_state` antes de responder — permitido, mas conta contra a precisão (a referência é
   vazia).

### O que o benchmark encontrou (e mudou no código)

Rodada de 2026-09-11 (issue #52):

1. **Regra 7 do prompt** (`agent/orquestrador.py`): a resposta final tem de trazer o número
   pedido explicitamente, na unidade pedida — H09 ("a melhor e outras 9") e a observação do
   mantenedor sobre o gpt-4.1-mini no Ipanema (1.730 no lugar de 479). H09 passou de 1/2 para 5/5
   e o gabarito de H07 (479) acertou 5/5.
2. **Eventos sem manobra no harness**: `evento: falta_transitoria | chave_indisponivel`,
   `verificar: sem_manobra`, `referencia: []`; o simulador anexa `clientes_a_jusante` ao evento de
   chave indisponível para o agente (e o gabarito) terem o número sem precisar de ferramenta.
3. **Custo em US$** (`bench.PRECOS_USD_MILHAO`, `custo_usd`): coluna `US$/exec.` no CSV/relatório
   e no comparativo, preço de lista por prefixo de modelo; execuções sem uso informado (timeout)
   contam zero. O `.md` de cada rodada registra o preço usado.
4. **Temperatura crescente nas repetições por resposta vazia** (`agent/llm.py`,
   `temperatura_da_tentativa`): item 5 acima.

Rodada de 2026-09-10 (PR #36), mantida como histórico:

1. **`MALFORMED_FUNCTION_CALL` do Gemini após `isolate_fault`.** Na primeira rodada *hard* (k=2,
   antes das correções) 6 de 20 execuções falharam com `finish_reason='function_call_filter:
   MALFORMED_FUNCTION_CALL'` (mensagem sem `content` nem `tool_calls`), sempre na chamada seguinte
   a `isolate_fault`, e as 3 tentativas do cliente repetiam o erro — pass@1 hard 65 %
   (`/tmp`-only, não versionado). Um lembrete extra no pedido repetido (`LEMBRETE_CHAMADA` em
   `agent/llm.py`) não resolveu (5/20). O A/B com `--sem-compactar` nas 5 tarefas afetadas deu
   **10/10**, apontando a compactação; a diferença relevante era `manobras`/`sequencia` virarem
   texto (`"abrir 479996584"`). Mantendo-as como objetos `{"acao", "chave"}` (`compactar._manobras`),
   as mesmas 5 tarefas com compactação deram **10/10** e a rodada *hard* completa passou a
   **19/20**, zero `MALFORMED_FUNCTION_CALL`. Custo: +~60 caracteres por retorno. *Revisto em
   2026-09-11*: com 55 + 22 + 22 execuções *hard* o erro voltou (8/55) também com compactação
   (2/22 sem compactar) e sumiu sem exemplos (0/22) — a amostra de 20 era pequena demais.
2. **Contabilidade de custo em execuções que falham.** Uma execução interrompida pelo provedor
   registrava `rodadas = 0` e `tokens = 0` — subestimando o custo por acerto. `conversar` agora
   anexa à exceção o parcial consumido (`ConversaParcial`: rodadas, usos — inclusive das
   tentativas falhas, que o Gemini cobra —, tempo) e o orquestrador o soma à `Execucao`.
3. **Resposta numérica errada com proposta certa** (observação da revisão): em H03 rep. 2 da
   rodada sem correções o Gemini respondeu "6 opções viáveis" quando `restore_options` devolveu
   4 — o critério `verificar: resposta` pega isso. Não se repetiu em 2026-09-11 (H03 5/5).
4. **Gabarito H08 (Taquara)**: as 10 opções de restauração são equivalentes (margens 60,8–62,0 %,
   mesmos 1.261 UCBT), então qualquer uma é acerto — o YAML documenta as 10 e o `melhor_opcao`
   recalcula o conjunto. Tolerância padrão passou a ser exata para contagens inteiras e ±2 % para
   grandezas fracionárias (o antigo ±2 % em contagens aceitaria 4.036 ≈ 4.100).

### Pendências

- **OpenAI não rodou nesta máquina** (sem `OPENAI_API_KEY` no ambiente do agente noturno, noites 2 e
  3). Comandos para o mantenedor, na ordem de custo (≈ US$ 0,10 + 0,15 + 0,30 nos preços de lista
  do `gpt-4.1-mini`): `uv run bdgd-light bench --provider openai --nivel simple --k 3 --seed 42`,
  depois `--nivel medium --k 3 --seed 42 --acrescentar` e `--nivel hard --k 3 --seed 42
  --acrescentar`; o comparativo e a coluna US$ saem sozinhos. Os 3 cenários do agente com OpenAI
  já estão em `docs/agent.md` (validação do mantenedor, 2026-09-10).
- Confirmar o efeito dos exemplos no `MALFORMED_FUNCTION_CALL`: `--provider gemini --nivel hard
  --k 5 --seed 42 --sem-exemplos` (55 execuções, ~US$ 0,55) contra os 8/55 com exemplos; se
  confirmar, o perfil `gemini` pode desligar os exemplos por padrão (ou trocar o formato textual
  `ferramenta(arg=…)` dos exemplos por uma lista) — decisão para o mantenedor.
- Tempo de resposta da API: um `ReadTimeout` de 60 s (H11, sem exemplos) — o cliente não repete em
  timeout; avaliar `timeout` maior ou repetição também nesse caso.
- Os preços em `PRECOS_USD_MILHAO` são de lista (Gemini conferido em 2026-09-11; OpenAI do
  lançamento dos modelos) — conferir antes da apresentação.
