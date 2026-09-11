"""Simulador de eventos sobre um cluster: faltas (permanentes e transitórias), picos de carga e
chaves telecomandadas indisponíveis, reprodutíveis por semente, publicados numa fila JSONL.

Cada evento é uma mensagem ``{"tipo", "cluster", "trecho" | "ctmt" | "chave", "hora", "detalhes"}``
que o agente (#34) consome — ``falta_*`` vira ``inject_fault(trecho)`` no servidor MCP — e o console
(#35) mostra. Os cenários nomeados são os da ``docs/escopo-cidade.md`` (v3) e da regressão TQR.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bdgd_light.grid.rede import ChaveInexistenteError, Rede, TrechoInexistenteError

FALTA_PERMANENTE = "falta_permanente"
FALTA_TRANSITORIA = "falta_transitoria"
PICO_CARGA = "pico_carga"
CHAVE_INDISPONIVEL = "chave_indisponivel"
TIPOS = (FALTA_PERMANENTE, FALTA_TRANSITORIA, PICO_CARGA, CHAVE_INDISPONIVEL)
# apelidos aceitos na CLI (``--tipo falta``)
APELIDOS = {
    "falta": FALTA_PERMANENTE,
    "permanente": FALTA_PERMANENTE,
    "transitoria": FALTA_TRANSITORIA,
    "transitória": FALTA_TRANSITORIA,
    "pico": PICO_CARGA,
    "carga": PICO_CARGA,
    "chave": CHAVE_INDISPONIVEL,
    "indisponivel": CHAVE_INDISPONIVEL,
}
# pesos do sorteio de tipo no cenário ``aleatorio`` (faltas permanentes dominam a operação real)
PESOS_TIPO = {FALTA_PERMANENTE: 5, FALTA_TRANSITORIA: 3, PICO_CARGA: 2, CHAVE_INDISPONIVEL: 1}
MOTIVOS_INDISPONIVEL = ("falha de comunicação", "bateria do comando", "manutenção programada")
TEMPOS_MORTOS_S = (0.5, 1.0, 2.0, 5.0)
DURACOES_PICO_MIN = (30, 60, 120)
LOADMULT_MIN, LOADMULT_MAX = 1.15, 1.6
FILA_PADRAO = Path("data/eventos/eventos.jsonl")


def _agora() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def normalizar_tipo(tipo: str) -> str:
    """``falta`` → ``falta_permanente`` etc.; erro claro para tipo desconhecido."""
    t = tipo.strip().lower()
    t = APELIDOS.get(t, t)
    if t not in TIPOS:
        raise ValueError(
            f"tipo {tipo!r} inválido; use {', '.join(TIPOS)} (ou {', '.join(APELIDOS)})"
        )
    return t


@dataclass
class Evento:
    """Uma mensagem da fila. ``trecho``/``ctmt``/``chave`` conforme o tipo; ``detalhes`` é livre."""

    tipo: str
    cluster: str
    hora: str
    detalhes: dict[str, Any] = field(default_factory=dict)
    trecho: str | None = None
    ctmt: str | None = None
    chave: str | None = None
    cenario: str | None = None
    seed: int | None = None
    id: str | None = None  # atribuído pela fila ao publicar

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # chaves opcionais só entram quando fazem sentido para o tipo
        for k in ("trecho", "ctmt", "chave", "cenario", "seed", "id"):
            if d[k] is None:
                d.pop(k)
        return d

    @classmethod
    def de_dict(cls, d: Mapping[str, Any]) -> Evento:
        campos = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in campos})

    @property
    def alvo(self) -> str:
        return self.trecho or self.chave or self.ctmt or "—"


@dataclass(frozen=True)
class Cenario:
    """Cenário nomeado: cluster, tipo e alvo fixos (``aleatorio`` sorteia tudo)."""

    nome: str
    descricao: str
    cluster: str | None = None
    tipo: str | None = None
    trecho: str | None = None
    ctmt: str | None = None


CENARIOS: dict[str, Cenario] = {
    c.nome: c
    for c in (
        Cenario(
            "tijuca_cabofrio_tronco",
            "Falta permanente no tronco de ALC9925 LDA CABOFRIO (SE Aldeia Campista): isolar "
            "abrindo 10927447 e 11035901; 4.036 UCBT restauráveis por ALC9946, RCP9882 ou "
            "URG29983 — o gêmeo ranqueia as três SEs.",
            cluster="tijuca",
            tipo=FALTA_PERMANENTE,
            trecho="11304252",
            ctmt="ALC9925",
        ),
        Cenario(
            "ipanema_9210",
            "Falta permanente no tronco de PTS0001 LDS 9210, a 144 m da SE Posto Seis: as 35 NA "
            "são pátio de manobra da SE (EM_SUB) — nenhuma chave de campo restaura; o agente deve "
            "reconhecer a ausência de opção e recomendar despacho de equipe (cenário negativo).",
            cluster="ipanema",
            tipo=FALTA_PERMANENTE,
            trecho="11409068",
            ctmt="PTS0001",
        ),
        Cenario(
            "taquara_bocari",
            "Falta permanente em TQR33862 LDA BOCARI (cluster TQR, regressão): 4 chaves isolam, "
            "2.023 UCBT restauráveis por PARNAIBA (tie 1007642983) ou CURUMAU (tie 789941518).",
            cluster="taquara",
            tipo=FALTA_PERMANENTE,
            trecho="11798327",
            ctmt="TQR33862",
        ),
        Cenario(
            "aleatorio",
            "Tipo sorteado (falta permanente 5 : transitória 3 : pico de carga 2 : chave "
            "indisponível 1) e alvo sorteado no cluster carregado — trechos ponderados por km.",
        ),
    )
}


class Simulador:
    """Gera eventos reprodutíveis por ``seed`` sobre uma ``Rede`` (ou sem rede, só cenários
    nomeados sem enriquecimento). ``agora`` é injetável para testes."""

    def __init__(
        self,
        rede: Rede | None,
        cluster: str,
        *,
        seed: int | None = None,
        agora: Callable[[], datetime] = _agora,
    ):
        self.rede = rede
        self.cluster = cluster
        self.seed = seed
        self.rng = random.Random(seed)
        self._agora = agora

    # -- geração -------------------------------------------------------------------------------

    def gerar(
        self,
        tipo: str | None = None,
        *,
        trecho: str | None = None,
        ctmt: str | None = None,
        chave: str | None = None,
    ) -> Evento:
        """Um evento do ``tipo`` (sorteado se ``None``) sobre o alvo dado ou sorteado."""
        if tipo is None:
            tipo = self.rng.choices(list(PESOS_TIPO), weights=list(PESOS_TIPO.values()))[0]
        tipo = normalizar_tipo(tipo)
        if tipo == FALTA_PERMANENTE:
            return self.falta_permanente(trecho)
        if tipo == FALTA_TRANSITORIA:
            return self.falta_transitoria(trecho)
        if tipo == PICO_CARGA:
            return self.pico_carga(ctmt)
        return self.chave_indisponivel(chave)

    def cenario(self, nome: str) -> Evento:
        """Evento de um cenário nomeado (``CENARIOS``); com rede carregada, enriquece os detalhes
        e confere que o alvo existe nela."""
        try:
            c = CENARIOS[nome]
        except KeyError:
            raise ValueError(f"cenário {nome!r} desconhecido; use {', '.join(CENARIOS)}") from None
        if c.tipo is None:
            ev = self.gerar()
        else:
            if self.rede is not None and c.trecho and c.trecho not in self.rede.trechos:
                raise ValueError(
                    f"cenário {nome} é do cluster {c.cluster}: o trecho {c.trecho} não existe "
                    f"no cluster carregado ({self.cluster})"
                )
            ev = self.gerar(c.tipo, trecho=c.trecho, ctmt=c.ctmt)
            ev.ctmt = ev.ctmt or c.ctmt
            ev.detalhes.setdefault("ctmt", c.ctmt)
        ev.cenario = nome
        ev.detalhes["descricao"] = c.descricao
        return ev

    def falta_permanente(self, trecho: str | None = None) -> Evento:
        trecho = trecho or self._sortear_trecho()
        detalhes = self._detalhes_trecho(trecho)
        detalhes["acao_esperada"] = (
            "religador abre e não religa: localizar, isolar e restaurar (inject_fault no MCP)"
        )
        return self._evento(FALTA_PERMANENTE, detalhes, trecho=trecho, ctmt=detalhes.get("ctmt"))

    def falta_transitoria(self, trecho: str | None = None) -> Evento:
        trecho = trecho or self._sortear_trecho()
        detalhes = self._detalhes_trecho(trecho)
        detalhes["tempo_morto_s"] = self.rng.choice(TEMPOS_MORTOS_S)
        detalhes["religou"] = True
        detalhes["acao_esperada"] = "religador religou com sucesso: só registrar, sem manobra"
        return self._evento(FALTA_TRANSITORIA, detalhes, trecho=trecho, ctmt=detalhes.get("ctmt"))

    def pico_carga(self, ctmt: str | None = None) -> Evento:
        ctmt = ctmt or self._sortear_ctmt()
        if self.rede is not None and ctmt not in self.rede.ctmts:
            raise ValueError(f"alimentador {ctmt!r} não está no cluster {self.cluster}")
        detalhes = {
            "loadmult": round(self.rng.uniform(LOADMULT_MIN, LOADMULT_MAX), 2),
            "duracao_min": self.rng.choice(DURACOES_PICO_MIN),
            "acao_esperada": (
                "rodar o fluxo (run_powerflow) com loadmult e checar violações de "
                "tensão/carregamento"
            ),
        }
        if self.rede is not None:
            nos = [n for n, d in self.rede.grafo.nodes(data=True) if d.get("ctmt") == ctmt]
            detalhes["clientes"] = self.rede.customers(nos).to_dict()
        return self._evento(PICO_CARGA, detalhes, ctmt=ctmt)

    def chave_indisponivel(self, chave: str | None = None) -> Evento:
        chave = chave or self._sortear_chave_tlcd()
        detalhes: dict[str, Any] = {
            "motivo": self.rng.choice(MOTIVOS_INDISPONIVEL),
            "acao_esperada": "não contar com telecomando nessa chave; manobra só por equipe",
        }
        ctmt = None
        if self.rede is not None:
            if chave not in self.rede.chaves:
                raise ChaveInexistenteError(chave)
            uv = self.rede.chaves[chave]
            d = self.rede.grafo.edges[uv]
            ctmt = d.get("ctmt")
            detalhes |= {
                "normal": d.get("normal"),
                "estado": "aberta" if d.get("aberta") else "fechada",
                "tlcd": bool(d.get("tlcd")),
            }
            if not d.get("aberta"):
                # quem depende dessa chave para uma manobra remota (NF: tudo a jusante dela)
                nos = self.rede.downstream_switch(chave)
                detalhes["clientes_a_jusante"] = self.rede.customers(nos).to_dict()
        return self._evento(CHAVE_INDISPONIVEL, detalhes, chave=chave, ctmt=ctmt)

    # -- sorteios (determinísticos para a mesma semente) ------------------------------------------

    def _exigir_rede(self) -> Rede:
        if self.rede is None:
            raise ValueError("sem rede carregada só é possível gerar cenários nomeados")
        return self.rede

    def _sortear_trecho(self) -> str:
        """Trecho MT ponderado pelo comprimento (km); uniforme se todos tiverem 0."""
        rede = self._exigir_rede()
        cods = list(rede.trechos)
        if not cods:
            raise ValueError("cluster sem trechos SSDMT")
        pesos = [float(rede.grafo.edges[rede.trechos[c]].get("comp") or 0.0) for c in cods]
        if sum(pesos) <= 0:
            pesos = [1.0] * len(cods)
        return self.rng.choices(cods, weights=pesos)[0]

    def _sortear_ctmt(self) -> str:
        return self.rng.choice(sorted(self._exigir_rede().ctmts))

    def _sortear_chave_tlcd(self) -> str:
        rede = self._exigir_rede()
        tlcd = [c for c, uv in rede.chaves.items() if rede.grafo.edges[uv].get("tlcd")]
        if not tlcd:
            raise ValueError(f"cluster {self.cluster} não tem chave telecomandada")
        return self.rng.choice(tlcd)

    # -- detalhes ------------------------------------------------------------------------------

    def _detalhes_trecho(self, trecho: str) -> dict[str, Any]:
        rede = self.rede
        if rede is None:
            return {}
        if trecho not in rede.trechos:
            raise TrechoInexistenteError(trecho)
        u, v = rede.trechos[trecho]
        d = rede.grafo.edges[u, v]
        detalhes: dict[str, Any] = {
            "ctmt": d.get("ctmt"),
            "comp_m": round(float(d.get("comp") or 0.0), 1),
            "tip_cnd": d.get("tip_cnd") or None,
            "pac": [u, v],
        }
        caminho = rede.caminho_da_fonte(u) or rede.caminho_da_fonte(v)
        if caminho:
            chaves = rede.chaves_no_caminho(caminho[-1])
            detalhes["religador"] = chaves[0] if chaves else None
            detalhes["chaves_com_indicacao"] = chaves
            if chaves:
                nos = rede.downstream_switch(chaves[0])
                detalhes["sem_tensao_se_religador_abrir"] = {
                    "n_nos": len(nos),
                    "clientes": rede.customers(nos).to_dict(),
                }
        else:
            detalhes["religador"] = None
            detalhes["observacao"] = "trecho já sem tensão no estado atual"
        return detalhes

    def _evento(self, tipo: str, detalhes: dict[str, Any], **alvo: str | None) -> Evento:
        return Evento(
            tipo=tipo,
            cluster=self.cluster,
            hora=_iso(self._agora()),
            detalhes=detalhes,
            seed=self.seed,
            **alvo,
        )


class FilaEventos:
    """Fila mínima: JSON Lines só de acréscimo (um evento por linha, ``id`` sequencial E-0001…).

    O agente lê com ``listar(desde=n)`` guardando quantos já consumiu; o console mostra a cauda.
    """

    def __init__(self, caminho: Path | str = FILA_PADRAO):
        self.caminho = Path(caminho)

    def __len__(self) -> int:
        return len(self._linhas())

    def _linhas(self) -> list[str]:
        if not self.caminho.exists():
            return []
        return [ln for ln in self.caminho.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def listar(self, desde: int = 0) -> list[Evento]:
        """Eventos a partir da posição ``desde`` (0 = todos), na ordem de publicação."""
        return [Evento.de_dict(json.loads(ln)) for ln in self._linhas()[desde:]]

    def ultimo(self) -> Evento | None:
        linhas = self._linhas()
        return Evento.de_dict(json.loads(linhas[-1])) if linhas else None

    def publicar(self, evento: Evento) -> Evento:
        """Atribui o ``id`` e anexa o evento ao arquivo (cria a pasta se preciso)."""
        evento.id = f"E-{len(self) + 1:04d}"
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with self.caminho.open("a", encoding="utf-8") as f:
            f.write(json.dumps(evento.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return evento
