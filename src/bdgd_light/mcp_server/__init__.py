"""Servidor MCP com as ferramentas de rede (grid + twin) e a sessão do COD por trás delas.

``SessaoCOD`` (domínio auditado, sem dependência do SDK) funciona só com o pacote base; o
servidor MCP (``criar_servidor``, ``servir``, ``descritores``) exige o extra ``agent``.
"""

from bdgd_light.mcp_server.sessao import (
    CLUSTERS,
    DSS_PADRAO,
    ESTADO_PADRAO,
    FEEDERS_PADRAO,
    VALIDADE_TOKEN_S,
    FilaPropostas,
    Proposta,
    RecusadoError,
    SessaoCOD,
    SessaoError,
    ferramentas_da_sessao,
)

__all__ = [
    "CLUSTERS",
    "DSS_PADRAO",
    "ESTADO_PADRAO",
    "FEEDERS_PADRAO",
    "VALIDADE_TOKEN_S",
    "FilaPropostas",
    "Proposta",
    "RecusadoError",
    "SessaoCOD",
    "SessaoError",
    "ferramentas_da_sessao",
]
