"""Testes do atlas de interligações (issue #94)."""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import pandas as pd

from bdgd_light.atlas_interligacoes import (
    consolidar_atlas,
    escrever_resultado,
    gerar_histograma_svg,
    renderizar_markdown,
)


def test_consolida_fixture_sintetica(parquet_mini: Path) -> None:
    resultado = consolidar_atlas(parquet_mini)

    assert resultado.resumo.n_alimentadores == 3
    assert resultado.resumo.n_ties_campo == 2
    assert resultado.resumo.n_ties_telecomandadas == 1
    assert resultado.resumo.n_pares_ctmt == 2
    assert resultado.resumo.n_arestas == 1
    assert resultado.resumo.n_grau_zero == 1
    assert resultado.resumo.n_componentes == 2
    assert resultado.resumo.maior_componente == 2
    assert resultado.resumo.n_clientes_total == 9
    assert resultado.resumo.n_clientes_sem_socorro == 2
    assert resultado.resumo.pct_clientes_sem_socorro == 22.22222222222222

    alimentadores = resultado.alimentadores.set_index("COD_ID")
    assert alimentadores.loc["RJO001", "ties_campo"] == 2
    assert alimentadores.loc["RJO001", "ties_telecomandadas"] == 1
    assert alimentadores.loc["RJO001", "grau"] == 1
    assert alimentadores.loc["RJO001", "alimentadores_socorro"] == "RJO002"
    assert alimentadores.loc["RJO002", "subestacoes_socorro_nomes"] == "SETD SINTETICA 01"
    assert alimentadores.loc["RJO003", "grau"] == 0
    assert bool(alimentadores.loc["RJO003", "sem_socorro"])
    assert alimentadores.loc["RJO003", "tamanho_componente"] == 1

    arestas = resultado.arestas.to_dict(orient="records")
    assert arestas == [
        {
            "CTMT_A": "RJO001",
            "CTMT_B": "RJO002",
            "SUB_A": "SE001",
            "SUB_B": "SE001",
            "SUB_NOME_A": "SETD SINTETICA 01",
            "SUB_NOME_B": "SETD SINTETICA 01",
            "CONJ_A": "1",
            "CONJ_B": "1",
            "CONJ_NOME_A": "CONJUNTO SINTÉTICO",
            "CONJ_NOME_B": "CONJUNTO SINTÉTICO",
            "n_ties_campo": 2,
            "n_ties_telecomandadas": 1,
            "chaves": "CH003;CH005",
            "chaves_telecomandadas": "CH003",
        }
    ]

    distribuicao = resultado.distribuicao_grau.set_index("grau")
    assert distribuicao.loc[0, "alimentadores"] == 1
    assert distribuicao.loc[1, "alimentadores"] == 2
    assert distribuicao.loc[0, "pct_clientes"] == "22,22 %"
    assert distribuicao.loc[1, "pct_clientes"] == "77,78 %"

    componentes = resultado.componentes.set_index("componente_id")
    assert componentes.loc[1, "n_alimentadores"] == 2
    assert componentes.loc[1, "n_ties_campo"] == 2
    assert componentes.loc[2, "n_alimentadores"] == 1

    assert sorted(resultado.grafo.nodes) == ["RJO001", "RJO002", "RJO003"]
    assert list(resultado.grafo.edges(data="n_ties_campo")) == [("RJO001", "RJO002", 2)]


def test_renderiza_markdown_e_svg(parquet_mini: Path) -> None:
    resultado = consolidar_atlas(parquet_mini)

    markdown = renderizar_markdown(resultado)
    assert "Atlas de interligações da Light" in markdown
    assert "22,22 % dos clientes" in markdown
    assert "RJO003" in markdown
    assert "grafo-socorro.graphml" in markdown

    svg = gerar_histograma_svg(resultado.distribuicao_grau)
    assert svg.startswith("<svg")
    assert "Distribuição de grau do grafo de socorro" in svg
    assert ">0<" in svg and ">1<" in svg


def test_escreve_arquivos_versionaveis(parquet_mini: Path, tmp_path: Path) -> None:
    resultado = consolidar_atlas(parquet_mini)

    out_md = tmp_path / "atlas.md"
    out_alimentadores = tmp_path / "dados" / "atlas.csv"
    out_arestas = tmp_path / "dados" / "arestas.csv"
    out_graphml = tmp_path / "dados" / "grafo.graphml"
    out_svg = tmp_path / "dados" / "grau.svg"

    escrever_resultado(
        resultado,
        out_markdown=out_md,
        out_alimentadores_csv=out_alimentadores,
        out_arestas_csv=out_arestas,
        out_graphml=out_graphml,
        out_svg=out_svg,
    )

    assert out_md.exists()
    assert out_alimentadores.exists()
    assert out_arestas.exists()
    assert out_graphml.exists()
    assert out_svg.exists()

    relido = pd.read_csv(out_alimentadores)
    assert sorted(relido["COD_ID"]) == ["RJO001", "RJO002", "RJO003"]
    assert pd.read_csv(out_arestas).loc[0, "n_ties_campo"] == 2

    grafo = nx.read_graphml(out_graphml)
    assert sorted(grafo.nodes()) == ["RJO001", "RJO002", "RJO003"]
    assert sorted(grafo.edges()) == [("RJO001", "RJO002")]
