# Spike LLM — GitHub Models, interface `LLMClient` e *tool calling* (issue #7)

**Resultado em uma frase:** a interface e o laço de *tool calling* estão prontos e testados sem
rede (`bdgd_light.agent`), mas o **GitHub Models foi aposentado em 30/07/2026** — a API responde
`HTTP 410 github_models_retirement_brownout` para qualquer token — então o provedor padrão do MVP
passa a ser "qualquer API compatível com `chat/completions` da OpenAI" configurada por variável de
ambiente, e o `GitHubModelsClient` fica só como *preset* nomeado que explica a aposentadoria.

| Entregue | Onde |
|---|---|
| Interface `LLMClient.chat(messages, tools) -> Text \| ToolCalls`, tipos `Message`/`ToolSpec`/`ToolCall`/`Uso` | `src/bdgd_light/agent/llm.py` |
| `interpretar_resposta()` — parsing do formato `chat/completions` (argumentos JSON, ids ausentes, erros) | idem |
| `FakeLLMClient` (fila de respostas ou regra) e `fake_soma()` (imita um modelo que chama `soma`) | idem |
| `OpenAICompatClient` (httpx; `BDGD_LLM_ENDPOINT`, `BDGD_LLM_TOKEN`, `BDGD_LLM_MODEL`; 429 com `Retry-After`; `listar_modelos()`) | idem |
| `GitHubModelsClient` (*preset*: `GITHUB_TOKEN`, endpoint e catálogo do GitHub, cabeçalhos `X-GitHub-Api-Version`) | idem |
| `conversar()` — laço de *tool calling* com histórico serializável (`Conversa.to_dict()`) | idem |
| Ferramenta de exemplo `soma(a, b)` (`SOMA`) | idem |
| CLI `bdgd-light llm PERGUNTA [--fake] [--endpoint] [--modelo] [--json]` | `src/bdgd_light/cli.py` |
| `scripts/listar_modelos.py` (destaca modelos com *tool calling*) | `scripts/` |
| 28 testes sem nenhuma chamada de rede (`FakeLLMClient` + `httpx.MockTransport`) | `tests/test_llm.py` |

## 1. O que aconteceu com o GitHub Models

Tentativa em 2026-09-09 com o token OAuth do `gh` (`gho_…`, escopos `repo, read:org, workflow`):

```
GET  https://models.github.ai/catalog/models              → HTTP 410
POST https://models.github.ai/inference/chat/completions  → HTTP 410
{"error":{"code":"github_models_retirement_brownout",
          "message":"GitHub Models is temporarily unavailable as part of a scheduled retirement brownout."}}
```

A documentação oficial (`docs.github.com/en/github-models`) confirma: *"As of July 30, 2026, GitHub
Models has been fully retired. The playground, model catalog, inference API, and bring your own key
(BYOK) are no longer available to any customer."* e aponta para o Azure AI Foundry ou para o GitHub
Copilot. Não há limite de taxa nem de tokens a observar — o serviço não existe mais. O plano
(`docs/PLANO.md`, "LLM via GitHub Models (abstraído)") e a decisão 10 da `ADR-001` foram
**alterados** por esta spike (ver §4).

## 2. Decisões

1. **A interface não muda**: `LLMClient.chat(messages, tools)` devolve `Text` ou `ToolCalls`, como
   pedia o backlog. O orquestrador do agente (F3) programa contra ela e nunca contra um SDK.
2. **Cliente real = `OpenAICompatClient`**. O formato `chat/completions` com `tools`/`tool_calls` é
   o denominador comum de OpenAI, Azure AI Foundry (`…/openai/deployments/<x>/chat/completions` ou
   o endpoint "Models as a Service"), Ollama (`http://localhost:11434/v1/chat/completions`), LM
   Studio, vLLM, OpenRouter, Mistral etc. Um só cliente HTTP cobre todos; a diferença é URL, token e
   id do modelo — os três vêm de variáveis de ambiente (`BDGD_LLM_ENDPOINT`, `BDGD_LLM_TOKEN`,
   `BDGD_LLM_MODEL`), nunca do código. Sem SDK do provedor: menos dependências e testes offline
   triviais com `httpx.MockTransport`.
3. **`GitHubModelsClient` permanece** como subclasse de `OpenAICompatClient` (endpoint, catálogo,
   `GITHUB_TOKEN`, cabeçalhos do GitHub). Ao receber 410 lança `ServicoIndisponivelError` com a
   explicação e a orientação de migrar. Custa 30 linhas e mantém o nome que o backlog, o plano e a
   ADR citam; sai quando a F3 escolher o provedor.
4. **Erros tipados** para o orquestrador decidir: `TokenAusenteError` (sem variável ou 401/403),
   `LimiteDeTaxaError(retry_after)` (429; com `max_tentativas > 1` o cliente espera o `Retry-After`
   e repete), `ServicoIndisponivelError(status)` (404/410/503), `RespostaInvalidaError` (payload ou
   argumentos de ferramenta fora do formato).
