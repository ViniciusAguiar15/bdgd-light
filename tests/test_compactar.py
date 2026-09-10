"""Compactação dos retornos das ferramentas para o modelo (``agent/compactar.py``, #36):
listas de nós viram contagens, ``restore_options`` traz top-N detalhadas + resumo das demais,
``get_topology`` traz contagens de chaves, floats arredondados e o original nunca é alterado."""

from __future__ import annotations

import copy
import json

from bdgd_light.agent.compactar import (
    MAX_TIES,
    arredondar,
    compactar,
    compactar_fluxo,
    compactar_restore_options,
    compactar_topologia,
    compactar_zona,
)


def _opcao(chave: str, margem: float | None, viavel: bool, motivos: list[str] | None = None):
    return {
        "chave": chave,
        "ctmt_chave": "RJO001",
        "fonte": "RJO002",
        "tlcd": True,
        "externa": False,
        "clientes": {"ucbt": 100, "ucmt": 2, "trafos": 5, "kva": 750.0, "total": 102, "extra": 1},
        "manobras": [{"acao": "abrir", "chave": "CH001"}, {"acao": "fechar", "chave": chave}],
        "score": {
            "viavel": viavel,
            "convergiu": True,
            "margem_disjuntor": margem,
            "i_disjuntor_a": 123.456789,
            "i_nominal_a": 400.0,
            "vmin_mt_pu": 0.98123456,
            "vmax_mt_pu": 1.02,
            "carregamento_max_mt_pct": 55.5555555,
            "sobrecargas_mt": [],
            "perdas_kw": 12.3456789,
            "motivos": motivos or [],
            "master": "/tmp/x/Master.dss",
            "detalhe_interno": {"a": 1},
        },
    }


def test_arredondar_preserva_tipos_e_arredonda_floats():
    entrada = {"a": 1.23456789, "b": [0.1 + 0.2, 3, True, None], "c": {"d": "x"}}
    saida = arredondar(entrada)
    assert saida == {"a": 1.2346, "b": [0.3, 3, True, None], "c": {"d": "x"}}
    assert saida["b"][2] is True and saida["b"][3] is None


def test_compactar_zona_troca_listas_por_contagens_e_enxuga_manobras():
    original = {
        "trecho": "T1",
        "zona": {"nos": ["n1", "n2", "n3"], "chave_montante": "CH001"},
        "desligados": ["n1", "n2", "n3", "n4"],
        "reenergizados": [],
        "manobras": [{"acao": "abrir", "chave": "CH001"}],
        "clientes_desligados": {
            "ucbt": 10,
            "ucmt": 0,
            "trafos": 1,
            "kva": 75.0,
            "total": 10,
            "x": 1,
        },
    }
    copia = copy.deepcopy(original)
    saida = compactar_zona(original)
    assert original == copia, "o original não pode ser alterado"
    assert saida["zona"] == {"n_nos": 3, "chave_montante": "CH001"}
    assert saida["n_desligados"] == 4 and saida["n_reenergizados"] == 0
    assert "desligados" not in saida and "zona" in saida
    assert saida["manobras"] == [{"acao": "abrir", "chave": "CH001"}]
    assert "x" not in saida["clientes_desligados"]


def test_compactar_restore_options_top_n_e_resumo_das_demais():
    opcoes = [
        _opcao("CH010", 0.4598, True),
        _opcao("CH011", 0.30, True),
        _opcao("CH012", 0.20, True),
        _opcao("CH013", None, False, ["1 trecho(s) MT acima de 100 % (Line.x 180 %)"]),
    ]
    original = {
        "trecho": "T1",
        "n_opcoes": 4,
        "score": {"vmin": 0.93, "vmax": 1.05, "master": "/tmp/Master.dss", "n_viaveis": 3},
        "opcoes": opcoes,
    }
    copia = copy.deepcopy(original)
    saida = compactar_restore_options(original, top_n=2)
    assert original == copia
    assert "master" not in saida["score"] and saida["score"]["n_viaveis"] == 3
    assert [o["chave"] for o in saida["opcoes"]] == ["CH010", "CH011"]
    detalhada = saida["opcoes"][0]
    assert detalhada["manobras"] == [
        {"acao": "abrir", "chave": "CH001"},
        {"acao": "fechar", "chave": "CH010"},
    ]
    assert detalhada["score"]["margem_disjuntor_pct"] == 46.0
    assert "master" not in detalhada["score"] and "detalhe_interno" not in detalhada["score"]
    assert "extra" not in detalhada["clientes"] and detalhada["clientes"]["ucbt"] == 100
    resumidas = saida["outras_opcoes"]
    assert [o["chave"] for o in resumidas] == ["CH012", "CH013"]
    assert resumidas[0] == {
        "chave": "CH012",
        "fonte": "RJO002",
        "clientes": 102,
        "viavel": True,
        "margem_disjuntor_pct": 20.0,
    }
    assert resumidas[1]["viavel"] is False and "180 %" in resumidas[1]["motivo"]
    assert "4 opções" in saida["nota"]
    # sem excedente não há resumo nem nota
    curta = compactar_restore_options({"opcoes": opcoes[:2]}, top_n=5)
    assert "outras_opcoes" not in curta and "nota" not in curta


