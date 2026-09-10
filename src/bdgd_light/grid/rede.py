"""Grafo do alimentador (issue #6): a rede MT de um ou mais CTMT como ``networkx.Graph``.

Mapeamento BDGD → grafo (detalhes, medições e decisões em ``docs/grid-modelo.md``):

- **Nós** são os ``PAC`` da rede MT: ``PAC_1``/``PAC_2`` de ``SSDMT`` e ``UNSEMT`` e o ``PAC_1`` de
  ``UNTRMT`` (lado MT — na Light 2025 sempre coincide com um PAC de ``SSDMT``). O nó-fonte de cada
  CTMT é ``CTMT.PAC_INI``: na Light 2025 ele é sempre o ``PAC_1`` do disjuntor de saída (``UNSEMT``,
  ``TIP_UNID = 29``) e nunca aparece em ``SSDMT`` — o alimentador começa no disjuntor.
- **Arestas**: trechos ``SSDMT`` (``tipo="trecho"``: ``comp`` em m, ``tip_cnd``, ``cod``), chaves
  ``UNSEMT`` (``tipo="chave"``: ``normal`` NA/NF por ``P_N_OPE``, estado atual ``aberta``, ``tlcd``,
  ``tip_unid``) e interligações (``tipo="tie"``): uma ponte sem impedância do PAC "de fora" da chave
  NA até o ``PAC_VIZ`` da camada ``INTERLIGACOES`` (extremidade do trecho do CTMT vizinho).
- CTMT vizinhos que não estão no grafo viram um nó externo ``EXT:<CTMT>`` — uma fonte sempre
  energizada — e a chave NA do vizinho que toca a nossa rede vira uma aresta ``chave`` ``externa``
  entre o nosso PAC e esse nó. Assim ``restore_options`` enxerga a transferência de carga mesmo num
  ``Feeder`` sozinho; num ``Cluster`` os vizinhos carregados se ligam pelos PAC reais.
- Clientes: ``UCBT_tab`` via ``UNI_TR_MT`` → ``UNTRMT.PAC_1``; ``UCMT_tab`` via ``PAC``. A rede BT
  não entra no grafo (é radial por transformador e não muda a análise de manobras MT).

Os métodos seguem os nomes da issue: ``energized_nodes``, ``downstream``, ``customers_downstream``,
``open_switch``/``close_switch``, ``tie_switches``, ``isolate_segment`` e ``restore_options``.
"""

from __future__ import annotations

import copy
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import networkx as nx
import pandas as pd
import pyogrio
import shapely

TRECHO = "trecho"
CHAVE = "chave"
TIE = "tie"
PREFIXO_EXTERNO = "EXT:"

# colunas lidas de cada camada do GeoPackage (as demais são ignoradas para o grafo ficar leve)
COLUNAS_GRAFO: dict[str, list[str]] = {
    "CTMT": ["COD_ID", "NOME", "SUB", "PAC_INI", "TEN_NOM"],
    "SSDMT": ["COD_ID", "CTMT", "PAC_1", "PAC_2", "COMP", "TIP_CND"],
    "UNSEMT": ["COD_ID", "CTMT", "PAC_1", "PAC_2", "P_N_OPE", "TLCD", "TIP_UNID"],
    "UNTRMT": ["COD_ID", "CTMT", "PAC_1", "POT_NOM"],
    "UCBT_tab": ["COD_ID", "UNI_TR_MT"],
    "UCMT_tab": ["COD_ID", "PAC"],
    "INTERLIGACOES": [
        "COD_ID",
        "CTMT",
        "CTMT_VIZ",
        "SSDMT_VIZ",
        "PAC_VIZ",
        "DIST_M",
        "TLCD",
        "TIP_UNID",
        "EM_SUB",
    ],
    "SUB": ["COD_ID"],
}
OBRIGATORIAS = ("CTMT", "SSDMT", "UNSEMT")


class ChaveInexistenteError(KeyError):
    def __init__(self, cod: str):
        super().__init__(f"chave {cod!r} não existe no grafo")


class TrechoInexistenteError(KeyError):
    def __init__(self, cod: str):
        super().__init__(f"trecho {cod!r} não existe no grafo")


