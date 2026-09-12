"""Testes da varredura de sensibilidade das premissas (issue #96)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

from bdgd_light.sensibilidade import (
    CargaSpec,
    _frase_turning_point,
    classificar_decisao,
    fmt_loadmult,
    mapear_fases_por_barra,
    rebalancear_fas_con,
    renderizar_cargas,
    resumir_caso,
    selecionar_alimentadores_sensibilidade,
)


class _ScoreFake:
    def __init__(self, chave: str, *, viavel: bool):
        self.chave = chave
        self.viavel = viavel


def test_seleciona_tres_casos_com_regioes_distintas(tmp_path: Path):
    tabela = pd.DataFrame(
        [
            {
                "ctmt": "BRR38521",
                "etapa": "restore_options",
                "status": "sucesso",
                "regiao": "Barra/Recreio",
                "porte": "G",
                "n_opcoes": 15,
                "score_viaveis": 15,
            },
            {
                "ctmt": "AVD0001",
                "etapa": "restore_options",
                "status": "sucesso",
                "regiao": "Barra/Recreio",
                "porte": "G",
                "n_opcoes": 7,
                "score_viaveis": 7,
            },
            {
                "ctmt": "ALC683",
                "etapa": "restore_options",
                "status": "sucesso",
                "regiao": "Tijuca",
                "porte": "P",
                "n_opcoes": 6,
                "score_viaveis": 6,
            },
            {
                "ctmt": "PDG33010",
                "etapa": "restore_options",
                "status": "sucesso",
                "regiao": "Jacarepaguá/Taquara",
                "porte": "M",
                "n_opcoes": 7,
                "score_viaveis": 5,
            },
        ]
    )
    caminho = tmp_path / "generalizacao.csv"
    tabela.to_csv(caminho, index=False)

    escolhidos = selecionar_alimentadores_sensibilidade(caminho)

    assert escolhidos["ctmt"].tolist() == ["BRR38521", "ALC683", "PDG33010"]


def test_rebalanceamento_seguro_respeita_fases_disponiveis():
    cargas = [
        CargaSpec(
            arquivo="CargasBT",
            base_nome="Load.BT_A",
            pac="PAC3F",
            fas_con="AN",
            fases=1,
            conn="Wye",
            kv=0.127,
            daily="flat_DU",
            ativa=True,
            uni_tr_mt="TR1",
            kw_curva_total=10.0,
            kw_nominal_total=12.0,
        ),
        CargaSpec(
            arquivo="CargasBT",
            base_nome="Load.BT_B",
            pac="PAC3F",
            fas_con="AN",
            fases=1,
            conn="Wye",
            kv=0.127,
            daily="flat_DU",
            ativa=True,
            uni_tr_mt="TR1",
            kw_curva_total=9.0,
            kw_nominal_total=11.0,
        ),
        CargaSpec(
            arquivo="CargasBT",
            base_nome="Load.BT_C",
            pac="PAC2F",
            fas_con="AN",
            fases=1,
            conn="Wye",
            kv=0.127,
            daily="flat_DU",
            ativa=True,
            uni_tr_mt="TR1",
            kw_curva_total=8.0,
            kw_nominal_total=10.0,
        ),
    ]

    rebalanceadas, trocas = rebalancear_fas_con(
        cargas,
        {"PAC3F": (1, 2, 3), "PAC2F": (1,)},
        "curva",
    )

    assert trocas == 1
    assert [c.fas_con for c in rebalanceadas] == ["AN", "BN", "AN"]


def test_renderizar_cargas_reflete_modelo_nominal_e_comenta_isoladas():
    linhas = renderizar_cargas(
        [
            CargaSpec(
                arquivo="CargasBT",
                base_nome="Load.BT_X",
                pac="PAC1",
                fas_con="BN",
                fases=1,
                conn="Wye",
                kv=0.127,
                daily="flat_DU",
                ativa=False,
                uni_tr_mt="TR1",
                kw_curva_total=8.0,
                kw_nominal_total=12.0,
            )
        ],
        modelo_carga="nominal",
    )

    assert "kw = 6.000000" in linhas[0]
    assert linhas[0].startswith('!New "Load.BT_X_M1"')
    assert 'bus1="PAC1.2.4"' in linhas[0]


def test_mapear_fases_por_barra_ler_topologia_dss(tmp_path: Path):
    pasta = tmp_path / "ctmt"
    pasta.mkdir()
    (pasta / "Rede.dss").write_text(
        'New "Line.SBT_1" bus1="PAC_A.1.2.3.4" bus2="PAC_B.1.4"\n'
        'New "Transformer.TRF_A" phases=3 windings=2 buses=["PAC_C.1.2.3" "PAC_D.1.2.3.4"]\n',
        encoding="utf-8",
    )

    fases = mapear_fases_por_barra(pasta)

    assert fases == {
        "PAC_A": (1, 2, 3),
        "PAC_B": (1,),
        "PAC_C": (1, 2, 3),
        "PAC_D": (1, 2, 3),
    }


def test_resumo_indica_ponto_de_virada_e_nao_virada():
    resultados = pd.DataFrame(
        [
            {
                "caso": "T1",
                "modelo_carga": "curva",
                "fas_con": "cadastrado",
                "loadmult": 0.6,
                "trocas_fas_con": 0,
                "decisao": "CH1",
                "virou_decisao": False,
            },
            {
                "caso": "T1",
                "modelo_carga": "curva",
                "fas_con": "cadastrado",
                "loadmult": 1.0,
                "trocas_fas_con": 0,
                "decisao": "CH1",
                "virou_decisao": False,
            },
            {
                "caso": "T1",
                "modelo_carga": "curva",
                "fas_con": "cadastrado",
                "loadmult": 1.2,
                "trocas_fas_con": 0,
                "decisao": "sem transferência",
                "virou_decisao": True,
            },
            {
                "caso": "T1",
                "modelo_carga": "nominal",
                "fas_con": "cadastrado",
                "loadmult": 1.0,
                "trocas_fas_con": 0,
                "decisao": "CH1",
                "virou_decisao": False,
            },
            {
                "caso": "T1",
                "modelo_carga": "curva",
                "fas_con": "rebalanceado",
                "loadmult": 1.0,
                "trocas_fas_con": 0,
                "decisao": "CH1",
                "virou_decisao": False,
            },
        ]
    )
    resultados = pd.concat(
        [
            resultados,
            pd.DataFrame(
                [
                    {
                        "caso": "T1",
                        "modelo_carga": "nominal",
                        "fas_con": "cadastrado",
                        "loadmult": 1.2,
                        "trocas_fas_con": 0,
                        "decisao": "sem transferência",
                        "virou_decisao": True,
                    },
                    {
                        "caso": "T1",
                        "modelo_carga": "curva",
                        "fas_con": "rebalanceado",
                        "loadmult": 1.0,
                        "trocas_fas_con": 0,
                        "decisao": "CH1",
                        "virou_decisao": False,
                    },
                ]
            ),
        ],
        ignore_index=True,
    )

    resumo = resumir_caso(resultados)

    assert (
        resumo.loadmult_atual == "premissas atuais: vira em loadmult 1,2 (CH1 → sem transferência)"
    )
    assert resumo.carga_nominal == "carga nominal: vira em loadmult 1,2 (CH1 → sem transferência)"
    assert (
        resumo.rebalanceamento
        == "FAS_CON rebalanceado: rebalanceamento seguro não moveu carga nenhuma neste caso"
    )
    assert (
        resumo.conclusao
        == "a escolha CH1 se mantém até loadmult 1,0; acima disso, sem transferência passa a valer"
    )


def test_classificacao_decisao_e_formatacao_loadmult():
    assert classificar_decisao(None, n_opcoes=0) == ("sem_opcoes_topologicas", "sem transferência")
    assert classificar_decisao(_ScoreFake("CH1", viavel=False), n_opcoes=2) == (
        "sem_opcao_viavel",
        "sem transferência",
    )
    assert classificar_decisao(_ScoreFake("CH1", viavel=True), n_opcoes=2) == ("restaurar", "CH1")
    assert fmt_loadmult(1.4) == "1,4"


def _carregar_script_sensibilidade():
    caminho = Path("scripts/sensibilidade.py")
    spec = importlib.util.spec_from_file_location("sensibilidade_script", caminho)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


def test_script_expoe_main():
    modulo = _carregar_script_sensibilidade()
    assert callable(modulo.main)


def test_frase_turning_point_marca_caso_nao_monotonico():
    resultados = pd.DataFrame(
        [
            {
                "modelo_carga": "curva",
                "fas_con": "cadastrado",
                "loadmult": 0.6,
                "decisao": "A",
                "virou_decisao": True,
            },
            {
                "modelo_carga": "curva",
                "fas_con": "cadastrado",
                "loadmult": 0.8,
                "decisao": "B",
                "virou_decisao": True,
            },
            {
                "modelo_carga": "curva",
                "fas_con": "cadastrado",
                "loadmult": 1.0,
                "decisao": "BASE",
                "virou_decisao": False,
            },
            {
                "modelo_carga": "curva",
                "fas_con": "cadastrado",
                "loadmult": 1.2,
                "decisao": "B",
                "virou_decisao": True,
            },
            {
                "modelo_carga": "curva",
                "fas_con": "cadastrado",
                "loadmult": 1.4,
                "decisao": "B",
                "virou_decisao": True,
            },
        ]
    )

    frase = _frase_turning_point(
        resultados,
        modelo_carga="curva",
        fas_con="cadastrado",
        rotulo_base="BASE",
        titulo="premissas atuais",
    )

    assert frase == (
        "premissas atuais: sem limiar único (0,6 → A; 0,8 → B; 1,0 mantém BASE; 1,2–1,4 → B)"
    )
