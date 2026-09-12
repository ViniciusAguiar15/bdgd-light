"""Gera ``docs/resultados.md`` a partir dos benchmarks e documentos versionados."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

DOCS_BENCH = RAIZ / "docs" / "bench"
DOC_BENCH = RAIZ / "docs" / "bench.md"
DOC_ESCOPO = RAIZ / "docs" / "escopo-cidade.md"
DOC_MCP = RAIZ / "docs" / "mcp-ferramentas.md"
DOC_GRID = RAIZ / "docs" / "grid-modelo.md"
DOC_AGENT = RAIZ / "docs" / "agent.md"
DOC_SESSAO_TIJUCA = RAIZ / "docs" / "agent" / "sessao-tijuca.json"
DOC_REVIEW_NOITE = RAIZ / "docs" / "review" / "NOITE.md"
DESTINO = RAIZ / "docs" / "resultados.md"

NIVEIS = ("simple", "medium", "hard")


@dataclass(frozen=True)
class RodadaCSV:
    tarefa: str
    nivel: str
    repeticao: int
    acerto: bool
    provider: str
    modelo: str | None
    exemplos: bool
    compactado: bool
    ordem: float
    precisao: float
    desnecessarias: int
    tokens_prompt: int
    tokens_completion: int
    tokens_total: int
    tokens_informados: bool
    chars_ferramentas: int
    segundos_total: float
    recusas: int
    data: str
    passos_sequencia: int
    passos_referencia: int
    passos_comuns: int


@dataclass(frozen=True)
class ResumoCSV:
    caminho: Path
    arquivo: str
    data_arquivo: str
    familia: str
    chave_familia: str
    provider: str
    exemplos: bool
    compactado: bool
    k_efetivo: int
    execucoes: int
    tarefas: int
    modelo: str | None
    resumo: dict[str, dict[str, float | int | None]]
    recusas_exec: int
    recusas_total: int

    @property
    def rotulo(self) -> str:
        partes = [self.provider]
        if not self.exemplos:
            partes.append("sem-exemplos")
        if not self.compactado:
            partes.append("sem-compactar")
        return "-".join(partes)

    @property
    def padrao(self) -> bool:
        return self.exemplos and self.compactado

    @property
    def modo(self) -> str:
        partes = [
            "com exemplos" if self.exemplos else "sem exemplos",
            "compactado" if self.compactado else "sem compactação",
        ]
        rotulo = ", ".join(partes)
        return f"{rotulo} ★ padrão" if self.padrao else rotulo

    @property
    def fonte(self) -> str:
        return f"docs/bench/{self.arquivo} ({self.data_arquivo})"


@dataclass(frozen=True)
class LinhaTabela:
    nome: str
    alimentadores: int
    trechos: int | None
    chaves: int
    ties_campo: int
    clientes: str
    fonte: str


@dataclass(frozen=True)
class LinhaFonteDoc:
    cenario: str
    provider: str
    proposta: str
    verificador: str
    rodadas: str
    tokens_total: str
    tempo: str
    fonte: str


def _ler_texto(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def _para_int(valor: str | None, padrao: int = 0) -> int:
    if valor in (None, ""):
        return padrao
    return int(float(valor))


def _para_float(valor: str | None, padrao: float = 0.0) -> float:
    if valor in (None, ""):
        return padrao
    return float(valor)


def _para_bool(valor: str | None, padrao: bool = False) -> bool:
    if valor in (None, ""):
        return padrao
    return bool(int(float(valor)))


def _json_lista(valor: str | None) -> list[str]:
    bruto = valor or "[]"
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError:
        return []
    if isinstance(dados, list):
        return [str(item) for item in dados]
    return []


def _lcs(a: Sequence[str], b: Sequence[str]) -> int:
    if not a or not b:
        return 0
    cols = len(b) + 1
    atual = [0] * cols
    for item_a in a:
        anterior = 0
        for j, item_b in enumerate(b, start=1):
            salvo = atual[j]
            if item_a == item_b:
                atual[j] = anterior + 1
            else:
                atual[j] = max(atual[j], atual[j - 1])
            anterior = salvo
    return atual[-1]


def _nome_benchmark(stem: str) -> str:
    return stem[11:] if re.match(r"\d{4}-\d{2}-\d{2}-", stem) else stem


def _nome_familia(stem: str) -> str:
    nome = _nome_benchmark(stem)
    for sufixo in ("-sem-exemplos", "-sem-compactar"):
        if nome.endswith(sufixo):
            nome = nome[: -len(sufixo)]
    return nome


def _fonte_relativa(caminho: Path) -> str:
    try:
        return caminho.relative_to(RAIZ).as_posix()
    except ValueError:
        return caminho.as_posix()


def ler_csv_benchmark(caminho: Path) -> list[RodadaCSV]:
    linhas: list[RodadaCSV] = []
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            sequencia = _json_lista(linha.get("sequencia"))
            referencia = _json_lista(linha.get("referencia"))
            passos_comuns = _lcs(sequencia, referencia)
            desnecessarias = linha.get("desnecessarias")
            linhas.append(
                RodadaCSV(
                    tarefa=linha["tarefa"],
                    nivel=linha["nivel"],
                    repeticao=_para_int(linha.get("repeticao"), 1),
                    acerto=_para_bool(linha.get("acerto")),
                    provider=linha.get("provider") or _nome_familia(caminho.stem).split("-")[0],
                    modelo=linha.get("modelo") or None,
                    exemplos=_para_bool(linha.get("exemplos"), True),
                    compactado=_para_bool(linha.get("compactado"), True),
                    ordem=_para_float(linha.get("ordem")),
                    precisao=_para_float(linha.get("precisao")),
                    desnecessarias=(
                        _para_int(desnecessarias)
                        if desnecessarias not in (None, "")
                        else max(len(sequencia) - passos_comuns, 0)
                    ),
                    tokens_prompt=_para_int(linha.get("tokens_prompt")),
                    tokens_completion=_para_int(linha.get("tokens_completion")),
                    tokens_total=_para_int(linha.get("tokens_total")),
                    tokens_informados=_para_bool(linha.get("tokens_informados")),
                    chars_ferramentas=_para_int(linha.get("chars_ferramentas")),
                    segundos_total=_para_float(linha.get("segundos_total")),
                    recusas=_para_int(linha.get("recusas")),
                    data=(linha.get("data") or "")[:10],
                    passos_sequencia=len(sequencia),
                    passos_referencia=len(referencia),
                    passos_comuns=passos_comuns,
                )
            )
    return linhas


PRECOS_USD_MILHAO = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5": (1.25, 10.00),
}


def preco_modelo(modelo: str | None) -> tuple[float, float] | None:
    if not modelo:
        return None
    nome = modelo.rsplit("/", 1)[-1].lower()
    candidatos = [prefixo for prefixo in PRECOS_USD_MILHAO if nome.startswith(prefixo)]
    if not candidatos:
        return None
    return PRECOS_USD_MILHAO[max(candidatos, key=len)]


def custo_usd(rodada: RodadaCSV) -> float | None:
    preco = preco_modelo(rodada.modelo)
    if preco is None or not rodada.tokens_informados:
        return None
    entrada, saida = preco
    tokens_saida = max(rodada.tokens_total - rodada.tokens_prompt, rodada.tokens_completion, 0)
    return (rodada.tokens_prompt * entrada + tokens_saida * saida) / 1e6


def pass_at_k(n: int, c: int, k: int) -> float:
    if c <= 0:
        return 0.0
    if c >= n:
        return 1.0
    k = min(k, n)
    return 1.0 - (math.comb(n - c, k) / math.comb(n, k))


def resumir_csv(caminho: Path) -> ResumoCSV:
    rodadas = ler_csv_benchmark(caminho)
    if not rodadas:
        raise ValueError(f"CSV sem rodadas válidas: {caminho}")
    k_efetivo = max(r.repeticao for r in rodadas)
    resumo: dict[str, dict[str, float | int | None]] = {}
    for nivel in (*NIVEIS, "total"):
        grupo = [r for r in rodadas if nivel == "total" or r.nivel == nivel]
        if not grupo:
            continue
        por_tarefa: dict[str, list[RodadaCSV]] = defaultdict(list)
        for rodada in grupo:
            por_tarefa[rodada.tarefa].append(rodada)
        execucoes = len(grupo)
        acertos = sum(1 for r in grupo if r.acerto)
        pass1 = acertos / execucoes
        passk = sum(
            pass_at_k(len(lista), sum(1 for r in lista if r.acerto), k_efetivo)
            for lista in por_tarefa.values()
        ) / len(por_tarefa)
        custos = [custo_usd(r) for r in grupo]
        resumo[nivel] = {
            "tarefas": len(por_tarefa),
            "execucoes": execucoes,
            "pass@1": round(pass1, 4),
            f"pass@{k_efetivo}": round(passk, 4),
            "ordem": round(sum(r.ordem for r in grupo) / execucoes, 4),
            "precisao": round(sum(r.precisao for r in grupo) / execucoes, 4),
            "ordem_passos": sum(r.passos_comuns for r in grupo),
            "ordem_total": sum(r.passos_referencia for r in grupo),
            "precisao_passos": sum(r.passos_comuns for r in grupo),
            "precisao_total": sum(r.passos_sequencia for r in grupo),
            "desnecessarias": round(sum(r.desnecessarias for r in grupo) / execucoes, 2),
            "tokens": round(sum(r.tokens_total for r in grupo) / execucoes, 1),
            "usd": (
                None
                if all(valor is None for valor in custos)
                else round(sum(valor or 0.0 for valor in custos) / execucoes, 5)
            ),
            "chars": round(sum(r.chars_ferramentas for r in grupo) / execucoes, 1),
            "segundos": round(sum(r.segundos_total for r in grupo) / execucoes, 2),
            "rodadas": round(sum(r.repeticao for r in grupo) / execucoes, 2),
        }
    datas = sorted({r.data for r in rodadas if r.data})
    modelos = sorted({r.modelo for r in rodadas if r.modelo})
    recusas_exec = sum(1 for r in rodadas if r.recusas > 0)
    recusas_total = sum(r.recusas for r in rodadas)
    return ResumoCSV(
        caminho=caminho,
        arquivo=caminho.name,
        data_arquivo=datas[-1] if datas else caminho.name[:10],
        familia=_nome_familia(caminho.stem),
        chave_familia=_nome_benchmark(caminho.stem),
        provider=rodadas[0].provider,
        exemplos=rodadas[0].exemplos,
        compactado=rodadas[0].compactado,
        k_efetivo=k_efetivo,
        execucoes=len(rodadas),
        tarefas=len({r.tarefa for r in rodadas}),
        modelo=", ".join(modelos) if modelos else None,
        resumo=resumo,
        recusas_exec=recusas_exec,
        recusas_total=recusas_total,
    )


def coletar_resumos(bench_dir: Path) -> list[ResumoCSV]:
    return [resumir_csv(caminho) for caminho in sorted(bench_dir.glob("*.csv"))]


def ultimos_por_familia(resumos: Sequence[ResumoCSV]) -> list[ResumoCSV]:
    por_familia: dict[str, ResumoCSV] = {}
    for resumo in resumos:
        atual = por_familia.get(resumo.chave_familia)
        if atual is None or resumo.arquivo > atual.arquivo:
            por_familia[resumo.chave_familia] = resumo
    return sorted(
        por_familia.values(),
        key=lambda resumo: (resumo.familia, 0 if resumo.padrao else 1, resumo.chave_familia),
    )


def pares_ab(resumos: Sequence[ResumoCSV], *, sufixo: str) -> list[tuple[ResumoCSV, ResumoCSV]]:
    por_familia: dict[str, dict[str, ResumoCSV]] = defaultdict(dict)
    for resumo in resumos:
        estado: str | None = None
        if sufixo == "sem-exemplos":
            if not resumo.compactado:
                continue
            estado = "controle" if resumo.exemplos else sufixo
        elif sufixo == "sem-compactar":
            if not resumo.exemplos:
                continue
            estado = "controle" if resumo.compactado else sufixo
        if estado is None:
            continue
        atual = por_familia[resumo.familia].get(estado)
        if atual is None or resumo.arquivo > atual.arquivo:
            por_familia[resumo.familia][estado] = resumo
    pares: list[tuple[ResumoCSV, ResumoCSV]] = []
    for familia in sorted(por_familia):
        grupo = por_familia[familia]
        if "controle" in grupo and sufixo in grupo:
            pares.append((grupo["controle"], grupo[sufixo]))
    return pares


def _pt_num(valor: float | int | None, casas: int = 1) -> str:
    if valor is None:
        return "—"
    texto = f"{float(valor):,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _pt_pct(valor: float | None, casas: int = 0) -> str:
    if valor is None:
        return "—"
    return f"{_pt_num(100 * valor, casas)} %"


def _pt_pct_fracao(
    valor: float | None,
    numerador: float | int | None,
    denominador: float | int | None,
    *,
    casas: int = 1,
) -> str:
    if valor is None or numerador is None or denominador is None:
        return _pt_pct(valor, casas)
    return f"{_pt_pct(valor, casas)} ({_pt_num(numerador, 0)}/{_pt_num(denominador, 0)})"


def _pt_usd(valor: float | None) -> str:
    if valor is None:
        return "—"
    return _pt_num(valor, 4)


def _dados_nivel(resumo: ResumoCSV, nivel: str) -> Mapping[str, float | int | None]:
    return resumo.resumo.get(nivel, {})


def _ratio(parte: int, total: int) -> str:
    if total == 0:
        return "0/0"
    return f"{parte}/{total} ({_pt_pct(parte / total)})"


def extrair_recortes(
    doc_escopo: Path, doc_mcp: Path, doc_grid: Path
) -> tuple[list[LinhaTabela], list[str]]:
    texto_escopo = _ler_texto(doc_escopo)
    texto_mcp = _ler_texto(doc_mcp) if doc_mcp.exists() else ""
    texto_grid = _ler_texto(doc_grid) if doc_grid.exists() else ""
    linhas: list[LinhaTabela] = []
    avisos: list[str] = []

    tijuca_adicionada = False
    if DOC_SESSAO_TIJUCA.exists():
        try:
            sessao = json.loads(_ler_texto(DOC_SESSAO_TIJUCA))
            resumo = sessao[0]["resultado"]["resumo"]
            clientes = resumo.get("clientes") or {}
            linhas.append(
                LinhaTabela(
                    nome="Tijuca",
                    alimentadores=len(resumo.get("ctmt") or []),
                    trechos=int(resumo.get("trechos") or 0) or None,
                    chaves=int(resumo.get("chaves") or 0),
                    ties_campo=int(resumo.get("ties") or 0),
                    clientes=(
                        f"{clientes.get('total')} clientes totais ({clientes.get('ucbt')} UCBT)"
                    ),
                    fonte=f"{_fonte_relativa(DOC_SESSAO_TIJUCA)} (criada_em 2026-09-10)",
                )
            )
            tijuca_adicionada = True
        except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass
    if not tijuca_adicionada:
        re_tijuca_mcp = re.search(
            r'cluster_tijuca".*?"ctmt": \[(?P<ctmts>[^\]]+)\].*?"trechos": (?P<trechos>\d+)'
            r'.*?"chaves": (?P<chaves>\d+).*?"ties": (?P<ties>\d+).*?"clientes": '
            r'\{"ucbt": (?P<ucbt>\d+), "ucmt": (?P<ucmt>\d+).*?"total": (?P<total>\d+)',
            texto_mcp,
            re.S,
        )
        if re_tijuca_mcp:
            ctmts = [
                item.strip().strip('"') for item in re_tijuca_mcp.group("ctmts").split(",") if item
            ]
            linhas.append(
                LinhaTabela(
                    nome="Tijuca",
                    alimentadores=len(ctmts),
                    trechos=int(re_tijuca_mcp.group("trechos")),
                    chaves=int(re_tijuca_mcp.group("chaves")),
                    ties_campo=int(re_tijuca_mcp.group("ties")),
                    clientes=(
                        f"{re_tijuca_mcp.group('total')} clientes totais "
                        f"({re_tijuca_mcp.group('ucbt')} UCBT)"
                    ),
                    fonte=(
                        f"{_fonte_relativa(doc_mcp)} (exemplo versionado do cluster_tijuca; "
                        f"apoio: {_fonte_relativa(doc_escopo)} com análise 2026-09-10 e "
                        "recálculo 2026-09-11)"
                    ),
                )
            )
            tijuca_adicionada = True
    if not tijuca_adicionada:
        avisos.append(
            "Tijuca: não encontrei os números combinados de recorte nas fontes versionadas."
        )

    re_ipanema = re.search(
        r"\| B Ipanema \| (?P<ctmts>[^|]+) \| (?P<feicoes>[\d.]+) \| "
        r"[\d.]+ / [\d,]+ / (?P<chaves>\d+) "
        r"\| (?P<ties>\d+) \([^)]*\) — (?P<em_sub>\d+) interligações `EM_SUB` \| "
        r"(?P<clientes>[^|]+) \|",
        texto_escopo,
    )
    if re_ipanema:
        linhas.append(
            LinhaTabela(
                nome="Ipanema",
                alimentadores=len(
                    [item.strip() for item in re_ipanema.group("ctmts").split(",") if item.strip()]
                ),
                trechos=None,
                chaves=int(re_ipanema.group("chaves")),
                ties_campo=int(re_ipanema.group("ties")),
                clientes=re_ipanema.group("clientes").strip(),
                fonte=(
                    f"{_fonte_relativa(doc_escopo)} (análise 2026-09-10; inventário "
                    "regerado em 2026-09-11)"
                ),
            )
        )
        avisos.append(
            "Ipanema: o documento versionado traz alimentadores, chaves, clientes e ties, "
            "mas não a contagem de trechos MT; o consolidado mantém esse campo em branco "
            "para não inferir valor."
        )
    else:
        avisos.append("Ipanema: não encontrei a linha do recorte no escopo versionado.")

    tqr_adicionada = False
    if DOC_REVIEW_NOITE.exists():
        texto_review = _ler_texto(DOC_REVIEW_NOITE)
        data_review = re.search(
            r"# Diário do modo noturno — (?P<data>\d{4}-\d{2}-\d{2})", texto_review
        )
        re_review_tqr = re.search(
            r"\*\*Cluster TQR\*\*: [\d.]+ nós, (?P<trechos>[\d.]+) trechos "
            r"\([\d,]+ km\), (?P<chaves>\d+) chaves, (?P<ties>\d+) ties.*?, "
            r"(?P<trafos>\d+) trafos, (?P<clientes>[\d.]+) UCBT",
            texto_review,
            re.S,
        )
        if re_review_tqr:
            linhas.append(
                LinhaTabela(
                    nome="Taquara",
                    alimentadores=3,
                    trechos=int(re_review_tqr.group("trechos").replace(".", "")),
                    chaves=int(re_review_tqr.group("chaves")),
                    ties_campo=int(re_review_tqr.group("ties")),
                    clientes=f"{re_review_tqr.group('clientes')} UCBT",
                    fonte=(
                        f"{_fonte_relativa(DOC_REVIEW_NOITE)} "
                        f"({data_review.group('data') if data_review else 'sem data explícita'})"
                    ),
                )
            )
            tqr_adicionada = True
    if not tqr_adicionada:
        re_tqr = re.search(
            r"Números no cluster TQR .*?: (?P<nos>[\d.]+) nós, (?P<trechos>[\d.]+) trechos "
            r"\((?P<km>[\d,]+) km\), (?P<chaves>\d+)\s+chaves, (?P<ties>\d+) ties.*?"
            r"(?P<clientes>[\d.]+) UCBT",
            texto_grid,
            re.S,
        )
        if re_tqr:
            linhas.append(
                LinhaTabela(
                    nome="Taquara",
                    alimentadores=3,
                    trechos=int(re_tqr.group("trechos").replace(".", "")),
                    chaves=int(re_tqr.group("chaves")),
                    ties_campo=int(re_tqr.group("ties")),
                    clientes=f"{re_tqr.group('clientes')} UCBT",
                    fonte=(
                        f"{_fonte_relativa(doc_grid)} (sem data explícita; números do cluster TQR "
                        "versionados no documento)"
                    ),
                )
            )
            tqr_adicionada = True
    if not tqr_adicionada:
        avisos.append(
            "Taquara: não encontrei os números do cluster TQR na documentação versionada."
        )

    linhas.sort(key=lambda item: item.nome)
    return linhas, avisos


def extrair_em_sub(doc_escopo: Path) -> list[dict[str, str]]:
    texto = _ler_texto(doc_escopo)
    linhas: list[dict[str, str]] = []
    fonte_escopo = (
        f"{_fonte_relativa(doc_escopo)} (análise 2026-09-10; inventário regerado em 2026-09-11)"
    )
    resumo = re.search(
        r"município perdeu (?P<tlcd_perda>\d+) "
        r".*?\((?P<tlcd_antes>[\d.]+) → (?P<tlcd_depois>[\d.]+)\) "
        r"e (?P<campo_perda>[\d.]+) ties de campo\s*"
        r"\((?P<campo_antes>[\d.]+) → (?P<campo_depois>[\d.]+)\), "
        r"reclassificadas como de SE \((?P<se_antes>[\d.]+) → (?P<se_depois>[\d.]+)\); "
        r"na Light toda foram (?P<light_delta>[\d.]+) chaves "
        r"\((?P<light_antes>[\d.]+) → (?P<light_depois>[\d.]+)\s+em SE\), "
        r"em (?P<alimentadores>[\d.]+) alimentadores",
        texto,
        re.S,
    )
    if resumo:
        linhas.append(
            {
                "escopo": "Município do Rio — ties TLCD de campo",
                "antes": resumo.group("tlcd_antes"),
                "depois": resumo.group("tlcd_depois"),
                "delta": f"-{resumo.group('tlcd_perda')}",
                "fonte": fonte_escopo,
            }
        )
        linhas.append(
            {
                "escopo": "Município do Rio — ties de campo totais",
                "antes": resumo.group("campo_antes"),
                "depois": resumo.group("campo_depois"),
                "delta": f"-{resumo.group('campo_perda')}",
                "fonte": fonte_escopo,
            }
        )
        delta_se = int(resumo.group("se_depois").replace(".", "")) - int(
            resumo.group("se_antes").replace(".", "")
        )
        linhas.append(
            {
                "escopo": "Município do Rio — ties em SE",
                "antes": resumo.group("se_antes"),
                "depois": resumo.group("se_depois"),
                "delta": f"+{delta_se}",
                "fonte": fonte_escopo,
            }
        )
        linhas.append(
            {
                "escopo": "Light inteira — chaves em SE",
                "antes": resumo.group("light_antes"),
                "depois": resumo.group("light_depois"),
                "delta": (
                    f"+{resumo.group('light_delta')} em "
                    f"{resumo.group('alimentadores')} alimentadores"
                ),
                "fonte": fonte_escopo,
            }
        )
    return linhas


def extrair_cenarios(doc_agent: Path) -> list[LinhaFonteDoc]:
    if not doc_agent.exists():
        return []
    texto = _ler_texto(doc_agent)
    data_match = re.search(r"## Validação com modelos reais \((?P<data>\d{4}-\d{2}-\d{2})\)", texto)
    data = data_match.group("data") if data_match else "sem data explícita"
    linhas: list[LinhaFonteDoc] = []
    padrao = re.compile(
        r"^\| `(?P<cenario>[^`]+)`(?P<cauda>[^|]*) \| [^|]+ \| (?P<proposta>[^|]+) \| "
        r"(?P<verificador>[^|]+) \| (?P<rodadas>[^|]+) \| (?P<tokens>[^|]+) \| "
        r"(?P<tempo>[^|]+) \|$",
        re.M,
    )
    for match in padrao.finditer(texto):
        cauda = match.group("cauda")
        provider = "OpenAI" if "OpenAI" in cauda else "Gemini"
        linhas.append(
            LinhaFonteDoc(
                cenario=match.group("cenario").strip(),
                provider=provider,
                proposta=match.group("proposta").strip(),
                verificador=match.group("verificador").strip(),
                rodadas=match.group("rodadas").strip(),
                tokens_total=match.group("tokens").strip(),
                tempo=match.group("tempo").strip(),
                fonte=f"{_fonte_relativa(doc_agent)} ({data})",
            )
        )
    return linhas


def extrair_total_tarefas(doc_bench: Path) -> tuple[int | None, str | None]:
    if not doc_bench.exists():
        return None, None
    texto = _ler_texto(doc_bench)
    match_total = re.search(r"(\d+) tarefas \(10 \*simple\*", texto)
    match_data = re.search(r"## Resultados \((\d{4}-\d{2}-\d{2})", texto)
    if not match_total:
        return None, None
    return int(match_total.group(1)), match_data.group(1) if match_data else None


def renderizar_resultados(
    *,
    bench_dir: Path,
    doc_bench: Path,
    doc_escopo: Path,
    doc_mcp: Path,
    doc_grid: Path,
    doc_agent: Path,
) -> str:
    resumos = coletar_resumos(bench_dir)
    latest = ultimos_por_familia(resumos)
    comparacoes_exemplos = pares_ab(resumos, sufixo="sem-exemplos")
    comparacoes_compactacao = pares_ab(resumos, sufixo="sem-compactar")
    recortes, avisos_recorte = extrair_recortes(doc_escopo, doc_mcp, doc_grid)
    em_sub = extrair_em_sub(doc_escopo)
    cenarios = extrair_cenarios(doc_agent)
    total_tarefas, data_tarefas = extrair_total_tarefas(doc_bench)

    datas = {resumo.data_arquivo for resumo in resumos if resumo.data_arquivo}
    if data_tarefas:
        datas.add(data_tarefas)
    data_base = max(datas) if datas else "sem data explícita"

    linhas: list[str] = [
        "# Resultados consolidados",
        "",
        "Documento gerado deterministicamente por `uv run python scripts/gerar_resultados.py`.",
        f"Data-base das fontes versionadas mais recentes: **{data_base}**.",
        "",
        "## Escopo das fontes",
        "",
        "| item | valor | fonte |",
        "|---|---:|---|",
    ]
    if total_tarefas is not None:
        linhas.append(
            f"| tarefas catalogadas no benchmark | {total_tarefas} | "
            f"{_fonte_relativa(doc_bench)} ({data_tarefas or 'sem data explícita'}) |"
        )
    linhas.append(
        f"| CSVs lidos em `docs/bench/` | {len(resumos)} | {_fonte_relativa(bench_dir)}/ |"
    )
    linhas += [
        "",
        "## Recortes e cenários usados pelos benchmarks",
        "",
        "| cenário | alimentadores | trechos MT | chaves | ties de campo | clientes | fonte |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for linha in recortes:
        trechos = "—" if linha.trechos is None else _pt_num(linha.trechos, 0)
        partes = [
            linha.nome,
            str(linha.alimentadores),
            trechos,
            str(linha.chaves),
            str(linha.ties_campo),
            linha.clientes,
            linha.fonte,
        ]
        linhas.append("| " + " | ".join(partes) + " |")
    if avisos_recorte:
        linhas += ["", "Notas de rastreabilidade:"]
        linhas += [f"- {aviso}" for aviso in avisos_recorte]

    linhas += [
        "",
        "## Efeito da folga `EM_SUB` nas interligações",
        "",
        "| escopo | antes | depois | delta | fonte |",
        "|---|---:|---:|---:|---|",
    ]
    for linha in em_sub:
        linhas.append(
            f"| {linha['escopo']} | {linha['antes']} | {linha['depois']} | {linha['delta']} | "
            f"{linha['fonte']} |"
        )

    linhas += [
        "",
        "## Benchmarks consolidados por arquivo mais recente de cada família",
        "",
        "Nas colunas **ordem** e **precisão**, a fração entre parênteses agrega passos "
        "(LCS/passos da referência ou chamadas totais) para dar a escala do percentual.",
        "",
        "| família | modo | modelo | tarefas | execuções | k efetivo | pass@1 simple | "
        "pass@1 medium | pass@1 hard | pass@k total | ordem | precisão | "
        "ferr. desnec./exec. | tokens/exec. | US$/exec. | s/exec. | fonte |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for resumo in latest:
        total = _dados_nivel(resumo, "total")
        partes = [
            resumo.familia,
            resumo.modo,
            resumo.modelo or "—",
            str(resumo.tarefas),
            str(resumo.execucoes),
            str(resumo.k_efetivo),
            _pt_pct(_dados_nivel(resumo, "simple").get("pass@1")),
            _pt_pct(_dados_nivel(resumo, "medium").get("pass@1")),
            _pt_pct(_dados_nivel(resumo, "hard").get("pass@1")),
            _pt_pct(total.get(f"pass@{resumo.k_efetivo}")),
            _pt_pct_fracao(total.get("ordem"), total.get("ordem_passos"), total.get("ordem_total")),
            _pt_pct_fracao(
                total.get("precisao"),
                total.get("precisao_passos"),
                total.get("precisao_total"),
            ),
            _pt_num(total.get("desnecessarias"), 2),
            _pt_num(total.get("tokens"), 0),
            _pt_usd(total.get("usd")),
            _pt_num(total.get("segundos")),
            resumo.fonte,
        ]
        linhas.append("| " + " | ".join(partes) + " |")

    linhas += [
        "",
        "## Comparação A/B — exemplos anotados",
        "",
        "| família | braço | execuções | pass@1 total | ordem | precisão | ferr. desnec./exec. | "
        "tokens/exec. | US$/exec. | fonte |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for controle, variante in comparacoes_exemplos:
        for rotulo, resumo in (("com exemplos", controle), ("sem exemplos", variante)):
            total = _dados_nivel(resumo, "total")
            partes = [
                resumo.familia,
                rotulo,
                str(resumo.execucoes),
                _pt_pct(total.get("pass@1")),
                _pt_pct_fracao(
                    total.get("ordem"), total.get("ordem_passos"), total.get("ordem_total")
                ),
                _pt_pct_fracao(
                    total.get("precisao"),
                    total.get("precisao_passos"),
                    total.get("precisao_total"),
                ),
                _pt_num(total.get("desnecessarias"), 2),
                _pt_num(total.get("tokens"), 0),
                _pt_usd(total.get("usd")),
                resumo.fonte,
            ]
            linhas.append("| " + " | ".join(partes) + " |")
    if not comparacoes_exemplos:
        linhas.append("| — | — | 0 | — | — | — | — | — | — | — |")

    linhas += [
        "",
        "## Comparação A/B — compactação das respostas de ferramenta",
        "",
        "| família | braço | execuções | pass@1 total | precisão | chars ferr./exec. | "
        "tokens/exec. | US$/exec. | fonte |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for controle, variante in comparacoes_compactacao:
        for rotulo, resumo in (("compactado", controle), ("sem compactação", variante)):
            total = _dados_nivel(resumo, "total")
            partes = [
                resumo.familia,
                rotulo,
                str(resumo.execucoes),
                _pt_pct(total.get("pass@1")),
                _pt_pct_fracao(
                    total.get("precisao"),
                    total.get("precisao_passos"),
                    total.get("precisao_total"),
                ),
                _pt_num(total.get("chars"), 0),
                _pt_num(total.get("tokens"), 0),
                _pt_usd(total.get("usd")),
                resumo.fonte,
            ]
            linhas.append("| " + " | ".join(partes) + " |")
    if not comparacoes_compactacao:
        linhas.append("| — | — | 0 | — | — | — | — | — | — |")

    linhas += [
        "",
        "## Taxa de reprovação do verificador nos CSVs mais recentes",
        "",
        "| família | modo | execuções com recusa | recusas totais | média de recusas/exec. | "
        "fonte |",
        "|---|---|---:|---:|---:|---|",
    ]
    for resumo in latest:
        media = resumo.recusas_total / resumo.execucoes if resumo.execucoes else 0.0
        partes = [
            resumo.familia,
            resumo.modo,
            _ratio(resumo.recusas_exec, resumo.execucoes),
            str(resumo.recusas_total),
            _pt_num(media, 2),
            resumo.fonte,
        ]
        linhas.append("| " + " | ".join(partes) + " |")

    linhas += [
        "",
        "## Cenários ponta a ponta já versionados",
        "",
        "| cenário | provedor | proposta final | verificador | rodadas | tokens totais | "
        "LLM / ferramentas | fonte |",
        "|---|---|---|---|---:|---|---|---|",
    ]
    for linha in cenarios:
        linhas.append(
            f"| {linha.cenario} | {linha.provider} | {linha.proposta} | {linha.verificador} | "
            f"{linha.rodadas} | {linha.tokens_total} | {linha.tempo} | {linha.fonte} |"
        )
    if not cenarios:
        linhas.append("| — | — | — | — | — | — | — | — |")

    linhas += [
        "",
        "## Limitações conhecidas",
        "",
        "- Este consolidado só usa números encontrados em arquivos versionados; onde a "
        "documentação não expõe um valor estruturado, o campo fica em branco em vez de "
        "ser inferido.",
        "- Os CSVs gerais de 2026-09-11 ainda cobrem a suíte-base de 34 tarefas; as 4 "
        "tarefas hard+ (H12–H15) aparecem nos arquivos dedicados "
        "`openai-hardplus-k3*`, mantendo a rastreabilidade sem misturar execuções "
        "heterogêneas.",
    ]
    return "\n".join(linhas).strip() + "\n"


def gerar_resultados(
    *,
    bench_dir: Path = DOCS_BENCH,
    doc_bench: Path = DOC_BENCH,
    doc_escopo: Path = DOC_ESCOPO,
    doc_mcp: Path = DOC_MCP,
    doc_grid: Path = DOC_GRID,
    doc_agent: Path = DOC_AGENT,
    saida: Path = DESTINO,
) -> Path:
    texto = renderizar_resultados(
        bench_dir=bench_dir,
        doc_bench=doc_bench,
        doc_escopo=doc_escopo,
        doc_mcp=doc_mcp,
        doc_grid=doc_grid,
        doc_agent=doc_agent,
    )
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(texto, encoding="utf-8")
    return saida


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench-dir", type=Path, default=DOCS_BENCH)
    parser.add_argument("--bench-doc", type=Path, default=DOC_BENCH)
    parser.add_argument("--escopo-doc", type=Path, default=DOC_ESCOPO)
    parser.add_argument("--mcp-doc", type=Path, default=DOC_MCP)
    parser.add_argument("--grid-doc", type=Path, default=DOC_GRID)
    parser.add_argument("--agent-doc", type=Path, default=DOC_AGENT)
    parser.add_argument("--saida", type=Path, default=DESTINO)
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    gerar_resultados(
        bench_dir=args.bench_dir,
        doc_bench=args.bench_doc,
        doc_escopo=args.escopo_doc,
        doc_mcp=args.mcp_doc,
        doc_grid=args.grid_doc,
        doc_agent=args.agent_doc,
        saida=args.saida,
    )


if __name__ == "__main__":
    main()
