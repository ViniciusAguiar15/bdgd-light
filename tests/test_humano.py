"""Lado humano nas rotas HTTP (revisão PR-12, pedidos 1–2): identidade do operador (``X-Operador``
+ segredo ``BDGD_CONSOLE_TOKEN``), decisão gravada em ``aprovada_por``/``hitl.jsonl``, execução da
proposta com o token emitido e ``hash`` da auditoria em ``GET /estado``."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from rich.console import Console

pytest.importorskip("mcp")
pytest.importorskip("opendssdirect")

from starlette.testclient import TestClient  # noqa: E402

from bdgd_light.agent.audit import AuditLog  # noqa: E402
from bdgd_light.ingest.recorte import recortar  # noqa: E402
from bdgd_light.mcp_server import SessaoCOD, SessaoError  # noqa: E402
from bdgd_light.mcp_server.humano import (  # noqa: E402
    Autorizador,
    NaoAutorizadoError,
    aprovar,
    rejeitar,
)
from bdgd_light.mcp_server.servidor import criar_servidor  # noqa: E402

CLUSTER_MINI = Path("tests/fixtures/dss/cluster_mini")


@pytest.fixture(scope="module")
def recorte(parquet_mini, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("humano_feeders")
    r = recortar(parquet_mini, ["RJO001", "RJO002"], out, console=Console(quiet=True))
    return r.cluster.gpkg


@pytest.fixture
def sessao(recorte, tmp_path) -> SessaoCOD:
    dss = tmp_path / "dss"
    shutil.copytree(CLUSTER_MINI, dss)
    s = SessaoCOD(feeders=recorte.parent, dss_out=dss, estado_dir=tmp_path / "estado")
    s.load_cluster(str(recorte))
    s.inject_fault("SEG001")
    s.propose_plan(chave="CH003", justificativa="maior margem")
    return s


def test_autorizador_modos():
    bloqueado = Autorizador(None)
    assert bloqueado.modo == "bloqueado"
    with pytest.raises(NaoAutorizadoError) as e:
        bloqueado.operador({})
    assert e.value.status == 400  # X-Operador vem antes de qualquer segredo
    with pytest.raises(NaoAutorizadoError) as e:
        bloqueado.operador({"X-Operador": "ana"})
    assert e.value.status == 503 and "BDGD_CONSOLE_TOKEN" in str(e.value)

    demo = Autorizador(None, exigir_segredo=False)
    assert demo.modo == "sem-segredo" and demo.operador({"x-operador": " ana "}) == "ana"

    seguro = Autorizador("s3gr3do")
    assert seguro.modo == "segredo"
    with pytest.raises(NaoAutorizadoError) as e:
        seguro.operador({"X-Operador": "ana"})
    assert e.value.status == 401
    with pytest.raises(NaoAutorizadoError) as e:
        seguro.operador({"X-Operador": "ana", "Authorization": "Bearer errado"})
    assert e.value.status == 401
    assert seguro.operador({"X-Operador": "ana", "Authorization": "Bearer s3gr3do"}) == "ana"
    assert seguro.operador({"X-Operador": "bia", "X-Console-Token": "s3gr3do"}) == "bia"
    assert Autorizador.do_ambiente(env={"BDGD_CONSOLE_TOKEN": "x"}).modo == "segredo"
    assert Autorizador.do_ambiente(env={}).modo == "bloqueado"


def test_aprovar_executa_e_registra_hitl(sessao: SessaoCOD):
    r = aprovar(sessao, "P-0001", operador="ana", cliente="127.0.0.1")
    assert r["erro"] is None and r["operador"] == "ana"
    assert [(p["chave"], p["estado"]) for p in r["execucao"]] == [
        ("CH001", "aberta"),
        ("CH003", "fechada"),
    ]
    assert r["proposta"]["status"] == "executada" and r["proposta"]["aprovada_por"] == "ana"
    assert r["proposta"]["token"] is None  # consumido; nunca sai em claro
    assert sessao.get_switch_state("CH003")["estado"] == "fechada"

    hitl = [json.loads(x) for x in (sessao.estado_dir / "hitl.jsonl").read_text().splitlines()]
    assert len(hitl) == 1 and hitl[0]["tipo"] == "hitl.aprovacao"
    assert hitl[0]["dados"]["operador"] == "ana" and hitl[0]["dados"]["origem"] == "http"
    assert hitl[0]["dados"]["proposta"]["token"] == "***"
    assert AuditLog(sessao.estado_dir / "hitl.jsonl").verificar() == 1

    tipos = [r.tipo for r in sessao.audit]
    assert "hitl.aprovacao" in tipos and tipos.count("mcp.chamada") >= 2


def test_aprovar_sem_executar_e_rejeitar(sessao: SessaoCOD):
    r = aprovar(sessao, "P-0001", operador="ana", executar=False)
    assert r["execucao"] == [] and r["proposta"]["status"] == "aprovada"
    assert r["proposta"]["token"] == "***"
    # rejeitar uma aprovada ainda não executada revoga o token
    r = rejeitar(sessao, "P-0001", operador="bia", motivo="prefiro CH005")
    assert r["proposta"]["status"] == "rejeitada" and r["proposta"]["token"] is None
    with pytest.raises(SessaoError):
        rejeitar(sessao, "P-0001", operador="bia")  # já rejeitada
    with pytest.raises(SessaoError):
        aprovar(sessao, "P-0001", operador="ana")
    hitl = [json.loads(x) for x in (sessao.estado_dir / "hitl.jsonl").read_text().splitlines()]
    assert [h["tipo"] for h in hitl] == ["hitl.aprovacao", "hitl.rejeicao"]
    assert hitl[1]["dados"]["motivo"] == "prefiro CH005"


def test_estado_traz_hash_da_auditoria(sessao: SessaoCOD):
    e = sessao.estado()
    assert e["hash"] == sessao.audit.ultimo_hash and e["audit_n"] == len(sessao.audit)
    assert e["cluster_demo"] is None  # o cluster_mini não é um dos clusters da demo
    vazia = SessaoCOD(estado_dir=None)
    assert vazia.estado()["hash"] is None and vazia.estado()["audit_n"] is None


def test_rotas_http_do_mcp_exigem_operador_e_segredo(sessao: SessaoCOD):
    srv = criar_servidor(sessao, Autorizador("abc"))
    with TestClient(srv.streamable_http_app()) as c:
        estado = c.get("/estado").json()
        assert estado["hash"] and estado["propostas"][0]["id"] == "P-0001"
        assert c.get("/propostas").json()[0]["token"] is None

        r = c.post("/propostas/P-0001/aprovar")
        assert r.status_code == 400 and "X-Operador" in r.json()["erro"]
        r = c.post("/propostas/P-0001/aprovar", headers={"X-Operador": "ana"})
        assert r.status_code == 401
        r = c.post(
            "/propostas/P-0001/rejeitar",
            headers={"X-Operador": "ana", "Authorization": "Bearer abc"},
            json={"motivo": "não agora"},
        )
        assert r.status_code == 200 and r.json()["proposta"]["status"] == "rejeitada"
        ok = {"X-Operador": "ana", "Authorization": "Bearer abc"}
        r = c.post("/propostas/P-0001/aprovar", headers=ok)
        assert r.status_code == 409  # já rejeitada

        sessao.propose_plan(chave="CH003")
        r = c.post(
            "/propostas/P-0002/aprovar",
            headers={"X-Operador": "ana", "X-Console-Token": "abc"},
            json={"executar": True},
        )
        assert r.status_code == 200
        assert r.json()["proposta"]["status"] == "executada"
        assert r.json()["proposta"]["aprovada_por"] == "ana"
        assert c.get("/estado").json()["propostas"][1]["executadas"] == 2


def test_rotas_http_bloqueadas_sem_segredo(sessao: SessaoCOD):
    srv = criar_servidor(sessao, Autorizador(None))
    with TestClient(srv.streamable_http_app()) as c:
        r = c.post("/propostas/P-0001/aprovar", headers={"X-Operador": "ana"})
        assert r.status_code == 503
    srv = criar_servidor(sessao, Autorizador(None, exigir_segredo=False))
    with TestClient(srv.streamable_http_app()) as c:
        r = c.post("/propostas/P-0001/aprovar", headers={"X-Operador": "ana"})
        assert r.status_code == 200 and r.json()["proposta"]["status"] == "aprovada"
