# Diário do modo noturno 3 — 2026-09-11

Trabalho autônomo sobre a fila da rodada 3 (`docs/backlog/16`–`18` = issues #51–#53, sendo #53 o
guarda-chuva de #48, #40, #39 e #44), mesmas regras das noites anteriores (cabeçalho de
`docs/review/NOITE-2.md`): uma branch e um PR por issue, Conventional Commits, `uv run ruff check . &&
uv run ruff format . && uv run pytest` verdes antes de cada push, CI verde → `gh pr merge --squash
--delete-branch` (máx. 3 tentativas), `docs/review/` lido antes de cada issue, nada de `data/` no git,
nunca force-push, nunca direto em `main`. Horários em BRT.

## 0. Ambiente e chaves (07:25–07:30)

| | |
|---|---|
| `main` | `5e38c1c` (revisão MANHA-2 / PR-16 / backlog da rodada 3), árvore limpa, nenhum PR aberto |
| Gemini | `GEMINI_API_KEY` presente. `uv run bdgd-light llm --provider gemini "Quanto é 2 + 3?"` → **OK**: `gemini-2.5-flash`, 2 rodadas, 277 tokens, 1,4 s (`/tmp/n3/llm_gemini.json`; auditoria em `data/audit/llm.jsonl`). |
| OpenAI | **`OPENAI_API_KEY` ausente** no processo da sessão, num `zsh -lic` de login, em `~/.zshrc`/`~/.zprofile`, nos `.env` do repositório, em `launchctl getenv` e no *keychain*. `uv run bdgd-light llm --provider openai "Quanto é 2 + 3?"` → `defina a variável de ambiente OPENAI_API_KEY`. Como na noite 2, tudo que depende de OpenAI fica registrado como pendência com o comando exato para o mantenedor rodar (ver §2 e o resumo final). |
| Leituras | `docs/review/MANHA-2.md`, `docs/review/PR-16.md` (PR #49 aprovado; pedidos: bench OpenAI, pendências 3–5 do diário da noite 2), backlogs 16–18. Nenhum pedido pendente aplicável antes da #51 além dos que ela própria cobre (GIF/capturas, roteiro, modo passo a passo). |
| Ferramentas | uv 0.9.24, node/npm ok, Chrome headless para o smoke; **sem** `ffmpeg`/`gifski`/`pngquant` (só `sips`) → README com 3 PNG em vez de GIF. Porta 8000 ocupada por outro processo (Docker) → `serve` local na **8010**. |

## 1. #51 — demo/aula: passo a passo, capturas e roteiro (07:30–)

| | |
|---|---|
| Branch | `feat/demo-passo-a-passo` (a partir de `main` `5e38c1c`) |
| PR | **#54** — CI verde (console, llm-smoke, test 3.11/3.12) → squash-merge às 07:52, `main` `791ca3d`; issue #51 fechada. Revisão do mantenedor em `docs/review/PR-17.md` (aprovado; a porta 8010 já está explícita no roteiro, §0). |

### Decisões

- **"Passo único do MCP" = `set_switch` com o token da proposta.** `SessaoCOD.set_switch` já impõe a
  ordem (`Proposta.proximo_passo`), incrementa `executadas` e marca `executada` ao fim; então o modo
  passo a passo não precisa de nada novo no servidor MCP — só de um lado humano que execute **uma**
  manobra por chamada: `humano.executar_passo` (aprova se ainda pendente, com `executar="passo"` na
  trilha; registra `hitl.passo` por manobra) e a rota `POST /api/propostas/{id}/passo`. O token nunca
  vai ao navegador (`to_dict(com_token=False)` → `***`); o servidor o lê internamente.
- **Mapa recolore sozinho a cada passo**: cada `set_switch` entra na auditoria → `estado.hash` muda →
  `cod.ts` recarrega `/api/estado.geojson`. Verificado no smoke: 467 trechos MT apagados após a
  falta, 467 após abrir a chave de isolamento (nada reenergiza ainda), 72 (só a zona isolada) após
  fechar o tie.
- **UI**: botão `#cod-passo` "Aprovar e executar a 1ª manobra: abrir X (1/n)" → "Próxima manobra:
  fechar Y (k/n)"; a lista marca ✓ as feitas e ▶ a atual; "Aprovar e executar" vira "Executar a
  última"/"Executar as k restantes" (mistura permitida: `executar_proposta` já fatia a partir de
  `executadas`); "Rejeitar" desabilita depois da primeira manobra aplicada (não há o que rejeitar).
