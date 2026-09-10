# Servidor MCP — ferramentas de rede para o agente (issue #32)

`bdgd_light.mcp_server` é a fronteira entre os modelos de rede (`grid` = grafo, `twin` = gêmeo
OpenDSS) e o LLM, no padrão PowerChain: **descritores de ferramenta** em português com unidades +
**execução verificável** (toda chamada vai para o log de auditoria encadeado por hash). O modelo
raciocina e propõe; **nenhuma manobra é executada sem aprovação humana** (HITL).

```
                                 ┌──────────────────────────────┐
  agente (LLM) ──MCP stdio/http─►│ SessaoCOD                    │──► AuditLog  data/agent/audit.jsonl
                                 │  rede (grafo) + gêmeo OpenDSS│──► FilaPropostas data/agent/propostas.json
  operador ── bdgd-light aprovar ─┤  propostas pendentes/aprov.  │◄── token de aprovação
            ── POST /propostas/…─┘                              │
                                 └──────────────────────────────┘
```

## Subir e usar

```bash
uv sync --extra agent --extra twin
uv run bdgd-light mcp --listar                       # tabela de ferramentas (nome, argumentos, descrição)
uv run bdgd-light mcp --cluster tijuca               # stdio (para clientes MCP locais: Copilot, Claude, mcp-cli…)
uv run bdgd-light mcp --cluster ipanema --transporte http --porta 8765
#   MCP em http://127.0.0.1:8765/mcp · GET /estado · GET /propostas · POST /propostas/P-0001/aprovar
uv run bdgd-light aprovar                            # fila de propostas (data/agent/propostas.json)
uv run bdgd-light aprovar P-0001                     # aprova → imprime o approval_token (validade 30 min)
uv run bdgd-light aprovar P-0002 --rejeitar --motivo "prefiro a outra fonte"
uv run bdgd-light audit data/agent/audit.jsonl --mostrar 5   # confere a cadeia de auditoria
```

| opção de `mcp` | padrão | descrição |
|---|---|---|
| `--cluster` | — | nome da demo (`tijuca`, `ipanema`, `taquara`) ou caminho de um GeoPackage do recorte; sem ele o modelo chama `load_cluster` |
| `--listar` | off | só imprime as ferramentas e sai |
| `--transporte` | `stdio` | `stdio` (stdout é o canal do protocolo; mensagens humanas vão para stderr) ou `http` (*streamable HTTP* em `/mcp` + rotas humanas) |
| `--host`, `--porta` | `127.0.0.1`, `8765` | endereço do transporte http |
| `--feeders` | `data/feeders` | pasta dos recortes (`cluster_tijuca.gpkg`…) |
| `--dss-out` | `data/dss/gpkg` | modelos OpenDSS por CTMT; os que faltarem são convertidos do GPKG na primeira necessidade (`restore_options --score`, `run_powerflow`) e o Master do cluster é escrito em `<dss-out>/cluster_<A>-<B>/Master_DU01_base.dss` |
| `--estado` | `data/agent` | `audit.jsonl` (auditoria do servidor), `propostas.json` (fila compartilhada com `aprovar`) e `hitl.jsonl` (auditoria das decisões humanas) |
| `--dia`, `--mes` | `DU`, `1` | curva de carga do gêmeo |

Configuração de cliente MCP (stdio), por exemplo em `.vscode/mcp.json` ou `~/.copilot/mcp-config.json`:

```json
{ "servers": { "bdgd-light": { "command": "uv", "args": ["run", "bdgd-light", "mcp", "--cluster", "tijuca"] } } }
```

## Ferramentas

Nomes em inglês (convenção da literatura FLISR/PowerChain); descrições, campos e unidades em português.
`ctmt`, `chave`, `trecho` e `no` são os `COD_ID` da BDGD (CTMT, UNSEMT, SSDMT e PAC). `clientes` é
sempre `{ucbt, ucmt, trafos, kva, total}`; `sem_tensao` é `{n_nos, clientes}`.

