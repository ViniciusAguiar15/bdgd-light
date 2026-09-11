# Agente orquestrador + verificador HITL (issue #34)

O agente é o nível 2 de autonomia do roteiro do COD (`docs/PLANO.md`): **analisa e propõe; quem
executa é o operador**. Ele consome eventos do simulador (`bdgd-light sim`, `docs/sim.md`), usa as
ferramentas de rede da `SessaoCOD` (`docs/mcp-ferramentas.md`) e termina em uma proposta pendente
de aprovação humana (`bdgd-light aprovar`). Segue o padrão do PowerChain (arXiv 2508.17094):
*orquestrador* (LLM com ferramentas e exemplos anotados) + *verificador* (checagens
determinísticas sobre a rede e o gêmeo) + humano no laço.

Código: `src/bdgd_light/agent/orquestrador.py`; exemplos: `docs/agent/exemplos.yaml`;
sessão Tijuca completa (JSON de cada chamada): `docs/agent/sessao-tijuca.json`;
testes: `tests/test_agente.py`; CLI: `bdgd-light agente`.

## Arquitetura

```
fila de eventos (sim) ──► Orquestrador.executar_evento(evento)
                              │  1. _preparar: load_cluster(evento.cluster); falta permanente →
                              │     inject_fault(trecho) (o modelo NÃO injeta faltas)
                              │  2. prompt = PROMPT_SISTEMA + top-K exemplos (afinidade com o evento)
                              │  3. mensagem = EVENTO {json} + SITUAÇÃO DA SESSÃO + TAREFA
                              │  4. conversar(cliente, mensagens, ferramentas, max_rodadas)
                              │       ferramentas = SessaoCOD.* exceto set_switch e load_cluster
                              │       propose_plan passa pelo Verificador antes de chegar à sessão
                              │  5. sem proposta (falta permanente)? mensagem de replanejamento
                              │     (até --replanejar vezes)
                              ▼
                         Execucao (proposta, veredito, chamadas, recusas, tokens, tempos, hash)
                              │
                              ▼
        proposta P-000n pendente ──► bdgd-light aprovar / console ──► set_switch com token
```

O agente roda **no mesmo processo** da `SessaoCOD` (não via transporte MCP): as ferramentas são os
mesmos métodos que o servidor MCP expõe, com os mesmos descritores (gerados da assinatura +
`DESCRICAO_PARAMETROS`) e a mesma auditoria (`audit.jsonl`). Um cliente MCP externo (Claude
Desktop, Inspector) continua podendo usar o servidor; o orquestrador é o caminho "de casa" para a
demo e o benchmark.

### Ferramentas expostas ao modelo (`FERRAMENTAS_MODELO`)

`get_topology`, `get_switch_state`, `downstream_customers`, `inject_fault`, `locate_fault`,
`isolate_fault`, `restore_options`, `run_powerflow`, `propose_plan`, `get_proposal`.
**Nunca** `set_switch` (manobra só com token humano) nem `load_cluster` (o orquestrador carrega).
`inject_fault` fica disponível para perguntas do tipo "e se cair o trecho X?", mas o prompt manda
não usá-lo em eventos (a falta já foi registrada).

### Prompt de sistema

Papel (assistente do COD da Light, nível 2), sete regras e, quando há exemplos, a seção "Exemplos
anotados (tarefa → ferramentas → justificativa)". Regras, em resumo:

1. Nunca executar manobras; toda manobra é uma proposta; **uma proposta por execução**.
2. Falta permanente: `locate_fault → isolate_fault → restore_options(score=true) → propose_plan`
   com a melhor opção **viável** (maior margem no disjuntor, mais clientes); sem opção viável,
   `propose_plan()` sem chave (isolar e religar o tronco são) + despacho de equipe.
3. Só chaves de `restore_options`; nunca fechar NA antes de abrir a fronteira; respeitar chaves
   indisponíveis.
4. Transitória: registrar, sem manobra, citando os clientes sem tensão no tempo morto. Pico:
   `run_powerflow(loadmult)`. Chave indisponível: registrar a restrição, sem manobra, dizendo
   quantos clientes a jusante passam a depender de equipe.
