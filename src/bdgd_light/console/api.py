"""Aplicação FastAPI do console (ver ``bdgd_light.console``).

Todas as rotas que decidem ou alteram estado (``POST``) exigem a identidade do operador
(``X-Operador`` + segredo, ``mcp_server.humano.Autorizador``); as leituras são livres. Os
handlers são síncronos de propósito: o FastAPI os executa num *threadpool*, e o fluxo de potência
do gêmeo leva segundos. O agente roda numa thread própria (``AgenteEmSegundoPlano``); enquanto
ele trabalha, injeção e aprovação respondem 409 — a sessão é uma só e não é *thread-safe*.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pyogrio.errors import DataSourceError

from bdgd_light.agent.audit import AuditError
from bdgd_light.grid.geojson import estado_geojson
from bdgd_light.mcp_server import humano
from bdgd_light.mcp_server.humano import Autorizador, NaoAutorizadoError
from bdgd_light.mcp_server.sessao import (
    LIMITE_REPLANEJAMENTOS_EVENTO,
    SessaoCOD,
    SessaoError,
    resolver_cluster,
)
from bdgd_light.sim.eventos import (
    CENARIOS,
    CHAVE_INDISPONIVEL,
    FALTA_PERMANENTE,
    FALTA_TRANSITORIA,
    PICO_CARGA,
    Evento,
    FilaEventos,
    Simulador,
)

LIMITE_EXECUCOES = 20
Corpo = Annotated[dict[str, Any] | None, Body()]  # corpo JSON opcional (objeto)


class AgenteEmSegundoPlano:
    """Executa o ``Orquestrador`` numa thread por evento e guarda as últimas execuções.

    ``sincrono=True`` (testes) trata o evento na própria thread. Uma execução por vez: ``tratar``
    devolve ``False`` se o agente está ocupado.
    """

    def __init__(self, orquestrador: Any, *, sincrono: bool = False):
        self.orq = orquestrador
        self.sincrono = sincrono
        self._thread: threading.Thread | None = None
        self.execucoes: list[dict[str, Any]] = []
        self.evento_atual: dict[str, Any] | None = None
        self.ultimo_evento: Evento | None = None
        self.erro: str | None = None
        self.inicio: str | None = None

    @property
    def ocupado(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def tratar(self, evento: Evento) -> bool:
        if self.ocupado:
            return False
        self.ultimo_evento = evento
        if self.sincrono:
            self._rodar(evento)
            return True
        self._thread = threading.Thread(target=self._rodar, args=(evento,), daemon=True)
        self._thread.start()
        return True

    def replanejar(self, proposta_id: str, motivo: str) -> str:
        """Nova execução para a mesma falta após rejeição; devolve o estado do disparo."""
        if self.ocupado:
            return "ocupado"
        if self.ultimo_evento is None:
            return "sem_evento"
        if self.orq.sessao.replanejamentos_evento >= LIMITE_REPLANEJAMENTOS_EVENTO:
            self.erro = (
                "SessaoError: limite de 3 replanejamentos automáticos por evento atingido; "
                "peça intervenção humana"
            )
            return "limite"
        try:
            if self.sincrono:
                self._rodar_replanejamento(proposta_id, motivo)
                return "erro" if self.erro else "concluido"
            self._thread = threading.Thread(
                target=self._rodar_replanejamento, args=(proposta_id, motivo), daemon=True
            )
            self._thread.start()
            return "iniciado"
        except SessaoError as exc:
            self.erro = str(exc)
            return "limite" if "limite de 3 replanejamentos" in str(exc) else "erro"

    def _rodar(self, evento: Evento) -> None:
        self.evento_atual = evento.to_dict()
        self.inicio = _agora()
        self.erro = None
        try:
            execucao = self.orq.executar_evento(evento)
            self.execucoes.append(execucao.to_dict())
            del self.execucoes[:-LIMITE_EXECUCOES]
        except Exception as exc:  # noqa: BLE001 — qualquer falha vira estado consultável
            self.erro = f"{type(exc).__name__}: {exc}"
        finally:
            self.evento_atual = None

    def _rodar_replanejamento(self, proposta_id: str, motivo: str) -> None:
        if self.ultimo_evento is None:
            raise SessaoError("nenhum evento anterior para replanejar")
        self.evento_atual = {
            **self.ultimo_evento.to_dict(),
            "replanejamento": {"proposta_id": proposta_id, "motivo": motivo},
        }
        self.inicio = _agora()
        self.erro = None
        try:
            execucao = self.orq.replanejar_apos_rejeicao(
                proposta_id, motivo, evento=self.ultimo_evento
            )
            self.execucoes.append(execucao.to_dict())
            del self.execucoes[:-LIMITE_EXECUCOES]
        except Exception as exc:  # noqa: BLE001 — qualquer falha vira estado consultável
            self.erro = f"{type(exc).__name__}: {exc}"
        finally:
            self.evento_atual = None

    def estado(self) -> dict[str, Any]:
        ultima = self.execucoes[-1] if self.execucoes else None
        return {
            "ocupado": self.ocupado,
            "provider": getattr(self.orq, "provider", None),
            "modelo": getattr(getattr(self.orq, "cliente", None), "modelo", None),
            "evento_atual": self.evento_atual,
            "inicio": self.inicio if self.ocupado else None,
            "erro": self.erro,
            "n_execucoes": len(self.execucoes),
            "replanejamentos_evento": getattr(
                getattr(self.orq, "sessao", None), "replanejamentos_evento", 0
            ),
            "ultima": None if ultima is None else _resumo_execucao(ultima),
        }


def _estado_motor() -> dict[str, Any] | None:
    """Modo/pid/reinícios do motor OpenDSS (``None`` sem o extra twin)."""
    try:
        from bdgd_light.twin.powerflow import estado_motor
    except ImportError:  # pragma: no cover - depende do extra
        return None
    return estado_motor()


def _resumo_execucao(d: Mapping[str, Any]) -> dict[str, Any]:
    chaves = (
        "evento_id",
        "tipo",
        "cluster",
        "proposta",
        "sequencia",
        "rodadas",
        "n_ferramentas",
        "recusas_verificador",
        "uso",
        "segundos_llm",
        "segundos_ferramentas",
        "segundos_total",
        "resposta",
        "erro",
        "modelo",
        "provider",
    )
    resumo = {k: d.get(k) for k in chaves if k in d}
    # a proposta completa vive em /api/propostas; aqui só o identificador
    if isinstance(resumo.get("proposta"), Mapping):
        resumo["proposta"] = resumo["proposta"].get("id")
    evento = d.get("evento")
    if isinstance(evento, Mapping):
        resumo["evento"] = {
            k: evento.get(k)
            for k in ("id", "tipo", "trecho", "ctmt", "chave", "cenario")
            if evento.get(k) is not None
        }
        resumo["alvo"] = _alvo_evento(evento)
        resumo["sem_manobra"] = bool(
            not d.get("proposta")
            and evento.get("tipo") in (FALTA_TRANSITORIA, PICO_CARGA, CHAVE_INDISPONIVEL)
        )
        destaques = _destaques_execucao(d)
        if destaques is not None:
            resumo["destaques"] = destaques
    return resumo


def _alvo_evento(evento: Mapping[str, Any]) -> str:
    for campo in ("trecho", "ctmt", "chave"):
        valor = evento.get(campo)
        if valor:
            return str(valor)
    return "—"


def _resultado_ferramenta(execucao: Mapping[str, Any], nome: str) -> Mapping[str, Any] | None:
    for chamada in reversed(execucao.get("ferramentas") or []):
        if (
            isinstance(chamada, Mapping)
            and chamada.get("ferramenta") == nome
            and chamada.get("ok") is True
            and isinstance(chamada.get("resultado"), Mapping)
        ):
            return chamada["resultado"]
    return None


def _cod_id_trecho_de_elemento(elemento: Any) -> str | None:
    nome = str(elemento or "").lower()
    prefixo = "line.smt_"
    if not nome.startswith(prefixo):
        return None
    return nome.split(prefixo, 1)[1].upper()


def _destaques_execucao(execucao: Mapping[str, Any]) -> dict[str, Any] | None:
    evento = execucao.get("evento")
    if not isinstance(evento, Mapping) or evento.get("tipo") != PICO_CARGA:
        return None
    fluxo = _resultado_ferramenta(execucao, "run_powerflow")
    if fluxo is None:
        return None
    trechos: list[str] = []
    for item in fluxo.get("sobrecargas") or []:
        if not isinstance(item, Mapping):
            continue
        cod = item.get("cod_id") or _cod_id_trecho_de_elemento(item.get("elemento"))
        if cod and cod not in trechos:
            trechos.append(str(cod))
    if not trechos:
        for item in fluxo.get("trechos_carregados_mt") or []:
            if not isinstance(item, Mapping):
                continue
            cod = item.get("cod_id") or _cod_id_trecho_de_elemento(item.get("elemento"))
            if cod and cod not in trechos:
                trechos.append(str(cod))
    return {
        "trechos": trechos,
        "n_subtensao": fluxo.get("n_subtensao"),
        "n_sobretensao": fluxo.get("n_sobretensao"),
        "n_sobrecargas": fluxo.get("n_sobrecargas"),
        "loadmult": fluxo.get("loadmult"),
    }


def _tipo_padrao(corpo: Mapping[str, Any]) -> str | None:
    """Tipo do evento: o informado; senão o que o alvo sugere (trecho → falta permanente, CTMT →
    pico de carga, chave → indisponível); sem alvo, ``None`` deixa o simulador sortear."""
    if corpo.get("tipo"):
        return str(corpo["tipo"])
    if corpo.get("trecho"):
        return FALTA_PERMANENTE
    if corpo.get("ctmt"):
        return PICO_CARGA
    if corpo.get("chave"):
        return CHAVE_INDISPONIVEL
    return None


def _agora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def criar_app(
    sessao: SessaoCOD,
    *,
    fila: FilaEventos,
    autorizador: Autorizador,
    agente: AgenteEmSegundoPlano | None = None,
    dist: Path | str | None = None,
) -> FastAPI:
    """Monta a aplicação. ``dist`` = pasta do console compilado (``npm run build``) para servir
    em ``/``; sem ela, só a API (o console em ``npm run dev`` usa ``?api=``)."""
    app = FastAPI(
        title="bdgd-light · console do COD",
        version="0.1.0",
        description="Fila de eventos, estado do grafo, propostas do agente e aprovação humana.",
    )
    from fastapi.middleware.cors import CORSMiddleware

    # console em desenvolvimento (vite, porta 5173) falando com a API em outra porta
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.state.sessao, app.state.fila, app.state.agente = sessao, fila, agente
    app.state.autorizador = autorizador

    def quem(request: Request) -> str:
        try:
            return autorizador.operador(request.headers)
        except NaoAutorizadoError as exc:
            raise HTTPException(exc.status, str(exc)) from None

    def exigir_agente_livre() -> None:
        if agente is not None and agente.ocupado:
            raise HTTPException(409, "agente em execução; aguarde a proposta")

    @app.exception_handler(SessaoError)
    async def _sessao_error(_: Request, exc: SessaoError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.get("/api/estado")
    def estado() -> dict[str, Any]:
        e = sessao.estado()
        e["eventos_n"] = len(fila)
        e["agente"] = None if agente is None else agente.estado()
        e["motor"] = _estado_motor()
        e["autorizacao"] = autorizador.modo
        e["hora"] = _agora()
        return e

    @app.get("/api/estado.geojson")
    def estado_mapa() -> dict[str, Any]:
        if sessao.rede is None:
            raise HTTPException(404, "nenhum cluster carregado")
        return estado_geojson(sessao.rede)

    @app.get("/api/eventos")
    def eventos(desde: int = Query(0, ge=0)) -> list[dict[str, Any]]:
        return [ev.to_dict() for ev in fila.listar(desde=desde)]

    @app.post("/api/eventos", status_code=202)
    def injetar(request: Request, corpo: Corpo = None) -> dict[str, Any]:
        """Modo demo: gera um evento (cenário nomeado ou tipo/alvo), publica na fila e, se houver
        agente, dispara o tratamento em segundo plano. ``recarregar: true`` recarrega o cluster
        antes (rede volta ao estado normal, falta zerada) — reinício da demo."""
        corpo = corpo or {}
        operador = quem(request)
        exigir_agente_livre()
        cenario = corpo.get("cenario")
        if cenario is not None and cenario not in CENARIOS:
            raise HTTPException(422, f"cenário {cenario!r} desconhecido; use {', '.join(CENARIOS)}")
        cluster = corpo.get("cluster") or (CENARIOS[cenario].cluster if cenario else None)
        if corpo.get("recarregar") and cluster is None and sessao.gpkg is not None:
            cluster = str(sessao.gpkg)
        try:
            _garantir_cluster(sessao, cluster, forcar=bool(corpo.get("recarregar")))
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None
        except (DataSourceError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from None
        if sessao.rede is None:
            raise HTTPException(409, "nenhum cluster carregado; informe cluster ou cenario")
        nome = sessao.cluster_demo or sessao.nome or ""
        sim = Simulador(sessao.rede, nome, seed=corpo.get("seed"))
        try:
            if cenario:
                ev = sim.cenario(cenario)
            else:
                ev = sim.gerar(
                    _tipo_padrao(corpo),
                    trecho=corpo.get("trecho"),
                    ctmt=corpo.get("ctmt"),
                    chave=corpo.get("chave"),
                )
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from None
        ev.detalhes["injetado_por"] = operador
        ev = fila.publicar(ev)
        situacao = "desligado"
        if agente is not None and corpo.get("agente", True):
            situacao = "iniciado" if agente.tratar(ev) else "ocupado"
        return {"evento": ev.to_dict(), "agente": situacao}

    @app.get("/api/propostas")
    def propostas(status: str | None = None) -> list[dict[str, Any]]:
        return [p.to_dict(com_token=False) for p in sessao.propostas.listar(status)]

    @app.get("/api/propostas/{proposta_id}")
    def proposta(proposta_id: str) -> dict[str, Any]:
        """Proposta + alternativas topológicas/elétricas + veredito do verificador do agente."""
        p = sessao.propostas.obter(proposta_id).to_dict(com_token=False)
        p["alternativas"] = sessao.alternativas(proposta_id)
        p["verificador"] = _veredito(agente, proposta_id)
        return p

    @app.get("/api/propostas/{proposta_id}/eletrico")
    def proposta_eletrica(proposta_id: str) -> dict[str, Any]:
        """Detalhes elétricos por opção simulada para a proposta.

        Reaproveita os scores do gêmeo OpenDSS já calculados em ``restore_options(score=true)``:
        corrente/margem no disjuntor, extremos de tensão MT com barra, perdas, trechos mais
        carregados, convergência e perfil de tensão da opção escolhida.
        """
        p = sessao.propostas.obter(proposta_id).to_dict(com_token=False)
        opcoes = [
            {
                "chave": a.get("chave"),
                "fonte": a.get("fonte"),
                "tlcd": a.get("tlcd"),
                "externa": a.get("externa"),
                "clientes": a.get("clientes"),
                "escolhida": bool(a.get("escolhida")),
                "score": a.get("score"),
            }
            for a in sessao.alternativas(proposta_id)
            if isinstance(a.get("score"), Mapping)
        ]
        if not opcoes and isinstance(p.get("score"), Mapping):
            opcoes = [
                {
                    "chave": p.get("chave"),
                    "fonte": p.get("fonte"),
                    "tlcd": p.get("score", {}).get("tlcd"),
                    "externa": False,
                    "clientes": p.get("clientes"),
                    "escolhida": True,
                    "score": p.get("score"),
                }
            ]
        if not opcoes:
            raise HTTPException(
                409,
                "proposta sem detalhes elétricos disponíveis; gere alternativas com score=true",
            )
        score_escolhido = next(
            (
                o["score"]
                for o in opcoes
                if o.get("escolhida") and isinstance(o.get("score"), Mapping)
            ),
            opcoes[0]["score"],
        )
        return {
            "proposta_id": p["id"],
            "status": p["status"],
            "falta": p["falta"],
            "escolhida": p["chave"],
            "simulado_em": score_escolhido.get("simulado_em"),
            "estado_rede": score_escolhido.get("estado_rede"),
            "opcoes": opcoes,
        }

    @app.post("/api/propostas/{proposta_id}/aprovar")
    def aprovar(request: Request, proposta_id: str, corpo: Corpo = None) -> dict[str, Any]:
        corpo = corpo or {}
        operador = quem(request)
        exigir_agente_livre()
        return humano.aprovar(
            sessao,
            proposta_id,
            operador=operador,
            validade_s=int(corpo.get("validade_s", 1800)),
            executar=bool(corpo.get("executar", True)),
            origem="console",
            cliente=request.client.host if request.client else None,
        )

    @app.post("/api/propostas/{proposta_id}/passo")
    def passo(request: Request, proposta_id: str, corpo: Corpo = None) -> dict[str, Any]:
        """Modo passo a passo: aprova (se pendente) e executa **uma** manobra — a próxima da
        sequência — por chamada; o mapa recolore a cada passo."""
        corpo = corpo or {}
        operador = quem(request)
        exigir_agente_livre()
        return humano.executar_passo(
            sessao,
            proposta_id,
            operador=operador,
            validade_s=int(corpo.get("validade_s", 1800)),
            origem="console",
            cliente=request.client.host if request.client else None,
        )

    @app.post("/api/propostas/{proposta_id}/rejeitar")
    def rejeitar(request: Request, proposta_id: str, corpo: Corpo = None) -> dict[str, Any]:
        corpo = corpo or {}
        operador = quem(request)
        resultado = humano.rejeitar(
            sessao,
            proposta_id,
            operador=operador,
            motivo=str(corpo.get("motivo", "")),
            origem="console",
            cliente=request.client.host if request.client else None,
        )
        motivo = str(corpo.get("motivo", "")).strip()
        status = "sem_agente"
        if agente is not None:
            status = agente.replanejar(proposta_id, motivo)
        resultado["replanejamento"] = {
            "status": status,
            "mensagem": {
                "iniciado": "agente replanejando com a restrição informada",
                "concluido": "agente replanejou com a restrição informada",
                "ocupado": "agente ainda ocupado; aguarde a execução atual",
                "sem_evento": "não há evento anterior para replanejar",
                "sem_agente": "console sem agente automático; intervenção humana necessária",
                "limite": (
                    "limite de 3 replanejamentos por evento atingido; peça intervenção humana"
                ),
                "erro": "falha ao iniciar o replanejamento automático",
            }.get(status, status),
        }
        return resultado

    @app.get("/api/auditoria")
    def auditoria(n: int = Query(12, ge=1, le=200)) -> dict[str, Any]:
        """Últimos ``n`` registros (compactos) e a verificação da cadeia inteira."""
        audit = sessao.audit
        if audit is None:
            return {"n_total": 0, "integra": None, "hash": None, "registros": []}
        try:
            audit.verificar()
            integra: bool | None = True
        except AuditError:
            integra = False
        registros = [_registro_compacto(r.to_dict()) for r in audit.registros[-n:]]
        return {
            "n_total": len(audit),
            "integra": integra,
            "hash": audit.ultimo_hash if len(audit) else None,
            "registros": registros,
        }

    @app.get("/api/agente")
    def agente_estado(n: int = Query(5, ge=1, le=LIMITE_EXECUCOES)) -> dict[str, Any]:
        if agente is None:
            return {"ativo": False}
        return {
            "ativo": True,
            **agente.estado(),
            "execucoes": [_resumo_execucao(e) for e in agente.execucoes[-n:]],
        }

    if dist is not None and Path(dist).is_dir():
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(dist), html=True), name="console")
    return app


def _garantir_cluster(sessao: SessaoCOD, cluster: str | None, *, forcar: bool = False) -> None:
    """Carrega ``cluster`` se a sessão está vazia ou com outro cluster (sempre, com ``forcar``);
    ``None`` mantém o atual."""
    if cluster is None:
        return
    alvo = resolver_cluster(cluster, sessao.feeders)
    if forcar or sessao.gpkg is None or Path(sessao.gpkg).resolve() != alvo.resolve():
        sessao.load_cluster(str(alvo))


def _veredito(agente: AgenteEmSegundoPlano | None, proposta_id: str) -> dict[str, Any] | None:
    """Veredito do verificador na execução do agente que gerou ``proposta_id`` (o veredito vive
    na execução, não na proposta da sessão)."""
    if agente is None:
        return None
    for ex in reversed(agente.execucoes):
        prop = ex.get("proposta")
        if isinstance(prop, Mapping) and prop.get("id") == proposta_id:
            return ex.get("veredito")
    return None


def _registro_compacto(r: Mapping[str, Any]) -> dict[str, Any]:
    dados = r.get("dados") or {}
    saida = {
        "seq": r.get("seq"),
        "ts": r.get("ts"),
        "tipo": r.get("tipo"),
        "hash": r.get("hash"),
    }
    for k in ("ferramenta", "ms", "erro", "operador", "proposta_id", "modelo", "rodada"):
        if k in dados:
            saida[k] = dados[k]
    args = dados.get("argumentos")
    if isinstance(args, Mapping) and args:
        saida["argumentos"] = {k: v for k, v in args.items() if k != "approval_token"}
    return saida
