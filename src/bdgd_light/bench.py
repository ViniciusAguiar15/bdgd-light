"""Benchmark do agente no estilo PowerChain (issue #36): tarefas com resposta esperada e sequência
de ferramentas de referência, executadas ``n`` vezes por provedor; métricas pass@1, pass@k,
ordenação/precisão da sequência de ferramentas, tokens por acerto e tempo; CSV por execução e
relatório Markdown com tabela comparativa entre provedores e modos (com/sem exemplos anotados,
com/sem compactação).

Tarefas (``bench/tarefas.yaml``): ``id``, ``nivel`` (simple/medium/hard), ``cluster``,
``pergunta`` (ou ``evento``: ``falta_permanente``, ``falta_transitoria`` ou ``chave_indisponivel``,
gerado pelo ``Simulador`` e tratado por ``Orquestrador.executar_evento``), ``falta`` (trecho:
injetado antes da pergunta; alvo do evento de falta), ``chave`` (alvo de ``chave_indisponivel``),
``referencia`` (ferramentas na ordem esperada; vazia quando nenhuma é necessária), ``gabarito``
(ferramenta + argumentos + ``campo`` lido do retorno; ``melhor_opcao`` = conjunto de chaves
eletricamente equivalentes à melhor de ``restore_options``), ``verificar`` (``resposta`` numérica,
``proposta`` ou ``sem_manobra`` — o agente não pode criar proposta nem chamar ferramentas de
manobra, e a resposta deve citar o número do gabarito), tolerâncias, ``escala`` e ``esperado``
(documental; ``bdgd-light bench --gabarito`` confere). O gabarito é **calculado** na hora chamando
a ferramenta na sessão — o mesmo arquivo serve ao recorte real e ao cluster de teste.
"""

from __future__ import annotations

import csv
import json
import math
import random
import re
import statistics
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from bdgd_light.agent.llm import LLMClient
from bdgd_light.agent.orquestrador import (
    TOLERANCIA_MARGEM,
    Execucao,
    Exemplo,
    Orquestrador,
    fake_operador,
)
from bdgd_light.mcp_server.sessao import SessaoCOD, SessaoError, resolver_cluster
from bdgd_light.sim.eventos import (
    CHAVE_INDISPONIVEL,
    FALTA_PERMANENTE,
    FALTA_TRANSITORIA,
    Simulador,
)

TAREFAS_PADRAO = Path(__file__).resolve().parents[2] / "bench" / "tarefas.yaml"
NIVEIS = ("simple", "medium", "hard")
EVENTOS = (FALTA_PERMANENTE, FALTA_TRANSITORIA, CHAVE_INDISPONIVEL)
VERIFICACOES = ("resposta", "proposta", "sem_manobra")
FERRAMENTAS_DE_MANOBRA = ("propose_plan", "set_switch", "inject_fault")
"""Chamadas que reprovam uma tarefa ``sem_manobra`` (falta transitória, chave indisponível)."""
TOLERANCIA_REL_PADRAO = 0.02
TOLERANCIA_ABS_PADRAO = 0.5
RESPOSTA_MAX = 300


class BenchError(Exception):
    """Arquivo de tarefas inválido ou execução impossível."""


# -- tarefas ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Tarefa:
    id: str
    nivel: str
    cluster: str
    pergunta: str | None
    referencia: tuple[str, ...]
    gabarito: Mapping[str, Any]
    verificar: str = "resposta"
    evento: str | None = None
    falta: str | None = None
    chave: str | None = None
    unidade: str | None = None
    tolerancia_rel: float | None = None
    tolerancia_abs: float | None = None
    escala: float | None = None
    esperado: Any = None
    descricao: str | None = None

    @property
    def gabarito_chave(self) -> str:
        return json.dumps(
            [self.cluster, self.falta, self.chave, self.evento, dict(self.gabarito)],
            sort_keys=True,
            ensure_ascii=False,
        )


def _opcional_float(valor: Any) -> float | None:
    return None if valor is None else float(valor)


