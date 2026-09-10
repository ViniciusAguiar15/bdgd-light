"""Testes do log de auditoria só de acréscimo (ADR-001, decisão 6; pedido de docs/review/PR-06)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta

import pytest
from typer.testing import CliRunner

from bdgd_light.agent.audit import (
    GENESIS,
    AuditError,
    AuditLog,
    Registro,
    calcular_hash,
    ler,
    verificar_registros,
)
from bdgd_light.cli import app

runner = CliRunner()
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def saida(resultado) -> str:
    return _ANSI.sub("", resultado.output)


def relogio(inicio: datetime = datetime(2026, 9, 10, 1, 0, tzinfo=UTC)):
    t = [inicio]

    def agora() -> datetime:
        t[0] += timedelta(seconds=1)
        return t[0]

    return agora


def test_cadeia_em_memoria_encadeia_hashes():
    log = AuditLog(agora=relogio())
    r1 = log.registrar("a", x=1)
    r2 = log.registrar("b", y="dois", z=[1, 2.5, None])
    assert (r1.seq, r2.seq) == (1, 2)
    assert r1.hash_anterior == GENESIS
    assert r2.hash_anterior == r1.hash
    assert r1.hash == calcular_hash(1, r1.ts, "a", {"x": 1}, GENESIS)
    assert len(r1.hash) == 64 and r1.hash != r2.hash
    assert r1.ts == "2026-09-10T01:00:01.000+00:00"
    assert log.verificar() == 2 and len(log) == 2 and log.ultimo_hash == r2.hash
    assert [r.tipo for r in log] == ["a", "b"]


def test_hash_e_deterministico_e_canonico():
    dados_a = {"b": 1, "a": {"y": 2, "x": 1}}
    dados_b = {"a": {"x": 1, "y": 2}, "b": 1}
    ts = "2026-09-10T01:00:00.000+00:00"
    assert calcular_hash(1, ts, "t", dados_a, GENESIS) == calcular_hash(
        1, ts, "t", dados_b, GENESIS
    )
    assert calcular_hash(1, ts, "t", dados_a, GENESIS) != calcular_hash(
        2, ts, "t", dados_a, GENESIS
    )


def test_dados_nao_serializaveis_viram_str():
    log = AuditLog(agora=relogio())
    r = log.registrar(
        "t", quando=datetime(2026, 1, 1, tzinfo=UTC), caminho=__import__("pathlib").Path("/x")
    )
    assert r.dados == {"quando": "2026-01-01 00:00:00+00:00", "caminho": "/x"}


def test_persiste_em_jsonl_e_continua_a_cadeia(tmp_path):
    caminho = tmp_path / "audit" / "log.jsonl"
    log = AuditLog(caminho, agora=relogio())
    log.registrar("um", n=1)
    log.registrar("dois", n=2)
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 2
    primeiro = json.loads(linhas[0])
    assert set(primeiro) == {"seq", "ts", "tipo", "dados", "hash_anterior", "hash"}
    assert primeiro["dados"] == {"n": 1}
    # reabrir continua do último hash
    log2 = AuditLog(caminho, agora=relogio(datetime(2026, 9, 10, 2, 0, tzinfo=UTC)))
    assert len(log2) == 2 and log2.ultimo_hash == log.ultimo_hash
    r3 = log2.registrar("tres", n=3)
    assert r3.seq == 3 and r3.hash_anterior == log.ultimo_hash
    assert AuditLog.verificar_arquivo(caminho) == 3
    assert [r.tipo for r in ler(caminho)] == ["um", "dois", "tres"]


def test_arquivo_vazio_e_linhas_em_branco(tmp_path):
    caminho = tmp_path / "log.jsonl"
    caminho.write_text("\n\n", encoding="utf-8")
    log = AuditLog(caminho)
    assert len(log) == 0 and log.ultimo_hash == GENESIS
    log.registrar("t")
    assert AuditLog.verificar_arquivo(caminho) == 1


def _gravar(tmp_path, n=3):
    caminho = tmp_path / "log.jsonl"
    log = AuditLog(caminho, agora=relogio())
    for i in range(1, n + 1):
        log.registrar("t", i=i)
    return caminho


def test_detecta_registro_alterado(tmp_path):
    caminho = _gravar(tmp_path)
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    meio = json.loads(linhas[1])
    meio["dados"]["i"] = 99
    linhas[1] = json.dumps(meio, ensure_ascii=False)
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    with pytest.raises(AuditError, match="seq=2: hash não bate"):
        AuditLog.verificar_arquivo(caminho)


def test_detecta_registro_removido_e_reordenado(tmp_path):
    caminho = _gravar(tmp_path)
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    caminho.write_text("\n".join([linhas[0], linhas[2]]) + "\n", encoding="utf-8")
    with pytest.raises(AuditError, match="sequência quebrada"):
        AuditLog.verificar_arquivo(caminho)
    caminho.write_text("\n".join([linhas[1], linhas[0], linhas[2]]) + "\n", encoding="utf-8")
    with pytest.raises(AuditError, match="sequência quebrada"):
        AuditLog.verificar_arquivo(caminho)


def test_detecta_hash_anterior_forjado():
    ts = "2026-09-10T01:00:00.000+00:00"
    h1 = calcular_hash(1, ts, "t", {}, GENESIS)
    falso = "f" * 64
    h2 = calcular_hash(2, ts, "t", {}, falso)  # hash correto para um elo errado
    regs = [Registro(1, ts, "t", {}, GENESIS, h1), Registro(2, ts, "t", {}, falso, h2)]
    with pytest.raises(AuditError, match="hash_anterior não bate"):
        verificar_registros(regs)


def test_linha_ilegivel_e_malformada(tmp_path):
    caminho = tmp_path / "log.jsonl"
    caminho.write_text("{isto não é json}\n", encoding="utf-8")
    with pytest.raises(AuditError, match="linha 1 ilegível"):
        list(ler(caminho))
    caminho.write_text('{"seq": 1}\n', encoding="utf-8")
    with pytest.raises(AuditError, match="malformado"):
        list(ler(caminho))
    with pytest.raises(AuditError):
        AuditLog(caminho)


def test_conversar_grava_rodadas_e_fim(tmp_path):
    pytest.importorskip("httpx")
    from bdgd_light.agent import SOMA, Message, conversar, fake_soma

    caminho = tmp_path / "llm.jsonl"
    log = AuditLog(caminho, agora=relogio())
    conversa = conversar(
        fake_soma(), [Message.system("s"), Message.user("Quanto é 2 + 3?")], [SOMA], audit=log
    )
    regs = log.registros
    assert [r.tipo for r in regs] == ["llm.rodada", "llm.rodada", "conversa.fim"]
    r1, r2, fim = (r.dados for r in regs)
    assert r1["rodada"] == 1 and r1["modelo"] == "fake"
    assert [m["role"] for m in r1["mensagens"]] == ["system", "user"]
    assert r1["resposta"]["tipo"] == "tool_calls"
    assert r1["resposta"]["tool_calls"][0]["ferramenta"] == "soma"
    assert r1["execucoes"] == [
        {
            "id": r1["resposta"]["tool_calls"][0]["id"],
            "ferramenta": "soma",
            "argumentos": {"a": 2.0, "b": 3.0},
            "resultado": 5.0,
        }
    ]
    assert r1["uso"]["total_tokens"] > 0
    # a rodada 2 registra só as mensagens novas (assistant + tool) e a resposta em texto
    assert [m["role"] for m in r2["mensagens"]] == ["assistant", "tool"]
    assert r2["resposta"] == {
        "tipo": "texto",
        "content": "O resultado é 5.",
        "finish_reason": "stop",
    }
    assert r2["execucoes"] == []
    assert fim["rodadas"] == 2 and fim["ferramentas_executadas"] == 1
    assert fim["uso_total"]["total_tokens"] == r1["uso"]["total_tokens"] + r2["uso"]["total_tokens"]
    assert conversa.hash_auditoria == regs[-1].hash
    assert conversa.uso_total is not None
    assert conversa.uso_total.total_tokens == fim["uso_total"]["total_tokens"]
    assert conversa.to_dict()["uso_total"] == fim["uso_total"]
    assert AuditLog.verificar_arquivo(caminho) == 3


def test_conversar_sem_audit_nao_tem_hash():
    pytest.importorskip("httpx")
    from bdgd_light.agent import SOMA, Message, conversar, fake_soma

    conversa = conversar(fake_soma(), [Message.user("olá")], [SOMA])
    assert conversa.hash_auditoria is None and conversa.rodadas == 1


def test_conversar_estourando_rodadas_grava_erro():
    pytest.importorskip("httpx")
    from bdgd_light.agent import (
        SOMA,
        FakeLLMClient,
        LLMError,
        Message,
        ToolCall,
        ToolCalls,
        conversar,
    )

    sempre_ferramenta = FakeLLMClient(
        regra=lambda msgs, tools: ToolCalls((ToolCall("c", "soma", {"a": 1, "b": 1}),))
    )
    log = AuditLog(agora=relogio())
    with pytest.raises(LLMError, match="2 rodadas"):
        conversar(sempre_ferramenta, [Message.user("x")], [SOMA], max_rodadas=2, audit=log)
    assert [r.tipo for r in log] == ["llm.rodada", "llm.rodada", "conversa.erro"]
    assert log.registros[-1].dados["rodadas"] == 2


def test_cli_audit_arquivo_inexistente_e_quebrado(tmp_path):
    r = runner.invoke(app, ["audit", str(tmp_path / "nada.jsonl")])
    assert r.exit_code == 1 and "não existe" in saida(r)
    caminho = _gravar(tmp_path, 2)
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    caminho.write_text(linhas[1] + "\n", encoding="utf-8")
    r = runner.invoke(app, ["audit", str(caminho)])
    assert r.exit_code == 1 and "cadeia inválida" in saida(r)
    caminho = _gravar(tmp_path / "ok", 2)
    r = runner.invoke(app, ["audit", str(caminho), "--mostrar", "1"])
    assert r.exit_code == 0 and "2 registro(s), cadeia íntegra" in saida(r)
