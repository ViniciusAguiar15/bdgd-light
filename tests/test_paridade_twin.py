from __future__ import annotations

from pathlib import Path

from bdgd_light.paridade_twin import (
    ConfiguracaoParidadeTwin,
    ResultadoParidadeCtmt,
    contar_definicoes_dss,
    renderizar_markdown,
)


def test_contar_definicoes_dss_normaliza_tipos(tmp_path):
    arquivo = tmp_path / "exemplo.dss"
    arquivo.write_text(
        "\n".join(
            [
                'New "Line.L1" bus1=a bus2=b',
                '!New "Generator.G1" bus1=a kw=10',
                'New "LoadShape.CURVA1" npts=24',
                'New "load.C1" bus1=a.1 kw=5',
            ]
        ),
        encoding="utf-8",
    )

    contagem = contar_definicoes_dss([arquivo])

    assert contagem["line"] == 1
    assert contagem["generator"] == 1
    assert contagem["loadshape"] == 1
    assert contagem["load"] == 1


def test_renderizar_markdown_resume_paridade():
    config = ConfiguracaoParidadeTwin(
        gdb=Path("data/base.gdb"),
        feeders_dir=Path("data/feeders"),
        workdir=Path("scratch/issue-95"),
        out_csv=Path("docs/dados/paridade.csv"),
        out_md=Path("docs/paridade.md"),
        ctmts=("AAA001",),
    )
    resultado = ResultadoParidadeCtmt(
        ctmt="AAA001",
        origem="amostra sintética",
        barras_mt=12,
        erro_tensao_max_pu=2e-6,
        erro_tensao_medio_pu=1e-6,
        perdas_kw_meu=10.0,
        perdas_kw_ref=10.000001,
        delta_perdas_kw=-0.000001,
        corrente_saida_a_meu=20.0,
        corrente_saida_a_ref=20.000001,
        delta_corrente_saida_a=-0.000001,
        linhas_meu=5,
        linhas_ref=5,
        trafos_meu=2,
        trafos_ref=2,
        cargas_meu=8,
        cargas_ref=8,
        reatores_meu=2,
        reatores_ref=2,
        fontes_meu=1,
        fontes_ref=1,
        codcondutor_meu=3,
        codcondutor_ref=10,
        curvacarga_meu=2,
        curvacarga_ref=6,
        gd_bt_ref=4,
        avisos=("AAA001: 1 ramal longo",),
    )

    texto = renderizar_markdown([resultado], config)

    assert "bdgd2opendss 1.2.5" in texto
    assert "Nenhum dos casos comparados passou de 1 % de diferença." in texto
    assert (
        "| `AAA001` | 12 | 2.000e-06 | 1.000e-06 | -0.000001 | -0.000001 | "
        "5/5 | 2/2 | 8/8 | paridade operacional |" in texto
    )
    assert "catálogo completo no oráculo; catálogo podado + GD fora do Master no gpkg2dss" in texto
    assert "AAA001: 1 ramal longo" in texto
