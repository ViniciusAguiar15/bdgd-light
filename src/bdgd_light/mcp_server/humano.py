"""Lado humano do HITL nas rotas HTTP (servidor MCP em ``http`` e backend do console).

Identidade do operador (pedido 1 da revisão PR-12): toda rota que decide ou altera estado exige o
cabeçalho ``X-Operador`` e, quando há segredo compartilhado (``BDGD_CONSOLE_TOKEN`` no ambiente do
servidor), também ``Authorization: Bearer <segredo>`` ou ``X-Console-Token``; a comparação é em
tempo constante. Sem segredo configurado, o servidor recusa decisões (503) a menos que tenha sido
iniciado explicitamente com ``--sem-segredo`` (demo local).

A decisão vai para dois lugares: ``audit.jsonl`` da sessão (``hitl.aprovacao``/``hitl.rejeicao``,
via ``SessaoCOD.approve/reject``) e ``hitl.jsonl`` — a cadeia própria do lado humano, a mesma que
``bdgd-light aprovar`` escreve — com operador, origem e endereço do cliente. ``executar_passo`` é o
modo passo a passo do console: uma manobra por chamada, cada uma registrada como ``hitl.passo``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from bdgd_light.agent.audit import AuditLog
from bdgd_light.mcp_server.sessao import (
    ABRIR,
    VALIDADE_TOKEN_S,
    RecusadoError,
    SessaoCOD,
    SessaoError,
)

VARIAVEL_SEGREDO = "BDGD_CONSOLE_TOKEN"
CABECALHO_OPERADOR = "x-operador"
CABECALHO_TOKEN = "x-console-token"


class NaoAutorizadoError(PermissionError):
    """Requisição sem identidade/segredo válidos; ``status`` é o código HTTP a devolver."""

    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status = status


class Autorizador:
    """Extrai e valida a identidade do operador dos cabeçalhos HTTP."""

    def __init__(self, segredo: str | None, *, exigir_segredo: bool = True):
        self.segredo = segredo or None
        self.exigir_segredo = exigir_segredo

    @classmethod
    def do_ambiente(
        cls, *, exigir_segredo: bool = True, env: Mapping[str, str] | None = None
    ) -> Autorizador:
        env = os.environ if env is None else env
        return cls(env.get(VARIAVEL_SEGREDO), exigir_segredo=exigir_segredo)

    @property
    def modo(self) -> str:
        if self.segredo:
            return "segredo"
        return "sem-segredo" if not self.exigir_segredo else "bloqueado"

    def operador(self, cabecalhos: Mapping[str, str]) -> str:
        """Nome do operador validado; levanta ``NaoAutorizadoError`` (400/401/503)."""
        baixos = {str(k).lower(): v for k, v in cabecalhos.items()}
        quem = (baixos.get(CABECALHO_OPERADOR) or "").strip()
        if not quem:
            raise NaoAutorizadoError(400, "cabeçalho X-Operador obrigatório (quem decide)")
        if self.segredo is None:
            if self.exigir_segredo:
                raise NaoAutorizadoError(
                    503,
                    f"servidor sem segredo: defina {VARIAVEL_SEGREDO} no ambiente do servidor "
                    "(ou inicie com --sem-segredo para demo local)",
                )
            return quem
        token = baixos.get(CABECALHO_TOKEN) or _bearer(baixos.get("authorization"))
        if not token:
            raise NaoAutorizadoError(
                401, "segredo ausente: envie Authorization: Bearer <token> ou X-Console-Token"
            )
        import secrets

        if not secrets.compare_digest(token.encode(), self.segredo.encode()):
            raise NaoAutorizadoError(401, "segredo inválido")
        return quem


def _bearer(valor: str | None) -> str | None:
    if not valor:
        return None
    esquema, _, token = valor.strip().partition(" ")
    return token.strip() if esquema.lower() == "bearer" and token.strip() else None


def hitl_log(sessao: SessaoCOD) -> AuditLog | None:
    """``hitl.jsonl`` na pasta de estado da sessão (``None`` em sessões só de memória)."""
    if sessao.estado_dir is None:
        return None
    return AuditLog(Path(sessao.estado_dir) / "hitl.jsonl")


def aprovar(
    sessao: SessaoCOD,
    proposta_id: str,
    *,
    operador: str,
    validade_s: int = VALIDADE_TOKEN_S,
    executar: bool = True,
    origem: str = "http",
    cliente: str | None = None,
) -> dict[str, Any]:
    """Aprova (token emitido) e, por padrão, executa a sequência da proposta via ``set_switch``
    com esse token — cada manobra auditada. Devolve ``{proposta, execucao, operador}``; se uma
    manobra for recusada no meio, ``erro`` traz o motivo e ``execucao`` os passos feitos."""
    p = sessao.approve(proposta_id, operador=operador, validade_s=validade_s)
    hitl = hitl_log(sessao)
    if hitl is not None:
        hitl.registrar(
            "hitl.aprovacao",
            proposta=_sem_token(p),
            operador=operador,
            origem=origem,
            cliente=cliente,
            executar=executar,
        )
    saida: dict[str, Any] = {"operador": operador, "execucao": [], "erro": None}
    if executar:
        try:
            saida["execucao"] = executar_proposta(sessao, p)
        except (RecusadoError, SessaoError) as exc:
            saida["erro"] = str(exc)
    saida["proposta"] = sessao.propostas.obter(proposta_id).to_dict(com_token=False)
    return saida


def executar_proposta(sessao: SessaoCOD, p: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Aplica os passos restantes de uma proposta aprovada (dict com ``token``) em ordem."""
    token = p.get("token")
    passos: list[dict[str, Any]] = []
    for m in list(p["manobras"])[int(p.get("executadas", 0)) :]:
        passos.append(_executar_manobra(sessao, m, token))
    return passos


