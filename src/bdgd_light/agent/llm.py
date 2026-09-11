"""Cliente LLM abstraído: interface ``LLMClient`` com *tool calling*, cliente *fake* para testes e
cliente HTTP para qualquer API compatível com ``chat/completions`` da OpenAI.

Provedores por **perfil** (ADR-003): ``openai`` (padrão), ``gemini`` (endpoint compatível com a
OpenAI do Google AI Studio), ``ollama`` (local, sem chave) e ``fake`` (testes). O perfil preenche
endpoint, modelo padrão e o nome da variável do token (``OPENAI_API_KEY``, ``GEMINI_API_KEY``);
``BDGD_LLM_PROVIDER`` ou ``bdgd-light llm --provider`` escolhem, e ``BDGD_LLM_ENDPOINT`` +
``BDGD_LLM_TOKEN`` continuam valendo para qualquer outro endpoint compatível.

O alvo original do spike (issue #7) era o GitHub Models, mas o serviço foi **aposentado em
30/07/2026** e o endpoint responde ``410 github_models_retirement_brownout``. Por isso o cliente
real é genérico (``OpenAICompatClient``) e ``GitHubModelsClient`` fica como *preset* nomeado que
falha com ``ServicoIndisponivelError`` explicando a aposentadoria. Ver ``docs/spike-llm.md``.

Segredos só por variável de ambiente; nada no código.
"""

from __future__ import annotations

import json
import os
import time
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from bdgd_light.agent.audit import AuditLog

ENV_MODELO = "BDGD_LLM_MODEL"
ENV_ENDPOINT = "BDGD_LLM_ENDPOINT"
ENV_TOKEN = "BDGD_LLM_TOKEN"
ENV_GITHUB_TOKEN = "GITHUB_TOKEN"
ENV_PROVIDER = "BDGD_LLM_PROVIDER"
ENV_OPENAI_KEY = "OPENAI_API_KEY"
ENV_GEMINI_KEY = "GEMINI_API_KEY"

# ---------------------------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolSpec:
    """Descrição de uma ferramenta no formato *function calling* (JSON Schema em ``parameters``)."""

    name: str
    description: str
    parameters: Mapping[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )

    def to_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": dict(self.parameters),
            },
        }


@dataclass(frozen=True)
class ToolCall:
    """Pedido do modelo para executar ``name`` com ``arguments`` (já decodificados)."""

    id: str
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)

    def to_openai(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": json.dumps(self.arguments)},
        }


