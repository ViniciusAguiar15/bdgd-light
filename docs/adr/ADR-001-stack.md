# ADR-001 — Stack e arquitetura do MVP

| | |
|---|---|
| Status | **Aceita** (decisões 1–7 já implementadas em `main`; 8–11 propostas para as fases F1/F3, a confirmar nas issues #4 e #7) |
| Data | 2026-09-09 |
| Origem | `docs/PLANO.md`, `docs/escopo-alimentadores.md`, `docs/bdgd-relacoes.md`, `docs/grid-modelo.md`, `docs/spike-opendss.md`, revisões em `docs/review/` |
| Issue | #8 |

Uma ADR curta por decisão: **contexto → decisão → consequências**. Quando a decisão já foi
exercitada com a BDGD Light 2025 (382, V11), o número que a justificou está registrado.

---

## 1. Python 3.11+ gerenciado por `uv`; CLI única `bdgd-light` (typer)

**Contexto.** O projeto é uma POC com muitas dependências nativas (GDAL via pyogrio, shapely 2,
pyarrow, OpenDSS) e dois perfis de uso: mantenedor no macOS e Copilot coding agent/Actions em
Linux. Precisamos de instalação reprodutível e comandos reproduzíveis nas issues.

**Decisão.** `uv` para ambiente, lock (`uv.lock` versionado) e execução (`uv run …` em todo comando
Python; `uv add` para dependências). Um único entry point `bdgd-light` (typer + rich) com um
subcomando por capacidade (`export`, `inventario`, `vizinhos`, `recortar`, `grafo`, `dss`, …);
extras opcionais por área (`twin`, `agent`, `dev`). Testes com pytest sobre fixtures sintéticas
(`tests/fixtures/gerar_fixture.py`); dados reais nunca entram no git (`data/`).

**Consequências.** Instalação em segundos e idêntica no CI (`uv sync --extra dev --extra twin`,
Python 3.11 e 3.12). Dependências mal declaradas por terceiros são corrigidas no `[tool.uv]`
(ex.: `override-dependencies` para o `pywin32` que o bdgd2opendss exige sem marcador de
plataforma). Cada issue traz o comando `uv run bdgd-light …` para o mantenedor validar com a base
real.

## 2. GeoParquet/Parquet como formato intermediário; GeoPackage para recortes

**Contexto.** A BDGD chega como FileGDB (`.gdb`, 43 camadas; SSDMT com 1,0 M de trechos, UCBT_tab
com 5,0 M de linhas, RAMLIG com 3,8 M). Ler o GDB a cada análise é lento e várias camadas-chave da
Light 2025 são **tabelas** (CTMT, UCBT_tab, UCMT_tab, RAMLIG, CRVCRG…), não feições.

**Decisão.** `bdgd-light export` lê o GDB em lotes pelo *stream* Arrow do GDAL (pyogrio) e grava
**GeoParquet** (geometria WKB, CRS EPSG:4674 preservado) para camadas geográficas e **Parquet** para
tabelas, uma pasta por base (`data/parquet/`). A leitura a jusante (`ingest/parquet.py`) empurra os
filtros por CTMT ao pyarrow. Recortes por alimentador (`bdgd-light recortar`) saem como **GeoPackage**
(um por CTMT + um do cluster) com `meta.json`, porque GPKG abre direto no QGIS e carrega camadas
mistas (feições + tabelas) num arquivo só.

**Consequências.** Exportação da Light 2025 em minutos com pico de memória < 500 MB; filtros por CTMT
em segundos. Dois formatos para manter (Parquet para pipelines, GPKG para pessoas e para o grafo).
O bdgd2opendss **não** lê nenhum dos dois (decisão 4).

## 3. Interligações entre alimentadores detectadas geometricamente; cluster de referência TQR

**Contexto.** Na BDGD da Light não existe PAC compartilhado entre CTMT: a chave NA de interligação
pertence a um CTMT e o trecho do vizinho termina a poucos centímetros dela. A relação "tie" não está
em nenhuma coluna.

**Decisão.** Tie = `UNSEMT` com `P_N_OPE = "A"` a até **2 m** (`--raio-tie`) de uma extremidade de
`SSDMT` de **outro** CTMT, calculada em CRS métrico (UTM SIRGAS 2000, EPSG:31983 para o Rio) com
índice espacial (`ingest/interligacoes.py`). Chaves NA dentro do polígono da SE são "ties de SE" e
ficam fora do *score* do inventário e das opções de restauração por padrão (`--sem-se`, `ties_na_se`;
revisão PR-02). A escolha dos alimentadores da demo usa esse score: cluster **TQR0007 (LDA
PARNAIBA) / TQR33859 (LDA CURUMAU) / TQR33862 (LDA BOCARI)**, mesma SE, interligados entre si por
ties de campo telecomandadas — o cluster PDG (MENEZES/XINGU/DANTAS) foi descartado porque só se
"interligava" por disjuntores de SE (`docs/escopo-alimentadores.md`).

**Consequências.** As ties viram arestas do grafo entre PAC distintos (`PAC` ↔ `PAC_VIZ`) e, no
gêmeo OpenDSS, um jumper `Line.TIE_<chave>_<n>` ao fechar a chave. Regras de junção entre camadas
documentadas em `docs/bdgd-relacoes.md`. O raio de 2 m é um parâmetro: com 50 m aparecem falsos
positivos (chaves NA internas ao próprio alimentador).

## 4. Gêmeo elétrico em OpenDSS via bdgd2opendss + OpenDSSDirect.py

**Contexto.** Precisamos de fluxo de potência trifásico com o modelo de carga da ANEEL (curvas
CRVCRG) para validar manobras. Escrever um conversor BDGD → OpenDSS completo (SEGCON, UNTRMT,
RAMLIG, UCBT_tab, GD…) é trabalho grande e já existe um conversor público mantido pela comunidade
brasileira.

**Decisão.** `bdgd2opendss` (≥ 1.2) como conversor, orquestrado por `twin/convert.py` (idempotente,
36 Masters DU/SA/DO × mês por CTMT), e **OpenDSSDirect.py** (dss-python, DSS C-API) como motor
in-process (`twin/powerflow.py`). Resolvemos em `snapshot` de pico e aplicamos — registrando em
`PowerFlowResult.ajustes` — a cascata de estabilizadores `maxiterations=100` → `vminpu=0.9` →
`model=2` quando o modelo bruto não converge. O conversor mínimo próprio fica como plano B só se o
bdgd2opendss deixar de atender (`docs/spike-opendss.md`).

**Consequências.** TQR0007 convertido em 180 s sem ajuste na BDGD e resolvido em 0,5 s; o cluster TQR
(18,5 mil barras, 33 mil cargas) em 1,2 s. Contras assumidos: o bdgd2opendss só lê o `.gdb` inteiro
(não o recorte GPKG) e arrasta dependências de GUI; chaves NA saem comentadas e cada CTMT é um
circuito — resolvido por `twin/cluster.py` (Master único com uma `Vsource` por CTMT, `GD_BT` fora
por padrão porque diverge, `Set AllowDuplicates=yes`). Qualidade de dado da BDGD (ramais `RAMLIG.COMP`
de centenas de metros) aparece como subtensão BT e é reportada, não corrigida.

## 5. Topologia em networkx, separada do gêmeo

**Contexto.** Localizar chaves de isolamento, contar clientes a jusante e enumerar ties que
restauram um trecho são perguntas de **conectividade**, que precisam de resposta em milissegundos e
de estado de chaves manipulável, independentemente do fluxo de potência.

**Decisão.** `grid/rede.py`: grafo `networkx.Graph` por alimentador (`Feeder`) ou cluster
(`Cluster`) com nós = PAC, arestas = trechos SSDMT e chaves UNSEMT (atributos `normal`, `aberta`,
`tlcd`, `externa`), energização por BFS a partir do `PAC_INI`, `isolate_segment`, `restore_options`
e sequência explícita de `manobras` serializável (`to_dict`). O grafo **não** checa capacidade nem
tensão — isso é papel do gêmeo (decisão 4), que consome a mesma sequência de manobras
(`twin/cluster.py::comandos_manobras`), já que os nomes de barra do bdgd2opendss são os PAC.

**Consequências.** FLISR topológico em < 1 s no cluster TQR; a mesma manobra é reproduzida no OpenDSS
sem tabela de tradução. Duas representações da rede para manter coerentes (grafo e DSS), com a BDGD
como fonte única.

## 6. Modo HITL (nível 2 de autonomia) com intertravamentos determinísticos e logs de auditoria

**Contexto.** O roteiro de modernização do COD prevê autonomia crescente; um agente de IA que
manobra rede sem revisão não é aceitável nem como demo.

**Decisão.** Nível 2: o agente **propõe** e o operador **aprova** cada manobra no console. Antes de
qualquer proposta chegar ao humano, um **verificador determinístico** (grafo + gêmeo) aplica os
intertravamentos: não fechar chave em trecho com falta ou em manutenção, não transferir carga que
viole tensão ou ampacidade no gêmeo, não abrir mais chaves do que o isolamento exige. Toda decisão
(raciocínio do agente, chamadas de ferramenta com argumentos e resultados, aprovação/rejeição
humana) vai para um log **imutável, só de acréscimo** (JSON Lines com carimbo de tempo e hash do
registro anterior), que também alimenta o benchmark (F4).

**Consequências.** A demo mostra propostas explicáveis (opções ordenadas com UC, TLCD, I no
disjuntor, MT mínima) e o humano no circuito; nenhuma ferramenta de escrita (`set_switch`) executa
sem token de aprovação. Custo: fluxo de trabalho mais lento e uma camada extra (verificador) que
precisa de testes próprios.

## 7. Conventional Commits, PR por issue, Copilot coding agent com revisão humana

**Contexto.** Backlog em Issues/Projects; a maior parte do código é escrita pelo Copilot (coding
agent ou CLI em modo autônomo) e revisada pelo mantenedor.

**Decisão.** Uma branch e um PR por issue com `Closes #N`; Conventional Commits em português;
`uv run ruff check . && uv run ruff format . && uv run pytest` verdes antes de cada push; CI em
3.11/3.12; ajustes de revisão em `docs/review/PR-NN.md` são aplicados num commit próprio antes da
próxima issue; diário do modo autônomo em `docs/review/NOITE.md`.

**Consequências.** Histórico legível e rastreável até a issue; o revisor humano decide o *merge*
(`--squash`). Convenções em `.github/copilot-instructions.md`.

---

## Decisões propostas (a confirmar na implementação)

## 8. Console em MapLibre GL JS + PMTiles no GitHub Pages (em vez de Leaflet + GeoJSON)

**Contexto.** O `index.html` legado (Leaflet, GeoJSON arrastado) não escala para 1 M de trechos nem
para estado em tempo real; o console precisa de mapa vetorial com estilo por atributo (tensão,
NA/NF, energizado/desligado) e hospedagem estática gratuita.

**Decisão.** `console/` em Vite + TypeScript + MapLibre GL JS lendo `.pmtiles` (protocolo
`pmtiles://`, um arquivo por recorte, gerado por `bdgd-light tiles` via tippecanoe) sobre base Esri
World Imagery/OSM; publicado no GitHub Pages por Actions. O estado dinâmico (chaves, energização)
entra como GeoJSON pequeno gerado pelo grafo (`bdgd-light grafo --geojson`) por cima dos tiles.

**Consequências.** Tiles estáticos servidos por HTTP range requests, sem servidor de tiles; o console
não precisa de backend para o mapa. Dependência de `tippecanoe` no ambiente de build (se ausente,
fallback para GeoJSON simplificado, documentado). Issue #4.

## 9. MCP (Model Context Protocol) como interface agente ↔ ferramentas

**Contexto.** O agente precisa chamar `load_feeder`, `get_topology`, `run_powerflow`,
`inject_fault`, `downstream_customers`, `propose_flisr`, `set_switch`… de forma tipada, auditável e
reutilizável por qualquer cliente (Copilot, console, benchmark).

**Decisão.** Servidor MCP em Python (`bdgd_light.mcp_server`) expondo essas ferramentas com esquema
explícito; grafo e gêmeo ficam atrás dele. O orquestrador (`bdgd_light.agent`) e o console falam só
MCP; nenhuma ferramenta de escrita age sem o token de aprovação da decisão 6.

**Consequências.** As mesmas ferramentas servem à demo e ao benchmark; o log de auditoria captura
chamadas no ponto único de passagem. Overhead de serialização e mais um processo para orquestrar.

## 10. LLM via GitHub Models atrás de uma interface `LLMClient`

**Contexto.** Queremos usar modelos com *tool calling* sem contratar provedor extra durante a POC e
sem acoplar o agente a um SDK específico; segredos só por variável de ambiente.

**Decisão.** Interface `LLMClient.chat(messages, tools) -> ToolCalls | Text` com duas implementações:
`GitHubModelsClient` (endpoint de inferência do GitHub Models, `GITHUB_TOKEN`, modelo por
`BDGD_LLM_MODEL`) e um cliente **fake** determinístico para testes — nenhuma chamada de rede na
suite. Se a API recusar ou limitar (rate limit da POC), o agente continua funcionando com o fake e
o limite fica documentado em `docs/spike-llm.md`.

**Consequências.** Troca de provedor sem tocar no orquestrador; testes rápidos e offline. Limites de
taxa/tokens do GitHub Models podem restringir o benchmark (medir em F4). Issue #7.

## 11. Benchmark e simulador como parte do produto (F4)

**Contexto.** A segunda finalidade do projeto é instrumentação de pesquisa (estilo PowerChain):
medir o agente em tarefas simple/medium/hard.

**Decisão.** `bdgd_light.sim` gera eventos (faltas, picos) sobre os alimentadores do cluster TQR;
`bench/` define tarefas com gabarito determinístico (grafo + gêmeo) e mede pass@k, precisão de
ordenação das opções e tokens/pass@1 a partir do log de auditoria.

**Consequências.** As decisões 5, 6 e 9 precisam expor resultados determinísticos e serializáveis
(já é o caso de `to_dict()`/`resumo()`); custo de manter gabaritos quando a BDGD muda de versão.

---

## Alternativas descartadas (resumo)

| Alternativa | Por que não |
|---|---|
| pip/venv + requirements.txt | sem lock cruzado de plataformas; `uv` resolve e instala em segundos e é o que o Copilot usa nas issues |
| Ler o `.gdb` direto em cada análise | minutos por consulta; CTMT/UCBT são tabelas e o filtro por alimentador exige junções que o Parquet faz em segundos |
| PostGIS | servidor a mais para uma POC estática; GeoParquet + GPKG cobrem o caso |
| Ties por PAC compartilhado | não existe na Light (`PAC_1/PAC_2` nunca coincidem entre CTMT) |
| Conversor BDGD → OpenDSS próprio | bdgd2opendss converteu sem ajuste; só vale como plano B |
| pandapower / OpenDSS via COM | sem modelo de carga ANEEL pronto; COM é só Windows |
| Leaflet + GeoJSON | não escala para a rede inteira nem para estado em tempo real |
| Chamar o SDK do provedor direto no agente | acopla e impede testes offline |
| Autonomia nível 3+ (agente executa) | fora do escopo de governança do MVP |
