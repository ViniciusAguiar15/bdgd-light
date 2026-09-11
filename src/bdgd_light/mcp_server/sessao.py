"""Sessão do COD: o estado de um cluster carregado e as operações que o servidor MCP expõe.

A sessão é o *domínio* por trás das ferramentas (padrão PowerChain: descritores + execução
verificável). Ela não depende do SDK ``mcp`` — o agente pode usá-la em processo e os testes
exercitam-na direto. Cada método marcado com ``@ferramenta`` vai para o ``AuditLog`` (JSON Lines
encadeado por hash) com argumentos, resumo do resultado e o SHA-256 do resultado completo.

Fluxo FLISR simulado::

    load_cluster → inject_fault → locate_fault → isolate_fault → restore_options →
    propose_plan → [humano: approve → token] → set_switch(chave, estado, token) × n

``inject_fault`` abre o **religador** (a primeira chave entre a fonte e o trecho) e marca o trecho
em falta; ``locate_fault``/``isolate_fault``/``restore_options`` raciocinam sobre a **vista de
plano** (religador fechado, como a rede ficará depois de isolar e religar). Nada muda o estado das
chaves a não ser ``set_switch`` com um token emitido por ``approve`` — que **não** é ferramenta do
modelo: só o console/CLI humano (``bdgd-light aprovar``) o chama. A ``FilaPropostas`` é gravada em
JSON para que a aprovação possa vir de outro processo.
"""

from __future__ import annotations

import functools
import hashlib
import inspect
import json
import math
import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

from bdgd_light.agent.audit import AuditLog
from bdgd_light.grid.impacto import (
    TEMPO_REPARO_PADRAO_MIN,
    calcular_impacto_opcao,
    premissa_impacto,
)
from bdgd_light.grid.rede import (
    ABRIR,
    CHAVE,
    FECHAR,
    ChaveInexistenteError,
    Cluster,
    Feeder,
    Isolamento,
    Rede,
    TrechoInexistenteError,
    ler_camadas,
    manobra,
)

FEEDERS_PADRAO = Path("data/feeders")
DSS_PADRAO = Path("data/dss/gpkg")
ESTADO_PADRAO = Path("data/agent")
VALIDADE_TOKEN_S = 30 * 60

# nomes da demo (docs/escopo-cidade.md v3) → GeoPackage em --feeders
CLUSTERS = {
    "tijuca": "cluster_tijuca.gpkg",
    "ipanema": "cluster_ipanema.gpkg",
    "taquara": "cluster_TQR0007-TQR33859-TQR33862.gpkg",
}
ESTADOS_CHAVE = {"aberta": ABRIR, "fechada": FECHAR, ABRIR: ABRIR, FECHAR: FECHAR}
LIMITE_LISTA_AUDIT = 30
LIMITE_TEXTO_AUDIT = 300
LIMITE_REPLANEJAMENTOS_EVENTO = 3


class SessaoError(RuntimeError):
    """Erro de uso da sessão (sem cluster, sem falta, opção inexistente…)."""


class RecusadoError(PermissionError):
    """``set_switch`` recusado: sem token válido, fora de sequência ou proposta vencida."""


def _agora() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def _canonico(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _limpar(obj: Any) -> Any:
    """Torna JSON-serializável (NaN → None, conjuntos → listas ordenadas, Path → str)."""
    if isinstance(obj, Mapping):
        return {str(k): _limpar(v) for k, v in obj.items()}
    if isinstance(obj, set | frozenset):
        return sorted(_limpar(v) for v in obj)
    if isinstance(obj, list | tuple):
        return [_limpar(v) for v in obj]
    if isinstance(obj, bool | int | str) or obj is None:
        return obj
    if isinstance(obj, float):
        return None if math.isnan(obj) else obj
    if hasattr(obj, "item"):  # escalares numpy
        return _limpar(obj.item())
    return str(obj)


def _compactar(obj: Any) -> Any:
    """Versão curta para o log: listas longas e textos grandes truncados (o hash cobre o todo)."""
    if isinstance(obj, dict):
        return {k: _compactar(v) for k, v in obj.items()}
    if isinstance(obj, list):
        if len(obj) > LIMITE_LISTA_AUDIT:
            inicio = [_compactar(v) for v in obj[:LIMITE_LISTA_AUDIT]]
            return [*inicio, f"…(+{len(obj) - LIMITE_LISTA_AUDIT})"]
        return [_compactar(v) for v in obj]
    if isinstance(obj, str) and len(obj) > LIMITE_TEXTO_AUDIT:
        return obj[: LIMITE_TEXTO_AUDIT - 1] + "…"
    return obj


CHAVES_TOKEN = frozenset({"approval_token", "token"})


def _mascarar_token(obj: Any) -> Any:
    """Tokens nunca vão em claro para a auditoria: só o prefixo do SHA-256 (rastreável)."""
    if isinstance(obj, dict):
        return {
            k: (
                f"sha256:{hashlib.sha256(str(v).encode()).hexdigest()[:12]}"
                if k in CHAVES_TOKEN and isinstance(v, str) and v not in ("", "***")
                else _mascarar_token(v)
            )
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_mascarar_token(v) for v in obj]
    return obj


def ferramenta(descricao: str) -> Callable:
    """Marca um método da sessão como ferramenta: audita chamada, resultado e erros."""

    def decorador(metodo: Callable) -> Callable:
        assinatura = inspect.signature(metodo)

        @functools.wraps(metodo)
        def wrapper(self: SessaoCOD, *args, **kwargs):
            vinculo = assinatura.bind(self, *args, **kwargs)
            vinculo.apply_defaults()
            argumentos = _limpar({k: v for k, v in vinculo.arguments.items() if k != "self"})
            inicio = perf_counter()
            try:
                resultado = metodo(self, *args, **kwargs)
            except RecusadoError as exc:
                self._auditar("mcp.recusa", metodo.__name__, argumentos, inicio, erro=str(exc))
                raise
            except Exception as exc:
                self._auditar("mcp.erro", metodo.__name__, argumentos, inicio, erro=str(exc))
                raise
            resultado = _limpar(resultado)
            self._auditar("mcp.chamada", metodo.__name__, argumentos, inicio, resultado=resultado)
            return resultado

        wrapper.descricao = descricao  # type: ignore[attr-defined]
        wrapper.ferramenta = True  # type: ignore[attr-defined]
        return wrapper

    return decorador


# ---------------------------------------------------------------------------------------------
# Propostas (plano de manobras pendente de aprovação humana)
# ---------------------------------------------------------------------------------------------


@dataclass
class Proposta:
    id: str
    criada_em: str
    cluster: str
    falta: str | None
    chave: str | None  # NA a fechar (a opção escolhida); None = só isolar e religar
    fonte: str
    manobras: list[dict]  # sequência completa e ordenada: abrir…, [fechar religador], [fechar NA]
    clientes: dict
    score: dict | None = None
    impacto: dict | None = None
    ja_satisfeitas: list[str] = field(default_factory=list)
    status: str = "pendente"  # pendente | aprovada | rejeitada | executada | expirada
    token: str | None = None
    aprovada_em: str | None = None
    aprovada_por: str | None = None
    expira_em: str | None = None
    motivo: str | None = None
    executadas: int = 0
    replanejada_apos_rejeicao: str | None = None
    restricoes_resumo: list[str] = field(default_factory=list)

    @property
    def proximo_passo(self) -> dict | None:
        return self.manobras[self.executadas] if self.executadas < len(self.manobras) else None

    def to_dict(self, *, com_token: bool = True) -> dict[str, Any]:
        d = asdict(self)
        d["proximo_passo"] = self.proximo_passo
        d["n_passos"] = len(self.manobras)
        if not com_token:
            d["token"] = None if self.token is None else "***"
        return d

    @classmethod
    def de_dict(cls, d: Mapping[str, Any]) -> Proposta:
        campos = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in campos})