| ferramenta | argumentos | retorno | muda estado? |
|---|---|---|---|
| `load_cluster` | `cluster` (nome da demo ou caminho `.gpkg`) | `cluster`, `gpkg`, `resumo` (nós, km, chaves, ties, clientes, energizados), `religadores` por CTMT | sim: troca o cluster, zera a falta, expira propostas pendentes |
| `get_topology` | `ctmt?`, `com_chaves?=true` | `resumo` (fontes, religadores, nós, trechos, km, chaves, chaves_NA, ties, clientes, energizados, sem_tensao, falta), `chaves[]` (estado, normal NF/NA, tlcd, PACs, `energizado_por`), `ties[]` | não |
| `get_switch_state` | `chave` | `chave, ctmt, estado (aberta/fechada), normal, tlcd, tip_unid, externa, pac[2], energizado_por[2]` | não |
| `inject_fault` | `trecho` (SSDMT) | `religador` (primeira chave fechada entre a fonte e o trecho, **aberto** pela proteção), `chaves_com_indicacao`, `sem_tensao` | sim (**simulador**): abre o religador e marca a falta |
| `locate_fault` | — | `zona` (nós, trechos, clientes entre chaves), `chaves_com_indicacao` na ordem fonte→falta, `ultima_indicacao`, `chaves_fronteira` a abrir | não |
| `isolate_fault` | — | `Isolamento.to_dict()` (`chaves`, `zona`, `desligados`, `clientes_zona`, `clientes_desligados`, `manobras`) + `religador`, `religar_apos_isolar`, `reenergizados_ao_religar`, `sequencia` (só o que ainda falta manobrar) | não (plano) |
| `downstream_customers` | `no?` ou `chave?` (exatamente um) | `referencia, tipo, energizado_por, n_nos, clientes` — quem perde tensão sem esse nó/chave | não |
| `restore_options` | `score?=true`, `vmin?=0.93`, `vmax?=1.05` | `desligados`, `n_opcoes`, `score` (master, limites, tempo, viáveis), `opcoes[]` (chave NA, fonte, tlcd, clientes recuperados, `manobras` ordenadas e `score` = veredito elétrico de `twin.score_eletrico`: `i_disjuntor_a`, `i_nominal_a`, `margem_disjuntor`, `vmin/vmax_mt_pu`, `sobrecargas_mt`, `perdas_kw`, `viavel`, `motivos`). Ordem: viáveis → maior margem → mais clientes | não (gêmeo) |
| `run_powerflow` | `manobras?=[]` (`[{acao: abrir\|fechar, chave}]`), `vmin?`, `vmax?` | fluxo no estado atual + manobras: `convergiu`, `vmin/vmax_pu`, `violacoes`, `piores_barras`, `sobrecargas` (%), `perdas_kw`, `fontes_kw`, `fontes_a`, `comandos_dss`, `manobras_aplicadas` | não (gêmeo) |
| `propose_plan` | `chave?` (NA a fechar; sem ela: só isolar e religar), `justificativa?` | `Proposta` (`id` P-0001…, `status=pendente`, `manobras`, `clientes`, `score`, `ja_satisfeitas`, `proximo_passo`, `n_passos`, `token=null`) | sim: cria proposta **pendente** |
| `get_proposal` | `proposta_id` | `Proposta`; se aprovada por humano, traz o `approval_token` | não |
| `set_switch` | `chave`, `estado` (`aberta`/`fechada`), `approval_token?` | `executado, chave, estado, proposta, aprovada_por, aprovada_em, passo, n_passos, proposta_status, sem_tensao` | **sim, só com token válido e só o próximo passo da proposta** |

