"""Gêmeo elétrico: conversão BDGD → OpenDSS (bdgd2opendss ou direto do GPKG do recorte) e fluxo
de potência (OpenDSSDirect)."""

from bdgd_light.twin.cluster import (
    comandos_manobras,
    montar_master_cluster,
    nome_master_cluster,
    preparar_master_cluster,
)
from bdgd_light.twin.convert import (
    converter,
    corrigir_bancos_monofasicos,
    escolher_master,
    listar_masters,
    localizar_pasta,
)
from bdgd_light.twin.gpkg2dss import (
    DIAS,
    ConversaoGpkg,
    GpkgInvalidoError,
    converter_ctmt,
    converter_gpkg,
    dias_por_tipo,
    listar_ctmts,
)
from bdgd_light.twin.powerflow import (
    ESTABILIZADORES,
    ErroOpenDSS,
    MotorError,
    PowerFlowResult,
    estado_motor,
    run_powerflow,
)
from bdgd_light.twin.score import (
    ScoreEletrico,
    ampacidade_tronco,
    ordenar_scores,
    score_eletrico,
    trechos_tronco,
)

__all__ = [
    "DIAS",
    "ESTABILIZADORES",
    "ConversaoGpkg",
    "ErroOpenDSS",
    "GpkgInvalidoError",
    "MotorError",
    "PowerFlowResult",
    "ScoreEletrico",
    "ampacidade_tronco",
    "comandos_manobras",
    "converter",
    "converter_ctmt",
    "converter_gpkg",
    "corrigir_bancos_monofasicos",
    "dias_por_tipo",
    "escolher_master",
    "estado_motor",
    "listar_ctmts",
    "listar_masters",
    "localizar_pasta",
    "montar_master_cluster",
    "nome_master_cluster",
    "ordenar_scores",
    "preparar_master_cluster",
    "run_powerflow",
    "score_eletrico",
    "trechos_tronco",
]
