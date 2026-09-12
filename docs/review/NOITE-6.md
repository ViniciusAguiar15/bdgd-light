---
title: "Diário — Modo noturno, rodada 6"
---

# Modo noturno — rodada 6

## 0. Ambiente (20:54)

- `main` em `f0b4ee3` (docs(backlog): rodada 6 — generalização, qualidade do cadastro e geração
  distribuída), após `4d88f80` (MANHA-5) e `a55e30d` (fechamento da rodada 5).
- Árvore de trabalho limpa, nenhuma pendência solta.
- `OPENAI_API_KEY` (164 caracteres) e `GEMINI_API_KEY` (53 caracteres) presentes via `zsh -lic`
  (persistidas em `~/.zshrc` desde a rodada 4). Nenhuma chave faltando no início da rodada.
- Fila desta rodada (ordem definida pelo usuário, backlog → issue):
  1. backlog 38 → #100 — pedidos da revisão MANHA-5 (rápido)
  2. backlog 29 → #91 — generalização: pipeline em alimentador nunca visto
  3. backlog 30 → #92 — agente fora do treino
  4. backlog 31 → #93 — qualidade do cadastro BDGD Light 2025
  5. backlog 32 → #94 — atlas de interligações
  6. backlog 35 → #97 — ingest GD (MMGD ANEEL)
  7. backlog 36 → #98 — GD no gêmeo
  8. backlog 37 → #99 — GD na restauração
  9. backlog 34 → #96 — sensibilidade de premissas
  10. backlog 33 → #95 — paridade gpkg2dss × bdgd2opendss
- Regra desta rodada: diário commitado no mesmo passo/PR de cada issue (mantida da rodada 5).
- Regra de honestidade das medições (29-37): resultado negativo é resultado — se o pipeline falhar
  em X% dos alimentadores sorteados, o número e as causas vão para o relatório; recorte não é
  ajustado para melhorar o número (ajuste, se necessário, vira issue nova).
