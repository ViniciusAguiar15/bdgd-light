#!/usr/bin/env python3
"""Lista os modelos disponíveis no provedor LLM configurado, destacando os que suportam
*tool calling* (OpenAI/Claude/Mistral/Llama 3.x…).

Provedor pelo ambiente (mesma regra de ``bdgd_light.agent.cliente_do_ambiente``):
  BDGD_LLM_ENDPOINT + BDGD_LLM_TOKEN  → API compatível com a OpenAI (Azure AI Foundry, OpenAI,
                                         Ollama http://localhost:11434/v1/chat/completions…)
  GITHUB_TOKEN                        → GitHub Models (aposentado em 30/07/2026: responde 410)

Uso:
    uv run scripts/listar_modelos.py [--endpoint URL] [--tools]
    (--tools: só os modelos que chamam ferramentas)
"""

from __future__ import annotations

import argparse
import os
import sys

from bdgd_light.agent import (
    ENV_ENDPOINT,
    ENV_GITHUB_TOKEN,
    ENV_TOKEN,
    GitHubModelsClient,
    LLMError,
    OpenAICompatClient,
)

# Famílias com tool calling nativo (heurística pelo id; confirme na ficha do modelo).
FAMILIAS_TOOL_CALLING = (
    "gpt-4",
    "gpt-5",
    "o1",
    "o3",
    "o4",
    "claude",
    "mistral",
    "ministral",
    "llama-3.1",
    "llama-3.2",
    "llama-3.3",
    "llama-4",
    "qwen2.5",
    "qwen3",
    "command-r",
    "deepseek",
    "phi-4",
    "grok",
    "gemini",
)


def suporta_tool_calling(modelo: dict) -> bool:
    caps = modelo.get("capabilities") or modelo.get("supported_features") or []
    if isinstance(caps, dict):
        caps = [k for k, v in caps.items() if v]
    texto = " ".join(str(c) for c in caps).lower()
    if "tool" in texto or "function" in texto:
        return True
    ident = str(modelo.get("id") or modelo.get("name") or "").lower()
    return any(f in ident for f in FAMILIAS_TOOL_CALLING)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--endpoint", help=f"URL …/chat/completions (padrão: ${ENV_ENDPOINT})")
    p.add_argument("--tools", action="store_true", help="mostra só modelos com tool calling")
    args = p.parse_args(argv)

    endpoint = args.endpoint or os.environ.get(ENV_ENDPOINT)
    try:
        if endpoint:
            cliente = OpenAICompatClient(endpoint)
            origem = cliente.url_modelos
        elif os.environ.get(ENV_GITHUB_TOKEN):
            cliente = GitHubModelsClient()
            origem = cliente.url_modelos
        else:
            print(
                f"Defina {ENV_ENDPOINT} e {ENV_TOKEN} (ou {ENV_GITHUB_TOKEN}); nada hardcoded.",
                file=sys.stderr,
            )
            return 2
        modelos = cliente.listar_modelos()
    except LLMError as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 2

    linhas = []
    for m in modelos:
        ident = str(m.get("id") or m.get("name") or "?")
        dono = str(m.get("publisher") or m.get("owned_by") or m.get("provider") or "")
        tools = suporta_tool_calling(m)
        if args.tools and not tools:
            continue
        linhas.append((ident, dono, tools))
    linhas.sort(key=lambda x: (not x[2], x[0]))

    print(f"Origem: {origem}")
    print(f"{'MODELO':<48} {'PUBLISHER':<16} TOOL CALLING")
    print("-" * 80)
    for ident, dono, tools in linhas:
        print(f"{ident:<48} {dono:<16} {'✓' if tools else '–'}")
    print(f"\n{len(linhas)} modelos ({sum(1 for x in linhas if x[2])} com tool calling).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
