# Diário do modo noturno 2 — 2026-09-10

Trabalho autônomo sobre a fila da fase 3 (`docs/backlog/09`–`15` = issues #30–#36, mais #17 e #18),
mesmas regras da noite anterior (cabeçalho de `docs/review/NOITE.md`): uma branch e um PR por issue,
Conventional Commits, `uv run ruff check . && uv run ruff format . && uv run pytest` verdes antes de
cada push, CI verde → `gh pr merge --squash --delete-branch` (máx. 3 tentativas), `docs/review/`
lido antes de cada issue, nada de `data/` no git, nunca force-push, nunca direto em `main`. Horários
em BRT.

## 0. Pages e ambiente (09:20–09:40)

| | |
|---|---|
| Pages | **não estava habilitado** (`GET /repos/…/pages` → 404, apesar do repositório já ser público). Habilitei via `gh api -X POST repos/ViniciusAguiar15/bdgd-light/pages -f build_type=workflow`, disparei `gh workflow run pages.yml` → run 34479103070 com `build` e `deploy` verdes; site em <https://viniciusaguiar15.github.io/bdgd-light/>. |
| Chaves LLM | `GEMINI_API_KEY` presente no ambiente; **`OPENAI_API_KEY` ausente** no shell da sessão (não vasculhei dotfiles). As validações com OpenAI ficam registradas como pendência; as com Gemini seguem. |
| Issues | #22–#29 são **duplicatas** de #1–#8 (já fechadas), criadas por script em 2026-09-10 12:22Z. Não mexi; sugiro fechar como duplicadas. |
| Ferramentas | uv 0.9.24, tippecanoe em `/opt/homebrew/bin`; `uv sync --extra dev --extra twin --extra agent` ok. |

## 1. #30 — escopo v3: clusters Tijuca (A) e Ipanema (B) (09:40–11:10)

| | |
|---|---|
| Branch | `feat/escopo-v3-clusters` (a partir de `main` `2e4e46f`) |
| PR | ver "Fechamento" ao fim da seção |
| Recortes | `data/feeders/cluster_tijuca.gpkg` (10,1 MB, 29.331 feições) e `cluster_ipanema.gpkg` (4,9 MB, 13.249 feições) + um GPKG/meta por CTMT |

### Bloqueio (10:25–10:55): `git commit` e `npm`/`node` negados pelo ambiente

Entre 10:25 e 10:55 **toda** forma de `git commit` (`-m`, `-F`, mensagem ASCII mínima) e qualquer
`npm`/`node` devolviam "Permission denied and could not request permission from user"; `git add`,
`git checkout -b`, `git status/log/diff`, `gh` e `uv run …` continuaram funcionando. Não contornei
(nada de plumbing nem `subprocess`): segui trabalhando no *working tree* com os arquivos agrupados por
commit pretendido e documentei o plano de commits. Às 10:55 o mantenedor pediu para tentar de novo e
**ambos passaram a funcionar** — os commits abaixo foram feitos na ordem planejada e o console foi
compilado e testado (smoke dos 3 cenários). Dei uma `git worktree add` de teste no meio (negado, nada
criado).

### Achado 1 — bug real no grafo: ties de chaves "ambíguas" (anéis internos)

Em `RCP9882` (`757513244`) e `URG29983` (`977464757`) há chaves NA cujos **dois** PAC estão na
própria rede (ponto de anel interno, dois tocos de ~1,3 m) e que também casam geometricamente com
um CTMT externo (`RCP33308`, `URG30000`). A aresta de tie para `EXT:` era sempre passável e
**contornava a chave aberta**: no estado base 453 nós de RCP9882 apareciam "energizados por
RCP33308" e 328 de URG29983 por URG30000, e as opções de restauração da falta em CABOFRIO
inventavam fontes. Correção em `grid/rede.py`: a tie passa a carregar `via_chave` e só conduz com a
chave fechada (`_passavel`), `tie_switches()` ganha a coluna `ambigua`, `isolate_segment` trata a
tie como fronteira e `restore_options` a considera opção via a chave. Teste em memória
`test_tie_ambigua_de_anel_interno_so_passa_com_a_chave_fechada`. Depois da correção, o estado base
de Tijuca fica: RCP9882 516 nós, URG29983 462, ALC9925 351, ALC9946 324 (externos 1 nó cada).

### Achado 2 — o cenário B literal não existe nos dados

`PTS0001` tem 63 chaves, 48 telecomandadas, mas **35 das 36 NA são o pátio da SE Posto Seis**:
PAC `PTSTSL42/43_MT_*` que não aparecem em nenhum `SSDMT` da BDGD (a barra de transferência não é
modelada), a 12–40 m do polígono `SUB` (que cobre só o edifício, 492 m²) — por isso `EM_SUB` saía
`False` e o inventário as contou como "ties de campo". A rede própria de PTS0001 é radial, sem
nenhuma tie de campo; PTS9088 e PTS9924 idem (0 opções de restauração em todas as zonas). Logo
"falta em LDS 9210 com restauração por PTS9088/PTS9924" **não é reproduzível** sem inventar a
conectividade da barra.

Decisões:

- `EM_SUB` passa a usar uma folga de **50 m** ao redor do polígono da SUB (`RAIO_SUB_PADRAO_M`,
  parâmetro `raio_sub_m` de `detectar_interligacoes`; `0` restaura o `within` estrito). Com isso as
  chaves do pátio saem das contagens "de campo". O inventário `data/inventario_ctmt.csv` e a tabela de
  `docs/escopo-cidade.md` **não foram regerados** (leva horas) — pendência para o mantenedor, com a
  ressalva anotada no doc: a Zona Sul provavelmente perde a maior parte das "141 ties TLCD".
- **Cenário B vira cenário negativo**: falta no tronco de PTS0001 (`11409068`, 144 m) → abrir
  `10933610` (disjuntor), `505111870`, `561826961`; zona isolada 298 nós/1.251 UCBT; 15 nós/479 UCBT
  "desligados" **sem nenhuma chave NA que os restaure**. É útil para o agente/verificador: a resposta
  certa é "sem alternativa telecomandada, despachar equipe", não uma manobra inventada. Registrado em
  `escopo-cidade.md` como v3.1; sugeri alternativas subterrâneas com ties de campo reais a verificar
  (Laranjeiras LDS 34707) quando o inventário for regerado.
- Os 78 nós de PTS0001 "sem tensão" no grafo são exatamente os tocos do pátio (`PTSTSL43_MT_34xx`,
  `<cod>_2`): não aparecem no GeoJSON (não têm trecho) e não distorcem a demo.

### Cenário A (Tijuca) — falta de referência

Tronco expresso de CABOFRIO na saída da SE: trecho **`11304252`** (137 m) → abrir `10927447` +
`11035901`; zona isolada 35 nós/0 UCBT; **315 nós / 4.036 UCBT / 6 UCMT / 63 trafos (8.960 kVA)**
restauráveis; 10 opções, 4 telecomandadas: `974020904` (ALC9946 RIMARAES), `746851189` (RCP9882
BOMPASTOR), `977361689` (URG29983 AMALIA) e `1009901594` (externa URG29706). Alternativas
documentadas no escopo: `10961734` (meio do tronco, 293 nós/3.863 UCBT, mesmas 4 TLCD) e `335515751`
(241 nós/3.106 UCBT, 3 TLCD).

### Gêmeo (OpenDSS)

- `montar_master_cluster` aceita CTMT **sem `CargasBT_*`** (PTS4022: 0 UCBT, só `CargasMT`, 1.285 kW
  de UCMT) — só erra se existir CargasBT de outro dia/mês (pedido errado). Teste
  `test_montar_master_cluster_circuito_sem_carga`.
- **Achado 3 — bug do bdgd2opendss com bancos monofásicos.** O primeiro fluxo de Tijuca convergiu com
  perdas de **64 %**, 0,218 pu e 464 sobrecargas (trafos a 1.100 %). Causa: `UNTRMT.TIP_TRAFO = "DF"`
  (banco de 3 unidades monofásicas em delta fechado; 24 em Tijuca, 72 unidades) sai como
  `Transformer.TRF_<cod>A|B|C phases=3 windings=2 buses=["MT.2.3" "BT.2.4"] kvs=[13.2 0.22]` —
  trifásico com barras de **2 nós**, então o OpenDSS liga o 3º condutor ao nó 0 e aterra um vértice do
  delta. TQR não tem nenhum DF (todos os 82 trafos com 3 nós), por isso o spike não pegou. Correção:
  `twin.convert.corrigir_bancos_monofasicos(pasta)` reescreve essas linhas como `phases=1` com
  `kvs=[13.2 0.127]` (BT/√3), idempotente, chamada ao converter e ao reaproveitar pasta existente
  (conserta conversões antigas). Fixture `tests/fixtures/dss/bancos_monofasicos.dss` + 2 testes.
  Pendência: abrir issue no bdgd2opendss (PauloRadatz) com o caso mínimo.
- Resultados depois da correção (DU01; tabela completa em `docs/escopo-cidade.md` v3.1):

| caso | conv. | kW fonte | perdas | V MT mín | nós a 0 pu | tempo |
|---|---|---|---|---|---|---|
| Tijuca base | 6 it. | 13.286 (ALC9925 4.094 · ALC9946 2.715 · URG 3.134 · RCP 3.343) | 839 kW (6,3 %) | 1,036 | 0 | 2,5 s |
| Tijuca falta `11304252` | 6 it. | 9.192 (ALC9925 0) | 653 kW (7,1 %) | 1,036 | 4.838 | 1,6 s |
| … restaurar `974020904` → ALC9946 | 6 it. | 13.270 (ALC9946 6.793) | 876 kW (6,6 %) | 1,027 (ALC9925) / 1,030 (ALC9946) | 105 | 2,1 s |
| … restaurar `746851189` → RCP9882 | 6 it. | 13.244 (RCP9882 7.395) | 893 kW (6,7 %) | 1,018 / 1,024 | 105 | 1,3 s |
| … restaurar `977361689` → URG29983 | 6 it. | 13.235 (URG 7.177) | 902 kW (6,8 %) | 1,014 / 1,021 | 105 | 1,7 s |
| Ipanema base | 7 it. | 7.803 (PTS0001 2.802 · PTS9088 2.560 · PTS9924 1.155 · PTS4022 1.285) | 537 kW (6,9 %) | 1,041 | 0 | 0,6 s |
| Ipanema falta `11409068` | 7 it. | 5.000 (PTS0001 0) | 219 kW (4,4 %) | 1,041 | 8.624 | 0,5 s |

  Ranking natural para o agente: RIMARAES (mesma SE) < BOMPASTOR < AMALIA. A BT segue com nós < 0,5 pu
  (ramais suspeitos da BDGD, como em TQR; Ipanema tem 2 nós a 0,01 pu em BT 400 V) — veredito é MT.
- Conversão: ~3–4 min por CTMT (Ipanema 99 + 129 + 57 + 28 s só o bdgd2opendss, fora a leitura do GDB).
  Saídas em `data/dss/sub__10385889/{ALC9925,ALC9946}`, `sub__10385979/URG29983`, `sub__10386006/RCP9882`,
  `sub__10386087/PTS*`; relatórios JSON/log em `data/relatorios/` (ignorado pelo git).
- Recortes regerados depois da folga `EM_SUB` (10:41): Ipanema 74/75 interligações `EM_SUB=True`
  (sobra 1 tie de campo, externa, sem TLCD); Tijuca só a externa `URG29995` virou `EM_SUB` e as 4 TLCD
  do cenário A continuam. Estados GeoJSON e PMTiles regerados dos novos GPKG.
- Testes de fumaça com dados reais (skipif sem `data/feeders/cluster_*.gpkg`):
  `test_fumaca_cluster_tijuca_cenario_a` (isolamento, 4.036 UCBT, 4 TLCD por fonte) e
  `test_fumaca_cluster_ipanema_cenario_b_negativo` (EM_SUB ≥ 70, `restore_options == []`).

### Console

- `console/src/cenarios.ts` + seletor "Cenário" no painel: **Tijuca / Ipanema / Taquara** trocam
  tiles, estado e vista inicial (`?cenario=`; `?tiles=`/`?estado=` explícitos prevalecem;
  `?estado=none` desliga o estado do cenário). Padrão sem parâmetros: Tijuca.
- Exemplos versionados: `exemplos/estado_tijuca_falta.geojson` (627 KB), `estado_ipanema_falta.geojson`
  (601 KB), `tiles/exemplo_tijuca.pmtiles` (0,98 MB), `exemplo_ipanema.pmtiles` (0,78 MB); exceções
  no `.gitignore`.
- `ci.yml` ganhou o job `console` (`npm ci && npm run build`) — o PR só fica verde se o TypeScript
  compilar. Depois que o `node` liberou (10:56): `npm run build` ok (tsc + vite, 245 ms) e smoke dos 3
  cenários em `npm run preview` (porta 4173): tijuca 8.7k feições / estado 1.214 energizados + 314
  desenergizados, ipanema 7.872 feições, taquara 8.817; `errosJS: []` nos três. Screenshots conferidos
  (Tijuca: falta em vermelho saindo da SE Aldeia Campista; Ipanema: PTS0001 em vermelho ao longo da
  praia).
- Observação: o bbox dos PMTiles sai enorme (lat −23,0 a −22,18) porque `UCBT_tab.PN_CON` aponta para
  postes fora do recorte (qualidade da BDGD); com `?cenario=` a vista inicial é fixa e isso não
  incomoda, mas `?tiles=` avulso enquadra a cidade inteira. Pendência: filtrar `PONNOT` pelo bbox do
  cluster no `recortar`/`tiles`.

### Docs

`docs/escopo-cidade.md` ganhou a seção **v3.1** (tabela dos clusters, ranking das 3 restaurações,
por que o cenário B vira negativo, bugs achados); `docs/escopo-alimentadores.md` aponta para a v3;
`README.md` (estrutura, escopo, `dss` com exemplo Tijuca e nota dos bancos DF, tiles dos clusters,
console com `?cenario=`, Pages publicado); `docs/grid-modelo.md` (ties ambíguas com `via_chave`, folga
`EM_SUB`); `console/README.md` (seção Cenários, parâmetros, Pages habilitado).

### Fechamento

Commits na branch, na ordem: `fix(grid)` → `fix(ingest)` → `fix(twin)` → `feat(console)` →
`fix(scripts)` (bootstrap_github não recria issues fechadas — causa dos duplicados #22–#29) →
`docs(escopo)`. Validação antes do push: `uv run ruff check . && uv run ruff format . && uv run pytest`
→ **169 passed** (162 da base + 7 novos), `cd console && npm run build` ok, smoke dos 3 cenários ok.

Pendências deixadas para o mantenedor (também na descrição do PR):

1. Regerar `data/inventario_ctmt.csv` e a tabela por região de `escopo-cidade.md` com a folga `EM_SUB`
   (Zona Sul deve perder a maior parte das "141 ties TLCD").
2. Filtrar `PONNOT`/`UCBT` pelo bbox do cluster no `recortar`/`tiles` (bbox dos PMTiles cobre a cidade).
3. Abrir issue no bdgd2opendss sobre os bancos `DF` (caso mínimo em `tests/fixtures/dss/bancos_monofasicos.dss`).
4. Fechar os duplicados #22–#29.

## 2. #31 — ADR-003 provedor LLM: perfis openai/gemini/ollama/fake + `llm-smoke` (11:10–11:45)

| | |
|---|---|
| Branch | `feat/adr-003-provedor-llm` (a partir de `main` `7431917`, pós-PR #37) |
| PR | ver "Fechamento" |
| Ambiente | `GEMINI_API_KEY` presente; **`OPENAI_API_KEY` ausente** (nem no `zsh -lic`) — validação real só com Gemini |
| docs/review | nenhum arquivo novo além dos meus; nada pendente a aplicar |

### Decisões

- **Perfis** em `agent/llm.py`: `Perfil(nome, endpoint, modelo, env_token, descricao, token_padrao,
  url_modelos)` e `PERFIS = {openai, gemini, ollama, fake}`; `cliente_por_perfil()` e
  `cliente_do_ambiente(modelo, provider)` com a ordem `provider`/`BDGD_LLM_PROVIDER` →
  `BDGD_LLM_ENDPOINT` → `OPENAI_API_KEY` → `GEMINI_API_KEY` → `GITHUB_TOKEN` → `TokenAusenteError`
  (mensagem lista todas as opções, inclusive `BDGD_LLM_PROVIDER=fake`). Modelo: argumento →
  `BDGD_LLM_MODEL` → padrão do perfil. Ollama usa `token_padrao="ollama"` (sem chave).
- `Conversa.segundos` (tempo de parede das rodadas) + `to_dict()["segundos"]`; o CLI imprime
  `modelo · N rodada(s), T tokens, S s` — insumo direto do benchmark (#36).
- CLI `llm --provider`; `--fake` virou atalho de `--provider fake`; `--endpoint` ignora o perfil.
  Perfil desconhecido → `ValueError` capturado como erro de CLI (código 1).
- `scripts/listar_modelos.py --provider {openai,gemini,ollama}` passa a usar `cliente_do_ambiente`
  (perfil fake é recusado com mensagem); a orientação sem ambiente cita `OPENAI_API_KEY`.
- CI: job `llm-smoke` (`needs: test`, Python 3.12, `--extra agent`): fake sempre; OpenAI e Gemini só
  com `env.OPENAI_API_KEY != ''`/`env.GEMINI_API_KEY != ''` (segredos passados como `env` do job — o
  contexto `secrets` não vale em `if` de job), `continue-on-error: true`; passo `::notice::` quando
  não há segredo. **Não criei os secrets** (chave pessoal; decisão do mantenedor).
- ADR-003 em `docs/adr/ADR-003-provedor-llm.md` (4 decisões + alternativas descartadas); ADR-001 §10
  e `PLANO.md` apontam para ela; `spike-llm.md` ganhou o item 8 (perfis) e a **§6** com as medidas.

### Validação real (Gemini)

`uv run bdgd-light llm --provider gemini "Quanto é 2 + 3?" --json data/relatorios/llm_gemini.json`
→ `⚙ soma({"b": 3, "a": 2}) → 5.0` · "A soma de 2 e 3 é 5." · `gemini-2.5-flash · 2 rodada(s),
277 tokens, 1.8 s`. Três chamadas: 1,41 / 1,83 / 1,84 s, sempre 198 in / 31 out; custo ≈ US$ 0,00014
por conversa (US$ 0,30/2,50 por M, tabela consultada hoje). Sem 429.
`gemini-2.5-flash-lite` devolveu `message` **vazia** (0 tokens de saída) → `RespostaInvalidaError`;
registrado na ADR e no spike como motivo de não ser padrão.
`uv run scripts/listar_modelos.py --provider gemini --tools` → 40 modelos `models/gemini-…`.

**Pendente para o mantenedor** (chave ausente aqui):
`uv run bdgd-light llm --provider openai "Quanto é 2 + 3?" --json data/relatorios/llm_openai.json`
e anotar a linha `openai` da tabela em `docs/spike-llm.md` §6; `gh secret set OPENAI_API_KEY` /
`gh secret set GEMINI_API_KEY` para ligar o `llm-smoke`.

### Testes

5 novos em `tests/test_llm.py` (33 no arquivo): resolução dos perfis e precedência de modelo,
`BDGD_LLM_PROVIDER` × `BDGD_LLM_ENDPOINT`, Gemini via `MockTransport` (host, `Bearer`, `segundos`),
CLI `--provider fake|gemini|azure`, `listar_modelos --provider gemini` com ids `models/…`. A fixture
`sem_segredos` também apaga `OPENAI_API_KEY`/`GEMINI_API_KEY`/`OLLAMA_API_KEY`/`BDGD_LLM_PROVIDER`;
a varredura de segredos passou a cobrir o prefixo `AIza` (chaves Google). Suite: **174 passed**.

## 3. #17 — Master do gêmeo a partir do GPKG do recorte (11:15–12:20)

| | |
|---|---|
| Branch | `feat/twin-master-gpkg` (a partir de `main` `a9bc733`, pós-PR #38) |
| PR | ver "Fechamento" |
| docs/review | **PR-08.md** (PR #37) e **PR-09.md** (PR #38) apareceram no working tree, não versionados. Pedidos da PR-08 aplicados em commit próprio (`850d4b3`: issue upstream [bdgd2opendss#35](https://github.com/PauloRadatz/bdgd2opendss/issues/35), aviso de tabela desatualizada em `escopo-cidade.md`, issues #39 e #40). PR-09 (registrar perfil/modelo no `AuditLog` em `cliente_do_ambiente`) fica para a #34, que é a próxima a tocar `agent/`. Os dois arquivos entraram no git em `docs(review)`. |
| Módulo | `src/bdgd_light/twin/gpkg2dss.py` (~830 linhas): `converter_ctmt`, `converter_gpkg`, `listar_ctmts`, `dias_por_tipo`, `ConversaoGpkg`, `GpkgInvalidoError` |

### Decisões

- **Conversor próprio, não FileGDB.** A alternativa de gravar o recorte como `.gdb` (`OpenFileGDB`)
  ainda obrigaria o bdgd2opendss a carregar 18 tabelas e não removeria a dependência do pacote nem
  o bug dos bancos. O `gpkg2dss` reproduz a modelagem do bdgd2opendss 1.2.5 (li `Case.py`,
  `Load.py`, `Transformer.py`, `Line.py`, `Count_days.py`, `Converter.py` e o `bdgd2dss.json`) e usa
  o bdgd2opendss como **oráculo de paridade**: mesmos nomes de elemento e arquivo, mesmas tabelas de
  códigos (tensão, kVA, fases/nós, conexão, condutores), mesma fórmula de kW (energia do mês /
  dias do tipo / 24 / Σmult, `trunc` a 6 casas, dividida em `_M1` model=2 e `_M2` model=3), mesmo
  calendário (feriados `holidays` + Carnaval + Corpus Christi), `Set mode=daily` e `Voltagebases`.
- **Paridade exata em TQR0007**: `SegmentosMT`, `ChavesMT`, `SegmentosBT`, `ChavesBT`, `RamaisBT`,
  `TransformadorMTMTMTBT`, `CargasBT_DU01` (6.152 cargas) e `CargasMT_DU01` idênticos linha a linha
  (ordem à parte); fluxo com as mesmas 6.334 barras / 12.312 cargas, 3.076,76 kW e **perdas
  264,335 kW nos dois**, |ΔV| máx = 0 pu em 14.695 nós. Só diferem `CodCondutor`/`CurvaCarga` (só
  códigos usados), o nome do `Energymeter` e o `pu` do `Circuit` (float32).
- **PIP faltava no recorte** — 1.235 das 6.152 cargas BT de TQR0007 são iluminação pública, que o
  bdgd2opendss escreve como `Load.BT_IP<COD_ID>`. Exportei a camada (`bdgd-light export --layers
  PIP`, 835.142 linhas, 3 s), incluí no catálogo/recorte/CRVCRG e **regerei todos os recortes**
  (`TQR0007`, cluster TQR, `cluster_tijuca`, `cluster_ipanema` e os GPKG por CTMT).
- **Bancos DF/DA**: o bdgd2opendss usa o kVA da unidade (`EQTRMT.POT_NOM`, código TPOTAPRT) mas as
  perdas do conjunto (`UNTRMT.PER_*`) em cada unidade → 3× as perdas do banco. Abri
  [bdgd2opendss#36](https://github.com/PauloRadatz/bdgd2opendss/issues/36); o gpkg2dss divide as
  perdas pelas unidades e já escreve `phases=1` (#35). Tijuca cenário A: 876 → 804 kW de perdas
  (6,6 % → 6,1 %), tensões MT idênticas, 32.132 cargas nos dois.
- **Fixture corrigida**: `bdgd_mini.gpkg` gravava `EQTRMT.POT_NOM` como kVA (75) em vez do código
  (`"16"`) — lido como código dava 12 MVA. `gerar_fixture.py` passa a usar `CODIGO_KVA` e perdas
  ≈ NBR 5440; só `UNTRMT.PER_*` e `EQTRMT.POT_NOM/PER_*` mudaram (diff camada a camada).
- **CLI**: `dss --gpkg X` sem `--gdb`/`--master` converte do recorte (todos os CTMT se não houver
  `--ctmt`), reaproveita `data/dss/gpkg/<CTMT>/` se já tiver o Master, `--reconverter` regenera. O
  padrão de `--out` passou a depender do modo (`data/dss/gpkg` × `data/dss`) para não misturar as
  árvores; para rodar manobras sobre modelos do bdgd2opendss basta `--out data/dss`.
- Elementos sem caminho até o `PAC_INI` saem **comentados** e contados (`isolados_<tabela>`), não
  omitidos; CTMT cujo `PAC_INI` não está em nenhum elemento (RJO003 da fixture) vira aviso.

### Validação

```bash
uv run ruff check . && uv run ruff format . && uv run pytest         # 182 passed
uv run bdgd-light dss --gpkg data/feeders/TQR0007.gpkg --json /tmp/tqr.json   # 1,0 s; 264,3 kW perdas
uv run bdgd-light dss --gpkg data/feeders/cluster_tijuca.gpkg --falha 11304252 --restaurar 974020904 \
    --json /tmp/tijuca_gpkg.json   # 4 CTMT em 3,6 s; 13.233 kW, perdas 804 kW, MT 1,027–1,045 pu
uv run bdgd-light dss --gdb data/Light_382_2025-12-31_V11_20260824-0926.gdb --out data/dss \
    --ctmt ALC9925,RCP9882,ALC9946,URG29983 --gpkg data/feeders/cluster_tijuca.gpkg \
    --falha 11304252 --restaurar 974020904 --json /tmp/tijuca_ref.json   # 13.270 kW, perdas 876 kW
uv run pytest tests/test_gpkg2dss.py -q   # 8 testes; o de paridade usa data/feeders + data/dss
```

### Pendências

1. **Mantenedor**: os recortes em `data/feeders/` foram regerados aqui com `PIP`; em outra máquina,
   `uv run bdgd-light export --gdb … --layers PIP` + `recortar` antes de usar `dss --gpkg`.
2. Reguladores (`UNREMT`) e `GD_BT` não entram no gpkg2dss (não há nos clusters da demo; o Master
   do bdgd2opendss também não inclui GD).
3. PR-09: `AuditLog` com perfil/modelo em `cliente_do_ambiente` → na #34.

## 4. #18 — `twin.score_eletrico`: verificador elétrico das opções de restauração (12:20–12:45)

| | |
|---|---|
| Branch | `feat/twin-score-eletrico` (a partir de `main` `f63a09a`, pós-PR #41) |
| PR | ver "Fechamento" |
| docs/review | **PR-10.md** (revisão do PR #41, aprovado) apareceu durante a issue. Pedidos aplicados em commit próprio: (1) seção "Quando usar `--gpkg` × `--gdb`" no spike e README com `--gpkg` como padrão e `--gdb` só como oráculo de paridade; (2) comando de paridade para o mantenedor (abaixo e no README); (3) o `--score` já roda sobre `data/dss/gpkg` (padrão de `--dss-out`). |
| Módulo | `src/bdgd_light/twin/score.py`: `score_eletrico`, `ScoreEletrico`, `ordenar_scores`, `trechos_tronco`, `ampacidade_tronco`; `PowerFlowResult.fontes` ganhou `i_a` (corrente máx. de fase da `Vsource`) |

### Decisões

- **Uma compilação por opção.** As manobras de `fechar` criam `New Line` (chave NA + jumper da tie),
  que não se desfaz sem recompilar; então cada opção roda `run_powerflow(master_base,
  comandos_extra=comandos_base + comandos_manobras(...))`. Custo real: 7 fluxos do cluster Tijuca
  (4 CTMT, 32 mil cargas) em ≈10 s. A função é pura sobre o Master base (o único I/O) e devolve a
  lista **já ordenada** (viável → margem do disjuntor arredondada a 0,1 % → UCBT; empates mantêm a
  ordem do grafo).
- **Corrente nominal do disjuntor: não há tabela.** `UNSEMT.COR_NOM` é um código de domínio (Light
  usa 26 códigos; disjuntores de SE = `40`/`39`/`46`/`35`). Procurei a tabela no Manual da BDGD
  (gov.br/ANEEL, buscas web e GitHub) e dentro do GDB (`GDB_Items` via `LIST_ALL_TABLES=YES`: só as
  45 tabelas, nenhum `CodedValueDomain`) — nada, e não vou chutar uma tabela. Referência adotada:
  ampacidade `normamps` do(s) trecho(s) SSDMT logo após o disjuntor (BFS do PAC da fonte só por
  chaves fechadas; os 4 alimentadores da Tijuca têm exatamente um trecho-tronco), com
  `nominais={CTMT: A}` para sobrepor. A chave em si sai do conversor sem ampacidade (400 A padrão do
  OpenDSS, fictício) e não serve. Registrado no módulo, no README e no spike.
- **Perímetro do veredito** = nós/trechos MT da fonte que recebe a carga **+** os nós/trechos
  transferidos (`opcao.nos`), não o cluster inteiro — senão um problema pré-existente em outro
  alimentador derrubaria todas as opções igualmente. Perdas são do cluster todo (comparáveis entre
  opções). BT fora, como pede a issue.
- Fontes fora do recorte (`externa`/CTMT sem modelo) não são simuladas: `convergiu=False`,
  `viavel=False`, motivo "fonte X fora do cluster (sem modelo)". `motivos` sempre explica o "não"
  (tensão, disjuntor, trechos com os 3 piores percentuais, convergência).
- CLI: `grafo --falha X --score [--dss-out data/dss/gpkg --dia DU --mes 1 --vmin --vmax]` monta o
  Master base do cluster (convertendo do GPKG os CTMT que faltarem) e troca a tabela de opções por
  uma versão com as colunas elétricas (colunas de rede reduzidas para caber no terminal; a 80 colunas
  o Rich ainda dobra os cabeçalhos — o teste do CLI só confere título/rodapé/motivos).

### Achado — URG29983 é inviável por um gargalo de 20 m

Na Tijuca (falta `11304252`, 4.036 UCBT): ALC9946 viável (320 A / 592 A, margem 46 %, Vmin 1,027),
RCP9882 viável (351 A / 438 A, 20 %, Vmin 1,018) e **URG29983 inviável**: o trecho `11051956`
(20 m, condutor `456027629_43_3`, CNOM 132 A) no caminho até a tie vai a **180 %**. O score
topológico não vê isso; o elétrico vê. Pergunta para o mantenedor: cadastro (condutor fino no tronco)
ou restrição real? Em ambos os casos é um bom momento da demo.

### Validação

```bash
uv run ruff check . && uv run ruff format . && uv run pytest         # 187 passed
uv run bdgd-light grafo --gpkg data/feeders/cluster_tijuca.gpkg --falha 11304252 --score   # 10 opções, 10 s
uv run pytest tests/test_twin.py -q -k "score or tronco"              # 5 testes (cluster_mini)
# paridade gpkg2dss × bdgd2opendss (PR-10, pedido 2): rodar após regerar recortes ou mexer no conversor
uv run bdgd-light dss --gdb data/Light_382_2025-12-31_V11_20260824-0926.gdb --ctmt TQR0007 --out data/dss --sem-fluxo
uv run pytest tests/test_gpkg2dss.py -q -k paridade                    # skip automático sem os dados
```

### Pendências

1. Tabela `COR_NOM` do Manual da BDGD → `catalogo.py` e usar como `i_nominal_a` primário.
2. Todos os fluxos do cluster Tijuca (base inclusive) precisam de `maxiterations=100` + `vminpu=0.9`;
   vale investigar a barra que trava a convergência padrão (provável ramal BT longo).

### Fechamento

PR #42 (`feat(twin): score_eletrico — verificador elétrico das opções de restauração`, Closes #18):
CI verde (test 3.11/3.12 + llm-smoke), squash → `main` `d983e00`. Commits: `feat(twin)` score +
`feat(cli)` `--score` + `test(twin)` + `docs` + `docs(review)` PR-10.

## 5. #32 — servidor MCP com as ferramentas de rede (12:45–13:20)

| | |
|---|---|
| Branch | `feat/mcp-server` (a partir de `main` `d983e00`, pós-PR #42) |
| PR | ver "Fechamento" |
| docs/review | nada novo (PR-01…PR-10 já versionados; PR-09 → #34) |
| Módulo | `src/bdgd_light/mcp_server/`: `sessao.py` (domínio: `SessaoCOD`, `Proposta`, `FilaPropostas`, `RecusadoError`), `servidor.py` (`MCPServer` + rotas humanas + `descritores`), CLI `mcp` e `aprovar`, `docs/mcp-ferramentas.md` |
| SDK | `mcp` **2.2.0** local (Python 3.13) mas **1.10.1 no CI** (3.11/3.12): `bdgd2opendss` fixa `typing-extensions==4.12.2` e o `mcp` 2.x exige `>=4.13`, então o `uv.lock` bifurca. Primeira rodada do CI quebrou na importação (`mcp.server.mcpserver`); corrigido com camada de compatibilidade (`MCPServer`/`FastMCP`, `Client`/`create_connected_server_and_client_session`, `is_error`/`isError`) e testes rodados também em venvs 3.11 e 3.12 (`UV_PROJECT_ENVIRONMENT=/tmp/venv311 uv sync --python 3.11 …`). Segunda rodada quebrou só no 3.11: o `FastMCP` 1.x faz `issubclass(anotação, Context)` e, com `from __future__ import annotations`, a anotação é string — no 3.12 o pydantic 2.11 engole, no 3.11 (pydantic 2.13) estoura. `servidor.py` ficou sem o `__future__` import (anotações reais). |

### Decisões

- **Domínio independente do SDK.** `SessaoCOD` é Python puro (grafo + gêmeo + fila + auditoria) e
  as 12 ferramentas são métodos decorados com `@ferramenta(descricao)` — o decorador audita
  argumentos, resultado (compactado + SHA-256 do completo), latência e erros. `servidor.py` só embrulha
  cada método em uma função tipada do `MCPServer` (descrições em pt-BR, unidades). O agente da #34
  pode usar a sessão em processo, sem JSON-RPC; os testes exercitam o domínio direto e a camada MCP
  com o cliente em memória.
- **Semântica FLISR do simulador.** `inject_fault(trecho)` abre o **religador** (primeira chave
  fechada no caminho fonte→trecho) — única mudança de estado fora de `set_switch` — e guarda as
  chaves com indicação de falta. Com o religador aberto, `isolate_segment` do grafo real não vê "nós a
  jusante"; então `locate/isolate/restore_options/propose` raciocinam sobre uma **visão de plano**
  (cópia da rede com o religador fechado) e devolvem só a `sequencia` que falta manobrar (chaves já
  abertas em `ja_satisfeitas`). Sem isso `restore_options` devolvia `[]` após a falta — foi o primeiro
  bug do smoke.
- **Sequência forçada em `set_switch`**: abrir fronteira → fechar religador (se a falta não estiver
  colada nele) → fechar NA. A ferramenta executa **só o próximo passo** da proposta aprovada; fechar o
  NA antes da fronteira é recusado (nunca fechar anel sobre a falta). Recusas por token ausente/
  inválido (`compare_digest`), proposta rejeitada/executada/expirada (validade 30 min) e fora de
  sequência geram `mcp.recusa` na auditoria.
- **Aprovação fora do modelo.** `approve`/`reject` não são ferramentas MCP: o humano decide pela CLI
  `bdgd-light aprovar` (outro processo, via `propostas.json`; `hitl.jsonl` com a própria cadeia) ou
  por `POST /propostas/{id}/aprovar|rejeitar` no transporte HTTP (console F3). O agente obtém o token
  com `get_proposal` depois da aprovação. **Tokens nunca em claro** na auditoria: `approval_token`/
  `token` viram `sha256:<12>` em argumentos e resultados (o teste flagrou o token vazando pelo
  resultado de `get_proposal`; a máscara agora é recursiva e o hash do resultado é calculado sobre o
  resultado mascarado, para continuar conferível).
- **Master do cluster sob demanda.** `twin.preparar_master_cluster(gpkg, ctmts, out)` (extraído de
  `_score_opcoes` da CLI, que agora o reutiliza) converte do GPKG os CTMT que faltarem e escreve
  `<dss-out>/cluster_<A>-<B>/Master_DU01_base.dss`. Armadilha: usar a fixture
  `tests/fixtures/dss/cluster_mini` diretamente como `dss_out` gera arquivos dentro do repositório —
  os testes copiam a fixture para `tmp_path`.
- Helpers novos em `Rede` (`caminho_da_fonte`, `chaves_no_caminho`, `downstream_switch`) ficaram no
  `grid` por serem topologia pura; o CLI `mcp` em stdio manda as mensagens humanas para **stderr**
  (stdout é o canal do protocolo).

### Validação

```bash
uv run ruff check . && uv run ruff format . && uv run pytest         # 200 passed (187 + 13 novos)
uv run pytest tests/test_mcp_server.py -q                             # fluxo completo, recusas, fila, MCP em memória, CLI
for v in 3.11 3.12; do UV_PROJECT_ENVIRONMENT=/tmp/venv$v uv sync --python $v --extra dev --extra twin --extra agent; done
/tmp/venv3.11/bin/python -m pytest tests/test_mcp_server.py -q        # mesma resolução do CI (mcp 1.10.1): 13 passed
uv run bdgd-light mcp --listar                                        # 12 ferramentas
uv run bdgd-light mcp --cluster tijuca --transporte http --porta 8765 # em outro terminal:
curl -s localhost:8765/estado | head -c 300; uv run bdgd-light aprovar
# smoke feito aqui: stdio via mcp.client.stdio (12 tools, is_error nas recusas, audit verificável),
# http via curl (/estado 200, /propostas 200, aprovar repetido 409, initialize MCP ok)
```

### Pendências

1. Sessão única por processo (um cluster, uma falta); multi-operador fica para depois do MVP.
2. Proteção só no religador do CTMT (sem fusíveis/religadores intermediários) — `chaves_com_indicacao`
   = chaves fechadas no caminho fonte→falta.
3. `load_cluster tijuca` com `--score` converte os 4 CTMT na primeira chamada (≈1–2 min); para a demo,
   rodar antes `bdgd-light grafo --gpkg data/feeders/cluster_tijuca.gpkg --falha … --score` ou manter
   `data/dss/gpkg/` populado.
4. #34 consome `SessaoCOD` em processo (ou o servidor via stdio); #35 usa `GET /estado`,
   `GET /propostas` e `POST /propostas/{id}/aprovar`.

### Fechamento

PR [#43](https://github.com/ViniciusAguiar15/bdgd-light/pull/43) — CI verde na **3ª tentativa**
(1ª: `mcp.server.mcpserver` inexistente no `mcp` 1.10.1 do CI; 2ª: `issubclass()` com anotação string
no 3.11) — merge squash em `main` `c4ef76b` às 13:19. Limite de 3 correções foi usado até o fim, mas
não estourado.

## 6. #33 — simulador de eventos e fila (13:20–13:45)

| | |
|---|---|
| Branch | `feat/sim-eventos` (a partir de `main` `c4ef76b`, pós-PR #43) |
| PR | ver "Fechamento" |
| docs/review | **novos `PR-11.md` (revisão do #42) e `PR-12.md` (revisão do #43)**, ambos aprovados. PR-11: pedido 2 (ranking elétrico no cenário A de `escopo-cidade.md`) e pedido 3 (issue [#44](https://github.com/ViniciusAguiar15/bdgd-light/issues/44) "diagnóstico de convergência") aplicados aqui em commit próprio; pedido 1 (`COR_NOM` do Manual) depende do PDF do mantenedor — pendente. PR-12: pedidos 1–2 (identidade do operador nas rotas HTTP, `hash` da auditoria em `GET /estado`) vão para #35 e o pedido 3 (sessão Tijuca completa em `docs/mcp-ferramentas.md`) para #34, como a revisão indica. PR-09 continua reservado para #34 |
| Módulo | `src/bdgd_light/sim/eventos.py` (`Evento`, `Cenario`/`CENARIOS`, `Simulador`, `FilaEventos`, `normalizar_tipo`), CLI `sim`, `docs/sim.md`, `tests/test_sim.py` (18 testes) |

### Decisões

1. **O simulador não mexe na rede.** Ele descreve o evento (e o que aconteceria se o religador
   abrisse: `sem_tensao_se_religador_abrir`) e deixa a mudança de estado para o agente via
   `inject_fault`/`set_switch` do MCP — assim há uma única porta de entrada auditada para alterar o
   gêmeo, e o evento continua válido mesmo se o agente demorar a tratá-lo.
2. **Fila = JSONL só de acréscimo** (`data/eventos/eventos.jsonl`), ids `E-0001…` continuando a
   numeração entre processos; sem ack/remoção — o consumidor guarda o índice. Zero dependência, dá
   para acompanhar com `tail -f`, e o arquivo vira registro do que foi injetado.
3. **Sorteio de trecho ponderado por `comp` (m)**: trechos longos falham mais (proporcional à
   exposição). Tipos com pesos 5:3:2:1 favorecendo faltas permanentes (o caso de uso FLISR).
4. **Cenários nomeados** com alvos fixos de `escopo-cidade.md`/`spike-opendss.md`
   (`tijuca_cabofrio_tronco` = `11304252`, `ipanema_9210` = `11409068` negativo, `taquara_bocari` =
   `11798327`). Com o recorte carregado, o cenário confere que o trecho existe (cenário de outro
   cluster = erro); sem recorte (CI, máquina sem `data/`), o CLI emite o evento "magro" com aviso —
   suficiente para o agente chamar `load_cluster` + `inject_fault`.
5. `resolver_cluster` saiu de `SessaoCOD._resolver_cluster` para função de módulo em
   `mcp_server.sessao` (importável sem o SDK `mcp`), reutilizada pelo CLI `sim`; `CLUSTERS` continua
   a fonte única dos nomes da demo.
6. `chaves_com_indicacao` = chaves fechadas no caminho fonte→falta (mesma simplificação da
   `locate_fault`); `religador` = a primeira delas. No cluster sintético, SEG002 devolve
   `["CH008", "CH001"]`.
7. Erros: trecho/chave inexistentes reaproveitam `TrechoInexistenteError`/`ChaveInexistenteError` do
   grafo; CTMT fora do cluster e tipo inválido são `ValueError`. No CLI tudo vira `Erro: …` + código 1
   e **nada é publicado**.

### Validação

```bash
uv run ruff check . && uv run ruff format . && uv run pytest         # 218 passed (200 + 18 novos)
uv run pytest tests/test_sim.py -q                                    # semente, sorteio por km, cenários, fila, CLI
uv run bdgd-light sim --listar
uv run bdgd-light sim --cluster tijuca --emitir 3 --seed 42           # com o recorte em data/feeders
uv run bdgd-light sim --cenario tijuca_cabofrio_tronco --json
uv run bdgd-light sim --cenario ipanema_9210 --feeders /tmp/nada      # sem recorte: aviso + evento magro
uv run bdgd-light sim --mostrar 5
# smoke feito aqui sobre /tmp/mini (recorte RJO001+RJO002): reprodutibilidade com seed 42 (6 eventos
# iguais), distribuição do sorteio ~ km (SEG008 270 m: 524/2000 vs SEG006 67 m: 114/2000), fila com
# ids sequenciais e listar(desde), erros de uso com exit 1
```

### Pendências

1. Os cenários nomeados só foram exercitados "magros" e sobre o cluster sintético aqui (a checagem de
   existência do trecho é testada com o cenário errado); rodar `uv run bdgd-light sim --cenario
   tijuca_cabofrio_tronco` com `data/feeders/cluster_tijuca.gpkg` para ver os detalhes reais
   (religador e ~4 mil UCBT sem tensão).
2. Push da fila para o console (`GET /eventos?desde=n` no servidor HTTP do MCP) fica para #35; #34
   consome `FilaEventos.listar(desde=)` em processo.
3. Sem fusíveis/religadores intermediários nem indicadores de falta em campo — telemetria = chaves
   fechadas no caminho.
