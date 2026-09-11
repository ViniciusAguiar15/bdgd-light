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
| PR | ver "Fechamento" ao fim da seção |

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