@dataclass(frozen=True)
class Clientes:
    """Contagem de clientes ligados a um conjunto de nós (via UNTRMT/UCBT_tab e UCMT_tab)."""

    ucbt: int = 0
    ucmt: int = 0
    trafos: int = 0
    kva: float = 0.0

    def __add__(self, outro: Clientes) -> Clientes:
        return Clientes(
            self.ucbt + outro.ucbt,
            self.ucmt + outro.ucmt,
            self.trafos + outro.trafos,
            round(self.kva + outro.kva, 3),
        )

    @property
    def total(self) -> int:
        return self.ucbt + self.ucmt

    def to_dict(self) -> dict:
        return {
            "ucbt": self.ucbt,
            "ucmt": self.ucmt,
            "trafos": self.trafos,
            "kva": self.kva,
            "total": self.total,
        }

    @classmethod
    def from_dict(cls, dados: Mapping) -> Clientes:
        return cls(
            int(dados.get("ucbt", 0)),
            int(dados.get("ucmt", 0)),
            int(dados.get("trafos", 0)),
            float(dados.get("kva", 0.0)),
        )


ABRIR = "abrir"
FECHAR = "fechar"


def manobra(acao: str, chave: str) -> dict:
    """Um passo de manobra, no formato que o agente propõe e o operador aprova."""
    if acao not in (ABRIR, FECHAR):
        raise ValueError(f"ação deve ser {ABRIR!r} ou {FECHAR!r}, não {acao!r}")
    return {"acao": acao, "chave": chave}


@dataclass
class Isolamento:
    """Resultado de ``isolate_segment``: o que abrir e quem fica sem tensão."""

    trecho: str
    chaves: list[str]  # chaves fechadas a abrir (mínimas: a primeira em cada direção)
    zona: set[str]  # nós entre essas chaves — ficam sem tensão enquanto durar a falta
    desligados: set[str]  # nós sãos que perdem alimentação e podem ser restaurados
    clientes_zona: Clientes
    clientes_desligados: Clientes

    @property
    def manobras(self) -> list[dict]:
        """Sequência de passos para isolar o trecho: abrir cada chave da fronteira."""
        return [manobra(ABRIR, c) for c in self.chaves]

    def to_dict(self) -> dict:
        """Versão serializável em JSON (conjuntos → listas ordenadas, ``Clientes`` → dict)."""
        return {
            "trecho": self.trecho,
            "chaves": list(self.chaves),
            "zona": sorted(self.zona),
            "desligados": sorted(self.desligados),
            "clientes_zona": self.clientes_zona.to_dict(),
            "clientes_desligados": self.clientes_desligados.to_dict(),
            "manobras": self.manobras,
        }


@dataclass
class OpcaoRestauracao:
    """Uma chave NA que, fechada após o isolamento, reenergiza ``nos`` a partir de ``fonte``."""

    chave: str
    ctmt_chave: str
    fonte: str  # CTMT que passa a alimentar os nós (o próprio, no caso de anel interno)
    tlcd: bool
    tip_unid: str
    externa: bool  # chave cadastrada em CTMT fora do grafo (vista pela camada INTERLIGACOES)
    nos: set[str]
    clientes: Clientes  # recuperados ao fechar a chave
    clientes_fonte: Clientes  # já atendidos pela fonte antes da transferência (0 se externa)
    manobras: list[dict] = field(default_factory=list)  # abrir chaves do isolamento, fechar a NA

    def to_dict(self) -> dict:
        """Versão serializável em JSON (conjuntos → listas ordenadas, ``Clientes`` → dict)."""
        return {
            "chave": self.chave,
            "ctmt_chave": self.ctmt_chave,
            "fonte": self.fonte,
            "tlcd": self.tlcd,
            "tip_unid": self.tip_unid,
            "externa": self.externa,
            "nos": sorted(self.nos),
            "clientes": self.clientes.to_dict(),
            "clientes_fonte": self.clientes_fonte.to_dict(),
            "manobras": [dict(m) for m in self.manobras],
        }


