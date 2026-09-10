---
title: "agent: servidor MCP com as ferramentas de rede (grid + twin)"
labels: area:agent, phase:F3, copilot
milestone: F3 Agente
---
## Contexto
Tudo já existe como função Python (`grid`, `twin`). O servidor MCP é a fronteira entre modelos de rede e o LLM
(padrão PowerChain: descritores de ferramenta + execução verificável).

## Tarefa
`bdgd_light.mcp_server` (SDK `mcp` do extra `agent`, transporte stdio e HTTP) com sessão por cluster carregado:
`load_cluster(nome|gpkg)`, `get_topology(ctmt)` (resumo + lista de chaves/ties), `get_switch_state`,
`inject_fault(trecho)` (simula: abre religador do CTMT, marca trecho em falta), `locate_fault()` (zona entre
chaves com indicação de falta), `isolate_fault()` → `Isolamento.to_dict()`, `downstream_customers(no|chave)`,
`restore_options()` → opções com `manobras` e, se `twin.score_eletrico` (#18) existir, o veredito elétrico,
`run_powerflow(manobras=[])`, `propose_plan(opcao)` → cria proposta pendente com id e sequência,
`set_switch(chave, estado, approval_token)` → **recusa sem token válido**; `approve(proposta_id)` só via console/CLI
humano (emite token). Toda chamada vai para o `AuditLog` (JSONL encadeado) com argumentos e resultado.
Descritores em português, curtos, com unidades. `bdgd-light mcp --cluster tijuca` sobe o servidor;
`bdgd-light mcp --listar` imprime as ferramentas.

## Critérios de aceite
- [ ] Testes com cluster sintético (`cluster_mini`): fluxo inject → locate → isolate → restore_options → propose →
      set_switch recusado sem token → approve → set_switch ok; audit verificável.
- [ ] `docs/mcp-ferramentas.md` com a tabela de ferramentas, argumentos, retorno e exemplo de JSON.
