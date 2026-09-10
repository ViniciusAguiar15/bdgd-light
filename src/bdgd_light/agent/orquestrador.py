"""Orquestrador + verificador HITL sobre as ferramentas do COD (issue #34, padrão PowerChain).

**Orquestrador**: recebe um evento da fila do simulador (``bdgd_light.sim``) ou uma pergunta em
linguagem natural, monta o prompt (papel, regras, os top-K exemplos anotados de
``docs/agent/exemplos.yaml``) e os descritores das ferramentas, chama o ``LLMClient`` e executa as
ferramentas pedidas sobre uma ``SessaoCOD`` em processo. Nível 2 de autonomia: o agente só
**propõe** — ``set_switch`` não é exposto ao modelo; ``propose_plan`` cria uma proposta pendente
de aprovação humana (CLI ``aprovar`` ou console).

**Verificador**: porta determinística na frente de ``propose_plan`` — chaves existem, sequência
abre antes de fechar, fronteira da falta coberta, opção consta de ``restore_options``, veredito
elétrico do gêmeo (convergência, 0,93–1,05 pu MT, corrente do disjuntor ≤ nominal, sem sobrecarga
MT) e chaves indisponíveis. Proposta recusada volta ao modelo como erro de ferramenta para ele
replanejar; ``max_rodadas`` e ``replanejamentos`` limitam o laço.
"""

from __future__ import annotations

import inspect
import json
import math
import re
import time
import types
import typing
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bdgd_light.agent.audit import AuditLog
from bdgd_light.agent.llm import (
    Conversa,
    FakeLLMClient,
    Ferramenta,
    LLMClient,
    LLMError,
    Message,
    Resposta,
    Text,
    ToolCall,
    ToolCalls,
    ToolSpec,
    Uso,
    conversar,
)
from bdgd_light.mcp_server.sessao import SessaoCOD, SessaoError, resolver_cluster
from bdgd_light.sim.eventos import (
    CHAVE_INDISPONIVEL,
    FALTA_PERMANENTE,
    FALTA_TRANSITORIA,
    PICO_CARGA,
    Evento,
)

EXEMPLOS_PADRAO = Path(__file__).resolve().parents[3] / "docs" / "agent" / "exemplos.yaml"
"""Pares tarefa → sequência de ferramentas anotados (repositório); sem o arquivo, zero-shot."""

FERRAMENTAS_MODELO: tuple[str, ...] = (
    "get_topology",
    "get_switch_state",
    "inject_fault",
    "locate_fault",
    "isolate_fault",
    "downstream_customers",
    "restore_options",
    "run_powerflow",
    "propose_plan",
    "get_proposal",
)
"""Ferramentas da sessão expostas ao modelo. ``set_switch`` (executa) e ``load_cluster`` (o
orquestrador carrega o cluster do evento) ficam de fora por desenho."""

DESCRICAO_PARAMETROS: dict[str, str] = {
    "cluster": "nome do cluster da demo (tijuca, ipanema, taquara) ou caminho de um GeoPackage",
    "ctmt": "código do alimentador (CTMT); vazio = cluster inteiro",
    "com_chaves": "incluir a lista de chaves e ties",
    "chave": "COD_ID da chave",
    "trecho": "COD_ID do trecho SSDMT",
    "no": "identificador do nó (PAC)",
    "score": "true = veredito elétrico no gêmeo OpenDSS (recomendado)",
    "vmin": "limite inferior de tensão MT em pu (padrão 0,93)",
    "vmax": "limite superior de tensão MT em pu (padrão 1,05)",
    "manobras": "manobras adicionais ao estado atual, na ordem",
    "loadmult": "multiplicador de carga (1,0 = caso base; 1,3 = pico de +30 %)",
    "justificativa": "por que esta opção (margem, tensão, clientes, alternativas descartadas)",
    "proposta_id": "id da proposta (P-0001…)",
}

VMIN_PADRAO, VMAX_PADRAO = 0.93, 1.05
TOLERANCIA_MARGEM = 0.02
"""Diferença de margem no disjuntor (2 pontos percentuais) abaixo da qual duas opções empatam."""

# ---------------------------------------------------------------------------------------------
# Descritores das ferramentas (ToolSpec a partir da assinatura da sessão)
# ---------------------------------------------------------------------------------------------


def _esquema_tipo(anotacao: Any, nome: str) -> dict[str, Any]:
    origem = typing.get_origin(anotacao)
    if origem in (typing.Union, types.UnionType):
        internos = [a for a in typing.get_args(anotacao) if a is not type(None)]
        return _esquema_tipo(internos[0] if len(internos) == 1 else str, nome)
    if anotacao is bool:
        return {"type": "boolean"}
    if anotacao is int:
        return {"type": "integer"}
    if anotacao is float:
        return {"type": "number"}
    if nome == "manobras":
        return {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "acao": {"type": "string", "enum": ["abrir", "fechar"]},
                    "chave": {"type": "string"},
                },
                "required": ["acao", "chave"],
            },
        }
    if origem in (list, tuple, Sequence) or anotacao in (list, tuple):
        return {"type": "array", "items": {"type": "string"}}
    return {"type": "string"}


def especificacao(nome: str, metodo: Callable) -> ToolSpec:
    """``ToolSpec`` (JSON Schema dos argumentos) de um método-ferramenta da ``SessaoCOD``."""
    original = inspect.unwrap(metodo)
    dicas = typing.get_type_hints(original)
    propriedades: dict[str, Any] = {}
    obrigatorios: list[str] = []
    for p in list(inspect.signature(original).parameters.values())[1:]:  # sem self
        esquema = _esquema_tipo(dicas.get(p.name, str), p.name)
        descricao = DESCRICAO_PARAMETROS.get(p.name)
        if p.default is inspect.Parameter.empty:
            obrigatorios.append(p.name)
        elif p.default is not None and p.default != ():
            descricao = f"{descricao or p.name} (padrão {p.default})"
        if descricao:
            esquema["description"] = descricao
        propriedades[p.name] = esquema
    parametros: dict[str, Any] = {"type": "object", "properties": propriedades}
    if obrigatorios:
        parametros["required"] = obrigatorios
    return ToolSpec(nome, getattr(metodo, "descricao", "") or "", parametros)


