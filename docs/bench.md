# Benchmark do agente (`bdgd-light bench`, issues #36, #52 e #82)

Mede, no estilo do PowerChain (arXiv 2508.17094), se o agente do COD **acerta** (resposta numérica ou
proposta de manobra), se **segue a sequência certa de ferramentas** e **quanto custa** (tokens por
acerto, tempo), comparando provedores (OpenAI × Gemini × operador fake) e modos (com/sem exemplos
anotados, com/sem compactação dos retornos). Tudo roda sobre os clusters da demo
([`docs/escopo-cidade.md`](escopo-cidade.md) v3) com o gêmeo OpenDSS de verdade — nada é simulado
no benchmark além do próprio evento de falta.

## Tarefas (`bench/tarefas.yaml`)

38 tarefas (10 *simple*, 13 *medium*, 15 *hard*) distribuídas entre Tijuca (ALC9925, ALC9946,
URG29983, RCP9882), Ipanema (PTS0001, PTS9088, PTS9924, PTS4022) e Taquara (TQR0007, TQR33859,
TQR33862 — regressão):

| nível | o que exige | ferramentas de referência | exemplos |
|---|---|---|---|
| **simple** (S01–S10) | ler uma grandeza de um alimentador | `get_topology` | km de rede MT do ALC9925 (4,246); UCBT do RCP9882 (5.824); chaves NA do PTS0001 (31); trafos do TQR0007 (82) |
| **medium** (M01–M13) | uma chave ou uma falta já registrada: clientes a jusante, zona de falta, fronteira, isolamento — e dois **eventos sem manobra** (chave indisponível, falta transitória) | `downstream_customers`; `locate_fault` [→ `isolate_fault`]; nenhuma (eventos) | UCBT a jusante da 1006470683 (1.307); nós da zona da falta 11304252 (35); UCBT que continuam sem tensão após isolar 11798327 e religar (2.023); religador do PTS9088 sem telecomando → 1.816 UCBT dependem de equipe |
| **hard** (H01–H15) | restauração com o gêmeo: opções viáveis, margem, clientes recuperados — quatro **eventos completos** e um bloco **hard+** com restrição ativa, chave indisponível e replanejamento após rejeição | `locate_fault → isolate_fault → restore_options(score) [→ propose_plan]`; em H14–H15 a referência considera a rederivação completa da falta (`locate_fault → isolate_fault → restore_options(score) → propose_plan`) | margem da melhor opção em Tijuca (45,98 %); opções viáveis (4); Ipanema sem opção (∅, 479 UCBT ficam sem tensão); Taquara com 10 equivalentes; H12–H15 estressam escolha/ordem sob restrição |

Cada tarefa tem `id, nivel, cluster`, uma `pergunta` **ou** um `evento` (`falta_permanente` e
`falta_transitoria` com o `falta` — trecho — que o simulador injeta; `chave_indisponivel` com a
`chave`), a `referencia` (ferramentas na ordem esperada; vazia = nenhuma necessária), o
`gabarito` (ferramenta + argumentos + `campo` lido do retorno, com caminhos `a.b[0].c` e
`len(...)`) e `verificar: resposta | proposta | sem_manobra`. As tarefas *hard+* também podem
trazer precondições: `restricoes` (estado persistente da issue #61), `indisponiveis` (chaves fora
de operação) e `rejeicao_previa` (a sessão nasce de uma proposta já rejeitada, e o benchmark mede
o replanejamento). O valor `esperado` gravado no YAML é **documental** (BDGD 2023 do recorte): o
gabarito real é **recalculado em tempo de execução** pelas próprias ferramentas da sessão, com a
mesma falta e as mesmas precondições que o agente verá — `uv run bdgd-light bench --gabarito`
recalcula os 38 e acusa divergências (assim uma BDGD nova ou um recorte diferente não invalidam o
arquivo silenciosamente).

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
| **ordem** | LCS(sequência executada, referência) / len(referência) — quanto da sequência certa apareceu, na ordem; nas tabelas abaixo a fração entre parênteses agrega **passos em ordem / passos de referência** |
| **precisão** | LCS / len(sequência executada) — quanto do que o agente chamou era necessário (penaliza chamadas supérfluas); nas tabelas abaixo a fração entre parênteses agrega **passos em ordem / chamadas feitas** |
| **ferr. desnec.** | `len(sequência) − LCS` — número médio de chamadas fora da subsequência de referência |
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
execução: acerto, obtido, esperado, sequência, referência, ordem, precisão, chamadas
desnecessárias, rodadas, tokens, chars, tempos, recusas, replanejamentos, erro, resposta truncada,
modelo, semente) e `.md` (métricas
por nível, por tarefa, erros e o **comparativo** com o CSV mais recente de cada provedor·modo da
pasta). Reprodutibilidade: mesma semente → mesma ordem e mesmas faltas; o fake é determinístico; nos
modelos reais a semente reduz mas não elimina a variação (o Gemini não expõe `seed`).

