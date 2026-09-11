# Roteiro da demo — aula de 15 minutos

Roteiro para apresentar o `bdgd-light` em sala: o que dizer, o que mostrar e o comando exato de cada
tela. Pensado para 15 min de fala + 5 de perguntas, com a demo ao vivo no cluster **Tijuca** e o
cenário negativo **Ipanema**. Testado do zero (clone limpo, `uv sync` + `npm ci`) em 2026-09-11 —
tempos reais na [seção 6](#6-preparação-testada-do-zero-tempos-reais).

Convenções: **[fala]** = o que dizer; `comando` = o que digitar; **[tela]** = o que apontar.
O relógio à esquerda é o minuto acumulado.

## 0. Antes da aula (10 min, uma vez)

```bash
git clone https://github.com/ViniciusAguiar15/bdgd-light && cd bdgd-light
uv sync --extra dev --extra twin --extra agent --extra console      # cria .venv com OpenDSS, agente e FastAPI
(cd console && npm ci && npm run build)                             # console compilado em console/dist
# dados: a BDGD não vai ao git. Copie (ou ligue) os recortes e os .dss dos clusters da demo:
#   data/feeders/cluster_tijuca.gpkg, cluster_ipanema.gpkg (+ um .gpkg/.meta.json por CTMT) e data/dss/
# se não tiver os recortes, gere-os a partir da BDGD (≈ 15 min): ver README "Começando" e docs/escopo-cidade.md
export OPENAI_API_KEY=…                                             # ou GEMINI_API_KEY (--provider gemini)
uv run bdgd-light llm --provider openai "Quanto é 2 + 3?"          # a chave funciona? (1 chamada, ~1 s)
```

Hoje, com `OPENAI_API_KEY` e `GEMINI_API_KEY` presentes e sem `BDGD_LLM_PROVIDER`/`BDGD_LLM_ENDPOINT`,
o `cliente_do_ambiente()` resolve por padrão para **OpenAI**; por isso a demo abaixo fixa
`--provider openai`.

Deixe **dois terminais** abertos na raiz do repositório e o navegador em `http://127.0.0.1:8000/`.
Se a porta 8000 estiver ocupada, use `--porta 8010` em todos os comandos abaixo.

Terminal 1 (fica rodando a aula toda):

```bash
BDGD_CONSOLE_TOKEN=demo uv run bdgd-light serve --cluster tijuca --provider openai --estado /tmp/aula/estado
#   → Console: http://127.0.0.1:8000/  · API: /api/estado · docs: /docs   (≈ 10 s para carregar o cluster)
```

No painel **COD · fila e aprovação** preencha operador (`seu nome`) e token (`demo`) — ficam no
`localStorage`. Escolha a base **Sem base (fundo escuro)** se o projetor for fraco: as cores de
energizado/desenergizado saltam mais.

## 1. Contexto — 0:00 → 3:00

**[tela]** README aberto na seção "A demo em três telas" (as 3 capturas).

**[fala]** Três siglas para começar:

- **BDGD** — Base de Dados Geográfica da Distribuidora. Toda distribuidora entrega à ANEEL, uma vez
  por ano, a rede inteira georreferenciada: alimentadores (`CTMT`), trechos MT/BT (`SSDMT`/`SSDBT`),
  chaves (`UNSEMT`, com estado normal aberta/fechada e se é telecomandada), transformadores,
  consumidores por poste. É dado **aberto**. Aqui: Light, 382, Rio de Janeiro, ano-base 2023 — 1.405
  alimentadores no município.
- **COD** — Centro de Operação da Distribuição. É quem, numa falta, decide o que abrir e fechar
  para religar o máximo de clientes com segurança. Hoje: telas SCADA, procedimentos, telefone com a
  equipe de campo. O ciclo *localizar → isolar → restaurar* (FLISR) é o caso clássico de automação.
- **PowerChain** (arXiv 2508.17094) — agentes de LLM operando *ferramentas* de rede (fluxo de
  potência, topologia) em vez de "conversar" sobre a rede. A ideia deste projeto: **o LLM não calcula
  nada; ele orquestra ferramentas determinísticas e um humano aprova**.

**[fala]** Pergunta que a demo responde: *dá para montar, só com dado aberto e software livre, um
COD agêntico auditável em que o operador continua no comando?*

## 2. Arquitetura em 5 camadas — 3:00 → 5:00

**[tela]** `docs/PLANO.md` (tabela de módulos) ou desenhe no quadro.

```
BDGD (.gdb) ─► 1 Dados: Parquet/GeoPackage por alimentador (geopandas, pyogrio)  · bdgd-light export/recortar
            ─► 2 Grafo: networkx por CTMT — falta, isolamento, rotas de restauração · bdgd-light grafo
            ─► 3 Gêmeo digital: OpenDSS (opendssdirect) — fluxo de potência de cada manobra · bdgd-light dss
            ─► 4 MCP + agente: ferramentas de rede (locate/isolate/restore_options/propose_plan/set_switch)
                 orquestrador (LLM) + verificador (regras) + aprovação humana (HITL) · bdgd-light mcp/agente
            ─► 5 Console: MapLibre + PMTiles + fila de eventos + botão de aprovar · bdgd-light serve
```

**[fala]** Dois pontos de projeto que valem a aula:

1. **Separação de papéis.** O *orquestrador* (LLM) só escolhe qual ferramenta chamar e com quais
   argumentos. O *verificador* é código: confere no gêmeo a tensão (0,93–1,05 pu), o carregamento
   dos trechos, a margem do disjuntor da fonte, a sequência abrir-antes-de-fechar. Se recusa, o LLM
   replaneja. E ainda assim **nada muda na rede sem um humano clicar**.
2. **Auditoria encadeada.** Cada chamada de ferramenta, cada resposta do modelo e cada decisão humana
   vai para um `audit.jsonl` com hash encadeado (o console mostra "trilha íntegra ✓").

## 3. Demo ao vivo — Tijuca, falta no tronco do CABOFRIO — 5:00 → 10:00

**[tela]** Console em `http://127.0.0.1:8000/?cenario=tijuca`, zoom na Praça Saens Peña.

**[fala]** Cluster A: `ALC9925` CABOFRIO (SE Aldeia Campista, 4,2 km aéreos, 4.036 clientes BT) no
centro de uma estrela com ties telecomandadas para três vizinhos de **três subestações diferentes**:
`ALC9946` RIMARAES (mesma SE), `URG29983` AMALIA (SE Uruguai) e `RCP9882` BOMPASTOR (SE Rio Comprido).
Verde = energizado, vermelho = sem tensão, círculos = chaves (contorno branco = telecomandada).

### 3.1 Injetar a falta (5:00)

**[ação]** clique **injetar falta** (ou, no terminal 2:
`curl -s -X POST localhost:8000/api/eventos -H 'X-Operador: prof' -H 'X-Console-Token: demo' -H 'Content-Type: application/json' -d '{"cenario":"tijuca_cabofrio_tronco"}'`).

**[tela · captura 1]** faixa "⏳ falta permanente em 11304252 — o agente localiza, isola e avalia
opções no gêmeo…"; o tronco fica vermelho; "sem tensão: 356 nós · 4.036 UCBT · 63 trafos". Na
auditoria, ao vivo: `inject_fault → locate_fault → isolate_fault → restore_options → propose_plan`.

**[fala]** O religador `10927447` abriu. O agente chama `locate_fault` (zona entre chaves),
`isolate_fault` (as duas chaves que cercam a falta, `10927447` e `11035901`) e `restore_options`, que
lista **todas** as chaves NA que reenergizam a zona a jusante e manda cada uma para o OpenDSS. É aqui
que o tempo passa (um fluxo de potência do cluster por opção): 10–20 s.

### 3.2 A proposta e as alternativas (6:00)

**[tela · captura 2]** cartão `P-0001 · pendente`: **abrir 11035901, fechar 974020904 → ALC9946**;
clientes recuperados 4.036 UCBT / 63 trafos; "gêmeo: viável · margem disjuntor 46 % · Vmin MT 1,027
pu"; "verificador: aprovou (11/11 checagens)". Abra **alternativas (10)**.

**[fala]** Três rotas, três subestações, e o motivo de cada descarte está escrito:

- `974020904 → ALC9946` — **escolhida**: viável, margem 46 %.
- `746851189 → RCP9882` (BOMPASTOR) — viável, mas margem de só 20 % no disjuntor da fonte.
- `11006815 → URG29983` (AMALIA) — **inviável**: o trecho `smt_11051956` (20 m, condutor de 132 A)
  no caminho até a tie iria a **180 %** de carregamento. *O LLM não sabe disso; o OpenDSS sabe, e o
  LLM leu o resultado.* Este é o momento "a ferramenta manda".
- As "sem telecomando" existem eletricamente, mas exigiriam equipe no local — o ranking as
  rebaixa em vez de esconder.

**[fala]** O texto em itálico é a justificativa do modelo, citando os números das ferramentas
(margem, pu, clientes). Com OpenAI `gpt-4.1-mini`: 4 rodadas, ~33 k tokens, 10–15 s de LLM; com
Gemini 2.5 Flash: 5 rodadas, ~24–54 k tokens, ~20 s (`docs/agent.md`).

### 3.3 Aprovação humana, uma manobra por vez (8:00)

**[ação]** em vez de **Aprovar e executar**, clique **Aprovar e executar a 1ª manobra: abrir
11035901 (1/2)**.

**[tela]** o cartão vira `aprovada`, a lista marca `✓ abrir 11035901` e `▶ fechar 974020904`; o mapa
**não muda** (467 trechos MT seguem sem tensão).

**[fala]** Abrir a chave de isolamento não religa ninguém — só cerca a falta. É a ordem que o
verificador impõe: abrir antes de fechar, senão a fonte vizinha alimentaria a falta. Cada clique é
um `set_switch` no servidor MCP com o token da proposta; o servidor só aceita **a próxima** manobra
da sequência aprovada — não dá para pular nem inverter.

**[ação]** clique **Próxima manobra: fechar 974020904 (2/2)**.

**[tela · captura 3]** mapa verde de novo; "sem tensão: 41 nós · 0 UCBT · 0 trafos" (só a zona
isolada, entre as duas chaves abertas); cartão `executada por <operador>`; auditoria com dois
`mcp.chamada set_switch` e "trilha íntegra ✓".

**[fala]** 4.036 clientes de volta em ~30 s de relógio, com o operador tendo lido a justificativa e
autorizado chave por chave. `data/agent/hitl.jsonl` guarda quem aprovou o quê, quando, de onde.

## 4. O outro Rio e o "o LLM errou" — 10:00 → 13:00

### Variações de 1 minuto no mesmo console (opcional entre 3.3 e 4.1)

Com o seletor do painel **COD · fila e aprovação**, troque o tipo de evento e injete duas variações
rápidas sem sair da mesma tela:

- **Pico de carga** — clique **injetar pico de carga**. O agente roda `run_powerflow` com o
  `loadmult` do evento, lista subtensões/sobrecargas previstas e o cartão final marca
  **veredito: sem manobra**. Aponte os botões de `COD_ID`: eles destacam no mapa os trechos MT
  violados.
- **Chave indisponível** — clique **injetar chave indisponível**. O agente registra a restrição,
  informa quantos clientes a jusante passam a depender de equipe e o console também mostra
  **veredito: sem manobra**. A mensagem importante aqui é governança: a chave fica fora de qualquer
  plano automático.

### 4.1 Cenário negativo — Ipanema (10:00)

**[ação]** terminal 2:

```bash
uv run bdgd-light agente --cenario ipanema_9210 --provider openai --estado /tmp/aula/ipanema
```

**[fala]** Cluster B: `PTS0001` LDS 9210, SE Posto Seis — subterrâneo, 63 chaves, 48 telecomandadas.
Parece o cenário perfeito para *self-healing*… mas as 35 chaves NA são de **pátio de subestação**
(barras que a BDGD não modela), nenhuma de campo. Falta no trecho `11409068`: não há rota.

**[tela]** saída do agente (≈ 15 s): proposta **sem chave de restauração** — isolar `505111870` e
`561826961` (o religador `10933610` já está aberto) e **despachar equipe**; verificador ok (5
checagens topológicas); dos 1.730 clientes do CTMT, **479** seguem sem tensão até a equipe chegar.
Nas rodadas reais nem OpenAI nem Gemini inventaram uma chave (Gemini, 2026-09-11: 5 rodadas,
18,6 k tokens, 13,9 s).

**[fala]** Reconhecer que *não há o que fazer automaticamente* é tão importante quanto restaurar.
Um agente que "sempre acha uma solução" é perigoso.

### 4.2 O LLM propôs, o verificador pegou (11:30)

**[ação]** terminal 2 — força o limite de tensão do verificador (só dele) para 1,01 pu:

```bash
uv run bdgd-light agente --cenario taquara_bocari --provider fake --vmin 1.01 \
  --estado /tmp/aula/recusa --saida /tmp/aula/taquara_vmin101.json
```

**[tela]** (≈ 16 s) duas linhas `verificador recusou chave=11053620: tensão MT fora de [1.01, 1.05]
pu: mín 1.009…` e `…chave=11056672 … mín 0.998`, depois `Proposta P-0001 … fechar 789941518 ·
Verificador: ok` (6 manobras: 4 aberturas, religador, tie). Sequência: `locate → isolate →
restore_options → propose_plan ×3`.

**[fala]** O modelo viu 10 opções "viáveis" com o limite normal e propôs a primeira; o *gate*
recusou duas vezes com o motivo numérico, o modelo leu e propôs a terceira, que passa. Com
`--vmin 1.03` em Tijuca nenhuma passa e a execução termina com **erro**, não com uma manobra
ruim. (`--provider fake` aqui só para ser reprodutível na sala; com `openai` o ciclo é o mesmo,
ver `docs/agent.md` "Recusa do verificador forçada".)

## 5. Números, limites e próximos passos — 13:00 → 15:00

**[tela]** `docs/bench.md` (tabela "Comparativo").

**[fala]** Benchmark de 30 tarefas (10 *simple* topologia, 10 *medium* falta/isolamento, 10 *hard*
restauração com gêmeo), pass@k, ordem das ferramentas e correção **numérica** do resumo:

- operador `fake` (roteiro determinístico) 150/150 — é o piso de sanidade do harness, não mede IA;
- **Gemini 2.5 Flash**: 100 % *simple* e *medium*, 95 % *hard* pass@1 (100 % pass@2), ~9 k
  tokens/execução, 6 s; o único erro foi uma resposta *implícita* ("existem outras 9 opções" para
  uma pergunta cujo gabarito era 10) — por isso o prompt agora exige o número explícito;
- **OpenAI gpt-4.1-mini**: mesmas propostas nos 3 cenários, 4–5 rodadas, 33–38 k tokens, 10–15 s;
  o resumo de Ipanema citou 1.730 clientes (o CTMT inteiro) em vez dos 479 ainda sem tensão — a
  proposta certa, o texto errado — daí a métrica de correção numérica;
- compactar os retornos das ferramentas para o modelo cortou 74 % dos caracteres (7.114 → 1.811 por
  execução) sem perder acerto. Custo por falta tratada: centavos de dólar (tabela em `docs/bench.md`).

**[fala]** Limites honestos: BDGD anual (não é tempo real), sem medição/SCADA, cargas típicas por dia
útil, gêmeo do cluster e não da cidade, um evento por vez, sem proteção coordenada. Próximos passos:
motor OpenDSS em subprocesso, vários operadores, eventos transitórios e chave indisponível no
benchmark, cenário C (Méier, único triângulo aéreo completo da cidade).

**[fecho]** *O modelo não decide; ele propõe, com os números das ferramentas, e o operador decide —
uma chave por vez, se quiser.*

## 6. Preparação testada do zero (tempos reais)

2026-09-11 07:45, macOS arm64 (M-series), clone em `/tmp/n3/clone` da branch do PR (o que virou
`main`), **caches do `uv` e do `npm` quentes** (a máquina já tinha as mesmas versões; a frio, some o
tempo de download — alguns minutos, dominado por `opendssdirect`/`geopandas`/`pyarrow`). Dados
(`data/feeders`, `data/dss`) ligados por *symlink* a partir de uma cópia local — a BDGD não vai ao git.

| etapa | comando | tempo |
|---|---|---|
| clonar | `git clone --branch … https://github.com/ViniciusAguiar15/bdgd-light` | 1–2 s |
| ambiente Python | `uv sync --extra dev --extra twin --extra agent --extra console` (146 pacotes resolvidos, 75 instalados) | ≈ 1 s (cache quente) |
| console | `cd console && npm ci` (45 pacotes) `&& npm run build` (tsc + vite) | 0,6 s + ≈ 1,5 s |
| primeiro `uv run bdgd-light --help` | compila o *bytecode* do venv | ≈ 20 s (só na primeira vez) |
| subir o backend | `BDGD_CONSOLE_TOKEN=demo uv run bdgd-light serve --cluster tijuca --provider fake --porta 8011 --estado /tmp/n3/clone-estado` | `/api/estado` responde em **2,1 s** |
| demo headless (passo a passo) | `SMOKE_FLUXO=1 SMOKE_PASSOS=1 SMOKE_TOKEN=demo SMOKE_OPERADOR=prof npm run smoke -- "http://127.0.0.1:8011/?cenario=tijuca"` | injetar → proposta **8,9 s** · 2 cliques = 2 manobras · 467 → 467 → 72 trechos sem tensão · smoke inteiro (com o Chrome) **17 s**, exit 0 |
| §4.1 Ipanema (`--provider gemini`) | `uv run bdgd-light agente --cenario ipanema_9210 --provider gemini --estado /tmp/aula/ipanema` | **14 s** (5 rodadas, 18,6 k tokens) — proposta sem chave + despacho |
| §4.2 recusa forçada | `uv run bdgd-light agente --cenario taquara_bocari --provider fake --vmin 1.01 --estado /tmp/aula/recusa --saida /tmp/aula/taquara_vmin101.json` | **16 s** (ferramentas 15,1 s) — 2 recusas, P-0001 fechar 789941518 |

Na cópia de trabalho (mesma máquina, `docs/console.md`): `fake` proposta em 7,5 s e 11,6 s total com
os 2 cliques; `gemini-2.5-flash` 19,4 s e 26,9 s (5 rodadas, 24,3 k tokens). Com OpenAI
`gpt-4.1-mini` a validação de 2026-09-10 deu 10–15 s de LLM por falta — a chave não estava
disponível na máquina que testou este roteiro, então a fala da §3.2 cita os números de `docs/agent.md`.

O smoke é exatamente a sequência da seção 3 sem o professor: se ele passa no clone limpo, a demo
está pronta. Se `serve` reclamar de `console/dist`, faltou o `npm run build`; se `/api/eventos`
devolver 404 "recorte do cenário não existe", faltam os `.gpkg` em `data/feeders`.

## Plano B (sem internet ou sem chave)

- `--provider fake` em todos os comandos: o operador roteirizado segue o mesmo fluxo de ferramentas
  e produz a mesma proposta em Tijuca (é o que o smoke usa); some a justificativa em linguagem
  natural.
- Sem backend nenhum: o console publicado em <https://viniciusaguiar15.github.io/bdgd-light/> mostra
  os três cenários com o estado estático da falta (`?cenario=tijuca|ipanema|taquara`), sem o painel
  de aprovação.
- As três capturas do README e a de `docs/console.md` (modo passo a passo) cobrem a seção 3 se o
  projetor não cooperar.
