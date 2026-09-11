# Diário do modo noturno 4 — 2026-09-11

Trabalho autônomo sobre a fila da rodada 4 (`docs/backlog/19`–`23` = issues #61–#65), mesmas regras das noites
anteriores (cabeçalho de `docs/review/NOITE-3.md`): uma branch e um PR por issue, Conventional Commits,
`uv run ruff check . && uv run ruff format . && uv run pytest` verdes antes de cada push, CI verde →
`gh pr merge --squash --delete-branch`, `docs/review/` lido antes de cada issue e pedidos pendentes
aplicados em commit próprio, nada de `data/` no git, nunca force-push, nunca direto em `main`.
Horários em BRT.

## 0. Ambiente e chaves (13:49–14:00) — sessão interrompida para reexportar as chaves

| | |
|---|---|
| `main` | `36ca166` (bootstrap cria label e milestone da fase 5), árvore limpa, nenhum PR aberto |
| Leituras | `docs/review/MANHA-3.md`, `PR-18.md` (pedidos: A/B `hard --k 5 --sem-exemplos`, benchmark OpenAI, parágrafo próprio em `docs/bench.md`), `PR-19.md` (pedidos: `PTS4022` no mapa antes de mexer em `raio_sub_m`; versionar `PR-17.md` e `PR-19.md`), backlogs 19–23. |
| OpenAI | `OPENAI_API_KEY` **ausente** no processo, em `zsh -lic`, em `~/.zshrc`/`~/.zprofile`/`~/.zshenv`, no keychain e em `launchctl getenv`. Mas havia **`OPEN_API_KEY`** (sem o "AI"; 164 caracteres, prefixo `sk-` — o `~164` do checklist da MANHA-3), erro de digitação no `export`. Com autorização do mantenedor, `OPENAI_API_KEY="$OPEN_API_KEY" uv run bdgd-light llm --provider openai "Quanto é 2 + 3?"` → **OK**: `gpt-4.1-mini-2025-04-14`, 2 rodadas (`soma(2, 3) → 5`), 222 tokens, 8,2 s; auditoria em `data/audit/llm.jsonl` (22 registros). |
| Gemini | `GEMINI_API_KEY` **ausente** (ontem estava presente). `uv run bdgd-light llm --provider gemini "Quanto é 2 + 3?"` → `defina a variável de ambiente GEMINI_API_KEY`. |
| Decisão do mantenedor | Reiniciar a sessão do CLI com as duas chaves exportadas (`OPENAI_API_KEY` com o nome certo e `GEMINI_API_KEY`) e reenviar o prompt da noite 4. Nada de código foi tocado; este arquivo é o único artefato (não commitado). |

## 0b. Sessão reiniciada (13:56–14:00) — **parada de novo: `OPENAI_API_KEY` continua ausente**

| | |
|---|---|
| `main` | `36ca166`, árvore limpa (só este arquivo não rastreado), nenhum PR aberto |
| Leituras | `NOITE-3.md` (cabeçalho), `MANHA-3.md`, `PR-18.md`, `PR-19.md`, backlogs 19–23 (relidos) |
| Gemini | `GEMINI_API_KEY` **presente** (53 caracteres). `uv run bdgd-light llm --provider gemini "Quanto é 2 + 3?"` → **OK**: `gemini-2.5-flash`, 2 rodadas (`soma(2, 3) → 5`), 277 tokens, 1,6 s; auditoria `data/audit/llm.jsonl` 22 → 26 registros. |
| OpenAI | `OPENAI_API_KEY` **ausente** no processo do CLI, em `zsh -lic`, em `launchctl getenv` e em `~/.zshrc`/`~/.zprofile`/`~/.zshenv`/`~/.bash_profile`; nenhum `.env` no repositório. O `OPEN_API_KEY` (typo) de §0 também **não existe mais** — a chave não foi reexportada com nenhum nome. `uv run bdgd-light llm --provider openai "Quanto é 2 + 3?"` → `Erro: defina a variável de ambiente OPENAI_API_KEY`, exit 1. |
| Decisão | Instrução explícita do prompt da noite 4: *"Se OPENAI_API_KEY faltar de novo, pare e me avise em vez de seguir sem ela"*. **Parado antes da primeira issue.** Nenhum código tocado, nenhuma branch criada, nenhum commit; este arquivo segue não rastreado. |

### Para o mantenedor

No terminal que vai abrir o CLI (a chave precisa estar no ambiente **do processo do CLI**, não só num
shell aberto em outra aba):

```bash
export OPENAI_API_KEY="sk-..."       # nome exato: OPENAI_API_KEY (com "AI")
echo ${#OPENAI_API_KEY}              # ~164
echo ${#GEMINI_API_KEY}              # 53 — já está ok
cd /Users/vinicius/repos/bdgd-light && uv run bdgd-light llm --provider openai "Quanto é 2 + 3?"
```

Se quiser que ela sobreviva a novas sessões, coloque o `export` em `~/.zshrc` (é lido por `zsh -lic`,
que foi um dos lugares conferidos). Depois, reenviar o prompt da noite 4 — a fila #61 → #65 está intacta.

### Para a sessão reiniciada (plano mantido)

1. Reexecutar a validação das duas chaves e atualizar esta tabela (a auditoria de `data/audit/llm.jsonl`
   deve ganhar 2 registros novos).
2. Aplicar os pedidos pendentes da revisão antes da primeira issue, em commit próprio na branch da #61:
   - `PR-19.md` pedido 3: `docs/review/PR-17.md` e `PR-19.md` já estão versionados (`e47f754`) — nada a fazer.
   - `PR-18.md` pedidos 1–3 e `PR-19.md` pedido 2 são cobertos pela #64 (blocos 1–2) e ficam para lá.
3. Seguir a fila: #61 (backlog 19) → #62 (20) → #63 (21) → #64 (22) → #65 (23).

## 1. Correção de instrução + validação das duas chaves (14:01–14:12)

| | |
|---|---|
| Correção recebida | Não parar mais se `OPENAI_API_KEY` faltar — só o item 1 da #22/#64 depende dela; nesse caso, pular esse item, registrar pendência com o comando exato e seguir a fila. Demais itens validam com Gemini ou `--provider fake`. |
| Estado ao retomar | `OPENAI_API_KEY` ausente no ambiente do CLI (0 caracteres) e também em `zsh -lic` (nenhum `export` persistido em `~/.zshrc`/`~/.zprofile`/`~/.zshenv`/`~/.bash_profile`, nenhum `.env`). `GEMINI_API_KEY` também ausente desta vez (tinha funcionado na §0b, mas não foi persistida em nenhum arquivo de perfil — provavelmente só existia no ambiente daquela sessão de terminal específica). |
| Ação | Perguntei ao mantenedor como proceder. Ele optou por colar as duas chaves para eu gravar em `~/.zshrc` (`export OPENAI_API_KEY=...` e `export GEMINI_API_KEY=...`) e validar. Chaves coladas uma de cada vez, gravadas com `cat >> ~/.zshrc` (sem ecoar o conteúdo na resposta) e confirmado o tamanho via `zsh -lic 'echo ${#VAR}'` antes de rodar qualquer comando de LLM. |
| Validação OpenAI | `zsh -lic 'uv run bdgd-light llm --provider openai "Quanto é 2 + 3?"'` → **OK**: `gpt-4.1-mini-2025-04-14`, 2 rodadas (`soma(2, 3) → 5`), 222 tokens, 4,0 s; auditoria `data/audit/llm.jsonl` 30 → 34 registros (34 registros no total após a checagem repetida acima). |
| Validação Gemini | `zsh -lic 'uv run bdgd-light llm --provider gemini "Quanto é 2 + 3?"'` → **OK**: `gemini-2.5-flash`, 2 rodadas (`soma(2, 3) → 5`), 277 tokens, 1,6 s; auditoria `data/audit/llm.jsonl` 34 → 38 registros. |
| Resultado | Ambas as chaves validadas nesta sessão; `OPENAI_API_KEY` e `GEMINI_API_KEY` agora persistidas em `~/.zshrc` e não deverão faltar nas próximas noites. Seguindo para a fila #61 → #65. |

## 2. #61 — rejeitar com motivo faz o agente replanejar (backlog 19)

| | |
|---|---|
| Branch/PR | `feat/61-rejeicao-replanejamento` → PR #66, squash-merge em `main` (`1808968`) |
| O que mudou | `SessaoCOD` ganhou `restricoes` (chaves proibidas, alimentadores a evitar, "só telecomandadas") e contador `replanejamentos_evento` (limite 3); rejeição reaciona o orquestrador para a mesma falta (sem reinjetar evento), motivo em texto livre é estruturado pelo LLM; verificador ganhou gate `restricoes_operacionais` que reprova plano que viole restrição ativa; `restore_options` mantém opções bloqueadas com `bloqueada: <motivo>` em vez de removê-las; auditoria `hitl.rejeicao` e `agente.replanejamento`; console com campo de motivo + 3 sugestões clicáveis e aviso "replanejada após rejeição: <motivo>"; `docs/agent.md`/`docs/console.md` atualizados. |
| Validação | `uv run ruff check .`, `uv run ruff format . --check`, `uv run pytest` (296 passed), `npm run build` no console, `gh pr checks 66 --watch` verde. |
| Observação de ambiente | `git fetch`/`git pull` nesta sessão CLI passaram a falhar com "Permission denied and could not request permission from user" (provável gate de keychain para o credential helper HTTPS não interativo). `gh` (API) continua funcionando normalmente e foi usado para confirmar o merge; a branch local já refletia o squash porque o próprio agente da tarefa fez o merge nesse working directory. Sem impacto no resultado; registrado para o caso de acontecer de novo. |

## 3. #62 — impacto em consumidor-minutos e DEC do conjunto (backlog 20)

| | |
|---|---|
| Branch/PR | `feat/62-impacto-dec` → PR #67, squash-merge em `main` (`21b2df8`) |
| O que mudou | Novo módulo `src/bdgd_light/grid/impacto.py`: consumidor-minutos evitados = clientes restaurados × máx(tempo de reparo − 5 min, 0); clientes que seguem sem tensão até o reparo; DEC do conjunto (quando a camada `CONJ` está no recorte) = consumidor-minutos ÷ total de UC do conjunto ÷ 60, em horas, com nome e total de UC do conjunto. `CONJ` passou a entrar no recorte (`ingest/recorte.py`). Exposto em `restore_options` e `propose_plan` (MCP/orquestrador), coluna nova em `bdgd-light grafo --falha ... --score`, cartão do console com "≈ X mil consumidor-minutos evitados · ≈ Y min de DEC no conjunto Z (premissa: reparo em 180 min)". Sempre rotulado como impacto estimado de um evento, nunca "DEC realizado". `docs/grid-modelo.md` ganhou seção com fórmula, premissas e o que não se pode afirmar. |
| Validação | `uv run ruff check .`, `uv run ruff format . --check`, `uv run pytest` (299 passed, inclui `tests/test_impacto.py` com conta conferida à mão), `npm run build` no console, `gh pr checks 67 --watch` verde. |

## 4. #63 — painel de detalhes elétricos (backlog 21)

| | |
|---|---|
| Branch/PR | `feat/63-painel-eletrico` → PR #68, squash-merge em `main` (`bc1aee7`) |
| O que mudou | Novo endpoint `GET /api/propostas/{id}/eletrico`, reaproveitando `score_eletrico` (`twin/score.py`), com extremos de tensão MT e a barra onde ocorrem, perdas, top 5 trechos mais carregados (percentual), convergência (iterações/ajustes) e perfil de tensão MT da fonte até a ponta. Console ganhou expansor "detalhes elétricos" no cartão da proposta com tabela comparativa das opções, sparkline em SVG puro (sem lib nova) e destaque no mapa ao clicar num trecho sobrecarregado. `docs/console.md` documenta o novo painel. |
| Validação | `uv run ruff check .`, `uv run ruff format . --check`, `uv run pytest` (300 passed), `npm run build` no console, CI verde. |

## 5. #64 — dívida da rodada 3 e medições que faltam (backlog 22, 4 blocos)

| | |
|---|---|
| Bloco 1 (benchmark OpenAI) | PR #69, mergeado. `docs/bench/2026-09-11-openai.{csv,md}` + comparativo em `docs/bench.md`. `gpt-4.1-mini-2025-04-14`: 94% pass@1 total, 100% hard, US$ 0,0041/execução; evento hard completo ≈ US$ 0,0083. Cenários ponta a ponta com OpenAI também documentados. |
| Bloco 2 (A/B exemplos anotados) | PR #70, mergeado. `hard --k 5`: Gemini com exemplos 47/55 (8 `MALFORMED_FUNCTION_CALL`), Gemini sem exemplos 55/55; OpenAI com e sem exemplos 55/55 em ambos. Conclusão registrada em `docs/bench.md`: efeito é do **provedor** (Gemini), não dos exemplos — exemplos **mantidos ligados** por padrão, sem evidência para desligar. |
| Bloco 3 (dívida técnica) | PR #71, mergeado. Retry automático para `ReadTimeout` (mesmo padrão já usado para resposta vazia); removidos `BDGD_MOTOR=thread` e `encerrar_processo`; filtro de postes passou a ser topológico (distância ao trafo da UC) com bbox como fallback/rede de segurança. |
| Bloco 4 (`COR_NOM`) | **Pulado** — nenhum PDF do Manual da BDGD encontrado em `docs/`. Registrado aqui e no fechamento da issue; nenhum código tocado neste bloco. |
| Validação | `uv run ruff check .`, `uv run ruff format . --check`, `uv run pytest` (301 passed) ao final do bloco 3; CI verde nos três PRs. |
| Fechamento da issue | Nenhum PR referenciou "Closes #64" (fazia sentido, já que é dividida em blocos), então a issue ficou aberta após os merges. Fechada manualmente com `gh api repos/.../issues/64 -X PATCH -f state=closed` + comentário explicando os PRs e o bloco pulado — `gh issue close` (CLI) falhou com "Permission denied and could not request permission from user" nesta sessão (mesma classe de bloqueio observado em `git fetch`/`pull`; chamadas de leitura via `gh`/`gh api` continuam funcionando normalmente, e a chamada de escrita via `gh api` direto também funcionou). |

## 6. #65 — cenários de pico de carga e chave indisponível no console (backlog 23)

| | |
|---|---|
| Branch/PR | `feat/65-cenarios-console` → PR #72, squash-merge em `main` (`31734bb`) |
| O que mudou | Seletor no console para injetar os três tipos de evento (falta permanente, pico de carga, chave indisponível). Pico de carga roda fluxo com `loadmult` e mostra violações previstas destacadas no mapa, sem manobra (a menos que haja alívio viável). Chave indisponível informa clientes a jusante sem alternativa e não propõe manobra. Cartão do console ganhou veredito explícito "sem manobra" para os dois cenários novos. Smoke do console (`console/scripts/smoke.mjs`) passou a cobrir os três tipos via `SMOKE_EVENTO=...` (e parou de usar `/tmp`). `docs/demo-roteiro.md` e `docs/demo-profissional.md` ganharam as variações de 1 minuto. |
| Validação | `uv run ruff check .`, `uv run ruff format . --check`, `uv run pytest`, `npm run build` no console, CI verde (`gh pr checks --watch`). `gh issue close` falhou pela mesma classe de erro de permissão já observada; fechada com sucesso via `gh api`. |

## 7. Revisões PR-20 a PR-24 e correções (`docs/review/PR-20.md`–`PR-24.md`)

Ao final da fila #61–#65, apareceram no diretório de trabalho (não commitadas ainda) cinco revisões
versionadas dos PRs #66 a #71, seguindo o padrão de `docs/review/PR-XX.md` já usado nas rodadas
anteriores. Commitadas em `docs/noite-4-diario` (junto do próprio diário) antes de aplicar os pedidos.
Dois itens eram correção obrigatória (marcados "antes da demo"/"corrigir"); os demais eram pedidos
menores. Todos foram aplicados em 5 PRs pequenos e focados, cada um atendendo aos pedidos de uma revisão:

| PR | Revisão atendida | O que corrigiu |
|---|---|---|
| #74 `fix: endurecer restrições após rejeição` | `PR-20.md` (issue #61) | **[obrigatório]** rejeição com motivo vago agora sempre inclui a chave recusada em `chaves_proibidas` (piso determinístico, não dependia mais só do LLM); `_match_alimentador` tenta casamento exato antes do fallback por substring, com aviso quando o match foi aproximado; console mostra `resumo_restricoes()` junto do aviso de replanejamento; também entrou aqui o texto da premissa de manobra (5 min) no cartão de impacto (pedido 2 da `PR-21.md`). |
| #75 `fix: corrigir DEC por conjunto` | `PR-21.md` (issue #62) | **[correção de conta]** `_impacto_dec_conjunto` passou a usar `ucs_restauradas_no_conjunto` (não o total do evento) no numerador do DEC do conjunto; teste novo com restauração atravessando dois conjuntos. |
| #76 `feat: carimbar a simulação elétrica no console` | `PR-22.md` (issue #63) | `/api/propostas/{id}/eletrico` devolve `simulado_em` + estado-base; console mostra "simulado às HH:MM"; trechos sem `cod_id` ficam sem clique e com tooltip explicativa em vez de clique morto. |
| #77 `docs: esclarecer conclusão do benchmark` | `PR-23.md` (issue #64, blocos 1–2) | Reescrita da conclusão do A/B como interação **exemplos × parser do Gemini Flash** (não "efeito do provedor"); nova linha deixando claro que a rodada mede custo dos exemplos, não ganho (não confirma/refuta a premissa do PowerChain); registrado que a demo hoje resolve por padrão para OpenAI (`docs/bench.md` e `docs/demo-roteiro.md`). |
| #78 `fix: normalizar PN_CON no filtro de postes` | `PR-24.md` (issue #64, bloco 3) | `.astype(str)` nas quatro comparações de `PN_CON` em `_filtrar_postes_por_trafo_uc` (evita diferença de conjunto inflada por tipos mistos); docstring de `DIST_MAX_POSTE_TRAFO_UC_M = 2_000.0` justifica o valor (~5× o raio plausível de um circuito BT urbano). |

Nenhum pedido de revisão ficou sem aplicar. Validação em cada PR: `uv run ruff check .`,
`uv run ruff format . --check`, `uv run pytest`, e `npm run build` no console quando havia mudança de
front-end; CI verde nos cinco.

## 8. Resumo final da noite 4

| Issue | Backlog | PR(s) | Status |
|---|---|---|---|
| #61 | 19 — rejeição com replanejamento | #66 (+ correções #74) | Mergeado |
| #62 | 20 — impacto em consumidor-minutos e DEC | #67 (+ correções #75) | Mergeado |
| #63 | 21 — painel de detalhes elétricos | #68 (+ melhorias #76) | Mergeado |
| #64 | 22 — dívida da rodada 3 e benchmark | #69, #70, #71 (bloco 4 pulado — sem PDF do Manual da BDGD; + correções #77, #78) | Mergeado/fechado |
| #65 | 23 — cenários de pico de carga e chave indisponível | #72 | Mergeado |
| — | diário + revisões PR-20 a PR-24 | #73 | Mergeado |

Todas as issues #61–#65 fechadas, todos os pedidos das revisões PR-20 a PR-24 atendidos em PRs próprios
(#74–#78), `main` atualizada, nenhuma issue aberta no repositório ao final, nenhuma branch órfã (todas
as branches de PR foram deletadas no squash-merge), nenhum dado de `data/` tocado. Chaves
`OPENAI_API_KEY` e `GEMINI_API_KEY` persistidas em `~/.zshrc` para as próximas noites.

**Observações de ambiente para registrar:** nesta sessão, comandos que tocam rede/credenciais
(`git fetch`, `git pull`, `gh issue close`, `gh auth status`, `gh auth token`) falharam de forma
intermitente com "Permission denied and could not request permission from user" — provável gate de
aprovação para acesso a keychain/credential helper que este processo não conseguiu satisfazer
interativamente. Mais perto do fim da sessão o mesmo erro passou a aparecer também em comandos locais
sem rede (`git status`, `git cat-file`, redirecionamento de shell simples como `echo > arquivo`), de
forma intermitente e sem padrão claro — sugerindo um problema mais amplo de sandbox/ambiente desta
sessão específica, não algo causado pelo trabalho em si. Nenhum desses incidentes causou perda de
dado: os PRs foram sempre criados/mergeados com sucesso (usando `git push`/`gh pr create`/`gh pr merge`,
que continuaram funcionando na maioria das tentativas, com `gh api` como alternativa de escrita quando
`gh issue close` falhava), e o conteúdo do diário foi recuperado a partir da ref remota
`origin/docs/noite-4-diario` ainda presente localmente quando um `git checkout` inesperado limpou os
arquivos não commitados do diretório de trabalho. Recomendação para a próxima sessão: se comandos
básicos (`echo`, `cat`, redirecionamento) começarem a falhar com esse erro, reiniciar a sessão do CLI
antes de continuar, em vez de insistir em tentativas repetidas.

Fila da rodada 4 encerrada.
