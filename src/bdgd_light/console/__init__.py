"""Backend HTTP do console do operador (``bdgd-light serve``): FastAPI sobre a ``SessaoCOD``.

Expõe, sob ``/api``: a fila de eventos do simulador, o estado do grafo em GeoJSON (recolore o
mapa), as propostas do agente (com alternativas e veredito elétrico), aprovação/rejeição humana
com identidade do operador (``mcp_server.humano``), a trilha de auditoria e a injeção de eventos
em modo demo — que dispara o agente orquestrador em segundo plano. Serve também o console
compilado (``console/dist``) quando existe.
"""

from bdgd_light.console.api import AgenteEmSegundoPlano, criar_app

__all__ = ["AgenteEmSegundoPlano", "criar_app"]
