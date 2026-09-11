# Diário do modo noturno 5 — 2026-09-11

Trabalho autônomo sobre a fila da rodada 5 (`docs/backlog/24`–`28` = issues #80–#84), sozinho até a fila
acabar, sem pausas para perguntar. Mesmas regras das rodadas anteriores (uma branch e um PR por issue,
Conventional Commits, `uv run ruff check . && uv run ruff format . --check && uv run pytest` verdes
antes de push, build do console quando aplicável, CI verde → `gh pr merge --squash --delete-branch`,
nada de `data/` no git, nunca force-push, nunca direto em `main`). **Regra nova desta rodada:** diário e
revisões entram no PR da própria issue, nunca ficam soltos e não commitados na árvore de trabalho — foi
o que custou caro na rodada 4 (ver `docs/review/MANHA-4.md`, seção "Processo"). Horários em BRT.

## 0. Ambiente (18:35)

| | |
|---|---|
| `main` | `f62f269` (docs: revisões PR-25 e PR-26, fechamento da rodada 4 e backlog da rodada 5), árvore com uma modificação não commitada em `scripts/bootstrap_github.sh` (adiciona os labels `area:bench` e `area:cli`, usados pelas issues #82/#84 e #83 respectivamente) e um `docs/review/NOITE-4.md` órfão no diretório de trabalho (já removido do git em `f62f269`, era cópia local desatualizada de uma sessão anterior — apagado do disco, sem perda: o conteúdo final já está versionado no histórico via PR #73). |
| Chaves | `OPENAI_API_KEY` (164 caracteres) e `GEMINI_API_KEY` (53 caracteres) presentes via `zsh -lic`, herdadas de `~/.zshrc` das rodadas anteriores. |
| Issues abertas | #80 (backlog 24, parser único de elemento), #81 (backlog 25, suíte adversarial), #82 (backlog 26, ganho dos exemplos), #83 (backlog 27, replay), #84 (backlog 28, resultados consolidados) — mapeadas por título do frontmatter de cada arquivo de backlog. |
| Plano | Levar o `scripts/bootstrap_github.sh` não commitado como um commit extra no PR da primeira issue (#80), já que é infraestrutura de repo pré-existente e pequena, sem branch própria só para isso. Seguir a fila em ordem: #80 → #81 → #82 → #83 → #84, cada uma com sua branch, PR e squash-merge antes da próxima. Diário atualizado e commitado dentro do PR de cada issue (nunca solto). |

## 1. Issue #80 — parser único de nome de elemento OpenDSS (19:02)

- **Branch/PR:** `refactor/80-parser-elemento`, PR #85.
- **Infraestrutura levada junto no primeiro commit:** `scripts/bootstrap_github.sh` entrou em
  `chore: versiona labels pendentes do bootstrap`, só para versionar a adição pré-existente dos
  labels `area:bench` e `area:cli`, como combinado para a rodada.
- **O que mudou no código:** centralizei em `src/bdgd_light/twin/gpkg2dss.py` a constante
  `PREFIXO_ELEMENTO_TRECHO_MT = "smt_"`, a geração (`nome_elemento_trecho_mt`) e o parsing
  (`cod_id_trecho_mt_de_elemento`) dos nomes `Line.SMT_<COD_ID>`. O conversor passou a usar a
  mesma função ao escrever `SegmentosMT` e o `Energymeter` no caso sem chave de cabeceira.
  `src/bdgd_light/twin/score.py`, `src/bdgd_light/mcp_server/sessao.py` e
  `src/bdgd_light/console/api.py` deixaram de ter lógica própria e passaram a importar a função
  compartilhada. Também exportei a utilidade em `src/bdgd_light/twin/__init__.py`.
- **Decisões de design:** preferi colocar a API compartilhada no próprio `gpkg2dss.py`, ao lado da
  geração real do nome, em vez de criar outro módulo utilitário. Em `SessaoCOD`, troquei o filtro
  textual `startswith(...)` por um `map(...)` do parser compartilhado para a lista de correntes já
  sair com `cod_id` consistente. Mantive o teste de aceitação implícito do formato gerado nos
  asserts existentes de `tests/test_gpkg2dss.py`.
- **Teste novo:** acrescentei um round-trip em `tests/test_gpkg2dss.py` que gera
  `Line.SMT_SEG001` a partir do `COD_ID` e recupera `SEG001` de volta, inclusive em minúsculas, e
  confirma que nomes de outros tipos de elemento não casam.
- **Varredura do repositório:** `grep -rn "smt_" src/` passou a apontar só a constante
  compartilhada em `gpkg2dss.py`; não encontrei outra cópia do parser além das três citadas pela
  issue.
- **Validação local antes do PR:** `uv run ruff check .`, `uv run ruff format . --check`,
  `uv run pytest` → `307 passed, 1 warning`. Também rodei o recorte direcionado
  `uv run pytest tests/test_gpkg2dss.py tests/test_mcp_server.py tests/test_console_api.py -q`
  para confirmar os três chamadores alterados.

## 2. Issue #81 — suíte adversarial do verificador (18:58)

- **Branch/PR:** `test/81-verificador-adversarial`, PR #86.
- **O que mudou no código:** criei `src/bdgd_light/agent/verificador_adversarial.py` como fonte única
  da matriz adversarial usada por teste e documentação. A matriz cobre 8 recusas determinísticas do
  verificador: `falta_registrada`, `chaves_existem`, `chaves_disponiveis`,
  `restricoes_operacionais`, `abre_antes_de_fechar`, `opcao_em_restore_options`,
  `sem_sobrecarga_mt` (caso AMALIA/Tijuca, trecho `11051956` a ~180 %) e `fronteira_isolada`.
  Todos os planos são montados diretamente em Python e passados ao `Verificador`, sem cliente de
  LLM e sem depender do orquestrador.
- **Teste novo:** `tests/test_verificador_adversarial.py` parametriza a matriz inteira, asserta
  `ok is False`, o **primeiro gate reprovado** e um trecho da mensagem esperada em cada caso.
  Também verifica que `docs/verificador.md` está sincronizado com `renderizar_markdown()`.
- **Documentação versionada no mesmo PR:** `docs/verificador.md` agora é gerado por
  `scripts/gerar_verificador_doc.py` a partir da mesma matriz, com tabela situação → gate →
  mensagem e um parágrafo explicando por que o gate é determinístico.
- **Decisões de design:** preferi uma fonte compartilhada em `src/` para evitar duplicação entre
  pytest e documentação. Para o caso elétrico de AMALIA, congelei no plano manual o score já
  conhecido da rota inviável (sobrecarga em `Line.smt_11051956`), o que mantém a suíte rápida e
  independente de provider de LLM; os demais casos exercitam apenas estado de sessão e sequência de
  manobras.
- **Validação local:** `uv run python scripts/gerar_verificador_doc.py`, `uv run pytest
  tests/test_verificador_adversarial.py`, `uv run ruff check .`, `uv run ruff format . --check` e
  `uv run pytest` → `316 passed, 1 warning`.

## 3. Issue #82 — ganho dos exemplos anotados (20:42)

- **Branch/PR:** `bench/82-ganho-exemplos`, PR desta issue.
- **Regra crítica seguida:** no recorte *hard* já versionado do OpenAI (`docs/bench/2026-09-11-openai-hard-k5.*`
  e `...-sem-exemplos.*`) o `pass@1` já estava saturado em **55/55** nos dois braços. Em vez de
  forçar uma conclusão, segui a opção **(a)** do backlog/issue e montei um conjunto **hard+**
  exploratório para pressionar ordenação e escolha de ferramenta.
- **O que entrou no harness:** `bench/tarefas.yaml` passou de **34 → 38 tarefas** com H12–H15:
  restrição ativa persistida na sessão (`restricoes`), chave indisponível (`indisponiveis`) e dois
  replanejamentos após rejeição (`rejeicao_previa`). Em `src/bdgd_light/bench.py`, o benchmark e o
  gabarito agora aplicam essas precondições de forma recalculável e registram também **chamadas de
  ferramenta desnecessárias** (`len(sequência) − LCS`) no CSV/relatório. Corrigi junto um bug da
  rodada anterior: `--seed` no provider OpenAI estava sendo passado ao construtor do cliente, não ao
  payload do `chat/completions`; `OpenAICompatClient` agora aceita `seed` e o inclui no JSON da API.
- **Hard+ construído assim:** H12 = H01 com restrição ativa para evitar ALC9946; H13 = H04 com a
  única tie viável (`746851189`) indisponível; H14 = H01 após rejeição da proposta com
  `974020904`; H15 = H04 após rejeição da única tie viável. Mantive `gabarito` recalculável via
  `restore_options(score=true)` e filtros determinísticos das precondições.
- **Medição OpenAI (via `zsh -lic`, `seed=42`, `k=n=3` no hard+):**
  - *hard* original (55 por braço, arquivos já versionados): com exemplos `ordem 100 %`,
    `precisão 97,3 %`, `0,11` chamadas desnecessárias/exec., `3,64` rodadas/exec., `18.897`
    tokens/exec.; sem exemplos `ordem 96,4 %`, `precisão 97,8 %`, `0,09`, `3,87`, `17.714`.
  - *hard+* novo (`docs/bench/2026-09-11-openai-hardplus-k3.*`): com exemplos `12/12`,
    `ordem 100 %`, `precisão 68,1 %`, `1,42` chamadas desnecessárias/exec., `4,08` rodadas,
    `41.269` tokens; sem exemplos `12/12`, `ordem 95,8 %`, `precisão 69,2 %`, `1,25`,
    `4,58` rodadas, `44.417` tokens.
- **Leitura honesta documentada em `docs/bench.md`:** os sinais seguem mistos. Com exemplos, o
  OpenAI preserva melhor a ordem e usa menos rodadas/tokens no *hard+*; sem exemplos, fica
  ligeiramente mais preciso e com menos chamadas extras. Isso **não** sustenta trocar o padrão do
  agente. O texto final agora diz explicitamente o que foi medido, o `n` de cada braço e o que
  **não** foi medido (poder estatístico/IC, outros provedores, um hard+ maior).
- **Testes/documentação da mudança:** `tests/fixtures/bench_mini.yaml` ganhou um caso mínimo de
  `rejeicao_previa` e `tests/test_bench.py` cobre o novo schema, o filtro de opções bloqueadas /
  indisponíveis, a métrica de chamadas extras e a execução fake do replanejamento.

## 4. Issue #83 — replay da auditoria do agente (19:40)

- **Branch/PR:** `feat/83-replay-auditoria`, PR desta issue.
- **O que mudou no código:** acrescentei em `src/bdgd_light/agent/audit.py` as utilidades
  `listar_arquivos`, `verificar_origem`, `reconstruir_evento` e a montagem de linha do tempo por
  `RegistroArquivo`. O replay identifica todas as execuções ligadas ao mesmo `evento.id`
  (`agente.inicio`/`agente.replanejamento`), puxa também os preparos imediatamente anteriores
  (`load_cluster` e `inject_fault`) e expande o conjunto relevante pelos ids de proposta (`P-0001`,
  `P-0002` etc.) para capturar aprovação, rejeição e `set_switch`, inclusive quando essas decisões
  também estão em `hitl.jsonl`.
- **Novo comando CLI:** `bdgd-light replay <id-do-evento>` entrou em `src/bdgd_light/cli.py` com
  `--origem` (arquivo ou diretório de JSONL, padrão `data/`), `--verificar-cadeia` e `--json`.
  Sem `--json`, a saída é uma timeline em pt-BR: preparo, ferramentas na ordem, opções com score,
  verificador (gates aprovados/falhos), rejeição humana, replanejamento, aprovação e execução.
  Com `--json`, a estrutura traz `evento`, `cadeia`, `linha_do_tempo`, `registros` e
  `resposta_final`.
- **Decisões de design:** preferi verificar a cadeia **por arquivo** e não num merge global, porque
  `audit.jsonl` e `hitl.jsonl` têm cadeias independentes. Para evitar duplicar eventos humanos na
  timeline, quando `hitl.jsonl` está presente ele vira a fonte canônica de `hitl.aprovacao`,
  `hitl.rejeicao` e `hitl.passo`; a cópia desses eventos no `audit.jsonl` continua disponível em
  `registros`, mas não polui a leitura humana. Ajustei a ordenação para que a aprovação apareça
  antes dos `set_switch` quando caem no mesmo milissegundo.
- **Teste novo:** criei `tests/test_replay.py`. O teste positivo gera um evento real com
  `Simulador` + `Orquestrador(..., provider="fake")`, rejeita a primeira proposta, dispara
  `replanejar_apos_rejeicao`, aprova a segunda via `humano.aprovar` e valida tanto a saída textual
  quanto a JSON do replay. O teste negativo adultera o registro `restore_options` em
  `audit.jsonl` e confirma que `--verificar-cadeia` retorna erro apontando a primeira divergência
  (`seq=8: hash não bate`).
- **Documentação commitada no mesmo PR:** `docs/comandos.md` agora tem uma seção própria do
  `bdgd-light replay`, exemplo no fluxo `mcp`/`aprovar` e a lista de comandos atualizada; em
  `docs/demo-profissional.md`, a seção "Trilha" passou a citar o replay como resposta operacional
  para provar o que o agente fez após a aprovação da manobra.
- **Validação local dirigida:** `uv run ruff check src/bdgd_light/agent/audit.py
  src/bdgd_light/cli.py tests/test_replay.py`, `uv run pytest tests/test_replay.py -q` e uma
  execução manual do comando sobre uma trilha sintética (`uv run bdgd-light replay E-0001 --origem
  .scratch_issue83/estado --verificar-cadeia`) para conferir a narrativa da timeline.