`approve`/`reject` **não são ferramentas do modelo**: só o humano aprova, pela CLI (`bdgd-light aprovar`),
pelas rotas HTTP (`POST /propostas/{id}/aprovar|rejeitar`, corpo `{"operador": …, "motivo": …}`) ou pelo
console (#35), que escrevem em `propostas.json`; o servidor sincroniza o arquivo antes de checar o token.

### Regras de segurança de `set_switch`

1. Sem `approval_token`, ou com token que não casa (comparação em tempo constante) → **recusa**
   (`mcp.recusa` na auditoria).
2. Proposta `rejeitada`, `executada` ou `expirada` (validade padrão 30 min; `--validade`) → recusa.
3. A manobra tem de ser **exatamente o próximo passo** da proposta (abrir fronteira → fechar religador
   se aplicável → fechar NA). Fechar o NA antes de abrir a fronteira é recusado — nunca se fecha um anel
   sobre a falta.
4. Ao executar o último passo a proposta vira `executada` e o token é anulado.
5. `load_cluster` expira todas as propostas pendentes/aprovadas do cluster anterior.

## Exemplo — falta no tronco do RJO001 (cluster sintético `cluster_mini`)

```jsonc
// inject_fault {"trecho": "SEG001"}  → o religador CH008 abre
{"trecho": "SEG001", "ctmt": "RJO001", "fonte": "RJO001", "religador": "CH008",
 "chaves_com_indicacao": ["CH008"],
 "sem_tensao": {"n_nos": 9, "clientes": {"ucbt": 4, "ucmt": 1, "trafos": 2, "kva": 120.0, "total": 5}}}

// locate_fault {}
{"trecho": "SEG001", "ctmt": "RJO001", "religador": "CH008", "chaves_com_indicacao": ["CH008"],
 "ultima_indicacao": "CH008",
 "zona": {"nos": ["RJO001_MT_1", "RJO001_MT_2"], "trechos": ["SEG001"],
          "clientes": {"ucbt": 1, "ucmt": 0, "trafos": 1, "kva": 45.0, "total": 1}},
 "chaves_fronteira": ["CH001", "CH008"], "sem_tensao": {"n_nos": 9, "clientes": {"total": 5, "...": "..."}}}

// isolate_fault {}  → CH008 já está aberto; só falta abrir CH001
{"trecho": "SEG001", "chaves": ["CH001", "CH008"], "zona": ["RJO001_MT_1", "RJO001_MT_2"],
 "desligados": ["RJO001_MT_3", "RJO001_MT_4", "RJO001_MT_5", "RJO001_MT_6", "RJO002_MT_7"],
 "clientes_zona": {"total": 1, "...": "..."}, "clientes_desligados": {"ucbt": 3, "ucmt": 1, "trafos": 1, "kva": 75.0, "total": 4},
 "manobras": [{"acao": "abrir", "chave": "CH001"}, {"acao": "abrir", "chave": "CH008"}],
 "religador": "CH008", "religar_apos_isolar": false, "reenergizados_ao_religar": null,
 "sequencia": [{"acao": "abrir", "chave": "CH001"}]}

// restore_options {"score": true}
{"trecho": "SEG001", "desligados": {"n_nos": 5, "clientes": {"total": 4, "...": "..."}}, "n_opcoes": 2,
 "score": {"master": ".../cluster_RJO001-RJO002/Master_DU01_base.dss", "vmin": 0.93, "vmax": 1.05, "tempo_s": 0.23, "viaveis": 2},
 "opcoes": [
   {"chave": "CH003", "ctmt_chave": "RJO001", "fonte": "RJO002", "tlcd": true, "tip_unid": "32", "externa": false,
    "clientes": {"ucbt": 3, "ucmt": 1, "trafos": 1, "kva": 75.0, "total": 4},
    "clientes_fonte": {"total": 2, "kva": 112.5, "...": "..."},
    "manobras": [{"acao": "abrir", "chave": "CH001"}, {"acao": "fechar", "chave": "CH003"}], "n_nos": 5,
    "score": {"fonte": "RJO002", "convergiu": true, "i_disjuntor_a": 16.2, "i_nominal_a": 200.0,
              "margem_disjuntor": 0.919, "vmin_mt_pu": 1.044, "vmax_mt_pu": 1.045, "sobrecargas_mt": [],
              "carregamento_max_mt_pct": 8.1, "perdas_kw": 2.08, "viavel": true, "motivos": [], "ajustes": []}},
   {"chave": "CH005", "fonte": "RJO002", "tlcd": false, "...": "..."}]}

// propose_plan {"chave": "CH003", "justificativa": "maior margem; tie telecomandada"}
{"id": "P-0001", "criada_em": "2026-09-10T16:02:20+00:00", "cluster": "cluster_RJO001-RJO002",
 "falta": "SEG001", "chave": "CH003", "fonte": "RJO002",
 "manobras": [{"acao": "abrir", "chave": "CH001"}, {"acao": "fechar", "chave": "CH003"}],
 "clientes": {"total": 4, "...": "..."}, "score": {"viavel": true, "margem_disjuntor": 0.919, "...": "..."},
 "ja_satisfeitas": ["CH008"], "status": "pendente", "token": null, "aprovada_em": null, "aprovada_por": null,
 "expira_em": null, "motivo": "maior margem; tie telecomandada", "executadas": 0,
 "proximo_passo": {"acao": "abrir", "chave": "CH001"}, "n_passos": 2}

// set_switch {"chave": "CH001", "estado": "aberta"}  → erro (is_error=true)
"manobra abrir CH001 recusada: sem token de aprovação válido (peça aprovação humana da proposta)"

// $ bdgd-light aprovar P-0001 --operador operadora
//   ✔ P-0001 aprovada por operadora até 2026-09-10T16:32:20+00:00 — sequência: abrir CH001 → fechar CH003
//   approval_token: DuhYFhtCsNdvduAOy8YUEO0Z
// get_proposal {"proposta_id": "P-0001"}  → status "aprovada", token "DuhYFhtCsNdvduAOy8YUEO0Z"

// set_switch {"chave": "CH003", "estado": "fechada", "approval_token": "Duh…"}  → erro: fora de sequência
"manobra fechar CH003 fora de sequência na proposta P-0001: próximo passo é abrir CH001"

// set_switch {"chave": "CH001", "estado": "aberta", "approval_token": "Duh…"}
{"executado": true, "chave": "CH001", "estado": "aberta", "proposta": "P-0001", "aprovada_por": "operadora",
 "aprovada_em": "2026-09-10T16:02:20+00:00", "passo": 1, "n_passos": 2, "proposta_status": "aprovada",
 "sem_tensao": {"n_nos": 9, "clientes": {"total": 5, "...": "..."}}}

// set_switch {"chave": "CH003", "estado": "fechada", "approval_token": "Duh…"}
{"executado": true, "chave": "CH003", "estado": "fechada", "proposta": "P-0001", "passo": 2, "n_passos": 2,
 "proposta_status": "executada",
 "sem_tensao": {"n_nos": 4, "clientes": {"ucbt": 1, "ucmt": 0, "trafos": 1, "kva": 45.0, "total": 1}}}
```

Resultado: dos 5 clientes sem tensão após a atuação do religador, 4 voltam pelo RJO002 via CH003
(margem de 92 % no disjuntor, tensões dentro de 0,93–1,05 pu); só o cliente da zona em falta segue
desligado, como esperado.

## Auditoria

Cada chamada gera um registro em `audit.jsonl` (formato do `AuditLog`: `seq`, `ts`, `tipo`, `dados`,
`hash`, `hash_anterior`) — `mcp.chamada` com `ferramenta`, `argumentos`, `ms`, `cluster`, `resultado`
(compactado: listas com mais de 30 itens e textos com mais de 300 caracteres truncados) e `resultado_sha256` do resultado
completo; `mcp.recusa` (token ausente/inválido/vencido, fora de sequência) e `mcp.erro` com `erro`;
`hitl.aprovacao`/`hitl.rejeicao` quando a decisão passa pela sessão. **Tokens nunca vão em claro**:
argumentos e resultados têm `approval_token`/`token` substituídos por `sha256:<12 hex>` — o mesmo
prefixo aparece na aprovação e nas execuções, ligando decisão humana e manobra.

```json
{"dados":{"argumentos":{"approval_token":"sha256:c30bd3723955","chave":"CH003","estado":"fechada"},
 "cluster":"cluster_RJO001-RJO002","ferramenta":"set_switch","ms":0.1,
 "resultado":{"aprovada_em":"2026-09-10T16:02:20+00:00","aprovada_por":"operadora","chave":"CH003","estado":"fechada",
              "executado":true,"n_passos":2,"passo":2,"proposta":"P-0001","proposta_status":"executada",
              "sem_tensao":{"clientes":{"kva":45.0,"total":1,"trafos":1,"ucbt":1,"ucmt":0},"n_nos":4}},
 "resultado_sha256":"abb4de6c…"},
 "hash":"855eddde…","hash_anterior":"4cabf9de…","seq":10,"tipo":"mcp.chamada","ts":"2026-09-10T16:02:20.545+00:00"}
```

A CLI `aprovar` mantém a própria cadeia em `hitl.jsonl` (`hitl.aprovacao`/`hitl.rejeicao` com a
proposta e o operador). `bdgd-light audit ARQUIVO` verifica qualquer uma das duas.

## Decisões de projeto

- **Domínio sem SDK**: `SessaoCOD` é Python puro (grafo + gêmeo + fila + auditoria); o `MCPServer` é
  uma camada fina de *wrappers* tipados (`servidor.py`). O agente da #34 pode usar a sessão em processo
  (sem JSON-RPC), e os testes exercitam o domínio direto.
- **Visão de plano**: depois que o religador abre, o grafo real não tem mais "nós a jusante da falta";
  `locate/isolate/restore_options/propose` raciocinam sobre uma cópia com o religador fechado e
  devolvem só a `sequencia` que ainda falta (chaves já abertas vão em `ja_satisfeitas`).
- **Sequência forçada**: abrir fronteira → (fechar religador, se a falta não estiver colada nele) →
  fechar NA. A ordem é a garantia contra fechar um anel sobre a falta.
- **Token pela ferramenta `get_proposal`**: o agente não recebe o token do humano fora do canal; ele
  pergunta pela proposta e, se aprovada, o token vem na resposta — tudo auditado (mascarado).
- **Fila em arquivo** (`propostas.json`): permite a aprovação em outro processo (CLI hoje, console F3
  depois) sem o servidor MCP precisar de banco.
- SDK `mcp` **1.10+ e 2.x**: `servidor.py` importa `MCPServer` (2.x) ou `FastMCP` (1.x) — em
  Python < 3.13 o `bdgd2opendss` fixa `typing-extensions==4.12.2` e trava o `mcp` em 1.x, que é o que
  o CI (3.11/3.12) instala. Retorno `dict` vira `structured_content`/`structuredContent`; `ToolError`
  → `is_error=true` no cliente; rotas humanas via `custom_route` no app Starlette do transporte HTTP
  (no 1.x o endpoint MCP redireciona `/mcp` → `/mcp/`). `cliente_em_memoria(srv)` e `campo(obj,
  "is_error")` escondem a diferença nos testes.

## Pendências

- Agente orquestrador/verificador que consome estas ferramentas (#34) e console com fila de
  aprovação (#35).
- Sessão única por processo (um cluster, uma falta). Vários operadores/faltas simultâneas ficam para
  depois do MVP.
- `inject_fault` assume proteção só no religador do CTMT (sem fusíveis/religadores intermediários);
  `chaves_com_indicacao` são as chaves fechadas no caminho fonte→falta.
