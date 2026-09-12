"""Prepara o benchmark da issue #92 em alimentadores fora dos clusters da demo.

Fluxo:

1. lê o CSV de generalização da issue #91;
2. filtra os CTMTs cujo pipeline chegou em ``restore_options`` com sucesso;
3. seleciona deterministicamente os ``n`` primeiros pela ``ordem_sorteio``;
4. materializa os recortes (CTMT principal + vizinhos diretos do inventário);
5. recalcula o gabarito via ``restore_options(score=true)`` para escrever um YAML de tarefas
   ``hard`` sem nenhum valor anotado à mão.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from rich.console import Console

from bdgd_light.bench import Gabarito, Tarefa
from bdgd_light.generalizacao import carregar_inventario
from bdgd_light.ingest.recorte import nome_cluster, recortar
from bdgd_light.mcp_server.sessao import SessaoCOD

GENERALIZACAO_PADRAO = Path("docs/bench/2026-09-11-generalizacao.csv")
INVENTARIO_PADRAO = Path("data/inventario_ctmt.csv")
PARQUET_PADRAO = Path("data/parquet")
WORKDIR_PADRAO = Path("scratch/issue-92-fora-treino")
TAREFAS_PADRAO = Path("bench/tarefas_fora_treino.yaml")
CASOS_PADRAO = Path("docs/bench/2026-09-11-fora-treino-casos.csv")


@dataclass(frozen=True)
class CasoForaTreino:
    ordem_sorteio: int
    ctmt: str
    regiao: str
    porte: str
    n_trechos: int
    trecho_falta: str
    n_ties: int
    n_opcoes: int
    score_viaveis: int
    vizinhos: tuple[str, ...]
    cluster: str
    esperado: tuple[str, ...] = ()

    @property
    def ctmts_cluster(self) -> tuple[str, ...]:
        return (self.ctmt, *self.vizinhos)


class ForaTreinoError(RuntimeError):
    """Erro de leitura ou preparação do benchmark fora do treino."""


def _para_int(valor: str | None) -> int:
    if valor in (None, ""):
        return 0
    return int(float(valor))


def _vizinhos_por_ctmt(inventario_csv: Path | str) -> dict[str, tuple[str, ...]]:
    inventario = carregar_inventario(inventario_csv)
    saida: dict[str, tuple[str, ...]] = {}
    for item in inventario.itertuples(index=False):
        ctmt = str(item.COD_ID)
        bruto = getattr(item, "vizinhos", "")
        texto = str(bruto or "").strip()
        if texto.lower() == "nan":
            texto = ""
        vizinhos = tuple(v for v in texto.split(";") if v)
        saida[ctmt] = vizinhos
    return saida


def carregar_casos_generalizacao(
    generalizacao_csv: Path | str = GENERALIZACAO_PADRAO,
    inventario_csv: Path | str = INVENTARIO_PADRAO,
) -> list[CasoForaTreino]:
    """Casos elegíveis: etapa ``restore_options`` com ``status=sucesso``."""
    vizinhos = _vizinhos_por_ctmt(inventario_csv)
    casos: list[CasoForaTreino] = []
    with Path(generalizacao_csv).open(encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            if linha.get("etapa") != "restore_options" or linha.get("status") != "sucesso":
                continue
            ctmt = str(linha["ctmt"])
            cluster = "-".join((ctmt, *vizinhos.get(ctmt, ())))
            casos.append(
                CasoForaTreino(
                    ordem_sorteio=_para_int(linha.get("ordem_sorteio")),
                    ctmt=ctmt,
                    regiao=str(linha.get("regiao") or ""),
                    porte=str(linha.get("porte") or ""),
                    n_trechos=_para_int(linha.get("n_trechos")),
                    trecho_falta=str(linha.get("trecho_falta") or ""),
                    n_ties=_para_int(linha.get("n_ties")),
                    n_opcoes=_para_int(linha.get("n_opcoes")),
                    score_viaveis=_para_int(linha.get("score_viaveis")),
                    vizinhos=vizinhos.get(ctmt, ()),
                    cluster=cluster,
                )
            )
    if not casos:
        raise ForaTreinoError(
            f"nenhum caso elegível em {generalizacao_csv} (esperado restore_options/sucesso)"
        )
    return sorted(casos, key=lambda caso: (caso.ordem_sorteio, caso.ctmt))


def selecionar_casos(casos: list[CasoForaTreino], n: int = 10) -> list[CasoForaTreino]:
    """Escolha honesta: os ``n`` primeiros CTMTs do sorteio determinístico da issue #91."""
    if n <= 0:
        raise ForaTreinoError("n precisa ser positivo")
    if len(casos) < n:
        raise ForaTreinoError(f"só há {len(casos)} caso(s) elegível(is), mas n={n}")
    return list(sorted(casos, key=lambda caso: (caso.ordem_sorteio, caso.ctmt))[:n])


def materializar_clusters(
    casos: list[CasoForaTreino],
    *,
    parquet_dir: Path | str = PARQUET_PADRAO,
    feeders_dir: Path | str,
    console: Console | None = None,
) -> list[Path]:
    """Recorta os clusters necessários para o benchmark reutilizando o pipeline real."""
    console = console or Console(quiet=True)
    parquet_dir = Path(parquet_dir)
    feeders_dir = Path(feeders_dir)
    feeders_dir.mkdir(parents=True, exist_ok=True)
    saida: list[Path] = []
    for caso in casos:
        nome = nome_cluster(caso.ctmts_cluster)
        recorte = recortar(
            parquet_dir,
            caso.ctmts_cluster,
            feeders_dir,
            nome_cluster_=nome,
            console=console,
        )
        gpkg = recorte.cluster.gpkg if recorte.cluster is not None else recorte.recortes[0].gpkg
        if gpkg is None or not Path(gpkg).is_file():
            raise ForaTreinoError(f"recorte de {caso.ctmt} não gerou um GeoPackage utilizável")
        saida.append(Path(gpkg))
    return saida


