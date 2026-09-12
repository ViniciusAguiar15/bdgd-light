"""Varredura de sensibilidade das premissas elétricas da restauração (issue #96)."""

from __future__ import annotations

import copy
import csv
import math
import re
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console

from bdgd_light.gd_restauracao import (
    CENARIOS_ALVO,
    CasoAnalise,
    carregar_rede,
    carregar_vizinhos,
    montar_casos_cenarios,
    preparar_plano_restauracao,
)
from bdgd_light.generalizacao import maior_trecho_tronco
from bdgd_light.ingest.recorte import nome_cluster, recortar
from bdgd_light.twin import montar_master_cluster, score_eletrico
from bdgd_light.twin.gpkg2dss import (
    ANO_PADRAO,
    CONEXAO_CARGA,
    NOS,
    _agrupar_cargas,
    _camadas,
    _Conversor,
    _Curvas,
    _kv,
    _ler,
    _num,
    _por_ctmt,
    _texto,
)

LOADMULTS = (0.6, 0.8, 1.0, 1.2, 1.4)
MODELOS_CARGA = ("curva", "nominal")
MODOS_FAS_CON = ("cadastrado", "rebalanceado")
DIA_PADRAO = "DU"
MES_PADRAO = 1
COLUNAS_RESULTADO = [
    "grupo",
    "caso",
    "descricao",
    "cluster",
    "origem",
    "ctmt_principal",
    "ctmts_cluster",
    "trecho_falta",
    "criterio_falta",
    "modelo_carga",
    "fas_con",
    "loadmult",
    "trocas_fas_con",
    "n_opcoes",
    "n_viaveis",
    "decisao",
    "tipo_decisao",
    "virou_decisao",
    "opcao_score",
    "fonte_score",
    "score_viavel",
    "margem_disjuntor",
    "i_disjuntor_a",
    "i_nominal_a",
    "vmin_mt_pu",
    "vmin_mt_barra",
    "vmax_mt_pu",
    "vmax_mt_barra",
    "carregamento_max_mt_pct",
    "perdas_kw",
    "motivos",
    "ajustes",
]

_RE_BUS = re.compile(r'"(?P<barra>[^".]+)\.(?P<nos>[0-9.]+)"')
_FASE_WYE = {"AN": 1, "BN": 2, "CN": 3, "A": 1, "B": 2, "C": 3, "AX": 1, "BX": 2, "CX": 3}
_FAS_POR_FASE = {1: "AN", 2: "BN", 3: "CN"}


@dataclass(frozen=True)
class ConfiguracaoSensibilidade:
    feeders_dir: Path
    parquet_dir: Path
    inventario_csv: Path
    generalizacao_csv: Path
    workdir: Path
    out_csv: Path
    out_md: Path
    dia: str = DIA_PADRAO
    mes: int = MES_PADRAO


@dataclass(frozen=True)
class CargaSpec:
    arquivo: str
    base_nome: str
    pac: str
    fas_con: str
    fases: int
    conn: str
    kv: float
    daily: str
    ativa: bool
    uni_tr_mt: str
    kw_curva_total: float
    kw_nominal_total: float

    def kw_total(self, modelo_carga: str) -> float:
        if modelo_carga == "nominal":
            return self.kw_nominal_total
        return self.kw_curva_total


@dataclass
class ContextoCtmt:
    ctmt: str
    pasta_base: Path
    cargas_bt: list[CargaSpec]
    cargas_mt: list[CargaSpec]
    fases_por_barra: dict[str, tuple[int, ...]]


@dataclass(frozen=True)
class VarianteCaso:
    master: Path
    trocas_fas_con: int


@dataclass(frozen=True)
class ResumoCaso:
    caso: str
    base: str
    loadmult_atual: str
    carga_nominal: str
    rebalanceamento: str
    conclusao: str


class SensibilidadeError(RuntimeError):
    """Erro de configuração ou de materialização da varredura."""