def carregar_tarefas(caminho: Path | str = TAREFAS_PADRAO) -> list[Tarefa]:
    """Lê e valida o YAML de tarefas (ids únicos, níveis conhecidos, gabarito completo)."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise BenchError(f"{exc} — instale o extra: uv sync --extra agent") from exc
    caminho = Path(caminho)
    if not caminho.exists():
        raise BenchError(f"arquivo de tarefas não encontrado: {caminho}")
    try:
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise BenchError(f"{caminho}: YAML inválido: {exc}") from exc
    itens = dados.get("tarefas") if isinstance(dados, Mapping) else dados
    if not isinstance(itens, list) or not itens:
        raise BenchError(f"{caminho}: esperado 'tarefas: [...]'")
    tarefas: list[Tarefa] = []
    vistos: set[str] = set()
    for i, item in enumerate(itens):
        if not isinstance(item, Mapping):
            raise BenchError(f"{caminho}: tarefa {i} não é um mapeamento")
        try:
            t = _tarefa(item)
        except (KeyError, TypeError, ValueError) as exc:
            raise BenchError(f"{caminho}: tarefa {item.get('id', i)!r} inválida: {exc}") from exc
        if t.id in vistos:
            raise BenchError(f"{caminho}: id repetido {t.id!r}")
        vistos.add(t.id)
        tarefas.append(t)
    return tarefas


def _tarefa(item: Mapping[str, Any]) -> Tarefa:
    nivel = str(item["nivel"]).lower()
    if nivel not in NIVEIS:
        raise ValueError(f"nível {nivel!r}; use {', '.join(NIVEIS)}")
    verificar = str(item.get("verificar", "resposta"))
    if verificar not in VERIFICACOES:
        raise ValueError(f"verificar {verificar!r}; use {', '.join(VERIFICACOES)}")
    gabarito = dict(item["gabarito"])
    if "ferramenta" not in gabarito or "campo" not in gabarito:
        raise ValueError("gabarito precisa de 'ferramenta' e 'campo'")
    gabarito.setdefault("argumentos", {})
    pergunta = item.get("pergunta")
    evento = item.get("evento")
    if pergunta is None and evento is None:
        raise ValueError("informe 'pergunta' ou 'evento'")
    if evento is not None and evento not in EVENTOS:
        raise ValueError(f"evento {evento!r} não suportado (use {', '.join(EVENTOS)})")
    if evento in (FALTA_PERMANENTE, FALTA_TRANSITORIA) and not item.get("falta"):
        raise ValueError(f"evento {evento} exige 'falta' (trecho)")
    if evento == CHAVE_INDISPONIVEL and not item.get("chave"):
        raise ValueError("evento chave_indisponivel exige 'chave'")
    if verificar == "proposta" and evento != FALTA_PERMANENTE:
        raise ValueError("verificar: proposta só com evento: falta_permanente")
    referencia = tuple(str(x) for x in item.get("referencia") or ())
    if not referencia and verificar != "sem_manobra":
        raise ValueError("referencia vazia")
    return Tarefa(
        id=str(item["id"]),
        nivel=nivel,
        cluster=str(item["cluster"]),
        pergunta=None if pergunta is None else str(pergunta),
        referencia=referencia,
        gabarito=gabarito,
        verificar=verificar,
        evento=evento,
        falta=None if item.get("falta") is None else str(item["falta"]),
        chave=None if item.get("chave") is None else str(item["chave"]),
        unidade=item.get("unidade"),
        tolerancia_rel=_opcional_float(item.get("tolerancia_rel")),
        tolerancia_abs=_opcional_float(item.get("tolerancia_abs")),
        escala=None if item.get("escala") is None else float(item["escala"]),
        esperado=item.get("esperado"),
        descricao=item.get("descricao"),
    )


def filtrar(
    tarefas: Sequence[Tarefa],
    *,
    niveis: Iterable[str] | None = None,
    ids: Iterable[str] | None = None,
    clusters: Iterable[str] | None = None,
) -> list[Tarefa]:
    niveis_set = {n.lower() for n in niveis} if niveis else None
    ids_set = set(ids) if ids else None
    clusters_set = {c.lower() for c in clusters} if clusters else None
    return [
        t
        for t in tarefas
        if (niveis_set is None or t.nivel in niveis_set)
        and (ids_set is None or t.id in ids_set)
        and (clusters_set is None or t.cluster.lower() in clusters_set)
    ]


# -- gabarito --------------------------------------------------------------------------------------


def ler_campo(dados: Any, campo: str) -> Any:
    """``a.b[0].c`` sobre dicts/listas; ``len(a.b)`` devolve o tamanho."""
    agregar = None
    m = re.fullmatch(r"(len|sum|min|max)\((.+)\)", campo.strip())
    if m:
        agregar, campo = m.group(1), m.group(2)
    atual = dados
    for parte in re.findall(r"[^.\[\]]+|\[\d+\]", campo):
        if parte.startswith("["):
            indice = int(parte[1:-1])
            if not isinstance(atual, Sequence) or indice >= len(atual):
                return None
            atual = atual[indice]
        else:
            if not isinstance(atual, Mapping):
                return None
            atual = atual.get(parte)
        if atual is None:
            return None
    if agregar == "len":
        return len(atual) if isinstance(atual, Sequence | Mapping) else None
    if agregar in ("sum", "min", "max") and isinstance(atual, Sequence):
        numeros = [float(x) for x in atual if isinstance(x, int | float)]
        return None if not numeros else {"sum": sum, "min": min, "max": max}[agregar](numeros)
    return atual


def melhor_opcao(resultado: Mapping[str, Any], tolerancia: float = TOLERANCIA_MARGEM) -> list[str]:
    """Chaves de ``restore_options`` eletricamente equivalentes à melhor: viáveis, mesmos clientes
    recuperados e margem do disjuntor a menos de ``tolerancia`` da maior (o mesmo critério do
    verificador). Lista vazia = não há opção viável (proposta sem chave)."""
    opcoes = [
        o for o in resultado.get("opcoes") or [] if (o.get("score") or {}).get("viavel") is True
    ]
    if not opcoes:
        return []

    def margem(o: Mapping[str, Any]) -> float:
        v = (o.get("score") or {}).get("margem_disjuntor")
        return float(v) if isinstance(v, int | float) else -math.inf

    def clientes(o: Mapping[str, Any]) -> Any:
        return (o.get("clientes") or {}).get("total")

    melhor = max(opcoes, key=margem)
    return [
        o["chave"]
        for o in opcoes
        if clientes(o) == clientes(melhor) and margem(o) >= margem(melhor) - tolerancia
    ]


class Gabarito:
    """Calcula (e guarda) a resposta esperada de cada tarefa chamando a ferramenta do gabarito na
    sessão — com a mesma falta injetada que o agente verá."""

    def __init__(self, sessao: SessaoCOD, feeders: Path | str):
        self.sessao = sessao
        self.feeders = Path(feeders)
        self._cache: dict[str, Any] = {}

    def esperado(self, tarefa: Tarefa) -> Any:
        chave = tarefa.gabarito_chave
        if chave not in self._cache:
            try:
                self._cache[chave] = self._calcular(tarefa)
            except (SessaoError, FileNotFoundError, KeyError, TypeError, ValueError) as exc:
                raise BenchError(f"{tarefa.id}: gabarito impossível — {exc}") from exc
        return self._cache[chave]

    def _calcular(self, tarefa: Tarefa) -> Any:
        # falta transitória (o religador religou) e chave indisponível: rede no estado normal
        preparar_sessao(
            self.sessao,
            tarefa,
            self.feeders,
            injetar_falta=tarefa.evento in (None, FALTA_PERMANENTE),
        )
        nome = tarefa.gabarito["ferramenta"]
        metodo = getattr(self.sessao, nome, None)
        if metodo is None:
            raise BenchError(f"{tarefa.id}: ferramenta de gabarito desconhecida {nome!r}")
        resultado = metodo(**dict(tarefa.gabarito.get("argumentos") or {}))
        campo = tarefa.gabarito["campo"]
        if campo == "melhor_opcao":
            return melhor_opcao(resultado)
        valor = ler_campo(resultado, campo)
        if valor is None:
            raise BenchError(f"{tarefa.id}: campo {campo!r} ausente no retorno de {nome}")
        if tarefa.escala is not None and isinstance(valor, int | float):
            valor = valor * tarefa.escala
        return valor


def preparar_sessao(
    sessao: SessaoCOD, tarefa: Tarefa, feeders: Path | str, *, injetar_falta: bool = True
) -> None:
    """Recarrega o cluster da tarefa (estado limpo) e injeta a falta, se houver. Nas tarefas de
    ``evento`` o orquestrador injeta a falta ele mesmo (``injetar_falta=False``)."""
    gpkg = resolver_cluster(tarefa.cluster, feeders)
    sessao.load_cluster(str(gpkg))
    if tarefa.falta and injetar_falta:
        sessao.inject_fault(tarefa.falta)


# -- extração de números e acerto ------------------------------------------------------------------

_RE_NUMERO = re.compile(r"(?<![\w,.])[-+]?(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)(?![\w])")


def extrair_numeros(texto: str) -> list[float]:
    """Números de um texto em pt-BR: ``4.036`` → 4036 (e também 4.036, ambíguo), ``45,98`` →
    45.98, ``1.234,5`` → 1234.5, ``0.93`` → 0.93."""
    saida: list[float] = []
    for bruto in _RE_NUMERO.findall(texto or ""):
        s = bruto.replace("+", "")
        if "," in s:
            saida.append(float(s.replace(".", "").replace(",", ".")))
        elif re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", s):
            saida.append(float(s.replace(".", "")))
            if s.count(".") == 1:
                saida.append(float(s))
        else:
            try:
                saida.append(float(s))
            except ValueError:
                continue
    return saida


def tolerancias(tarefa: Tarefa, esperado: float) -> tuple[float, float]:
    """(absoluta, relativa) da tarefa. Padrão: contagens inteiras exigem o valor exato (±0,5);
    grandezas fracionárias aceitam ±2 %. A tarefa pode fixar qualquer das duas."""
    inteiro = float(esperado).is_integer()
    rel = tarefa.tolerancia_rel
    if rel is None:
        rel = 0.0 if inteiro else TOLERANCIA_REL_PADRAO
    abs_ = tarefa.tolerancia_abs
    if abs_ is None:
        abs_ = TOLERANCIA_ABS_PADRAO if inteiro else 0.0
    return abs_, rel


def confere(valor: float, esperado: float, tarefa: Tarefa) -> bool:
    abs_, rel = tolerancias(tarefa, esperado)
    return abs(valor - esperado) <= max(abs_, rel * abs(esperado))


def acerto_resposta(resposta: str, esperado: Any, tarefa: Tarefa) -> tuple[bool, Any]:
    """Se algum número da resposta bate com o esperado (na escala pedida ou na fração); devolve o
    número que casou (ou o mais próximo, para diagnóstico)."""
    if not isinstance(esperado, int | float) or isinstance(esperado, bool):
        return (str(esperado) in (resposta or ""), esperado)
    numeros = extrair_numeros(resposta)
    if not numeros:
        return False, None
    alvos = [float(esperado)]
    if tarefa.escala:
        alvos.append(float(esperado) / tarefa.escala)
    for alvo in alvos:
        for n in numeros:
            if confere(n, alvo, tarefa):
                return True, n
    return False, min(numeros, key=lambda n: abs(n - float(esperado)))


def acerto_proposta(execucao: Execucao, esperado: Any) -> tuple[bool, Any]:
    proposta = execucao.proposta or {}
    chave = proposta.get("chave") if proposta else None
    aceitos = list(esperado) if isinstance(esperado, list | tuple | set) else [esperado]
    if not proposta:
        return False, None
    if not aceitos:
        return chave is None, chave
    return chave in aceitos, chave


def acerto_sem_manobra(execucao: Execucao, esperado: Any, tarefa: Tarefa) -> tuple[bool, Any]:
    """Eventos sem manobra (falta transitória, chave indisponível): reprova se o agente criou
    proposta ou chamou ferramenta de manobra; fora isso, a resposta tem de citar o gabarito
    (número do evento, ex. clientes afetados) — ``None`` dispensa a citação."""
    if execucao.proposta:
        return False, f"proposta {execucao.proposta.get('id')}"
    indevidas = [f for f in execucao.sequencia if f in FERRAMENTAS_DE_MANOBRA]
    if indevidas:
        return False, f"chamou {', '.join(indevidas)}"
    if esperado is None:
        return bool((execucao.resposta or "").strip()), None
    return acerto_resposta(execucao.resposta, esperado, tarefa)


# -- sequência de ferramentas ----------------------------------------------------------------------


def lcs(a: Sequence[str], b: Sequence[str]) -> int:
    tabela = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                tabela[i][j] = tabela[i - 1][j - 1] + 1
            else:
                tabela[i][j] = max(tabela[i - 1][j], tabela[i][j - 1])
    return tabela[len(a)][len(b)]


def ordenacao(sequencia: Sequence[str], referencia: Sequence[str]) -> tuple[float, float]:
    """``(ordem, precisao)``: fração da referência coberta em ordem (LCS/len(ref)) e fração das
    chamadas feitas que estão nessa subsequência (LCS/len(seq))."""
    if not referencia:
        return (1.0, 1.0 if not sequencia else 0.0)
    comum = lcs(list(sequencia), list(referencia))
    ordem = comum / len(referencia)
    precisao = comum / len(sequencia) if sequencia else 0.0
    return round(ordem, 4), round(precisao, 4)


# -- métricas --------------------------------------------------------------------------------------


def pass_at_k(n: int, c: int, k: int) -> float:
    """Estimador sem viés de pass@k (Chen et al., 2021): 1 − C(n−c, k)/C(n, k); k é limitado a n."""
    if n <= 0:
        return 0.0
    k = min(k, n)
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


@dataclass
class Rodada:
    """Uma execução de uma tarefa."""

    tarefa: str
    nivel: str
    cluster: str
    repeticao: int
    acerto: bool
    obtido: Any
    esperado: Any
    sequencia: list[str]
    referencia: list[str]
    ordem: float
    precisao: float
    rodadas: int
    tokens_prompt: int
    tokens_completion: int
    tokens_total: int
    tokens_informados: bool
    chars_ferramentas: int
    segundos_llm: float
    segundos_ferramentas: float
    segundos_total: float
    replanejamentos: int
    recusas: int
    erro: str | None
    resposta: str
    provider: str
    modelo: str | None
    exemplos: bool
    compactado: bool
    seed: int | None
    data: str


# Preços de lista (US$ por milhão de tokens: entrada, saída) das páginas de preços dos provedores —
# Gemini conferido em 2026-09-11 (ai.google.dev/gemini-api/docs/pricing); OpenAI = preço de lista
# dos modelos (platform.openai.com/docs/pricing). Só para a leitura de custo na apresentação: sem
# cache de contexto, sem lote. Tokens de raciocínio (Gemini 2.5 conta os "thoughts" em ``total`` mas
# não em ``completion``) são cobrados como saída.
PRECOS_USD_MILHAO: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5": (1.25, 10.00),
}


def preco_modelo(modelo: str | None) -> tuple[float, float] | None:
    """Preço ``(entrada, saída)`` em US$/M tokens pelo prefixo mais longo do nome do modelo
    (``gpt-4.1-mini-2025-04-14`` → ``gpt-4.1-mini``; ``openai/gpt-4.1-mini`` do GitHub Models
    também); ``None`` para fake, ollama ou modelo fora da tabela."""
    if not modelo:
        return None
    nome = modelo.rsplit("/", 1)[-1].lower()
    candidatos = [prefixo for prefixo in PRECOS_USD_MILHAO if nome.startswith(prefixo)]
    if not candidatos:
        return None
    return PRECOS_USD_MILHAO[max(candidatos, key=len)]


def custo_usd(rodada: Rodada) -> float | None:
    """Custo estimado da execução em US$ (preço de lista × tokens informados pelo provedor);
    ``None`` quando não há uso informado ou preço conhecido."""
    preco = preco_modelo(rodada.modelo)
    if preco is None or not rodada.tokens_informados:
        return None
    entrada, saida = preco
    tokens_saida = max(rodada.tokens_total - rodada.tokens_prompt, rodada.tokens_completion, 0)
    return (rodada.tokens_prompt * entrada + tokens_saida * saida) / 1e6


def resumir(rodadas: Sequence[Rodada], k: int) -> dict[str, dict[str, Any]]:
    """Métricas por nível e no total: tarefas, execuções, pass@1, pass@k (média por tarefa),
    ordem, precisão, tokens por acerto (pass@1), custo em US$ (preço de lista), chars de
    ferramenta, segundos."""
    saida: dict[str, dict[str, Any]] = {}
    for nivel in (*NIVEIS, "total"):
        grupo = [r for r in rodadas if nivel == "total" or r.nivel == nivel]
        if not grupo:
            continue
        por_tarefa: dict[str, list[Rodada]] = {}
        for r in grupo:
            por_tarefa.setdefault(r.tarefa, []).append(r)
        n = len(grupo)
        c = sum(1 for r in grupo if r.acerto)
        p1 = c / n
        pk = statistics.fmean(
            pass_at_k(len(rs), sum(1 for r in rs if r.acerto), k) for rs in por_tarefa.values()
        )
        tokens = statistics.fmean(r.tokens_total for r in grupo)
        chars = statistics.fmean(r.chars_ferramentas for r in grupo)
        # execução sem uso informado (ex.: timeout) entra como 0; grupo sem preço conhecido → None
        custos = [custo_usd(r) for r in grupo]
        usd = None if all(c is None for c in custos) else statistics.fmean(c or 0.0 for c in custos)
        saida[nivel] = {
            "tarefas": len(por_tarefa),
            "execucoes": n,
            "acertos": c,
            "pass@1": round(p1, 4),
            f"pass@{k}": round(pk, 4),
            "ordem": round(statistics.fmean(r.ordem for r in grupo), 4),
            "precisao": round(statistics.fmean(r.precisao for r in grupo), 4),
            "tokens_medio": round(tokens, 1),
            "tokens_por_pass1": None if p1 == 0 else round(tokens / p1, 1),
            "usd_medio": None if usd is None else round(usd, 5),
            "usd_por_pass1": None if usd is None or p1 == 0 else round(usd / p1, 5),
            "chars_ferramentas_medio": round(chars, 1),
            "segundos_medio": round(statistics.fmean(r.segundos_total for r in grupo), 2),
            "rodadas_medio": round(statistics.fmean(r.rodadas for r in grupo), 2),
            "erros": sum(1 for r in grupo if r.erro),
        }
    return saida


# -- execução --------------------------------------------------------------------------------------


@dataclass
class Configuracao:
    provider: str = "fake"
    modelo: str | None = None
    k: int = 5
    n: int | None = None
    seed: int | None = None
    exemplos: bool = True
    compactar: bool = True
    top_k: int = 3
    max_rodadas: int = 8
    replanejamentos: int = 2
    exigir_score: bool = True
    dia: str = "DU"
    mes: int = 1

    @property
    def repeticoes(self) -> int:
        return self.n if self.n is not None else self.k

    @property
    def modo(self) -> str:
        partes = []
        if not self.exemplos:
            partes.append("sem-exemplos")
        if not self.compactar:
            partes.append("sem-compactar")
        return "-".join(partes) or "padrao"

    @property
    def rotulo(self) -> str:
        return self.provider + ("" if self.modo == "padrao" else f"-{self.modo}")


class Benchmark:
    """Roda as tarefas com um provedor e devolve as ``Rodada``s."""

    def __init__(
        self,
        feeders: Path | str,
        dss_out: Path | str,
        estado_dir: Path | str,
        config: Configuracao,
        *,
        cliente: LLMClient | None = None,
        exemplos: Sequence[Exemplo] | None = None,
    ):
        self.feeders = Path(feeders)
        self.config = config
        self.sessao = SessaoCOD(
            feeders=self.feeders,
            dss_out=Path(dss_out),
            estado_dir=Path(estado_dir),
            dia=config.dia.upper(),
            mes=config.mes,
        )
        self.gabarito = Gabarito(self.sessao, self.feeders)
        self.cliente = cliente if cliente is not None else self._cliente()
        self.exemplos = exemplos
        self.modelo = getattr(self.cliente, "modelo", None)
        self.data = datetime.now(UTC).isoformat(timespec="seconds")

    def _cliente(self) -> LLMClient:
        cfg = self.config
        if cfg.provider == "fake":
            return fake_operador(cfg.modelo or "fake-operador")
        from bdgd_light.agent.llm import cliente_por_perfil

        opcoes: dict[str, Any] = {}
        if cfg.seed is not None and cfg.provider == "openai":
            opcoes["seed"] = cfg.seed
        return cliente_por_perfil(cfg.provider, cfg.modelo, audit=self.sessao.audit, **opcoes)

    def orquestrador(self) -> Orquestrador:
        cfg = self.config
        return Orquestrador(
            self.sessao,
            self.cliente,
            exemplos=self.exemplos if cfg.exemplos else [],
            top_k=cfg.top_k if cfg.exemplos else 0,
            max_rodadas=cfg.max_rodadas,
            replanejamentos=cfg.replanejamentos,
            exigir_score=cfg.exigir_score,
            provider=cfg.provider,
            compactar=cfg.compactar,
        )

    def executar_tarefa(self, tarefa: Tarefa, repeticao: int) -> Rodada:
        cfg = self.config
        inicio = perf_counter()
        try:
            esperado = self.gabarito.esperado(tarefa)
        except BenchError as exc:
            return self._rodada_erro(tarefa, repeticao, None, str(exc), perf_counter() - inicio)
        execucao: Execucao | None = None
        erro: str | None = None
        try:
            preparar_sessao(self.sessao, tarefa, self.feeders, injetar_falta=tarefa.evento is None)
            orq = self.orquestrador()
            if tarefa.evento is not None:
                seed = None if cfg.seed is None else cfg.seed + repeticao
                sim = Simulador(self.sessao.rede, tarefa.cluster, seed=seed)
                if tarefa.evento == FALTA_PERMANENTE:
                    ev = sim.falta_permanente(tarefa.falta)
                elif tarefa.evento == FALTA_TRANSITORIA:
                    ev = sim.falta_transitoria(tarefa.falta)
                else:
                    ev = sim.chave_indisponivel(tarefa.chave)
                execucao = orq.executar_evento(ev)
            else:
                execucao = orq.responder(tarefa.pergunta or "")
            erro = execucao.erro
        except (SessaoError, FileNotFoundError, KeyError, ValueError, RuntimeError) as exc:
            erro = f"{type(exc).__name__}: {exc}"
        except Exception as exc:  # provedor caiu, HTTP, etc.: registra e segue
            erro = f"{type(exc).__name__}: {exc}"
        segundos = perf_counter() - inicio
        if execucao is None:
            return self._rodada_erro(tarefa, repeticao, esperado, erro, segundos)
        if tarefa.verificar == "proposta":
            acerto, obtido = acerto_proposta(execucao, esperado)
        elif tarefa.verificar == "sem_manobra":
            acerto, obtido = acerto_sem_manobra(execucao, esperado, tarefa)
        else:
            acerto, obtido = acerto_resposta(execucao.resposta, esperado, tarefa)
        ordem, precisao = ordenacao(execucao.sequencia, tarefa.referencia)
        uso = execucao.uso or {}
        return Rodada(
            tarefa=tarefa.id,
            nivel=tarefa.nivel,
            cluster=tarefa.cluster,
            repeticao=repeticao,
            acerto=bool(acerto),
            obtido=obtido,
            esperado=esperado,
            sequencia=list(execucao.sequencia),
            referencia=list(tarefa.referencia),
            ordem=ordem,
            precisao=precisao,
            rodadas=execucao.rodadas,
            tokens_prompt=int(uso.get("prompt_tokens") or 0),
            tokens_completion=int(uso.get("completion_tokens") or 0),
            tokens_total=int(uso.get("total_tokens") or 0),
            tokens_informados=bool(uso.get("informado")),
            chars_ferramentas=execucao.chars_ferramentas,
            segundos_llm=round(execucao.segundos_llm, 3),
            segundos_ferramentas=round(execucao.segundos_ferramentas, 3),
            segundos_total=round(execucao.segundos_total or segundos, 3),
            replanejamentos=execucao.replanejamentos,
            recusas=len(execucao.recusas),
            erro=erro,
            resposta=(execucao.resposta or "")[:RESPOSTA_MAX],
            provider=cfg.provider,
            modelo=execucao.modelo or self.modelo,
            exemplos=cfg.exemplos,
            compactado=cfg.compactar,
            seed=cfg.seed,
            data=self.data,
        )

    def _rodada_erro(self, tarefa, repeticao, esperado, erro, segundos) -> Rodada:
        cfg = self.config
        return Rodada(
            tarefa=tarefa.id,
            nivel=tarefa.nivel,
            cluster=tarefa.cluster,
            repeticao=repeticao,
            acerto=False,
            obtido=None,
            esperado=esperado,
            sequencia=[],
            referencia=list(tarefa.referencia),
            ordem=0.0,
            precisao=0.0,
            rodadas=0,
            tokens_prompt=0,
            tokens_completion=0,
            tokens_total=0,
            tokens_informados=False,
            chars_ferramentas=0,
            segundos_llm=0.0,
            segundos_ferramentas=0.0,
            segundos_total=round(segundos, 3),
            replanejamentos=0,
            recusas=0,
            erro=erro,
            resposta="",
            provider=cfg.provider,
            modelo=self.modelo,
            exemplos=cfg.exemplos,
            compactado=cfg.compactar,
            seed=cfg.seed,
            data=self.data,
        )

    def rodar(
        self,
        tarefas: Sequence[Tarefa],
        *,
        progresso: Callable[[Rodada, int, int], None] | None = None,
    ) -> list[Rodada]:
        """Executa cada tarefa ``repeticoes`` vezes; a ordem é embaralhada pela semente (mesma
        semente → mesma ordem, mesma falta, mesmo fake)."""
        ordem = [(t, r) for t in tarefas for r in range(1, self.config.repeticoes + 1)]
        if self.config.seed is not None:
            random.Random(self.config.seed).shuffle(ordem)
        saida: list[Rodada] = []
        for i, (tarefa, rep) in enumerate(ordem, start=1):
            rodada = self.executar_tarefa(tarefa, rep)
            saida.append(rodada)
            if progresso is not None:
                progresso(rodada, i, len(ordem))
        return saida


# -- saída -----------------------------------------------------------------------------------------

COLUNAS_CSV = [f.name for f in Rodada.__dataclass_fields__.values()]


_COLUNAS_JSON = ("obtido", "esperado", "sequencia", "referencia")
"""Colunas gravadas como JSON (preservam tipo: chave "746851189" ≠ número, listas, None)."""


def _celula(chave: str, valor: Any) -> Any:
    if chave in _COLUNAS_JSON:
        return json.dumps(valor, ensure_ascii=False, default=str)
    if isinstance(valor, list | tuple | dict):
        return json.dumps(valor, ensure_ascii=False, default=str)
    if isinstance(valor, bool):
        return int(valor)
    return "" if valor is None else valor


def escrever_csv(rodadas: Sequence[Rodada], caminho: Path | str) -> Path:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS_CSV)
        w.writeheader()
        for r in rodadas:
            w.writerow({k: _celula(k, v) for k, v in asdict(r).items()})
    return caminho


def ler_csv(caminho: Path | str) -> list[Rodada]:
    caminho = Path(caminho)
    saida: list[Rodada] = []
    with caminho.open(encoding="utf-8", newline="") as f:
        for linha in csv.DictReader(f):
            try:
                saida.append(_rodada_de_csv(linha))
            except (KeyError, ValueError, json.JSONDecodeError):
                continue
    return saida


def _rodada_de_csv(linha: Mapping[str, str]) -> Rodada:
    def num(chave: str, tipo=float):
        v = linha.get(chave, "")
        return tipo(0) if v in ("", None) else tipo(float(v))

    def lista(chave: str) -> list[str]:
        v = linha.get(chave) or "[]"
        return list(json.loads(v))

    def opcional(chave: str) -> Any:
        v = linha.get(chave)
        return None if v in ("", None) else v

    def valor(chave: str) -> Any:
        v = linha.get(chave)
        if v in ("", None):
            return None
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return v

    return Rodada(
        tarefa=linha["tarefa"],
        nivel=linha["nivel"],
        cluster=linha.get("cluster", ""),
        repeticao=num("repeticao", int),
        acerto=bool(num("acerto", int)),
        obtido=valor("obtido"),
        esperado=valor("esperado"),
        sequencia=lista("sequencia"),
        referencia=lista("referencia"),
        ordem=num("ordem"),
        precisao=num("precisao"),
        rodadas=num("rodadas", int),
        tokens_prompt=num("tokens_prompt", int),
        tokens_completion=num("tokens_completion", int),
        tokens_total=num("tokens_total", int),
        tokens_informados=bool(num("tokens_informados", int)),
        chars_ferramentas=num("chars_ferramentas", int),
        segundos_llm=num("segundos_llm"),
        segundos_ferramentas=num("segundos_ferramentas"),
        segundos_total=num("segundos_total"),
        replanejamentos=num("replanejamentos", int),
        recusas=num("recusas", int),
        erro=opcional("erro"),
        resposta=linha.get("resposta", ""),
        provider=linha.get("provider", "?"),
        modelo=opcional("modelo"),
        exemplos=bool(num("exemplos", int)) if linha.get("exemplos") not in ("", None) else True,
        compactado=(
            bool(num("compactado", int)) if linha.get("compactado") not in ("", None) else True
        ),
        seed=None if linha.get("seed") in ("", None) else int(float(linha["seed"])),
        data=linha.get("data", ""),
    )


def nome_relatorio(config: Configuracao, quando: datetime | None = None) -> str:
    quando = quando or datetime.now(UTC)
    return f"{quando:%Y-%m-%d}-{config.rotulo}"


def _pct(v: Any) -> str:
    return "—" if v is None else f"{100 * float(v):.0f} %"


def _num(v: Any, casas: int = 1) -> str:
    if v is None:
        return "—"
    return f"{float(v):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _rotulo(r: Rodada) -> str:
    partes = [r.provider]
    if not r.exemplos:
        partes.append("sem-exemplos")
    if not r.compactado:
        partes.append("sem-compactar")
    return "-".join(partes)


def comparativo(rodadas_por_rotulo: Mapping[str, Sequence[Rodada]], k: int) -> str:
    """Tabela Markdown comparando provedores/modos: pass@1 por nível, pass@k, ordem, tokens por
    acerto, custo em US$ por execução (preço de lista), chars por execução, segundos."""
    linhas = [
        f"| provedor · modo | modelo | tarefas | pass@1 simple | pass@1 medium | pass@1 hard | "
        f"pass@1 total | pass@{k} total | ordem | precisão | tokens/pass@1 | US$/exec. | "
        f"chars ferr./exec. | s/exec. |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for rotulo in sorted(rodadas_por_rotulo):
        rs = rodadas_por_rotulo[rotulo]
        if not rs:
            continue
        res = resumir(rs, k)
        total = res.get("total", {})
        modelos = sorted({r.modelo for r in rs if r.modelo})
        linhas.append(
            f"| {rotulo} | {', '.join(modelos) or '—'} | {total.get('tarefas', 0)} | "
            f"{_pct(res.get('simple', {}).get('pass@1'))} | "
            f"{_pct(res.get('medium', {}).get('pass@1'))} | "
            f"{_pct(res.get('hard', {}).get('pass@1'))} | {_pct(total.get('pass@1'))} | "
            f"{_pct(total.get(f'pass@{k}'))} | {_pct(total.get('ordem'))} | "
            f"{_pct(total.get('precisao'))} | {_num(total.get('tokens_por_pass1'), 0)} | "
            f"{_usd(total.get('usd_medio'))} | {_num(total.get('chars_ferramentas_medio'), 0)} | "
            f"{_num(total.get('segundos_medio'))} |"
        )
    return "\n".join(linhas)


def carregar_comparativo(pasta: Path | str) -> dict[str, list[Rodada]]:
    """Rodadas dos CSVs de ``pasta`` agrupadas por provedor·modo — só o arquivo mais recente (nome
    ``<data>-<rótulo>.csv``) de cada rótulo, para o comparativo não misturar versões; um arquivo
    pode acumular execuções de datas diferentes (``bench --acrescentar``)."""
    por_rotulo: dict[str, tuple[str, list[Rodada]]] = {}
    for csv_path in sorted(Path(pasta).glob("*.csv")):
        por_arquivo: dict[str, list[Rodada]] = {}
        for r in ler_csv(csv_path):
            por_arquivo.setdefault(_rotulo(r), []).append(r)
        for rotulo, rs in por_arquivo.items():
            atual = por_rotulo.get(rotulo)
            if atual is None or csv_path.name >= atual[0]:
                por_rotulo[rotulo] = (csv_path.name, rs)
    return {rotulo: rs for rotulo, (_, rs) in por_rotulo.items()}


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
        ).stdout.strip()
    except OSError:
        return ""


def relatorio_markdown(
    rodadas: Sequence[Rodada],
    config: Configuracao,
    *,
    tarefas: Sequence[Tarefa],
    arquivo_tarefas: Path | str,
    csv_path: Path | str | None = None,
    comparativo_md: str | None = None,
    k: int | None = None,
) -> str:
    k = k or config.k
    res = resumir(rodadas, k)
    modelos = sorted({r.modelo for r in rodadas if r.modelo})
    quando = rodadas[0].data if rodadas else datetime.now(UTC).isoformat(timespec="seconds")
    por_id = {t.id: t for t in tarefas}
    linhas = [
        f"# Benchmark do agente — {config.rotulo} ({quando[:10]})",
        "",
        f"- provedor/modelo: **{config.provider}** · {', '.join(modelos) or '—'}",
        f"- modo: exemplos anotados {'sim' if config.exemplos else 'não'} (top-k "
        f"{config.top_k if config.exemplos else 0}); compactação dos retornos "
        f"{'sim' if config.compactar else 'não'}",
        f"- k = {k}; repetições por tarefa = {config.repeticoes}; semente = {config.seed}",
        f"- tarefas: {len({r.tarefa for r in rodadas})} de `{arquivo_tarefas}`; execuções: "
        f"{len(rodadas)}; erros: {sum(1 for r in rodadas if r.erro)}",
        f"- commit: `{_commit() or '?'}`" + (f"; CSV: `{csv_path}`" if csv_path else ""),
        "",
        "## Métricas por nível",
        "",
        f"| nível | tarefas | exec. | pass@1 | pass@{k} | ordem | precisão | tokens médios | "
        f"tokens/pass@1 | US$/exec. | US$/pass@1 | chars ferr. | s/exec. | rodadas |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for nivel, m in res.items():
        linhas.append(
            f"| {nivel} | {m['tarefas']} | {m['execucoes']} | {_pct(m['pass@1'])} | "
            f"{_pct(m[f'pass@{k}'])} | {_pct(m['ordem'])} | {_pct(m['precisao'])} | "
            f"{_num(m['tokens_medio'], 0)} | {_num(m['tokens_por_pass1'], 0)} | "
            f"{_usd(m['usd_medio'])} | {_usd(m['usd_por_pass1'])} | "
            f"{_num(m['chars_ferramentas_medio'], 0)} | {_num(m['segundos_medio'])} | "
            f"{_num(m['rodadas_medio'])} |"
        )
    if rodadas and not any(r.tokens_informados for r in rodadas):
        linhas.append("")
        linhas.append(
            "> O provedor não informa uso de tokens (fake): `chars ferr.` (caracteres de JSON das "
            "respostas de ferramenta enviadas ao modelo) é o proxy de custo."
        )
    elif res.get("total", {}).get("usd_medio") is not None:
        entrada, saida = preco_modelo(modelos[0]) or (0.0, 0.0)
        linhas.append("")
        linhas.append(
            f"> US$ = preço de lista de `{modelos[0]}` (US$ {entrada:.2f}/M tokens de entrada, "
            f"US$ {saida:.2f}/M de saída, raciocínio incluído) × tokens informados pelo provedor; "
            "sem cache de contexto nem lote."
        )
    linhas += ["", "## Por tarefa", ""]
    linhas.append(
        "| id | nível | cluster | acertos | pass@1 | ordem | sequência típica | esperado | obtido "
        "(último) | tokens médios | s/exec. |"
    )
    linhas.append("|---|---|---|---|---|---|---|---|---|---|---|")
    por_tarefa: dict[str, list[Rodada]] = {}
    for r in rodadas:
        por_tarefa.setdefault(r.tarefa, []).append(r)
    for tid in sorted(
        por_tarefa, key=lambda x: (NIVEIS.index(por_id[x].nivel) if x in por_id else 9, x)
    ):
        rs = por_tarefa[tid]
        c = sum(1 for r in rs if r.acerto)
        seqs = [" → ".join(r.sequencia) for r in rs if r.sequencia]
        tipica = max(set(seqs), key=seqs.count) if seqs else "—"
        ultimo = rs[-1]
        linhas.append(
            f"| {tid} | {rs[0].nivel} | {rs[0].cluster} | {c}/{len(rs)} | {_pct(c / len(rs))} | "
            f"{_pct(statistics.fmean(r.ordem for r in rs))} | {tipica} | "
            f"{_fmt_valor(ultimo.esperado)} | {_fmt_valor(ultimo.obtido)} | "
            f"{_num(statistics.fmean(r.tokens_total for r in rs), 0)} | "
            f"{_num(statistics.fmean(r.segundos_total for r in rs))} |"
        )
    erros = [r for r in rodadas if r.erro]
    if erros:
        linhas += ["", "## Erros", ""]
        for r in erros:
            linhas.append(f"- {r.tarefa} (rep. {r.repeticao}): {r.erro}")
    if comparativo_md:
        linhas += ["", "## Comparativo (todos os CSVs de `docs/bench/`)", "", comparativo_md]
    linhas.append("")
    return "\n".join(linhas)


def _usd(v: float | None) -> str:
    return "—" if v is None else f"{v:.4f}"


def _fmt_valor(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer()):
        return _num(v, 0)
    if isinstance(v, float):
        return _num(v, 3 if abs(v) < 100 else 1)
    if isinstance(v, list | tuple | set):
        return ", ".join(str(x) for x in v) or "∅ (sem chave)"
    return str(v)


__all__ = [
    "Benchmark",
    "BenchError",
    "Configuracao",
    "Gabarito",
    "Rodada",
    "Tarefa",
    "acerto_proposta",
    "acerto_resposta",
    "carregar_comparativo",
    "carregar_tarefas",
    "comparativo",
    "escrever_csv",
    "extrair_numeros",
    "filtrar",
    "ler_campo",
    "ler_csv",
    "melhor_opcao",
    "nome_relatorio",
    "ordenacao",
    "pass_at_k",
    "relatorio_markdown",
    "resumir",
]
