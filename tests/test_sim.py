"""Simulador de eventos: reprodutibilidade, sorteios, cenários nomeados, fila JSONL e CLI."""

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from bdgd_light.cli import app
from bdgd_light.grid import Cluster
from bdgd_light.ingest.recorte import recortar
from bdgd_light.sim import (
    CENARIOS,
    CHAVE_INDISPONIVEL,
    FALTA_PERMANENTE,
    FALTA_TRANSITORIA,
    PICO_CARGA,
    TIPOS,
    Evento,
    FilaEventos,
    Simulador,
    normalizar_tipo,
)

runner = CliRunner()


@pytest.fixture(scope="module")
def gpkg(parquet_mini, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("sim")
    recortar(parquet_mini, ["RJO001", "RJO002"], out, console=Console(quiet=True))
    return next(out.glob("cluster_*.gpkg"))


@pytest.fixture(scope="module")
def rede(gpkg) -> Cluster:
    return Cluster.from_gpkg(gpkg)


def _assinatura(ev: Evento) -> tuple:
    d = dict(ev.to_dict())
    d.pop("hora")
    d.pop("id", None)
    return (ev.tipo, ev.alvo, json.dumps(d, sort_keys=True))


def test_mesma_semente_mesmos_eventos(rede):
    a = Simulador(rede, "mini", seed=42)
    b = Simulador(rede, "mini", seed=42)
    ea = [a.gerar() for _ in range(8)]
    eb = [b.gerar() for _ in range(8)]
    assert [_assinatura(e) for e in ea] == [_assinatura(e) for e in eb]
    assert all(e.seed == 42 for e in ea)
    assert {e.tipo for e in ea} <= set(TIPOS)


def test_sementes_diferentes_divergem(rede):
    ea = [Simulador(rede, "mini", seed=1).gerar() for _ in range(6)]
    eb = [Simulador(rede, "mini", seed=2).gerar() for _ in range(6)]
    assert [_assinatura(e) for e in ea] != [_assinatura(e) for e in eb]


def test_falta_permanente_enriquecida_pela_rede(rede):
    ev = Simulador(rede, "mini", seed=0).falta_permanente("SEG002")
    assert ev.tipo == FALTA_PERMANENTE
    assert ev.trecho == "SEG002" and ev.alvo == "SEG002"
    assert ev.ctmt == "RJO001"
    d = ev.detalhes
    assert d["religador"] == "CH008"
    assert d["chaves_com_indicacao"][0] == "CH008"
    assert set(d["chaves_com_indicacao"]) <= set(rede.chaves)
    assert d["pac"] == ["RJO001_MT_3", "RJO001_MT_4"]
    assert d["sem_tensao_se_religador_abrir"]["clientes"]["total"] == 5
    assert d["comp_m"] == pytest.approx(102.5)
    assert "inject_fault" in d["acao_esperada"]
    # o estado da rede não é alterado pelo simulador
    assert rede.grafo.edges[rede.chaves["CH008"]]["aberta"] is False


def test_falta_transitoria_religa(rede):
    ev = Simulador(rede, "mini", seed=5).falta_transitoria("SEG007")
    assert ev.tipo == FALTA_TRANSITORIA
    assert ev.detalhes["religou"] is True
    assert ev.detalhes["tempo_morto_s"] > 0
    assert ev.ctmt == "RJO002"


def test_trecho_inexistente(rede):
    from bdgd_light.grid import TrechoInexistenteError

    with pytest.raises(TrechoInexistenteError):
        Simulador(rede, "mini", seed=0).falta_permanente("NAO_EXISTE")


def test_sorteio_de_trecho_ponderado_por_comprimento(rede):
    sim = Simulador(rede, "mini", seed=7)
    contagem = Counter(sim._sortear_trecho() for _ in range(3000))
    comp = {t: rede.grafo.edges[uv]["comp"] for t, uv in rede.trechos.items()}
    maior = max(comp, key=comp.get)
    menor = min(comp, key=comp.get)
    assert contagem[maior] > 2 * contagem[menor]
    assert set(contagem) <= set(rede.trechos)


def test_pico_de_carga(rede):
    ev = Simulador(rede, "mini", seed=3).pico_carga("RJO002")
    assert ev.tipo == PICO_CARGA
    assert ev.ctmt == "RJO002" and ev.alvo == "RJO002"
    assert 1.15 <= ev.detalhes["loadmult"] <= 1.6
    assert ev.detalhes["duracao_min"] in (15, 30, 60, 120)
    assert ev.detalhes["clientes"]["total"] > 0
    assert "run_powerflow" in ev.detalhes["acao_esperada"]
    with pytest.raises(ValueError):
        Simulador(rede, "mini", seed=3).pico_carga("XXX")


def test_chave_indisponivel_so_telecomandada(rede):
    sim = Simulador(rede, "mini", seed=11)
    for _ in range(20):
        ev = sim.chave_indisponivel()
        assert ev.tipo == CHAVE_INDISPONIVEL
        assert ev.detalhes["tlcd"] is True
        assert ev.detalhes["normal"] in ("NA", "NF")
        assert ev.chave in rede.chaves
    ev = sim.chave_indisponivel("CH001")
    assert ev.chave == "CH001" and ev.alvo == "CH001"
    from bdgd_light.grid import ChaveInexistenteError

    with pytest.raises(ChaveInexistenteError):
        sim.chave_indisponivel("CH999")


def test_normalizar_tipo():
    assert normalizar_tipo("falta") == FALTA_PERMANENTE
    assert normalizar_tipo("Transitória") == FALTA_TRANSITORIA
    assert normalizar_tipo("pico") == PICO_CARGA
    assert normalizar_tipo("chave") == CHAVE_INDISPONIVEL
    assert normalizar_tipo(" FALTA_PERMANENTE ") == FALTA_PERMANENTE
    with pytest.raises(ValueError, match="inválido"):
        normalizar_tipo("terremoto")


def test_cenario_nomeado_sem_rede():
    ev = Simulador(None, "tijuca", seed=1).cenario("tijuca_cabofrio_tronco")
    assert ev.cenario == "tijuca_cabofrio_tronco"
    assert ev.tipo == FALTA_PERMANENTE
    assert ev.trecho == "11304252" and ev.ctmt == "ALC9925"
    assert ev.cluster == "tijuca"
    assert "descricao" in ev.detalhes and "CABOFRIO" in ev.detalhes["descricao"]
    neg = Simulador(None, "ipanema", seed=1).cenario("ipanema_9210")
    assert neg.trecho == "11409068" and neg.ctmt == "PTS0001"
    assert "negativo" in neg.detalhes["descricao"]


def test_cenario_de_outro_cluster_falha_com_rede(rede):
    with pytest.raises(ValueError, match="tijuca"):
        Simulador(rede, "mini", seed=1).cenario("tijuca_cabofrio_tronco")
    with pytest.raises(ValueError, match="desconhecido"):
        Simulador(rede, "mini", seed=1).cenario("inexistente")


def test_cenario_aleatorio_usa_a_rede(rede):
    ev = Simulador(rede, "mini", seed=9).cenario("aleatorio")
    assert ev.cenario == "aleatorio"
    assert ev.tipo in TIPOS
    assert set(CENARIOS) == {
        "tijuca_cabofrio_tronco",
        "ipanema_9210",
        "taquara_bocari",
        "aleatorio",
    }


def test_evento_ida_e_volta():
    ev = Evento(
        tipo=FALTA_PERMANENTE,
        cluster="mini",
        hora=datetime(2026, 9, 10, 12, 0, tzinfo=UTC).isoformat(),
        detalhes={"x": 1},
        trecho="SEG001",
        ctmt="RJO001",
    )
    d = ev.to_dict()
    assert "chave" not in d and "cenario" not in d and "id" not in d
    assert Evento.de_dict(d) == ev
    assert Evento.de_dict(json.loads(json.dumps(d))).alvo == "SEG001"


def test_fila_publica_ids_sequenciais_e_persiste(tmp_path, rede):
    caminho = tmp_path / "eventos" / "eventos.jsonl"
    fila = FilaEventos(caminho)
    assert len(fila) == 0 and fila.ultimo() is None and fila.listar() == []
    sim = Simulador(rede, "mini", seed=4)
    publicados = [fila.publicar(sim.gerar()) for _ in range(3)]
    assert [e.id for e in publicados] == ["E-0001", "E-0002", "E-0003"]
    assert len(fila) == 3
    assert fila.ultimo().id == "E-0003"
    assert [e.id for e in fila.listar(desde=2)] == ["E-0003"]
    # outra instância lê o mesmo arquivo e continua a numeração
    outra = FilaEventos(caminho)
    assert len(outra) == 3
    assert outra.publicar(sim.gerar()).id == "E-0004"
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 4
    assert all(json.loads(linha)["id"].startswith("E-") for linha in linhas)


def test_cli_sim_listar():
    r = runner.invoke(app, ["sim", "--listar"], env={"COLUMNS": "200"})
    assert r.exit_code == 0, r.output
    for nome in ("tijuca_cabofrio_tronco", "ipanema_9210", "taquara_bocari"):
        assert nome in r.output


def test_cli_sim_emitir_json_e_mostrar(tmp_path, gpkg):
    fila = tmp_path / "eventos.jsonl"
    args = ["sim", "--cluster", str(gpkg), "--emitir", "2", "--tipo", "falta", "--seed", "1"]
    r = runner.invoke(app, [*args, "--fila", str(fila), "--json"])
    assert r.exit_code == 0, r.output
    eventos = [json.loads(linha) for linha in r.output.strip().splitlines()]
    assert [e["id"] for e in eventos] == ["E-0001", "E-0002"]
    assert all(e["tipo"] == FALTA_PERMANENTE for e in eventos)
    assert all(e["seed"] == 1 for e in eventos)
    # mesma semente em outra fila: mesmos alvos
    r2 = runner.invoke(app, [*args, "--fila", str(tmp_path / "outra.jsonl"), "--json"])
    assert [json.loads(x)["trecho"] for x in r2.output.strip().splitlines()] == [
        e["trecho"] for e in eventos
    ]
    r3 = runner.invoke(app, ["sim", "--fila", str(fila), "--mostrar", "1"], env={"COLUMNS": "200"})
    assert r3.exit_code == 0, r3.output
    assert "E-0002" in r3.output and "E-0001" not in r3.output
    r4 = runner.invoke(app, ["sim", "--fila", str(tmp_path / "vazia.jsonl"), "--mostrar", "3"])
    assert r4.exit_code == 0 and "fila vazia" in r4.output


def test_cli_sim_erros(tmp_path, gpkg):
    fila = str(tmp_path / "e.jsonl")
    r = runner.invoke(app, ["sim", "--cluster", str(gpkg), "--tipo", "xyz", "--fila", fila])
    assert r.exit_code == 1 and "inválido" in r.output
    r = runner.invoke(app, ["sim", "--cluster", "nada", "--feeders", str(tmp_path), "--fila", fila])
    assert r.exit_code == 1 and "não encontrado" in r.output
    r = runner.invoke(app, ["sim", "--fila", fila])
    assert r.exit_code == 1 and "--cluster" in r.output
    r = runner.invoke(app, ["sim", "--cluster", str(gpkg), "--cenario", "tijuca_cabofrio_tronco"])
    assert r.exit_code == 1 and "tijuca" in r.output
    assert not Path(fila).exists()


def test_cli_sim_cenario_sem_recorte_disponivel(tmp_path):
    fila = tmp_path / "e.jsonl"
    r = runner.invoke(
        app,
        [
            "sim",
            "--cenario",
            "ipanema_9210",
            "--feeders",
            str(tmp_path),
            "--fila",
            str(fila),
            "--json",
        ],
    )
    assert r.exit_code == 0, r.output
    ev = json.loads(r.output.strip().splitlines()[-1])
    assert ev["cenario"] == "ipanema_9210" and ev["trecho"] == "11409068"
    assert fila.exists()