def selecionar_alimentadores_sensibilidade(caminho_csv: str | Path, *, n: int = 3) -> pd.DataFrame:
    """Escolhe `n` CTMTs da #91 com opções viáveis, priorizando diversidade regional."""
    tabela = pd.read_csv(caminho_csv, dtype={"ctmt": str}).copy()
    tabela["n_opcoes"] = (
        pd.to_numeric(tabela.get("n_opcoes"), errors="coerce").fillna(0).astype(int)
    )
    if "score_viaveis" in tabela.columns:
        tabela["score_viaveis"] = (
            pd.to_numeric(tabela["score_viaveis"], errors="coerce")
            .fillna(tabela["n_opcoes"])
            .astype(int)
        )
    else:
        tabela["score_viaveis"] = tabela["n_opcoes"]
    candidatos = tabela[
        (tabela["etapa"] == "restore_options")
        & (tabela["status"] == "sucesso")
        & (tabela["n_opcoes"] > 0)
        & (tabela["score_viaveis"] > 0)
    ].copy()
    if candidatos.empty:
        raise SensibilidadeError(f"nenhum CTMT elegível em {caminho_csv}")
    candidatos = candidatos.sort_values(
        ["score_viaveis", "n_opcoes", "regiao", "porte", "ctmt"],
        ascending=[False, False, True, True, True],
    ).reset_index(drop=True)
    escolhidos: list[pd.Series] = []
    regioes: set[str] = set()
    for _, linha in candidatos.iterrows():
        regiao = str(linha.get("regiao") or "")
        if regiao and regiao not in regioes:
            escolhidos.append(linha)
            regioes.add(regiao)
        if len(escolhidos) == n:
            break
    if len(escolhidos) < n:
        usados = {str(item["ctmt"]) for item in escolhidos}
        for _, linha in candidatos.iterrows():
            ctmt = str(linha["ctmt"])
            if ctmt in usados:
                continue
            escolhidos.append(linha)
            usados.add(ctmt)
            if len(escolhidos) == n:
                break
    return pd.DataFrame(escolhidos).reset_index(drop=True)


def materializar_casos_sensibilidade(
    config: ConfiguracaoSensibilidade,
    console: Console | None = None,
) -> list[CasoAnalise]:
    """Monta os 3 cenários fixos e 3 alimentadores escolhidos da #91."""
    console = console or Console()
    casos = montar_casos_cenarios(config.feeders_dir)
    selecionados = selecionar_alimentadores_sensibilidade(config.generalizacao_csv)
    vizinhos = carregar_vizinhos(config.inventario_csv)
    for item in selecionados.itertuples(index=False):
        ctmt = str(item.ctmt)
        ctmts_cluster = tuple(dict.fromkeys((ctmt, *vizinhos.get(ctmt, ()))))
        nome = nome_cluster(ctmts_cluster)
        console.print(
            f"[cyan]Recortando caso adicional {ctmt} ({len(ctmts_cluster) - 1} vizinho(s))…[/]"
        )
        rodada = recortar(
            config.parquet_dir,
            ctmts_cluster,
            config.feeders_dir,
            nome_cluster_=nome,
            console=Console(quiet=True),
        )
        gpkg = rodada.cluster.gpkg if rodada.cluster is not None else rodada.recortes[0].gpkg
        if gpkg is None:
            raise SensibilidadeError(f"{ctmt}: recorte não gerou GeoPackage")
        rede = carregar_rede(gpkg)
        casos.append(
            CasoAnalise(
                grupo="alimentador",
                caso=ctmt,
                descricao=(
                    f"amostra #91 — região {item.regiao}, porte {item.porte}, "
                    f"{int(item.n_opcoes)} opção(ões) / {int(item.score_viaveis)} viável(is)"
                ),
                cluster=nome,
                gpkg=Path(gpkg),
                ctmts_cluster=tuple(rede.ctmts),
                ctmt_principal=ctmt,
                trecho_falta=maior_trecho_tronco(rede, ctmt),
                criterio_falta="maior trecho do tronco do CTMT principal",
                origem="issue #91 / docs/bench/2026-09-11-generalizacao.csv",
            )
        )
    return casos