def especificacoes(nomes: Sequence[str] = FERRAMENTAS_MODELO) -> list[ToolSpec]:
    """Descritores das ferramentas expostas ao modelo (sem precisar do SDK MCP)."""
    return [especificacao(n, getattr(SessaoCOD, n)) for n in nomes]


# ---------------------------------------------------------------------------------------------
# Exemplos anotados (docs/agent/exemplos.yaml)
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Exemplo:
    """Par anotado: tarefa → sequência de ferramentas + justificativa (seleção por afinidade)."""

    id: str
    tarefa: str
    ferramentas: tuple[str, ...]
    justificativa: str
    tags: tuple[str, ...] = ()

    def texto(self) -> str:
        return (
            f"- [{self.id}] Tarefa: {self.tarefa}\n"
            f"  Ferramentas: {' → '.join(self.ferramentas) or '(nenhuma)'}\n"
            f"  Justificativa: {self.justificativa}"
        )

    def palavras(self) -> set[str]:
        return _palavras(
            f"{self.tarefa} {self.justificativa} {' '.join(self.tags)} {' '.join(self.ferramentas)}"
        )


def carregar_exemplos(caminho: Path | str | None = EXEMPLOS_PADRAO) -> list[Exemplo]:
    """Lê o YAML de exemplos (lista de ``{id, tarefa, ferramentas, justificativa, tags}``); sem
    caminho ou arquivo inexistente devolve lista vazia (o agente roda zero-shot)."""
    if caminho is None:
        return []
    caminho = Path(caminho)
    if not caminho.is_file():
        return []
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - extra agent traz o pyyaml
        raise LLMError(f"{exc} — instale o extra: uv sync --extra agent") from exc
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or []
    if isinstance(dados, Mapping):
        dados = dados.get("exemplos", [])
    if not isinstance(dados, list):
        raise ValueError(f"{caminho}: esperava uma lista de exemplos (ou {{exemplos: [...]}})")
    exemplos = []
    for i, d in enumerate(dados):
        if not isinstance(d, Mapping) or not d.get("tarefa"):
            raise ValueError(f"{caminho}: exemplo {i + 1} sem 'tarefa'")
        exemplos.append(
            Exemplo(
                id=str(d.get("id") or f"exemplo_{i + 1}"),
                tarefa=str(d.get("tarefa", "")).strip(),
                ferramentas=tuple(str(f) for f in d.get("ferramentas", []) or []),
                justificativa=str(d.get("justificativa", "")).strip(),
                tags=tuple(str(t) for t in d.get("tags", []) or []),
            )
        )
    return exemplos


def _palavras(texto: str) -> set[str]:
    return {p for p in re.findall(r"[a-zà-ú0-9_]+", texto.lower()) if len(p) > 2}


def selecionar_exemplos(
    exemplos: Sequence[Exemplo], consulta: str, k: int = 3, *, tipo: str | None = None
) -> list[Exemplo]:
    """Top-K por afinidade com a consulta (evento ou pergunta).

    Pontuação: ``tipo`` do evento presente nas tags do exemplo vale 10 (categoria domina); cada
    palavra da consulta presente nas tags vale 2 e na tarefa/justificativa/ferramentas vale 1,
    normalizada pelo tamanho do exemplo para não favorecer textos longos. Empate: ordem do arquivo.
    """
    if k <= 0 or not exemplos:
        return []
    alvo = _palavras(consulta)
    pontuados = []
    for i, e in enumerate(exemplos):
        tags = _palavras(" ".join(e.tags))
        base = e.palavras() - tags
        pontuacao = 2 * len(alvo & tags) + len(alvo & base) / (1 + math.log(len(base) or 1))
        if tipo and tipo.lower() in tags:
            pontuacao += 10
        pontuados.append((-pontuacao, i, e))
    pontuados.sort()
    return [e for _, _, e in pontuados[:k]]


# ---------------------------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------------------------

PROMPT_SISTEMA = """\
Você é o assistente de operação do Centro de Operação da Distribuição (COD) da Light, no nível 2 de
autonomia: você ANALISA e PROPÕE; quem executa é o operador humano. Você trabalha sobre um cluster
de alimentadores de média tensão (grafo da BDGD + gêmeo digital OpenDSS) por meio de ferramentas.

Regras:
1. Nunca execute manobras. Você não tem a ferramenta set_switch; toda manobra vira uma PROPOSTA
   (propose_plan) que fica pendente de aprovação humana. Uma execução termina com no máximo uma
   proposta.
2. Falta permanente (o simulador já registrou a falta na sessão — não chame inject_fault):
   locate_fault → isolate_fault → restore_options com score=true (veredito elétrico do gêmeo) →
   propose_plan com a melhor opção VIÁVEL (viavel=true; entre as viáveis, maior margem no
   disjuntor e mais clientes). Se não houver opção ou nenhuma for viável, chame propose_plan()
   sem chave (isolar a falta e religar o tronco são) e recomende despacho de equipe.
3. Só proponha chaves que apareçam em restore_options; nunca feche uma NA antes de abrir as chaves
   de fronteira; não conte com chaves informadas como indisponíveis.
4. Falta transitória (o religador religou): não há manobra — registre e explique. Pico de carga:
   run_powerflow com o loadmult do evento e relate violações e sobrecargas. Chave indisponível:
   registre a restrição, sem manobra.
5. Se o verificador recusar sua proposta (erro da ferramenta com "problemas"), leia os problemas e
   escolha outra opção, ou proponha só o isolamento.
6. Termine com um resumo em português para o operador: falta (trecho, CTMT, religador), clientes
   sem tensão, isolamento (chaves a abrir), opção escolhida e por quê (margem em %, tensão em pu),
   alternativas descartadas e por quê, e o que ele deve aprovar (id da proposta). Objetivo, com
   unidades (A, pu, kW, clientes); sem inventar números que não vieram das ferramentas.
"""


