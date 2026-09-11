"""Gera ``docs/verificador.md`` a partir da matriz adversarial do verificador."""

from __future__ import annotations

from pathlib import Path

from bdgd_light.agent.verificador_adversarial import renderizar_markdown

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "docs" / "verificador.md"


def main() -> None:
    DESTINO.write_text(renderizar_markdown(), encoding="utf-8")


if __name__ == "__main__":
    main()