5. **Laço de *tool calling* tolerante**: ferramenta desconhecida ou exceção na execução viram
   `{"erro": ...}` devolvido ao modelo (que pode se corrigir), em vez de derrubar a conversa;
   `max_rodadas` (padrão 5) evita laço infinito. Tudo o que aconteceu fica em `Conversa`
   (mensagens, execuções com argumentos e resultados, modelo, tokens) e `to_dict()` é JSON puro —
   é o embrião do log de auditoria da decisão 6 da ADR-001.
6. **`temperature=0` por padrão** (reprodutibilidade das propostas do agente); `None` desliga o
   envio para provedores/modelos que rejeitam o parâmetro (ex.: família `o1`/`o3`).
7. **Modelo padrão**: sem GitHub Models não há catálogo "grátis" a recomendar. Padrão do cliente
   genérico: `gpt-4.1-mini` (id da OpenAI e do Azure AI Foundry, *tool calling* nativo, barato);
   `BDGD_LLM_MODEL` sobrescreve. Recomendação para a F3, em ordem: (a) **Azure AI Foundry** com
   `gpt-4.1-mini` (é para onde o GitHub aponta; mesmo formato de API); (b) **Ollama local** com um
   modelo que suporte ferramentas (`llama3.1:8b`, `qwen2.5:7b`) para desenvolvimento offline e CI
   sem segredo; (c) OpenAI direto. Medir custo/tokens no benchmark (F4) com o `Uso` que o cliente
   já devolve.

## 3. Como usar

```bash
uv sync --extra agent                                   # httpx (+ mcp, pydantic para a F3)
uv run bdgd-light llm --fake "Quanto é 2 + 3?"          # sem rede: ⚙ soma({"a": 2.0, "b": 3.0}) → 5.0
uv run pytest tests/test_llm.py -q                      # 28 testes, nenhum acesso à rede

# com um provedor compatível com a OpenAI
export BDGD_LLM_ENDPOINT=https://SEU-RECURSO.openai.azure.com/openai/v1/chat/completions
export BDGD_LLM_TOKEN=...                               # nunca no código nem no git
export BDGD_LLM_MODEL=gpt-4.1-mini
uv run scripts/listar_modelos.py --tools                # quem suporta tool calling
uv run bdgd-light llm "Quanto é 2 + 3?" --json data/conversa.json

# Ollama local (sem token real; o cliente exige a variável, qualquer valor serve)
ollama pull llama3.1:8b
BDGD_LLM_ENDPOINT=http://localhost:11434/v1/chat/completions BDGD_LLM_TOKEN=ollama \
  BDGD_LLM_MODEL=llama3.1:8b uv run bdgd-light llm "Quanto é 2 + 3?"

# preset GitHub Models (aposentado): mostra o 410 com a explicação
GITHUB_TOKEN=$(gh auth token) uv run bdgd-light llm "Quanto é 2 + 3?"
```

Em Python:

```python
from bdgd_light.agent import Ferramenta, Message, ToolSpec, cliente_do_ambiente, conversar


def downstream_customers(no: str) -> dict: ...  # ferramenta real da F3 (grafo)


FERRAMENTA = Ferramenta(
    ToolSpec(
        "downstream_customers",
        "Clientes a jusante de um PAC.",
        {"type": "object", "properties": {"no": {"type": "string"}}, "required": ["no"]},
    ),
    downstream_customers,
)
conversa = conversar(
    cliente_do_ambiente(), [Message.user("Quantos clientes há a jusante de 123?")], [FERRAMENTA]
)
conversa.resposta.content
conversa.to_dict()
```

## 4. Impacto no plano e na ADR

- `docs/PLANO.md` fala em "LLM via GitHub Models (abstraído)"; o "abstraído" salvou a decisão: o
  agente continua programando contra `LLMClient`. A `ADR-001` (decisão 10) ganhou a nota de
  alteração apontando para este documento.
- O que o GitHub Models daria de graça (catálogo multi-fornecedor com um token que o repositório
  já tem no Actions) precisa ser substituído por um segredo de provedor no repositório
  (`BDGD_LLM_TOKEN`) quando a F3 rodar o agente no CI; até lá, o CI usa só o `FakeLLMClient`.

## 5. Próximos passos (F3)

1. Escolher o provedor (recomendação: Azure AI Foundry + `gpt-4.1-mini`, ou Ollama para
   desenvolvimento) e guardar `BDGD_LLM_TOKEN` como *secret* do repositório.
2. Expor as ferramentas do grafo/gêmeo (`load_feeder`, `downstream_customers`, `propose_flisr`,
   `run_powerflow`…) como `Ferramenta` — ou, conforme a decisão 9 da ADR, via servidor MCP com o
   mesmo `ToolSpec`.
3. Transformar `Conversa.to_dict()` no registro do log de auditoria (JSON Lines, hash encadeado) e
   acrescentar o verificador determinístico antes de qualquer ferramenta de escrita.
4. Suporte a *streaming* e a mensagens multimodais só se o console precisar.
