# Benchmark do agente (`bdgd-light bench`, issue #36)

Mede, no estilo do PowerChain (arXiv 2508.17094), se o agente do COD **acerta** (resposta numérica ou
proposta de manobra), se **segue a sequência certa de ferramentas** e **quanto custa** (tokens por
acerto, tempo), comparando provedores (OpenAI × Gemini × operador fake) e modos (com/sem exemplos
anotados, com/sem compactação dos retornos). Tudo roda sobre os clusters da demo
([`docs/escopo-cidade.md`](escopo-cidade.md) v3) com o gêmeo OpenDSS de verdade — nada é simulado
no benchmark além do próprio evento de falta.

## Tarefas (`bench/tarefas.yaml`)

30 tarefas, 10 por nível, distribuídas entre Tijuca (ALC9925, ALC9946, URG29983, RCP9882), Ipanema
(PTS0001, PTS9088, PTS9924, PTS4022) e Taquara (TQR0007, TQR33859, TQR33862 — regressão):

| nível | o que exige | ferramentas de referência | exemplos |
|---|---|---|---|
| **simple** (S01–S10) | ler uma grandeza de um alimentador | `get_topology` | km de rede MT do ALC9925 (4,246); UCBT do RCP9882 (5.824); chaves NA do PTS0001 (31); trafos do TQR0007 (82) |
| **medium** (M01–M10) | uma chave ou uma falta já registrada: clientes a jusante, zona de falta, fronteira, isolamento | `downstream_customers`; `locate_fault` [→ `isolate_fault`] | UCBT a jusante da 1006470683 (1.307); nós da zona da falta 11304252 (35); UCBT que continuam sem tensão após isolar 11798327 e religar (2.023) |
| **hard** (H01–H10) | restauração com o gêmeo: opções viáveis, margem, clientes recuperados — e três **eventos completos** que terminam em `propose_plan` | `locate_fault → isolate_fault → restore_options(score) [→ propose_plan]` | margem da melhor opção em Tijuca (45,98 %); opções viáveis (4); Ipanema sem opção (∅, 479 UCBT ficam sem tensão); Taquara com 10 equivalentes |

Cada tarefa tem `id, nivel, cluster`, uma `pergunta` **ou** um `evento: falta_permanente` (com o
`falta` — trecho — que o simulador injeta), a `referencia` (ferramentas na ordem esperada), o
`gabarito` (ferramenta + argumentos + `campo` lido do retorno, com caminhos `a.b[0].c` e
`len(...)`) e `verificar: resposta | proposta`. O valor `esperado` gravado no YAML é
**documental** (BDGD 2023 do recorte): o gabarito real é **recalculado em tempo de execução**
pelas próprias ferramentas da sessão, com a mesma falta injetada que o agente verá —
`uv run bdgd-light bench --gabarito` recalcula os 30 e acusa divergências (assim uma BDGD nova ou
um recorte diferente não invalidam o arquivo silenciosamente).

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

### Métricas

| métrica | definição |
|---|---|
| **pass@1** | fração de execuções certas (por nível e total) |
| **pass@k** | estimador não enviesado do Codex, `1 − C(n−c, k)/C(n, k)`, por tarefa (n execuções, c acertos), média entre tarefas; com n < k usa k = n |
| **ordem** | LCS(sequência executada, referência) / len(referência) — quanto da sequência certa apareceu, na ordem |
| **precisão** | LCS / len(sequência executada) — quanto do que o agente chamou era necessário (penaliza chamadas supérfluas) |
| **tokens/pass@1** | tokens médios por execução ÷ pass@1 — custo por acerto (PowerChain); `tokens médios` inclui as rodadas todas de uma execução |
| **chars ferr.** | caracteres de JSON das respostas de ferramenta enviadas ao modelo — proxy de custo que existe também para o fake (0 tokens) e mede a compactação |
| **s/exec.** | segundos por execução (LLM + ferramentas; o gêmeo OpenDSS domina nas *hard*) |

## Como rodar

