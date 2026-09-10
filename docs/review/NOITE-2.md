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