- **Smoke em etapas** (`SMOKE_FLUXO=1`): 1 injetar → 2 proposta (agente ocioso, `<details>` das
  alternativas aberto) → 3 aprovar **ou**, com `SMOKE_PASSOS=1`, n cliques em `#cod-passo` exigindo
  exatamente n = manobras e `executadas == k` a cada clique. `SMOKE_CAPTURAS=<pasta>` grava
  `1-evento`, `2-proposta`, `2b-passo`, `3-executada`; `SMOKE_BASE=base-nenhuma` troca para o fundo
  escuro (PNG de ~315 KB em vez de 1,9 MB com satélite). Sem `ffmpeg`/`gifski`, o README leva as 3
  capturas (critério alternativo do backlog) em `docs/img/`.

### Validação

```bash
uv run pytest tests/test_console_api.py -q          # + test_passo_a_passo_uma_manobra_por_chamada
BDGD_CONSOLE_TOKEN=demo uv run bdgd-light serve --cluster tijuca --provider fake --porta 8010 --estado /tmp/n3/serve/estado
cd console && npm run build
SMOKE_FLUXO=1 SMOKE_PASSOS=1 SMOKE_TOKEN=demo SMOKE_OPERADOR=ana SMOKE_BASE=base-nenhuma \
  SMOKE_CAPTURAS=../docs/img npm run smoke -- "http://127.0.0.1:8010/?cenario=tijuca"
# → cliques 2 = manobras 2; executadas 1→2; apagados 467→467→72; tProposta 7,5 s; tTotal 11,6 s; exit 0
SMOKE_FLUXO=1 SMOKE_TOKEN=demo npm run smoke -- "http://127.0.0.1:8010/?cenario=tijuca"   # modo clássico, exit 0
uv run ruff check . && uv run ruff format . && uv run pytest                                # 276 testes verdes
```

Demo com LLM real (`serve --provider gemini`, mesma sequência pelo smoke, sessão nova): proposta em
19,4 s, agente livre em 22,7 s, 2 cliques, total 26,9 s; `gemini-2.5-flash` 5 rodadas, 24.253 tokens,
mesma proposta do fake (abrir 11035901, fechar 974020904 → ALC9946). Registrado em `docs/console.md`.

### Roteiro testado do zero (07:45)

Clone limpo da branch em `/tmp/n3/clone` (`git clone --branch feat/demo-passo-a-passo …`), com caches
do `uv`/`npm` quentes: clone 1–2 s, `uv sync --extra dev --extra twin --extra agent --extra console`
≈ 1 s (146 resolvidos/75 instalados), `npm ci` 0,6 s (45 pacotes), `npm run build` ≈ 1,5 s,
primeiro `uv run bdgd-light --help` ≈ 20 s (bytecode). `data/feeders` e `data/dss` por *symlink*.
`serve --cluster tijuca --provider fake --porta 8011` respondeu em 2,1 s; smoke passo a passo:
proposta em 8,9 s, 2 cliques = 2 manobras, 467 → 467 → 72 trechos, 17 s no total, exit 0. Os comandos
da §4 do roteiro também rodaram no clone: recusa forçada (`taquara_bocari --provider fake --vmin
1.01`) 16 s com as 2 recusas esperadas e P-0001 fechar 789941518; Ipanema com Gemini 14 s, 5 rodadas,
18,6 k tokens, proposta sem chave + despacho (479 clientes seguem sem tensão). O script de tempos
(`/tmp/n3/clone.sh`) apagou o próprio log com um `rm -rf` no início — os tempos de instalação vieram
dos *mtimes* dos logs por etapa; os das demos foram medidos direto. Tudo em `docs/demo-roteiro.md` §6.

### Pendências desta issue