def executar_sensibilidade(
    config: ConfiguracaoSensibilidade,
    *,
    console: Console | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[CasoAnalise]]:
    """Executa a varredura completa e grava CSV + Markdown."""
    console = console or Console()
    config.workdir.mkdir(parents=True, exist_ok=True)
    config.out_csv.parent.mkdir(parents=True, exist_ok=True)
    config.out_md.parent.mkdir(parents=True, exist_ok=True)

    casos = materializar_casos_sensibilidade(config, console=console)
    linhas: list[dict[str, Any]] = []
    resumos: list[ResumoCaso] = []

    for caso in casos:
        console.print(f"[bold cyan]Caso {caso.caso}[/] — preparando variantes…")
        rede = carregar_rede(caso.gpkg)
        plano, opcoes, _ = preparar_plano_restauracao(rede, caso.trecho_falta)
        variantes = preparar_variantes_caso(caso, config, console=console)
        baseline_scores = score_eletrico(opcoes, plano, variantes[("curva", "cadastrado")].master)
        _, baseline = classificar_decisao(
            baseline_scores[0] if baseline_scores else None, n_opcoes=len(opcoes)
        )
        for modelo_carga in MODELOS_CARGA:
            for modo_fas in MODOS_FAS_CON:
                variante = variantes[(modelo_carga, modo_fas)]
                for loadmult in LOADMULTS:
                    comandos = []
                    if float(loadmult) != 1.0:
                        comandos.append(f"set loadmult={float(loadmult):g}")
                    scores = score_eletrico(opcoes, plano, variante.master, comandos_base=comandos)
                    n_viaveis = sum(1 for item in scores if item.viavel)
                    melhor = scores[0] if scores else None
                    tipo_decisao, decisao = classificar_decisao(melhor, n_opcoes=len(opcoes))
                    linhas.append(
                        montar_linha_resultado(
                            caso,
                            variante,
                            modelo_carga=modelo_carga,
                            modo_fas=modo_fas,
                            loadmult=float(loadmult),
                            n_opcoes=len(opcoes),
                            n_viaveis=n_viaveis,
                            baseline=baseline,
                            tipo_decisao=tipo_decisao,
                            decisao=decisao,
                            melhor=melhor,
                        )
                    )
        tabela_caso = pd.DataFrame(
            [
                linha
                for linha in linhas
                if linha["caso"] == caso.caso and linha["grupo"] == caso.grupo
            ]
        )
        resumos.append(resumir_caso(tabela_caso))

    resultados = pd.DataFrame(linhas, columns=COLUNAS_RESULTADO)
    resumo = pd.DataFrame([r.__dict__ for r in resumos])
    resultados.to_csv(config.out_csv, index=False)
    config.out_md.write_text(renderizar_markdown(resultados, resumo, casos), encoding="utf-8")
    return resultados, resumo, casos