@dataclass
class RestricaoOperacional:
    """Restrição explícita aplicada à sessão após rejeição humana."""

    motivo: str
    criada_em: str
    chaves_proibidas: list[str] = field(default_factory=list)
    alimentadores_evitar: list[str] = field(default_factory=list)
    somente_telecomandadas: bool = False
    resumo: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def de_dict(cls, d: Mapping[str, Any]) -> RestricaoOperacional:
        campos = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in campos})


class FilaPropostas:
    """Propostas em memória, espelhadas em ``caminho`` (JSON) quando informado.

    Outro processo (CLI ``bdgd-light aprovar``, console) pode aprovar/rejeitar no arquivo;
    ``sincronizar`` traz essas decisões para a memória antes de qualquer verificação de token.
    """

    def __init__(
        self, caminho: Path | str | None = None, *, agora: Callable[[], datetime] = _agora
    ):
        self.caminho = None if caminho is None else Path(caminho)
        self._agora = agora
        self._itens: dict[str, Proposta] = {}
        self.sincronizar()

    def __len__(self) -> int:
        return len(self._itens)

    def __iter__(self):
        return iter(self._itens.values())

    def obter(self, proposta_id: str) -> Proposta:
        self.sincronizar()
        try:
            return self._itens[proposta_id]
        except KeyError:
            raise SessaoError(f"proposta {proposta_id!r} não existe") from None

    def listar(self, status: str | None = None) -> list[Proposta]:
        self.sincronizar()
        return [p for p in self._itens.values() if status is None or p.status == status]

    def criar(self, **campos: Any) -> Proposta:
        self.sincronizar()
        p = Proposta(id=f"P-{len(self._itens) + 1:04d}", criada_em=_iso(self._agora()), **campos)
        self._itens[p.id] = p
        self.salvar()
        return p

    def aprovar(
        self, proposta_id: str, *, operador: str = "operador", validade_s: int = VALIDADE_TOKEN_S
    ) -> Proposta:
        p = self.obter(proposta_id)
        if p.status != "pendente":
            raise SessaoError(f"proposta {proposta_id} está {p.status}; só pendentes são aprovadas")
        agora = self._agora()
        p.status = "aprovada"
        p.token = secrets.token_urlsafe(18)
        p.aprovada_em = _iso(agora)
        p.aprovada_por = operador
        p.expira_em = _iso(agora + timedelta(seconds=validade_s))
        self.salvar()
        return p

    def rejeitar(
        self, proposta_id: str, *, operador: str = "operador", motivo: str = ""
    ) -> Proposta:
        p = self.obter(proposta_id)
        if p.status not in ("pendente", "aprovada"):
            raise SessaoError(f"proposta {proposta_id} está {p.status}; não pode ser rejeitada")
        p.status = "rejeitada"
        p.token = None
        p.aprovada_por = operador
        p.motivo = motivo or None
        self.salvar()
        return p

    def por_token(self, token: str | None) -> Proposta | None:
        """Proposta cujo token confere (comparação em tempo constante); ``None`` se nenhuma."""
        self.sincronizar()
        if not token:
            return None
        for p in self._itens.values():
            if p.token and secrets.compare_digest(p.token, str(token)):
                return p
        return None

    def vencida(self, p: Proposta) -> bool:
        return bool(p.expira_em) and datetime.fromisoformat(p.expira_em) <= self._agora()

    def salvar(self) -> None:
        if self.caminho is None:
            return
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        dados = [p.to_dict() for p in self._itens.values()]
        for d in dados:
            d.pop("proximo_passo", None)
            d.pop("n_passos", None)
        self.caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")

    def sincronizar(self) -> None:
        """Relê o arquivo: decisões (aprovar/rejeitar) tomadas fora vencem as da memória."""
        if self.caminho is None or not self.caminho.exists():
            return
        try:
            gravadas = json.loads(self.caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SessaoError(f"arquivo de propostas {self.caminho} ilegível: {exc}") from exc
        for d in gravadas:
            gravada = Proposta.de_dict(d)
            atual = self._itens.get(gravada.id)
            if atual is None:
                self._itens[gravada.id] = gravada
            elif atual.status == "pendente" and gravada.status in ("aprovada", "rejeitada"):
                for campo in (
                    "status",
                    "token",
                    "aprovada_em",
                    "aprovada_por",
                    "expira_em",
                    "replanejada_apos_rejeicao",
                ):
                    setattr(atual, campo, getattr(gravada, campo))
                atual.motivo = gravada.motivo or atual.motivo


# ---------------------------------------------------------------------------------------------
# Sessão
# ---------------------------------------------------------------------------------------------


def resolver_cluster(cluster: str, feeders: Path | str = FEEDERS_PADRAO) -> Path:
    """GeoPackage de um cluster: caminho direto, nome da demo (``CLUSTERS``) ou
    ``<feeders>/cluster_<nome>.gpkg`` / ``<feeders>/<nome>.gpkg``."""
    feeders = Path(feeders)
    direto = Path(cluster)
    if direto.is_file():
        return direto
    candidatos = [
        feeders / CLUSTERS.get(cluster.lower(), ""),
        feeders / f"cluster_{cluster}.gpkg",
        feeders / f"{cluster}.gpkg",
    ]
    for c in candidatos:
        if c.name and c.is_file():
            return c
    raise FileNotFoundError(
        f"cluster {cluster!r} não encontrado em {feeders} (nomes conhecidos: "
        f"{', '.join(CLUSTERS)}; ou informe o caminho de um .gpkg do recorte)"
    )


class SessaoCOD:
    """Um cluster carregado + falta simulada + propostas; toda ferramenta é auditada."""

    def __init__(
        self,
        *,
        feeders: Path | str = FEEDERS_PADRAO,
        dss_out: Path | str = DSS_PADRAO,
        estado_dir: Path | str | None = ESTADO_PADRAO,
        audit: AuditLog | None = None,
        dia: str = "DU",
        mes: int = 1,
        agora: Callable[[], datetime] = _agora,
    ):
        self.feeders = Path(feeders)
        self.dss_out = Path(dss_out)
        self.estado_dir = None if estado_dir is None else Path(estado_dir)
        self.dia, self.mes = dia, mes
        self._agora = agora
        if audit is None and self.estado_dir is not None:
            audit = AuditLog(self.estado_dir / "audit.jsonl")
        self.audit = audit
        self.propostas = FilaPropostas(
            None if self.estado_dir is None else self.estado_dir / "propostas.json", agora=agora
        )
        self.rede: Rede | None = None
        self.gpkg: Path | None = None
        self.nome: str | None = None
        self.falta: str | None = None
        self.religador: str | None = None
        self._indicacoes: list[str] = []
        self._master_base: Path | None = None
        self._scores: dict[str, dict] = {}  # último restore_options com score, por chave
        self.restricoes: list[RestricaoOperacional] = []
        self.replanejamentos_evento = 0
        self.ultima_rejeicao: str | None = None

    @property
    def restricoes_agregadas(self) -> dict[str, Any]:
        """Visão agregada das restrições ativas, para console e verificador."""
        chaves: list[str] = []
        alimentadores: list[str] = []
        somente_telecomandadas = False
        for r in self.restricoes:
            chaves.extend(r.chaves_proibidas)
            alimentadores.extend(r.alimentadores_evitar)
            somente_telecomandadas = somente_telecomandadas or r.somente_telecomandadas
        return {
            "chaves_proibidas": sorted(set(chaves)),
            "alimentadores_evitar": sorted(set(alimentadores)),
            "somente_telecomandadas": somente_telecomandadas,
            "motivos": [r.motivo for r in self.restricoes],
        }

    def limpar_restricoes(self) -> None:
        """Zera o histórico de restrições do evento atual."""
        self.restricoes = []
        self.replanejamentos_evento = 0
        self.ultima_rejeicao = None

    def aplicar_restricao(self, restricao: Mapping[str, Any], *, motivo: str) -> dict[str, Any]:
        """Anexa a restrição estruturada à sessão e registra o motivo da rejeição."""

        def _lista(campo: str) -> list[str]:
            valores = restricao.get(campo) or []
            if not isinstance(valores, list):
                return []
            vistos: set[str] = set()
            saida: list[str] = []
            for valor in valores:
                texto = str(valor).strip()
                if texto and texto not in vistos:
                    vistos.add(texto)
                    saida.append(texto)
            return saida

        item = RestricaoOperacional(
            motivo=motivo.strip() or "sem motivo informado",
            criada_em=_iso(self._agora()),
            chaves_proibidas=_lista("chaves_proibidas"),
            alimentadores_evitar=_lista("alimentadores_evitar"),
            somente_telecomandadas=bool(restricao.get("somente_telecomandadas")),
            resumo=(str(restricao.get("resumo")).strip() or None)
            if restricao.get("resumo") is not None
            else None,
        )
        self.restricoes.append(item)
        self.replanejamentos_evento += 1
        self.ultima_rejeicao = item.motivo
        return item.to_dict()

    def resumo_restricoes(self) -> list[str]:
        """Descrições curtas das restrições ativas para o prompt/situação da sessão."""
        linhas = []
        for r in self.restricoes:
            partes = []
            if r.chaves_proibidas:
                partes.append("chaves proibidas: " + ", ".join(r.chaves_proibidas))
            if r.alimentadores_evitar:
                partes.append("alimentadores a evitar: " + ", ".join(r.alimentadores_evitar))
            if r.somente_telecomandadas:
                partes.append("usar apenas rotas/manobras telecomandadas")
            corpo = "; ".join(partes) or (r.resumo or "motivo sem restrição estruturada")
            linhas.append(f"{corpo} (motivo: {r.motivo})")
        return linhas

    @staticmethod
    def _normalizar_alimentador(valor: str | None) -> str:
        return "".join(ch for ch in str(valor or "").upper() if ch.isalnum())

    @classmethod
    def _match_alimentador(cls, alvo: str, valor: str | None) -> tuple[bool, bool]:
        if not alvo or not valor:
            return False, False
        a = cls._normalizar_alimentador(alvo)
        b = cls._normalizar_alimentador(valor)
        if not a or not b:
            return False, False
        if a == b:
            return True, False
        return (a in b or b in a), True

    @classmethod
    def _descricao_match_alimentador(cls, alvo: str, valor: str) -> str:
        a = cls._normalizar_alimentador(alvo)
        b = cls._normalizar_alimentador(valor)
        modo = "prefixo" if a.startswith(b) or b.startswith(a) else "substring"
        return f"casamento aproximado: {alvo} casou com {valor} por {modo}"

    @classmethod
    def _restricao_alimentador(
        cls, alvos: Sequence[str], *valores: str | None
    ) -> tuple[str, str, bool] | None:
        for alvo in alvos:
            for valor in valores:
                texto = str(valor or "").strip()
                if not texto:
                    continue
                casou, aproximado = cls._match_alimentador(alvo, texto)
                if casou:
                    return alvo, texto, aproximado
        return None

    def motivo_bloqueio_opcao(self, opcao: Mapping[str, Any]) -> str | None:
        """Explica por que a opção viola alguma restrição ativa; ``None`` se liberada."""
        if not self.restricoes:
            return None
        rede = self._rede()
        motivos: list[str] = []
        chaves_seq = [
            str(m.get("chave"))
            for m in list(opcao.get("manobras") or [])
            if isinstance(m, Mapping) and m.get("chave")
        ]
        chave_opcao = str(opcao.get("chave") or "")
        fonte = str(opcao.get("fonte") or "")
        for r in self.restricoes:
            proibidas = set(r.chaves_proibidas)
            usadas = sorted({c for c in [chave_opcao, *chaves_seq] if c in proibidas})
            if usadas:
                motivos.append(f"{r.motivo}: usa chave proibida {', '.join(usadas)}")
            ctmt_chave = str(opcao.get("ctmt_chave") or "")
            match_alimentador = self._restricao_alimentador(
                r.alimentadores_evitar, fonte, ctmt_chave
            )
            if match_alimentador is not None:
                alvo, valor, aproximado = match_alimentador
                texto = f"{r.motivo}: evita alimentar pela fonte {fonte or ctmt_chave}"
                if aproximado:
                    texto += f" ({self._descricao_match_alimentador(alvo, valor)})"
                motivos.append(texto)
            if r.somente_telecomandadas:
                sem_telecom = []
                if not bool(opcao.get("tlcd")):
                    sem_telecom.append(chave_opcao)
                for chave in chaves_seq:
                    if chave in rede.chaves and not bool(self._dados_chave(rede, chave)["tlcd"]):
                        sem_telecom.append(chave)
                if sem_telecom:
                    unicas = ", ".join(sorted(set(filter(None, sem_telecom))))
                    motivos.append(
                        f"{r.motivo}: exige só telecomandadas; há manobra local em {unicas}"
                    )
        return "; ".join(motivos) or None

    def motivos_restricao_sequencia(
        self,
        sequencia: Sequence[Mapping[str, Any]],
        *,
        chave: str | None = None,
        fonte: str | None = None,
        opcao: Mapping[str, Any] | None = None,
    ) -> list[str]:
        """Motivos determinísticos para o verificador reprovar um plano por restrição ativa."""
        if opcao is not None:
            bloqueio = self.motivo_bloqueio_opcao(opcao)
            return [bloqueio] if bloqueio else []
        if not self.restricoes:
            return []
        rede = self._rede()
        chaves_seq = [str(m.get("chave")) for m in sequencia if m.get("chave")]
        motivos: list[str] = []
        for r in self.restricoes:
            proibidas = sorted(
                {c for c in [*(chaves_seq or []), chave or ""] if c in r.chaves_proibidas}
            )
            if proibidas:
                motivos.append(f"{r.motivo}: usa chave proibida {', '.join(proibidas)}")
            match_alimentador = self._restricao_alimentador(r.alimentadores_evitar, fonte)
            if match_alimentador is not None:
                alvo, valor, aproximado = match_alimentador
                texto = f"{r.motivo}: evita alimentar pelo alimentador {fonte}"
                if aproximado:
                    texto += f" ({self._descricao_match_alimentador(alvo, valor)})"
                motivos.append(texto)
            if r.somente_telecomandadas:
                sem_telecom = [
                    c
                    for c in chaves_seq
                    if c in rede.chaves and not bool(self._dados_chave(rede, c)["tlcd"])
                ]
                if sem_telecom:
                    motivos.append(
                        f"{r.motivo}: exige só telecomandadas; há manobra local em "
                        + ", ".join(sorted(set(sem_telecom)))
                    )
        return motivos

    # -- infraestrutura -----------------------------------------------------------------------

    def _auditar(self, tipo: str, nome: str, argumentos, inicio: float, **extra) -> None:
        if self.audit is None:
            return
        dados: dict[str, Any] = {
            "ferramenta": nome,
            "argumentos": _mascarar_token(dict(argumentos)),
            "ms": round((perf_counter() - inicio) * 1000, 1),
            "cluster": self.nome,
        }
        if "resultado" in extra:
            # o hash cobre o resultado completo (com o token mascarado, para poder ser conferido)
            completo = _mascarar_token(extra["resultado"])
            dados["resultado"] = _compactar(completo)
            dados["resultado_sha256"] = hashlib.sha256(_canonico(completo).encode()).hexdigest()
        if "erro" in extra:
            dados["erro"] = extra["erro"]
        self.audit.registrar(tipo, **dados)

    def _rede(self) -> Rede:
        if self.rede is None:
            raise SessaoError("nenhum cluster carregado; chame load_cluster primeiro")
        return self.rede

    def _com_falta(self) -> tuple[Rede, str]:
        rede = self._rede()
        if self.falta is None:
            raise SessaoError("não há falta simulada; chame inject_fault primeiro")
        return rede, self.falta

    def _plano(self) -> Rede:
        """Vista de plano: a rede como ficará após isolar e religar (religador fechado)."""
        rede = self._rede()
        if self.religador is None or not rede.is_open(self.religador):
            return rede
        plano = rede.copy()
        plano.close_switch(self.religador)
        return plano

    def _religar(self, iso: Isolamento) -> bool:
        """O religador pode fechar depois do isolamento (não é chave de fronteira da zona)?"""
        return self.religador is not None and self.religador not in iso.chaves

    def _sequencia(
        self, rede: Rede, iso: Isolamento, religar: bool, fechar: str | None = None
    ) -> list[dict]:
        """Passos na ordem segura: abrir fronteira → religar o tronco são → fechar a NA."""
        passos = [manobra(ABRIR, c) for c in iso.chaves if not rede.is_open(c)]
        if religar and self.religador and rede.is_open(self.religador):
            passos.append(manobra(FECHAR, self.religador))
        if fechar is not None:
            passos.append(manobra(FECHAR, fechar))
        return passos

    def _dados_chave(self, rede: Rede, cod: str) -> dict[str, Any]:
        if cod not in rede.chaves:
            raise ChaveInexistenteError(cod)
        u, v = rede.chaves[cod]
        d = rede.grafo.edges[u, v]
        return {
            "chave": cod,
            "ctmt": d["ctmt"],
            "estado": "aberta" if d["aberta"] else "fechada",
            "normal": d["normal"],
            "tlcd": bool(d["tlcd"]),
            "tip_unid": d["tip_unid"],
            "externa": bool(d.get("externa", False)),
            "pac": [u, v],
            "energizado_por": [rede.energized_by(u), rede.energized_by(v)],
        }

    def _sem_tensao(self, rede: Rede) -> dict[str, Any]:
        energizados = rede.energized_nodes()
        apagados = [n for n in rede.nos() if n not in energizados]
        return {"n_nos": len(apagados), "clientes": rede.customers(apagados).to_dict()}

    def _estado_rede_score(self, rede: Rede) -> dict[str, Any]:
        """Resumo serializável do estado-base usado pelo último lote de score elétrico."""
        return {
            "cluster": self.nome,
            "falta": self.falta,
            "religador": self.religador,
            "manobras": self._manobras_estado(rede),
        }

    def _manobras_estado(self, rede: Rede) -> list[dict]:
        """Manobras que levam do estado normal (P_N_OPE) ao estado atual das chaves."""
        passos = []
        for cod, (u, v) in rede.chaves.items():
            d = rede.grafo.edges[u, v]
            if d["aberta"] != (d["normal"] == "NA"):
                passos.append(manobra(ABRIR if d["aberta"] else FECHAR, cod))
        return passos

    @staticmethod
    def _cod_id_elemento_mt(elemento: str | None) -> str | None:
        nome = str(elemento or "").lower()
        prefixo = "line.smt_"
        if not nome.startswith(prefixo):
            return None
        return nome.split(prefixo, 1)[1].upper()

    @classmethod
    def _trechos_carregados_mt(cls, correntes, *, limite: int = 5) -> list[dict[str, Any]]:
        if len(correntes) == 0:
            return []
        linhas = correntes[correntes["elemento"].str.lower().str.startswith("line.smt_")]
        linhas = linhas.dropna(subset=["carregamento_pct"]).sort_values(
            "carregamento_pct", ascending=False
        )
        return [
            {
                "elemento": item["elemento"],
                "cod_id": cls._cod_id_elemento_mt(item.get("elemento")),
                "i_max_a": item["i_max_a"],
                "i_nominal_a": item["i_nominal_a"],
                "carregamento_pct": item["carregamento_pct"],
            }
            for item in linhas.head(limite).to_dict(orient="records")
        ]

    @staticmethod
    def _religador_de(rede: Rede, ctmt: str) -> str | None:
        """Chave de cabeceira do CTMT: a primeira chave ligada ao PAC da fonte."""
        inicio = rede.fontes.get(ctmt)
        if inicio is None:
            return None
        for d in rede.grafo.adj[inicio].values():
            if d["tipo"] == CHAVE:
                return d["cod"]
        return None

    def master_base(self) -> Path:
        """Master base do cluster no gêmeo (converte do GPKG o que faltar; exige extra ``twin``)."""
        if self._master_base is None:
            rede = self._rede()
            try:
                from bdgd_light.twin import preparar_master_cluster
            except ImportError as exc:
                raise SessaoError(f"{exc} — instale o extra: uv sync --extra twin") from exc
            self._master_base = preparar_master_cluster(
                self.gpkg, rede.ctmts, self.dss_out, dia=self.dia, mes=self.mes
            )
        return self._master_base

    def _resolver_cluster(self, cluster: str) -> Path:
        return resolver_cluster(cluster, self.feeders)

    # -- ferramentas ---------------------------------------------------------------------------

    @ferramenta(
        "Carrega um cluster de alimentadores: nome da demo (tijuca, ipanema, taquara) ou caminho "
        "de um GeoPackage do recorte. Zera a falta e expira propostas em aberto. Devolve o resumo "
        "da rede (nós, km, chaves, ties, clientes) e o religador de cada CTMT."
    )
    def load_cluster(self, cluster: str) -> dict[str, Any]:
        caminho = self._resolver_cluster(cluster)
        camadas = ler_camadas(caminho)
        self.rede = Feeder(camadas) if len(camadas.ctmt) == 1 else Cluster(camadas)
        self.gpkg = caminho
        self.nome = caminho.stem
        self.falta = self.religador = None
        self._indicacoes = []
        self._master_base = None
        self._scores = {}
        self.limpar_restricoes()
        for p in self.propostas.listar():
            if p.status in ("pendente", "aprovada"):
                p.status, p.token = "expirada", None
        self.propostas.salvar()
        return {
            "cluster": self.nome,
            "gpkg": str(caminho),
            "resumo": self.rede.resumo(),
            "religadores": {c: self._religador_de(self.rede, c) for c in self.rede.ctmts},
            "avisos": len(self.rede.avisos),
        }

    @ferramenta(
        "Topologia do cluster ou de um CTMT: resumo (nós, trechos, km, clientes, energizados, sem "
        "tensão), religador, chaves (estado, normal NF/NA, telecomando) e ties de interligação."
    )
    def get_topology(self, ctmt: str | None = None, com_chaves: bool = True) -> dict[str, Any]:
        rede = self._rede()
        if ctmt is not None and ctmt not in rede.ctmts:
            raise SessaoError(f"CTMT {ctmt!r} não está no cluster ({', '.join(rede.ctmts)})")
        ctmts = [ctmt] if ctmt else list(rede.ctmts)
        energizados = rede.energized_nodes()
        nos = [
            n
            for n, d in rede.grafo.nodes(data=True)
            if d.get("ctmt") in ctmts and d.get("tipo") == "pac"
        ]
        arestas = rede.grafo.edges
        trechos = [uv for uv in rede.trechos.values() if arestas[uv]["ctmt"] in ctmts]
        chaves = [
            self._dados_chave(rede, c)
            for c, uv in rede.chaves.items()
            if arestas[uv]["ctmt"] in ctmts
        ]
        ties = rede.tie_switches()
        ties = ties[ties["ctmt"].isin(ctmts) | ties["ctmt_viz"].isin(ctmts)]
        resumo = {
            "ctmt": ctmts,
            "fontes": {c: rede.fontes.get(c) for c in ctmts},
            "religadores": {c: self._religador_de(rede, c) for c in ctmts},
            "nos": len(nos),
            "trechos": len(trechos),
            "km": round(sum(arestas[uv]["comp"] for uv in trechos) / 1000, 3),
            "chaves": len(chaves),
            "chaves_NA": sum(1 for c in chaves if c["normal"] == "NA"),
            "ties": int(len(ties)),
            "clientes": rede.customers(nos).to_dict(),
            "energizados": sum(1 for n in nos if n in energizados),
            "sem_tensao": self._sem_tensao(rede),
            "falta": self.falta,
        }
        saida: dict[str, Any] = {"cluster": self.nome, "resumo": resumo}
        if com_chaves:
            saida["chaves"] = chaves
            saida["ties"] = ties.to_dict(orient="records")
        return saida

    @ferramenta(
        "Estado de uma chave (COD_ID da UNSEMT): aberta/fechada, normal NF/NA, telecomando, PACs "
        "e o CTMT que energiza cada lado."
    )
    def get_switch_state(self, chave: str) -> dict[str, Any]:
        return self._dados_chave(self._rede(), chave)

    @ferramenta(
        "SIMULADOR: injeta uma falta permanente no trecho SSDMT (COD_ID). O religador do CTMT "
        "(primeira chave entre a fonte e o trecho) abre e o trecho fica marcado em falta. Devolve "
        "religador, chaves com indicação de falta e clientes sem tensão."
    )
    def inject_fault(self, trecho: str) -> dict[str, Any]:
        rede = self._rede()
        if self.falta is not None:
            raise SessaoError(
                f"já há uma falta em {self.falta}; recarregue o cluster (load_cluster)"
            )
        if trecho not in rede.trechos:
            raise TrechoInexistenteError(trecho)
        u, v = rede.trechos[trecho]
        ctmt = rede.grafo.edges[u, v]["ctmt"]
        ponta = u if rede.energized_by(u) else v
        fonte = rede.energized_by(ponta)
        if fonte is None:
            raise SessaoError(f"o trecho {trecho} já está sem tensão; nada a simular")
        indicacoes = rede.chaves_no_caminho(ponta)
        if not indicacoes:
            raise SessaoError(f"não há chave entre a fonte {fonte} e o trecho {trecho}")
        religador = indicacoes[0]
        rede.open_switch(religador)
        self.falta, self.religador, self._indicacoes = trecho, religador, indicacoes
        self._scores = {}
        self.limpar_restricoes()
        return {
            "trecho": trecho,
            "ctmt": ctmt,
            "fonte": fonte,
            "religador": religador,
            "chaves_com_indicacao": indicacoes,
            "sem_tensao": self._sem_tensao(rede),
        }

    @ferramenta(
        "Localiza a falta simulada: zona entre chaves (nós, trechos, clientes), chaves com "
        "indicação de falta na ordem fonte→falta, chaves de fronteira a abrir."
    )
    def locate_fault(self) -> dict[str, Any]:
        rede, trecho = self._com_falta()
        iso = self._plano().isolate_segment(trecho)
        u, v = rede.trechos[trecho]
        trechos_zona = sorted(
            c for c, (a, b) in rede.trechos.items() if a in iso.zona and b in iso.zona
        )
        return {
            "trecho": trecho,
            "ctmt": rede.grafo.edges[u, v]["ctmt"],
            "religador": self.religador,
            "chaves_com_indicacao": list(self._indicacoes),
            "ultima_indicacao": self._indicacoes[-1] if self._indicacoes else None,
            "zona": {
                "nos": sorted(iso.zona),
                "trechos": trechos_zona,
                "clientes": iso.clientes_zona.to_dict(),
            },
            "chaves_fronteira": list(iso.chaves),
            "sem_tensao": self._sem_tensao(rede),
        }

    @ferramenta(
        "Plano de isolamento da falta (não executa): chaves a abrir, nós/clientes da zona isolada, "
        "nós sãos que ficam desligados (restauráveis), se o religador pode religar após isolar e "
        "a sequência de manobras."
    )
    def isolate_fault(self) -> dict[str, Any]:
        rede, trecho = self._com_falta()
        iso = self._plano().isolate_segment(trecho)
        religar = self._religar(iso)
        sequencia = self._sequencia(rede, iso, religar)
        reenergizados: dict[str, Any] | None = None
        if religar:
            depois = rede.copy()
            for passo in sequencia:
                if passo["acao"] == ABRIR:
                    depois.open_switch(passo["chave"])
                else:
                    depois.close_switch(passo["chave"])
            novos = depois.energized_nodes() - rede.energized_nodes()
            reenergizados = {"n_nos": len(novos), "clientes": rede.customers(novos).to_dict()}
        return {
            **iso.to_dict(),
            "religador": self.religador,
            "religar_apos_isolar": religar,
            "reenergizados_ao_religar": reenergizados,
            "sequencia": sequencia,
        }

    @ferramenta(
        "Clientes a jusante de um nó (PAC) ou de uma chave: nós que perdem tensão sem ele/ela, "
        "com UCBT, UCMT, trafos e kVA."
    )
    def downstream_customers(
        self, no: str | None = None, chave: str | None = None
    ) -> dict[str, Any]:
        rede = self._rede()
        if (no is None) == (chave is None):
            raise SessaoError("informe exatamente um de: no, chave")
        if chave is not None:
            nos = rede.downstream_switch(chave)
            referencia, tipo = chave, "chave"
        else:
            if no not in rede.grafo:
                raise SessaoError(f"nó {no!r} não existe no cluster")
            nos = rede.downstream(no)
            referencia, tipo = no, "no"
        return {
            "referencia": referencia,
            "tipo": tipo,
            "energizado_por": rede.energized_by(no) if no else None,
            "n_nos": len(nos),
            "clientes": rede.customers(nos).to_dict(),
        }

    @ferramenta(
        "Opções de restauração para a falta simulada: chaves NA que, fechadas após o isolamento, "
        "reenergizam os nós desligados — com fonte, clientes recuperados, manobras ordenadas e, "
        "com score=true (gêmeo OpenDSS), veredito elétrico (I do disjuntor × nominal em A, "
        "Vmin/Vmax MT em pu, sobrecargas, perdas em kW). Também devolve o impacto estimado da "
        "manobra em consumidor-minutos e, se a camada CONJ estiver no recorte, no DEC do "
        "conjunto, sempre sob a premissa explícita de tempo de reparo. Ordem: viáveis → maior "
        "margem → clientes."
    )
    def restore_options(
        self,
        score: bool = True,
        vmin: float = 0.93,
        vmax: float = 1.05,
        tempo_reparo: float = TEMPO_REPARO_PADRAO_MIN,
    ) -> dict[str, Any]:
        rede, trecho = self._com_falta()
        plano = self._plano()
        iso = plano.isolate_segment(trecho)
        opcoes = plano.restore_options(trecho)
        religar = self._religar(iso)
        saida: dict[str, Any] = {
            "trecho": trecho,
            "desligados": {
                "n_nos": len(iso.desligados),
                "clientes": iso.clientes_desligados.to_dict(),
            },
            "n_opcoes": len(opcoes),
            "score": None,
            "impacto": {
                "tempo_reparo_min": float(tempo_reparo),
                "tempo_manobra_min": 5.0,
                "premissa": premissa_impacto(float(tempo_reparo)),
            },
            "opcoes": [],
        }
        scores: dict[str, dict] = {}
        if opcoes and score:
            try:
                from bdgd_light.twin import score_eletrico

                master = self.master_base()
                inicio = perf_counter()
                avaliados = score_eletrico(opcoes, plano, master, vmin=vmin, vmax=vmax)
                contexto_score = {
                    "simulado_em": _iso(self._agora()),
                    "estado_rede": self._estado_rede_score(plano),
                }
                scores = {
                    s.chave: {
                        **{k: v for k, v in s.to_dict().items() if k not in ("chave", "opcao")},
                        **contexto_score,
                    }
                    for s in avaliados
                }
                self._scores = scores
                ordem = {s.chave: i for i, s in enumerate(avaliados)}
                opcoes.sort(key=lambda o: ordem.get(o.chave, len(ordem)))
                saida["score"] = {
                    "master": str(master),
                    "vmin": vmin,
                    "vmax": vmax,
                    "tempo_s": round(perf_counter() - inicio, 2),
                    "viaveis": sum(1 for s in avaliados if s.viavel),
                    **contexto_score,
                }
            except (ImportError, SessaoError, FileNotFoundError, RuntimeError) as exc:
                saida["aviso"] = f"sem score elétrico: {exc}"
        for pos, o in enumerate(opcoes):
            d = o.to_dict()
            d["n_nos"] = len(d.pop("nos"))
            d["manobras"] = self._sequencia(rede, iso, religar, fechar=o.chave)
            d["score"] = scores.get(o.chave)
            d["impacto"] = calcular_impacto_opcao(
                plano,
                o,
                isolamento=iso,
                tempo_reparo_min=tempo_reparo,
            ).to_dict()
            d["bloqueada"] = self.motivo_bloqueio_opcao(d)
            d["_ordem"] = pos
            saida["opcoes"].append(d)
        saida["opcoes"].sort(key=lambda o: (o.get("bloqueada") is not None, o.get("_ordem", 0)))
        for d in saida["opcoes"]:
            d.pop("_ordem", None)
        return saida

    @ferramenta(
        "Fluxo de potência no gêmeo OpenDSS do cluster: estado atual das chaves mais as manobras "
        "informadas ([{acao: abrir|fechar, chave}]) e, opcionalmente, um multiplicador de carga "
        "(loadmult, 1.0 = caso base; 1.3 = pico de +30 %). Devolve convergência, Vmin/Vmax (pu), "
        "violações, sobrecargas (%), perdas e potência (kW) e corrente (A) por fonte."
    )
    def run_powerflow(
        self,
        manobras: Sequence[Mapping[str, str]] = (),
        vmin: float = 0.93,
        vmax: float = 1.05,
        loadmult: float = 1.0,
    ) -> dict[str, Any]:
        rede = self._rede()
        try:
            from bdgd_light.twin import comandos_manobras, run_powerflow
        except ImportError as exc:
            raise SessaoError(f"{exc} — instale o extra: uv sync --extra twin") from exc
        if not 0 < float(loadmult) <= 5:
            raise SessaoError(f"loadmult fora da faixa (0, 5]: {loadmult}")
        passos = self._manobras_estado(rede) + [manobra(m["acao"], m["chave"]) for m in manobras]
        comandos = comandos_manobras(rede, passos)
        if float(loadmult) != 1.0:
            comandos = [*comandos, f"set loadmult={float(loadmult):g}"]
        r = run_powerflow(self.master_base(), vmin=vmin, vmax=vmax, comandos_extra=comandos)
        resumo = r.resumo()
        resumo["master"] = Path(resumo["master"]).name
        return {
            "manobras_aplicadas": passos,
            "loadmult": float(loadmult),
            "comandos_dss": comandos,
            **resumo,
            "piores_barras": r.piores_barras(5).to_dict(orient="records"),
            "sobrecargas": [
                {
                    **item,
                    "cod_id": self._cod_id_elemento_mt(item.get("elemento")),
                }
                for item in r.sobrecargas.head(5).to_dict(orient="records")
            ],
            "trechos_carregados_mt": self._trechos_carregados_mt(r.correntes),
            "fontes_a": {f.fonte: round(f.i_a, 1) for f in r.fontes.itertuples(index=False)},
        }

    @ferramenta(
        "Cria uma PROPOSTA de restauração a partir de uma opção (chave NA a fechar; sem chave, só "
        "isolar a falta e religar o tronco são): fica pendente de aprovação humana e devolve id e "
        "sequência de manobras. Quando houver opção, inclui o impacto estimado em "
        "consumidor-minutos e, se possível, no DEC do conjunto sob a premissa explícita de tempo "
        "de reparo. Sem aprovação nada é executado."
    )
    def propose_plan(
        self,
        chave: str | None = None,
        justificativa: str = "",
        tempo_reparo: float = TEMPO_REPARO_PADRAO_MIN,
    ) -> dict[str, Any]:
        rede, trecho = self._com_falta()
        plano = self._plano()
        iso = plano.isolate_segment(trecho)
        religar = self._religar(iso)
        u, v = rede.trechos[trecho]
        impacto = None
        if chave is None:
            fonte = rede.grafo.edges[u, v]["ctmt"]
            sequencia = self._sequencia(rede, iso, religar)
            if not sequencia:
                raise SessaoError("nada a manobrar: a falta já está isolada e o religador aberto")
            depois = rede.copy()
            for passo in sequencia:
                if passo["acao"] == ABRIR:
                    depois.open_switch(passo["chave"])
                else:
                    depois.close_switch(passo["chave"])
            clientes = rede.customers(depois.energized_nodes() - rede.energized_nodes())
        else:
            opcao = next((o for o in plano.restore_options(trecho) if o.chave == chave), None)
            if opcao is None:
                raise SessaoError(
                    f"a chave {chave} não restaura a falta em {trecho}; veja restore_options"
                )
            fonte, clientes = opcao.fonte, opcao.clientes
            sequencia = self._sequencia(rede, iso, religar, fechar=chave)
            impacto = calcular_impacto_opcao(
                plano,
                opcao,
                isolamento=iso,
                tempo_reparo_min=tempo_reparo,
            ).to_dict()
        p = self.propostas.criar(
            cluster=self.nome or "",
            falta=trecho,
            chave=chave,
            fonte=fonte,
            manobras=sequencia,
            clientes=clientes.to_dict(),
            score=None if chave is None else self._scores.get(chave),
            impacto=impacto,
            ja_satisfeitas=[c for c in iso.chaves if rede.is_open(c)],
            motivo=justificativa or None,
            replanejada_apos_rejeicao=self.ultima_rejeicao,
            restricoes_resumo=self.resumo_restricoes(),
        )
        return p.to_dict(com_token=False)

    @ferramenta(
        "Situação de uma proposta (pendente, aprovada, rejeitada, executada, expirada), próximo "
        "passo e, se aprovada por humano, o approval_token."
    )
    def get_proposal(self, proposta_id: str) -> dict[str, Any]:
        return self.propostas.obter(proposta_id).to_dict()

    @ferramenta(
        "EXECUTA uma manobra (estado: aberta|fechada) — só com approval_token de uma proposta "
        "aprovada por humano, e só o próximo passo da sequência dela. Sem token válido, recusa."
    )
    def set_switch(
        self, chave: str, estado: str, approval_token: str | None = None
    ) -> dict[str, Any]:
        rede = self._rede()
        if chave not in rede.chaves:
            raise ChaveInexistenteError(chave)
        acao = ESTADOS_CHAVE.get(str(estado).lower())
        if acao is None:
            raise SessaoError(f"estado {estado!r} inválido; use 'aberta' ou 'fechada'")
        p = self.propostas.por_token(approval_token)
        if p is None:
            raise RecusadoError(
                f"manobra {acao} {chave} recusada: sem token de aprovação válido "
                "(peça aprovação humana da proposta)"
            )
        if p.status != "aprovada":
            raise RecusadoError(f"manobra recusada: proposta {p.id} está {p.status}")
        if self.propostas.vencida(p):
            p.status, p.token = "expirada", None
            self.propostas.salvar()
            raise RecusadoError(
                f"manobra recusada: aprovação da proposta {p.id} venceu em {p.expira_em}"
            )
        passo = p.proximo_passo
        if passo is None or passo["chave"] != chave or passo["acao"] != acao:
            esperado = f"{passo['acao']} {passo['chave']}" if passo else "nenhum (concluída)"
            raise RecusadoError(
                f"manobra {acao} {chave} fora de sequência na proposta {p.id}: "
                f"próximo passo é {esperado}"
            )
        if acao == ABRIR:
            rede.open_switch(chave)
        else:
            rede.close_switch(chave)
        p.executadas += 1
        if p.proximo_passo is None:
            p.status, p.token = "executada", None
        self.propostas.salvar()
        return {
            "executado": True,
            "chave": chave,
            "estado": "aberta" if acao == ABRIR else "fechada",
            "proposta": p.id,
            "aprovada_por": p.aprovada_por,
            "aprovada_em": p.aprovada_em,
            "passo": p.executadas,
            "n_passos": len(p.manobras),
            "proposta_status": p.status,
            "sem_tensao": self._sem_tensao(rede),
        }

    # -- lado humano (não são ferramentas do modelo) -----------------------------------------

    def approve(
        self, proposta_id: str, *, operador: str = "operador", validade_s: int = VALIDADE_TOKEN_S
    ) -> dict[str, Any]:
        """Aprovação humana: emite o token que libera ``set_switch`` na sequência da proposta."""
        inicio = perf_counter()
        p = self.propostas.aprovar(proposta_id, operador=operador, validade_s=validade_s)
        self._auditar(
            "hitl.aprovacao",
            "approve",
            {"proposta_id": proposta_id, "operador": operador, "validade_s": validade_s},
            inicio,
            resultado=p.to_dict(),  # o token entra mascarado (sha256) pelo _auditar
        )
        return p.to_dict()

    def reject(
        self, proposta_id: str, *, operador: str = "operador", motivo: str = ""
    ) -> dict[str, Any]:
        """Rejeição humana: a proposta deixa de ser executável (token anulado)."""
        inicio = perf_counter()
        p = self.propostas.rejeitar(proposta_id, operador=operador, motivo=motivo)
        self._auditar(
            "hitl.rejeicao",
            "reject",
            {"proposta_id": proposta_id, "operador": operador, "motivo": motivo},
            inicio,
            resultado=p.to_dict(com_token=False),
        )
        return p.to_dict()

    def alternativas(self, proposta_id: str) -> list[dict[str, Any]]:
        """Opções de restauração da falta de uma proposta (topologia + último score elétrico),
        para o console mostrar o que o agente descartou. Leitura: não é ferramenta do modelo nem
        entra na auditoria; ``[]`` se a proposta já foi executada ou é de outra sessão."""
        p = self.propostas.obter(proposta_id)
        rede = self.rede
        if (
            rede is None
            or p.falta is None
            or p.falta != self.falta
            or p.cluster != self.nome
            or p.status == "executada"
        ):
            return []
        try:
            plano = self._plano()
            opcoes = plano.restore_options(p.falta)
            iso = plano.isolate_segment(p.falta)
            religar = self._religar(iso)
        except (KeyError, ValueError, TrechoInexistenteError):
            return []
        saida = []
        for o in opcoes:
            sc = self._scores.get(o.chave)
            impacto = None
            if p.impacto and isinstance(p.impacto, Mapping):
                impacto = calcular_impacto_opcao(
                    plano,
                    o,
                    isolamento=iso,
                    tempo_reparo_min=float(
                        p.impacto.get("tempo_reparo_min", TEMPO_REPARO_PADRAO_MIN)
                    ),
                ).to_dict()
            saida.append(
                {
                    "chave": o.chave,
                    "fonte": o.fonte,
                    "tlcd": o.tlcd,
                    "externa": o.externa,
                    "clientes": o.clientes.to_dict(),
                    "escolhida": o.chave == p.chave,
                    "score": sc,
                    "impacto": impacto,
                    "bloqueada": self.motivo_bloqueio_opcao(
                        {
                            "chave": o.chave,
                            "fonte": o.fonte,
                            "ctmt_chave": o.ctmt_chave,
                            "tlcd": o.tlcd,
                            "manobras": self._sequencia(rede, iso, religar, fechar=o.chave),
                            "score": sc,
                        }
                    ),
                }
            )
        # ordem do ranking elétrico quando existe (viáveis primeiro, a escolhida, maior margem),
        # senão a topológica
        if any(a["score"] for a in saida):
            saida.sort(
                key=lambda a: (
                    not (a["score"] or {}).get("viavel", False),
                    not a["escolhida"],
                    -((a["score"] or {}).get("margem_disjuntor") or -math.inf),
                )
            )
        return saida

    def estado(self) -> dict[str, Any]:
        """Foto da sessão (console/CLI): cluster, falta, religador, propostas, sem tensão e o
        ``hash`` da última entrada da auditoria (o console mostra "trilha íntegra")."""
        rede = self.rede
        audit = None if self.audit is None or self.audit.caminho is None else self.audit.caminho
        return {
            "cluster": self.nome,
            "cluster_demo": self.cluster_demo,
            "gpkg": None if self.gpkg is None else str(self.gpkg),
            "falta": self.falta,
            "religador": self.religador,
            "sem_tensao": None if rede is None else self._sem_tensao(rede),
            "propostas": [p.to_dict(com_token=False) for p in self.propostas.listar()],
            "restricoes": [r.to_dict() for r in self.restricoes],
            "restricoes_agregadas": self.restricoes_agregadas,
            "replanejamentos_evento": self.replanejamentos_evento,
            "limite_replanejamentos_evento": LIMITE_REPLANEJAMENTOS_EVENTO,
            "ultima_rejeicao": self.ultima_rejeicao,
            "audit": None if audit is None else str(audit),
            "audit_n": None if self.audit is None else len(self.audit),
            "hash": None if self.audit is None or not len(self.audit) else self.audit.ultimo_hash,
        }

    @property
    def cluster_demo(self) -> str | None:
        """Nome da demo (``tijuca``/``ipanema``/``taquara``) do cluster carregado, se for um."""
        if self.gpkg is None:
            return None
        return next((n for n, arq in CLUSTERS.items() if self.gpkg.name == arq), None)


def ferramentas_da_sessao() -> list[tuple[str, str]]:
    """``(nome, descrição)`` das ferramentas expostas ao modelo, na ordem de declaração."""
    return [
        (nome, metodo.descricao)
        for nome, metodo in vars(SessaoCOD).items()
        if getattr(metodo, "ferramenta", False)
    ]
