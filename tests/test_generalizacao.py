"""Testes de generalização do pipeline (issue #91)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest
from rich.console import Console

from bdgd_light.generalizacao import (
    COLUNAS_RESULTADO,
    ConfiguracaoGeneralizacao,
    ContextoExecucao,
    FalhaEtapa,
    agrupar_falhas,
    classificar_porte,
    classificar_regioes,
    descrever_amostra,
    executar_generalizacao,
    executar_pipeline,
    markdown_resumo,
    preparar_universo,
    resumir_resultados,
    sortear_alimentadores,
)


@pytest.fixture
def inventario_sintetico() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "COD_ID": "R1",
                "MUN": "3304557",
                "lat_min": -22.9055,
                "lat_max": -22.9045,
                "lon_min": -43.1825,
                "lon_max": -43.1815,
            },
            {
                "COD_ID": "R2",
                "MUN": "3304557",
                "lat_min": -22.9255,
                "lat_max": -22.9245,
                "lon_min": -43.2355,
                "lon_max": -43.2345,
            },
            {
                "COD_ID": "R3",
                "MUN": "3304557",
                "lat_min": -22.9845,
                "lat_max": -22.9835,
                "lon_min": -43.2035,
                "lon_max": -43.2025,
            },
            {
                "COD_ID": "R4",
                "MUN": "3304557",
                "lat_min": -23.0035,
                "lat_max": -23.0025,
                "lon_min": -43.3505,
                "lon_max": -43.3495,
            },
            {
                "COD_ID": "FORA",
                "MUN": "3306206",
                "lat_min": -22.9,
                "lat_max": -22.89,
                "lon_min": -43.19,
                "lon_max": -43.18,
            },
        ]
    )


@pytest.fixture
def contagem_trechos_sintetica() -> pd.Series:
    return pd.Series({"R1": 5, "R2": 20, "R3": 40, "R4": 80}, dtype="int64")


def test_regioes_e_porte_sao_classificados(inventario_sintetico, contagem_trechos_sintetica):
    regioes = classificar_regioes(inventario_sintetico[inventario_sintetico["MUN"] == "3304557"])
    assert regioes.tolist() == ["Centro", "Tijuca", "Ipanema/Leblon", "Barra/Recreio"]
    portes = classificar_porte(contagem_trechos_sintetica)
    assert set(portes) <= {"P", "M", "G"}
    assert list(portes.index) == ["R1", "R2", "R3", "R4"]


def test_sorteio_e_deterministico_e_estratificado(inventario_sintetico, contagem_trechos_sintetica):
    universo = preparar_universo(inventario_sintetico, contagem_trechos_sintetica)
    a = sortear_alimentadores(universo, n=4, seed=91)
    b = sortear_alimentadores(universo, n=4, seed=91)
    c = sortear_alimentadores(universo, n=4, seed=92)
    assert a[["COD_ID", "ordem_sorteio"]].equals(b[["COD_ID", "ordem_sorteio"]])
    assert a["COD_ID"].tolist() != c["COD_ID"].tolist()
    assert sorted(a["regiao"].unique()) == ["Barra/Recreio", "Centro", "Ipanema/Leblon", "Tijuca"]


def test_pipeline_grava_sucesso_falha_e_nao_execucao(
    inventario_sintetico,
    contagem_trechos_sintetica,
    tmp_path,
):
    universo = preparar_universo(inventario_sintetico, contagem_trechos_sintetica)
    amostra = sortear_alimentadores(universo, n=4, seed=91)
    sucesso = {
        "recorte": {"status": "sucesso", "duracao_s": 0.1, "resumo": "ok"},
        "grafo": {"status": "sucesso", "duracao_s": 0.1, "resumo": "ok", "n_ties": 1},
        "gpkg2dss": {"status": "sucesso", "duracao_s": 0.1, "resumo": "ok"},
        "fluxo_base": {"status": "sucesso", "duracao_s": 0.1, "resumo": "ok"},
        "deteccao_ties": {"status": "sucesso", "duracao_s": 0.1, "resumo": "1 tie", "n_ties": 1},
        "injecao_falta": {
            "status": "sucesso",
            "duracao_s": 0.1,
            "resumo": "ok",
            "trecho_falta": "SEG001",
        },
        "restore_options": {
            "status": "sucesso",
            "duracao_s": 0.1,
            "resumo": "2 opção(ões), 1 viável(is)",
            "n_ties": 1,
            "n_opcoes": 2,
            "score_viaveis": 1,
            "trecho_falta": "SEG001",
        },
    }

    def executor(contexto: ContextoExecucao, console: Console | None = None) -> dict[str, dict]:
        if contexto.ctmt == "R2":
            raise FalhaEtapa("recorte", "RuntimeError: recorte falhou")
        if contexto.ctmt == "R3":
            raise FalhaEtapa(
                "fluxo_base",
                "RuntimeError: fluxo não convergiu",
                parciais={
                    "recorte": {"status": "sucesso", "duracao_s": 0.1, "resumo": "ok"},
                    "grafo": {
                        "status": "sucesso",
                        "duracao_s": 0.1,
                        "resumo": "ok",
                        "n_ties": 1,
                    },
                    "gpkg2dss": {"status": "sucesso", "duracao_s": 0.1, "resumo": "ok"},
                },
            )
        return sucesso

    resultados = executar_pipeline(
        amostra,
        tmp_path / "parquet",
        tmp_path / "work",
        executar_etapas=executor,
    )
    assert list(resultados.columns) == COLUNAS_RESULTADO
    assert len(resultados) == 28
    r2 = resultados[resultados["ctmt"] == "R2"].set_index("etapa")
    assert r2.loc["recorte", "status"] == "falha"
    assert r2.loc["grafo", "status"] == "nao_executada"
    r3 = resultados[resultados["ctmt"] == "R3"].set_index("etapa")
    assert r3.loc["fluxo_base", "status"] == "falha"
    assert r3.loc["restore_options", "status"] == "nao_executada"
    resumo = resumir_resultados(resultados)
    assert resumo.set_index("etapa").loc["recorte", "falha"] == 1
    assert resumo.set_index("etapa").loc["fluxo_base", "falha"] == 2


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_execucao_real_na_fixture_mini(parquet_mini, tmp_path):
    inventario = pd.DataFrame(
        [
            {
                "COD_ID": "RJO001",
                "MUN": "3304557",
                "lat_min": -22.9255,
                "lat_max": -22.9245,
                "lon_min": -43.2355,
                "lon_max": -43.2345,
            },
            {
                "COD_ID": "RJO002",
                "MUN": "3304557",
                "lat_min": -22.9254,
                "lat_max": -22.9244,
                "lon_min": -43.2354,
                "lon_max": -43.2344,
            },
            {
                "COD_ID": "RJO003",
                "MUN": "3304557",
                "lat_min": -22.9253,
                "lat_max": -22.9243,
                "lon_min": -43.2353,
                "lon_max": -43.2343,
            },
        ]
    )
    inventario_csv = tmp_path / "inventario.csv"
    inventario.to_csv(inventario_csv, index=False)
    config = ConfiguracaoGeneralizacao(
        inventario_csv=inventario_csv,
        parquet_dir=parquet_mini,
        workdir=tmp_path / "work",
        out_csv=tmp_path / "generalizacao.csv",
        n=2,
        seed=91,
    )
    amostra, resultados, resumo = executar_generalizacao(config, console=Console(quiet=True))
    assert len(amostra) == 2
    assert len(resultados) == 14
    assert (tmp_path / "generalizacao.csv").is_file()
    assert list(resumo["etapa"]) == [
        "recorte",
        "grafo",
        "gpkg2dss",
        "fluxo_base",
        "deteccao_ties",
        "injecao_falta",
        "restore_options",
    ]


def _carregar_script_generalizacao():
    caminho = Path("scripts/generalizacao.py")
    spec = importlib.util.spec_from_file_location("generalizacao_script", caminho)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


def test_script_expoe_main():
    modulo = _carregar_script_generalizacao()
    assert callable(modulo.main)


def test_helpers_de_markdown_e_descricao():
    resultados = pd.DataFrame(
        [
            {
                "ctmt": "A",
                "ordem_sorteio": 1,
                "seed": 91,
                "regiao": "Centro",
                "porte": "P",
                "n_trechos": 10,
                "etapa": "recorte",
                "status": "sucesso",
                "duracao_s": 0.1,
                "motivo": "",
                "resumo": "ok",
                "n_ties": pd.NA,
                "n_opcoes": pd.NA,
                "score_viaveis": pd.NA,
                "trecho_falta": pd.NA,
            },
            {
                "ctmt": "B",
                "ordem_sorteio": 2,
                "seed": 91,
                "regiao": "Centro",
                "porte": "P",
                "n_trechos": 11,
                "etapa": "recorte",
                "status": "falha",
                "duracao_s": 0.1,
                "motivo": "RuntimeError: x",
                "resumo": "",
                "n_ties": pd.NA,
                "n_opcoes": pd.NA,
                "score_viaveis": pd.NA,
                "trecho_falta": pd.NA,
            },
        ]
    )
    resumo = resumir_resultados(resultados)
    falhas = agrupar_falhas(resultados)
    md = markdown_resumo(resumo, falhas, "docs/bench/x.csv")
    assert "| etapa | n | sucesso | falha |" in md
    assert "docs/bench/x.csv" in md and "RuntimeError: x" in md
    amostra = pd.DataFrame(
        [
            {
                "COD_ID": "A",
                "seed": 91,
                "ordem_sorteio": 1,
                "regiao": "Centro",
                "porte": "P",
                "n_trechos": 10,
            }
        ]
    )
    desc = descrever_amostra(amostra)
    assert "semente: 91" in desc and "CTMTs: A" in desc
