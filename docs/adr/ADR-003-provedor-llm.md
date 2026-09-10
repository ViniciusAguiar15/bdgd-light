# ADR-003 — Provedor de LLM: OpenAI como padrão, Gemini pelo endpoint compatível, perfis nomeados e segredos só no ambiente

| | |
|---|---|
| Status | **Aceita** (implementada na issue #31; detalha a decisão 10 da ADR-001, já alterada pela spike da issue #7, que fica como está) |
| Data | 2026-09-10 |
| Origem | `docs/backlog/10-adr-003-llm.md`, `docs/spike-llm.md`, `docs/adr/ADR-001-stack.md` (decisão 10), `docs/escopo-cidade.md` (v3) |
| Issue | #31 |

Mesmo formato das ADRs anteriores: **contexto → decisão → consequências**, com as medidas da chamada
real registradas em `docs/spike-llm.md` §6.

---

## 1. OpenAI (`gpt-4.1-mini` por padrão; `gpt-4.1`/`gpt-5` no benchmark) é o provedor padrão

**Contexto.** A spike da issue #7 encontrou o GitHub Models aposentado (410) e deixou o cliente real
genérico (`OpenAICompatClient`, formato `chat/completions` + `tools`), mas sem escolher provedor: a
recomendação provisória era Azure AI Foundry ou Ollama. A F3 (agente orquestrador, issue #34) e a F4
(benchmark, #36) precisam de um provedor com *tool calling* estável, preços públicos por token e um
modelo barato para as iterações de desenvolvimento. O mantenedor já tem chave da OpenAI
(`OPENAI_API_KEY`) e do Google AI Studio (`GEMINI_API_KEY`).

**Decisão.** Perfil **`openai`** é o padrão de `cliente_do_ambiente()`: endpoint
`https://api.openai.com/v1/chat/completions`, token em `OPENAI_API_KEY`, modelo padrão
**`gpt-4.1-mini`** (tool calling nativo, US$ 0,40/1,60 por milhão de tokens de entrada/saída na
tabela pública de 2025 — conferir). `gpt-4.1` (US$ 2/8) e `gpt-5` (US$ 1,25/10) entram só por
`BDGD_LLM_MODEL`/`--modelo`, para o benchmark comparar qualidade × custo. Nenhum SDK: o cliente
HTTP continua sendo o `OpenAICompatClient` com `httpx`, testado offline por `MockTransport`.

**Consequências.** Custo real por conversa mínima de tool calling (≈ 300 tokens) fica na casa de
US$ 0,0002 com `gpt-4.1-mini`; o log de auditoria (`conversa.fim` com `uso_total`) e o novo campo
`segundos` da `Conversa` dão tokens e latência por conversa para o benchmark. A chave é um segredo
de conta pessoal: entra só por variável de ambiente local e por *repository secret* no Actions
(`gh secret set OPENAI_API_KEY`), nunca no código — o teste de varredura de `tests/test_llm.py`
(`test_tokens_so_por_ambiente`) falha se um token literal aparecer em `agent/llm.py`. Azure AI
Foundry (mesmo formato de API) continua possível por `BDGD_LLM_ENDPOINT`/`BDGD_LLM_TOKEN`, sem
perfil próprio por ora.

## 2. Gemini pelo endpoint compatível com a OpenAI é o segundo provedor, para comparação

**Contexto.** O benchmark (#36) quer ao menos dois fornecedores diferentes para que a conclusão
não seja "o agente funciona com um modelo". O Google AI Studio expõe um endpoint compatível com a
API da OpenAI (`https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`) que
aceita `tools`/`tool_calls` e `/models`, com chave por `GEMINI_API_KEY` e camada gratuita.

**Decisão.** Perfil **`gemini`** com esse endpoint e modelo padrão **`gemini-2.5-flash`**
(US$ 0,30/2,50 por milhão de tokens, tabela de 2026-09-10). Validado nesta ADR com a chave real
(`docs/spike-llm.md` §6): `bdgd-light llm --provider gemini "Quanto é 2 + 3?"` chamou `soma(2, 3)`
e respondeu em 1,4–1,8 s com 277 tokens; `scripts/listar_modelos.py --provider gemini --tools`
listou 40 modelos com ids `models/gemini-…`. **`gemini-2.5-flash-lite` fica fora**: na mesma
pergunta devolveu `message` vazia (sem `content` nem `tool_calls`, 0 tokens de saída), que o cliente
recusa com `RespostaInvalidaError`. Vertex AI (autenticação por conta de serviço, outro SDK) fica
**fora por ora**: o endpoint do AI Studio basta para a POC.

**Consequências.** Toda comparação do benchmark roda com o mesmo prompt, as mesmas ferramentas e o
mesmo laço `conversar()` nos dois provedores — só muda o perfil. Diferenças de formato observadas
(argumentos da ferramenta chegam como inteiros `{"b": 3, "a": 2}` no Gemini e como
`{"a": 2.0, "b": 3.0}` no fake/OpenAI; ids de modelo com prefixo `models/`) são absorvidas pelo
parser existente. Limites de taxa da camada gratuita variam por *tier* da chave; na chamada de
teste não houve 429, e o cliente já trata `Retry-After` quando `max_tentativas > 1`.

## 3. Perfis nomeados (`BDGD_LLM_PROVIDER`, `--provider`) em vez de três variáveis soltas

**Contexto.** Até aqui o operador precisava exportar `BDGD_LLM_ENDPOINT`, `BDGD_LLM_TOKEN` e
`BDGD_LLM_MODEL` coerentes entre si; trocar de provedor no benchmark significava trocar as três.

**Decisão.** `bdgd_light.agent.llm.PERFIS` guarda, por nome, endpoint, modelo padrão, nome da
variável do token e descrição: **`openai`**, **`gemini`**, **`ollama`**
(`http://localhost:11434/v1/chat/completions`, `llama3.1:8b`, sem chave — desenvolvimento
offline) e **`fake`** (`FakeLLMClient`, testes e CI sem segredo). `cliente_por_perfil(nome, modelo)`
monta o cliente; `cliente_do_ambiente(modelo, provider)` resolve nesta ordem:
`provider`/`BDGD_LLM_PROVIDER` → `BDGD_LLM_ENDPOINT` (qualquer endpoint compatível, com
`BDGD_LLM_TOKEN`) → `OPENAI_API_KEY` → `GEMINI_API_KEY` → `GITHUB_TOKEN` (preset aposentado) →
`TokenAusenteError` listando as opções. O modelo segue a precedência argumento → `BDGD_LLM_MODEL`
→ padrão do perfil. `bdgd-light llm --provider …` e `scripts/listar_modelos.py --provider …`
expõem o mesmo seletor; `--fake` vira atalho de `--provider fake`.

**Consequências.** Com só a chave no ambiente, `uv run bdgd-light llm "Quanto é 2 + 3?"` já
funciona (OpenAI se houver `OPENAI_API_KEY`, senão Gemini). O benchmark alterna provedores por
`--provider`. Adicionar um provedor (Azure, OpenRouter, Mistral…) é uma linha em `PERFIS`.
`GitHubModelsClient` permanece como preset que falha com a explicação da aposentadoria, até a F3
concluir; a saída do CLI passa a mostrar a latência (`… 277 tokens, 1.8 s`).

## 4. CI: testes sem rede e job `llm-smoke` opcional, que só roda com o segredo cadastrado

**Contexto.** O CI não pode depender de serviço externo nem expor segredo em *fork*; mas uma
chamada real periódica é o único jeito de perceber que um provedor mudou de formato (como o 410 do
GitHub Models).

**Decisão.** `pytest` continua 100 % offline (`MockTransport`, `FakeLLMClient`; a fixture
`sem_segredos` apaga `OPENAI_API_KEY`, `GEMINI_API_KEY`, `BDGD_LLM_PROVIDER` etc. antes de cada
teste). O job **`llm-smoke`** do `ci.yml` recebe os segredos como variáveis de ambiente do job e
roda `bdgd-light llm --provider fake` sempre e `--provider openai`/`--provider gemini` só quando
`env.OPENAI_API_KEY`/`env.GEMINI_API_KEY` não estão vazios (o contexto `secrets` não é permitido no
`if` de job; no de passo funciona via `env`), com `continue-on-error: true` — cota ou 5xx do
provedor não bloqueiam o PR. Os segredos **não** são criados automaticamente: o mantenedor roda
`gh secret set OPENAI_API_KEY` e `gh secret set GEMINI_API_KEY` quando quiser ligar o smoke.

**Consequências.** Sem segredos o job passa em segundos (fake + aviso `::notice::`); com eles, cada
push a `main`/PR custa duas chamadas mínimas (< US$ 0,001). Em *fork* os segredos não existem e o
job continua verde.

---

## Resumo das alternativas descartadas

| alternativa | por quê não |
|---|---|
| GitHub Models como provedor | aposentado em 30/07/2026 (410); ver `docs/spike-llm.md` §1 |
| Azure AI Foundry como padrão | exige conta/recurso Azure que o mantenedor não tem hoje; continua acessível por `BDGD_LLM_ENDPOINT` |
| SDKs oficiais (`openai`, `google-genai`) | duas dependências e dois formatos para manter; o formato `chat/completions` cobre os dois provedores |
| Vertex AI para o Gemini | autenticação por conta de serviço e SDK próprio; o endpoint do AI Studio basta para a POC |
| `gemini-2.5-flash-lite` como padrão do Gemini | devolveu mensagem vazia na chamada de tool calling de teste |
| Criar os *secrets* do repositório pela automação | chave pessoal do mantenedor; decisão e custo são dele (`gh secret set …`) |
