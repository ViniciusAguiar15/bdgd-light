"""Backend do console (issue #35): rotas ``/api`` sobre o cluster_mini com o operador fake —
injeção de evento → proposta do agente → aprovação com identidade → mapa (GeoJSON) recolorido,
alternativas, auditoria íntegra, recusas (sem X-Operador, agente ocupado) e o comando ``serve``."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

pytest.importorskip("fastapi")
if importlib.util.find_spec("opendssdirect") is None:  # não importar: ver twin.powerflow.no_motor
    pytest.skip("opendssdirect não instalado (uv sync --extra twin)", allow_module_level=True)
pytest.importorskip("yaml")

from fastapi.testclient import TestClient  # noqa: E402

from bdgd_light.agent.orquestrador import Orquestrador, fake_operador  # noqa: E402
from bdgd_light.cli import app as cli  # noqa: E402
from bdgd_light.console import AgenteEmSegundoPlano, criar_app  # noqa: E402
from bdgd_light.ingest.recorte import recortar  # noqa: E402
from bdgd_light.mcp_server import SessaoCOD  # noqa: E402
from bdgd_light.mcp_server.humano import Autorizador  # noqa: E402
from bdgd_light.sim import Evento, FilaEventos  # noqa: E402

CLUSTER_MINI = Path("tests/fixtures/dss/cluster_mini")
OP = {"X-Operador": "ana", "Authorization": "Bearer segredo"}
runner = CliRunner()


@pytest.fixture(scope="module")
def recorte(parquet_mini, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("console_feeders")
    r = recortar(parquet_mini, ["RJO001", "RJO002"], out, console=Console(quiet=True))
    return r.cluster.gpkg


@pytest.fixture
def sessao(recorte, tmp_path) -> SessaoCOD:
    dss = tmp_path / "dss"
    shutil.copytree(CLUSTER_MINI, dss)
    return SessaoCOD(feeders=recorte.parent, dss_out=dss, estado_dir=tmp_path / "estado")


@pytest.fixture
def cliente(sessao, tmp_path) -> TestClient:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>console</h1>")
    agente = AgenteEmSegundoPlano(Orquestrador(sessao, fake_operador()), sincrono=True)
    web = criar_app(
        sessao,
        fila=FilaEventos(tmp_path / "eventos.jsonl"),
        autorizador=Autorizador("segredo"),
        agente=agente,
        dist=dist,
    )
    return TestClient(web)


def test_estado_vazio_e_console_estatico(cliente: TestClient):
    e = cliente.get("/api/estado").json()
    assert e["cluster"] is None and e["eventos_n"] == 0 and e["autorizacao"] == "segredo"
    assert e["agente"]["ocupado"] is False and e["agente"]["provider"] is None
    assert cliente.get("/api/estado.geojson").status_code == 404
    assert cliente.get("/api/eventos").json() == []
    assert cliente.get("/api/auditoria").json()["registros"] == []
    assert cliente.get("/api/agente").json()["ativo"] is True
    assert "<h1>console</h1>" in cliente.get("/").text
    assert cliente.get("/docs").status_code == 200


def test_fluxo_injetar_propor_aprovar(cliente: TestClient, sessao: SessaoCOD, recorte: Path):
    # injeção exige identidade
    r = cliente.post("/api/eventos", json={"cluster": str(recorte), "trecho": "SEG001"})
    assert r.status_code == 400
    r = cliente.post(
        "/api/eventos",
        json={"cluster": str(recorte), "tipo": "falta_permanente", "trecho": "SEG001"},
        headers=OP,
    )
    assert r.status_code == 202, r.text
    corpo = r.json()
    assert corpo["agente"] == "iniciado" and corpo["evento"]["id"] == "E-0001"
    assert corpo["evento"]["detalhes"]["injetado_por"] == "ana"

    # o agente (fake, síncrono nos testes) já deixou a proposta pendente
    e = cliente.get("/api/estado").json()
    assert e["cluster"] == recorte.stem and e["falta"] == "SEG001" and e["eventos_n"] == 1
    assert e["agente"]["n_execucoes"] == 1 and e["agente"]["ultima"]["proposta"] == "P-0001"
    assert e["hash"] and e["audit_n"] > 3
    [p] = e["propostas"]
    assert p["status"] == "pendente" and p["chave"] == "CH003" and p["token"] is None

    detalhe = cliente.get("/api/propostas/P-0001").json()
    alternativas = detalhe["alternativas"]
    assert [a["chave"] for a in alternativas] == ["CH003", "CH005"]
    assert alternativas[0]["escolhida"] is True and alternativas[0]["score"]["viavel"] is True
    assert detalhe["verificador"]["ok"] is True and detalhe["verificador"]["eletrico"] is True
    assert cliente.get("/api/propostas", params={"status": "pendente"}).json()[0]["id"] == "P-0001"
    assert cliente.get("/api/eventos", params={"desde": 0}).json()[0]["trecho"] == "SEG001"

    # mapa antes: trechos sem tensão a jusante da falta
    antes = cliente.get("/api/estado.geojson").json()
    sem_tensao = [
        f["properties"]["COD_ID"]
        for f in antes["features"]
        if f["properties"]["camada"] == "SSDMT" and f["properties"]["energizado"] is False
    ]
    assert "SEG002" in sem_tensao

    # aprovação: recusada sem segredo, executada com ele
    r = cliente.post("/api/propostas/P-0001/aprovar", headers={"X-Operador": "ana"})
    assert r.status_code == 401
    r = cliente.post("/api/propostas/P-0001/aprovar", headers=OP)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["erro"] is None and corpo["proposta"]["status"] == "executada"
    assert corpo["proposta"]["aprovada_por"] == "ana"
    assert [(x["chave"], x["estado"]) for x in corpo["execucao"]] == [
        ("CH001", "aberta"),
        ("CH003", "fechada"),
    ]

    depois = cliente.get("/api/estado.geojson").json()
    energizados = {
        f["properties"]["COD_ID"]
        for f in depois["features"]
        if f["properties"]["camada"] == "SSDMT" and f["properties"]["energizado"]
    }
    assert "SEG002" in energizados and "SEG001" not in energizados  # falta isolada, resto de volta
    ch003 = next(f for f in depois["features"] if f["properties"].get("COD_ID") == "CH003")
    assert ch003["properties"]["aberta"] is False

    # trilha: íntegra, hitl.jsonl com a decisão, alternativas vazias após execução
    aud = cliente.get("/api/auditoria", params={"n": 5}).json()
    assert aud["integra"] is True and aud["hash"] == cliente.get("/api/estado").json()["hash"]
    assert len(aud["registros"]) == 5 and aud["registros"][-1]["ferramenta"] == "set_switch"
    assert "approval_token" not in aud["registros"][-1].get("argumentos", {})
    hitl = [json.loads(x) for x in (sessao.estado_dir / "hitl.jsonl").read_text().splitlines()]
    assert hitl[0]["dados"]["operador"] == "ana" and hitl[0]["dados"]["origem"] == "console"
    assert cliente.get("/api/propostas/P-0001").json()["alternativas"] == []
    assert cliente.get("/api/agente").json()["execucoes"][0]["proposta"] == "P-0001"

    # reinício da demo: recarregar volta a rede ao normal e a nova falta gera P-0002
    r = cliente.post("/api/eventos", json={"trecho": "SEG001", "recarregar": True}, headers=OP)
    assert r.status_code == 202
    e = cliente.get("/api/estado").json()
    assert e["falta"] == "SEG001" and e["eventos_n"] == 2
    assert [p["id"] for p in e["propostas"] if p["status"] == "pendente"] == ["P-0002"]


def test_passo_a_passo_uma_manobra_por_chamada(cliente: TestClient, sessao: SessaoCOD, recorte):
    r = cliente.post("/api/eventos", json={"cluster": str(recorte), "trecho": "SEG001"}, headers=OP)
    assert r.status_code == 202
    [p] = cliente.get("/api/estado").json()["propostas"]
    assert p["status"] == "pendente" and p["executadas"] == 0 and p["n_passos"] == 2
    assert p["proximo_passo"] == {"acao": "abrir", "chave": "CH001"}

    def apagados() -> int:
        gj = cliente.get("/api/estado.geojson").json()
        return sum(
            1
            for f in gj["features"]
            if f["properties"]["camada"] == "SSDMT" and f["properties"]["energizado"] is False
        )

    na_falta = apagados()
    assert na_falta > 0
    sem_segredo = cliente.post("/api/propostas/P-0001/passo", headers={"X-Operador": "ana"})
    assert sem_segredo.status_code == 401

    # 1º clique: aprova (token emitido) e executa só a primeira manobra
    r = cliente.post("/api/propostas/P-0001/passo", headers=OP)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["erro"] is None and c["passo"]["chave"] == "CH001" and c["passo"]["estado"] == "aberta"
    assert c["passo"]["passo"] == 1 and c["passo"]["n_passos"] == 2
    assert c["proposta"]["status"] == "aprovada" and c["proposta"]["executadas"] == 1
    assert c["proposta"]["proximo_passo"] == {"acao": "fechar", "chave": "CH003"}
    assert c["proposta"]["aprovada_por"] == "ana" and c["proposta"]["token"] == "***"
    apos_1 = apagados()
    assert apos_1 == na_falta  # abrir a chave de isolamento ainda não reenergiza nada

    # 2º clique: última manobra → executada; mapa recolorido
    c = cliente.post("/api/propostas/P-0001/passo", headers=OP).json()
    assert c["passo"]["chave"] == "CH003" and c["passo"]["estado"] == "fechada"
    assert c["proposta"]["status"] == "executada" and c["proposta"]["proximo_passo"] is None
    assert apagados() < apos_1

    # 3º clique: nada a executar (409, proposta concluída)
    r = cliente.post("/api/propostas/P-0001/passo", headers=OP)
    assert r.status_code == 409 and "executada" in r.json()["detail"]

    # trilha: aprovação com executar="passo" e um hitl.passo por manobra; auditoria íntegra
    hitl = [json.loads(x) for x in (sessao.estado_dir / "hitl.jsonl").read_text().splitlines()]
    assert [h["tipo"] for h in hitl] == ["hitl.aprovacao", "hitl.passo", "hitl.passo"]
    assert hitl[0]["dados"]["executar"] == "passo"
    assert [h["dados"]["manobra"]["chave"] for h in hitl[1:]] == ["CH001", "CH003"]
    assert [h["dados"]["passo"] for h in hitl[1:]] == [1, 2]
    aud = cliente.get("/api/auditoria", params={"n": 3}).json()
    assert aud["integra"] is True
    assert [x.get("ferramenta") for x in aud["registros"]][-2:] == ["set_switch", "set_switch"]


def test_rejeitar_e_erros(cliente: TestClient, recorte: Path):
    r = cliente.post("/api/eventos", json={"cluster": str(recorte), "trecho": "SEG001"}, headers=OP)
    assert r.status_code == 202
    r = cliente.post(
        "/api/propostas/P-0001/rejeitar", json={"motivo": "equipe no local"}, headers=OP
    )
    assert r.status_code == 200 and r.json()["proposta"]["status"] == "rejeitada"
    assert cliente.post("/api/propostas/P-0001/aprovar", headers=OP).status_code == 409
    assert cliente.get("/api/propostas/P-9999").status_code == 409
    r = cliente.post("/api/eventos", json={"cenario": "inexistente"}, headers=OP)
    assert r.status_code == 422
    r = cliente.post("/api/eventos", json={"cluster": "nao_existe"}, headers=OP)
    assert r.status_code == 404
    r = cliente.post("/api/eventos", json={"cenario": "tijuca_cabofrio_tronco"}, headers=OP)
    assert r.status_code == 404  # o recorte da demo não está nesta máquina de testes


def test_evento_sem_agente_e_agente_ocupado(sessao: SessaoCOD, recorte: Path, tmp_path):
    class Lento:
        provider = "fake"

        def executar_evento(self, ev):  # nunca chamado: o agente fica "ocupado" por fora
            raise AssertionError

    agente = AgenteEmSegundoPlano(Lento())
    web = criar_app(
        sessao,
        fila=FilaEventos(tmp_path / "ev.jsonl"),
        autorizador=Autorizador(None, exigir_segredo=False),
        agente=agente,
    )
    c = TestClient(web)
    cab = {"X-Operador": "demo"}
    r = c.post(
        "/api/eventos",
        json={"cluster": str(recorte), "trecho": "SEG001", "agente": False},
        headers=cab,
    )
    assert r.status_code == 202 and r.json()["agente"] == "desligado"
    assert c.get("/api/estado").json()["propostas"] == []

    import threading

    agente._thread = threading.Thread(target=threading.Event().wait, daemon=True)
    agente._thread.start()
    r = c.post("/api/eventos", json={"trecho": "SEG001"}, headers=cab)
    assert r.status_code == 409 and "agente em execução" in r.json()["detail"]
    assert c.get("/api/estado").json()["agente"]["ocupado"] is True


def test_agente_em_thread_registra_erro(sessao: SessaoCOD):
    class Quebrado:
        def executar_evento(self, ev):
            raise RuntimeError("sem LLM")

    agente = AgenteEmSegundoPlano(Quebrado())
    ev = Evento(tipo="falta_permanente", cluster="x", hora="2025-01-01T00:00:00+00:00")
    assert agente.tratar(ev) is True
    agente._thread.join(timeout=5)
    assert agente.estado()["erro"] == "RuntimeError: sem LLM" and agente.ocupado is False


def test_motor_morre_durante_o_agente_e_o_console_sobrevive(
    cliente: TestClient, recorte: Path, monkeypatch
):
    """Issue #48: o subprocesso do motor OpenDSS morre no meio de uma execução do agente; a falha
    vira erro da ferramenta (registrado na execução), a API continua respondendo e o evento
    seguinte roda num motor novo."""
    import bdgd_light.twin as twin
    from bdgd_light.twin.powerflow import simular_falha_do_motor

    original = twin.run_powerflow
    falhas = []

    def run_powerflow_com_falha(*args, **kwargs):
        if not falhas:
            falhas.append(1)
            simular_falha_do_motor()  # mata o filho no meio da chamada → MotorError
        return original(*args, **kwargs)

    monkeypatch.setattr(twin, "run_powerflow", run_powerflow_com_falha)
    corpo = {"cluster": str(recorte), "tipo": "pico_carga", "ctmt": "RJO001"}
    r = cliente.post("/api/eventos", json=corpo, headers=OP)
    assert r.status_code == 202, r.text
    e = cliente.get("/api/estado").json()
    assert e["agente"]["erro"] is None and e["agente"]["n_execucoes"] == 1
    assert e["motor"]["modo"] == "processo" and e["motor"]["ativo"] is False
    ultima = e["agente"]["ultima"]
    assert "NÃO convergiu" in ultima["resposta"]
    execucao = cliente.app.state.agente.execucoes[-1]
    [chamada] = [c for c in execucao["ferramentas"] if c["ferramenta"] == "run_powerflow"]
    assert chamada["ok"] is False and "morreu durante _abortar (SIGSEGV)" in chamada["erro"]

    # o servidor segue vivo e o próximo evento roda num motor recriado
    r = cliente.post("/api/eventos", json=corpo, headers=OP)
    assert r.status_code == 202, r.text
    e = cliente.get("/api/estado").json()
    assert e["agente"]["n_execucoes"] == 2 and "convergiu" in e["agente"]["ultima"]["resposta"]
    assert "NÃO convergiu" not in e["agente"]["ultima"]["resposta"]
    assert e["motor"]["ativo"] is True and e["motor"]["reinicios"] >= 1


def test_cli_serve_erros(tmp_path):
    r = runner.invoke(cli, ["serve", "--cluster", "nao_existe", "--feeders", str(tmp_path)])
    assert r.exit_code == 1 and "não encontrado" in r.output
    r = runner.invoke(cli, ["serve", "--provider", "openai", "--estado", str(tmp_path)], env={})
    assert r.exit_code == 1