def test_compactar_topologia_conta_chaves_e_resume_ties_longas():
    chaves = [
        {
            "chave": f"CH{i:03d}",
            "normal": "NF" if i % 3 else "NA",
            "estado": "fechada",
            "tlcd": i % 2,
        }
        for i in range(30)
    ]
    chaves[0]["estado"] = "aberta"
    ties = [
        {"chave": f"T{i}", "ctmt": "A", "ctmt_viz": "B", "aberta": True, "tlcd": False, "extra": 1}
        for i in range(3)
    ]
    saida = compactar_topologia({"ctmt": "A", "km": 12.34567, "chaves": chaves, "ties": ties})
    assert "chaves" not in saida
    assert saida["chaves_resumo"]["total"] == 30
    assert saida["chaves_resumo"]["NA"] == 10 and saida["chaves_resumo"]["NF"] == 20
    assert saida["chaves_resumo"]["abertas"] == 1 and saida["chaves_resumo"]["telecomandadas"] == 15
    assert saida["ties"] == [{k: v for k, v in t.items() if k != "extra"} for t in ties]
    assert saida["km"] == 12.34567  # compactar_topologia não arredonda; compactar() sim
    muitas = [dict(ties[0], chave=f"T{i}", aberta=i % 2 == 0) for i in range(MAX_TIES + 5)]
    saida = compactar("get_topology", {"ties": muitas, "km": 12.34567})
    assert "ties" not in saida and saida["ties_resumo"]["total"] == MAX_TIES + 5
    assert saida["ties_resumo"]["abertas"] == (MAX_TIES + 5 + 1) // 2
    assert saida["km"] == 12.3457


def test_compactar_fluxo_remove_comandos_e_limita_listas():
    r = {
        "convergiu": True,
        "comandos_dss": ["open Line.x"] * 10,
        "master": "/tmp/Master.dss",
        "ajustes": {"a": 1},
        "n_nos_fase": 1234,
        "vmin_pu": 0.9512345,
        "manobras_aplicadas": [{"acao": "abrir", "chave": "CH001"}],
        "piores_barras": [
            {"barra": f"b{i}", "no": f"n{i}", "kv_base": 13.8, "v_pu": 0.95} for i in range(8)
        ],
        "sobrecargas": [{"elemento": f"Line.{i}", "carregamento_pct": 150.0} for i in range(7)],
    }
    saida = compactar("run_powerflow", r)
    for campo in ("comandos_dss", "master", "ajustes", "n_nos_fase"):
        assert campo not in saida
    assert saida["manobras_aplicadas"] == [{"acao": "abrir", "chave": "CH001"}]
    assert len(saida["piores_barras"]) == 5 and "no" not in saida["piores_barras"][0]
    assert len(saida["sobrecargas"]) == 5
    assert saida["vmin_pu"] == 0.9512
    assert compactar_fluxo({"x": 1}) == {"x": 1}


def test_compactar_sem_regra_so_arredonda_e_reduz_tamanho():
    assert compactar("get_switch_state", {"chave": "CH1", "v": 1.00000001}) == {
        "chave": "CH1",
        "v": 1.0,
    }
    assert compactar("propose_plan", [1.23456789]) == [1.2346]
    assert compactar("x", "texto") == "texto"
    original = {
        "opcoes": [_opcao(f"CH{i}", 0.5 - i / 100, True) for i in range(10)],
        "score": {"master": "m"},
    }
    antes = len(json.dumps(original, default=str))
    depois = len(json.dumps(compactar("restore_options", original), default=str))
    assert depois < antes * 0.6