- **GIF**: sem `ffmpeg`/`gifski`/`pngquant` na máquina; ficaram as 3 capturas PNG (critério
  alternativo do backlog). Com `gifski` instalado: `SMOKE_CAPTURAS=/tmp/cap … && gifski -o demo.gif
  /tmp/cap/*.png`.
- **OpenAI na demo ao vivo**: o roteiro está escrito com `--provider openai` (como pedido) e os
  números da §3.2 vêm de `docs/agent.md` (validação do mantenedor em 2026-09-10); nesta máquina só
  foi possível ensaiar com `fake` e `gemini`.

## 2. #52 — benchmark completo (07:55–09:05)

| | |
|---|---|
| Branch | `feat/bench-completo` (a partir de `main` `791ca3d`) |
| PR | **#55** — CI verde (console, llm-smoke, test 3.11/3.12) → squash-merge às 09:15, `main` `2a10a76`; issue #52 fechada. |
| Leituras | `docs/review/PR-17.md` (revisão do #54, chegou 08:55: aprovado; nada a aplicar — a porta 8010 já está na §0 do roteiro; OpenAI segue ausente neste shell, conferido de novo: `env`/`zsh -lic` sem `OPENAI_API_KEY`). |

### Decisões

- **Eventos sem manobra no harness**: `evento: falta_transitoria | chave_indisponivel` (com `falta`
  ou `chave`), `verificar: sem_manobra` (reprova proposta ou `propose_plan`/`set_switch`/`inject_fault`;
  exige o número do gabarito na resposta) e `referencia: []` = nenhuma ferramenta necessária — o
  número já vem nos detalhes do evento (`sem_tensao_se_religador_abrir` / `clientes_a_jusante`, este
  acrescentado ao `chave_indisponivel` do simulador para chaves NF). Consultar continua permitido,
  mas derruba a precisão. O gabarito só injeta a falta quando o evento é `falta_permanente`.
- **+4 tarefas de Ipanema** (M11–M13, H11) sobre o que a rede subterrânea tem de diferente: NF do
  PTS9088 (271 UCBT), religador 10934177 indisponível (1.816), transitória no tronco do PTS0001
  (1.730), falta na ponta do PTS9924 → proposta sem chave. `bench --gabarito` confere os 34
  (`34 gabaritos conferem`). Cabeçalho do YAML atualizado (versão 2).
- **Regra 7 do prompt** (número explícito na resposta final, na unidade pedida) — H09/H03 e a
  observação do mantenedor (1.730 no lugar de 479). Regra 4 explicitada para transitória/chave
  indisponível (citar os clientes). O operador fake responde aos dois eventos citando o número.
- **Custo em US$** no harness (`PRECOS_USD_MILHAO`, `preco_modelo`, `custo_usd`): preço de lista
  por prefixo de modelo (`gpt-4.1-mini-2025-04-14` → `gpt-4.1-mini`; `openai/…` do GitHub Models),
  raciocínio do Gemini (total − prompt) cobrado como saída, execuções sem uso informado (timeout)
  contam zero, grupos só de fake → `—`. Coluna `US$/exec.` no CSV/`.md`/comparativo e na tabela do
  CLI; o `.md` registra o preço usado. Gemini conferido na página de preços (US$ 0,30/2,50);
  OpenAI = preço de lista do lançamento (a página é renderizada no cliente; conferir antes da aula).
- **`MALFORMED_FUNCTION_CALL` voltou** (8/55 nas *hard* com exemplos, sempre após `isolate_fault`,
  3 tentativas iguais): a hipótese de ontem (compactação) não se sustentou com mais dados — 2/22 sem
  compactar e **0/22 sem exemplos**. Mitigação barata e testada: o pedido repetido após resposta
  vazia sobe a temperatura (0 → 0,5 → 1,0) além do lembrete (`temperatura_da_tentativa`); validação
  em 24 execuções das 6 tarefas que falharam → 1 erro (4 %) contra 15 %, n pequeno, registrado como
  tal. Não mudei o padrão dos exemplos: fica como pendência com o comando do A/B k=5.
- **Baselines refeitos com as 34 tarefas** (fake ×3 modos, k=5, 170 execuções cada) para o
  comparativo não misturar 30 e 34 tarefas; os CSVs de 2026-09-10 ficam como histórico (o
  comparativo usa só o mais recente de cada provedor·modo). Os `.md` de hoje foram regenerados ao
  fim (`relatorio_markdown` sobre os CSVs) para todos trazerem o comparativo completo.

### Rodadas (Gemini 2.5 Flash, `--seed 42`; 284 execuções, 3,9 M tokens, US$ 1,69)

| rodada | exec. | acertos | erros | tokens/exec. | US$/exec. | s/exec. |
|---|---|---|---|---|---|---|
| `--nivel hard --k 5` (08:01–08:18) | 55 | 47 (85 %; pass@5 100 %) | 8 × MALFORMED | 19.234 | 0,0090 | 16,9 |
| `--nivel simple,medium --k 3 --acrescentar` (08:18–08:20) | 69 | 69 | — | 5.437 | 0,0020 | 1,9 |
| `--k 2 --sem-exemplos` (08:20–08:31) | 68 | 67 | 1 × ReadTimeout (H11) | 9.290 | 0,0044 | 8,1 |
| `--k 2 --sem-compactar` (08:31–08:42) | 68 | 66 | 2 × MALFORMED | 18.858 | 0,0071 | 7,2 |
| validação da temperatura: `--ids H01,H02,H04,H06,H08,H10 --k 4` (08:43–08:52, `/tmp`) | 24 | 23 | 1 × MALFORMED | — | — | — |

Leitura completa (compactação −52 % de tokens nas *hard*; exemplos não compram acerto no Flash, mas
contêm o `propose_plan` sem pedido; custo por evento < US$ 0,01) em `docs/bench.md`.

### Validação

```bash
uv run bdgd-light bench --gabarito                                                  # 34 gabaritos conferem
uv run bdgd-light bench --provider fake --ids M11,M12,M13,H11 --k 1 --seed 42 --saida /tmp/…   # 4/4
uv run bdgd-light bench --provider gemini --nivel hard --k 5 --seed 42 --estado /tmp/n3/bench/estado-gemini
uv run bdgd-light bench --provider gemini --nivel simple,medium --k 3 --seed 42 --acrescentar --estado …
uv run bdgd-light bench --provider gemini --k 2 --seed 42 --sem-exemplos --estado …
uv run bdgd-light bench --provider gemini --k 2 --seed 42 --sem-compactar --estado …
uv run bdgd-light bench --provider fake --k 5 --seed 42 [--sem-compactar | --sem-exemplos]     # 170/170 ×3
uv run ruff check . && uv run ruff format . && uv run pytest                        # 278 testes verdes
```

### Pendências desta issue

- **OpenAI** (simple/medium/hard k=3 e o comparativo final): sem `OPENAI_API_KEY` neste shell, de
  novo. Comandos e custo estimado (~US$ 0,55) em `docs/bench.md` → Pendências; os 3 cenários do
  agente com OpenAI já estão em `docs/agent.md` (mantenedor, 10/09).
- Confirmar o efeito dos exemplos no `MALFORMED_FUNCTION_CALL` com `--nivel hard --k 5 --sem-exemplos`
  (~US$ 0,55) e decidir se o perfil `gemini` desliga os exemplos por padrão.
- `ReadTimeout` de 60 s (1 em 284): o cliente não repete em timeout.

## 3. #48 — motor OpenDSS em subprocesso (09:05–09:35)

| | |
|---|---|
| Branch | `fix/opendss-subprocesso` (a partir de `main` `791ca3d`; `origin/main` `2a10a76` mesclado após o #55) |
| PR | ver "Fechamento" ao fim da seção |
| Leituras | `docs/review/` sem arquivo novo desde o PR-17; issue #48 (contrato de `no_motor`, filho reciclado, `BDGD_MOTOR`, sem `os._exit` no conftest) e `docs/backlog/18`. |

### Decisões

- **Subprocesso próprio, não `multiprocessing` spawn.** A primeira versão usava
  `multiprocessing.get_context("spawn").Process`; funcionou nos testes, mas o *bootstrap* do spawn
  reexecuta o `__main__` do pai no filho e quebrou num script lido de stdin (`python - <<EOF` →
  `FileNotFoundError: …/<stdin>`), o que também alcançaria notebooks/REPLs. O motor agora é um
  `subprocess.Popen([sys.executable, "-c", "from bdgd_light.twin.powerflow import _main_motor; …"])`
  que importa **só** este módulo, ligado ao pai por um socket `AF_UNIX` em pasta temporária com
  `multiprocessing.connection.Connection` e desafio HMAC (chave de 32 bytes aleatórios passada por
  stdin, nunca por argv/ambiente). Mesmo contrato de `no_motor`: `(fn, args, kwargs)` em pickle,
  `(True, resultado)` ou `(False, exceção)` de volta; funções de módulo já eram serializáveis
  (`_run_powerflow`, `_ampacidade_tronco`).
- **Filho reciclado, erro visível.** Uma chamada por vez (trava); filho morto no meio de uma chamada
  (`SIGILL`/`SIGSEGV`/sem resposta em `BDGD_MOTOR_TIMEOUT`, padrão 600 s) → `MotorError`
  (subclasse de `ErroOpenDSS`) com o sinal no texto; a chamada seguinte recria o filho (`reinicios`).
  No agente isso vira `{"erro": …}` para o modelo e `ok: false` na execução (nada novo a fazer: o laço
  de ferramentas já convertia exceções). Exceções do filho sem construtor compatível com pickle
  (`DSSException(numero, texto)`) viram `ErroOpenDSS` com o mesmo texto (`_exportavel`).
- **Sem `os._exit`**: `tests/conftest.py` perdeu `pytest_sessionfinish`/`pytest_unconfigure`; o
  guarda de coleta (`opendssdirect` importado no processo de testes) fica, agora protegendo a
  invariante "o pai nunca carrega a biblioteca". `encerrar_processo` sobrevive só para
  `BDGD_MOTOR=thread` (estratégia anterior, mantida na transição) e é um `sys.exit` normal no modo
  padrão. `/api/estado` ganhou `motor` (`modo`, `pid`, `chamadas`, `reinicios`).
- **Custo medido** (macOS arm64, Master DU01 base do cluster Tijuca, 34.095 nós, resultado de
  3,1 MiB em pickle): criar o filho 0,4–0,8 s na 1ª chamada; **5–20 ms por chamada** sobre 1,0–1,2 s
  de fluxo; a suíte inteira caiu de ~40 s para 28 s (sem a troca de thread a cada chamada).
  `serve --cluster tijuca --provider fake`: cenário Cabo Frio → 14 chamadas ao motor, 7,6 s de
  ferramentas, `P-0004`; `kill -11` no filho + novo evento → `P-0005`, `reinicios: 1`, sem traceback
  no log; ao parar o servidor o filho sai junto (conexão cai → `EOFError` → fim do laço; `atexit`
  também o mata).

### Validação

```bash
uv run pytest tests/test_twin.py -k motor -q                     # recriação após morte (no meio e entre chamadas), timeout, exceção relançada, estado
uv run pytest tests/test_console_api.py -k motor_morre -q        # motor morre durante o agente; API viva; evento seguinte em motor novo
uv run bdgd-light dss --master tests/fixtures/dss/ieee13/IEEE13_Master.dss   # entry point sai com 0 sem os._exit
BDGD_CONSOLE_TOKEN=demo uv run bdgd-light serve --cluster tijuca --provider fake --porta 8012   # + kill -11 <pid do motor> (ver /api/estado → motor)
uv run ruff check . && uv run ruff format . && uv run pytest     # 285 testes verdes, 28 s, nenhum processo _main_motor órfão
```

### Pendências desta issue

- CI Linux é o teste definitivo do adeus ao `SIGSEGV` na saída (aqui no macOS nunca ocorreu); se
  voltar, a suspeita passa a ser outra biblioteca nativa, não a DSS C-API.
- `BDGD_MOTOR=thread` fica documentado como modo de transição; remover (junto com
  `encerrar_processo`) quando ninguém mais precisar dele.
- Windows não é alvo (socket `AF_UNIX`); se um dia for, trocar por `AF_INET` em 127.0.0.1.
