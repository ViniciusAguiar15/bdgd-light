"""Verificador elétrico das opções de restauração (ADR-001, decisão 6; issue #18).

Para cada ``OpcaoRestauracao`` do grafo (``Rede.restore_options``), roda o fluxo snapshot do Master
do cluster com as manobras da opção aplicadas (``comandos_manobras``) e mede, **só na MT**:

- corrente no disjuntor da fonte que recebe a carga (corrente da ``Vsource`` do CTMT) e a margem em
  relação à corrente nominal de referência;
- tensões MT mínima e máxima nos nós da fonte e nos nós transferidos;
- trechos MT sobrecarregados (carregamento > 100 % da ampacidade) na fonte e na zona transferida;
- perdas totais do cluster.

``viavel`` = convergiu ∧ ``vmin`` ≤ V_MT ≤ ``vmax`` ∧ I_disjuntor ≤ I_nominal ∧ sem sobrecarga MT.
A BT fica fora do veredito (ramais RAMLIG suspeitos na BDGD — ver ``docs/spike-opendss.md``).

Corrente nominal de referência: ``UNSEMT.COR_NOM`` é um código do domínio da BDGD que não vem
embutido no GDB e não foi resolvido para ampères; a chave sai do conversor sem ampacidade
(``normamps`` padrão do OpenDSS, 400 A, fictício). Usa-se então a ampacidade ``normamps`` dos
trechos SSDMT imediatamente a jusante do disjuntor (o tronco; somada se a SE tiver mais de uma
saída), com ``nominais`` permitindo sobrescrever o valor por CTMT quando a corrente nominal real
for conhecida.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx

from bdgd_light.grid.rede import CHAVE, TRECHO, OpcaoRestauracao, Rede
from bdgd_light.twin.cluster import comandos_manobras
from bdgd_light.twin.gpkg2dss import cod_id_trecho_mt_de_elemento, nome_elemento_trecho_mt
from bdgd_light.twin.powerflow import PowerFlowResult, _dss, no_motor, run_powerflow

_NAN = float("nan")


@dataclass
class ScoreEletrico:
    """Veredito elétrico de uma ``OpcaoRestauracao`` no gêmeo OpenDSS."""

    chave: str
    fonte: str
    convergiu: bool
    iteracoes: int
    controle_iteracoes: int | None
    i_disjuntor_a: float  # corrente máxima de fase na Vsource da fonte (NaN se não simulado)
    i_nominal_a: float  # referência: tronco a jusante do disjuntor ou ``nominais`` (NaN se ignota)
    margem_disjuntor: float  # (i_nominal - i_disjuntor) / i_nominal; NaN se sem referência
    vmin_mt_pu: float
    vmin_mt_barra: str | None
    vmax_mt_pu: float
    vmax_mt_barra: str | None
    sobrecargas_mt: list[str]  # elementos MT (fonte + zona transferida) acima de 100 %
    carregamento_max_mt_pct: float
    trechos_carregados_mt: list[dict[str, Any]]
    perfil_tensao_mt: list[dict[str, Any]]
    perdas_kw: float
    viavel: bool
    motivos: list[str]  # por que não é viável (vazio se viável)
    ajustes: list[str]  # estabilizadores do fluxo que foram necessários
    tempo_s: float
    opcao: OpcaoRestauracao = field(repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        """Versão serializável em JSON (NaN → ``None``)."""

        def num(x: float) -> float | None:
            return None if x is None or math.isnan(x) else float(x)

        return {
            "chave": self.chave,
            "fonte": self.fonte,
            "convergiu": self.convergiu,
            "iteracoes": self.iteracoes,
            "controle_iteracoes": self.controle_iteracoes,
            "i_disjuntor_a": num(self.i_disjuntor_a),
            "i_nominal_a": num(self.i_nominal_a),
            "margem_disjuntor": num(self.margem_disjuntor),
            "vmin_mt_pu": num(self.vmin_mt_pu),
            "vmin_mt_barra": self.vmin_mt_barra,
            "vmax_mt_pu": num(self.vmax_mt_pu),
            "vmax_mt_barra": self.vmax_mt_barra,
            "vmin_mt": {"barra": self.vmin_mt_barra, "pu": num(self.vmin_mt_pu)},
            "vmax_mt": {"barra": self.vmax_mt_barra, "pu": num(self.vmax_mt_pu)},
            "sobrecargas_mt": list(self.sobrecargas_mt),
            "carregamento_max_mt_pct": num(self.carregamento_max_mt_pct),
            "trechos_carregados_mt": [
                {
                    "elemento": t.get("elemento"),
                    "cod_id": t.get("cod_id"),
                    "i_max_a": num(t.get("i_max_a")),
                    "i_nominal_a": num(t.get("i_nominal_a")),
                    "carregamento_pct": num(t.get("carregamento_pct")),
                }
                for t in self.trechos_carregados_mt
            ],
            "perfil_tensao_mt": [
                {
                    "barra": p.get("barra"),
                    "distancia_m": num(p.get("distancia_m")),
                    "v_pu": num(p.get("v_pu")),
                }
                for p in self.perfil_tensao_mt
            ],
            "perdas_kw": num(self.perdas_kw),
            "viavel": self.viavel,
            "motivos": list(self.motivos),
            "ajustes": list(self.ajustes),
            "convergencia": {
                "convergiu": self.convergiu,
                "iteracoes": self.iteracoes,
                "controle_iteracoes": self.controle_iteracoes,
                "ajustes": list(self.ajustes),
                "tempo_s": self.tempo_s,
            },
            "tempo_s": self.tempo_s,
            "clientes": self.opcao.clientes.to_dict(),
            "tlcd": self.opcao.tlcd,
        }


def trechos_tronco(rede: Rede, fonte: str) -> list[str]:
    """COD_ID dos trechos SSDMT imediatamente a jusante do disjuntor de ``fonte``.

    Anda a partir do PAC da fonte só por chaves fechadas e para no primeiro trecho de cada ramo.
    """
    inicio = rede.fontes.get(fonte)
    if inicio is None:
        return []
    vistos = {inicio}
    fila = deque([inicio])
    cods: list[str] = []
    while fila:
        a = fila.popleft()
        for b, d in rede.grafo.adj[a].items():
            if b in vistos:
                continue
            if d["tipo"] == TRECHO:
                cods.append(d["cod"])
            elif d["tipo"] == CHAVE and not d["aberta"]:
                vistos.add(b)
                fila.append(b)
    return cods


def ampacidade_tronco(rede: Rede, fonte: str) -> float:
    """Soma dos ``normamps`` dos trechos-tronco de ``fonte`` no circuito OpenDSS já carregado.

    NaN se nenhum trecho existir no modelo (ex.: fonte fora do cluster).
    """
    return no_motor(_ampacidade_tronco, trechos_tronco(rede, fonte))


def _ampacidade_tronco(cods: list[str]) -> float:
    dss = _dss()
    ampacidades = [
        a
        for a in (_normamps(dss, nome_elemento_trecho_mt(cod)) for cod in cods)
        if not math.isnan(a) and a > 0
    ]
    return sum(ampacidades) if ampacidades else _NAN


def _normamps(dss, nome: str) -> float:
    """``normamps`` do elemento ``nome`` no circuito carregado (NaN se não existir)."""
    try:
        dss.Circuit.SetActiveElement(nome)
    except Exception:  # circuito ausente ou nome inválido
        return _NAN
    if dss.CktElement.Name().lower() != nome.lower():
        return _NAN
    return float(dss.CktElement.NormalAmps())


def _corrente_fonte(resultado: PowerFlowResult, barra: str) -> float:
    f = resultado.fontes
    if "i_a" not in f.columns:
        return _NAN
    sel = f[f["barra"].str.lower() == barra.lower()]
    return float(sel["i_a"].iloc[0]) if len(sel) else _NAN


def _elementos_mt(rede: Rede, fonte: str, nos: Iterable[str]) -> set[str]:
    """Nomes (minúsculos) dos trechos MT da fonte e da zona transferida."""
    nos = set(nos)
    nomes: set[str] = set()
    for u, v, d in rede.grafo.edges(data=True):
        if d["tipo"] != TRECHO:
            continue
        if d["ctmt"] == fonte or (u in nos and v in nos):
            nomes.add(nome_elemento_trecho_mt(d["cod"]).lower())
    return nomes


def _fmt(x: float, casas: int = 3) -> str:
    return f"{x:.{casas}f}".replace(".", ",")


def _aresta_passavel(d: Mapping[str, Any]) -> bool:
    return d["tipo"] != CHAVE or not d["aberta"]


def _peso_aresta(d: Mapping[str, Any]) -> float:
    return float(d.get("comp") or 0.0)


def _extremo_tensao(sel, *, maior: bool) -> tuple[float, str | None]:
    if len(sel) == 0:
        return _NAN, None
    idx = sel["v_pu"].idxmax() if maior else sel["v_pu"].idxmin()
    linha = sel.loc[idx]
    return float(linha["v_pu"]), str(linha["barra"])


def _trechos_carregados_mt(
    rede: Rede, fonte: str, nos: Iterable[str], correntes, *, limite: int = 5
) -> list[dict[str, Any]]:
    c = correntes
    c = c[c["elemento"].str.lower().isin(_elementos_mt(rede, fonte, nos))]
    c = c.dropna(subset=["carregamento_pct"]).sort_values("carregamento_pct", ascending=False)
    return [
        {
            "elemento": str(r.elemento),
            "cod_id": cod_id_trecho_mt_de_elemento(str(r.elemento)),
            "i_max_a": float(r.i_max_a),
            "i_nominal_a": float(r.i_nominal_a),
            "carregamento_pct": float(r.carregamento_pct),
        }
        for r in c.head(limite).itertuples(index=False)
    ]


def _perfil_tensao_mt(
    opcao: OpcaoRestauracao, rede: Rede, resultado: PowerFlowResult
) -> list[dict]:
    depois = rede.copy()
    for passo in opcao.manobras:
        if passo["acao"] == "abrir":
            depois.open_switch(passo["chave"])
        elif passo["acao"] == "fechar":
            depois.close_switch(passo["chave"])
    inicio = depois.fontes.get(opcao.fonte)
    if inicio is None:
        return []

    grafo = nx.Graph()
    for u, v, d in depois.grafo.edges(data=True):
        if _aresta_passavel(d):
            grafo.add_edge(u, v, peso=_peso_aresta(d))
    if inicio not in grafo:
        return []

    candidatos = [n for n in opcao.nos if n in grafo and not str(n).startswith("EXT:")]
    if not candidatos:
        return []
    comprimentos, caminhos = nx.single_source_dijkstra(grafo, inicio, weight="peso")
    alcançados = [n for n in candidatos if n in caminhos]
    if not alcançados:
        return []
    ponta = max(alcançados, key=lambda n: (comprimentos[n], str(n)))
    caminho = caminhos[ponta]

    mt = resultado.tensoes_mt()
    por_barra = mt.groupby("barra", as_index=False)["v_pu"].min()
    tensoes = {str(r.barra).lower(): float(r.v_pu) for r in por_barra.itertuples(index=False)}
    perfil: list[dict[str, Any]] = []
    distancia = 0.0
    for i, barra in enumerate(caminho):
        if not str(barra).startswith("EXT:"):
            perfil.append(
                {
                    "barra": str(barra),
                    "distancia_m": round(distancia, 1),
                    "v_pu": tensoes.get(str(barra).lower(), _NAN),
                }
            )
        if i + 1 < len(caminho):
            aresta = depois.grafo.edges[caminho[i], caminho[i + 1]]
            distancia += _peso_aresta(aresta)
    return perfil


def _avaliar(
    opcao: OpcaoRestauracao,
    rede: Rede,
    resultado: PowerFlowResult,
    *,
    vmin: float,
    vmax: float,
    i_nominal: float,
) -> ScoreEletrico:
    fonte = opcao.fonte
    motivos: list[str] = []
    if not resultado.convergiu:
        motivos.append("fluxo não convergiu")

    mt = resultado.tensoes_mt()
    nos_lower = {n.lower() for n in opcao.nos}
    sel = mt[(mt["ctmt"] == fonte.upper()) | mt["barra"].str.lower().isin(nos_lower)]
    v_min, barra_vmin = _extremo_tensao(sel, maior=False)
    v_max, barra_vmax = _extremo_tensao(sel, maior=True)
    if not math.isnan(v_min) and v_min < vmin:
        motivos.append(f"Vmin MT {_fmt(v_min)} pu < {_fmt(vmin, 2)}")
    if not math.isnan(v_max) and v_max > vmax:
        motivos.append(f"Vmax MT {_fmt(v_max)} pu > {_fmt(vmax, 2)}")

    trechos_carregados = _trechos_carregados_mt(rede, fonte, opcao.nos, resultado.correntes)
    c = resultado.correntes
    c = c[c["elemento"].str.lower().isin(_elementos_mt(rede, fonte, opcao.nos))]
    c = c.dropna(subset=["carregamento_pct"])
    sobrecargas = c[c["carregamento_pct"] > 100.0].sort_values("carregamento_pct", ascending=False)
    carregamento_max = float(c["carregamento_pct"].max()) if len(c) else _NAN
    if len(sobrecargas):
        piores = ", ".join(
            f"{r.elemento} {r.carregamento_pct:.0f} %" for r in sobrecargas.head(3).itertuples()
        )
        motivos.append(f"{len(sobrecargas)} trecho(s) MT acima de 100 % ({piores})")

    i_disj = _corrente_fonte(resultado, rede.fontes[fonte])
    margem = _NAN
    if not math.isnan(i_nominal) and i_nominal > 0 and not math.isnan(i_disj):
        margem = (i_nominal - i_disj) / i_nominal
        if i_disj > i_nominal:
            motivos.append(f"I disjuntor {i_disj:.0f} A > {i_nominal:.0f} A nominal")

    return ScoreEletrico(
        chave=opcao.chave,
        fonte=fonte,
        convergiu=resultado.convergiu,
        iteracoes=resultado.iteracoes,
        controle_iteracoes=int(resultado.extra.get("controle_iteracoes"))
        if resultado.extra.get("controle_iteracoes") is not None
        else None,
        i_disjuntor_a=i_disj,
        i_nominal_a=i_nominal,
        margem_disjuntor=margem,
        vmin_mt_pu=v_min,
        vmin_mt_barra=barra_vmin,
        vmax_mt_pu=v_max,
        vmax_mt_barra=barra_vmax,
        sobrecargas_mt=sobrecargas["elemento"].tolist(),
        carregamento_max_mt_pct=carregamento_max,
        trechos_carregados_mt=trechos_carregados,
        perfil_tensao_mt=_perfil_tensao_mt(opcao, rede, resultado),
        perdas_kw=resultado.perdas_kw,
        viavel=not motivos,
        motivos=motivos,
        ajustes=list(resultado.ajustes),
        tempo_s=resultado.tempo_s,
        opcao=opcao,
    )


def _nao_simulado(opcao: OpcaoRestauracao, motivo: str) -> ScoreEletrico:
    return ScoreEletrico(
        chave=opcao.chave,
        fonte=opcao.fonte,
        convergiu=False,
        iteracoes=0,
        controle_iteracoes=None,
        i_disjuntor_a=_NAN,
        i_nominal_a=_NAN,
        margem_disjuntor=_NAN,
        vmin_mt_pu=_NAN,
        vmin_mt_barra=None,
        vmax_mt_pu=_NAN,
        vmax_mt_barra=None,
        sobrecargas_mt=[],
        carregamento_max_mt_pct=_NAN,
        trechos_carregados_mt=[],
        perfil_tensao_mt=[],
        perdas_kw=_NAN,
        viavel=False,
        motivos=[motivo],
        ajustes=[],
        tempo_s=0.0,
        opcao=opcao,
    )


def ordenar_scores(scores: Iterable[ScoreEletrico]) -> list[ScoreEletrico]:
    """Viáveis primeiro; depois maior margem no disjuntor (arredondada a 0,1 %; sem referência por
    último); depois mais UCBT restauradas. Estável: empates mantêm a ordem do grafo (clientes,
    telecomando, código)."""

    def chave(s: ScoreEletrico) -> tuple:
        margem = -math.inf if math.isnan(s.margem_disjuntor) else round(s.margem_disjuntor, 3)
        return (not s.viavel, -margem, -s.opcao.clientes.ucbt)

    return sorted(scores, key=chave)


def score_eletrico(
    opcoes: Sequence[OpcaoRestauracao],
    rede: Rede,
    master_cluster: str | Path,
    *,
    vmin: float = 0.93,
    vmax: float = 1.05,
    nominais: Mapping[str, float] | None = None,
    comandos_base: Sequence[str] = (),
    estabilizar: bool = True,
) -> list[ScoreEletrico]:
    """Roda o fluxo de cada opção no Master do cluster e devolve os scores já ordenados.

    ``master_cluster`` é o Master **base** do cluster (``montar_master_cluster`` sem manobras): as
    manobras de cada opção entram como comandos antes do ``Solve``. ``comandos_base`` (ex.: ``set
    loadmult=1.2``) valem para todas as opções; ``nominais`` (CTMT → A) sobrescreve a corrente
    nominal de referência do disjuntor. Opções cuja fonte não está no cluster (``externa`` ou CTMT
    fora do recorte) não são simuladas e saem inviáveis com o motivo registrado.
    """
    master_cluster = Path(master_cluster)
    nominais = dict(nominais or {})
    scores: list[ScoreEletrico] = []
    for opcao in opcoes:
        if opcao.fonte not in rede.fontes:
            scores.append(_nao_simulado(opcao, f"fonte {opcao.fonte} fora do cluster (sem modelo)"))
            continue
        comandos = [*comandos_base, *comandos_manobras(rede, opcao.manobras)]
        resultado = run_powerflow(
            master_cluster, vmin=vmin, vmax=vmax, estabilizar=estabilizar, comandos_extra=comandos
        )
        i_nominal = float(nominais[opcao.fonte]) if opcao.fonte in nominais else _NAN
        if math.isnan(i_nominal):
            i_nominal = ampacidade_tronco(rede, opcao.fonte)
        scores.append(_avaliar(opcao, rede, resultado, vmin=vmin, vmax=vmax, i_nominal=i_nominal))
    return ordenar_scores(scores)