O CI roda o harness com o operador fake sobre o cluster de teste (`tests/fixtures/bench_mini.yaml`,
13 tarefas nos três níveis, inclusive um evento `chave_indisponivel`, um `falta_transitoria` e um
caso de `rejeicao_previa`;
`tests/test_bench.py`): pass@1 = 100 % em todas é pré-condição para o arquivo de tarefas real
fazer sentido.

## Resultados (2026-09-11, BDGD 2023, 34 tarefas — PR da issue #52)

Ambiente: macOS arm64, `uv run bdgd-light bench --seed 42`, gêmeo OpenDSS (`opendssdirect`),
recortes `data/feeders/cluster_*` da BDGD 2023, `gemini-2.5-flash` pelo endpoint compatível.
Relatórios completos (por nível, por tarefa, erros, comparativo) em [`docs/bench/`](bench/):
`2026-09-11-fake*.md` (k=5, 170 execuções cada) e `2026-09-11-gemini*.md`. Os de 2026-09-10 (30
tarefas, rodada da PR #36) ficam como histórico; o comparativo usa só o CSV mais recente de cada
provedor·modo. Custo total da noite em Gemini: 284 execuções, 3,9 M tokens, **US$ 1,69**.
Na demo ao vivo, porém, o padrão atual do `cliente_do_ambiente()` é **OpenAI**: sem
`BDGD_LLM_PROVIDER`/`BDGD_LLM_ENDPOINT`, com `OPENAI_API_KEY` e `GEMINI_API_KEY` presentes, a
resolução para em `OPENAI_API_KEY`.

### Comparativo

| provedor · modo | modelo | exec. | pass@1 simple | pass@1 medium | pass@1 hard | pass@1 total | pass@k total | ordem | precisão | tokens/exec. | **US$/exec.** | chars ferr./exec. | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fake | fake-operador | 170 (k=5) | 100 % | 100 % | 100 % | 100 % | 100 % | 100,0 % (310/310) | 100,0 % (310/310) | 0 | — | 1.806 | 2,3 |
| fake · sem compactar | fake-operador | 170 (k=5) | 100 % | 100 % | 100 % | 100 % | 100 % | 100,0 % (310/310) | 100,0 % (310/310) | 0 | — | 6.352 | 2,1 |
| fake · sem exemplos | fake-operador | 170 (k=5) | 100 % | 100 % | 100 % | 100 % | 100 % | 100,0 % (310/310) | 100,0 % (310/310) | 0 | — | 1.806 | 1,9 |
| **gemini** (exemplos + compactação) | gemini-2.5-flash | 124 (k=3 simple/medium, **k=5 hard**) | 100 % | 100 % | 85 % | 94 % | **100 %** | 94,8 % (245/264) | 98,8 % (245/248) | 11.557 | **0,0051** | 2.366 | 8,6 |
| gemini · sem exemplos | gemini-2.5-flash | 68 (k=2) | 100 % | 100 % | 95 % | 99 % | 100 % | 97,8 % (119/124) | 95,6 % (119/125) | 9.290 | 0,0044 | 2.244 | 8,1 |
| gemini · sem compactar | gemini-2.5-flash | 68 (k=2) | 100 % | 100 % | 91 % | 97 % | 100 % | 95,6 % (116/124) | 100,0 % (116/116) | 18.858 | 0,0071 | 9.236 | 7,2 |
| **openai** | gpt-4.1-mini-2025-04-14 | 102 (k=3) | 100 % | 85 % | 100 % | 94 % | 94 % | 98,5 % (183/186) | 95,1 % (183/193) | 9.556 | **0,0041** | 5.687 | 8,4 |

Por nível, Gemini com exemplos e compactação (a configuração padrão do agente):

| nível | exec. | pass@1 | pass@k | tokens/exec. | US$/exec. | s/exec. | erros |
|---|---|---|---|---|---|---|---|
| simple | 30 (k=3) | 30/30 | 100 % | 5.830 | 0,0021 | 1,9 | — |
| medium | 39 (k=3) | 39/39 | 100 % | 5.135 | 0,0019 | 2,0 | — |
| hard | 55 (k=5) | 47/55 = 85 % | 100 % (pass@5) | 19.234 | 0,0090 | 16,9 | 8 × `MALFORMED_FUNCTION_CALL` |

Os 3 **cenários ponta a ponta** também foram rerodados localmente com OpenAI via
`zsh -lic 'uv run bdgd-light agente --cenario ... --provider openai'`:
Tijuca (`tijuca_cabofrio_tronco`) em 4 rodadas / 25.841 tokens / ~US$ 0,011, mesma proposta de
fechar `974020904`; Ipanema (`ipanema_9210`) em 4 rodadas / 13.274 tokens / ~US$ 0,0058,
reconhecendo corretamente o caso **sem chave**; Taquara (`taquara_bocari`) em 4 rodadas / 33.316
tokens / ~US$ 0,0139, com chave equivalente `11056672` para `TQR33859`. Em todos: 0 recusas, 0
replanejamentos e verificador aprovado.

### A/B dos exemplos anotados (*hard*, k=5)

Relatórios versionados desta rodada: `docs/bench/2026-09-11-gemini-hard-k5-sem-exemplos.*`,
`docs/bench/2026-09-11-openai-hard-k5.*` e
`docs/bench/2026-09-11-openai-hard-k5-sem-exemplos.*`. O braço Gemini **com** exemplos já estava
em `docs/bench/2026-09-11-gemini.md` (55 execuções *hard*).

| provedor | modo | n | pass@1 *hard* | erros | `MALFORMED_FUNCTION_CALL` | tokens/exec. | US$/exec. | s/exec. |
|---|---|---|---|---|---|---|---|---|
| Gemini 2.5 Flash | com exemplos | 55 | 47/55 = 85 % | 8 | 8/55 = 15 % | 19.234 | 0,0090 | 16,9 |
| Gemini 2.5 Flash | sem exemplos | 55 | **55/55 = 100 %** | 0 | **0/55** | 25.401 | 0,0118 | 17,8 |
| gpt-4.1-mini | com exemplos | 55 | 55/55 = 100 % | 0 | 0/55 | 18.897 | 0,0081 | 18,7 |
| gpt-4.1-mini | sem exemplos | 55 | 55/55 = 100 % | 0 | 0/55 | 17.714 | 0,0075 | 16,4 |

Conclusão daquela rodada: com **n = 55 por braço**, o gatilho é o texto dos exemplos, mas **só no Gemini Flash**:
dentro do mesmo provedor, mesma seed e mesmo n, o braço com exemplos fica em **47/55** e o sem
exemplos em **55/55**, enquanto no `gpt-4.1-mini` o mesmo prompt fica em **55/55** com e sem
exemplos e nunca produz a chamada malformada. Logo, não há evidência de que exemplos anotados
degradem o planejamento em geral — há um parser de *tool call* do Gemini Flash que quebra com esse
formato textual. Por isso, **não** vale desligá-los por padrão sem uma decisão específica para o
perfil Gemini (ou uma mudança no formato textual dos exemplos).
Naquela rodada, o benchmark media se os exemplos **custavam** acerto; ele **não** media se os exemplos **rendiam**
acerto, porque não há aqui um braço com n comparável que isole eventual ganho de ordenação/precisão
atribuível aos exemplos. Portanto, ela não confirma nem refuta a premissa do PowerChain de que
pares tarefa↔workflow anotados ajudam; mostra apenas que, no provedor padrão da demo, eles não
custam acerto e saem ~6 % mais baratos.

### Ganho dos exemplos anotados (*OpenAI*, issue #82)

Para fechar a lacuna acima sem repetir 110 chamadas reais desnecessárias, reutilizei os dois
relatórios *hard* já versionados e comparáveis do OpenAI
(`docs/bench/2026-09-11-openai-hard-k5.*` e
`docs/bench/2026-09-11-openai-hard-k5-sem-exemplos.*`: **n = 55 por braço**, mesmo modelo,
mesmo recorte, mesma configuração e mesma semente efetiva `None`). Como o `pass@1` saturou em
**100 % nos dois braços**, segui a opção **(a)** do backlog e acrescentei um conjunto **hard+**
exploratório de 4 tarefas, com **k = n = 3** e `seed = 42`, versionado em
`docs/bench/2026-09-11-openai-hardplus-k3.*` e
`docs/bench/2026-09-11-openai-hardplus-k3-sem-exemplos.*`.

Reabrindo os CSVs H12–H15, a maior parte da queda original de precisão no *hard+* apareceu como
artefato do gabarito de referência, não como desperdício real do agente. Nos dois casos de
**rejeição prévia** (H14–H15), as 6 execuções rederivam a mesma cadeia
`locate_fault → isolate_fault → restore_options → propose_plan` antes de propor a alternativa
restante. Isso é coerente com o prompt de replanejamento (`EVENTO` + `REJEICAO_HUMANA` + proposta
anterior) e com o fato de a sessão não injetar no contexto o cache das chamadas anteriores; o
agente recebe a falta registrada e a proposta rejeitada, mas não uma garantia de que a localização
e o isolamento já estejam “materializados” na conversa corrente. Por isso, corrigi a
`referencia` de H14 e H15 em `bench/tarefas.yaml` para aceitar a rederivação completa. A tabela
abaixo já reflete essa leitura corrigida; os CSVs versionados mantêm a métrica histórica da rodada.

Como o *hard+* foi construído:

- **H12 — restrição ativa:** parte do caso H01, mas a sessão já nasce com
  `restricoes = [{alimentadores_evitar: [ALC9946]}]`, forçando a restauração via RCP9882.
- **H13 — chave indisponível:** parte do caso H04, mas a única tie viável (`746851189`) entra em
  `indisponiveis`, então a resposta correta passa a ser proposta **sem chave**.
- **H14 — rejeição prévia com alternativa:** parte do caso H01, cria a proposta inicial, registra
  a rejeição `"a chave 974020904 está em manutenção"` e mede o replanejamento; o gabarito passa a
  ser `529355823`.
- **H15 — rejeição prévia sem alternativa:** parte do caso H04, rejeita a única tie viável pelo
  mesmo motivo de manutenção e mede o replanejamento até a proposta **sem chave**.

| recorte | modo | n | pass@1 | ordem | precisão | ferr. desnec./exec. | rodadas/exec. | tokens/exec. | US$/exec. |
|---|---|---|---|---|---|---|---|---|---|
| *hard* original | com exemplos | 55 | 55/55 = 100 % | **100,0 % (195/195)** | 97,3 % (195/201) | 0,11 | **3,64** | 18.897 | 0,0081 |
| *hard* original | sem exemplos | 55 | 55/55 = 100 % | 96,4 % (189/195) | **97,8 % (189/194)** | **0,09** | 3,87 | **17.714** | **0,0075** |
| *hard+* | com exemplos | 12 | 12/12 = 100 % | **100,0 % (48/48)** | 92,2 % (48/53) | 0,42 | **4,08** | **41.269** | **0,0172** |
| *hard+* | sem exemplos | 12 | 12/12 = 100 % | 95,8 % (46/48) | **94,2 % (46/49)** | **0,25** | 4,58 | 44.417 | 0,0184 |

Leitura honesta:

1. **No *hard* original, nenhum ganho detectável apesar de n=55.** `pass@1` saturou em 100 % nos
   dois braços; as métricas secundárias ficaram em direções diferentes: com exemplos a **ordem**
   ficou em **100,0 % (195/195)**, sem exemplos caiu para **96,4 % (189/195)**; em compensação, a
   **precisão** ficou ligeiramente melhor sem exemplos (**97,8 % = 189/194** contra
   **97,3 % = 195/201**), assim como **tokens** e **chamadas desnecessárias**. Isso continua
   compatível com efeito pequeno ou nulo nesse recorte, não com benefício claro.
2. **A maior parte da “queda para ~68 %” no *hard+* vinha do gabarito estreito de H14–H15.**
   Nas 6 execuções com rejeição prévia (3 em H14, 3 em H15), os dois braços repetem
   `locate_fault` + `isolate_fault` antes de `restore_options` e `propose_plan`. Como o prompt de
   replanejamento reapresenta o evento e a rejeição, mas não injeta o cache das ferramentas
   anteriores, tratei essa rederivação como **sequência válida** e atualizei o gabarito. Com isso,
   a **precisão** do *hard+* sobe para **92,2 % (48/53)** com exemplos e **94,2 % (46/49)** sem
   exemplos; as **chamadas desnecessárias** caem de **1,42/1,25** para **0,42/0,25** por execução.
3. **O resíduo real de desperdício ficou concentrado em H13.** Ali, o agente faz uma
   `propose_plan` extra em **6/6 execuções** antes de encerrar corretamente com proposta **sem
   chave**; em **1/3** das execuções com exemplos ainda entra um `get_topology` a mais, e em
   **2/3** das execuções sem exemplos ele pula `isolate_fault`, o que derruba a **ordem** para
   **83,3 % (10/12)** sem alterar o desfecho. Ou seja: o problema remanescente não é
   “replanejar de novo” em si, e sim insistir numa proposta intermediária onde a tie já nasce
   indisponível.
4. **Mesmo no *hard+* corrigido, os exemplos continuam sem vencedor claro.** Com exemplos, a
   **ordem** fica um pouco melhor e há menos **rodadas**; sem exemplos, a **precisão** residual e
   as **chamadas desnecessárias** ficam um pouco melhores. De novo, os sinais se cancelam.
5. **O padrão do agente não muda.** Não há evidência suficiente, no provedor padrão da demo, para
   ligar ou desligar exemplos anotados por padrão com base em “ganho de planejamento”.

O que **não** foi medido aqui: intervalo de confiança formal, poder estatístico para diferenças
pequenas (especialmente no *hard+*, onde **n = 12 por braço** é exploratório), outros provedores
além do OpenAI, e um *hard+* maior cobrindo mais combinações de restrição/fonte. A conclusão
correta, hoje, é: no OpenAI não apareceu **efeito consistente e detectável** dos exemplos nem no
*hard* original (n=55) nem no *hard+* exploratório (n=12).

### Leitura para a apresentação

1. **Acerto.** O Gemini 2.5 Flash acertou **todas** as execuções que chegaram a uma resposta: 30/30
   *simple*, 39/39 *medium* (inclusive as 4 tarefas novas de Ipanema: 271 UCBT a jusante da
   504519384, chave 10934177 indisponível → 1.816, falta transitória → 1.730, ponta do PTS9924 →
   proposta sem chave 5/5) e 47/47 *hard* com resposta — inclusive H09 5/5 ("existem 10 opções"),
   que na rodada de 2026-09-10 errou 1 de 2 por resposta implícita e motivou a **regra 7** do
   prompt (número explícito), e H07 5/5 (479, o número que o gpt-4.1-mini trocou pelo total do
   CTMT). Os 8 erros das *hard* (15 %) são todos de infraestrutura — abaixo — e pass@5 = 100 % em
   todas as tarefas.
2. **OpenAI fechou a lacuna do comparativo, mas revelou outro tipo de erro.** O
   `gpt-4.1-mini-2025-04-14` ficou em **94 %** no total sem nenhum erro de infraestrutura: 30/30
   *simple*, 33/39 *medium* e 33/33 *hard*. As 6 falhas são todas das duas perguntas *medium* que
   pedem o número de clientes que continuam sem tensão após o isolamento (M07 e M09): o modelo
   chamou a sequência certa, mas respondeu **zero** em Tijuca e **516** em Taquara, confundindo o
   total ainda desligado com outra grandeza do retorno. Em compensação, nas *hard* ele não exibiu
   o `MALFORMED_FUNCTION_CALL` do Gemini e entregou 100 % de pass@1.
3. **Custo.** Uma execução *simple*/*medium* custa **~US$ 0,002** nos dois provedores; uma *hard*
   completa custa **US$ 0,0090** no Gemini e **US$ 0,0083** no OpenAI. O evento inteiro da demo
   segue abaixo de um centavo de dólar em ambos; o tempo é dominado pelo gêmeo OpenDSS, não pelo
   modelo. No agregado desta rodada, o OpenAI foi ligeiramente mais barato por execução
   (**US$ 0,0041** vs **US$ 0,0051**) porque consumiu menos tokens.
4. **Compactação dos retornos (PR-14): metade dos tokens nas *hard*, mesmo acerto.** Sem
   compactar, os JSON de ferramenta passam de 2,4 k para 9,2 k caracteres por execução (nas *hard*
   de 4,2 k para 15,8 k) e as *hard* vão de 19 k para **40 k tokens** (−52 % com compactação;
   US$ 0,0157 → 0,0090, −43 %); nas *simple* 11,1 k → 5,8 k (−47 %), nas *medium* 6,8 k → 5,1 k
   (−25 %). Acerto e ordem não mudam (precisão até sobe a 100 %) — é ganho puro de custo, e afasta
   o contexto de qualquer limite prático.
5. **Exemplos anotados: o efeito é uma interação entre exemplos e o parser do Gemini Flash.** No
   Gemini 2.5 Flash, tirar os exemplos zera o `MALFORMED_FUNCTION_CALL` nas *hard* (8/55 →
   **0/55**), mas o custo sobe (19,2 k → **25,4 k** tokens/exec.) e a precisão/ordem não melhoram
   o suficiente para justificar uma troca global. No OpenAI, com o mesmo recorte *hard* k=5, o
   acerto fica em **55/55** com e sem exemplos; sem exemplos ele só fica um pouco mais barato e
   rápido (18,9 k → 17,7 k tokens; US$ 0,0081 → 0,0075). A leitura correta, portanto, é: o texto
   dos exemplos é o gatilho do problema observado, mas o componente suscetível é o parser de
   *tool call* do Gemini Flash — não há evidência de degradação geral do planejamento.
6. **No estado atual, o erro remanescente é específico do provedor.** No Gemini, todos os 8 erros
   *hard* da configuração
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
   ainda falhou nesse caso. O A/B k=5 reforça que esse ruído vem do Gemini: no OpenAI o problema
   não é tool call malformada, e sim resposta final numérica em duas tarefas *medium* do benchmark
   completo.
7. **Sem manobra é tão importante quanto manobrar.** Nos dois eventos novos (`chave_indisponivel`,
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

- Avaliar uma mitigação **específica do perfil Gemini** para o `MALFORMED_FUNCTION_CALL`: manter os
  exemplos ligados, mas trocar o formato textual `ferramenta(arg=…)` por uma lista/JSON mais
  literal, ou desabilitá-los só no perfil `gemini` se a apresentação priorizar robustez acima de
  custo e explicabilidade.
- Tempo de resposta da API: um `ReadTimeout` de 60 s (H11, sem exemplos) — o cliente não repete em
  timeout; avaliar `timeout` maior ou repetição também nesse caso.
- Os preços em `PRECOS_USD_MILHAO` são de lista (Gemini conferido em 2026-09-11; OpenAI do
  lançamento dos modelos) — conferir antes da apresentação.

## Alimentadores fora dos três clusters (issue #92, 2026-09-12)

Objetivo desta rodada: medir se o **agente** decide bem em alimentadores que passaram na
generalização da issue #91, mas **fora** dos três clusters conhecidos da demo. Aqui o gabarito não
é imaginado nem copiado do YAML-base: ele foi **recalculado pelas próprias ferramentas** em cada
caso (`locate_fault → isolate_fault → restore_options(score=true)`), e o arquivo versionado de
referência da rodada é [`docs/bench/2026-09-11-fora-treino-casos.csv`](bench/2026-09-11-fora-treino-casos.csv),
gerado junto com [`bench/tarefas_fora_treino.yaml`](../bench/tarefas_fora_treino.yaml) pelo runner
`scripts/preparar_bench_fora_treino.py`.

Comandos usados:

```bash
uv run python scripts/preparar_bench_fora_treino.py
uv run bdgd-light bench --gabarito \
  --tarefas bench/tarefas_fora_treino.yaml \
  --feeders scratch/issue-92-fora-treino/feeders \
  --dss-out scratch/issue-92-fora-treino/dss \
  --estado scratch/issue-92-fora-treino/estado
zsh -lic 'uv run bdgd-light bench \
  --provider openai \
  --familia fora-treino-k3 \
  --k 3 \
  --seed 92 \
  --tarefas bench/tarefas_fora_treino.yaml \
  --feeders scratch/issue-92-fora-treino/feeders \
  --dss-out scratch/issue-92-fora-treino/dss \
  --estado scratch/issue-92-fora-treino/estado'
```

### Como os 10 alimentadores foram escolhidos

Regra de seleção, sem ajuste para “melhorar o número”: peguei os **10 primeiros CTMTs** da amostra
determinística da issue #91 (`docs/bench/2026-09-11-generalizacao.csv`), ordenados por
`ordem_sorteio`, desde que tivessem chegado com sucesso à etapa `restore_options`. Isso produz o
seguinte subconjunto versionado:

| ordem | CTMT | região | porte | tie(s) | opções | viáveis | falta determinística | gabarito real |
|---|---|---|---|---:|---:|---:|---|---|
| 1 | RCP33308 | Tijuca | G | 1 | 1 | 1 | `12320339` | `757513244` |
| 2 | SAT1960 | Centro | P | 0 | 0 | 0 | `12416163` | ∅ |
| 3 | CBI24982 | Méier | M | 5 | 0 | 0 | `23718413` | ∅ |
| 4 | AVD33625 | Barra/Recreio | P | 5 | 4 | 4 | `287306161` | `11138583` |
| 5 | ITP00005 | Barra/Recreio | M | 2 | 2 | 1 | `92794304` | `456765966` |
| 6 | PDG33010 | Jacarepaguá/Taquara | M | 7 | 7 | 5 | `12311381` | `11009531` |
| 7 | BPD9350 | Lapa/Glória | G | 0 | 0 | 0 | `32750469` | ∅ |
| 8 | COP2700 | Copacabana/Leme | M | 0 | 0 | 0 | `164481985` | ∅ |
| 9 | LBN00061 | Ipanema/Leblon | P | 0 | 0 | 0 | `294042270` | ∅ |
| 10 | PTS9310 | Ipanema/Leblon | G | 0 | 0 | 0 | `12827915` | ∅ |

Leitura do subconjunto:

- cobre **8 regiões** e os três portes (**P/M/G**);
- **5/10** casos têm ao menos uma tie ligada ao CTMT;
- só **4/10** têm alguma opção viável de restauração; nos outros **6/10** o desfecho correto é
  **proposta sem chave**.

### Resultado do OpenAI fora do treino

Relatório completo: [`docs/bench/2026-09-12-openai-fora-treino-k3.md`](bench/2026-09-12-openai-fora-treino-k3.md).

| recorte | tarefas | execuções | pass@1 | pass@k | ordem | precisão | ferr. desnec./exec. | rodadas/exec. | tokens/exec. | US$/exec. | taxa de reprovação do verificador |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fora do treino (`openai-fora-treino-k3`) | 10 | 30 | **27/30 = 90 %** | **90 % (pass@3)** | 97,5 % (117/120) | 100,0 % (117/117) | 0,00 | 4,30 | 20.897 | 0,0090 | **0/30 = 0 %** |

O erro ficou todo concentrado em **FT02 (SAT1960)**: nas **3/3 execuções** o modelo fez
`locate_fault → isolate_fault → restore_options`, viu corretamente que não havia opção viável, mas
**encerrou sem chamar `propose_plan`** para formalizar a proposta **sem chave**. Ou seja: a queda
de acerto aqui **não** veio de proposta insegura rejeitada pelo verificador; veio de um fechamento
incompleto justamente num caso “sem manobra”. A investigação desse sintoma ficou registrada na
follow-up **#104**, sem alterar o número desta rodada.

### Comparação com o recorte *hard* conhecido

**Não é A/B controlado.** O recorte conhecido
[`docs/bench/2026-09-11-openai-hard-k5.csv`](bench/2026-09-11-openai-hard-k5.csv) usa **11 tarefas
hard** escritas sobre os três clusters da demo, mistura perguntas numéricas com propostas e foi
rodado com **k=5**; a suíte fora do treino usa **10 tarefas hard de proposta**, todas derivadas da
amostra da issue #91, e foi rodada com **k=3**. A tabela abaixo serve só para leitura lado a lado:

| recorte | tarefas | execuções | pass@1 | ordem | precisão | ferr. desnec./exec. | tokens/exec. | US$/exec. | taxa de reprovação do verificador |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| *hard* conhecido (`openai-hard-k5`) | 11 | 55 | **100 %** | 100,0 % (195/195) | 97,3 % (195/201) | 0,11 | 18.897 | 0,0081 | **0/55 = 0 %** |
| fora do treino (`openai-fora-treino-k3`) | 10 | 30 | **90 %** | 97,5 % (117/120) | 100,0 % (117/117) | 0,00 | 20.897 | 0,0090 | **0/30 = 0 %** |

Leitura honesta:

1. **O desempenho caiu fora do treino.** O mesmo `gpt-4.1-mini-2025-04-14` que estava em
   **100 %** no recorte *hard* conhecido ficou em **90 %** aqui. Esse é o resultado principal da
   issue #92 e precisa ser dito com todas as letras.
2. **A queda não veio do verificador.** A taxa de reprovação do verificador ficou em **0 %** nos
   dois recortes. Logo, o problema fora do treino não foi “o modelo insistiu numa manobra errada e
   foi barrado”; foi “o modelo não fechou a proposta sem chave em um caso novo”.
3. **O custo também subiu.** Fora do treino, a execução média foi de **20.897 tokens** e
   **US$ 0,0090**, contra **18.897 tokens** e **US$ 0,0081** no *hard* conhecido.
4. **A dificuldade é diferente.** Nesta suíte, **6/10** tarefas corretas terminam em **∅ (sem
   chave)** e apenas **4/10** têm alguma opção viável de transferência; portanto, não faz sentido
   ler a diferença de 100 % → 90 % como um experimento controlado de causalidade.
