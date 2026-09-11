"""Testes do replay da auditoria do agente (issue #83)."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

if importlib.util.find_spec("opendssdirect") is None:  # não importar: ver twin.powerflow.no_motor
    pytest.skip("opendssdirect não instalado (uv sync --extra twin)", allow_module_level=True)
pytest.importorskip("yaml")

from bdgd_light.agent.orquestrador import Orquestrador, fake_operador  # noqa: E402
from bdgd_light.cli import app  # noqa: E402
from bdgd_light.grid import Cluster  # noqa: E402
from bdgd_light.ingest.recorte import recortar  # noqa: E402
from bdgd_light.mcp_server import SessaoCOD  # noqa: E402
from bdgd_light.mcp_server.humano import aprovar, rejeitar  # noqa: E402
from bdgd_light.sim import FilaEventos, Simulador  # noqa: E402

CLUSTER_MINI = Path("tests/fixtures/dss/cluster_mini")
runner = CliRunner()
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def saida(resultado) -> str:
    return _ANSI.sub("", resultado.output)


@pytest.fixture(scope="module")
def recorte(parquet_mini, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("replay_feeders")
    resultado = recortar(parquet_mini, ["RJO001", "RJO002"], out, console=Console(quiet=True))
    return resultado.cluster.gpkg


@pytest.fixture
def dss_out(tmp_path) -> Path:
    destino = tmp_path / "dss"
    shutil.copytree(CLUSTER_MINI, destino)
    return destino


@pytest.fixture
def sessao(recorte, dss_out, tmp_path) -> SessaoCOD:
    return SessaoCOD(feeders=recorte.parent, dss_out=dss_out, estado_dir=tmp_path / "estado")


@pytest.fixture
def simulador(recorte) -> Simulador:
    return Simulador(Cluster.from_gpkg(recorte), recorte.stem, seed=7)


def gerar_evento_completo(sessao: SessaoCOD, simulador: Simulador, tmp_path: Path):
    fila = FilaEventos(tmp_path / "eventos.jsonl")
    evento = fila.publicar(simulador.falta_permanente("SEG001"))
    orq = Orquestrador(sessao, fake_operador(), provider="fake")
    ex1 = orq.executar_evento(evento)
    rejeitar(sessao, ex1.proposta["id"], operador="ana", motivo="a chave CH003 está em manutenção")
    ex2 = orq.replanejar_apos_rejeicao(
        ex1.proposta["id"], "a chave CH003 está em manutenção", evento=evento
    )
    execucao = aprovar(sessao, ex2.proposta["id"], operador="bia")
    return evento, ex1, ex2, execucao


def test_cli_replay_reconstroi_linha_do_tempo_completa(sessao, simulador, tmp_path):
    evento, ex1, ex2, execucao = gerar_evento_completo(sessao, simulador, tmp_path)

    r_texto = runner.invoke(
        app, ["replay", evento.id, "--origem", str(sessao.estado_dir), "--verificar-cadeia"]
    )
    texto = saida(r_texto)
    assert r_texto.exit_code == 0, texto
    assert f"Replay do evento {evento.id}" in texto
    assert "Cadeia: ✔ íntegra" in texto
    assert "restore_options" in texto and "CH003" in texto and "CH005" in texto
    assert "rejeição humana" in texto and "replanejamento" in texto
    assert "aprovação humana" in texto and "set_switch" in texto

    r_json = runner.invoke(
        app,
        ["replay", evento.id, "--origem", str(sessao.estado_dir), "--verificar-cadeia", "--json"],
    )
    assert r_json.exit_code == 0, r_json.output
    dados = json.loads(r_json.output)
    assert dados["evento_id"] == evento.id and dados["evento"]["id"] == evento.id
    assert dados["cadeia"]["integra"] is True
    assert sorted(Path(a).name for a in dados["arquivos"]) == ["audit.jsonl", "hitl.jsonl"]

    linha = dados["linha_do_tempo"]
    tipos = [item["tipo"] for item in linha]
    assert {"evento", "opcoes", "verificador", "rejeicao", "replanejamento", "aprovacao"} <= set(
        tipos
    )
    ferramentas = [item["ferramenta"] for item in linha if item["tipo"] == "ferramenta"]
    assert ferramentas[:5] == [
        "load_cluster",
        "inject_fault",
        "locate_fault",
        "isolate_fault",
        "propose_plan",
    ]
    assert ferramentas[-2:] == ["set_switch", "set_switch"]

    opcoes = next(item for item in linha if item["tipo"] == "opcoes")
    assert [opcao["chave"] for opcao in opcoes["opcoes"]] == ["CH003", "CH005"]
    assert opcoes["opcoes"][0]["score"]["viavel"] is True

    recusas = [item for item in linha if item["tipo"] == "rejeicao"]
    assert len(recusas) == 1
    assert recusas[0]["operador"] == "ana"
    assert recusas[0]["proposta"] == ex1.proposta["id"]
    assert recusas[0]["motivo"] == "a chave CH003 está em manutenção"
    aprovacao = next(item for item in linha if item["tipo"] == "aprovacao")
    assert aprovacao["operador"] == "bia" and aprovacao["proposta"] == ex2.proposta["id"]
    manobras = [item for item in linha if item.get("ferramenta") == "set_switch"]
    assert [m["resultado"]["chave"] for m in manobras] == ["CH001", "CH005"]
    assert manobras[-1]["resultado"]["proposta_status"] == "executada"
    assert execucao["proposta"]["status"] == "executada"


def test_cli_replay_aponta_primeira_divergencia_na_cadeia(sessao, simulador, tmp_path):
    evento, *_ = gerar_evento_completo(sessao, simulador, tmp_path)
    caminho = sessao.estado_dir / "audit.jsonl"
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    adulterado = json.loads(linhas[7])
    adulterado["dados"]["resultado"]["opcoes"][0]["score"]["margem_disjuntor"] = 0.01
    linhas[7] = json.dumps(adulterado, ensure_ascii=False)
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")

    r = runner.invoke(
        app,
        ["replay", evento.id, "--origem", str(sessao.estado_dir), "--verificar-cadeia", "--json"],
    )
    assert r.exit_code == 1, r.output
    dados = json.loads(r.output)
    assert dados["cadeia"]["integra"] is False
    assert Path(dados["cadeia"]["primeira_divergencia"]["arquivo"]).name == "audit.jsonl"
    assert "seq=8: hash não bate" in dados["cadeia"]["primeira_divergencia"]["erro"]
