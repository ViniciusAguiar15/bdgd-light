"""Testes da comparação de GD na restauração (issue #99)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest
from rich.console import Console

if importlib.util.find_spec("opendssdirect") is None:  # não importar: ver tests/conftest.py
    pytest.skip("opendssdirect não instalado (uv sync --extra twin)", allow_module_level=True)

from bdgd_light.gd_restauracao import (  # noqa: E402
    CasoAnalise,
    carregar_rede,
    comparar_vencedoras,
    preparar_plano_restauracao,
    renderizar_relatorio,
    rodar_analise,
    selecionar_alimentadores_alta_penetracao,
)
from bdgd_light.ingest.recorte import recortar  # noqa: E402
from bdgd_light.twin import ConfiguracaoGd  # noqa: E402

CLUSTER_MINI = Path("tests/fixtures/dss/cluster_mini")


def _mmgd_gemeo(destino: Path) -> Path:
    dados = [
        {
            "DatGeracaoConjuntoDados": "2026-09-11",
            "AnmPeriodoReferencia": "09/2026",
            "NumCNPJDistribuidora": "60444437000146",
            "SigAgente": "LIGHT SESA",
            "NomAgente": "LIGHT SERVICOS DE ELETRICIDADE S A",
            "CodClasseConsumo": "RE",
            "DscClasseConsumo": "Residencial",
            "CodSubGrupoTarifario": "B1",
            "DscSubGrupoTarifario": "B1",
            "CodUFibge": "33",
            "SigUF": "RJ",
            "CodRegiao": "3301",
            "NomRegiao": "Metropolitana",
            "CodMunicipioIbge": "3304557",
            "NomMunicipio": "Rio de Janeiro",
            "CodCEP": "20000000",
            "SigTipoConsumidor": "PF",
            "NumCPFCNPJ": "***",
            "CodEmpreendimento": "GD.RJ.UGBT001",
            "DthAtualizaCadastralEmpreend": "2024-07-10",
            "SigModalidadeEmpreendimento": "",
            "DscModalidadeHabilitado": "Geracao na propria UC",
            "QtdUCRecebeCredito": 1,
            "SigTipoGeracao": "UFV",
            "DscFonteGeracao": "Radiação solar",
            "DscPorte": "Microgeracao",
            "MdaPotenciaInstaladaKW": 5.0,
            "NomSubEstacao": "SE001",
            "NumCoordESub": -43.2,
            "NumCoordNSub": -22.9,
            "NomTitularEmpreendimento": "***",
        },
        {
            "DatGeracaoConjuntoDados": "2026-09-11",
            "AnmPeriodoReferencia": "09/2026",
            "NumCNPJDistribuidora": "60444437000146",
            "SigAgente": "LIGHT SESA",
            "NomAgente": "LIGHT SERVICOS DE ELETRICIDADE S A",
            "CodClasseConsumo": "CO",
            "DscClasseConsumo": "Comercial",
            "CodSubGrupoTarifario": "B3",
            "DscSubGrupoTarifario": "B3",
            "CodUFibge": "33",
            "SigUF": "RJ",
            "CodRegiao": "3301",
            "NomRegiao": "Metropolitana",
            "CodMunicipioIbge": "3304557",
            "NomMunicipio": "Rio de Janeiro",
            "CodCEP": "20000000",
            "SigTipoConsumidor": "PJ",
            "NumCPFCNPJ": "***",
            "CodEmpreendimento": "GD.RJ.UGBT002",
            "DthAtualizaCadastralEmpreend": "2024-07-10",
            "SigModalidadeEmpreendimento": "",
            "DscModalidadeHabilitado": "Geracao na propria UC",
            "QtdUCRecebeCredito": 1,
            "SigTipoGeracao": "UTE",
            "DscFonteGeracao": "Biogás",
            "DscPorte": "Microgeracao",
            "MdaPotenciaInstaladaKW": 10.0,
            "NomSubEstacao": "SE001",
            "NumCoordESub": -43.2,
            "NumCoordNSub": -22.9,
            "NomTitularEmpreendimento": "***",
        },
        {
            "DatGeracaoConjuntoDados": "2026-09-11",
            "AnmPeriodoReferencia": "09/2026",
            "NumCNPJDistribuidora": "60444437000146",
            "SigAgente": "LIGHT SESA",
            "NomAgente": "LIGHT SERVICOS DE ELETRICIDADE S A",
            "CodClasseConsumo": "CO",
            "DscClasseConsumo": "Comercial",
            "CodSubGrupoTarifario": "A4",
            "DscSubGrupoTarifario": "A4",
            "CodUFibge": "33",
            "SigUF": "RJ",
            "CodRegiao": "3301",
            "NomRegiao": "Metropolitana",
            "CodMunicipioIbge": "3304557",
            "NomMunicipio": "Rio de Janeiro",
            "CodCEP": "20000000",
            "SigTipoConsumidor": "PJ",
            "NumCPFCNPJ": "***",
            "CodEmpreendimento": "GD.RJ.UGMT001",
            "DthAtualizaCadastralEmpreend": "2024-07-10",
            "SigModalidadeEmpreendimento": "",
            "DscModalidadeHabilitado": "Geracao na propria UC",
            "QtdUCRecebeCredito": 1,
            "SigTipoGeracao": "UFV",
            "DscFonteGeracao": "Radiação solar",
            "DscPorte": "Minigeracao",
            "MdaPotenciaInstaladaKW": 500.0,
            "NomSubEstacao": "SE001",
            "NumCoordESub": -43.2,
            "NumCoordNSub": -22.9,
            "NomTitularEmpreendimento": "***",
        },
    ]
    destino.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(dados).to_parquet(destino, index=False)
    return destino


@pytest.fixture(scope="module")
def recorte_cluster_mini(parquet_mini, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("gd_restauracao")
    resultado = recortar(parquet_mini, ["RJO001", "RJO002"], out, console=Console(quiet=True))
    assert resultado.cluster is not None and resultado.cluster.gpkg is not None
    return resultado.cluster.gpkg


def test_selecionar_alimentadores_alta_penetracao(tmp_path: Path):
    tabela = pd.DataFrame(
        [
            {
                "ctmt": "GDN0022",
                "origem": "alta penetração convergente na #97",
                "potencia_exata_kw": 29.58,
                "potencia_agregada_kw": 11.92,
            },
            {
                "ctmt": "TRS003",
                "origem": "alta penetração convergente na #97",
                "potencia_exata_kw": 2022.84,
                "potencia_agregada_kw": 123.17,
            },
            {
                "ctmt": "BRI001",
                "origem": "maior penetração da #97/#35",
                "potencia_exata_kw": 12165.25,
                "potencia_agregada_kw": 1644.03,
            },
            {
                "ctmt": "SRD002",
                "origem": "segunda maior penetração da #97/#35",
                "potencia_exata_kw": 15744.08,
                "potencia_agregada_kw": 4116.12,
            },
        ]
    )
    csv = tmp_path / "gd-gemeo-alocacao.csv"
    tabela.to_csv(csv, index=False)

    escolhidos = selecionar_alimentadores_alta_penetracao(csv)

    assert escolhidos["ctmt"].tolist() == ["SRD002", "BRI001", "TRS003"]


def test_preparar_plano_restauracao_cluster_mini(recorte_cluster_mini: Path):
    rede = carregar_rede(recorte_cluster_mini)

    plano, opcoes, religador = preparar_plano_restauracao(rede, "SEG001")

    assert religador == "CH008"
    assert not plano.is_open("CH008")
    assert {opcao.chave for opcao in opcoes} == {"CH003", "CH005"}


def test_rodar_analise_e_renderizar_relatorio(
    parquet_mini: Path,
    recorte_cluster_mini: Path,
    tmp_path: Path,
):
    mmgd = _mmgd_gemeo(tmp_path / "dados" / "mmgd.parquet")
    caso = CasoAnalise(
        grupo="cenario",
        caso="cluster_mini",
        descricao="cenário sintético",
        cluster="cluster_mini",
        gpkg=recorte_cluster_mini,
        ctmts_cluster=("RJO001", "RJO002"),
        ctmt_principal="RJO001",
        trecho_falta="SEG001",
        criterio_falta="fixture sintética",
        origem="teste",
    )

    opcoes, resumo, comparacao = rodar_analise(
        [caso],
        dss_out=tmp_path / "dss",
        dia="DU",
        mes=1,
        gd_cfg=ConfiguracaoGd(parquet_dir=parquet_mini, mmgd_path=mmgd),
        console_=Console(quiet=True),
    )

    assert set(opcoes["instante"]) == {"meio-dia com GD", "ponta da noite sem GD"}
    assert resumo["caso"].tolist() == ["cluster_mini", "cluster_mini"]
    assert comparacao["caso"].tolist() == ["cluster_mini"]
    assert comparar_vencedoras(resumo)["caso"].tolist() == ["cluster_mini"]

    markdown = renderizar_relatorio(
        opcoes=opcoes,
        resumo=resumo,
        comparacao=comparacao,
        casos=[caso],
        alimentadores_selecionados=pd.DataFrame(
            [
                {
                    "ctmt": "RJO001",
                    "origem": "teste",
                    "potencia_total_kw": 515.0,
                }
            ]
        ),
        dia="DU",
        mes=1,
        out_opcoes_csv=Path("docs/dados/gd-restauracao-opcoes.csv"),
        out_resumo_csv=Path("docs/dados/gd-restauracao-resumo.csv"),
    )

    assert "Ilhamento não entra como hipótese de restauração" in markdown
    assert "docs/dados/gd-restauracao-opcoes.csv" in markdown
    assert "`cluster_mini`" in markdown
