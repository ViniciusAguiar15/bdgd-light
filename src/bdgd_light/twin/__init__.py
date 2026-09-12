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
    PREFIXO_ELEMENTO_TRECHO_MT,
    ConfiguracaoGd,
    ConversaoGpkg,
    GpkgInvalidoError,
    ResumoGdCtmt,
    cod_id_trecho_mt_de_elemento,
    converter_ctmt,
    converter_gpkg,
    dias_por_tipo,
    listar_ctmts,
    nome_elemento_trecho_mt,
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
    "ConfiguracaoGd",
    "ConversaoGpkg",
    "ErroOpenDSS",
    "GpkgInvalidoError",
    "MotorError",
    "PREFIXO_ELEMENTO_TRECHO_MT",
    "PowerFlowResult",
    "ResumoGdCtmt",
    "ScoreEletrico",
    "ampacidade_tronco",
    "cod_id_trecho_mt_de_elemento",
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
    "nome_elemento_trecho_mt",
    "nome_master_cluster",
    "ordenar_scores",
    "preparar_master_cluster",
    "run_powerflow",
    "score_eletrico",
    "trechos_tronco",
]
