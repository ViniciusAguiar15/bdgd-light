"""Cliente LLM abstraído: interface ``LLMClient`` com *tool calling*, cliente *fake* para testes e
cliente HTTP para qualquer API compatível com ``chat/completions`` da OpenAI.

O alvo original do spike (issue #7) era o GitHub Models, mas o serviço foi **aposentado em
30/07/2026** e o endpoint responde ``410 github_models_retirement_brownout``. Por isso o cliente
real é genérico (``OpenAICompatClient``: Azure AI Foundry, OpenAI, Ollama/LM Studio locais…) e
``GitHubModelsClient`` fica como *preset* nomeado que falha com ``ServicoIndisponivelError``
explicando a aposentadoria. Detalhes em ``docs/spike-llm.md``.

Segredos só por variável de ambiente (``GITHUB_TOKEN``, ``BDGD_LLM_TOKEN``); nada no código.
"""

from __future__ import annotations

import json
import os
import time
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

ENV_MODELO = "BDGD_LLM_MODEL"
ENV_ENDPOINT = "BDGD_LLM_ENDPOINT"
ENV_TOKEN = "BDGD_LLM_TOKEN"
ENV_GITHUB_TOKEN = "GITHUB_TOKEN"

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
        raise RespostaInvalidaError(f"mensagem sem 'content' nem 'tool_calls': {_resumo(payload)}")
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
        if ultima.role == "tool":
            try:
                valor = json.loads(ultima.content or "null")
            except json.JSONDecodeError:
                valor = ultima.content
            return Text(f"O resultado é {_fmt_num(valor)}.", modelo="fake")
        numeros = _numeros(ultima.content or "")
        if len(numeros) >= 2 and any(t.name == "soma" for t in tools):
            a, b = numeros[0], numeros[1]
            return ToolCalls(
                (ToolCall("call_fake_1", "soma", {"a": a, "b": b}),), None, modelo="fake"
            )
        return Text("Não encontrei dois números para somar.", modelo="fake")

    return FakeLLMClient(regra=regra)


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
    ``max_tentativas > 1`` repete em 429 respeitando ``Retry-After`` (``dormir`` é injetável para
    testes). ``transporte`` aceita um ``httpx.MockTransport`` para exercitar o cliente sem rede.
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
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.modelo,
            "messages": [m.to_openai() for m in messages],
        }
        if tools:
            payload["tools"] = [t.to_openai() for t in tools]
            payload["tool_choice"] = "auto"
        if self.temperatura is not None:
            payload["temperature"] = self.temperatura
        return payload

    def chat(self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()) -> Resposta:
        payload = self.montar_payload(messages, tools)
        dados = self._post(payload)
        resposta = interpretar_resposta(dados)
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


def cliente_do_ambiente(modelo: str | None = None, **opcoes) -> LLMClient:
    """Escolhe o cliente pelo ambiente: ``BDGD_LLM_ENDPOINT`` (+ ``BDGD_LLM_TOKEN``) →
    ``OpenAICompatClient``; senão ``GITHUB_TOKEN`` → ``GitHubModelsClient``; senão
    ``TokenAusenteError``."""
    endpoint = os.environ.get(ENV_ENDPOINT)
    if endpoint:
        return OpenAICompatClient(endpoint, modelo=modelo, **opcoes)
    if os.environ.get(ENV_GITHUB_TOKEN):
        return GitHubModelsClient(modelo=modelo, **opcoes)
    raise TokenAusenteError(
        f"defina {ENV_ENDPOINT} e {ENV_TOKEN} (provedor compatível com a OpenAI) ou "
        f"{ENV_GITHUB_TOKEN}; para testes use FakeLLMClient."
    )


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

    def to_dict(self) -> dict[str, Any]:
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
        }


def conversar(
    cliente: LLMClient,
    mensagens: Sequence[Message],
    ferramentas: Sequence[Ferramenta] = (),
    *,
    max_rodadas: int = 5,
) -> Conversa:
    """Laço mínimo de *tool calling*: chama o modelo, executa cada ferramenta pedida, devolve os
    resultados como mensagens ``tool`` e repete até receber texto. Ferramenta desconhecida ou
    exceção viram ``{"erro": ...}`` para o modelo se corrigir; ``max_rodadas`` limita o laço."""
    historico = list(mensagens)
    por_nome = {f.name: f for f in ferramentas}
    specs = [f.spec for f in ferramentas]
    execucoes: list[tuple[ToolCall, Any]] = []
    for rodada in range(1, max_rodadas + 1):
        resposta = cliente.chat(historico, specs)
        if isinstance(resposta, Text):
            return Conversa(historico, resposta, rodada, execucoes)
        historico.append(Message.assistant(resposta.content, resposta.calls))
        for chamada in resposta.calls:
            resultado = _executar(por_nome.get(chamada.name), chamada)
            execucoes.append((chamada, resultado))
            historico.append(Message.tool(chamada, resultado))
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
