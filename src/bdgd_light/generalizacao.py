"""Generalização do pipeline em alimentadores nunca vistos (issue #91).

A partir do inventário, sorteia uma amostra determinística estratificada por região e porte
(número de trechos SSDMT) e executa o pipeline completo, sem ajuste manual, em cada CTMT:
recorte → grafo → gpkg2dss → fluxo base → detecção de ties → injeção de falta no maior trecho do
tronco → restore_options(score=true).

Quando o alimentador sorteado tem vizinhos por tie, o recorte e o gêmeo incluem automaticamente o
CTMT principal e seus vizinhos diretos, para que ``restore_options(score=true)`` consiga avaliar a
transferência de carga no cluster necessário sem ajuste manual.
"""

from __future__ import annotations

import math
import random
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd
from rich.console import Console

from bdgd_light.grid import Cluster, Feeder, Rede
from bdgd_light.ingest.parquet import DiretorioParquet
from bdgd_light.ingest.recorte import recortar
from bdgd_light.mcp_server.sessao import SessaoCOD
from bdgd_light.twin import preparar_master_cluster, run_powerflow, trechos_tronco

MUN_RIO = "3304557"
SEMENTE_PADRAO = 91
N_AMOSTRA_PADRAO = 30
ETAPAS = [
    "recorte",
    "grafo",
    "gpkg2dss",
    "fluxo_base",
    "deteccao_ties",
    "injecao_falta",
    "restore_options",
]
COLUNAS_RESULTADO = [
    "ctmt",
    "ordem_sorteio",
    "seed",
    "regiao",
    "porte",
    "n_trechos",
    "etapa",
    "status",
    "duracao_s",
    "motivo",
    "resumo",
    "n_ties",
    "n_opcoes",
    "score_viaveis",
    "trecho_falta",
]
_REFERENCIAS: list[tuple[str, float, float, float]] = [
    ("Centro", -22.905, -43.182, 1.8),
    ("Lapa/Glória", -22.917, -43.178, 1.0),
    ("Flamengo/Catete", -22.932, -43.176, 1.0),
    ("Laranjeiras/Cosme Velho", -22.937, -43.195, 1.2),
    ("Botafogo/Humaitá", -22.953, -43.188, 1.5),
    ("Copacabana/Leme", -22.970, -43.184, 1.6),
    ("Ipanema/Leblon", -22.984, -43.203, 1.4),
    ("Ipanema/Leblon", -22.984, -43.224, 1.4),
    ("Tijuca", -22.925, -43.235, 2.0),
    ("Vila Isabel/Grajaú", -22.917, -43.255, 1.8),
    ("Méier", -22.902, -43.280, 2.5),
    ("Jacarepaguá/Taquara", -22.925, -43.375, 3.5),
    ("Barra/Recreio", -23.003, -43.350, 4.0),
    ("Barra/Recreio", -23.022, -43.460, 4.0),
]
_LABELS_PORTE = ["P", "M", "G"]


@dataclass(frozen=True)
class ConfiguracaoGeneralizacao:
    inventario_csv: Path
    parquet_dir: Path
    workdir: Path
    out_csv: Path
    n: int = N_AMOSTRA_PADRAO
    seed: int = SEMENTE_PADRAO
    dia: str = "DU"
    mes: int = 1
    limpar_workdir: bool = True


@dataclass(frozen=True)
class ContextoExecucao:
    ctmt: str
    parquet_dir: Path
    workdir: Path
    dia: str
    mes: int
    vizinhos: tuple[str, ...] = ()


@dataclass
class EstadoPipeline:
    ctmts_cluster: list[str]
    gpkg: Path | None = None
    rede: Rede | None = None
    master_base: Path | None = None
    n_ties: int | None = None
    trecho_falta: str | None = None
    n_opcoes: int | None = None
    score_viaveis: int | None = None


class GeneralizacaoError(RuntimeError):
    """Erro de configuração ou de entrada da rodada de generalização."""


class EtapaPipelineError(RuntimeError):
    """Falha lógica de uma etapa do pipeline."""