@dataclass
class Camadas:
    """Camadas do grafo: ``CTMT``, ``SSDMT`` e ``UNSEMT`` obrigatórias; o resto é opcional."""

    ctmt: pd.DataFrame
    ssdmt: gpd.GeoDataFrame
    unsemt: gpd.GeoDataFrame
    untrmt: gpd.GeoDataFrame | None = None
    ucbt_tab: pd.DataFrame | None = None
    ucmt_tab: pd.DataFrame | None = None
    interligacoes: gpd.GeoDataFrame | None = None
    sub: gpd.GeoDataFrame | None = None

    @classmethod
    def de_dict(cls, camadas: Mapping[str, pd.DataFrame]) -> Camadas:
        ausentes = [c for c in OBRIGATORIAS if c not in camadas]
        if ausentes:
            raise ValueError(f"camada(s) obrigatória(s) ausente(s) para o grafo: {ausentes}")
        return cls(
            ctmt=camadas["CTMT"],
            ssdmt=camadas["SSDMT"],
            unsemt=camadas["UNSEMT"],
            untrmt=camadas.get("UNTRMT"),
            ucbt_tab=camadas.get("UCBT_tab"),
            ucmt_tab=camadas.get("UCMT_tab"),
            interligacoes=camadas.get("INTERLIGACOES"),
            sub=camadas.get("SUB"),
        )


def ler_camadas(gpkg: str | Path) -> Camadas:
    """Lê do GeoPackage de ``bdgd-light recortar`` só as camadas e colunas que o grafo usa."""
    caminho = str(gpkg)
    existentes = {nome: geom for nome, geom in pyogrio.list_layers(caminho)}
    lidas: dict[str, pd.DataFrame] = {}
    for camada, colunas in COLUNAS_GRAFO.items():
        if camada not in existentes:
            continue
        campos = set(pyogrio.read_info(caminho, layer=camada)["fields"])
        lidas[camada] = pyogrio.read_dataframe(
            caminho,
            layer=camada,
            columns=[c for c in colunas if c in campos],
            read_geometry=existentes[camada] is not None,
        )
    return Camadas.de_dict(lidas)


def _texto(valor) -> str:
    return (
        "" if valor is None or (isinstance(valor, float) and pd.isna(valor)) else str(valor).strip()
    )


def _tlcd(valor) -> bool:
    numero = pd.to_numeric(valor, errors="coerce")
    return bool(not pd.isna(numero) and int(numero) == 1)


def _externo(no: str) -> bool:
    return no.startswith(PREFIXO_EXTERNO)


def _extremidades(geom) -> tuple[tuple[float, float], tuple[float, float]] | None:
    if geom is None or geom.is_empty:
        return None
    partes = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    ini, fim = partes[0].coords[0], partes[-1].coords[-1]
    return (float(ini[0]), float(ini[1])), (float(fim[0]), float(fim[1]))