5. Recusa do verificador → ler `problemas` e escolher outra opção (ou só isolar).
6. Resumo final em português com unidades, alternativas descartadas e o id da proposta.
7. Pergunta numérica → o número pedido **escrito explicitamente** na resposta final, na unidade
   pedida — nunca implícito ("a melhor e outras 9") nem outra grandeza no lugar (o total do CTMT em
   vez dos clientes que continuam sem tensão). Regra acrescentada pelo benchmark (issue #52): são
   os dois erros que o critério `verificar: resposta` pegou no Gemini (H09) e no gpt-4.1-mini
   (Ipanema, [`docs/review/RESULTADOS-OPENAI.md`](review/RESULTADOS-OPENAI.md)).

### Exemplos anotados (`docs/agent/exemplos.yaml`)

Doze pares `tarefa → ferramentas → justificativa` com `tags`: falta simples (uma rota), duas rotas
(margem), rota inviável por corrente/gargalo (caso URG29983 em Tijuca), rota inviável por tensão,
sem opção (Ipanema, negativo), recusa do verificador → replanejar, chave indisponível + falta,
falta transitória, pico de carga, chave indisponível, pergunta de clientes a jusante e pergunta de
topologia. `selecionar_exemplos(exemplos, consulta, k, tipo=)` pontua: `tipo` do evento presente
nas tags vale 10 (a categoria domina), palavra da consulta nas tags vale 2, no texto vale 1
(normalizado pelo tamanho do exemplo). Os ids escolhidos ficam em `Execucao.exemplos`.

### Verificador (`Verificador.verificar(sessao, chave, opcoes=, isolamento=)`)

Gate dentro do wrapper de `propose_plan`. Checagens (nome → o que falha):

| checagem | recusa quando |
|---|---|
| `falta_registrada` | não há falta na sessão |
| `opcao_em_restore_options` | a chave proposta não está entre as opções devolvidas |
| `chaves_existem` | alguma chave da sequência não existe no cluster |
| `chaves_disponiveis` | a sequência usa chave marcada indisponível (evento `chave_indisponivel`) |
| `abre_antes_de_fechar` | há um `fechar` antes de um `abrir` na sequência |
| `fronteira_isolada` | a sequência não abre toda a fronteira da falta (`isolate_fault.chaves`) |
| `score_eletrico` | opção sem score e `exigir_score=True` (peça `restore_options(score=true)`) |
| `convergiu` | o fluxo da opção não convergiu |
| `tensao_mt` | Vmin MT < `vmin` (0,93) ou Vmax MT > `vmax` (1,05) |
| `corrente_disjuntor` | corrente no disjuntor da fonte receptora acima da nominal (margem < 0) |
| `sem_sobrecarga_mt` | há trecho MT acima de 100 % no caminho |
| `viavel` | `score.viavel` é falso por outro motivo |

Avisos (não recusam): há opção viável com margem ≥ 2 p.p. maior; `propose_plan()` sem chave quando
existe opção viável. A recusa vira `{"erro", "problemas", "avisos"}` para o modelo, um registro
`agente.verificador.recusa` na auditoria e uma entrada em `Execucao.recusas`; a aprovação registra
`agente.verificador.ok` e o veredito vai dentro da proposta (`verificador`).

### Métricas por execução (`Execucao.to_dict()`)

`tipo`, `cluster`, `evento`/`pergunta`, `provider`, `modelo`, `rodadas`, `replanejamentos`,
`n_ferramentas`, `ferramentas` (nome, argumentos, resumo/erro, segundos), `sequencia`,
`recusas_verificador`, `proposta`, `veredito`, `resposta`, `uso` (prompt/completion/total tokens;
`informado` = o provedor devolveu uso), `segundos_llm`, `segundos_ferramentas`, `segundos_total`,
`hash_auditoria` (hash do registro `agente.fim`), `exemplos`, `erro`. `bdgd-light agente --json`
imprime isso; `--saida arquivo.json` grava.

### Compactação dos retornos para o modelo (`agent/compactar.py`)

Pedido da revisão PR-14: a `SessaoCOD`/MCP continua devolvendo os dados completos (console,
verificador e clientes MCP precisam deles), mas a mensagem `tool` que vai ao LLM é reduzida —
listas de nós viram contagens (`n_desligados`, `zona.n_nos`), manobras ficam só com `acao`/`chave`,
`restore_options` traz as 5 primeiras opções detalhadas (`top_n_opcoes`) e as demais em uma linha
(`outras_opcoes`: chave, fonte, clientes, viável, margem, primeiro motivo), `get_topology` troca a
lista de chaves por contagens (`chaves_resumo`; `get_switch_state` para uma chave), `run_powerflow`
perde `comandos_dss`/`master`/`ajustes`, e todo float é arredondado a 4 casas. Medido no
`tijuca_cabofrio_tronco` com o operador fake (`chars_ferramentas` em `Execucao.to_dict()`):

| | locate_fault | isolate_fault | restore_options | propose_plan | total |
|---|---|---|---|---|---|
| íntegro (`--sem-compactar`) | 1.546 | 7.876 | 9.529 | 1.578 | **20.529** chars |
| compactado (padrão) | 814 | 437 | 3.850 | 1.566 | **6.667** chars (−68 %) |

`get_topology(com_chaves=True)` do cluster inteiro cai de 39,4 k para ≈ 1 k chars. `Execucao.compactado`
registra o modo; o benchmark (#36) compara tokens e acerto com e sem compactação.

### Operador fake (`fake_operador()`)

`FakeLLMClient` com regra que lê o histórico e segue o fluxo do prompt: falta permanente →
locate → isolate → restore_options(score) → propose_plan (primeira opção viável ainda não tentada;
se o verificador recusar, a seguinte; sem chave se não houver) → resumo; pico → run_powerflow com
o `loadmult` do evento; transitória e chave indisponível → só o resumo; pergunta → get_topology →
resposta. Serve aos testes, à demo offline e como baseline do benchmark (#36).

## CLI

```bash
uv run bdgd-light agente --cenario tijuca_cabofrio_tronco --provider gemini
uv run bdgd-light agente --cenario ipanema_9210            # OpenAI (OPENAI_API_KEY) por padrão
uv run bdgd-light agente --evento E-0003 --fila data/eventos/eventos.jsonl
uv run bdgd-light agente --evento '{"tipo":"pico_carga","cluster":"tijuca","hora":"…","ctmt":"ALC9925","detalhes":{"loadmult":1.4}}'
uv run bdgd-light agente --pergunta "quantos clientes ficam sem tensão se a chave 11035901 abrir?" --cluster tijuca
uv run bdgd-light agente --cenario taquara_bocari --provider fake --json --saida /tmp/taq.json
```

Opções: `--provider openai|gemini|ollama|fake`, `--modelo`, `--max-rodadas 8`,
`--replanejar 2`, `--top-k 3`, `--exemplos outro.yaml`, `--sem-score` (só topologia; o verificador
não checa tensão/corrente), `--sem-compactar` (retornos íntegros ao modelo), `--vmin/--vmax`, `--feeders`, `--dss-out`, `--estado data/agent`
(mesma pasta do `mcp` e do `aprovar`: a proposta aparece em `bdgd-light aprovar`), `--dia/--mes`,
`--seed`, `--json`, `--saida`. Sai com código 1 quando a execução termina com `erro` (sem proposta
em falta permanente, rodadas esgotadas, provedor indisponível).

O benchmark do agente (`bdgd-light bench`, 34 tarefas, pass@k, ordenação, tokens e US$ por
acerto, OpenAI × Gemini × fake, com/sem exemplos e compactação) está em [`docs/bench.md`](bench.md).

## Validação com modelos reais (2026-09-10)

Comandos (um por cenário; `--estado /tmp/ag/estado` para não misturar com a sessão de demo):

```bash
for c in tijuca_cabofrio_tronco ipanema_9210 taquara_bocari; do
  uv run bdgd-light agente --cenario $c --provider gemini --estado /tmp/ag/estado --saida /tmp/ag/${c}_gemini.json
done
```

Resultados com `gemini-2.5-flash` (endpoint OpenAI-compatível do Gemini, ADR-003), `top_k=3`:

| cenário | sequência | proposta | verificador | rodadas | tokens (prompt+saída=total*) | LLM / ferramentas |
|---|---|---|---|---|---|---|
| `tijuca_cabofrio_tronco` (ALC9925, trecho 11304252) | locate → isolate → restore_options(score) → propose_plan | **P-0001: abrir 11035901, fechar 974020904 → ALC9946**, 4042 clientes, margem 46 %, Vmin 1,027 pu | ok (11 checagens) | 5 | 49 360 + 735 = 53 480 | ≈23 s / 6,9 s |
| `ipanema_9210` (PTS0001, trecho 11409068) | idem | **P-0002 sem chave** (isolar 505111870 e 561826961; religador já aberto) + despacho de equipe | ok (só topologia: 5 checagens, sem chave) | 5 | 63 179 + 389 = 65 474 | 14,4 s / 0,1 s |
| `taquara_bocari` (TQR33862, trecho 11798327) | idem | **P-0003: abrir 11026473, 22826994, 528574225, 790615689; fechar 10924213 (religador); fechar 11056672 → TQR33859**, 1984 clientes, margem 62 %, Vmin 0,998 pu | ok | 5 | 54 075 + 468 = 59 395 | 25,8 s / 18,5 s |

| `tijuca_cabofrio_tronco` — **OpenAI** `gpt-4.1-mini` | idem | **P-0001: abrir 11035901, fechar 974020904 → ALC9946**, 4042 clientes, margem 45,98 %, Vmin 1,027 pu (mesma do Gemini) | ok | 4 | 32 154 + 508 = 32 662 | 14,3 s / 9,8 s |
| `ipanema_9210` — **OpenAI** | idem | **P-0002 sem chave** (isolar 505111870 e 561826961) + despacho (mesma do Gemini) | ok (5 checagens) | 4 | 32 559 + 376 = 32 935 | 10,2 s / 0,04 s |
| `taquara_bocari` — **OpenAI** | idem | **P-0003: abrir 11026473, 22826994, 528574225, 790615689; fechar 10924213; fechar 11053620 → TQR33859**, 1984 clientes, margem 61,96 %, Vmin 1,009 pu (chave NA equivalente à do Gemini: mesma fonte, mesmos clientes, empate de margem) | ok | 5 | 37 150 + 385 = 37 535 | 15,0 s / 24,8 s |

\* o total do Gemini inclui tokens de raciocínio ("thoughts"), por isso é maior que prompt + saída.
Os ~50 k tokens de prompt são cumulativos das 5 rodadas: o resultado de `restore_options` com
10 opções e scores é a maior parte; compactar esse retorno para o modelo é a otimização óbvia (#36).

Leitura: nos três cenários o modelo seguiu o fluxo do prompt sem replanejamento, escolheu a mesma
opção que o ranking elétrico do gêmeo (Tijuca: descartou URG29983 pelo gargalo `Line.smt_11051956`
a 180 % e RCP9882 pela margem de 20 %; Taquara: maior margem entre 10 viáveis) e reconheceu o
caso negativo de Ipanema (35 NA de pátio de SE, nenhuma de campo) sem inventar chave. Os resumos
citaram os números das ferramentas (A, pu, %, clientes). Exemplos escolhidos: Tijuca
`falta_simples_uma_rota, falta_duas_rotas, rota_inviavel_por_corrente`; Ipanema
`sem_opcao_negativo, …`; Taquara `falta_simples_uma_rota, rota_inviavel_por_corrente, …`.

**OpenAI** (`gpt-4.1-mini-2025-04-14`, perfil padrão; rodado pelo mantenedor com os mesmos
comandos e `--provider openai`, saídas em `data/relatorios/*_openai.json`): mesmas propostas do
Gemini nos três cenários, 0 replanejamentos e 0 recusas, em 4–5 rodadas e ~33–38 k tokens (menos
que o Gemini porque não há tokens de raciocínio e uma rodada a menos) — 10–15 s de LLM por falta.
**Observação (Ipanema)**: o resumo do OpenAI citou "1730 clientes sem tensão" — o total do CTMT
PTS0001 antes de religar o tronco — em vez dos **479** que continuam sem tensão depois de isolar a
falta e religar o religador (o número que interessa ao operador e que `isolate_fault` devolve). A
proposta estava certa; o texto, não. Por isso o benchmark (#36) pontua também a **correção
numérica do resumo** (a resposta tem de conter o número esperado, com tolerância), e não só a
proposta/sequência de ferramentas.

### Recusa do verificador forçada (ciclo de replanejamento)

Nas execuções reais acima o verificador aprovou a primeira proposta (0 recusas); para ver o *gate*
segurar e o modelo replanejar, aperte o limite de tensão só do verificador — `--vmin` vale para o
`Verificador`, enquanto o `restore_options(score=True)` que o modelo chama continua com o padrão
0,93 pu, então o modelo vê 10 opções viáveis e propõe a primeira:

```bash
uv run bdgd-light agente --cenario taquara_bocari --provider fake --vmin 1.01 \
  --estado /tmp/ag-recusa/estado --saida /tmp/ag-recusa/taquara_vmin101.json
```

```
verificador recusou chave=11053620: tensão MT fora de [1.01, 1.05] pu: mín 1.009, máx 1.045
verificador recusou chave=11056672: tensão MT fora de [1.01, 1.05] pu: mín 0.998, máx 1.045
Proposta P-0002 (pendente): fechar 789941518 · fonte TQR33859 · 1984 clientes · abrir 11026473 →
abrir 22826994 → abrir 528574225 → abrir 790615689 → fechar 10924213 → fechar 789941518
Verificador: ok · … tensao_mt=✔ …
fake-operador · 7 rodada(s), 0 replanejamento(s), 6 chamada(s) · ferramentas 15.4s
```

Sequência: `locate → isolate → restore_options → propose_plan ×3` — as duas primeiras chamadas
de `propose_plan` voltam com `ok=false` e `problemas=[…]` (não criam proposta; ficam em
`recusas_verificador` do JSON), o modelo lê o problema e propõe a próxima opção com Vmin acima de
1,01 pu (789941518, margem 62 %). O contador `replanejamentos` só conta os ciclos em que o modelo
encerrou sem proposta e foi mandado replanejar; `--replanejar 2` limita esses ciclos, e cada
recusa consome uma rodada de `--max-rodadas`. Com `--vmin 1.03` em `tijuca_cabofrio_tronco`
nenhuma opção passa (Vmin 1,018–1,027 pu) e a execução termina com `erro` após esgotar as
opções — o *gate* nunca deixa passar uma manobra fora dos limites.

## Limites conhecidos

- O agente é **sequencial e síncrono**: um evento por vez, sem fila interna; o console (#35,
  `bdgd-light serve`, [`docs/console.md`](console.md)) é quem encadeia eventos → execuções →
  propostas, rodando o orquestrador numa thread por evento (`AgenteEmSegundoPlano`).
- Só uma proposta por execução; propostas anteriores pendentes não são canceladas pelo agente
  (`load_cluster` as expira).
- O verificador confia no score do gêmeo: sem `--sem-score` ele exige `restore_options(score=true)`;
  com `--sem-score` só checa topologia e sequência (marca `eletrico=false`).
- Seleção de exemplos é lexical (sem embeddings) — suficiente para 12 exemplos e 4 tipos de evento.
- Custo: ~50–65 k tokens de prompt por falta permanente com o Gemini Flash (rodadas cumulativas);
  ver #36 para compactação dos retornos e comparação entre provedores.
- Não há memória entre execuções além de `indisponiveis` (chaves sem telecomando) e do estado da
  sessão (falta, propostas, auditoria).