def preparar_variantes_caso(
    caso: CasoAnalise,
    config: ConfiguracaoSensibilidade,
    *,
    console: Console | None = None,
) -> dict[tuple[str, str], VarianteCaso]:
    """Gera os Masters do caso para curva/nominal × cadastrado/rebalanceado."""
    console = console or Console()
    base_dir = config.workdir / f"{caso.grupo}_{caso.caso}" / "base"
    if base_dir.exists():
        shutil.rmtree(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    contextos = [
        _preparar_contexto_ctmt(caso.gpkg, ctmt, base_dir, config.dia, config.mes)
        for ctmt in caso.ctmts_cluster
    ]
    variantes: dict[tuple[str, str], VarianteCaso] = {}
    for modelo_carga in MODELOS_CARGA:
        for modo_fas in MODOS_FAS_CON:
            pasta_variante = (
                config.workdir / f"{caso.grupo}_{caso.caso}" / f"{modelo_carga}_{modo_fas}"
            )
            if pasta_variante.exists():
                shutil.rmtree(pasta_variante)
            pasta_variante.mkdir(parents=True, exist_ok=True)
            trocas_total = 0
            pastas_ctmt: list[Path] = []
            for contexto in contextos:
                destino = pasta_variante / contexto.ctmt
                shutil.copytree(contexto.pasta_base, destino)
                cargas_bt = copy.deepcopy(contexto.cargas_bt)
                cargas_mt = copy.deepcopy(contexto.cargas_mt)
                if modo_fas == "rebalanceado":
                    cargas_bt, trocas = rebalancear_fas_con(
                        cargas_bt, contexto.fases_por_barra, modelo_carga
                    )
                    trocas_total += trocas
                _sobrescrever_arquivo_cargas(destino, "CargasBT", cargas_bt, modelo_carga)
                _sobrescrever_arquivo_cargas(destino, "CargasMT", cargas_mt, modelo_carga)
                pastas_ctmt.append(destino)
            nome = f"{caso.cluster}_{modelo_carga}_{modo_fas}"
            master = montar_master_cluster(
                pastas_ctmt,
                pasta_variante
                / f"Master_{config.dia}{config.mes:02d}_{modelo_carga}_{modo_fas}.dss",
                dia=config.dia,
                mes=config.mes,
                nome=nome,
            )
            console.print(
                f"  [green]✔[/] {modelo_carga}/{modo_fas}: "
                f"{trocas_total} troca(s) de fase segura(s)"
            )
            variantes[(modelo_carga, modo_fas)] = VarianteCaso(
                master=master, trocas_fas_con=trocas_total
            )
    return variantes


def rebalancear_fas_con(
    cargas: list[CargaSpec],
    fases_por_barra: dict[str, tuple[int, ...]],
    modelo_carga: str,
) -> tuple[list[CargaSpec], int]:
    """Redistribui cargas 1F Wye só quando há mais de uma fase disponível no PAC."""
    saida = list(cargas)
    carga_por_grupo: dict[tuple[str, int], float] = {}
    trocas = 0
    ordem = sorted(
        range(len(saida)),
        key=lambda pos: (saida[pos].uni_tr_mt, saida[pos].pac, saida[pos].base_nome),
    )
    for pos in ordem:
        carga = saida[pos]
        atual = fase_wye(carga.fas_con)
        permitidas = tuple(sorted(set(fases_por_barra.get(carga.pac, ())) & {1, 2, 3}))
        if not (
            carga.arquivo == "CargasBT"
            and carga.conn == "Wye"
            and carga.fases == 1
            and carga.uni_tr_mt
            and atual is not None
            and len(permitidas) >= 2
        ):
            continue
        grupo = carga.uni_tr_mt
        escolhida = min(
            permitidas,
            key=lambda fase: (carga_por_grupo.get((grupo, fase), 0.0), fase),
        )
        carga_por_grupo[(grupo, escolhida)] = carga_por_grupo.get((grupo, escolhida), 0.0) + max(
            carga.kw_total(modelo_carga), 0.0
        )
        if escolhida == atual:
            continue
        novo = replace(carga, fas_con=_FAS_POR_FASE[escolhida])
        saida[pos] = novo
        trocas += 1
    return saida, trocas


def fase_wye(fas_con: str) -> int | None:
    return _FASE_WYE.get(_texto(fas_con).upper())


def classificar_decisao(melhor, *, n_opcoes: int) -> tuple[str, str]:
    if n_opcoes == 0:
        return "sem_opcoes_topologicas", "sem transferência"
    if melhor is None or not melhor.viavel:
        return "sem_opcao_viavel", "sem transferência"
    return "restaurar", str(melhor.chave)


def montar_linha_resultado(
    caso: CasoAnalise,
    variante: VarianteCaso,
    *,
    modelo_carga: str,
    modo_fas: str,
    loadmult: float,
    n_opcoes: int,
    n_viaveis: int,
    baseline: str,
    tipo_decisao: str,
    decisao: str,
    melhor,
) -> dict[str, Any]:
    melhor_dict = melhor.to_dict() if melhor is not None else {}
    return {
        "grupo": caso.grupo,
        "caso": caso.caso,
        "descricao": caso.descricao,
        "cluster": caso.cluster,
        "origem": caso.origem,
        "ctmt_principal": caso.ctmt_principal,
        "ctmts_cluster": ";".join(caso.ctmts_cluster),
        "trecho_falta": caso.trecho_falta,
        "criterio_falta": caso.criterio_falta,
        "modelo_carga": modelo_carga,
        "fas_con": modo_fas,
        "loadmult": loadmult,
        "trocas_fas_con": variante.trocas_fas_con,
        "n_opcoes": n_opcoes,
        "n_viaveis": n_viaveis,
        "decisao": decisao,
        "tipo_decisao": tipo_decisao,
        "virou_decisao": decisao != baseline,
        "opcao_score": melhor_dict.get("chave"),
        "fonte_score": melhor_dict.get("fonte"),
        "score_viavel": melhor_dict.get("viavel"),
        "margem_disjuntor": melhor_dict.get("margem_disjuntor"),
        "i_disjuntor_a": melhor_dict.get("i_disjuntor_a"),
        "i_nominal_a": melhor_dict.get("i_nominal_a"),
        "vmin_mt_pu": melhor_dict.get("vmin_mt_pu"),
        "vmin_mt_barra": melhor_dict.get("vmin_mt_barra"),
        "vmax_mt_pu": melhor_dict.get("vmax_mt_pu"),
        "vmax_mt_barra": melhor_dict.get("vmax_mt_barra"),
        "carregamento_max_mt_pct": melhor_dict.get("carregamento_max_mt_pct"),
        "perdas_kw": melhor_dict.get("perdas_kw"),
        "motivos": "; ".join(melhor_dict.get("motivos") or []),
        "ajustes": "; ".join(melhor_dict.get("ajustes") or []),
    }


def resumir_caso(resultados_caso: pd.DataFrame) -> ResumoCaso:
    base = resultados_caso[
        (resultados_caso["modelo_carga"] == "curva")
        & (resultados_caso["fas_con"] == "cadastrado")
        & (resultados_caso["loadmult"] == 1.0)
    ].iloc[0]
    atual = _frase_turning_point(
        resultados_caso,
        modelo_carga="curva",
        fas_con="cadastrado",
        rotulo_base=str(base["decisao"]),
        titulo="premissas atuais",
    )
    nominal = _frase_primeira_virada(
        resultados_caso,
        modelo_carga="nominal",
        fas_con="cadastrado",
        trocas_esperadas=False,
        rotulo_base=str(base["decisao"]),
        titulo="carga nominal",
    )
    rebalanceamento = _frase_primeira_virada(
        resultados_caso,
        modelo_carga="curva",
        fas_con="rebalanceado",
        trocas_esperadas=True,
        rotulo_base=str(base["decisao"]),
        titulo="FAS_CON rebalanceado",
    )
    conclusao = sintetizar_conclusao(resultados_caso)
    return ResumoCaso(
        caso=str(base["caso"]),
        base=f"base atual: {base['decisao']} (loadmult 1,0)",
        loadmult_atual=atual,
        carga_nominal=nominal,
        rebalanceamento=rebalanceamento,
        conclusao=conclusao,
    )


def _frase_turning_point(
    resultados: pd.DataFrame,
    *,
    modelo_carga: str,
    fas_con: str,
    rotulo_base: str,
    titulo: str,
) -> str:
    trecho = resultados[
        (resultados["modelo_carga"] == modelo_carga) & (resultados["fas_con"] == fas_con)
    ].copy()
    if trecho.empty:
        return f"{titulo}: sem dados"
    if not bool(trecho["virou_decisao"].any()):
        return f"{titulo}: não vira na faixa testada (0,6–1,4)"
    if _eh_limiar_unico(trecho, rotulo_base):
        mudou = trecho[trecho["virou_decisao"]].sort_values("loadmult")
        primeira = mudou.iloc[0]
        return (
            f"{titulo}: vira em loadmult {fmt_loadmult(primeira['loadmult'])} "
            f"({rotulo_base} → {primeira['decisao']})"
        )
    return f"{titulo}: sem limiar único ({_descrever_segmentos(trecho, rotulo_base)})"


def _frase_primeira_virada(
    resultados: pd.DataFrame,
    *,
    modelo_carga: str,
    fas_con: str,
    trocas_esperadas: bool,
    rotulo_base: str,
    titulo: str,
) -> str:
    trecho = resultados[
        (resultados["modelo_carga"] == modelo_carga) & (resultados["fas_con"] == fas_con)
    ].copy()
    if trocas_esperadas and int(trecho["trocas_fas_con"].max() or 0) == 0:
        return f"{titulo}: rebalanceamento seguro não moveu carga nenhuma neste caso"
    return _frase_turning_point(
        resultados,
        modelo_carga=modelo_carga,
        fas_con=fas_con,
        rotulo_base=rotulo_base,
        titulo=titulo,
    )


def sintetizar_conclusao(resultados: pd.DataFrame) -> str:
    base = resultados[
        (resultados["modelo_carga"] == "curva")
        & (resultados["fas_con"] == "cadastrado")
        & (resultados["loadmult"] == 1.0)
    ].iloc[0]
    atual = resultados[
        (resultados["modelo_carga"] == "curva") & (resultados["fas_con"] == "cadastrado")
    ]
    mudou_atual = atual[atual["virou_decisao"]].sort_values("loadmult")
    if mudou_atual.empty:
        return f"a escolha {base['decisao']} se mantém em toda a faixa 0,6–1,4 nas premissas atuais"
    if not _eh_limiar_unico(atual, str(base["decisao"])):
        return (
            f"não há limiar único nas premissas atuais: "
            f"{_descrever_segmentos(atual, str(base['decisao']))}"
        )
    primeira = mudou_atual.iloc[0]
    return (
        f"a escolha {base['decisao']} se mantém até loadmult "
        f"{fmt_loadmult(anterior_loadmult(float(primeira['loadmult'])))}; acima disso, "
        f"{primeira['decisao']} passa a valer"
    )


def anterior_loadmult(valor: float) -> float:
    anteriores = [item for item in LOADMULTS if item < valor]
    return anteriores[-1] if anteriores else valor


def fmt_loadmult(valor: float | object) -> str:
    numero = float(valor)
    return f"{numero:.1f}".replace(".", ",")


def _eh_limiar_unico(trecho: pd.DataFrame, rotulo_base: str) -> bool:
    ordenado = trecho.sort_values("loadmult")
    decisoes = ordenado["decisao"].astype(str).tolist()
    if not decisoes:
        return False
    primeiro_diferente = next((i for i, item in enumerate(decisoes) if item != rotulo_base), None)
    if primeiro_diferente is None:
        return True
    posteriores = decisoes[primeiro_diferente:]
    return len(set(posteriores)) == 1 and rotulo_base not in posteriores


def _descrever_segmentos(trecho: pd.DataFrame, rotulo_base: str) -> str:
    ordenado = trecho.sort_values("loadmult")
    segmentos: list[tuple[list[float], str]] = []
    for linha in ordenado.itertuples(index=False):
        carga = float(linha.loadmult)
        decisao = str(linha.decisao)
        if not segmentos or segmentos[-1][1] != decisao:
            segmentos.append(([carga], decisao))
        else:
            segmentos[-1][0].append(carga)
    frases = []
    for cargas, decisao in segmentos:
        rotulo = _faixa_cargas(cargas)
        if decisao == rotulo_base:
            frases.append(f"{rotulo} mantém {rotulo_base}")
        else:
            frases.append(f"{rotulo} → {decisao}")
    return "; ".join(frases)


def _faixa_cargas(cargas: list[float]) -> str:
    if len(cargas) == 1:
        return fmt_loadmult(cargas[0])
    return f"{fmt_loadmult(cargas[0])}–{fmt_loadmult(cargas[-1])}"


def renderizar_markdown(
    resultados: pd.DataFrame,
    resumo: pd.DataFrame,
    casos: list[CasoAnalise],
) -> str:
    escolhidos = [c for c in casos if c.grupo == "alimentador"]
    linhas = [
        "# Sensibilidade das premissas da restauração",
        "",
        "Varredura real da issue #96: `loadmult` em {0,6; 0,8; 1,0; 1,2; 1,4}, "
        "carga por curva × carga nominal e `FAS_CON` cadastrado × rebalanceado com critério "
        "conservador (só em cargas BT monofásicas com mais de uma fase disponível no PAC).",
        "",
        f"CSV completo: `{resultados_path_rel()}`.",
        "",
        "## Casos analisados",
        "",
        "- cenários fixos: " + ", ".join(f"`{nome}`" for nome in CENARIOS_ALVO),
        "- alimentadores adicionais escolhidos da #91: "
        + ", ".join(f"`{c.caso}`" for c in escolhidos)
        + " (prioridade para casos com opções viáveis e regiões distintas).",
        "",
        "## Ponto de virada por caso",
        "",
        "| caso | base | loadmult nas premissas atuais | carga nominal | "
        "FAS_CON rebalanceado | conclusão |",
        "|---|---|---|---|---|---|",
    ]
    for item in resumo.itertuples(index=False):
        linhas.append(
            f"| {item.caso} | {item.base} | {item.loadmult_atual} | {item.carga_nominal} | "
            f"{item.rebalanceamento} | {item.conclusao} |"
        )
    linhas += ["", "## Leitura direta", ""]
    for item in resumo.itertuples(index=False):
        linhas += [
            f"### {item.caso}",
            "",
            f"- {item.loadmult_atual}.",
            f"- {item.carga_nominal}.",
            f"- {item.rebalanceamento}.",
            f"- Conclusão: {item.conclusao}.",
            "",
        ]
    linhas += [
        "## Observações metodológicas",
        "",
        "- `tempo_reparo` não entrou na varredura porque **não participa do score elétrico nem da "
        "ordenação de `restore_options`**; hoje ele só altera o campo de impacto estimado.",
        "- `FAS_CON rebalanceado` aqui **não** muda o comportamento do produto: "
        "é apenas um cenário de medição offline. Cargas em PAC de dois fios ficaram "
        "como cadastradas.",
    ]
    return "\n".join(linhas) + "\n"


def resultados_path_rel() -> str:
    return "docs/bench/2026-09-12-sensibilidade-premissas.csv"


def _preparar_contexto_ctmt(
    gpkg: Path,
    ctmt: str,
    out_dir: Path,
    dia: str,
    mes: int,
) -> ContextoCtmt:
    from bdgd_light.twin import converter_ctmt

    conv = converter_ctmt(gpkg, ctmt, out_dir, dias=[dia], meses=[mes])
    pasta_base = conv.pasta
    existentes = _camadas(gpkg)
    ctmts = _ler(gpkg, "CTMT", existentes)
    sel = ctmts[ctmts["COD_ID"] == ctmt]
    if sel.empty:
        raise SensibilidadeError(f"CTMT {ctmt} não encontrado em {gpkg}")
    nomes = (
        "SSDMT",
        "UNSEMT",
        "UNTRMT",
        "SSDBT",
        "UNSEBT",
        "RAMLIG",
        "UCBT_tab",
        "UCMT_tab",
        "UGBT_tab",
        "UGMT_tab",
        "PIP",
        "EQTRMT",
        "SEGCON",
        "CRVCRG",
    )
    tabelas = {n: _por_ctmt(_ler(gpkg, n, existentes), ctmt) for n in nomes}
    if tabelas["UCBT_tab"].empty and "UCBT" in existentes:
        tabelas["UCBT_tab"] = _por_ctmt(_ler(gpkg, "UCBT", existentes), ctmt)
    for nome in ("UCBT_tab", "UCMT_tab", "PIP"):
        tabelas[nome] = _agrupar_cargas(tabelas[nome])
    conversor = _Conversor(Path(gpkg), sel.iloc[0], tabelas, ANO_PADRAO)
    conversor._conectividade()
    conversor.transformadores()
    curvas = _Curvas.das_linhas(tabelas["CRVCRG"])
    tipos_cc = [
        _texto(x) or "flat"
        for nome in ("UCBT_tab", "UCMT_tab", "PIP")
        if "TIP_CC" in tabelas[nome].columns
        for x in tabelas[nome]["TIP_CC"]
    ]
    for nome in ("UCBT_tab", "UCMT_tab", "PIP"):
        if not tabelas[nome].empty and "TIP_CC" not in tabelas[nome].columns:
            tipos_cc.append("flat")
    curvas.garantir(tipos_cc)
    fases_por_barra = mapear_fases_por_barra(pasta_base)
    return ContextoCtmt(
        ctmt=ctmt,
        pasta_base=pasta_base,
        cargas_bt=(
            _montar_specs_carga(conversor, curvas, "UCBT_tab", dia, mes)
            + _montar_specs_carga(conversor, curvas, "PIP", dia, mes)
        ),
        cargas_mt=_montar_specs_carga(conversor, curvas, "UCMT_tab", dia, mes),
        fases_por_barra=fases_por_barra,
    )


def _montar_specs_carga(
    conversor: _Conversor,
    curvas: _Curvas,
    nome: str,
    tip_dia: str,
    mes: int,
) -> list[CargaSpec]:
    df = conversor.t[nome]
    if df.empty:
        return []
    ip = nome == "PIP"
    bt = ip or nome.startswith("UCBT")
    if ip:
        col_id = "COD_ID"
    elif bt and "RAMAL" in df.columns:
        col_id = "RAMAL"
    else:
        col_id = "PN_CON" if "PN_CON" in df.columns else "COD_ID"
    ids = df[col_id].map(_texto)
    repetidos = ids[ids.duplicated(keep=False)] if not ip else ids.iloc[0:0]
    sufixos: dict[str, int] = {}
    energias = [c for c in [f"ENE_{i:02d}" for i in range(1, 13)] if c in df.columns]
    col_mes = f"ENE_{mes:02d}"
    specs: list[CargaSpec] = []
    for i, r in df.iterrows():
        ident = ids[i]
        if i in repetidos.index:
            sufixos[ident] = sufixos.get(ident, 0) + 1
            ident = f"{ident}_{sufixos[ident]}"
        total = sum(_num(r[c]) for c in energias)
        if total == 0:
            continue
        pac = _texto(r["PAC"])
        fas = _texto(r.get("FAS_CON")) or ("AN" if bt else "ABC")
        fases = 3 if fas in ("ABC", "ABCN") else 1
        conn = CONEXAO_CARGA.get(fas, "Wye")
        tip_cc = _texto(r.get("TIP_CC")) or "flat"
        kw_curva_total = curvas.kw(tip_cc, tip_dia, mes, _num(r.get(col_mes)), conversor.dias)
        kw_curva_total = math.trunc(kw_curva_total * 1e6) / 1e6
        car_inst = max(_num(r.get("CAR_INST")), 0.0)
        kw_nominal_total = car_inst if car_inst > 0 else kw_curva_total
        if bt:
            trafo = _texto(r.get("UNI_TR_MT"))
            kv_linha = conversor.kv_bt.get(trafo) or _kv(r.get("TEN_FORN"), 0.22) or 0.22
            kv = (
                conversor.kv_fase_bt.get(trafo) or kv_linha / math.sqrt(3.0)
                if fases == 1 and conn == "Wye"
                else kv_linha
            )
            prefixo = "BT_IP" if ip else "BT_"
        else:
            trafo = ""
            kv = conversor.basekv
            prefixo = "MT_"
        specs.append(
            CargaSpec(
                arquivo="CargasBT" if bt else "CargasMT",
                base_nome=f"Load.{prefixo}{ident}",
                pac=pac,
                fas_con=fas,
                fases=fases,
                conn=conn,
                kv=kv,
                daily=f"{tip_cc}_{tip_dia}",
                ativa=conversor._ligado(pac),
                uni_tr_mt=trafo,
                kw_curva_total=kw_curva_total,
                kw_nominal_total=kw_nominal_total,
            )
        )
    return specs


def mapear_fases_por_barra(pasta_ctmt: Path) -> dict[str, tuple[int, ...]]:
    """Extrai, dos arquivos DSS do CTMT, as fases 1/2/3 disponíveis em cada barra."""
    fases: dict[str, set[int]] = {}
    for caminho in pasta_ctmt.glob("*.dss"):
        texto = caminho.read_text(encoding="utf-8", errors="replace")
        for barra, nos in _RE_BUS.findall(texto):
            fases.setdefault(barra, set()).update(
                int(no) for no in nos.split(".") if no in {"1", "2", "3"}
            )
    return {barra: tuple(sorted(nos)) for barra, nos in fases.items()}


def _sobrescrever_arquivo_cargas(
    destino: Path,
    prefixo: str,
    cargas: list[CargaSpec],
    modelo_carga: str,
) -> None:
    arquivo = next(destino.glob(f"{prefixo}_{DIA_PADRAO}{MES_PADRAO:02d}_*.dss"), None)
    if arquivo is None:
        if cargas:
            raise FileNotFoundError(
                f"{prefixo}_{DIA_PADRAO}{MES_PADRAO:02d}_*.dss ausente em {destino}"
            )
        return
    linhas = renderizar_cargas(cargas, modelo_carga=modelo_carga)
    arquivo.write_text("\n".join(linhas) + ("\n" if linhas else ""), encoding="utf-8")


def renderizar_cargas(cargas: list[CargaSpec], *, modelo_carga: str) -> list[str]:
    linhas: list[str] = []
    for carga in cargas:
        nos = NOS.get(carga.fas_con, "1.2.3.4")
        kw = carga.kw_total(modelo_carga) / 2
        base = (
            f'New "{carga.base_nome}_M{{m}}" bus1="{carga.pac}.{nos}" phases={carga.fases} '
            f"conn={carga.conn} model={{modelo}} kv={carga.kv:.9f} kw = {kw:.6f} pf=0.92 "
            f'status=variable vmaxpu=1.5 vminpu=0.5 daily="{carga.daily}"'
        )
        l1 = base.format(m=1, modelo=2)
        l2 = base.format(m=2, modelo=3)
        if carga.ativa:
            linhas.extend([l1, l2])
        else:
            linhas.extend([f"!{l1}", f"!{l2}"])
    return linhas


def carregar_resultados_csv(caminho: str | Path) -> list[dict[str, str]]:
    with Path(caminho).open(encoding="utf-8") as fp:
        return list(csv.DictReader(fp))