class Rede:
    """Grafo de um ou mais alimentadores. Use ``Feeder`` (um CTMT) ou ``Cluster`` (vários)."""

    def __init__(self, camadas: Camadas, *, ties_na_se: bool = False):
        self.camadas = camadas
        self.ties_na_se = ties_na_se
        self.grafo = nx.Graph()
        self.ctmts: list[str] = [_texto(c) for c in camadas.ctmt["COD_ID"]]
        self.fontes: dict[str, str] = {}
        self.trechos: dict[str, tuple[str, str]] = {}
        self.chaves: dict[str, tuple[str, str]] = {}
        self.trafos: dict[str, str] = {}
        self.clientes: dict[str, Clientes] = {}
        self.avisos: list[str] = []
        self._pacs_por_ctmt: dict[str, set[str]] = {}
        self._ties: list[dict] = []
        self._cache: dict[str, str] | None = None
        self._montar_trechos()
        self._montar_chaves()
        self._montar_fontes()
        self._montar_ties()
        self._montar_clientes()

    # --- construção ---------------------------------------------------------------------------

    @classmethod
    def from_camadas(cls, camadas: Mapping[str, pd.DataFrame], **opcoes) -> Rede:
        """Monta a partir de um ``dict`` de camadas em memória (ex.: ``Recorte.camadas``)."""
        return cls(Camadas.de_dict(camadas), **opcoes)

    def _no(self, no: str, ctmt: str, xy: tuple[float, float] | None = None) -> None:
        dados = self.grafo.nodes[no]
        dados.setdefault("ctmt", ctmt)
        dados.setdefault("tipo", "pac")
        if xy is not None and "x" not in dados:
            dados["x"], dados["y"] = xy

    def _montar_trechos(self) -> None:
        for r in self.camadas.ssdmt.itertuples(index=False):
            u, v, cod, ctmt = _texto(r.PAC_1), _texto(r.PAC_2), _texto(r.COD_ID), _texto(r.CTMT)
            if not u or not v or u == v:
                self.avisos.append(
                    f"trecho {cod}: PAC ausente ou repetido ({u!r}, {v!r}); ignorado"
                )
                continue
            if self.grafo.has_edge(u, v):
                self.avisos.append(f"trecho {cod}: par de PAC já usado por outra aresta; ignorado")
                continue
            comp = pd.to_numeric(getattr(r, "COMP", 0.0), errors="coerce")
            self.grafo.add_edge(
                u,
                v,
                tipo=TRECHO,
                cod=cod,
                ctmt=ctmt,
                comp=0.0 if pd.isna(comp) else float(comp),
                tip_cnd=_texto(getattr(r, "TIP_CND", "")),
            )
            pontas = _extremidades(getattr(r, "geometry", None))
            self._no(u, ctmt, pontas[0] if pontas else None)
            self._no(v, ctmt, pontas[1] if pontas else None)
            self.trechos[cod] = (u, v)
            self._pacs_por_ctmt.setdefault(ctmt, set()).update((u, v))

    def _montar_chaves(self) -> None:
        for r in self.camadas.unsemt.itertuples(index=False):
            u, v, cod, ctmt = _texto(r.PAC_1), _texto(r.PAC_2), _texto(r.COD_ID), _texto(r.CTMT)
            if not u or not v or u == v:
                self.avisos.append(f"chave {cod}: PAC ausente ou repetido ({u!r}, {v!r}); ignorada")
                continue
            if self.grafo.has_edge(u, v):
                self.avisos.append(f"chave {cod}: par de PAC já usado por outra aresta; ignorada")
                continue
            aberta = _texto(r.P_N_OPE).upper() == "A"
            self.grafo.add_edge(
                u,
                v,
                tipo=CHAVE,
                cod=cod,
                ctmt=ctmt,
                normal="NA" if aberta else "NF",
                aberta=aberta,
                tlcd=_tlcd(getattr(r, "TLCD", 0)),
                tip_unid=_texto(getattr(r, "TIP_UNID", "")),
                externa=False,
            )
            geom = getattr(r, "geometry", None)
            xy = (float(geom.x), float(geom.y)) if geom is not None and not geom.is_empty else None
            self._no(u, ctmt, xy)
            self._no(v, ctmt, xy)
            self.chaves[cod] = (u, v)

    def _montar_fontes(self) -> None:
        for r in self.camadas.ctmt.itertuples(index=False):
            cod, pac_ini = _texto(r.COD_ID), _texto(getattr(r, "PAC_INI", ""))
            if pac_ini and pac_ini in self.grafo:
                fonte = pac_ini
            else:
                fonte = self._fonte_alternativa(cod, _texto(getattr(r, "SUB", "")))
                if fonte is None:
                    self.avisos.append(f"{cod}: sem PAC_INI no grafo e sem trecho; CTMT sem fonte")
                    continue
                self.avisos.append(
                    f"{cod}: PAC_INI {pac_ini!r} não está no grafo; fonte = {fonte} (PAC de SSDMT "
                    "mais próximo da subestação)"
                )
            self.fontes[cod] = fonte
            self.grafo.nodes[fonte]["tipo"] = "fonte"
            self.grafo.nodes[fonte]["ctmt"] = cod

    def _fonte_alternativa(self, ctmt: str, sub: str) -> str | None:
        candidatos = sorted(self._pacs_por_ctmt.get(ctmt, set()))
        if not candidatos:
            return None
        poligono = None
        if self.camadas.sub is not None and sub and "geometry" in self.camadas.sub:
            sel = self.camadas.sub[self.camadas.sub["COD_ID"].astype(str) == sub]
            if not sel.empty:
                poligono = sel.geometry.union_all()
        if poligono is None:
            return candidatos[0]
        com_xy = [n for n in candidatos if "x" in self.grafo.nodes[n]]
        if not com_xy:
            return candidatos[0]
        pontos = shapely.points(
            [(self.grafo.nodes[n]["x"], self.grafo.nodes[n]["y"]) for n in com_xy]
        )
        distancias = shapely.distance(pontos, poligono)
        return com_xy[int(distancias.argmin())]

    def _no_externo(self, ctmt: str) -> str:
        no = f"{PREFIXO_EXTERNO}{ctmt}"
        if no not in self.grafo:
            self.grafo.add_node(no, tipo="externo", ctmt=ctmt)
        return no

    def _lado_de_fora(self, cod: str, dono: str) -> str:
        """PAC da chave que fica do lado do vizinho (o que não está na rede do CTMT dono)."""
        u, v = self.chaves[cod]
        pacs = self._pacs_por_ctmt.get(dono, set())
        u_in, v_in = u in pacs, v in pacs
        if u_in and not v_in:
            return v
        if v_in and not u_in:
            return u
        if u_in and v_in:
            self.avisos.append(
                f"chave {cod}: os dois PAC estão na rede de {dono}; tie ligada ao PAC_2 ({v})"
            )
        return v  # nenhum PAC na rede: PAC_1 é o lado fonte por convenção (como nos disjuntores)

    def _montar_ties(self) -> None:
        inter = self.camadas.interligacoes
        if inter is None or inter.empty:
            return
        carregados = set(self.ctmts)
        # da mais próxima para a mais distante: uma chave externa que toca vários PAC fica com o
        # mais próximo
        if "DIST_M" in inter:
            inter = inter.sort_values(["DIST_M", "COD_ID"], kind="stable")
        for r in inter.itertuples(index=False):
            em_sub = bool(getattr(r, "EM_SUB", False))
            if em_sub and not self.ties_na_se:
                continue
            cod, dono, viz = _texto(r.COD_ID), _texto(r.CTMT), _texto(r.CTMT_VIZ)
            pac_viz = _texto(r.PAC_VIZ)
            info = {
                "chave": cod,
                "ctmt": dono,
                "ctmt_viz": viz,
                "pac_viz": pac_viz,
                "tlcd": _tlcd(getattr(r, "TLCD", 0)),
                "tip_unid": _texto(getattr(r, "TIP_UNID", "")),
                "em_sub": em_sub,
                "dist_m": float(pd.to_numeric(getattr(r, "DIST_M", 0.0), errors="coerce") or 0.0),
            }
            if dono in carregados:
                if cod not in self.chaves:
                    self.avisos.append(
                        f"tie {cod} ({dono}→{viz}): chave não está em UNSEMT; ignorada"
                    )
                    continue
                longe = self._lado_de_fora(cod, dono)
                alvo = (
                    pac_viz
                    if viz in carregados and pac_viz in self.grafo
                    else self._no_externo(viz)
                )
                if longe == alvo or self.grafo.has_edge(longe, alvo):
                    continue
                self.grafo.add_edge(
                    longe, alvo, tipo=TIE, chave=cod, ctmt=dono, ctmt_viz=viz, dist_m=info["dist_m"]
                )
                self._ties.append({**info, "pac": longe, "externa": False})
            elif viz in carregados:
                if pac_viz not in self.grafo:
                    self.avisos.append(f"tie {cod} ({dono}→{viz}): PAC_VIZ {pac_viz} fora do grafo")
                    continue
                if cod in self.chaves:
                    self.avisos.append(
                        f"tie {cod}: chave externa toca mais de um PAC; só o primeiro"
                    )
                    continue
                ext = self._no_externo(dono)
                self.grafo.add_edge(
                    pac_viz,
                    ext,
                    tipo=CHAVE,
                    cod=cod,
                    ctmt=dono,
                    ctmt_viz=viz,
                    normal="NA",
                    aberta=True,
                    tlcd=info["tlcd"],
                    tip_unid=info["tip_unid"],
                    externa=True,
                )
                self.chaves[cod] = (pac_viz, ext)
                self._ties.append({**info, "pac": pac_viz, "externa": True})

    def _montar_clientes(self) -> None:
        untrmt = self.camadas.untrmt
        if untrmt is not None:
            por_trafo = pd.Series(dtype="int64")
            if self.camadas.ucbt_tab is not None and "UNI_TR_MT" in self.camadas.ucbt_tab:
                por_trafo = (
                    self.camadas.ucbt_tab["UNI_TR_MT"].astype(str).str.strip().value_counts()
                )
            for r in untrmt.itertuples(index=False):
                cod, no = _texto(r.COD_ID), _texto(r.PAC_1)
                if no not in self.grafo:
                    self.avisos.append(f"trafo {cod}: PAC_1 {no!r} não está na rede MT; ignorado")
                    continue
                kva = pd.to_numeric(getattr(r, "POT_NOM", 0.0), errors="coerce")
                self.trafos[cod] = no
                self._somar_clientes(
                    no,
                    Clientes(
                        ucbt=int(por_trafo.get(cod, 0)),
                        trafos=1,
                        kva=0.0 if pd.isna(kva) else float(kva),
                    ),
                )
        ucmt = self.camadas.ucmt_tab
        if ucmt is not None and "PAC" in ucmt:
            for pac, n in ucmt["PAC"].astype(str).str.strip().value_counts().items():
                if pac in self.grafo:
                    self._somar_clientes(pac, Clientes(ucmt=int(n)))
                else:
                    self.avisos.append(f"UCMT: {n} cliente(s) no PAC {pac!r} fora da rede MT")

    def _somar_clientes(self, no: str, clientes: Clientes) -> None:
        self.clientes[no] = self.clientes.get(no, Clientes()) + clientes

    # --- consulta -------------------------------------------------------------------------------

    @property
    def externos(self) -> list[str]:
        """CTMT vizinhos representados por nó externo (fora do grafo)."""
        return sorted(
            d["ctmt"] for _, d in self.grafo.nodes(data=True) if d.get("tipo") == "externo"
        )

    def nos(self) -> list[str]:
        """Nós reais (PAC), sem os externos."""
        return [n for n in self.grafo if not _externo(n)]

    def customers(self, nos: Iterable[str]) -> Clientes:
        total = Clientes()
        for no in nos:
            if no in self.clientes:
                total = total + self.clientes[no]
        return total

    def km(self) -> float:
        return round(
            sum(d["comp"] for _, _, d in self.grafo.edges(data=True) if d["tipo"] == TRECHO) / 1000,
            3,
        )

    def _passavel(self, u: str, v: str, abertas_extra: set[str]) -> bool:
        d = self.grafo.edges[u, v]
        if d["tipo"] != CHAVE:
            return True
        return not d["aberta"] and d["cod"] not in abertas_extra

    def _bfs(self, *, abertas_extra: set[str] | None = None, bloqueados: set[str] | None = None):
        """Nó → CTMT que o alimenta, a partir das fontes (PAC_INI) e dos nós externos."""
        abertas_extra = abertas_extra or set()
        bloqueados = bloqueados or set()
        fonte_de: dict[str, str] = {}
        fila: deque[str] = deque()
        for ctmt, no in self.fontes.items():
            if no not in bloqueados:
                fonte_de[no] = ctmt
                fila.append(no)
        for no, d in self.grafo.nodes(data=True):
            if d.get("tipo") == "externo" and no not in bloqueados:
                fonte_de[no] = d["ctmt"]
                fila.append(no)
        while fila:
            u = fila.popleft()
            for v in self.grafo.neighbors(u):
                if v in fonte_de or v in bloqueados or not self._passavel(u, v, abertas_extra):
                    continue
                fonte_de[v] = fonte_de[u]
                fila.append(v)
        return fonte_de

    def _energizacao(self) -> dict[str, str]:
        if self._cache is None:
            self._cache = self._bfs()
        return self._cache

    def energized_nodes(self) -> set[str]:
        """PAC com tensão no estado atual das chaves (nós externos não entram)."""
        return {n for n in self._energizacao() if not _externo(n)}

    def energized_by(self, no: str) -> str | None:
        """CTMT que alimenta o nó no estado atual (``None`` se estiver sem tensão)."""
        return self._energizacao().get(no)

    def downstream(self, no: str) -> set[str]:
        """Nós (inclusive ``no``) que só têm tensão passando por ``no``.

        Vale também em rede em anel: é o que ficaria sem alimentação se ``no`` fosse removido.
        """
        if no not in self._energizacao():
            return set()
        sem_no = self._bfs(bloqueados={no})
        return {n for n in self._energizacao() if n not in sem_no and not _externo(n)}

    def customers_downstream(self, no: str) -> Clientes:
        return self.customers(self.downstream(no))

    # --- chaves ---------------------------------------------------------------------------------

    def _aresta_chave(self, cod: str) -> dict:
        if cod not in self.chaves:
            raise ChaveInexistenteError(cod)
        u, v = self.chaves[cod]
        return self.grafo.edges[u, v]

    def open_switch(self, cod: str) -> None:
        self._aresta_chave(cod)["aberta"] = True
        self._cache = None

    def close_switch(self, cod: str) -> None:
        self._aresta_chave(cod)["aberta"] = False
        self._cache = None

    def is_open(self, cod: str) -> bool:
        return bool(self._aresta_chave(cod)["aberta"])

    def reset_switches(self) -> None:
        """Volta todas as chaves ao estado normal (``P_N_OPE``)."""
        for u, v in self.chaves.values():
            d = self.grafo.edges[u, v]
            d["aberta"] = d["normal"] == "NA"
        self._cache = None

    def tie_switches(self) -> pd.DataFrame:
        """Chaves NA de interligação (próprias e de vizinhos), uma linha por chave × vizinho."""
        colunas = [
            "chave",
            "ctmt",
            "ctmt_viz",
            "pac",
            "pac_viz",
            "tlcd",
            "tip_unid",
            "externa",
            "em_sub",
            "dist_m",
            "aberta",
        ]
        linhas = [{**t, "aberta": self.is_open(t["chave"])} for t in self._ties]
        tabela = pd.DataFrame(linhas, columns=colunas)
        return tabela.sort_values(["ctmt", "ctmt_viz", "chave"]).reset_index(drop=True)

    # --- manobras -------------------------------------------------------------------------------

    def isolate_segment(self, cod: str, *, aplicar: bool = False) -> Isolamento:
        """Chaves mínimas a abrir para isolar o trecho ``cod`` e o efeito da manobra.

        A zona de isolamento cresce a partir das duas pontas do trecho por trechos e ties (que não
        se abrem) e para na primeira chave em cada direção; as chaves dessa fronteira que estão
        fechadas são as que precisam abrir. ``desligados`` são os nós sãos que perdem tensão com a
        manobra — candidatos a ``restore_options``.
        """
        if cod not in self.trechos:
            raise TrechoInexistenteError(cod)
        u, v = self.trechos[cod]
        zona = {u, v}
        fila = deque([u, v])
        while fila:
            a = fila.popleft()
            for b, d in self.grafo.adj[a].items():
                if d["tipo"] == CHAVE or b in zona or _externo(b):
                    continue
                zona.add(b)
                fila.append(b)
        chaves = sorted(
            {
                d["cod"]
                for a in zona
                for b, d in self.grafo.adj[a].items()
                if d["tipo"] == CHAVE and not d["aberta"] and b not in zona
            }
        )
        antes = self._energizacao()
        depois = self._bfs(abertas_extra=set(chaves))
        desligados = {n for n in antes if n not in depois and n not in zona and not _externo(n)}
        resultado = Isolamento(
            trecho=cod,
            chaves=chaves,
            zona=zona,
            desligados=desligados,
            clientes_zona=self.customers(zona),
            clientes_desligados=self.customers(desligados),
        )
        if aplicar:
            for chave in chaves:
                self.open_switch(chave)
        return resultado

    def restore_options(self, cod: str) -> list[OpcaoRestauracao]:
        """Chaves NA que, fechadas depois de isolar ``cod``, devolvem tensão aos nós desligados.

        Cada opção traz os nós e clientes recuperados e o CTMT que passa a alimentá-los (um vizinho
        via tie, um nó externo, ou o próprio alimentador por um anel interno). Ordenadas por
        clientes recuperados, telecomando e código. Não altera o estado da rede.
        """
        isolamento = self.isolate_segment(cod)
        abertas = set(isolamento.chaves)
        desligados = isolamento.desligados
        if not desligados:
            return []
        energizados = self._bfs(abertas_extra=abertas)
        por_fonte: dict[str, Clientes] = {}
        for no, fonte in energizados.items():
            if no in self.clientes:
                por_fonte[fonte] = por_fonte.get(fonte, Clientes()) + self.clientes[no]
        componente: dict[str, frozenset[str]] = {}
        for inicio in desligados:
            if inicio in componente:
                continue
            grupo = {inicio}
            fila = deque([inicio])
            while fila:
                a = fila.popleft()
                for b in self.grafo.neighbors(a):
                    if b in desligados and b not in grupo and self._passavel(a, b, abertas):
                        grupo.add(b)
                        fila.append(b)
            congelado = frozenset(grupo)
            for n in grupo:
                componente[n] = congelado
        opcoes: list[OpcaoRestauracao] = []
        for chave, (a, b) in self.chaves.items():
            d = self.grafo.edges[a, b]
            if not d["aberta"] or chave in abertas:
                continue
            for lado_sem, lado_com in ((a, b), (b, a)):
                if lado_sem in desligados and lado_com in energizados:
                    nos = set(componente[lado_sem])
                    opcoes.append(
                        OpcaoRestauracao(
                            chave=chave,
                            ctmt_chave=d["ctmt"],
                            fonte=energizados[lado_com],
                            tlcd=bool(d["tlcd"]),
                            tip_unid=d["tip_unid"],
                            externa=bool(d.get("externa", False)),
                            nos=nos,
                            clientes=self.customers(nos),
                            clientes_fonte=por_fonte.get(energizados[lado_com], Clientes()),
                            manobras=isolamento.manobras + [manobra(FECHAR, chave)],
                        )
                    )
                    break
        opcoes.sort(key=lambda o: (-o.clientes.total, -int(o.tlcd), o.chave))
        return opcoes

    def copy(self) -> Rede:
        """Cópia independente do estado das chaves (as camadas são compartilhadas)."""
        novo = copy.copy(self)
        novo.grafo = self.grafo.copy()
        novo._cache = None
        return novo

    def resumo(self) -> dict:
        """Números da rede, serializáveis em JSON (``clientes`` como dict)."""
        energizados = self.energized_nodes()
        chaves = [d for _, _, d in self.grafo.edges(data=True) if d["tipo"] == CHAVE]
        return {
            "ctmt": list(self.ctmts),
            "fontes": dict(self.fontes),
            "nos": len(self.nos()),
            "trechos": len(self.trechos),
            "km": self.km(),
            "chaves": sum(1 for d in chaves if not d["externa"]),
            "chaves_NA": sum(1 for d in chaves if d["normal"] == "NA" and not d["externa"]),
            "chaves_NF": sum(1 for d in chaves if d["normal"] == "NF" and not d["externa"]),
            "ties": len(self._ties),
            "ties_externas": sum(1 for t in self._ties if t["externa"]),
            "externos": self.externos,
            "trafos": len(self.trafos),
            "clientes": self.customers(self.nos()).to_dict(),
            "energizados": len(energizados),
            "avisos": len(self.avisos),
        }

    def __repr__(self) -> str:
        r = self.resumo()
        return (
            f"{type(self).__name__}({','.join(r['ctmt'])}: {r['nos']} nós, {r['trechos']} trechos, "
            f"{r['chaves']} chaves, {r['ties']} ties, {r['energizados']} energizados)"
        )