- Nota: issue #90 (título "cli: bdgd-light replay...") é uma duplicata da #83, já implementada e
  mergeada na rodada 5 (PR #88). Não faz parte da fila desta rodada — não foi tocada.

## 1. Issue #100 — pedidos da revisão MANHA-5 (21:01)

- Corrigi `scripts/gerar_resultados.py` para distinguir família por modo (com/sem exemplos e com/sem compactação), acrescentar a coluna **modo** no consolidado, marcar a configuração padrão com `★ padrão` e mostrar frações brutas ao lado de **ordem**/**precisão** em `docs/resultados.md`.
- Estendi `tests/test_gerar_resultados.py` para cobrir a nova coluna, o marcador da configuração padrão, as frações e a saída determinística em duas gerações consecutivas.
- Investiguei H12–H15 nos CSVs `openai-hardplus-k3*`: H14/H15 rederivam `locate_fault → isolate_fault → restore_options → propose_plan` em 6/6 execuções, o que os dados sustentam como sequência válida de replanejamento; por isso corrigi a `referencia` dessas tarefas em `bench/tarefas.yaml` e reescrevi a análise em `docs/bench.md`.
- O desperdício residual ficou concentrado em H13: `propose_plan` extra em 6/6 execuções, `get_topology` extra em 1/3 do braço com exemplos e salto de `isolate_fault` em 2/3 do braço sem exemplos; documentei isso no bench.
- Regenerei `docs/resultados.md`, validei `uv run bdgd-light --help`, rodei a suíte de testes completa e deixei a árvore pronta para lint final, commit, push e PR da #100.


## 2. Issue #91 — generalização: pipeline em alimentador nunca visto (21:21)

- Li a issue #91, o backlog canônico (`docs/backlog/29-generalizacao-alimentadores.md`) e o
  pipeline relacionado: inventário/recorte por CTMT, grafo (`grid/rede.py`), `gpkg2dss`, score
  elétrico e as ferramentas `inject_fault`/`restore_options` do servidor MCP.
- Confirmei que o ambiente tinha dados reais da Light (`data/parquet/`, `data/inventario_ctmt.csv`
  e `data/Light_382_2025-12-31_V11_20260824-0926.gdb`), então rodei a execução real pedida, sem
  recorrer a mocks para o relatório final.
- Implementei `src/bdgd_light/generalizacao.py` e o runner `scripts/generalizacao.py`: amostragem
  determinística estratificada por região × porte, recorte automático de `CTMT + vizinhos diretos`
  quando há tie, execução do pipeline completo por etapa e exportação de um CSV por `CTMT × etapa`.
- Adicionei `tests/test_generalizacao.py` cobrindo o sorteio determinístico, a normalização do CSV
  (sucesso/falha/não executada) e uma rodada real pequena sobre a fixture sintética do projeto.
- Rodei a amostra real de 30 alimentadores com semente 91 e gerei
  `docs/bench/2026-09-11-generalizacao.csv`: 30/30 sucesso em todas as etapas, 18/30 sem tie,
  12/30 com tie, 7/30 com opções de restauração e 39 opções viáveis entre 42 avaliadas no score.
- Documentei os números e os limites de interpretação em `docs/generalizacao.md`, incluindo o
  comando exato de reprodução e o resultado negativo relevante (tie não implica restauração útil).
- Abri a follow-up issue #102 para separar, em rodadas futuras, “fluxo convergiu” de “caso base
  eletricamente saudável”, porque vários casos-base convergiram com `Vmin` muito baixa.

## 3. Issue #92 — agente fora do treino (21:45)

- Li o backlog canônico (`docs/backlog/30-agente-fora-do-treino.md`), a issue #92 no GitHub e a
  infraestrutura existente de benchmark (`src/bdgd_light/bench.py`, `bench/tarefas.yaml`,
  `docs/bench.md`, `scripts/gerar_resultados.py`) antes de escrever código novo.
- Implementei `src/bdgd_light/bench_fora_treino.py` + `scripts/preparar_bench_fora_treino.py` para
  reutilizar o pipeline da #91: ler o CSV de generalização, selecionar deterministicamente os
  **10 primeiros CTMTs** com `restore_options` bem-sucedido, materializar os recortes
  `CTMT + vizinhos`, recalcular o gabarito pelas ferramentas reais e escrever
  `bench/tarefas_fora_treino.yaml` + `docs/bench/2026-09-11-fora-treino-casos.csv`.
- Estendi o benchmark com um rótulo opcional de família (`--familia`) e persisti essa família no
  CSV para que suítes dedicadas como `openai-fora-treino-k3` não se misturem ao comparativo da
  suíte-base; também corrigi a leitura retrocompatível dos CSVs antigos por nome de arquivo.
- Ajustei `scripts/gerar_resultados.py` para ignorar CSVs auxiliares que não têm o schema do
  benchmark, o que permite manter o CSV versionado dos 10 casos dentro de `docs/bench/` sem
  quebrar a regeneração de `docs/resultados.md`.
- Adicionei testes em `tests/test_bench.py`, `tests/test_bench_fora_treino.py` e
  `tests/test_gerar_resultados.py` cobrindo seleção determinística, geração do YAML, inferência de
  família por arquivo e a tolerância do consolidado a CSVs auxiliares.
- Rodei a validação manual real pedida com OpenAI via
  `zsh -lic 'uv run bdgd-light bench --provider openai --familia fora-treino-k3 --k 3 --seed 92 ...'`
  e gerei `docs/bench/2026-09-12-openai-fora-treino-k3.{csv,md}`: **27/30 = 90 %** de pass@1,
  **0/30 reprovações do verificador**, custo médio de **20.897 tokens / US$ 0,0090** por execução.
- Resultado negativo registrado sem maquiagem: fora do treino o `gpt-4.1-mini-2025-04-14` caiu de
  **100 %** no `openai-hard-k5` conhecido para **90 %**. As **3 falhas** ficaram concentradas em
  `FT02` (SAT1960), onde o modelo reconheceu corretamente que não havia opção viável, mas encerrou
  sem formalizar `propose_plan` para a proposta **sem chave**.
- Abri a follow-up **#104** para investigar esse sintoma específico sem alterar o resultado
  histórico da issue #92.

## 4. Issue #93 — qualidade do cadastro BDGD Light 2025 (21:56)

- Li o backlog canônico (`docs/backlog/31-qualidade-cadastro.md`), a issue #93 e as regras já
  documentadas em `docs/bdgd-relacoes.md`, `docs/bdgd-light-2025.md`, `ingest/export.py`,
  `ingest/parquet.py` e `recorte.py` antes de escrever o perfil de qualidade.
- Implementei `src/bdgd_light/qualidade.py` e o runner `scripts/qualidade_bdgd.py` para gerar, de
  modo determinístico, `docs/qualidade-bdgd.md` a partir de `data/parquet` com as 9 verificações
  pedidas: `FAS_CON`, `RAMLIG`, `PN_CON`, `TIP_CND`×`SEGCON`, referências de `CTMT`, PACs
  multi-alimentador, geometria inválida/vazia, bbox da concessão e `TLCD`.
- Adicionei `tests/test_qualidade.py` com uma base sintética pequena em Parquet/GeoParquet cobrindo
  as anomalias principais, a limitação real de `UCMT_tab` sem `UNI_TR_MT` e a equivalência entre o
  Markdown escrito pelo script e o renderizador do módulo.
- Rodei o script na base inteira da Light 2025 e commitei o relatório real sem digitar números à
  mão. Principais achados honestos: `FAS_CON` monofásico em **5.466.508 / 11.807.122 (46,30 %)**;
  `RAMLIG > 300 m` em **2.069 / 3.818.151 (0,05 %)** com p99 **81,83 m**; `PN_CON` a > 2 km em
  **6.412 / 5.041.346 (0,13 %)**; `TIP_CND` sem `SEGCON`, `CTMT` ausente/inverso, PAC multi-CTMT,
  geometria inválida/vazia e `TLCD` nulo/indefinido ficaram todos em **0**; bbox fora da concessão
  apareceu em **164 / 3.872.877 (0,0042 %)**, concentrado em `CONJ`, `PONNOT`, `SSDAT` e um `SUB`.
- Adaptação explicitada no relatório: a Light 2025 não oferece vínculo direto de `UCMT_tab` com
  transformador de distribuição, então a checagem de 2 km ficou restrita a `UCBT_tab` e terminou
  com uma pergunta pronta para a distribuidora sobre qual campo físico deve ser usado.

## 5. Issue #94 — atlas de interligações (22:07)

- Li o backlog canônico (`docs/backlog/32-atlas-interligacoes.md`), a issue #94 e reaproveitei a
  lógica já existente de detecção geométrica de ties em `ingest/interligacoes.py` e do inventário
  por alimentador em `ingest/inventario.py`, sem reimplementar do zero.
- Implementei `src/bdgd_light/atlas_interligacoes.py` e o runner
  `scripts/atlas_interligacoes.py` para consolidar, a partir de `data/parquet`, o atlas completo:
  tabela por CTMT com ties de campo, telecomando, destinos (`CTMT`, subestação e conjunto),
  componente conexa e grau no grafo de socorro; arestas agregadas CTMT–CTMT; GraphML; e
  histograma em SVG puro.
- Adicionei `tests/test_atlas_interligacoes.py` cobrindo a fixture sintética do projeto, a
  renderização do Markdown/SVG e a escrita dos artefatos versionáveis.
- Rodei o script na base inteira da Light 2025 e commitei os agregados reais em `docs/`:
  `docs/atlas-interligacoes.md`, `docs/dados/atlas-interligacoes-alimentadores.csv`,
  `docs/dados/grafo-socorro-arestas.csv`, `docs/dados/grafo-socorro.graphml` e
  `docs/dados/grau-socorro-histograma.svg`.
- Números honestos da base real: **1.802 alimentadores**, **4.524 ties de campo únicos**
  (**616 telecomandados**), **2.386 arestas** CTMT–CTMT no grafo, **600 alimentadores grau 0**,
  **626 componentes conexas** e **379.348 / 5.049.006 clientes = 7,51 %** sem socorro possível por
  tie de campo.

## 6. Issue #97 — ingest GD ANEEL (MMGD) (22:19)

- Li o backlog canônico (`docs/backlog/35-ingest-gd-aneel.md`), a issue #97 no GitHub e confirmei
  a fonte real via CKAN/API da ANEEL antes de codar: recurso principal
  `empreendimento-geracao-distribuida.parquet`, `ZIP` equivalente e o PDF
  `dm-geracao-distribuida-relacao-de-empreendimentos.pdf` (dicionário v2.3, 17-11-2025).
- Baixei e parseei o PDF real, sem adivinhar nomes de coluna. O Parquet expõe exatamente os campos
  usados no pipeline, em especial `CodEmpreendimento`, `DthAtualizaCadastralEmpreend`,
  `DscClasseConsumo`, `DscSubGrupoTarifario`, `SigTipoGeracao`, `DscFonteGeracao` e
  `MdaPotenciaInstaladaKW`.
- Implementei `scripts/baixar_gd.py` com descoberta do recurso correto por nome no catálogo CKAN,
  retomada via `HTTP Range`, preferência por Parquet e gravação de `data/gd/metadata.json` com
  data/hora de extração, URL do `package_show` e metadados do arquivo baixado.
- Implementei `src/bdgd_light/ingest/gd.py` e `scripts/gerar_gd_light.py` para:
  filtrar a Light (`NumCNPJDistribuidora = 60444437000146`, `NomAgente = LIGHT SERVICOS DE
  ELETRICIDADE S A`, `SigUF = RJ`), normalizar potência/fonte/classe/subgrupo, cruzar MMGD × BDGD
  pela chave direta `CodEmpreendimento ↔ CEG_GD`, agregar por alimentador e conjunto e gerar
  `docs/gd-light.md` + CSVs auxiliares em `docs/dados/`.
- Evidência documentada no relatório, sem fingir precisão inexistente: a chave direta existe e casa
  **56.941 / 64.233 = 88,65 %** dos empreendimentos da MMGD da Light (**699.667,12 /
  843.404,78 kW = 82,96 %**). O que sobra **não** tem `CTMT`, `UNI_TR_MT` nem código da UC
  beneficiária na MMGD; por isso o saldo sem chave foi agregado **apenas por município**.
- Divergências reais registradas: **7.292** empreendimentos MMGD sem match direto
  (**143.737,66 kW**), **1.197** linhas BDGD com `CEG_GD` vazio (**92.199,47 kW**) e **3**
  repetições BT/MT idênticas da própria BDGD para a mesma chave no mesmo CTMT.
- Gerei e commitei o relatório real `docs/gd-light.md`: topo por alimentador, conjuntos, evolução
  anual pelo único campo temporal disponível (`DthAtualizaCadastralEmpreend`), municípios sem chave
  e maiores divergências de potência entre MMGD e BDGD.
- Adicionei `tests/test_gd.py` cobrindo filtro/nome real de colunas, junção exata com fixture
  sintética, renderização determinística do Markdown, geração dos CSVs e leitura dos metadados do
  downloader.