def montar_prompt_sistema(exemplos: Sequence[Exemplo] = ()) -> str:
    if not exemplos:
        return PROMPT_SISTEMA
    corpo = "\n".join(e.texto() for e in exemplos)
    return f"{PROMPT_SISTEMA}\nExemplos anotados (tarefa → ferramentas → justificativa):\n{corpo}\n"


# ---------------------------------------------------------------------------------------------
# Verificador
# ---------------------------------------------------------------------------------------------


@dataclass
class Veredito:
    """Resultado do verificador: ``ok`` só se nenhuma checagem falhou; ``avisos`` não bloqueiam."""

    ok: bool
    checagens: dict[str, bool] = field(default_factory=dict)
    problemas: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    eletrico: bool = False
    """Houve veredito elétrico do gêmeo (score) na checagem."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "eletrico": self.eletrico,
            "checagens": dict(self.checagens),
            "problemas": list(self.problemas),
            "avisos": list(self.avisos),
        }


def _numero(valor: Any) -> float | None:
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


class Verificador:
    """Checagens determinísticas de um plano de restauração antes de virar proposta."""

    def __init__(
        self,
        *,
        vmin: float = VMIN_PADRAO,
        vmax: float = VMAX_PADRAO,
        exigir_score: bool = True,
        indisponiveis: set[str] | None = None,
    ):
        self.vmin, self.vmax = vmin, vmax
        self.exigir_score = exigir_score
        self.indisponiveis: set[str] = set(indisponiveis or ())

    def verificar(
        self,
        sessao: SessaoCOD,
        chave: str | None,
        *,
        opcoes: Sequence[Mapping[str, Any]] | None = None,
        isolamento: Mapping[str, Any] | None = None,
    ) -> Veredito:
        """Verifica a proposta ``chave`` (NA a fechar; ``None`` = só isolar). ``opcoes`` e
        ``isolamento`` são os resultados de ``restore_options``/``isolate_fault`` já obtidos na
        conversa; sem eles, o verificador chama a sessão (fica na auditoria)."""
        v = Veredito(ok=True)

        def falha(nome: str, mensagem: str) -> None:
            v.checagens[nome] = False
            v.problemas.append(mensagem)
            v.ok = False

        def passa(nome: str) -> None:
            v.checagens.setdefault(nome, True)

        if sessao.rede is None or sessao.falta is None:
            falha("falta_registrada", "não há falta registrada na sessão; nada a propor")
            return v
        passa("falta_registrada")
        rede = sessao.rede
        if isolamento is None:
            isolamento = sessao.isolate_fault()
        if opcoes is None:
            opcoes = sessao.restore_options(score=self.exigir_score)["opcoes"]
        por_chave = {o["chave"]: o for o in opcoes}

        opcao: Mapping[str, Any] | None = None
        if chave is None:
            sequencia = list(isolamento.get("sequencia") or [])
            viaveis = [o for o in opcoes if _viavel(o)]
            if viaveis:
                v.avisos.append(
                    "há opção viável não usada: "
                    + ", ".join(f"{o['chave']} → {o.get('fonte')}" for o in viaveis[:3])
                )
        else:
            opcao = por_chave.get(chave)
            if opcao is None:
                falha(
                    "opcao_em_restore_options",
                    f"a chave {chave} não está entre as opções de restore_options "
                    f"({', '.join(por_chave) or 'nenhuma opção'})",
                )
                return v
            passa("opcao_em_restore_options")
            sequencia = list(opcao.get("manobras") or [])

        chaves_seq = [m.get("chave") for m in sequencia]
        inexistentes = [c for c in chaves_seq if c not in rede.chaves]
        if inexistentes:
            falha(
                "chaves_existem", f"chave(s) inexistente(s) no cluster: {', '.join(inexistentes)}"
            )
        else:
            passa("chaves_existem")
        usadas_indisponiveis = sorted(set(chaves_seq) & self.indisponiveis)
        if usadas_indisponiveis:
            falha(
                "chaves_disponiveis",
                f"a sequência usa chave(s) indisponível(is): {', '.join(usadas_indisponiveis)}",
            )
        else:
            passa("chaves_disponiveis")
        acoes = [m.get("acao") for m in sequencia]
        fechamentos = [i for i, a in enumerate(acoes) if a == "fechar"]
        aberturas = [i for i, a in enumerate(acoes) if a == "abrir"]
        if fechamentos and aberturas and min(fechamentos) < max(aberturas):
            falha("abre_antes_de_fechar", "há fechamento antes de uma abertura na sequência")
        else:
            passa("abre_antes_de_fechar")
        fronteira = set(isolamento.get("chaves") or [])
        abertas = {m.get("chave") for m in sequencia if m.get("acao") == "abrir"}
        faltando = sorted(c for c in fronteira if c not in abertas and not rede.is_open(c))
        if faltando:
            falha(
                "fronteira_isolada",
                f"a sequência não abre toda a fronteira da falta: falta(m) {', '.join(faltando)}",
            )
        else:
            passa("fronteira_isolada")

        if opcao is not None:
            self._checar_eletrico(v, opcao, opcoes, falha, passa)
        return v

    def _checar_eletrico(self, v: Veredito, opcao, opcoes, falha, passa) -> None:
        score = opcao.get("score")
        if not score:
            if self.exigir_score:
                falha(
                    "score_eletrico",
                    "sem veredito elétrico para esta opção: chame restore_options com score=true",
                )
            else:
                v.avisos.append("sem verificação elétrica (score desativado ou gêmeo indisponível)")
            return
        v.eletrico = True
        if score.get("convergiu") is False:
            falha("convergiu", "o fluxo de potência da opção não convergiu")
        else:
            passa("convergiu")
        vmin_pu, vmax_pu = _numero(score.get("vmin_mt_pu")), _numero(score.get("vmax_mt_pu"))
        if vmin_pu is None:
            v.avisos.append("tensão MT mínima não informada pelo gêmeo")
        elif vmin_pu < self.vmin or (vmax_pu is not None and vmax_pu > self.vmax):
            falha(
                "tensao_mt",
                f"tensão MT fora de [{self.vmin}, {self.vmax}] pu: "
                f"mín {vmin_pu:.3f}" + (f", máx {vmax_pu:.3f}" if vmax_pu is not None else ""),
            )
        else:
            passa("tensao_mt")
        margem = _numero(score.get("margem_disjuntor"))
        if margem is None:
            v.avisos.append("sem referência de corrente nominal do disjuntor da fonte receptora")
        elif margem < 0:
            falha(
                "corrente_disjuntor",
                f"corrente no disjuntor acima da nominal: {score.get('i_disjuntor_a')} A > "
                f"{score.get('i_nominal_a')} A (margem {margem:.0%})",
            )
        else:
            passa("corrente_disjuntor")
        sobrecargas = list(score.get("sobrecargas_mt") or [])
        if sobrecargas:
            falha(
                "sem_sobrecarga_mt",
                f"elemento(s) MT acima de 100 %: {', '.join(map(str, sobrecargas[:5]))}",
            )
        else:
            passa("sem_sobrecarga_mt")
        if not score.get("viavel", True):
            motivos = "; ".join(map(str, score.get("motivos") or [])) or "sem motivo informado"
            falha("viavel", f"o gêmeo considera a opção inviável: {motivos}")
        else:
            passa("viavel")
        melhores = [
            o
            for o in opcoes
            if _viavel(o)
            and (_numero((o.get("score") or {}).get("margem_disjuntor")) or -1)
            > (margem if margem is not None else -1) + TOLERANCIA_MARGEM
        ]
        if v.ok and melhores:
            o = melhores[0]
            v.avisos.append(
                f"há opção viável com margem maior: {o['chave']} → {o.get('fonte')} "
                f"({_numero(o['score'].get('margem_disjuntor')):.0%})"
            )


def _viavel(opcao: Mapping[str, Any]) -> bool:
    score = opcao.get("score")
    return bool(score) and bool(score.get("viavel"))


# ---------------------------------------------------------------------------------------------
# Orquestrador
# ---------------------------------------------------------------------------------------------


@dataclass
class Execucao:
    """Métricas e resultado de uma execução do agente (uma por evento/pergunta)."""

    tipo: str
    cluster: str | None
    evento: dict[str, Any] | None
    pergunta: str | None
    provider: str | None
    modelo: str | None
    rodadas: int = 0
    replanejamentos: int = 0
    ferramentas: list[dict[str, Any]] = field(default_factory=list)
    recusas: list[dict[str, Any]] = field(default_factory=list)
    proposta: dict[str, Any] | None = None
    veredito: dict[str, Any] | None = None
    resposta: str = ""
    uso: dict[str, Any] | None = None
    segundos_llm: float = 0.0
    segundos_total: float = 0.0
    hash_auditoria: str | None = None
    exemplos: list[str] = field(default_factory=list)
    erro: str | None = None
    inicio: str = ""

    @property
    def n_ferramentas(self) -> int:
        return len(self.ferramentas)

    @property
    def sequencia(self) -> list[str]:
        return [f["ferramenta"] for f in self.ferramentas]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tipo": self.tipo,
            "cluster": self.cluster,
            "evento": self.evento,
            "pergunta": self.pergunta,
            "provider": self.provider,
            "modelo": self.modelo,
            "inicio": self.inicio,
            "rodadas": self.rodadas,
            "replanejamentos": self.replanejamentos,
            "n_ferramentas": self.n_ferramentas,
            "ferramentas": list(self.ferramentas),
            "sequencia": self.sequencia,
            "recusas_verificador": list(self.recusas),
            "proposta": self.proposta,
            "veredito": self.veredito,
            "resposta": self.resposta,
            "uso": self.uso,
            "segundos_llm": round(self.segundos_llm, 3),
            "segundos_total": round(self.segundos_total, 3),
            "hash_auditoria": self.hash_auditoria,
            "exemplos": list(self.exemplos),
            "erro": self.erro,
        }


def _resumir(valor: Any, limite: int = 200) -> str:
    texto = json.dumps(valor, ensure_ascii=False, default=str)
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


class Orquestrador:
    """Laço evento/pergunta → prompt → ferramentas (com o verificador em ``propose_plan``) →
    proposta pendente + resumo. Reutiliza a ``SessaoCOD`` (e o ``AuditLog`` dela)."""

    def __init__(
        self,
        sessao: SessaoCOD,
        cliente: LLMClient,
        *,
        exemplos: Sequence[Exemplo] | None = None,
        top_k: int = 3,
        max_rodadas: int = 8,
        replanejamentos: int = 2,
        vmin: float = VMIN_PADRAO,
        vmax: float = VMAX_PADRAO,
        exigir_score: bool = True,
        audit: AuditLog | None = None,
        provider: str | None = None,
        ferramentas: Sequence[str] = FERRAMENTAS_MODELO,
    ):
        self.sessao = sessao
        self.cliente = cliente
        self.exemplos = list(carregar_exemplos() if exemplos is None else exemplos)
        self.top_k = top_k
        self.max_rodadas = max_rodadas
        self.replanejamentos = replanejamentos
        self.exigir_score = exigir_score
        self.audit = sessao.audit if audit is None else audit
        self.provider = provider
        self.nomes_ferramentas = tuple(n for n in ferramentas if n != "set_switch")
        self.verificador = Verificador(vmin=vmin, vmax=vmax, exigir_score=exigir_score)
        self._chamadas: list[dict[str, Any]] = []
        self._recusas: list[dict[str, Any]] = []
        self._opcoes: list[dict[str, Any]] | None = None
        self._isolamento: dict[str, Any] | None = None
        self._proposta: dict[str, Any] | None = None
        self._veredito: Veredito | None = None

    # -- entrada -------------------------------------------------------------------------------

    @property
    def indisponiveis(self) -> set[str]:
        """Chaves sem telecomando (eventos ``chave_indisponivel``); o verificador as bloqueia."""
        return self.verificador.indisponiveis

    def executar_evento(self, evento: Evento | Mapping[str, Any]) -> Execucao:
        """Trata um evento da fila: carrega o cluster, registra a falta (se permanente) e conduz o
        modelo até a proposta (falta permanente) ou até o registro (demais tipos)."""
        ev = evento if isinstance(evento, Evento) else Evento.de_dict(evento)
        contexto = self._preparar(ev)
        if ev.tipo == CHAVE_INDISPONIVEL and ev.chave:
            self.indisponiveis.add(ev.chave)
        mensagem = self._mensagem_evento(ev, contexto)
        consulta = (
            f"{ev.tipo} {ev.detalhes.get('descricao', '')} {ev.detalhes.get('acao_esperada', '')}"
        )
        return self._rodar(
            mensagem,
            consulta=consulta,
            exigir_proposta=ev.tipo == FALTA_PERMANENTE,
            tipo="evento",
            evento=ev.to_dict(),
        )

    def responder(self, pergunta: str, cluster: str | None = None) -> Execucao:
        """Pergunta em linguagem natural sobre o cluster carregado (ou ``cluster``)."""
        if cluster is not None:
            self._carregar(cluster)
        if self.sessao.rede is None:
            raise SessaoError("nenhum cluster carregado; informe cluster=")
        mensagem = f"PERGUNTA: {pergunta}\n{self._situacao()}"
        return self._rodar(
            mensagem, consulta=pergunta, exigir_proposta=False, tipo="pergunta", pergunta=pergunta
        )

    # -- preparação ----------------------------------------------------------------------------

    def _carregar(self, cluster: str) -> None:
        alvo = resolver_cluster(cluster, self.sessao.feeders)
        if self.sessao.gpkg is None or Path(self.sessao.gpkg).resolve() != alvo.resolve():
            self.sessao.load_cluster(str(alvo))

    def _preparar(self, ev: Evento) -> dict[str, Any]:
        self._carregar(ev.cluster)
        contexto: dict[str, Any] = {}
        if ev.tipo == FALTA_PERMANENTE:
            if not ev.trecho:
                raise SessaoError("evento de falta permanente sem trecho")
            if self.sessao.falta != ev.trecho:
                if self.sessao.falta is not None:
                    self.sessao.load_cluster(str(self.sessao.gpkg))
                contexto["inject_fault"] = self.sessao.inject_fault(ev.trecho)
        return contexto

    def _situacao(self) -> str:
        s = self.sessao
        rede = s.rede
        partes = [f'SITUAÇÃO DA SESSÃO: cluster "{s.nome}" carregado']
        if rede is not None:
            partes[0] += f" ({len(rede.ctmts)} CTMT: {', '.join(sorted(rede.ctmts))})"
        if s.falta is not None and rede is not None:
            sem = s.estado().get("sem_tensao") or {}
            clientes = sem.get("clientes", {})
            partes.append(
                f"Falta registrada pelo simulador no trecho {s.falta}: religador {s.religador} "
                f"aberto; {clientes.get('ucbt', 0)} UCBT / {clientes.get('ucmt', 0)} UCMT "
                f"({clientes.get('total', 0)} clientes) sem tensão."
            )
        else:
            partes.append("Sem falta registrada.")
        partes.append(
            "Chaves indisponíveis (telecomando fora): "
            + (", ".join(sorted(self.indisponiveis)) or "nenhuma")
            + "."
        )
        return "\n".join(partes)

    def _mensagem_evento(self, ev: Evento, contexto: Mapping[str, Any]) -> str:
        tarefa = {
            FALTA_PERMANENTE: (
                "TAREFA: localizar, isolar e avaliar a restauração; terminar com propose_plan "
                "(a melhor opção viável, ou sem chave se não houver) e o resumo para o operador."
            ),
            FALTA_TRANSITORIA: (
                "TAREFA: registrar a ocorrência (o religador religou) e explicar por que não há "
                "manobra; se útil, informe a zona afetada."
            ),
            PICO_CARGA: (
                "TAREFA: rodar run_powerflow com o loadmult do evento e relatar tensões, violações "
                "e sobrecargas; sem proposta de manobra."
            ),
            CHAVE_INDISPONIVEL: (
                "TAREFA: registrar a restrição operacional (a chave não deve entrar em planos) e "
                "dizer o que muda para a operação; sem manobra."
            ),
        }.get(ev.tipo, "TAREFA: analisar o evento e responder ao operador.")
        return (
            f"EVENTO {json.dumps(ev.to_dict(), ensure_ascii=False)}\n{self._situacao()}\n{tarefa}"
        )

    # -- ferramentas ---------------------------------------------------------------------------

    def _ferramentas(self) -> list[Ferramenta]:
        saida = []
        for spec in especificacoes(self.nomes_ferramentas):
            saida.append(Ferramenta(spec, self._envolver(spec.name)))
        return saida

    def _envolver(self, nome: str) -> Callable[..., Any]:
        metodo = getattr(self.sessao, nome)

        def executar(**argumentos: Any) -> Any:
            if nome == "propose_plan":
                return self._propor(**argumentos)
            if nome == "restore_options" and not self.exigir_score:
                argumentos["score"] = False
            inicio = time.perf_counter()
            try:
                resultado = metodo(**argumentos)
            except Exception as exc:
                self._chamadas.append(
                    {
                        "ferramenta": nome,
                        "argumentos": argumentos,
                        "ok": False,
                        "erro": str(exc),
                        "segundos": round(time.perf_counter() - inicio, 3),
                    }
                )
                raise
            self._chamadas.append(
                {
                    "ferramenta": nome,
                    "argumentos": argumentos,
                    "ok": True,
                    "resumo": _resumir(resultado),
                    "segundos": round(time.perf_counter() - inicio, 3),
                }
            )
            if nome == "restore_options":
                self._opcoes = list(resultado.get("opcoes") or [])
            elif nome == "isolate_fault":
                self._isolamento = dict(resultado)
            elif nome == "inject_fault":
                self._opcoes = self._isolamento = None
            return resultado

        executar.__name__ = nome
        return executar

    def _propor(self, chave: str | None = None, justificativa: str = "") -> dict[str, Any]:
        argumentos = {"chave": chave, "justificativa": justificativa}
        inicio = time.perf_counter()

        def registrar(**campos: Any) -> None:
            self._chamadas.append(
                {
                    "ferramenta": "propose_plan",
                    "argumentos": argumentos,
                    **campos,
                    "segundos": round(time.perf_counter() - inicio, 3),
                }
            )

        if self._proposta is not None:
            registrar(ok=False, erro="já há proposta")
            return {
                "erro": f"já existe a proposta {self._proposta['id']} nesta execução; encerre "
                "com o resumo para o operador",
                "proposta": self._proposta,
            }
        veredito = self.verificador.verificar(
            self.sessao, chave, opcoes=self._opcoes, isolamento=self._isolamento
        )
        if not veredito.ok:
            recusa = {"chave": chave, **veredito.to_dict()}
            self._recusas.append(recusa)
            registrar(ok=False, erro="verificador recusou", problemas=list(veredito.problemas))
            if self.audit is not None:
                self.audit.registrar("agente.verificador.recusa", **recusa)
            return {
                "erro": "o verificador recusou a proposta; escolha outra opção viável ou proponha "
                "só o isolamento (sem chave)",
                "problemas": veredito.problemas,
                "avisos": veredito.avisos,
            }
        resultado = self.sessao.propose_plan(chave=chave, justificativa=justificativa)
        resultado["verificador"] = veredito.to_dict()
        self._proposta, self._veredito = resultado, veredito
        registrar(ok=True, resumo=_resumir(resultado))
        if self.audit is not None:
            self.audit.registrar(
                "agente.verificador.ok", proposta=resultado["id"], chave=chave, **veredito.to_dict()
            )
        return resultado

    # -- laço ----------------------------------------------------------------------------------

    def _rodar(
        self,
        mensagem: str,
        *,
        consulta: str,
        exigir_proposta: bool,
        tipo: str,
        evento: dict[str, Any] | None = None,
        pergunta: str | None = None,
    ) -> Execucao:
        self._chamadas, self._recusas = [], []
        self._opcoes = self._isolamento = None
        self._proposta, self._veredito = None, None
        tipo_evento = (evento or {}).get("tipo")
        escolhidos = selecionar_exemplos(self.exemplos, consulta, self.top_k, tipo=tipo_evento)
        execucao = Execucao(
            tipo=tipo,
            cluster=self.sessao.nome,
            evento=evento,
            pergunta=pergunta,
            provider=self.provider,
            modelo=getattr(self.cliente, "modelo", None),
            exemplos=[e.id for e in escolhidos],
            inicio=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        historico: list[Message] = [
            Message.system(montar_prompt_sistema(escolhidos)),
            Message.user(mensagem),
        ]
        ferramentas = self._ferramentas()
        if self.audit is not None:
            self.audit.registrar(
                "agente.inicio",
                tipo=tipo,
                cluster=self.sessao.nome,
                evento=evento,
                pergunta=pergunta,
                provider=self.provider,
                modelo=execucao.modelo,
                exemplos=execucao.exemplos,
                ferramentas=[f.name for f in ferramentas],
            )
        t0 = time.perf_counter()
        usos: list[Uso] = []
        try:
            conversa = self._conversar(historico, ferramentas, execucao, usos)
            while (
                exigir_proposta
                and self._proposta is None
                and execucao.replanejamentos < self.replanejamentos
            ):
                execucao.replanejamentos += 1
                historico = [*conversa.mensagens, Message.user(self._mensagem_replanejar())]
                conversa = self._conversar(historico, ferramentas, execucao, usos)
            execucao.resposta = conversa.resposta.content or ""
            if exigir_proposta and self._proposta is None:
                execucao.erro = (
                    f"sem proposta após {execucao.replanejamentos} replanejamento(s): o modelo "
                    "encerrou sem chamar propose_plan (ou o verificador recusou todas)"
                )
        except LLMError as exc:
            execucao.erro = str(exc)
            if "não concluiu" in str(exc):  # conversar esgotou max_rodadas
                execucao.rodadas += self.max_rodadas
        execucao.segundos_total = time.perf_counter() - t0
        execucao.ferramentas = list(self._chamadas)
        execucao.recusas = list(self._recusas)
        execucao.proposta = self._proposta
        execucao.veredito = None if self._veredito is None else self._veredito.to_dict()
        execucao.uso = {
            "prompt_tokens": sum(u.prompt_tokens for u in usos),
            "completion_tokens": sum(u.completion_tokens for u in usos),
            "total_tokens": sum(u.total_tokens for u in usos),
            "informado": bool(usos),
        }
        if self.audit is not None:
            execucao.hash_auditoria = self.audit.registrar(
                "agente.fim",
                tipo=tipo,
                cluster=self.sessao.nome,
                proposta=None if self._proposta is None else self._proposta["id"],
                veredito=execucao.veredito,
                sequencia=execucao.sequencia,
                rodadas=execucao.rodadas,
                replanejamentos=execucao.replanejamentos,
                recusas=len(self._recusas),
                uso=execucao.uso,
                segundos_llm=round(execucao.segundos_llm, 3),
                segundos_total=round(execucao.segundos_total, 3),
                modelo=execucao.modelo,
                erro=execucao.erro,
                resposta=execucao.resposta[:2000],
            ).hash
        return execucao

    def _conversar(self, historico, ferramentas, execucao: Execucao, usos: list[Uso]) -> Conversa:
        conversa = conversar(
            self.cliente,
            historico,
            ferramentas,
            max_rodadas=self.max_rodadas,
            audit=self.audit,
        )
        execucao.rodadas += conversa.rodadas
        execucao.segundos_llm += conversa.segundos
        execucao.modelo = conversa.resposta.modelo or execucao.modelo
        if conversa.uso_total is not None:
            usos.append(conversa.uso_total)
        return conversa

    def _mensagem_replanejar(self) -> str:
        if self._recusas:
            ultima = self._recusas[-1]
            return (
                "Você terminou sem uma proposta aceita. O verificador recusou a última tentativa: "
                + "; ".join(ultima.get("problemas", []))
                + ". Escolha outra opção VIÁVEL de restore_options ou chame propose_plan() sem "
                "chave para isolar a falta e religar o tronco são. Depois, o resumo."
            )
        return (
            "Você terminou sem chamar propose_plan. Há uma falta permanente registrada: se existe "
            "opção viável em restore_options, chame propose_plan(chave=...); se não existe, chame "
            "propose_plan() sem chave (isolar e religar o tronco são) e recomende despacho de "
            "equipe. Depois, o resumo para o operador."
        )


# ---------------------------------------------------------------------------------------------
# Operador fake (offline, determinístico): segue o fluxo FLISR pelas regras do prompt
# ---------------------------------------------------------------------------------------------

_RE_EVENTO = re.compile(r"^EVENTO (\{.*\})$", re.MULTILINE)


def _execucoes_do_historico(messages: Sequence[Message]) -> list[tuple[str, dict, Any]]:
    """``(ferramenta, argumentos, resultado)`` de cada chamada já respondida no histórico."""
    pendentes: dict[str, ToolCall] = {}
    saida = []
    for m in messages:
        if m.role == "assistant":
            for c in m.tool_calls:
                pendentes[c.id] = c
        elif m.role == "tool" and m.tool_call_id in pendentes:
            c = pendentes.pop(m.tool_call_id)
            try:
                resultado = json.loads(m.content or "null")
            except json.JSONDecodeError:
                resultado = m.content
            saida.append((c.name, dict(c.arguments), resultado))
    return saida


def _evento_do_historico(messages: Sequence[Message]) -> dict[str, Any] | None:
    for m in messages:
        if m.role == "user" and m.content:
            achado = _RE_EVENTO.search(m.content)
            if achado:
                try:
                    return json.loads(achado.group(1))
                except json.JSONDecodeError:
                    return None
    return None


def fake_operador(modelo: str = "fake-operador") -> FakeLLMClient:
    """``FakeLLMClient`` com regra que emula um operador competente e segue o fluxo do prompt:
    falta permanente → locate → isolate → restore_options(score) → propose_plan(melhor viável; a
    seguinte se o verificador recusar; sem chave se não houver) → resumo; pico → run_powerflow;
    transitória/chave → só resumo; pergunta → get_topology → resposta. Sem rede, sem custo."""

    def regra(messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Resposta:
        feitas = _execucoes_do_historico(messages)
        nomes = [n for n, _, _ in feitas]
        disponiveis = {t.name for t in tools}
        evento = _evento_do_historico(messages) or {}
        tipo = evento.get("tipo")

        def chamar(nome: str, **args: Any) -> ToolCalls:
            return ToolCalls(
                (ToolCall(f"call_{len(feitas) + 1}", nome, args),), modelo=modelo, uso=Uso()
            )

        def resultado_de(nome: str) -> Any:
            for n, _, r in reversed(feitas):
                if n == nome and isinstance(r, dict) and "erro" not in r:
                    return r
            return None

        if tipo == FALTA_PERMANENTE:
            if "locate_fault" not in nomes:
                return chamar("locate_fault")
            if "isolate_fault" not in nomes:
                return chamar("isolate_fault")
            if "restore_options" not in nomes:
                return chamar("restore_options", score=True)
            proposta = resultado_de("propose_plan")
            if proposta is None and "propose_plan" in disponiveis:
                opcoes = (resultado_de("restore_options") or {}).get("opcoes") or []
                tentadas = {a.get("chave") for n, a, _ in feitas if n == "propose_plan"}
                candidatas = [
                    o
                    for o in opcoes
                    if o["chave"] not in tentadas
                    and (o.get("score") is None or o["score"].get("viavel"))
                ]
                if candidatas:
                    o = candidatas[0]
                    score = o.get("score") or {}
                    ucbt = (o.get("clientes") or {}).get("ucbt", "?")
                    just = (
                        f"opção viável com maior margem no disjuntor de {o.get('fonte')}: "
                        f"margem {_fmt_pct(score.get('margem_disjuntor'))}, Vmin MT "
                        f"{score.get('vmin_mt_pu', '?')} pu, {ucbt} UCBT recuperados"
                    )
                    return chamar("propose_plan", chave=o["chave"], justificativa=just)
                if None not in tentadas:
                    return chamar(
                        "propose_plan",
                        justificativa="nenhuma opção de restauração viável: isolar a falta, "
                        "religar o tronco são e despachar equipe para o trecho",
                    )
            return Text(_resumo_falta(feitas), modelo=modelo, uso=Uso())
        if tipo == PICO_CARGA:
            if "run_powerflow" not in nomes and "run_powerflow" in disponiveis:
                lm = float(evento.get("detalhes", {}).get("loadmult") or 1.3)
                return chamar("run_powerflow", loadmult=lm)
            r = resultado_de("run_powerflow") or {}
            convergiu = "convergiu" if r.get("convergiu") else "NÃO convergiu"
            return Text(
                f"Pico de carga em {evento.get('ctmt')}: fluxo com loadmult "
                f"{r.get('loadmult', '?')} {convergiu}; Vmin {r.get('vmin_pu', '?')} pu, "
                f"{len(r.get('sobrecargas') or [])} sobrecarga(s), perdas "
                f"{_fmt(r.get('perdas_kw'))} kW. Sem manobra; acompanhar.",
                modelo=modelo,
                uso=Uso(),
            )
        if tipo == FALTA_TRANSITORIA:
            d = evento.get("detalhes", {})
            return Text(
                f"Falta transitória em {evento.get('trecho')} ({evento.get('ctmt')}): o religador "
                f"{d.get('religador', '?')} religou em {d.get('tempo_morto_s', '?')} s. Nenhuma "
                "manobra; registrar a ocorrência e acompanhar reincidência.",
                modelo=modelo,
                uso=Uso(),
            )
        if tipo == CHAVE_INDISPONIVEL:
            d = evento.get("detalhes", {})
            return Text(
                f"Chave {evento.get('chave')} ({d.get('normal', '?')}, {d.get('estado', '?')}) "
                f"indisponível por {d.get('motivo', '?')}: não entra em planos de manobra até "
                "restabelecer o telecomando; manobra local só por equipe.",
                modelo=modelo,
                uso=Uso(),
            )
        if "get_topology" not in nomes and "get_topology" in disponiveis:
            return chamar("get_topology", com_chaves=False)
        topo = (resultado_de("get_topology") or {}).get("resumo", {})
        return Text(
            "Resumo do cluster: " + ", ".join(f"{k} {v}" for k, v in list(topo.items())[:8]) + ".",
            modelo=modelo,
            uso=Uso(),
        )

    return FakeLLMClient(regra=regra)


def _fmt(valor: Any) -> str:
    n = _numero(valor)
    return "?" if n is None else f"{n:.1f}"


def _fmt_pct(valor: Any) -> str:
    n = _numero(valor)
    return "?" if n is None else f"{n:.0%}"


def _resumo_falta(feitas: Sequence[tuple[str, dict, Any]]) -> str:
    por_nome: dict[str, Any] = {}
    for n, _, r in feitas:
        if isinstance(r, dict) and "erro" not in r:
            por_nome[n] = r
    loc = por_nome.get("locate_fault", {})
    iso = por_nome.get("isolate_fault", {})
    opt = por_nome.get("restore_options", {})
    prop = por_nome.get("propose_plan")
    sem = (loc.get("sem_tensao") or {}).get("clientes", {})
    linhas = [
        f"Falta permanente no trecho {loc.get('trecho', '?')} ({loc.get('ctmt', '?')}), religador "
        f"{loc.get('religador', '?')} aberto: {sem.get('total', '?')} clientes sem tensão.",
        f"Isolamento (fronteira {', '.join(iso.get('chaves') or []) or '—'}): "
        f"{_sequencia_texto(iso.get('sequencia')) if iso.get('sequencia') else 'já isolada'}"
        + ("; religar o tronco são" if iso.get("religar_apos_isolar") else "")
        + ".",
    ]
    descartadas = []
    for o in opt.get("opcoes") or []:
        s = o.get("score") or {}
        if prop is not None and o.get("chave") == prop.get("chave"):
            continue
        motivo = "; ".join(s.get("motivos") or []) or (
            f"margem {_fmt_pct(s.get('margem_disjuntor'))}" if s else "sem score"
        )
        descartadas.append(f"{o.get('chave')} → {o.get('fonte')} ({motivo})")
    if prop is not None:
        if prop.get("chave"):
            linhas.append(
                f"Proposta {prop.get('id')}: restaurar por {prop.get('chave')} → "
                f"{prop.get('fonte')}; sequência {_sequencia_texto(prop.get('manobras'))}."
            )
        else:
            linhas.append(
                f"Proposta {prop.get('id')}: sem opção viável de restauração — só isolar e "
                f"religar o tronco são ({_sequencia_texto(prop.get('manobras'))}); despachar "
                "equipe."
            )
    else:
        linhas.append("Nenhuma proposta criada.")
    if descartadas:
        linhas.append("Alternativas descartadas: " + "; ".join(descartadas) + ".")
    if prop is not None:
        linhas.append(f"Aguarda aprovação do operador: bdgd-light aprovar {prop.get('id')}.")
    return "\n".join(linhas)


def _sequencia_texto(manobras: Any) -> str:
    if not manobras:
        return "—"
    return ", ".join(f"{m.get('acao')} {m.get('chave')}" for m in manobras)
