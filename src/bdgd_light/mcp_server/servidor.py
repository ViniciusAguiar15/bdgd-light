"""Servidor MCP ``bdgd-light``: ferramentas de rede (grid + twin) sobre uma ``SessaoCOD``.

Uma função tipada por ferramenta (o SDK gera o JSON Schema dos argumentos a partir das anotações;
as descrições vêm dos ``@ferramenta`` da sessão). Erros de domínio viram ``ToolError`` — o
cliente recebe ``is_error=True`` com a mensagem, e a recusa de ``set_switch`` fica registrada no
``AuditLog`` pela própria sessão. ``approve``/``reject`` **não** são ferramentas: ficam na CLI
(``bdgd-light aprovar``) e, no transporte HTTP, nas rotas ``/propostas`` para o console.

Requer o extra ``agent`` (``uv sync --extra agent``). Funciona com o SDK ``mcp`` 1.10+ (``FastMCP``)
e 2.x (``MCPServer``): em Python < 3.13 o ``bdgd2opendss`` fixa ``typing-extensions==4.12.2``, o
que trava o ``mcp`` em 1.x — daí a camada de compatibilidade ``_compat``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from bdgd_light.grid.rede import ChaveInexistenteError, TrechoInexistenteError
from bdgd_light.mcp_server.sessao import (
    RecusadoError,
    SessaoCOD,
    SessaoError,
    ferramentas_da_sessao,
)

try:
    try:  # mcp >= 2
        from mcp.server.mcpserver import MCPServer
        from mcp.server.mcpserver.exceptions import ToolError

        MCP_V2 = True
    except ImportError:  # mcp 1.10+
        from mcp.server.fastmcp import FastMCP as MCPServer
        from mcp.server.fastmcp.exceptions import ToolError

        MCP_V2 = False
except ImportError as exc:  # pragma: no cover - depende do extra
    raise ImportError(f"{exc} — instale o extra: uv sync --extra agent") from exc

NOME = "bdgd-light"
INSTRUCOES = (
    "Ferramentas do Centro de Operação da Distribuição (COD) da Light sobre a BDGD: grafo MT por "
    "alimentador (CTMT) e gêmeo OpenDSS. Fluxo FLISR: load_cluster → (falta injetada pelo "
    "simulador) → locate_fault → isolate_fault → restore_options → propose_plan → aprovação "
    "HUMANA (fora do modelo) → set_switch com approval_token, um passo por vez, na ordem da "
    "proposta. Nunca invente tokens; sem aprovação, nenhuma chave é manobrada. Unidades: "
    "correntes em A, tensões em pu, potências em kW/kvar, comprimentos em km."
)
DESCRICOES = dict(ferramentas_da_sessao())
ERROS_DOMINIO = (
    SessaoError,
    RecusadoError,
    ChaveInexistenteError,
    TrechoInexistenteError,
    FileNotFoundError,
    ValueError,
)


def _executar(funcao, **argumentos):
    try:
        return funcao(**argumentos)
    except ERROS_DOMINIO as exc:
        raise ToolError(str(exc)) from exc


def criar_servidor(sessao: SessaoCOD) -> MCPServer:
    """Monta o ``MCPServer`` com as ferramentas da sessão (descritores em português, unidades)."""
    srv = MCPServer(NOME, instructions=INSTRUCOES)

    @srv.tool(name="load_cluster", description=DESCRICOES["load_cluster"])
    def load_cluster(cluster: str) -> dict[str, Any]:
        return _executar(sessao.load_cluster, cluster=cluster)

    @srv.tool(name="get_topology", description=DESCRICOES["get_topology"])
    def get_topology(ctmt: str | None = None, com_chaves: bool = True) -> dict[str, Any]:
        return _executar(sessao.get_topology, ctmt=ctmt, com_chaves=com_chaves)

    @srv.tool(name="get_switch_state", description=DESCRICOES["get_switch_state"])
    def get_switch_state(chave: str) -> dict[str, Any]:
        return _executar(sessao.get_switch_state, chave=chave)

    @srv.tool(name="inject_fault", description=DESCRICOES["inject_fault"])
    def inject_fault(trecho: str) -> dict[str, Any]:
        return _executar(sessao.inject_fault, trecho=trecho)

    @srv.tool(name="locate_fault", description=DESCRICOES["locate_fault"])
    def locate_fault() -> dict[str, Any]:
        return _executar(sessao.locate_fault)

    @srv.tool(name="isolate_fault", description=DESCRICOES["isolate_fault"])
    def isolate_fault() -> dict[str, Any]:
        return _executar(sessao.isolate_fault)

    @srv.tool(name="downstream_customers", description=DESCRICOES["downstream_customers"])
    def downstream_customers(no: str | None = None, chave: str | None = None) -> dict[str, Any]:
        return _executar(sessao.downstream_customers, no=no, chave=chave)

    @srv.tool(name="restore_options", description=DESCRICOES["restore_options"])
    def restore_options(
        score: bool = True, vmin: float = 0.93, vmax: float = 1.05
    ) -> dict[str, Any]:
        return _executar(sessao.restore_options, score=score, vmin=vmin, vmax=vmax)

    @srv.tool(name="run_powerflow", description=DESCRICOES["run_powerflow"])
    def run_powerflow(
        manobras: Sequence[dict[str, str]] = (), vmin: float = 0.93, vmax: float = 1.05
    ) -> dict[str, Any]:
        return _executar(sessao.run_powerflow, manobras=list(manobras), vmin=vmin, vmax=vmax)

    @srv.tool(name="propose_plan", description=DESCRICOES["propose_plan"])
    def propose_plan(chave: str | None = None, justificativa: str = "") -> dict[str, Any]:
        return _executar(sessao.propose_plan, chave=chave, justificativa=justificativa)

    @srv.tool(name="get_proposal", description=DESCRICOES["get_proposal"])
    def get_proposal(proposta_id: str) -> dict[str, Any]:
        return _executar(sessao.get_proposal, proposta_id=proposta_id)

    @srv.tool(name="set_switch", description=DESCRICOES["set_switch"])
    def set_switch(chave: str, estado: str, approval_token: str | None = None) -> dict[str, Any]:
        return _executar(
            sessao.set_switch, chave=chave, estado=estado, approval_token=approval_token
        )

    _rotas_humanas(srv, sessao)
    return srv


def _rotas_humanas(srv: MCPServer, sessao: SessaoCOD) -> None:
    """Rotas HTTP fora do protocolo MCP (transporte streamable-http) para o console/operador:
    ``GET /estado``, ``GET /propostas``, ``POST /propostas/{id}/aprovar|rejeitar``."""
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response

    async def _json(request: Request) -> dict[str, Any]:
        try:
            corpo = await request.json()
        except Exception:  # corpo vazio ou não-JSON
            return {}
        return corpo if isinstance(corpo, dict) else {}

    @srv.custom_route("/estado", methods=["GET"])
    async def estado(_: Request) -> Response:
        return JSONResponse(sessao.estado())

    @srv.custom_route("/propostas", methods=["GET"])
    async def propostas(_: Request) -> Response:
        return JSONResponse([p.to_dict(com_token=False) for p in sessao.propostas.listar()])

    @srv.custom_route("/propostas/{proposta_id}/aprovar", methods=["POST"])
    async def aprovar(request: Request) -> Response:
        corpo = await _json(request)
        try:
            p = sessao.approve(
                request.path_params["proposta_id"],
                operador=str(corpo.get("operador", "console")),
                validade_s=int(corpo.get("validade_s", 1800)),
            )
        except SessaoError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=409)
        return JSONResponse(p)

    @srv.custom_route("/propostas/{proposta_id}/rejeitar", methods=["POST"])
    async def rejeitar(request: Request) -> Response:
        corpo = await _json(request)
        try:
            p = sessao.reject(
                request.path_params["proposta_id"],
                operador=str(corpo.get("operador", "console")),
                motivo=str(corpo.get("motivo", "")),
            )
        except SessaoError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=409)
        return JSONResponse(p)


def descritores(srv: MCPServer | None = None) -> list[dict[str, Any]]:
    """``[{name, description, parameters}]`` das ferramentas (JSON Schema dos argumentos) — o
    mesmo formato de ``agent.ToolSpec``; sem ``srv`` monta um servidor sobre uma sessão vazia."""
    srv = srv or criar_servidor(SessaoCOD(estado_dir=None))
    ferramentas = asyncio.run(srv.list_tools())
    return [
        {"name": f.name, "description": f.description or "", "parameters": campo(f, "input_schema")}
        for f in ferramentas
    ]


def campo(obj: Any, nome: str) -> Any:
    """Atributo de um modelo do SDK nos dois dialetos: ``input_schema`` (2.x) ou ``inputSchema``
    (1.x); idem ``is_error``/``isError`` e ``structured_content``/``structuredContent``."""
    if hasattr(obj, nome):
        return getattr(obj, nome)
    partes = nome.split("_")
    camelo = partes[0] + "".join(p.capitalize() for p in partes[1:])
    return getattr(obj, camelo)


def cliente_em_memoria(srv: MCPServer):
    """Gerenciador de contexto assíncrono com um cliente MCP ligado ao servidor em memória
    (testes e uso em processo): ``async with cliente_em_memoria(srv) as c: ...``."""
    if MCP_V2:
        from mcp.client.client import Client

        return Client(srv)
    from mcp.shared.memory import create_connected_server_and_client_session

    return create_connected_server_and_client_session(srv._mcp_server)


def servir(
    sessao: SessaoCOD, transporte: str = "stdio", *, host: str = "127.0.0.1", port: int = 8765
) -> None:
    """Sobe o servidor (bloqueante): ``stdio`` para clientes locais ou ``http`` (streamable)."""
    if transporte not in ("stdio", "http", "streamable-http"):
        raise ValueError(f"transporte {transporte!r} inválido; use stdio ou http")
    srv = criar_servidor(sessao)
    if transporte == "stdio":
        srv.run("stdio")
    elif MCP_V2:
        srv.run("streamable-http", host=host, port=port)
    else:  # 1.x: host/porta são configurações do servidor
        srv.settings.host, srv.settings.port = host, port
        srv.run("streamable-http")