def _executar_manobra(sessao: SessaoCOD, m: Mapping[str, Any], token: str | None) -> dict[str, Any]:
    estado = "aberta" if m["acao"] == ABRIR else "fechada"
    return sessao.set_switch(m["chave"], estado, approval_token=token)


def executar_passo(
    sessao: SessaoCOD,
    proposta_id: str,
    *,
    operador: str,
    validade_s: int = VALIDADE_TOKEN_S,
    origem: str = "http",
    cliente: str | None = None,
) -> dict[str, Any]:
    """Modo **passo a passo** (pedido 1 da revisão PR-15): executa **uma** manobra da proposta — a
    próxima da sequência — por chamada. Se a proposta ainda está pendente, a primeira chamada a
    aprova (token emitido, ``hitl.aprovacao`` com ``executar: "passo"``) e executa o passo 1; as
    seguintes só executam. Cada passo é um ``set_switch`` auditado e vai para ``hitl.jsonl`` como
    ``hitl.passo``. Devolve ``{operador, passo, proposta, erro}``; ``passo`` é ``None`` se a
    proposta já estava concluída."""
    p = sessao.propostas.obter(proposta_id)  # relê o arquivo: decisões externas vencem
    hitl = hitl_log(sessao)
    if p.status == "pendente":
        aprovada = sessao.approve(proposta_id, operador=operador, validade_s=validade_s)
        if hitl is not None:
            hitl.registrar(
                "hitl.aprovacao",
                proposta=_sem_token(aprovada),
                operador=operador,
                origem=origem,
                cliente=cliente,
                executar="passo",
            )
        p = sessao.propostas.obter(proposta_id)
    if p.status != "aprovada":
        raise SessaoError(f"proposta {proposta_id} está {p.status}; nada a executar")
    saida: dict[str, Any] = {"operador": operador, "passo": None, "erro": None}
    proximo = p.proximo_passo
    if proximo is not None:
        try:
            saida["passo"] = _executar_manobra(sessao, proximo, p.token)
        except (RecusadoError, SessaoError) as exc:
            saida["erro"] = str(exc)
        if hitl is not None:
            hitl.registrar(
                "hitl.passo",
                proposta_id=proposta_id,
                operador=operador,
                origem=origem,
                cliente=cliente,
                manobra=dict(proximo),
                passo=None if saida["passo"] is None else saida["passo"].get("passo"),
                n_passos=len(p.manobras),
                erro=saida["erro"],
            )
    saida["proposta"] = sessao.propostas.obter(proposta_id).to_dict(com_token=False)
    return saida


def rejeitar(
    sessao: SessaoCOD,
    proposta_id: str,
    *,
    operador: str,
    motivo: str = "",
    origem: str = "http",
    cliente: str | None = None,
) -> dict[str, Any]:
    p = sessao.reject(proposta_id, operador=operador, motivo=motivo)
    hitl = hitl_log(sessao)
    if hitl is not None:
        hitl.registrar(
            "hitl.rejeicao",
            proposta=_sem_token(p),
            operador=operador,
            motivo=motivo,
            origem=origem,
            cliente=cliente,
        )
    return {"operador": operador, "proposta": _sem_token(p), "erro": None}


def _sem_token(p: Mapping[str, Any]) -> dict[str, Any]:
    d = dict(p)
    if d.get("token"):
        d["token"] = "***"
    return d
