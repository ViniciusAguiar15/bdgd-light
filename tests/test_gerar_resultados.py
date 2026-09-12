"""Testes do gerador de ``docs/resultados.md``."""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path


def _carregar_modulo():
    caminho = Path(__file__).resolve().parents[1] / "scripts" / "gerar_resultados.py"
    spec = importlib.util.spec_from_file_location("gerar_resultados_script", caminho)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


modulo = _carregar_modulo()


def _escrever_csv(caminho: Path, linhas: list[dict[str, object]]) -> None:
    cabecalho = [
        "tarefa",
        "nivel",
        "repeticao",
        "acerto",
        "provider",
        "modelo",
        "exemplos",
        "compactado",
        "sequencia",
        "referencia",
        "ordem",
        "precisao",
        "desnecessarias",
        "tokens_prompt",
        "tokens_completion",
        "tokens_total",
        "tokens_informados",
        "chars_ferramentas",
        "segundos_total",
        "recusas",
        "data",
    ]
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=cabecalho)
        writer.writeheader()
        writer.writerows(linhas)


def test_gerar_resultados_e_deterministico_com_csv_sintetico(tmp_path):
    docs = tmp_path / "docs"
    bench = docs / "bench"
    _escrever_csv(
        bench / "2026-01-02-openai.csv",
        [
            {
                "tarefa": "S01",
                "nivel": "simple",
                "repeticao": 1,
                "acerto": 1,
                "provider": "openai",
                "modelo": "gpt-4.1-mini-2025-04-14",
                "exemplos": 1,
                "compactado": 1,
                "sequencia": '["get_topology"]',
                "referencia": '["get_topology"]',
                "ordem": 1.0,
                "precisao": 1.0,
                "desnecessarias": 0,
                "tokens_prompt": 100,
                "tokens_completion": 50,
                "tokens_total": 150,
                "tokens_informados": 1,
                "chars_ferramentas": 200,
                "segundos_total": 1.2,
                "recusas": 0,
                "data": "2026-01-02T12:00:00+00:00",
            },
            {
                "tarefa": "H01",
                "nivel": "hard",
                "repeticao": 1,
                "acerto": 0,
                "provider": "openai",
                "modelo": "gpt-4.1-mini-2025-04-14",
                "exemplos": 1,
                "compactado": 1,
                "sequencia": '["locate_fault", "get_topology", "restore_options", '
                '"propose_plan", "downstream_customers", "get_switch_state"]',
                "referencia": '["locate_fault", "isolate_fault", "restore_options", '
                '"propose_plan"]',
                "ordem": 0.75,
                "precisao": 0.5,
                "desnecessarias": 2,
                "tokens_prompt": 200,
                "tokens_completion": 100,
                "tokens_total": 300,
                "tokens_informados": 1,
                "chars_ferramentas": 400,
                "segundos_total": 2.4,
                "recusas": 1,
                "data": "2026-01-02T12:00:00+00:00",
            },
        ],
    )
    _escrever_csv(
        bench / "2026-01-02-openai-sem-exemplos.csv",
        [
            {
                "tarefa": "S01",
                "nivel": "simple",
                "repeticao": 1,
                "acerto": 1,
                "provider": "openai",
                "modelo": "gpt-4.1-mini-2025-04-14",
                "exemplos": 0,
                "compactado": 1,
                "sequencia": '["get_topology"]',
                "referencia": '["get_topology"]',
                "ordem": 1.0,
                "precisao": 1.0,
                "desnecessarias": 0,
                "tokens_prompt": 90,
                "tokens_completion": 40,
                "tokens_total": 130,
                "tokens_informados": 1,
                "chars_ferramentas": 180,
                "segundos_total": 1.0,
                "recusas": 0,
                "data": "2026-01-02T12:00:00+00:00",
            },
            {
                "tarefa": "H01",
                "nivel": "hard",
                "repeticao": 1,
                "acerto": 1,
                "provider": "openai",
                "modelo": "gpt-4.1-mini-2025-04-14",
                "exemplos": 0,
                "compactado": 1,
                "sequencia": '["locate_fault", "isolate_fault", "restore_options", "propose_plan"]',
                "referencia": '["locate_fault", "isolate_fault", "restore_options", '
                '"propose_plan"]',
                "ordem": 1.0,
                "precisao": 1.0,
                "desnecessarias": 0,
                "tokens_prompt": 180,
                "tokens_completion": 80,
                "tokens_total": 260,
                "tokens_informados": 1,
                "chars_ferramentas": 300,
                "segundos_total": 2.0,
                "recusas": 0,
                "data": "2026-01-02T12:00:00+00:00",
            },
        ],
    )
    _escrever_csv(
        bench / "2026-01-02-openai-sem-compactar.csv",
        [
            {
                "tarefa": "S01",
                "nivel": "simple",
                "repeticao": 1,
                "acerto": 1,
                "provider": "openai",
                "modelo": "gpt-4.1-mini-2025-04-14",
                "exemplos": 1,
                "compactado": 0,
                "sequencia": '["get_topology"]',
                "referencia": '["get_topology"]',
                "ordem": 1.0,
                "precisao": 1.0,
                "desnecessarias": 0,
                "tokens_prompt": 100,
                "tokens_completion": 50,
                "tokens_total": 150,
                "tokens_informados": 1,
                "chars_ferramentas": 999,
                "segundos_total": 1.3,
                "recusas": 0,
                "data": "2026-01-02T12:00:00+00:00",
            },
        ],
    )
    caminho_casos = bench / "2026-01-02-fora-treino-casos.csv"
    caminho_casos.parent.mkdir(parents=True, exist_ok=True)
    with caminho_casos.open("w", encoding="utf-8", newline="") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=["ctmt", "regiao", "trecho_falta"])
        writer.writeheader()
        writer.writerow({"ctmt": "AAA001", "regiao": "Centro", "trecho_falta": "TR1"})

    (docs / "bench.md").write_text(
        "38 tarefas (10 *simple*, 13 *medium*, 15 *hard*) distribuídas entre "
        "Tijuca, Ipanema e Taquara.\n\n"
        "## Resultados (2026-01-02)\n",
        encoding="utf-8",
    )
    (docs / "escopo-cidade.md").write_text(
        "Análise (2026-01-01; inventário regerado em 2026-01-02) sobre o recorte.\n\n"
        "| A Tijuca | A1, A2 | 1.000 | 100 / 10,0 / 20 | 5 (2) | "
        "2.000 UCBT, 10 trafos (1,0 MVA) | x |\n"
        "| B Ipanema | P1, P2 | 900 | 90 / 9,0 / 15 | 1 (0) — 7 interligações "
        "`EM_SUB` | 1.500 UCBT, 8 trafos (0,8 MVA) | x |\n\n"
        'Com a folga `EM_SUB`, o município perdeu 10 "ties TLCD de campo" (100 → 90) e 20 ties de '
        "campo (200 → 180), reclassificadas como de SE (50 → 70); na Light toda foram 30 chaves "
        "(40 → 70 em SE), em 12 alimentadores.\n",
        encoding="utf-8",
    )
    (docs / "mcp-ferramentas.md").write_text(
        'cluster_tijuca"\n'
        '"resumo": {"ctmt": ["A1", "A2"], "nos": 100, "trechos": 88, "km": 10.432, '
        '"chaves": 20, "ties": 5, "ties_externas": 1, "trafos": 10, '
        '"clientes": {"ucbt": 2000, "ucmt": 0, "trafos": 10, "kva": 1000.0, "total": 2000}}}\n',
        encoding="utf-8",
    )
    (docs / "grid-modelo.md").write_text(
        "Números no cluster TQR (PARNAIBA / CURUMAU / BOCARI): "
        "2.069 nós, 1.924 trechos (46,65 km), "
        "162 chaves, 35 ties (12 de chaves de CTMT fora do cluster, 7 CTMT externos), 2.068 nós "
        "energizados (o único sem tensão é um PAC solto de chave) e 16.504 UCBT.\n",
        encoding="utf-8",
    )
    (docs / "agent.md").write_text(
        "## Validação com modelos reais (2026-01-03)\n\n"
        "| cenário | sequência | proposta | verificador | rodadas | "
        "tokens (prompt+saída=total*) | LLM / ferramentas |\n"
        "|---|---|---|---|---|---|---|\n"
        "| `tijuca_cabofrio_tronco` | idem | **P-0001** | ok | 4 | "
        "32 154 + 508 = 32 662 | 14,3 s / 9,8 s |\n"
        "| `ipanema_9210` — **OpenAI** | idem | **P-0002 sem chave** | ok | 4 | "
        "32 559 + 376 = 32 935 | 10,2 s / 0,04 s |\n",
        encoding="utf-8",
    )

    saida = docs / "resultados.md"
    modulo.main(
        [
            "--bench-dir",
            str(bench),
            "--bench-doc",
            str(docs / "bench.md"),
            "--escopo-doc",
            str(docs / "escopo-cidade.md"),
            "--mcp-doc",
            str(docs / "mcp-ferramentas.md"),
            "--grid-doc",
            str(docs / "grid-modelo.md"),
            "--agent-doc",
            str(docs / "agent.md"),
            "--saida",
            str(saida),
        ]
    )
    primeiro = saida.read_text(encoding="utf-8")
    modulo.main(
        [
            "--bench-dir",
            str(bench),
            "--bench-doc",
            str(docs / "bench.md"),
            "--escopo-doc",
            str(docs / "escopo-cidade.md"),
            "--mcp-doc",
            str(docs / "mcp-ferramentas.md"),
            "--grid-doc",
            str(docs / "grid-modelo.md"),
            "--agent-doc",
            str(docs / "agent.md"),
            "--saida",
            str(saida),
        ]
    )
    segundo = saida.read_text(encoding="utf-8")

    assert primeiro == segundo
    assert "Data-base das fontes versionadas mais recentes: **2026-01-02**." in primeiro
    assert "docs/bench/2026-01-02-openai.csv (2026-01-02)" in primeiro
    assert (
        "| openai | com exemplos, compactado ★ padrão | gpt-4.1-mini-2025-04-14 | 2 | 2 | 1 | "
        "100 % | — | 0 % | 50 % | 87,5 % (4/5) | 75,0 % (4/7) |" in primeiro
    )
    assert (
        "| openai | com exemplos, compactado ★ padrão | 1/2 (50 %) | 1 | 0,50 | "
        "docs/bench/2026-01-02-openai.csv (2026-01-02) |" in primeiro
    )
    assert "| openai | sem exemplos, compactado |" in primeiro
    assert "| openai | com exemplos, sem compactação |" in primeiro
    assert "Nas colunas **ordem** e **precisão**" in primeiro