class FalhaEtapa(RuntimeError):
    """Falha explicitamente atribuída a uma etapa; útil para testes/mocks."""

    def __init__(
        self,
        etapa: str,
        motivo: str,
        parciais: dict[str, dict[str, Any]] | None = None,
    ):
        super().__init__(motivo)
        self.etapa = etapa
        self.motivo = motivo
        self.parciais = parciais or {}


def carregar_inventario(caminho: str | Path) -> pd.DataFrame:
    caminho = Path(caminho)
    if not caminho.is_file():
        raise FileNotFoundError(f"inventário não encontrado: {caminho}")
    inventario = pd.read_csv(
        caminho,
        dtype={"COD_ID": str, "MUN": str, "TEN_NOM": str, "SUB": str},
    )
    colunas = {"COD_ID", "MUN", "lat_min", "lat_max", "lon_min", "lon_max"}
    faltando = sorted(colunas - set(inventario.columns))
    if faltando:
        raise GeneralizacaoError(
            f"inventário {caminho} não tem as colunas obrigatórias: {', '.join(faltando)}"
        )
    return inventario


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dy = (lat2 - lat1) * 111.32
    dx = (lon2 - lon1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def classificar_regioes(inventario: pd.DataFrame) -> pd.Series:
    """Região de referência de cada CTMT do município do Rio; fora dos raios fica ``None``."""
    lat = (inventario["lat_min"] + inventario["lat_max"]) / 2
    lon = (inventario["lon_min"] + inventario["lon_max"]) / 2
    regioes: list[str | None] = []
    for y, x in zip(lat, lon, strict=True):
        melhor, menor = None, math.inf
        if pd.isna(y) or pd.isna(x):
            regioes.append(None)
            continue
        for regiao, ry, rx, raio in _REFERENCIAS:
            distancia = distancia_km(float(y), float(x), ry, rx)
            if distancia <= raio and distancia < menor:
                melhor, menor = regiao, distancia
        regioes.append(melhor)
    return pd.Series(regioes, index=inventario.index, dtype="object")


def contar_trechos_por_ctmt(parquet_dir: str | Path) -> pd.Series:
    fonte = DiretorioParquet(parquet_dir)
    ssdmt = fonte.ler("SSDMT", ["CTMT"])
    contagem = ssdmt.groupby("CTMT").size()
    contagem.index = contagem.index.astype(str)
    return contagem.astype("int64")


def classificar_porte(n_trechos: pd.Series) -> pd.Series:
    """Estratos de porte por quantis do número de trechos; empates preservam estabilidade."""
    if n_trechos.empty:
        return pd.Series(dtype="object")
    validos = n_trechos.fillna(0).astype(float)
    n_bins = min(len(_LABELS_PORTE), validos.nunique())
    if n_bins <= 1:
        return pd.Series([_LABELS_PORTE[0]] * len(validos), index=validos.index, dtype="object")
    ranks = validos.rank(method="first")
    categorias = pd.qcut(ranks, q=n_bins, labels=_LABELS_PORTE[:n_bins])
    return categorias.astype("string").astype("object")


def preparar_universo(inventario: pd.DataFrame, n_trechos: pd.Series) -> pd.DataFrame:
    """Filtra o município do Rio, classifica região/porte e prepara a base do sorteio."""
    base = inventario.copy()
    base = base[base["MUN"] == MUN_RIO].copy()
    base["regiao"] = classificar_regioes(base)
    base = base[base["regiao"].notna()].copy()
    base["n_trechos"] = base["COD_ID"].map(n_trechos).fillna(0).astype("int64")
    base["porte"] = classificar_porte(base["n_trechos"])
    if "vizinhos" not in base.columns:
        base["vizinhos"] = ""
    if base.empty:
        raise GeneralizacaoError("nenhum CTMT elegível no município do Rio com região classificada")
    return base.sort_values(["regiao", "porte", "n_trechos", "COD_ID"]).reset_index(drop=True)


def _alocar_por_estrato(base: pd.DataFrame, n: int) -> dict[tuple[str, str], int]:
    tamanhos = base.groupby(["regiao", "porte"]).size().sort_index()
    total = int(tamanhos.sum())
    if n > total:
        raise GeneralizacaoError(f"amostra pedida ({n}) maior que o universo elegível ({total})")
    quotas = {chave: n * int(tamanho) / total for chave, tamanho in tamanhos.items()}
    alocadas = {
        chave: min(int(math.floor(quota)), int(tamanhos[chave])) for chave, quota in quotas.items()
    }
    restante = n - sum(alocadas.values())
    sobras = sorted(
        (
            quotas[chave] - alocadas[chave],
            int(tamanhos[chave]),
            str(chave[0]),
            str(chave[1]),
        )
        for chave in quotas
        if alocadas[chave] < int(tamanhos[chave])
    )
    while restante > 0:
        if not sobras:
            raise GeneralizacaoError("não foi possível distribuir a amostra entre os estratos")
        _, _, regiao, porte = sobras.pop()
        chave = (regiao, porte)
        alocadas[chave] += 1
        restante -= 1
        if alocadas[chave] < int(tamanhos[chave]):
            sobras.append(
                (
                    quotas[chave] - alocadas[chave],
                    int(tamanhos[chave]),
                    str(chave[0]),
                    str(chave[1]),
                )
            )
            sobras.sort()
    return alocadas


def sortear_alimentadores(
    base: pd.DataFrame,
    n: int = N_AMOSTRA_PADRAO,
    seed: int = SEMENTE_PADRAO,
) -> pd.DataFrame:
    """Sorteio determinístico e estratificado por região × porte."""
    rng = random.Random(seed)
    alocadas = _alocar_por_estrato(base, n)
    escolhidos: list[pd.DataFrame] = []
    for regiao, porte in sorted(alocadas):
        quantidade = alocadas[(regiao, porte)]
        grupo = base[(base["regiao"] == regiao) & (base["porte"] == porte)].copy()
        grupo = grupo.sort_values("COD_ID").reset_index(drop=True)
        grupo["_rand"] = [rng.random() for _ in range(len(grupo))]
        escolhidos.append(grupo.sort_values(["_rand", "COD_ID"]).head(quantidade))
    amostra = pd.concat(escolhidos, ignore_index=True)
    amostra = amostra.sort_values(["_rand", "regiao", "porte", "COD_ID"]).reset_index(drop=True)
    amostra["ordem_sorteio"] = range(1, len(amostra) + 1)
    amostra["seed"] = int(seed)
    return amostra.drop(columns="_rand")


def _lista_vizinhos(valor: Any) -> tuple[str, ...]:
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return ()
    itens = [str(item).strip() for item in str(valor).split(";")]
    return tuple(item for item in itens if item)


def maior_trecho_tronco(rede: Rede, ctmt: str) -> str:
    tronco = trechos_tronco(rede, ctmt)
    if not tronco:
        raise EtapaPipelineError(f"{ctmt}: sem trecho de tronco a jusante da fonte")
    comprimentos = []
    for cod in tronco:
        u, v = rede.trechos[cod]
        comp = float(rede.grafo.edges[u, v].get("comp") or 0.0)
        comprimentos.append((comp, cod))
    comp, cod = max(comprimentos, key=lambda item: (item[0], item[1]))
    if comp <= 0:
        raise EtapaPipelineError(f"{ctmt}: maior trecho do tronco sem comprimento positivo")
    return cod


def _mensagem_erro(exc: BaseException) -> str:
    tipo = type(exc).__name__
    texto = str(exc).strip() or "sem mensagem"
    return f"{tipo}: {texto}"


def _resumo_restore(saida: dict[str, Any]) -> str:
    opcoes = int(saida.get("n_opcoes", 0))
    score = saida.get("score") or {}
    viaveis = int(score.get("viaveis", 0)) if isinstance(score, dict) else 0
    return f"{opcoes} opção(ões), {viaveis} viável(is)"


def _resumo_cluster(ctmts: list[str]) -> str:
    return f"{len(ctmts)} CTMT(s): " + ", ".join(ctmts)


def executar_etapas_reais(
    contexto: ContextoExecucao,
    console: Console | None = None,
) -> dict[str, dict[str, Any]]:
    """Executa as sete etapas do pipeline para um CTMT e devolve um dicionário por etapa."""
    console = console or Console(quiet=True)
    ctmts_cluster = [contexto.ctmt, *contexto.vizinhos]
    estado = EstadoPipeline(ctmts_cluster=ctmts_cluster)
    resultado: dict[str, dict[str, Any]] = {}
    recorte_dir = contexto.workdir / "feeders"
    dss_dir = contexto.workdir / "dss"
    sessao_dir = contexto.workdir / "estado"

    try:
        inicio = perf_counter()
        rodada = recortar(contexto.parquet_dir, estado.ctmts_cluster, recorte_dir, console=console)
        recorte_item = rodada.cluster or rodada.recortes[0]
        assert recorte_item.gpkg is not None
        estado.gpkg = recorte_item.gpkg
        resultado["recorte"] = {
            "status": "sucesso",
            "duracao_s": round(perf_counter() - inicio, 3),
            "resumo": (
                f"{sum(recorte_item.contagens.values())} feições em "
                f"{len(recorte_item.contagens)} camada(s); {_resumo_cluster(ctmts_cluster)}"
            ),
        }

        inicio = perf_counter()
        estado.rede = (
            Feeder.from_gpkg(estado.gpkg)
            if len(ctmts_cluster) == 1
            else Cluster.from_gpkg(estado.gpkg)
        )
        ties = estado.rede.tie_switches()
        ties_ctmt = ties[(ties["ctmt"] == contexto.ctmt) | (ties["ctmt_viz"] == contexto.ctmt)]
        estado.n_ties = len(ties_ctmt)
        resultado["grafo"] = {
            "status": "sucesso",
            "duracao_s": round(perf_counter() - inicio, 3),
            "resumo": (
                f"{len(estado.rede.trechos)} trechos, {len(estado.rede.chaves)} chaves; "
                f"{len(ties_ctmt)} tie(s) ligadas a {contexto.ctmt}"
            ),
            "n_ties": len(ties_ctmt),
        }

        inicio = perf_counter()
        estado.master_base = preparar_master_cluster(
            estado.gpkg,
            estado.ctmts_cluster,
            dss_dir,
            dia=contexto.dia,
            mes=contexto.mes,
        )
        resultado["gpkg2dss"] = {
            "status": "sucesso",
            "duracao_s": round(perf_counter() - inicio, 3),
            "resumo": f"master do cluster em {estado.master_base.name}",
        }

        inicio = perf_counter()
        fluxo = run_powerflow(estado.master_base)
        if not fluxo.convergiu:
            raise EtapaPipelineError(f"fluxo base não convergiu ({len(fluxo.ajustes)} ajuste(s))")
        resultado["fluxo_base"] = {
            "status": "sucesso",
            "duracao_s": round(perf_counter() - inicio, 3),
            "resumo": f"Vmin {fluxo.v_min_pu:.3f} pu, perdas {fluxo.perdas_kw:.1f} kW",
        }

        resultado["deteccao_ties"] = {
            "status": "sucesso",
            "duracao_s": 0.0,
            "resumo": f"{estado.n_ties} tie(s) ligadas a {contexto.ctmt}",
            "n_ties": estado.n_ties,
        }

        sessao = SessaoCOD(
            feeders=recorte_dir,
            dss_out=dss_dir,
            estado_dir=sessao_dir,
            dia=contexto.dia,
            mes=contexto.mes,
        )
        sessao.load_cluster(str(estado.gpkg))

        inicio = perf_counter()
        estado.trecho_falta = maior_trecho_tronco(estado.rede, contexto.ctmt)
        injecao = sessao.inject_fault(estado.trecho_falta)
        resultado["injecao_falta"] = {
            "status": "sucesso",
            "duracao_s": round(perf_counter() - inicio, 3),
            "resumo": f"trecho {estado.trecho_falta}, religador {injecao['religador']}",
            "trecho_falta": estado.trecho_falta,
        }

        inicio = perf_counter()
        saida = sessao.restore_options(score=True)
        estado.n_opcoes = int(saida.get("n_opcoes", 0))
        if estado.n_opcoes > 0 and saida.get("score") is None:
            raise EtapaPipelineError(saida.get("aviso") or "score elétrico indisponível")
        estado.score_viaveis = int((saida.get("score") or {}).get("viaveis", 0))
        resultado["restore_options"] = {
            "status": "sucesso",
            "duracao_s": round(perf_counter() - inicio, 3),
            "resumo": _resumo_restore(saida),
            "n_ties": estado.n_ties,
            "n_opcoes": estado.n_opcoes,
            "score_viaveis": estado.score_viaveis,
            "trecho_falta": estado.trecho_falta,
        }
        return resultado
    except FalhaEtapa:
        raise
    except BaseException as exc:
        etapa = next((nome for nome in ETAPAS if nome not in resultado), ETAPAS[-1])
        raise FalhaEtapa(etapa, _mensagem_erro(exc), parciais=resultado) from exc


def executar_pipeline(
    amostra: pd.DataFrame,
    parquet_dir: str | Path,
    workdir: str | Path,
    *,
    dia: str = "DU",
    mes: int = 1,
    console: Console | None = None,
    executar_etapas=executar_etapas_reais,
) -> pd.DataFrame:
    """Executa a rodada para todos os CTMT sorteados e normaliza o CSV por etapa."""
    console = console or Console(quiet=True)
    parquet_dir = Path(parquet_dir)
    workdir = Path(workdir)
    linhas: list[dict[str, Any]] = []
    for item in amostra.itertuples(index=False):
        contexto = ContextoExecucao(
            ctmt=str(item.COD_ID),
            parquet_dir=parquet_dir,
            workdir=workdir / str(item.COD_ID),
            dia=dia,
            mes=int(mes),
            vizinhos=_lista_vizinhos(getattr(item, "vizinhos", "")),
        )
        contexto.workdir.mkdir(parents=True, exist_ok=True)
        try:
            resultados_ctmt = executar_etapas(contexto, console)
        except FalhaEtapa as exc:
            resultados_ctmt = dict(exc.parciais)
            falhou = False
            for etapa in ETAPAS:
                if etapa == exc.etapa:
                    falhou = True
                    resultados_ctmt[etapa] = {"status": "falha", "motivo": exc.motivo}
                elif falhou:
                    resultados_ctmt[etapa] = {
                        "status": "nao_executada",
                        "motivo": f"dependência anterior falhou ({exc.etapa})",
                    }
        for etapa in ETAPAS:
            dados = resultados_ctmt.get(etapa, {})
            linhas.append(
                {
                    "ctmt": str(item.COD_ID),
                    "ordem_sorteio": int(item.ordem_sorteio),
                    "seed": int(item.seed),
                    "regiao": str(item.regiao),
                    "porte": str(item.porte),
                    "n_trechos": int(item.n_trechos),
                    "etapa": etapa,
                    "status": dados.get("status", "nao_executada"),
                    "duracao_s": float(dados.get("duracao_s", 0.0)),
                    "motivo": dados.get("motivo", ""),
                    "resumo": dados.get("resumo", ""),
                    "n_ties": dados.get("n_ties"),
                    "n_opcoes": dados.get("n_opcoes"),
                    "score_viaveis": dados.get("score_viaveis"),
                    "trecho_falta": dados.get("trecho_falta"),
                }
            )
    return pd.DataFrame(linhas, columns=COLUNAS_RESULTADO)


def resumir_resultados(resultados: pd.DataFrame) -> pd.DataFrame:
    """Tabela por etapa com n, sucesso, falha e motivo mais comum."""
    linhas = []
    for etapa in ETAPAS:
        grupo = resultados[resultados["etapa"] == etapa]
        if grupo.empty:
            continue
        sucesso = int((grupo["status"] == "sucesso").sum())
        falha = int((grupo["status"] != "sucesso").sum())
        motivos = [m for m in grupo.loc[grupo["status"] != "sucesso", "motivo"] if str(m).strip()]
        motivo_comum = Counter(motivos).most_common(1)[0][0] if motivos else ""
        linhas.append(
            {
                "etapa": etapa,
                "n": int(len(grupo)),
                "sucesso": sucesso,
                "falha": falha,
                "taxa_sucesso": round(sucesso / len(grupo), 4),
                "motivo_mais_comum": motivo_comum,
            }
        )
    return pd.DataFrame(linhas)


def agrupar_falhas(resultados: pd.DataFrame) -> pd.DataFrame:
    falhas = resultados[resultados["status"] != "sucesso"].copy()
    if falhas.empty:
        return pd.DataFrame(columns=["etapa", "motivo", "n", "ctmts"])
    agrupado = (
        falhas.groupby(["etapa", "motivo"], dropna=False)
        .agg(n=("ctmt", "size"), ctmts=("ctmt", lambda s: ", ".join(sorted(set(map(str, s))))))
        .reset_index()
        .sort_values(["etapa", "n", "motivo"], ascending=[True, False, True])
    )
    return agrupado


def escrever_csv(resultados: pd.DataFrame, caminho: str | Path) -> Path:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    saida = resultados.copy()
    for coluna in ("n_ties", "n_opcoes", "score_viaveis"):
        saida[coluna] = saida[coluna].astype("Int64")
    saida.to_csv(caminho, index=False)
    return caminho


def executar_generalizacao(
    config: ConfiguracaoGeneralizacao,
    *,
    console: Console | None = None,
    executar_etapas=executar_etapas_reais,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    console = console or Console()
    inventario = carregar_inventario(config.inventario_csv)
    n_trechos = contar_trechos_por_ctmt(config.parquet_dir)
    universo = preparar_universo(inventario, n_trechos)
    amostra = sortear_alimentadores(universo, n=config.n, seed=config.seed)
    if config.limpar_workdir and config.workdir.exists():
        shutil.rmtree(config.workdir)
    config.workdir.mkdir(parents=True, exist_ok=True)
    resultados = executar_pipeline(
        amostra,
        config.parquet_dir,
        config.workdir,
        dia=config.dia,
        mes=config.mes,
        console=Console(quiet=True),
        executar_etapas=executar_etapas,
    )
    escrever_csv(resultados, config.out_csv)
    return amostra, resultados, resumir_resultados(resultados)


def markdown_resumo(resumo: pd.DataFrame, falhas: pd.DataFrame, csv_relativo: str) -> str:
    linhas = [
        "| etapa | n | sucesso | falha | taxa de sucesso | motivo mais comum |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in resumo.itertuples(index=False):
        linhas.append(
            "| "
            + " | ".join(
                [
                    str(r.etapa),
                    str(r.n),
                    str(r.sucesso),
                    str(r.falha),
                    f"{100 * r.taxa_sucesso:.1f}%",
                    str(r.motivo_mais_comum or "—"),
                ]
            )
            + " |"
        )
    if falhas.empty:
        falhas_md = "Nenhuma falha registrada nas etapas executadas."
    else:
        falhas_md = "\n".join(
            [
                "| etapa | falhas | motivo | CTMTs |",
                "|---|---:|---|---|",
                *[
                    f"| {r.etapa} | {r.n} | {r.motivo} | {r.ctmts} |"
                    for r in falhas.itertuples(index=False)
                ],
            ]
        )
    return (
        "### Tabela por etapa\n\n"
        + "\n".join(linhas)
        + "\n\n"
        + f"Falhas detalhadas: [`{csv_relativo}`]({csv_relativo}).\n\n"
        + "### Falhas agrupadas\n\n"
        + falhas_md
    )


def descrever_amostra(amostra: pd.DataFrame) -> str:
    linhas = [
        f"- semente: {int(amostra['seed'].iloc[0])}",
        f"- alimentadores sorteados: {len(amostra)}",
    ]
    por_porte = amostra.groupby("porte").size().to_dict()
    por_regiao = amostra.groupby("regiao").size().to_dict()
    linhas.append("- porte: " + ", ".join(f"{k}={v}" for k, v in sorted(por_porte.items())))
    linhas.append("- regiões: " + ", ".join(f"{k}={v}" for k, v in sorted(por_regiao.items())))
    linhas.append("- CTMTs: " + ", ".join(amostra.sort_values("ordem_sorteio")["COD_ID"].tolist()))
    return "\n".join(linhas)
