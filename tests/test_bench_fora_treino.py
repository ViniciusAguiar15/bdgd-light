from __future__ import annotations

import csv
from pathlib import Path

from bdgd_light.bench import carregar_tarefas
from bdgd_light.bench_fora_treino import (
    CasoForaTreino,
    carregar_casos_generalizacao,
    escrever_casos_csv,
    escrever_tarefas_yaml,
    recalcular_esperados,
    selecionar_casos,
)


def _escrever_csv(caminho: Path, cabecalho: list[str], linhas: list[dict[str, object]]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=cabecalho)
        writer.writeheader()
        writer.writerows(linhas)


def test_carrega_e_seleciona_casos_da_generalizacao(tmp_path):
    inventario = tmp_path / "inventario.csv"
    _escrever_csv(
        inventario,
        ["COD_ID", "MUN", "lat_min", "lat_max", "lon_min", "lon_max", "vizinhos"],
        [
            {
                "COD_ID": "AAA001",
                "MUN": "3304557",
                "lat_min": -22.9,
                "lat_max": -22.8,
                "lon_min": -43.3,
                "lon_max": -43.2,
                "vizinhos": "BBB002;CCC003",
            },
            {
                "COD_ID": "DDD004",
                "MUN": "3304557",
                "lat_min": -22.9,
                "lat_max": -22.8,
                "lon_min": -43.3,
                "lon_max": -43.2,
                "vizinhos": "",
            },
        ],
    )
    generalizacao = tmp_path / "generalizacao.csv"
    _escrever_csv(
        generalizacao,
        [
            "ctmt",
            "ordem_sorteio",
            "regiao",
            "porte",
            "n_trechos",
            "etapa",
            "status",
            "n_ties",
            "n_opcoes",
            "score_viaveis",
            "trecho_falta",
        ],
        [
            {
                "ctmt": "AAA001",
                "ordem_sorteio": 2,
                "regiao": "Centro",
                "porte": "M",
                "n_trechos": 10,
                "etapa": "restore_options",
                "status": "sucesso",
                "n_ties": 3,
                "n_opcoes": 2,
                "score_viaveis": 1,
                "trecho_falta": "TR1",
            },
            {
                "ctmt": "DDD004",
                "ordem_sorteio": 1,
                "regiao": "Tijuca",
                "porte": "P",
                "n_trechos": 7,
                "etapa": "restore_options",
                "status": "sucesso",
                "n_ties": 0,
                "n_opcoes": 0,
                "score_viaveis": 0,
                "trecho_falta": "TR2",
            },
            {
                "ctmt": "AAA001",
                "ordem_sorteio": 2,
                "regiao": "Centro",
                "porte": "M",
                "n_trechos": 10,
                "etapa": "grafo",
                "status": "sucesso",
                "n_ties": 3,
                "n_opcoes": "",
                "score_viaveis": "",
                "trecho_falta": "",
            },
        ],
    )

    casos = carregar_casos_generalizacao(generalizacao, inventario)
    assert [caso.ctmt for caso in casos] == ["DDD004", "AAA001"]
    assert casos[1].vizinhos == ("BBB002", "CCC003")
    assert casos[1].cluster == "AAA001-BBB002-CCC003"
    assert [caso.ctmt for caso in selecionar_casos(casos, n=1)] == ["DDD004"]


def test_recalcula_esperados_e_escreve_tarefas(tmp_path, monkeypatch):
    class SessaoFake:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class GabaritoFake:
        def __init__(self, sessao, feeders):
            self.sessao = sessao
            self.feeders = feeders

        def esperado(self, tarefa):
            return [] if tarefa.cluster == "DDD004" else ["CH001", "CH002"]

    monkeypatch.setattr("bdgd_light.bench_fora_treino.SessaoCOD", SessaoFake)
    monkeypatch.setattr("bdgd_light.bench_fora_treino.Gabarito", GabaritoFake)
    casos = [
        CasoForaTreino(
            ordem_sorteio=1,
            ctmt="DDD004",
            regiao="Tijuca",
            porte="P",
            n_trechos=7,
            trecho_falta="TR2",
            n_ties=0,
            n_opcoes=0,
            score_viaveis=0,
            vizinhos=(),
            cluster="DDD004",
        ),
        CasoForaTreino(
            ordem_sorteio=2,
            ctmt="AAA001",
            regiao="Centro",
            porte="M",
            n_trechos=10,
            trecho_falta="TR1",
            n_ties=3,
            n_opcoes=2,
            score_viaveis=1,
            vizinhos=("BBB002",),
            cluster="AAA001-BBB002",
        ),
    ]
    completos = recalcular_esperados(
        casos,
        feeders_dir=tmp_path / "feeders",
        dss_out=tmp_path / "dss",
        estado_dir=tmp_path / "estado",
    )
    assert completos[0].esperado == ()
    assert completos[1].esperado == ("CH001", "CH002")

    tarefas_yaml = escrever_tarefas_yaml(completos, tmp_path / "tarefas.yaml")
    tarefas = carregar_tarefas(tarefas_yaml)
    assert [t.id for t in tarefas] == ["FT01", "FT02"]
    assert tarefas[0].esperado == []
    assert tarefas[1].esperado == ["CH001", "CH002"]

    casos_csv = escrever_casos_csv(completos, tmp_path / "casos.csv")
    texto = casos_csv.read_text(encoding="utf-8")
    assert "AAA001" in texto and "CH001;CH002" in texto
