"""Testes do cálculo de impacto estimado da manobra em consumidor-minutos e DEC."""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

import bdgd_light.grid.impacto as impacto_mod
from bdgd_light.grid import Cluster, calcular_impacto_opcao
from bdgd_light.ingest.recorte import recortar

TIJUCA = Path("data/feeders/cluster_tijuca.gpkg")


@pytest.fixture(scope="module")
def recorte_impacto(parquet_mini, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("impacto_feeders")
    resultado = recortar(parquet_mini, ["RJO001", "RJO002"], out, console=Console(quiet=True))
    return resultado.cluster.gpkg


def test_impacto_estimado_sintetico_com_dec(recorte_impacto: Path):
    rede = Cluster.from_gpkg(recorte_impacto)
    isolamento = rede.isolate_segment("SEG001")
    opcao = next(o for o in rede.restore_options("SEG001") if o.chave == "CH003")

    impacto = calcular_impacto_opcao(rede, opcao, isolamento=isolamento).to_dict()

    # 4 clientes restaurados × (180 min de reparo estimado − 5 min de manobra) = 700
    # consumidor-minutos evitados. O recorte RJO001+RJO002 tem 7 UC no mesmo conjunto sintético,
    # então o DEC estimado é 700 ÷ 7 ÷ 60 = 1,666666... h = 100 min.
    assert impacto["clientes_restaurados"] == 4
    assert impacto["clientes_sem_tensao_ate_reparo"] == 0
    assert impacto["consumidor_minutos_evitados"] == 700.0
    assert impacto["premissa"].startswith("impacto estimado do evento sob premissa")
    dec = impacto["dec_conjunto"]
    assert dec["codigo"] == "1"
    assert dec["nome"] == "CONJUNTO SINTÉTICO"
    assert dec["total_uc"] == 7
    assert dec["ucs_restauradas_no_conjunto"] == 4
    assert dec["dec_horas"] == pytest.approx(700 / 7 / 60)
    assert dec["dec_minutos"] == pytest.approx(700 / 7)


def test_impacto_sem_camada_conj_nao_estima_dec(recorte_impacto: Path):
    rede = Cluster.from_gpkg(recorte_impacto)
    rede.camadas.conj = None
    isolamento = rede.isolate_segment("SEG001")
    opcao = next(o for o in rede.restore_options("SEG001") if o.chave == "CH003")
    impacto = calcular_impacto_opcao(rede, opcao, isolamento=isolamento)
    assert impacto.dec_conjunto is None


def test_dec_conjunto_usa_so_clientes_do_proprio_conjunto(recorte_impacto: Path, monkeypatch):
    rede = Cluster.from_gpkg(recorte_impacto)

    monkeypatch.setattr(
        impacto_mod, "_clientes_por_conjunto", lambda *_args, **_kwargs: {"A": 2, "B": 1}
    )
    monkeypatch.setattr(
        impacto_mod, "_total_uc_conjunto", lambda _rede, codigo: {"A": 10, "B": 20}[codigo]
    )
    monkeypatch.setattr(impacto_mod, "_nome_conjunto", lambda _conj, codigo: f"Conjunto {codigo}")
    monkeypatch.setattr(impacto_mod, "_resolver_codigo_conjunto", lambda *_args, **_kwargs: "A")

    dec_a = impacto_mod._impacto_dec_conjunto(rede, {"n1", "n2"}, 175.0)
    assert dec_a is not None
    assert dec_a.codigo == "A"
    assert dec_a.ucs_restauradas_no_conjunto == 2
    assert dec_a.dec_minutos == pytest.approx((2 * 175.0) / 10)

    monkeypatch.setattr(impacto_mod, "_resolver_codigo_conjunto", lambda *_args, **_kwargs: "B")
    dec_b = impacto_mod._impacto_dec_conjunto(rede, {"n1", "n2"}, 175.0)
    assert dec_b is not None
    assert dec_b.codigo == "B"
    assert dec_b.ucs_restauradas_no_conjunto == 1
    assert dec_b.dec_minutos == pytest.approx((1 * 175.0) / 20)


@pytest.mark.skipif(not TIJUCA.exists(), reason=f"recorte real {TIJUCA} ausente")
def test_fumaca_impacto_cluster_tijuca():
    rede = Cluster.from_gpkg(TIJUCA)
    isolamento = rede.isolate_segment("11304252")
    opcao = next(o for o in rede.restore_options("11304252") if o.chave == "974020904")
    impacto = calcular_impacto_opcao(rede, opcao, isolamento=isolamento).to_dict()

    assert impacto["clientes_restaurados"] == 4042
    assert impacto["clientes_sem_tensao_ate_reparo"] == 0
    assert impacto["consumidor_minutos_evitados"] == 4042 * (180 - 5)
    assert impacto["dec_conjunto"] is None  # o recorte real versionado ainda não traz a camada CONJ