class Feeder(Rede):
    """Grafo de um único alimentador (GPKG ``<CTMT>.gpkg`` do ``bdgd-light recortar``)."""

    def __init__(self, camadas: Camadas, **opcoes):
        if len(camadas.ctmt) != 1:
            raise ValueError(
                f"Feeder exige exatamente um CTMT (recebeu {len(camadas.ctmt)}); use Cluster"
            )
        super().__init__(camadas, **opcoes)

    @classmethod
    def from_gpkg(cls, caminho: str | Path, **opcoes) -> Feeder:
        return cls(ler_camadas(caminho), **opcoes)

    @property
    def ctmt(self) -> str:
        return self.ctmts[0]

    @property
    def fonte(self) -> str | None:
        return self.fontes.get(self.ctmt)


class Cluster(Rede):
    """União de vários alimentadores, ligados pelas arestas ``tie`` (transferência de carga)."""

    @classmethod
    def from_gpkg(cls, caminho: str | Path, **opcoes) -> Cluster:
        """A partir do ``cluster_<A>-<B>….gpkg`` do ``bdgd-light recortar``."""
        return cls(ler_camadas(caminho), **opcoes)

    @classmethod
    def from_gpkgs(cls, caminhos: Iterable[str | Path], **opcoes) -> Cluster:
        """A partir de vários ``<CTMT>.gpkg``: concatena as camadas e deduplica as interligações."""
        partes = [ler_camadas(c) for c in caminhos]
        if not partes:
            raise ValueError("nenhum GeoPackage informado")

        def juntar(nome: str, chave: list[str] | None):
            frames = [getattr(p, nome) for p in partes if getattr(p, nome) is not None]
            if not frames:
                return None
            junto = pd.concat(frames, ignore_index=True)
            return junto.drop_duplicates(subset=chave) if chave else junto

        camadas = Camadas(
            ctmt=juntar("ctmt", ["COD_ID"]),
            ssdmt=juntar("ssdmt", ["COD_ID"]),
            unsemt=juntar("unsemt", ["COD_ID"]),
            untrmt=juntar("untrmt", ["COD_ID"]),
            ucbt_tab=juntar("ucbt_tab", ["COD_ID"]),
            ucmt_tab=juntar("ucmt_tab", ["COD_ID"]),
            interligacoes=juntar("interligacoes", ["COD_ID", "CTMT_VIZ"]),
            sub=juntar("sub", ["COD_ID"]),
        )
        return cls(camadas, **opcoes)
