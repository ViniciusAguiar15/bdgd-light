"""Testes do cliente LLM abstraído (issue #7). Nenhuma chamada de rede: ``FakeLLMClient`` para a
lógica de conversa e ``httpx.MockTransport`` para exercitar o cliente HTTP ponta a ponta."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

httpx = pytest.importorskip("httpx")

from bdgd_light.agent import (  # noqa: E402
    PERFIS,
    SOMA,
    AuditLog,
    FakeLLMClient,
    Ferramenta,
    GitHubModelsClient,
    LimiteDeTaxaError,
    LLMClient,
    LLMError,
    Message,
    OpenAICompatClient,
    RespostaInvalidaError,
    ServicoIndisponivelError,
    Text,
    TokenAusenteError,
    ToolCall,
    ToolCalls,
    ToolSpec,
    cliente_do_ambiente,
    cliente_por_perfil,
    conversar,
    fake_soma,
    interpretar_resposta,
    soma,
)
from bdgd_light.cli import app  # noqa: E402

runner = CliRunner()
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
ENDPOINT = "https://exemplo.invalid/v1/chat/completions"
CORPO_410 = {
    "error": {
        "code": "github_models_retirement_brownout",
        "message": "GitHub Models is temporarily unavailable as part of a scheduled retirement "
        "brownout.",
    }
}


def saida(resultado) -> str:
    return _ANSI.sub("", resultado.output)


def payload_texto(conteudo: str, **extra) -> dict:
    return {
        "id": "chatcmpl-1",
        "model": extra.get("model", "gpt-teste"),
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": conteudo},
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def payload_tool_call(nome: str, argumentos, ident: str | None = "call_1", conteudo=None) -> dict:
    chamada = {"type": "function", "function": {"name": nome, "arguments": argumentos}}
    if ident is not None:
        chamada["id"] = ident
    return {
        "model": "gpt-teste",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": conteudo, "tool_calls": [chamada]},
            }
        ],
    }


@pytest.fixture(autouse=True)
def sem_segredos(monkeypatch):
    """Garante ambiente limpo: nenhum token/endpoint herdado da máquina do desenvolvedor."""
    for nome in (
        "GITHUB_TOKEN",
        "BDGD_LLM_TOKEN",
        "BDGD_LLM_ENDPOINT",
        "BDGD_LLM_MODEL",
        "BDGD_LLM_PROVIDER",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "OLLAMA_API_KEY",
    ):
        monkeypatch.delenv(nome, raising=False)


# -- parsing ----------------------------------------------------------------------------------


def test_interpretar_texto():
    r = interpretar_resposta(payload_texto("olá"))
    assert isinstance(r, Text)
    assert r.content == "olá"
    assert r.modelo == "gpt-teste"
    assert r.finish_reason == "stop"
    assert r.uso is not None and r.uso.total_tokens == 15


def test_interpretar_tool_calls_decodifica_argumentos():
    r = interpretar_resposta(payload_tool_call("soma", '{"a": 2, "b": 3}', conteudo="vou somar"))
    assert isinstance(r, ToolCalls)
    assert len(r) == 1
    (chamada,) = r
    assert chamada == ToolCall("call_1", "soma", {"a": 2, "b": 3})
    assert r.content == "vou somar"
    # argumentos vazios viram {} e id ausente ganha um padrão estável
    r2 = interpretar_resposta(payload_tool_call("soma", "", ident=None))
    assert isinstance(r2, ToolCalls)
    assert r2.calls[0].arguments == {} and r2.calls[0].id == "call_0"
    # alguns servidores já mandam objeto em vez de string
    r3 = interpretar_resposta(payload_tool_call("soma", {"a": 1, "b": 1}))
    assert isinstance(r3, ToolCalls) and r3.calls[0].arguments == {"a": 1, "b": 1}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {"role": "assistant"}}]},
        payload_tool_call("soma", "{a: 2"),
        payload_tool_call("soma", "[1, 2]"),
        {"choices": [{"message": {"tool_calls": [{"id": "x", "function": {}}]}}]},
    ],
)
def test_interpretar_invalido(payload):
    with pytest.raises(RespostaInvalidaError):
        interpretar_resposta(payload)


def test_message_to_openai_roundtrip_de_tool_calls():
    chamada = ToolCall("c1", "soma", {"a": 1, "b": 2})
    assistente = Message.assistant(None, [chamada]).to_openai()
    assert assistente["tool_calls"][0]["function"]["arguments"] == '{"a": 1, "b": 2}'
    assert "tool_call_id" not in assistente
    ferramenta = Message.tool(chamada, 3.0).to_openai()
    assert ferramenta == {"role": "tool", "content": "3.0", "tool_call_id": "c1"}
    # resultado não serializável em JSON vira string
    assert Message.tool(chamada, object()).content.startswith('"<object')
    assert Message.system("s").to_openai() == {"role": "system", "content": "s"}
    assert SOMA.spec.to_openai()["function"]["parameters"]["required"] == ["a", "b"]


# -- fake ---------------------------------------------------------------------------------------


def test_fake_fila_regra_e_registro():
    fake = FakeLLMClient(["oi", payload_texto("payload"), Text("pronto")])
    assert isinstance(fake, LLMClient)
    assert fake.restantes == 3
    assert fake.chat([Message.user("a")]).content == "oi"
    assert fake.chat([Message.user("b")], [SOMA.spec]).content == "payload"
    assert fake.chat([]).content == "pronto"
    assert len(fake.chamadas) == 3
    assert fake.chamadas[1] == ((Message.user("b"),), (SOMA.spec,))
    with pytest.raises(LLMError, match="sem resposta"):
        fake.chat([])
    com_regra = FakeLLMClient(regra=lambda msgs, tools: Text(f"{len(msgs)}:{len(tools)}"))
    assert com_regra.chat([Message.user("x")], [SOMA.spec]).content == "1:1"


def test_conversar_soma_com_fake(tmp_path):
    fake = fake_soma()
    conversa = conversar(fake, [Message.system("s"), Message.user("Quanto é 2 + 3?")], [SOMA])
    assert conversa.resposta.content == "O resultado é 5."
    assert conversa.rodadas == 2
    assert [(c.name, dict(c.arguments), r) for c, r in conversa.execucoes] == [
        ("soma", {"a": 2.0, "b": 3.0}, 5.0)
    ]
    assert [m.role for m in conversa.mensagens] == ["system", "user", "assistant", "tool"]
    assert conversa.mensagens[3].tool_call_id == conversa.mensagens[2].tool_calls[0].id
    # a segunda chamada ao modelo recebeu o histórico com a resposta da ferramenta
    assert fake.chamadas[1][0][-1].role == "tool"
    dados = conversa.to_dict()
    (tmp_path / "conversa.json").write_text(json.dumps(dados, ensure_ascii=False))
    assert dados["execucoes"][0]["resultado"] == 5.0
    assert dados["mensagens"][2]["tool_calls"][0]["function"]["name"] == "soma"
    sem_numeros = conversar(fake_soma(), [Message.user("olá")], [SOMA])
    assert sem_numeros.rodadas == 1 and sem_numeros.execucoes == []


def test_conversar_ferramenta_desconhecida_e_excecao_voltam_como_erro():
    fake = FakeLLMClient(
        [
            ToolCalls(
                (
                    ToolCall("c1", "inexistente", {}),
                    ToolCall("c2", "soma", {"a": "x", "b": 1}),
                    ToolCall("c3", "soma", {"a": 1}),
                )
            ),
            Text("desisto"),
        ]
    )
    conversa = conversar(fake, [Message.user("?")], [SOMA])
    erros = [r["erro"] for _, r in conversa.execucoes]
    assert erros[0] == "ferramenta desconhecida: inexistente"
    assert erros[1].startswith("ValueError")
    assert erros[2].startswith("TypeError")
    mensagens_tool = [m for m in conversa.mensagens if m.role == "tool"]
    assert [m.tool_call_id for m in mensagens_tool] == ["c1", "c2", "c3"]
    assert all("erro" in json.loads(m.content) for m in mensagens_tool)


def test_conversar_limite_de_rodadas():
    pedido = ToolCalls((ToolCall("c", "soma", {"a": 1, "b": 1}),))
    insistente = FakeLLMClient(regra=lambda m, t: pedido)
    with pytest.raises(LLMError, match="3 rodadas"):
        conversar(insistente, [Message.user("?")], [SOMA], max_rodadas=3)
    assert len(insistente.chamadas) == 3


def test_soma_e_ferramenta():
    assert soma(2, 3) == 5.0
    eco = Ferramenta(ToolSpec("eco", "repete"), lambda **kw: kw)
    assert eco.name == "eco"
    assert eco.spec.to_openai()["function"]["parameters"] == {"type": "object", "properties": {}}


# -- cliente HTTP (MockTransport, sem rede) -----------------------------------------------------


def transporte(respostas):
    """MockTransport que devolve ``respostas`` (status, json[, headers]) em ordem e guarda os
    pedidos recebidos."""
    fila = list(respostas)
    pedidos: list[httpx.Request] = []

    def handler(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        status, corpo, *resto = fila.pop(0)
        cabecalhos = resto[0] if resto else None
        if isinstance(corpo, str):
            return httpx.Response(status, text=corpo, headers=cabecalhos)
        return httpx.Response(status, json=corpo, headers=cabecalhos)

    return httpx.MockTransport(handler), pedidos


def test_openai_compat_client_envia_ferramentas_e_interpreta(monkeypatch):
    monkeypatch.setenv("BDGD_LLM_TOKEN", "segredo-de-teste")
    monkeypatch.setenv("BDGD_LLM_MODEL", "modelo-env")
    mock, pedidos = transporte(
        [(200, payload_tool_call("soma", '{"a": 2, "b": 3}')), (200, payload_texto("5"))]
    )
    with OpenAICompatClient(ENDPOINT, transporte=mock) as cliente:
        assert cliente.modelo == "modelo-env"
        assert cliente.url_modelos == "https://exemplo.invalid/v1/models"
        conversa = conversar(cliente, [Message.user("2 + 3?")], [SOMA])
    assert conversa.resposta.content == "5"
    assert conversa.execucoes[0][1] == 5.0
    assert cliente.ultimo_uso.total_tokens == 15
    assert len(pedidos) == 2
    primeiro = pedidos[0]
    assert str(primeiro.url) == ENDPOINT
    assert primeiro.headers["authorization"] == "Bearer segredo-de-teste"
    assert primeiro.headers["content-type"] == "application/json"
    corpo = json.loads(primeiro.content)
    assert corpo["model"] == "modelo-env"
    assert corpo["tool_choice"] == "auto"
    assert corpo["tools"][0]["function"]["name"] == "soma"
    assert corpo["temperature"] == 0.0
    segundo = json.loads(pedidos[1].content)
    assert [m["role"] for m in segundo["messages"]] == ["user", "assistant", "tool"]
    assert segundo["messages"][2] == {"role": "tool", "content": "5.0", "tool_call_id": "call_1"}


def test_openai_compat_client_429_repete_e_depois_falha():
    mock, pedidos = transporte(
        [(429, {"error": {"message": "slow"}}, {"retry-after": "2"}), (200, payload_texto("ok"))]
    )
    pausas: list[float] = []
    cliente = OpenAICompatClient(
        ENDPOINT, token="t", max_tentativas=2, dormir=pausas.append, transporte=mock
    )
    assert cliente.chat([Message.user("x")]).content == "ok"
    assert pausas == [2.0] and len(pedidos) == 2

    erro = {"error": {"code": "rate", "message": "slow"}}
    mock2, _ = transporte([(429, erro, {"retry-after": "7"})])
    unico = OpenAICompatClient(ENDPOINT, token="t", transporte=mock2)
    with pytest.raises(LimiteDeTaxaError, match="rate: slow") as info:
        unico.chat([Message.user("x")])
    assert info.value.retry_after == 7.0


@pytest.mark.parametrize(
    ("status", "corpo", "erro"),
    [
        (401, {"error": {"message": "bad token"}}, TokenAusenteError),
        (403, {"message": "forbidden"}, TokenAusenteError),
        (404, {"error": {"message": "no model"}}, ServicoIndisponivelError),
        (503, "indisponível", ServicoIndisponivelError),
        (500, {"error": {"message": "boom"}}, LLMError),
        (200, "isto não é json", RespostaInvalidaError),
    ],
)
def test_openai_compat_client_erros_http(status, corpo, erro):
    mock, _ = transporte([(status, corpo)])
    cliente = OpenAICompatClient(ENDPOINT, token="t", transporte=mock)
    with pytest.raises(erro):
        cliente.chat([Message.user("x")])


def test_openai_compat_listar_modelos_formato_openai():
    mock, pedidos = transporte(
        [(200, {"object": "list", "data": [{"id": "gpt-4.1-mini", "owned_by": "openai"}]})]
    )
    cliente = OpenAICompatClient(ENDPOINT, token="t", transporte=mock)
    assert cliente.listar_modelos() == [{"id": "gpt-4.1-mini", "owned_by": "openai"}]
    assert str(pedidos[0].url) == "https://exemplo.invalid/v1/models"
    assert pedidos[0].method == "GET"


def test_github_models_client_410_aposentado(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-teste")
    mock, pedidos = transporte([(410, CORPO_410), (410, CORPO_410)])
    cliente = GitHubModelsClient(transporte=mock)
    assert cliente.modelo == "openai/gpt-4.1-mini"
    assert cliente.url_modelos == GitHubModelsClient.CATALOGO
    with pytest.raises(ServicoIndisponivelError, match="aposentado em 30/07/2026") as info:
        cliente.chat([Message.user("ok")])
    assert info.value.status == 410
    assert "github_models_retirement_brownout" in str(info.value)
    with pytest.raises(ServicoIndisponivelError):
        cliente.listar_modelos()
    assert str(pedidos[0].url) == GitHubModelsClient.ENDPOINT
    assert pedidos[0].headers["accept"] == "application/vnd.github+json"
    assert pedidos[0].headers["x-github-api-version"] == "2022-11-28"
    assert pedidos[0].headers["authorization"] == "Bearer ghp-teste"


def test_tokens_so_por_ambiente(monkeypatch):
    with pytest.raises(TokenAusenteError, match="BDGD_LLM_TOKEN"):
        OpenAICompatClient(ENDPOINT)
    with pytest.raises(TokenAusenteError, match="GITHUB_TOKEN"):
        GitHubModelsClient()
    padrao = "OPENAI_API_KEY.*GEMINI_API_KEY.*BDGD_LLM_ENDPOINT"
    with pytest.raises(TokenAusenteError, match=padrao) as e:
        cliente_do_ambiente()
    assert "BDGD_LLM_PROVIDER=fake" in str(e.value)
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    assert isinstance(cliente_do_ambiente(), GitHubModelsClient)
    monkeypatch.setenv("BDGD_LLM_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("BDGD_LLM_TOKEN", "y")
    generico = cliente_do_ambiente("m")
    assert type(generico) is OpenAICompatClient
    assert generico.endpoint == ENDPOINT and generico.modelo == "m"
    # nada hardcoded no pacote: nenhum token literal no código-fonte
    fonte = Path("src/bdgd_light/agent/llm.py").read_text(encoding="utf-8")
    assert not re.search(r"(ghp|gho|github_pat|sk-|AIza)_?[A-Za-z0-9]{10,}", fonte)


# -- perfis de provedor (ADR-003) --------------------------------------------------------------


def test_perfil_openai_e_padrao_e_gemini_usa_endpoint_compativel(monkeypatch):
    assert set(PERFIS) == {"openai", "gemini", "ollama", "fake"}
    monkeypatch.setenv("OPENAI_API_KEY", "chave-openai")
    cliente = cliente_do_ambiente()
    assert type(cliente) is OpenAICompatClient
    assert cliente.endpoint == "https://api.openai.com/v1/chat/completions"
    assert cliente.modelo == "gpt-4.1-mini" and cliente.url_modelos.endswith("/v1/models")
    # explícito > BDGD_LLM_MODEL > padrão do perfil
    monkeypatch.setenv("BDGD_LLM_MODEL", "gpt-4.1")
    assert cliente_do_ambiente().modelo == "gpt-4.1"
    assert cliente_do_ambiente("gpt-5").modelo == "gpt-5"
    # só GEMINI_API_KEY → gemini; com as duas, openai continua o padrão
    monkeypatch.setenv("GEMINI_API_KEY", "chave-gemini")
    assert cliente_do_ambiente().endpoint.startswith("https://api.openai.com/")
    monkeypatch.delenv("OPENAI_API_KEY")
    gemini = cliente_do_ambiente()
    assert gemini.endpoint == (
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    )
    assert gemini.url_modelos == "https://generativelanguage.googleapis.com/v1beta/openai/models"
    assert gemini.modelo == "gpt-4.1"  # BDGD_LLM_MODEL ainda vale para qualquer perfil
    monkeypatch.delenv("BDGD_LLM_MODEL")
    assert cliente_do_ambiente().modelo == "gemini-2.5-flash"


def test_perfil_explicito_e_erros(monkeypatch):
    # BDGD_LLM_PROVIDER manda mesmo com outra chave presente; a chave do perfil é obrigatória
    monkeypatch.setenv("OPENAI_API_KEY", "chave-openai")
    monkeypatch.setenv("BDGD_LLM_PROVIDER", "gemini")
    with pytest.raises(TokenAusenteError, match="GEMINI_API_KEY"):
        cliente_do_ambiente()
    monkeypatch.setenv("GEMINI_API_KEY", "chave-gemini")
    assert cliente_do_ambiente().endpoint.startswith("https://generativelanguage.googleapis.com/")
    assert cliente_do_ambiente(provider="openai").endpoint.startswith("https://api.openai.com/")
    # perfil explícito tem precedência sobre BDGD_LLM_ENDPOINT
    monkeypatch.setenv("BDGD_LLM_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("BDGD_LLM_TOKEN", "y")
    assert cliente_do_ambiente(provider="OpenAI").endpoint.startswith("https://api.openai.com/")
    monkeypatch.delenv("BDGD_LLM_PROVIDER")
    assert cliente_do_ambiente().endpoint == ENDPOINT
    # ollama não exige chave; fake devolve o cliente determinístico
    ollama = cliente_por_perfil("ollama")
    assert ollama.endpoint == "http://localhost:11434/v1/chat/completions"
    assert ollama.modelo == "llama3.1:8b"
    assert isinstance(cliente_por_perfil("fake"), FakeLLMClient)
    with pytest.raises(ValueError, match="perfil LLM desconhecido: 'azure'"):
        cliente_por_perfil("azure")


def test_perfil_gemini_envia_chave_e_registra_latencia(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-gemini")
    mock, pedidos = transporte([(200, payload_texto("5", model="gemini-2.5-flash"))])
    cliente = cliente_do_ambiente(provider="gemini", transporte=mock)
    conversa = conversar(cliente, [Message.user("2+3?")], [SOMA])
    assert conversa.resposta.content == "5" and conversa.resposta.modelo == "gemini-2.5-flash"
    assert pedidos[0].url.host == "generativelanguage.googleapis.com"
    assert pedidos[0].headers["authorization"] == "Bearer chave-gemini"
    assert json.loads(pedidos[0].content)["model"] == "gemini-2.5-flash"
    assert conversa.segundos >= 0 and conversa.to_dict()["segundos"] == round(conversa.segundos, 3)


# -- CLI e script -----------------------------------------------------------------------------


def test_cli_llm_fake(tmp_path):
    destino = tmp_path / "conversa.json"
    audit = tmp_path / "audit" / "llm.jsonl"
    r = runner.invoke(
        app,
        ["llm", "--fake", "Quanto é 2 + 3?", "--json", str(destino), "--audit", str(audit)],
    )
    assert r.exit_code == 0, r.output
    texto = saida(r)
    assert 'soma({"a": 2.0, "b": 3.0}) → 5.0' in texto
    assert "O resultado é 5." in texto
    assert "fake · 2 rodada(s)" in texto
    assert "auditoria: 3 registro(s)" in texto
    dados = json.loads(destino.read_text(encoding="utf-8"))
    assert dados["resposta"] == "O resultado é 5."
    assert dados["execucoes"][0]["ferramenta"] == "soma"
    assert len(dados["hash_auditoria"]) == 64
    # 2 rodadas + fim; segunda execução continua a cadeia do mesmo arquivo
    assert len(audit.read_text(encoding="utf-8").splitlines()) == 3
    r2 = runner.invoke(app, ["llm", "--fake", "Quanto é 1 + 1?", "--audit", str(audit)])
    assert r2.exit_code == 0, r2.output
    assert "auditoria: 6 registro(s)" in saida(r2)
    r3 = runner.invoke(app, ["audit", str(audit), "--mostrar", "2"])
    assert r3.exit_code == 0, r3.output
    assert "6 registro(s), cadeia íntegra" in saida(r3)
    assert "conversa.fim" in saida(r3)
    # --sem-audit não toca no arquivo
    r4 = runner.invoke(
        app, ["llm", "--fake", "Quanto é 1 + 1?", "--audit", str(audit), "--sem-audit"]
    )
    assert r4.exit_code == 0 and "auditoria" not in saida(r4)
    assert len(audit.read_text(encoding="utf-8").splitlines()) == 6


def test_cli_llm_sem_token_falha_com_instrucao():
    r = runner.invoke(app, ["llm", "Quanto é 2 + 3?"])
    assert r.exit_code == 1
    texto = saida(r)
    assert "OPENAI_API_KEY" in texto and "GEMINI_API_KEY" in texto and "BDGD_LLM_ENDPOINT" in texto
    r = runner.invoke(app, ["llm", "--provider", "gemini", "Quanto é 2 + 3?"])
    assert r.exit_code == 1 and "GEMINI_API_KEY" in saida(r)
    r = runner.invoke(app, ["llm", "--provider", "azure", "Quanto é 2 + 3?"])
    assert r.exit_code == 1 and "perfil LLM desconhecido" in saida(r)


def test_cli_llm_provider_fake_e_latencia():
    r = runner.invoke(app, ["llm", "--provider", "fake", "Quanto é 2 + 3?", "--sem-audit"])
    assert r.exit_code == 0, r.output
    assert re.search(r"fake · 2 rodada\(s\), 99 tokens, \d+\.\d s", saida(r))


def _carregar_script():
    caminho = Path("scripts/listar_modelos.py")
    spec = importlib.util.spec_from_file_location("listar_modelos", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_script_listar_modelos_destaca_tool_calling(monkeypatch, capsys):
    modulo = _carregar_script()
    monkeypatch.setenv("BDGD_LLM_TOKEN", "t")
    catalogo = {
        "data": [
            {"id": "gpt-4.1-mini", "owned_by": "openai"},
            {"id": "claude-sonnet", "publisher": "anthropic"},
            {"id": "text-embedding-3-small", "owned_by": "openai"},
            {"id": "misterioso", "capabilities": ["tool_calling"]},
        ]
    }
    mock, _ = transporte([(200, catalogo)])

    class ClienteMock(OpenAICompatClient):
        def __init__(self, endpoint, **opcoes):
            super().__init__(endpoint, transporte=mock, **opcoes)

    monkeypatch.setattr(modulo, "OpenAICompatClient", ClienteMock)
    assert modulo.main(["--endpoint", ENDPOINT]) == 0
    texto = capsys.readouterr().out
    assert "Origem: https://exemplo.invalid/v1/models" in texto
    assert "4 modelos (3 com tool calling)" in texto
    prefixos = ("gpt", "claude", "text", "mist")
    linhas = [linha for linha in texto.splitlines() if linha.startswith(prefixos)]
    assert linhas[-1].startswith("text-embedding-3-small") and linhas[-1].rstrip().endswith("–")
    assert modulo.suporta_tool_calling({"id": "gpt-4o"})
    assert not modulo.suporta_tool_calling({"id": "ada"})
    # sem ambiente → orientação e código 2, sem rede
    monkeypatch.delenv("BDGD_LLM_TOKEN")
    assert modulo.main([]) == 2
    erro = capsys.readouterr().err
    assert "OPENAI_API_KEY" in erro and "BDGD_LLM_ENDPOINT" in erro


def test_script_listar_modelos_por_perfil_gemini(monkeypatch, capsys):
    modulo = _carregar_script()
    catalogo = {
        "data": [
            {"id": "models/gemini-2.5-flash", "owned_by": "google"},
            {"id": "models/embedding-001", "owned_by": "google"},
        ]
    }
    mock, pedidos = transporte([(200, catalogo)])
    monkeypatch.setattr(
        modulo,
        "cliente_do_ambiente",
        lambda provider=None, **o: cliente_do_ambiente(provider=provider, transporte=mock, **o),
    )
    # sem chave: orientação nomeando a variável do perfil, sem rede
    assert modulo.main(["--provider", "gemini"]) == 2
    assert "GEMINI_API_KEY" in capsys.readouterr().err and not pedidos
    monkeypatch.setenv("GEMINI_API_KEY", "chave-gemini")
    assert modulo.main(["--provider", "gemini", "--tools"]) == 0
    texto = capsys.readouterr().out
    assert "Origem: https://generativelanguage.googleapis.com/v1beta/openai/models" in texto
    assert "models/gemini-2.5-flash" in texto and "embedding" not in texto
    assert "1 modelos (1 com tool calling)" in texto
    assert pedidos[0].headers["authorization"] == "Bearer chave-gemini"


def test_cliente_do_ambiente_registra_proveniencia_no_audit(monkeypatch, tmp_path):
    for var in ("BDGD_LLM_PROVIDER", "BDGD_LLM_ENDPOINT", "OPENAI_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaFAKE")
    log = AuditLog(tmp_path / "audit.jsonl")
    cliente = cliente_do_ambiente(audit=log)
    registro = log.registros[-1]
    assert registro.tipo == "llm.cliente"
    assert registro.dados["perfil"] == "gemini"
    assert registro.dados["origem"] == "GEMINI_API_KEY"
    assert registro.dados["modelo"] == cliente.modelo == "gemini-2.5-flash"
    assert registro.dados["endpoint"].startswith("https://generativelanguage.googleapis.com/")
    assert "AIzaFAKE" not in (tmp_path / "audit.jsonl").read_text()
    # perfil explícito e fake também ficam registrados
    cliente_por_perfil("fake", audit=log)
    assert log.registros[-1].dados == {
        "perfil": "fake",
        "origem": "perfil",
        "tipo": "FakeLLMClient",
        "modelo": None,
        "endpoint": None,
    }
    assert log.verificar() == len(log)
