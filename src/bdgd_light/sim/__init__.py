"""Simulador de eventos (faltas, picos de carga, chaves indisponíveis) sobre um cluster."""

from bdgd_light.sim.eventos import (
    APELIDOS,
    CENARIOS,
    CHAVE_INDISPONIVEL,
    FALTA_PERMANENTE,
    FALTA_TRANSITORIA,
    FILA_PADRAO,
    PICO_CARGA,
    TIPOS,
    Cenario,
    Evento,
    FilaEventos,
    Simulador,
    normalizar_tipo,
)

__all__ = [
    "APELIDOS",
    "CENARIOS",
    "CHAVE_INDISPONIVEL",
    "FALTA_PERMANENTE",
    "FALTA_TRANSITORIA",
    "FILA_PADRAO",
    "PICO_CARGA",
    "TIPOS",
    "Cenario",
    "Evento",
    "FilaEventos",
    "Simulador",
    "normalizar_tipo",
]