```bash
uv sync --extra dev --extra twin --extra agent
uv run bdgd-light bench --gabarito                                   # confere os 30 gabaritos (sem LLM, ~3 min)
uv run bdgd-light bench --provider fake --k 5 --seed 42              # baseline determinístico: 150 execuções
uv run bdgd-light bench --provider fake --k 5 --seed 42 --sem-compactar   # custo sem compactação (chars ferr.)
uv run bdgd-light bench --provider fake --k 5 --seed 42 --sem-exemplos    # sem exemplos anotados (top-k 0)
uv run bdgd-light bench --provider gemini --nivel simple,medium --k 3 --seed 42
uv run bdgd-light bench --provider gemini --nivel hard --k 2 --seed 42 --acrescentar   # acumula no CSV do dia
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
10 tarefas nos três níveis, `tests/test_bench.py`): pass@1 = 100 % em todas é pré-condição para o
arquivo de tarefas real fazer sentido.

## Resultados (2026-09-10, BDGD 2023, commit da PR #36)

Ambiente: macOS arm64, `uv run bdgd-light bench` com `--seed 42`, gêmeo OpenDSS (`opendssdirect`),
recortes `data/feeders/cluster_*` da BDGD 2023. Relatórios completos (por nível, por tarefa, erros)
em [`docs/bench/`](bench/): `2026-09-10-fake*.md` e `2026-09-10-gemini.md`.

### Comparativo

| provedor · modo | modelo | exec. | pass@1 simple | pass@1 medium | pass@1 hard | pass@1 total | pass@k total | ordem | precisão | tokens/exec. | chars ferr./exec. | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fake | fake-operador | 150 (k=5) | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0 | 1.811 | 2,5 |
| fake · sem compactar | fake-operador | 150 (k=5) | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0 | 7.114 | 2,5 |
| fake · sem exemplos | fake-operador | 150 (k=5) | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0 | 1.811 | 2,3 |
| gemini | gemini-2.5-flash | 60 (k=3) + 20 (k=2) | 100 % | 100 % | 95 % | 99 % | 100 % | 98 % | 99 % | 9.148 | 2.101 | 6,3 |
| openai | gpt-4o-mini | — | — | — | — | — | — | — | — | — | — | — |

- **Fake = piso de sanidade do harness**: o operador fake (`agent/orquestrador.py`, roteiro
  determinístico + respostas às perguntas) acerta as 150 execuções nos três modos — ou seja, os
  gabaritos, as tolerâncias e a extração de números estão coerentes com o que as ferramentas
  devolvem. Não mede inteligência nenhuma; mede o harness. `--sem-exemplos` não muda nada no fake
  (ele não lê o prompt) e só faz sentido com modelo real.
- **Compactação (PR-14)**: os retornos de ferramenta enviados ao modelo caem de **7.114 para 1.811
  caracteres por execução (−74 %)**; nas *hard* de 17,4 k para 4,6 k. É o que mantém o Gemini em
  ~5,5 k tokens por execução *simple* (o prompt de sistema com 3 exemplos anotados é a maior parte)
  e ~14–26 k nas *hard*.
- **Gemini 2.5 Flash** acerta **60/60** nas *simple* e *medium* (ordem 98 %: em M07 pulou
  `locate_fault` e chamou `isolate_fault` direto nas 3 repetições — resposta certa, ordem 50 %, uma
  chamada a menos). Nas *hard*: **19/20** (pass@1 95 %, pass@2 100 %,
  ordem 100 %, precisão 95 %, ~20 k tokens e 19 s por execução — o gêmeo OpenDSS pontuando as
  opções domina o tempo). O único erro (H09 rep. 2) é uma resposta **implícita**: a pergunta pedia o
  número de opções de restauração e o modelo, além de propor um plano que ninguém pediu (daí a
  precisão 95 %), escreveu "a melhor opção é fechar 11053620 … existem outras 9 opções viáveis" —
  o 10 nunca aparece e o critério estrito conta como erro. Rodada feita já com a correção da
  compactação (item 1 abaixo); a rodada anterior está descrita lá.
- **OpenAI não rodou nesta máquina** (sem `OPENAI_API_KEY` no ambiente do agente noturno). Comando
  para o mantenedor, na ordem de custo: `uv run bdgd-light bench --provider openai --nivel simple
  --k 3 --seed 42` (~30 chamadas curtas), depois `--nivel medium,hard --k 3 --seed 42 --acrescentar`
  e, para o relatório definitivo, `--k 5`. O comparativo é regenerado automaticamente a partir dos
  CSVs da pasta.

### O que o benchmark encontrou (e mudou no código)

1. **`MALFORMED_FUNCTION_CALL` do Gemini após `isolate_fault`.** Na primeira rodada *hard* (k=2,
   antes das correções) 6 de 20 execuções falharam com `finish_reason='function_call_filter:
   MALFORMED_FUNCTION_CALL'` (mensagem sem `content` nem `tool_calls`), sempre na chamada seguinte
   a `isolate_fault`, e as 3 tentativas do cliente repetiam o erro — pass@1 hard 65 %
   (`/tmp`-only, não versionado). Um lembrete extra no pedido repetido (`LEMBRETE_CHAMADA` em
   `agent/llm.py`) não resolveu (5/20). O A/B com `--sem-compactar` nas 5 tarefas afetadas deu
   **10/10**, apontando a compactação; a diferença relevante era `manobras`/`sequencia` virarem
   texto (`"abrir 479996584"`). Mantendo-as como objetos `{"acao", "chave"}` (`compactar._manobras`),
   as mesmas 5 tarefas com compactação deram **10/10** e a rodada *hard* completa passou a
   **19/20**, zero `MALFORMED_FUNCTION_CALL`. Custo: +~60 caracteres por retorno.
2. **Contabilidade de custo em execuções que falham.** Uma execução interrompida pelo provedor
   registrava `rodadas = 0` e `tokens = 0` — subestimando o custo por acerto. `conversar` agora
   anexa à exceção o parcial consumido (`ConversaParcial`: rodadas, usos — inclusive das
   tentativas falhas, que o Gemini cobra —, tempo) e o orquestrador o soma à `Execucao`.
3. **Resposta numérica errada com proposta certa** (observação da revisão): em H03 rep. 2 da
   rodada sem correções o Gemini respondeu "6 opções viáveis" quando `restore_options` devolveu
   4 — o critério `verificar: resposta` pega isso. Nas rodadas seguintes não se repetiu; é o tipo
   de erro que o `--k 5` com OpenAI deve quantificar.
4. **Gabarito H08 (Taquara)**: as 10 opções de restauração são equivalentes (margens 60,8–62,0 %,
   mesmos 1.261 UCBT), então qualquer uma é acerto — o YAML documenta as 10 e o `melhor_opcao`
   recalcula o conjunto. Tolerância padrão passou a ser exata para contagens inteiras e ±2 % para
   grandezas fracionárias (o antigo ±2 % em contagens aceitaria 4.036 ≈ 4.100).

### Pendências

- Rodar OpenAI (comandos acima) e comparar tokens/pass@1 com o Gemini.
- Variação entre execuções do Gemini sem `seed`: k=2 nas *hard* é pouco para pass@k; subir para
  k=5 quando houver orçamento (~26 k tokens × 50 execuções).
- Ampliar as tarefas *medium*/*hard* de Ipanema (hoje 3 e 2) e incluir eventos `chave_indisponivel`
  e `falta_transitoria` (o harness só injeta `falta_permanente`).