def _tarefa_de_caso(caso: CasoForaTreino) -> Tarefa:
    descricao = (
        f"Fora do treino (issue #92): {caso.ctmt} em {caso.regiao}, porte {caso.porte}, "
        f"falta determinística no trecho {caso.trecho_falta}; referência recalculada pelas "
        "ferramentas do benchmark."
    )
    return Tarefa(
        id=f"FT{caso.ordem_sorteio:02d}",
        nivel="hard",
        cluster=caso.cluster,
        pergunta=None,
        evento="falta_permanente",
        falta=caso.trecho_falta,
        referencia=("locate_fault", "isolate_fault", "restore_options", "propose_plan"),
        gabarito={
            "ferramenta": "restore_options",
            "argumentos": {"score": True},
            "campo": "melhor_opcao",
        },
        verificar="proposta",
        esperado=list(caso.esperado),
        descricao=descricao,
    )


def recalcular_esperados(
    casos: list[CasoForaTreino],
    *,
    feeders_dir: Path | str,
    dss_out: Path | str,
    estado_dir: Path | str,
    dia: str = "DU",
    mes: int = 1,
) -> list[CasoForaTreino]:
    """Recalcula o gabarito real via ``restore_options(score=true)``."""
    sessao = SessaoCOD(
        feeders=Path(feeders_dir),
        dss_out=Path(dss_out),
        estado_dir=Path(estado_dir),
        dia=dia,
        mes=mes,
    )
    gab = Gabarito(sessao, Path(feeders_dir))
    saida: list[CasoForaTreino] = []
    for caso in casos:
        esperado = gab.esperado(_tarefa_de_caso(caso))
        if not isinstance(esperado, list):
            raise ForaTreinoError(f"gabarito inesperado para {caso.ctmt}: {esperado!r}")
        saida.append(replace(caso, esperado=tuple(map(str, esperado))))
    return saida


def escrever_casos_csv(casos: list[CasoForaTreino], caminho: Path | str = CASOS_PADRAO) -> Path:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    colunas = [
        "ordem_sorteio",
        "ctmt",
        "regiao",
        "porte",
        "n_trechos",
        "trecho_falta",
        "n_ties",
        "n_opcoes",
        "score_viaveis",
        "vizinhos",
        "cluster",
        "esperado",
    ]
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=colunas)
        writer.writeheader()
        for caso in casos:
            linha = asdict(caso)
            linha["vizinhos"] = ";".join(caso.vizinhos)
            linha["esperado"] = ";".join(caso.esperado)
            writer.writerow({coluna: linha[coluna] for coluna in colunas})
    return caminho


def escrever_tarefas_yaml(
    casos: list[CasoForaTreino], caminho: Path | str = TAREFAS_PADRAO
) -> Path:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise ForaTreinoError(f"{exc} — instale o extra: uv sync --extra agent") from exc
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    documento = {
        "versao": 1,
        "origem": "issue-92-fora-treino",
        "tarefas": [_yaml_tarefa(_tarefa_de_caso(caso)) for caso in casos],
    }
    caminho.write_text(
        yaml.safe_dump(documento, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return caminho


def _yaml_tarefa(tarefa: Tarefa) -> dict[str, Any]:
    return {
        "id": tarefa.id,
        "nivel": tarefa.nivel,
        "cluster": tarefa.cluster,
        "evento": tarefa.evento,
        "falta": tarefa.falta,
        "descricao": tarefa.descricao,
        "referencia": list(tarefa.referencia),
        "gabarito": dict(tarefa.gabarito),
        "verificar": tarefa.verificar,
        "esperado": list(tarefa.esperado or []),
    }


def preparar_benchmark_fora_treino(
    *,
    generalizacao_csv: Path | str = GENERALIZACAO_PADRAO,
    inventario_csv: Path | str = INVENTARIO_PADRAO,
    parquet_dir: Path | str = PARQUET_PADRAO,
    feeders_dir: Path | str = WORKDIR_PADRAO / "feeders",
    dss_out: Path | str = WORKDIR_PADRAO / "dss",
    estado_dir: Path | str = WORKDIR_PADRAO / "estado",
    tarefas_out: Path | str = TAREFAS_PADRAO,
    casos_out: Path | str = CASOS_PADRAO,
    n: int = 10,
    dia: str = "DU",
    mes: int = 1,
    console: Console | None = None,
) -> list[CasoForaTreino]:
    """Prepara recortes, recalcula gabaritos e escreve os artefatos versionáveis da issue #92."""
    console = console or Console(quiet=True)
    casos = selecionar_casos(
        carregar_casos_generalizacao(generalizacao_csv, inventario_csv),
        n=n,
    )
    materializar_clusters(casos, parquet_dir=parquet_dir, feeders_dir=feeders_dir, console=console)
    completos = recalcular_esperados(
        casos,
        feeders_dir=feeders_dir,
        dss_out=dss_out,
        estado_dir=estado_dir,
        dia=dia,
        mes=mes,
    )
    escrever_casos_csv(completos, casos_out)
    escrever_tarefas_yaml(completos, tarefas_out)
    return completos