@dataclass(frozen=True)
class Message:
    """Mensagem da conversa (``system``, ``user``, ``assistant`` ou ``tool``)."""

    role: str
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None

    @classmethod
    def system(cls, texto: str) -> Message:
        return cls("system", texto)

    @classmethod
    def user(cls, texto: str) -> Message:
        return cls("user", texto)

    @classmethod
    def assistant(cls, texto: str | None = None, tool_calls: Iterable[ToolCall] = ()) -> Message:
        return cls("assistant", texto, tuple(tool_calls))

    @classmethod
    def tool(cls, chamada: ToolCall, resultado: Any) -> Message:
        """Resposta de uma ferramenta; ``resultado`` vira JSON (objetos estranhos via ``str``)."""
        conteudo = json.dumps(resultado, ensure_ascii=False, default=str)
        return cls("tool", conteudo, tool_call_id=chamada.id)

    def to_openai(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [c.to_openai() for c in self.tool_calls]
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        return d


@dataclass(frozen=True)
class Uso:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def de_payload(cls, dados: Mapping[str, Any] | None) -> Uso | None:
        if not dados:
            return None
        return cls(
            int(dados.get("prompt_tokens") or 0),
            int(dados.get("completion_tokens") or 0),
            int(dados.get("total_tokens") or 0),
        )


@dataclass(frozen=True)
class Text:
    """Resposta final em texto."""

    content: str
    uso: Uso | None = None
    modelo: str | None = None
    finish_reason: str | None = None


@dataclass(frozen=True)
class ToolCalls:
    """O modelo pediu ferramentas; ``content`` pode trazer um texto de acompanhamento."""

    calls: tuple[ToolCall, ...]
    content: str | None = None
    uso: Uso | None = None
    modelo: str | None = None
    finish_reason: str | None = None

    def __iter__(self):
        return iter(self.calls)

    def __len__(self) -> int:
        return len(self.calls)


Resposta = Text | ToolCalls


@runtime_checkable
class LLMClient(Protocol):
    """Contrato mínimo do agente: ``chat(messages, tools) -> Text | ToolCalls``."""

    def chat(self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()) -> Resposta: ...


# ---------------------------------------------------------------------------------------------
# Erros
# ---------------------------------------------------------------------------------------------


class LLMError(Exception):
    """Erro genérico do cliente LLM."""


class TokenAusenteError(LLMError):
    """Nenhum token na variável de ambiente esperada (ou token recusado)."""


class ServicoIndisponivelError(LLMError):
    """O provedor recusou o serviço (410 aposentado, 503 etc.)."""

    def __init__(self, mensagem: str, status: int | None = None):
        super().__init__(mensagem)
        self.status = status


class LimiteDeTaxaError(LLMError):
    """HTTP 429; ``retry_after`` em segundos quando o provedor informa."""

    def __init__(self, mensagem: str, retry_after: float | None = None):
        super().__init__(mensagem)
        self.retry_after = retry_after


class RespostaInvalidaError(LLMError):
    """Payload fora do formato ``chat/completions`` ou argumentos de ferramenta indecodificáveis."""


class RespostaVaziaError(RespostaInvalidaError):
    """Mensagem sem ``content`` nem ``tool_calls`` — o Gemini devolve isso com ``finish_reason``
    ``MALFORMED_FUNCTION_CALL`` (falha transitória do modelo ao montar a chamada); vale repetir.
    ``uso`` guarda os tokens cobrados pela tentativa falha (o payload traz ``usage``)."""

    def __init__(self, mensagem: str, uso: Uso | None = None):
        super().__init__(mensagem)
        self.uso = uso


LEMBRETE_CHAMADA = (
    "Sua última resposta veio vazia (chamada de ferramenta malformada). Refaça: chame a próxima "
    "ferramenta com argumentos JSON válidos (um objeto, só os parâmetros do esquema) ou responda "
    "em texto."
)


# ---------------------------------------------------------------------------------------------
# Parsing do formato chat/completions
# ---------------------------------------------------------------------------------------------


def interpretar_resposta(payload: Mapping[str, Any]) -> Resposta:
    """Converte um payload ``chat/completions`` (OpenAI, GitHub Models, Azure, Ollama) em
    ``Text`` ou ``ToolCalls``. Argumentos das ferramentas chegam como *string* JSON e são
    decodificados aqui; ``""`` vira ``{}``."""
    choices = payload.get("choices") or []
    if not choices:
        raise RespostaInvalidaError(f"payload sem 'choices': {_resumo(payload)}")
    escolha = choices[0]
    mensagem = escolha.get("message") or {}
    uso = Uso.de_payload(payload.get("usage"))
    modelo = payload.get("model")
    fim = escolha.get("finish_reason")
    brutos = mensagem.get("tool_calls") or []
    if brutos:
        chamadas = tuple(_interpretar_tool_call(b, i) for i, b in enumerate(brutos))
        return ToolCalls(chamadas, mensagem.get("content"), uso, modelo, fim)
    conteudo = mensagem.get("content")
    if conteudo is None:
        raise RespostaVaziaError(
            f"mensagem sem 'content' nem 'tool_calls' (finish_reason={fim!r}): {_resumo(payload)}",
            uso=uso,
        )
    return Text(str(conteudo), uso, modelo, fim)


def _interpretar_tool_call(bruto: Mapping[str, Any], indice: int) -> ToolCall:
    funcao = bruto.get("function") or {}
    nome = funcao.get("name")
    if not nome:
        raise RespostaInvalidaError(f"tool_call sem nome: {bruto}")
    args = funcao.get("arguments", {})
    if isinstance(args, str):
        texto = args.strip()
        if not texto:
            args = {}
        else:
            try:
                args = json.loads(texto)
            except json.JSONDecodeError as exc:
                raise RespostaInvalidaError(
                    f"argumentos da ferramenta {nome!r} não são JSON: {texto[:200]!r}"
                ) from exc
    if not isinstance(args, Mapping):
        raise RespostaInvalidaError(f"argumentos da ferramenta {nome!r} não são objeto: {args!r}")
    return ToolCall(str(bruto.get("id") or f"call_{indice}"), str(nome), dict(args))


def _resumo(payload: Any, limite: int = 300) -> str:
    texto = json.dumps(payload, ensure_ascii=False, default=str)
    return texto if len(texto) <= limite else texto[:limite] + "…"


# ---------------------------------------------------------------------------------------------
# Cliente fake (testes e demonstração offline)
# ---------------------------------------------------------------------------------------------

Regra = Callable[[Sequence[Message], Sequence[ToolSpec]], Resposta]


class FakeLLMClient:
    """Cliente determinístico sem rede.

    Devolve, em ordem, as ``respostas`` enfileiradas (``Text``/``ToolCalls`` prontos, uma *string*
    que vira ``Text`` ou um payload ``chat/completions`` que passa por ``interpretar_resposta`` —
    útil para testar o parsing). Esgotada a fila, usa ``regra(messages, tools)`` se houver. Toda
    chamada fica em ``chamadas`` para inspeção.
    """

    def __init__(
        self,
        respostas: Iterable[Resposta | Mapping[str, Any] | str] = (),
        *,
        regra: Regra | None = None,
    ):
        self._fila: deque[Resposta] = deque(_normalizar(r) for r in respostas)
        self._regra = regra
        self.chamadas: list[tuple[tuple[Message, ...], tuple[ToolSpec, ...]]] = []

    def chat(self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()) -> Resposta:
        self.chamadas.append((tuple(messages), tuple(tools)))
        if self._fila:
            return self._fila.popleft()
        if self._regra is not None:
            return self._regra(messages, tools)
        raise LLMError("FakeLLMClient sem resposta enfileirada nem regra.")

    @property
    def restantes(self) -> int:
        return len(self._fila)


def _normalizar(r: Resposta | Mapping[str, Any] | str) -> Resposta:
    if isinstance(r, Text | ToolCalls):
        return r
    if isinstance(r, str):
        return Text(r)
    return interpretar_resposta(r)


def fake_soma() -> FakeLLMClient:
    """Fake que imita um modelo usando a ferramenta ``soma``: com dois números na última mensagem
    do usuário pede ``soma(a, b)``; ao receber o resultado, responde em texto."""

    def regra(messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Resposta:
        ultima = messages[-1]
        uso = _uso_estimado(messages)
        if ultima.role == "tool":
            try:
                valor = json.loads(ultima.content or "null")
            except json.JSONDecodeError:
                valor = ultima.content
            texto = f"O resultado é {_fmt_num(valor)}."
            return Text(texto, uso=uso, modelo="fake", finish_reason="stop")
        numeros = _numeros(ultima.content or "")
        if len(numeros) >= 2 and any(t.name == "soma" for t in tools):
            a, b = numeros[0], numeros[1]
            chamada = ToolCall("call_fake_1", "soma", {"a": a, "b": b})
            return ToolCalls((chamada,), None, uso=uso, modelo="fake", finish_reason="tool_calls")
        return Text(
            "Não encontrei dois números para somar.", uso=uso, modelo="fake", finish_reason="stop"
        )

    return FakeLLMClient(regra=regra)


def _uso_estimado(messages: Sequence[Message], completion: int = 12) -> Uso:
    """Contagem de tokens fictícia (~4 caracteres por token) para o fake alimentar o log de
    auditoria e o benchmark com números plausíveis e determinísticos."""
    caracteres = sum(len(m.content or "") for m in messages)
    prompt = 10 + caracteres // 4 + 8 * sum(len(m.tool_calls) for m in messages)
    return Uso(prompt, completion, prompt + completion)


def _numeros(texto: str) -> list[float]:
    saida: list[float] = []
    for pedaco in texto.replace(",", ".").replace("?", " ").split():
        try:
            saida.append(float(pedaco))
        except ValueError:
            continue
    return saida


def _fmt_num(valor: Any) -> str:
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor)


# ---------------------------------------------------------------------------------------------
# Cliente HTTP compatível com chat/completions da OpenAI
# ---------------------------------------------------------------------------------------------


class OpenAICompatClient:
    """Cliente para qualquer endpoint ``…/chat/completions`` compatível com a OpenAI (Azure AI
    Foundry, OpenAI, Ollama ``http://localhost:11434/v1/chat/completions``, LM Studio…).

    ``token`` vem por parâmetro ou de ``BDGD_LLM_TOKEN``; ``modelo`` de ``BDGD_LLM_MODEL``. Com
    ``max_tentativas > 1`` repete em 429 respeitando ``Retry-After`` e em resposta vazia
    (``RespostaVaziaError``, ex.: ``MALFORMED_FUNCTION_CALL`` do Gemini); ``dormir`` é injetável
    para testes. ``transporte`` aceita um ``httpx.MockTransport`` para exercitar o cliente sem rede.
    """

    MODELO_PADRAO = "gpt-4.1-mini"

    def __init__(
        self,
        endpoint: str,
        *,
        modelo: str | None = None,
        token: str | None = None,
        env_token: str = ENV_TOKEN,
        url_modelos: str | None = None,
        cabecalhos: Mapping[str, str] | None = None,
        temperatura: float | None = 0.0,
        timeout: float = 60.0,
        max_tentativas: int = 1,
        dormir: Callable[[float], None] = time.sleep,
        transporte: Any = None,
    ):
        import httpx

        self.endpoint = endpoint
        self.url_modelos = url_modelos or endpoint.rsplit("/chat/completions", 1)[0] + "/models"
        self.modelo = modelo or os.environ.get(ENV_MODELO) or self.MODELO_PADRAO
        self.token = token or os.environ.get(env_token)
        if not self.token:
            raise TokenAusenteError(
                f"defina a variável de ambiente {env_token} (nunca coloque o token no código)."
            )
        self.temperatura = temperatura
        self.max_tentativas = max(1, max_tentativas)
        self._dormir = dormir
        self._cabecalhos = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            **(cabecalhos or {}),
        }
        self._http = httpx.Client(timeout=timeout, transport=transporte)
        self.ultimo_uso: Uso | None = None

    # -- contexto -----------------------------------------------------------------------------
    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> OpenAICompatClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- API ----------------------------------------------------------------------------------
    def montar_payload(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] = (),
        *,
        temperatura: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.modelo,
            "messages": [m.to_openai() for m in messages],
        }
        if tools:
            payload["tools"] = [t.to_openai() for t in tools]
            payload["tool_choice"] = "auto"
        temperatura = self.temperatura if temperatura is None else temperatura
        if temperatura is not None:
            payload["temperature"] = temperatura
        return payload

    def temperatura_da_tentativa(self, tentativa: int) -> float | None:
        """Temperatura da ``tentativa`` (1 = pedido original) de um pedido repetido por resposta
        vazia: sobe 0,5 por repetição até 1,0. Com temperatura 0 o mesmo pedido tende a reproduzir
        a mesma chamada malformada (``MALFORMED_FUNCTION_CALL`` do Gemini após ``isolate_fault``:
        3 falhas em 3 no benchmark de 2026-09-11, as três com as 3 tentativas iguais)."""
        if tentativa <= 1 or self.temperatura is None:
            return self.temperatura
        return min(1.0, self.temperatura + 0.5 * (tentativa - 1))

    def chat(self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()) -> Resposta:
        payload = self.montar_payload(messages, tools)
        tentativa = 0
        usos_falhos: list[Uso] = []
        while True:
            tentativa += 1
            dados = self._post(payload)
            try:
                resposta = interpretar_resposta(dados)
            except RespostaVaziaError as exc:
                if exc.uso is not None:
                    usos_falhos.append(exc.uso)
                if tentativa >= self.max_tentativas:
                    exc.uso = _somar_uso(usos_falhos)  # tudo o que as tentativas custaram
                    raise
                self._dormir(1.0)
                # repetir o mesmo pedido costuma falhar igual: acrescenta um lembrete (só neste
                # pedido; o histórico do chamador não muda) e sobe a temperatura para o modelo
                # refazer a chamada de outro jeito
                payload = self.montar_payload(
                    [*messages, Message.user(LEMBRETE_CHAMADA)],
                    tools,
                    temperatura=self.temperatura_da_tentativa(tentativa + 1),
                )
                continue
            self.ultimo_uso = resposta.uso
            return resposta

    def listar_modelos(self) -> list[dict[str, Any]]:
        """``GET`` na lista de modelos (``/models`` da OpenAI devolve ``{"data": [...]}``; o
        catálogo do GitHub devolvia uma lista)."""
        r = self._http.get(self.url_modelos, headers=self._cabecalhos)
        self._checar(r)
        dados = r.json()
        if isinstance(dados, Mapping):
            dados = dados.get("data") or dados.get("models") or []
        return list(dados)

    # -- internos -----------------------------------------------------------------------------
    def _post(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        tentativa = 0
        while True:
            tentativa += 1
            r = self._http.post(self.endpoint, json=payload, headers=self._cabecalhos)
            if r.status_code == 429 and tentativa < self.max_tentativas:
                self._dormir(_retry_after(r.headers.get("retry-after")) or 1.0)
                continue
            self._checar(r)
            try:
                return r.json()
            except ValueError as exc:
                raise RespostaInvalidaError(f"resposta não é JSON: {r.text[:200]!r}") from exc

    def _checar(self, r) -> None:
        if r.status_code < 400:
            return
        detalhe = _mensagem_de_erro(r)
        if r.status_code == 429:
            raise LimiteDeTaxaError(
                f"429 limite de taxa: {detalhe}", _retry_after(r.headers.get("retry-after"))
            )
        if r.status_code in (401, 403):
            raise TokenAusenteError(f"{r.status_code} não autorizado: {detalhe}")
        if r.status_code in (404, 410, 503):
            raise ServicoIndisponivelError(f"{r.status_code} {detalhe}", r.status_code)
        raise LLMError(f"HTTP {r.status_code}: {detalhe}")


def _mensagem_de_erro(r) -> str:
    try:
        dados = r.json()
    except ValueError:
        return r.text[:300]
    erro = dados.get("error") if isinstance(dados, Mapping) else None
    if isinstance(erro, Mapping):
        codigo = erro.get("code")
        msg = erro.get("message") or ""
        return f"{codigo}: {msg}" if codigo else str(msg)
    return _resumo(dados)


def _retry_after(valor: str | None) -> float | None:
    if not valor:
        return None
    try:
        return float(valor)
    except ValueError:
        return None


class GitHubModelsClient(OpenAICompatClient):
    """*Preset* do GitHub Models (``GITHUB_TOKEN``, ``BDGD_LLM_MODEL``).

    **Aposentado em 30/07/2026**: o endpoint responde ``410 github_models_retirement_brownout``,
    que aqui vira ``ServicoIndisponivelError`` com a explicação. Mantido para a interface e a
    documentação do spike; use ``OpenAICompatClient`` com outro provedor.
    """

    ENDPOINT = "https://models.github.ai/inference/chat/completions"
    CATALOGO = "https://models.github.ai/catalog/models"
    MODELO_PADRAO = "openai/gpt-4.1-mini"
    AVISO_APOSENTADO = (
        "o GitHub Models foi aposentado em 30/07/2026 (playground, catálogo e API de inferência); "
        "aponte BDGD_LLM_ENDPOINT/BDGD_LLM_TOKEN para outro provedor compatível com a OpenAI "
        "(ver docs/spike-llm.md)"
    )

    def __init__(self, *, modelo: str | None = None, token: str | None = None, **opcoes):
        opcoes.setdefault("url_modelos", self.CATALOGO)
        opcoes.setdefault(
            "cabecalhos",
            {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
        )
        super().__init__(
            self.ENDPOINT, modelo=modelo, token=token, env_token=ENV_GITHUB_TOKEN, **opcoes
        )

    def _checar(self, r) -> None:
        if r.status_code == 410:
            raise ServicoIndisponivelError(
                f"410 {_mensagem_de_erro(r)} — {self.AVISO_APOSENTADO}", 410
            )
        super()._checar(r)


@dataclass(frozen=True)
class Perfil:
    """Perfil nomeado de provedor (ADR-003): endpoint, modelo padrão e variável do token.

    ``token_padrao`` cobre provedores locais sem chave (Ollama exige o cabeçalho, não o valor).
    """

    nome: str
    endpoint: str
    modelo: str
    env_token: str
    descricao: str = ""
    token_padrao: str | None = None
    url_modelos: str | None = None


PERFIS: dict[str, Perfil] = {
    "openai": Perfil(
        "openai",
        "https://api.openai.com/v1/chat/completions",
        "gpt-4.1-mini",
        ENV_OPENAI_KEY,
        "OpenAI (padrão): tool calling nativo; gpt-4.1/gpt-5 via BDGD_LLM_MODEL",
    ),
    "gemini": Perfil(
        "gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "gemini-2.5-flash",
        ENV_GEMINI_KEY,
        "Google Gemini pelo endpoint compatível com a OpenAI (Google AI Studio)",
    ),
    "ollama": Perfil(
        "ollama",
        "http://localhost:11434/v1/chat/completions",
        "llama3.1:8b",
        "OLLAMA_API_KEY",
        "Ollama local (dev offline); qualquer modelo com tool calling (llama3.1, qwen2.5…)",
        token_padrao="ollama",
    ),
    "fake": Perfil("fake", "", "fake", "", "FakeLLMClient determinístico (testes, CI sem segredo)"),
}
PROVEDOR_PADRAO = "openai"


def cliente_por_perfil(
    nome: str, modelo: str | None = None, *, audit: AuditLog | None = None, **opcoes
) -> LLMClient:
    """Cliente de um perfil (``openai``, ``gemini``, ``ollama``, ``fake``). Precedência do modelo:
    argumento → ``BDGD_LLM_MODEL`` → padrão do perfil. Token da variável do perfil (ou
    ``token_padrao``); ``ValueError`` para perfil desconhecido. Com ``audit``, grava um registro
    ``llm.cliente`` com o perfil e o modelo resolvidos (proveniência para o benchmark)."""
    perfil = PERFIS.get(nome.lower().strip()) if nome else None
    if perfil is None:
        raise ValueError(f"perfil LLM desconhecido: {nome!r}; use um de {', '.join(PERFIS)}")
    if perfil.nome == "fake":
        cliente: LLMClient = fake_soma()
    else:
        token = os.environ.get(perfil.env_token) or perfil.token_padrao
        # provedores reais: 3 tentativas em 429 e em resposta vazia (MALFORMED_FUNCTION_CALL)
        opcoes.setdefault("max_tentativas", 3)
        cliente = OpenAICompatClient(
            perfil.endpoint,
            modelo=modelo or os.environ.get(ENV_MODELO) or perfil.modelo,
            token=token,
            env_token=perfil.env_token,
            url_modelos=perfil.url_modelos,
            **opcoes,
        )
    registrar_cliente(audit, cliente, perfil=perfil.nome, origem="perfil")
    return cliente


def cliente_do_ambiente(
    modelo: str | None = None,
    provider: str | None = None,
    *,
    audit: AuditLog | None = None,
    **opcoes,
) -> LLMClient:
    """Escolhe o cliente pelo ambiente, nesta ordem: ``provider``/``BDGD_LLM_PROVIDER`` (perfil da
    ADR-003) → ``BDGD_LLM_ENDPOINT`` (+ ``BDGD_LLM_TOKEN``, qualquer endpoint compatível) →
    ``OPENAI_API_KEY`` (perfil ``openai``, o padrão) → ``GEMINI_API_KEY`` (``gemini``) →
    ``GITHUB_TOKEN`` (``GitHubModelsClient``, aposentado) → ``TokenAusenteError``.

    Com ``audit``, o cliente resolvido (perfil, modelo, endpoint e de onde veio a escolha) vira um
    registro ``llm.cliente`` — quem lê o log sabe a proveniência de cada execução."""
    nome = provider or os.environ.get(ENV_PROVIDER)
    if nome:
        return cliente_por_perfil(
            nome,
            modelo,
            audit=audit,
            **opcoes,
        )
    endpoint = os.environ.get(ENV_ENDPOINT)
    if endpoint:
        cliente: LLMClient = OpenAICompatClient(endpoint, modelo=modelo, **opcoes)
        registrar_cliente(audit, cliente, perfil=None, origem=ENV_ENDPOINT)
        return cliente
    for nome_perfil in (PROVEDOR_PADRAO, "gemini"):
        if os.environ.get(PERFIS[nome_perfil].env_token):
            cliente = cliente_por_perfil(nome_perfil, modelo, **opcoes)
            registrar_cliente(
                audit, cliente, perfil=nome_perfil, origem=PERFIS[nome_perfil].env_token
            )
            return cliente
    if os.environ.get(ENV_GITHUB_TOKEN):
        cliente = GitHubModelsClient(modelo=modelo, **opcoes)
        registrar_cliente(audit, cliente, perfil="github-models", origem=ENV_GITHUB_TOKEN)
        return cliente
    raise TokenAusenteError(
        f"defina {ENV_OPENAI_KEY} (perfil openai, padrão) ou {ENV_GEMINI_KEY} (gemini), ou "
        f"{ENV_PROVIDER}=ollama para um Ollama local, ou {ENV_ENDPOINT} e {ENV_TOKEN} para outro "
        f"provedor compatível com a OpenAI; para testes use {ENV_PROVIDER}=fake (FakeLLMClient)."
    )


def descrever_cliente(cliente: LLMClient) -> dict[str, Any]:
    """Proveniência de um cliente: ``tipo`` (classe), ``modelo`` e ``endpoint`` (sem token)."""
    return {
        "tipo": type(cliente).__name__,
        "modelo": getattr(cliente, "modelo", None),
        "endpoint": getattr(cliente, "endpoint", None),
    }


def registrar_cliente(
    audit: AuditLog | None, cliente: LLMClient, *, perfil: str | None, origem: str
) -> None:
    """Registro ``llm.cliente`` no log de auditoria: perfil e modelo resolvidos e a ``origem`` da
    escolha (argumento/perfil, ``BDGD_LLM_ENDPOINT`` ou a variável de chave encontrada). Nunca
    grava o token."""
    if audit is None:
        return
    audit.registrar("llm.cliente", perfil=perfil, origem=origem, **descrever_cliente(cliente))


# ---------------------------------------------------------------------------------------------
# Laço de tool calling
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Ferramenta:
    """Par (descrição para o modelo, função Python)."""

    spec: ToolSpec
    funcao: Callable[..., Any]

    @property
    def name(self) -> str:
        return self.spec.name


@dataclass
class Conversa:
    """Resultado de ``conversar``: histórico completo (serializável) e a resposta final."""

    mensagens: list[Message]
    resposta: Text
    rodadas: int
    execucoes: list[tuple[ToolCall, Any]] = field(default_factory=list)
    hash_auditoria: str | None = None
    """Hash do último registro gravado no ``AuditLog`` (liga a conversa ao log)."""
    _usos: list[Uso] = field(default_factory=list, repr=False)
    segundos: float = 0.0
    """Tempo de parede das chamadas ao modelo (todas as rodadas), para latência/benchmark."""

    @property
    def uso_total(self) -> Uso | None:
        """Soma do uso de tokens de todas as rodadas (quando o cliente informa)."""
        return _somar_uso(self._usos)

    def to_dict(self) -> dict[str, Any]:
        uso_total = self.uso_total
        return {
            "mensagens": [m.to_openai() for m in self.mensagens],
            "resposta": self.resposta.content,
            "rodadas": self.rodadas,
            "execucoes": [
                {"id": c.id, "ferramenta": c.name, "argumentos": dict(c.arguments), "resultado": r}
                for c, r in self.execucoes
            ],
            "modelo": self.resposta.modelo,
            "uso": None if self.resposta.uso is None else vars(self.resposta.uso),
            "uso_total": None if uso_total is None else vars(uso_total),
            "hash_auditoria": self.hash_auditoria,
            "segundos": round(self.segundos, 3),
        }


@dataclass
class ConversaParcial:
    """O que uma conversa interrompida por erro do provedor já havia consumido (anexado à
    exceção como ``exc.parcial``): rodadas, usos de tokens (inclusive das tentativas falhas),
    ferramentas executadas e segundos."""

    rodadas: int
    usos: list[Uso]
    ferramentas_executadas: int
    segundos: float


def _somar_uso(usos: Sequence[Uso]) -> Uso | None:
    if not usos:
        return None
    return Uso(
        sum(u.prompt_tokens for u in usos),
        sum(u.completion_tokens for u in usos),
        sum(u.total_tokens for u in usos),
    )


def _resposta_para_log(resposta: Resposta) -> dict[str, Any]:
    d: dict[str, Any] = {
        "tipo": "texto" if isinstance(resposta, Text) else "tool_calls",
        "content": resposta.content,
        "finish_reason": resposta.finish_reason,
    }
    if isinstance(resposta, ToolCalls):
        d["tool_calls"] = [
            {"id": c.id, "ferramenta": c.name, "argumentos": dict(c.arguments)} for c in resposta
        ]
    return d


def conversar(
    cliente: LLMClient,
    mensagens: Sequence[Message],
    ferramentas: Sequence[Ferramenta] = (),
    *,
    max_rodadas: int = 5,
    audit: AuditLog | None = None,
) -> Conversa:
    """Laço mínimo de *tool calling*: chama o modelo, executa cada ferramenta pedida, devolve os
    resultados como mensagens ``tool`` e repete até receber texto. Ferramenta desconhecida ou
    exceção viram ``{"erro": ...}`` para o modelo se corrigir; ``max_rodadas`` limita o laço.

    Com ``audit``, cada rodada vira um registro ``llm.rodada`` (mensagens enviadas naquela rodada,
    resposta do modelo, chamadas de ferramenta com argumentos e resultados, uso de tokens) e o
    fim vira ``conversa.fim`` (ou ``conversa.erro``) — ADR-001, decisão 6."""
    historico = list(mensagens)
    por_nome = {f.name: f for f in ferramentas}
    specs = [f.spec for f in ferramentas]
    execucoes: list[tuple[ToolCall, Any]] = []
    usos: list[Uso] = []
    modelo = getattr(cliente, "modelo", None)
    enviadas_desde = 0
    t0 = time.perf_counter()
    for rodada in range(1, max_rodadas + 1):
        try:
            resposta = cliente.chat(historico, specs)
        except LLMError as exc:
            # o chamador ainda contabiliza o que já foi gasto (rodadas, tokens, tempo)
            uso_falho = getattr(exc, "uso", None)
            exc.parcial = ConversaParcial(
                rodadas=rodada,
                usos=[*usos, *([uso_falho] if uso_falho else [])],
                ferramentas_executadas=len(execucoes),
                segundos=time.perf_counter() - t0,
            )
            if audit is not None:
                audit.registrar("conversa.erro", rodadas=rodada, modelo=modelo, erro=str(exc))
            raise
        if resposta.uso is not None:
            usos.append(resposta.uso)
        modelo = resposta.modelo or modelo
        novas = historico[enviadas_desde:]
        enviadas_desde = len(historico)
        execucoes_rodada: list[dict[str, Any]] = []
        if isinstance(resposta, ToolCalls):
            historico.append(Message.assistant(resposta.content, resposta.calls))
            for chamada in resposta.calls:
                resultado = _executar(por_nome.get(chamada.name), chamada)
                execucoes.append((chamada, resultado))
                historico.append(Message.tool(chamada, resultado))
                execucoes_rodada.append(
                    {
                        "id": chamada.id,
                        "ferramenta": chamada.name,
                        "argumentos": dict(chamada.arguments),
                        "resultado": resultado,
                    }
                )
        if audit is not None:
            audit.registrar(
                "llm.rodada",
                rodada=rodada,
                modelo=modelo,
                mensagens=[m.to_openai() for m in novas],
                resposta=_resposta_para_log(resposta),
                execucoes=execucoes_rodada,
                uso=None if resposta.uso is None else vars(resposta.uso),
            )
        if isinstance(resposta, Text):
            hash_final = None
            if audit is not None:
                uso_total = _somar_uso(usos)
                hash_final = audit.registrar(
                    "conversa.fim",
                    rodadas=rodada,
                    modelo=modelo,
                    resposta=resposta.content,
                    ferramentas_executadas=len(execucoes),
                    uso_total=None if uso_total is None else vars(uso_total),
                ).hash
            return Conversa(
                historico,
                resposta,
                rodada,
                execucoes,
                hash_final,
                usos,
                segundos=time.perf_counter() - t0,
            )
    if audit is not None:
        audit.registrar(
            "conversa.erro",
            rodadas=max_rodadas,
            modelo=modelo,
            erro=f"não concluiu em {max_rodadas} rodadas",
        )
    raise LLMError(f"o modelo não concluiu em {max_rodadas} rodadas de ferramentas.")


def _executar(ferramenta: Ferramenta | None, chamada: ToolCall) -> Any:
    if ferramenta is None:
        return {"erro": f"ferramenta desconhecida: {chamada.name}"}
    try:
        return ferramenta.funcao(**chamada.arguments)
    except Exception as exc:  # devolvido ao modelo como erro de ferramenta
        return {"erro": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------------------------
# Exemplo mínimo: soma(a, b)
# ---------------------------------------------------------------------------------------------


def soma(a: float, b: float) -> float:
    """Soma dois números (ferramenta de exemplo do spike)."""
    return float(a) + float(b)


SOMA = Ferramenta(
    ToolSpec(
        name="soma",
        description="Soma dois números e devolve o resultado.",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "primeira parcela"},
                "b": {"type": "number", "description": "segunda parcela"},
            },
            "required": ["a", "b"],
            "additionalProperties": False,
        },
    ),
    soma,
)
