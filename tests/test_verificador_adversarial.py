"""Suíte adversarial do verificador determinístico sem dependência de LLM."""

from __future__ import annotations

from pathlib import Path

import pytest

from bdgd_light.agent.verificador_adversarial import (
    CASOS_ADVERSARIAIS,
    TIJUCA,
    avaliar_caso,
    primeiro_gate_reprovado,
    renderizar_markdown,
)

pytestmark = pytest.mark.skipif(not TIJUCA.exists(), reason=f"recorte real {TIJUCA} ausente")


@pytest.mark.parametrize("caso", CASOS_ADVERSARIAIS, ids=[caso.id for caso in CASOS_ADVERSARIAIS])
def test_verificador_reprova_matriz_adversarial(caso):
    veredito = avaliar_caso(caso.id)

    assert veredito.ok is False
    assert primeiro_gate_reprovado(veredito) == caso.gate
    assert veredito.checagens[caso.gate] is False
    assert caso.mensagem in "\n".join(veredito.problemas)


def test_docs_verificador_sincronizado_com_matriz():
    caminho = Path("docs/verificador.md")
    assert caminho.read_text(encoding="utf-8") == renderizar_markdown()
