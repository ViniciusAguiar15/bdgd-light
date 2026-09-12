# bdgd-light

**Um Centro de Operação da Distribuição (COD) em miniatura, construído sobre dados públicos, onde uma
IA propõe manobras de rede e um operador humano aprova.** A rede é a da Light no Rio de Janeiro, vinda
da BDGD da ANEEL; a física é calculada pelo OpenDSS; a decisão continua sendo humana.

Quando um curto-circuito derruba um alimentador, alguém precisa descobrir onde foi a falta, isolar o
trecho defeituoso abrindo as chaves certas e reenergizar o resto dos clientes fechando alguma chave
normalmente aberta que liga aquele alimentador a um vizinho — é o que o setor chama de FLISR, e é o
que mais pesa nos indicadores DEC e FEC. Este projeto monta esse ciclo inteiro sobre uma rede real:
o agente localiza, isola, compara as rotas de restauração **simulando cada uma no gêmeo digital** e
propõe um plano; o operador aprova, de uma vez ou uma manobra por clique, e o mapa recolore.

Nada é manobrado sem aprovação humana com identidade e token, e cada passo — raciocínio, chamada de
ferramenta, resultado, aprovação, comando — vai para um log encadeado por hash.

- **Mapa publicado** (sem backend, só a rede): <https://viniciusaguiar15.github.io/bdgd-light/>
- **Roteiro de aula de 15 min**, cronometrado e com plano B: [`docs/demo-roteiro.md`](docs/demo-roteiro.md)
- **Arquitetura e decisões**: [`docs/PLANO.md`](docs/PLANO.md) · [ADR-001](docs/adr/ADR-001-stack.md) · [ADR-002](docs/adr/ADR-002-console-maplibre-pmtiles.md) · [ADR-003](docs/adr/ADR-003-provedor-llm.md)
- **Referência da CLI**: [`docs/comandos.md`](docs/comandos.md)

## A demo em três telas

Falta no tronco do alimentador ALC9925 (CABOFRIO, Tijuca), 4.036 clientes sem tensão. O agente isola
a falta, compara as três rotas de restauração no OpenDSS — **descartando a via AMALIA porque um trecho
de 20 m iria a 180 % da capacidade** — e propõe a rota por RIMARAES. O operador aprova; o mapa recolore.

| 1 · evento em curso | 2 · proposta, alternativas e motivos | 3 · aprovada e executada |
|---|---|---|
| ![falta injetada; 4.036 UCBT sem tensão; agente pensando](docs/img/1-evento.png) | ![proposta P-0001: abrir 11035901, fechar 974020904 → ALC9946; 10 alternativas com motivo do descarte](docs/img/2-proposta.png) | ![rede restaurada: 0 UCBT sem tensão; trilha de auditoria íntegra](docs/img/3-executada.png) |

## Ver funcionando

Precisa de [uv](https://docs.astral.sh/uv/), Node 20+ e uma chave de LLM (OpenAI ou Gemini; sem chave,
use `--provider fake`, que roteiriza o operador e não chama modelo nenhum).

```bash
uv sync --extra dev --extra twin --extra agent --extra console
(cd console && npm ci && npm run build)

export OPENAI_API_KEY="..."        # ou GEMINI_API_KEY, e --provider gemini abaixo
BDGD_CONSOLE_TOKEN=demo uv run bdgd-light serve --cluster tijuca --provider openai --porta 8010
```

Abra <http://127.0.0.1:8010/?cenario=tijuca>. No painel da direita, na seção **"COD · fila e
aprovação"**, preencha **operador** (qualquer nome — vai para a auditoria) e **token** (`demo`), e
clique em **injetar falta**. Em 20 a 40 segundos aparece a proposta com a sequência de manobras, o
veredito do verificador e as alternativas com o motivo de cada descarte. Aprove clicando uma vez por
manobra e acompanhe o mapa.

Os recortes da rede (`data/feeders/`) e os modelos OpenDSS (`data/dss/`) não vão para o git. Para
gerá-los do zero a partir da BDGD, veja [`docs/comandos.md`](docs/comandos.md) — são quatro comandos
(`export`, `recortar`, `dss`, `tiles`) e uns 15 minutos, a maior parte baixando 1,1 GB da ANEEL.

## Como funciona

**Dados.** A BDGD é a base geográfica que toda distribuidora entrega à ANEEL uma vez por ano: cada
poste, trecho, chave, transformador e consumidor, com posição e atributos elétricos. A da Light tem
43 camadas e 1.802 alimentadores; recortamos quatro deles (o cluster da Tijuca: 1.662 nós, 148 chaves,
23 interligações) porque é o que cabe numa demonstração e numa simulação rápida.

**Três modelos da mesma rede**, para três perguntas diferentes. O **grafo** (networkx) responde
topologia — se eu abrir esta chave, quem apaga? qual chave aberta reenergiza o resto? O **gêmeo
digital** (OpenDSS) responde eletricidade — a tensão fica na faixa? o cabo aguenta a corrente? E os
**tiles** (PMTiles) respondem visualização, que é o mapa do console.

**Ferramentas.** Cada capacidade virou uma função com nome, argumentos e descrição em português,
exposta por um servidor MCP: localizar falta, isolar, listar opções de restauração, rodar fluxo de
potência, propor plano, comandar chave. É essa camada que faz um modelo de linguagem enxergar a rede —
em vez de ensinar eletricidade ao LLM, damos a ele ferramentas que já sabem eletricidade.

**Agente.** O orquestrador decide qual ferramenta chamar a cada passo, guiado por exemplos anotados.
O **verificador** é determinístico e roda antes de qualquer proposta chegar ao operador: confere se a
chave existe, se abre antes de fechar, se a fronteira está isolada, e passa o plano pelo OpenDSS para
checar convergência, tensão e corrente. Reprovou, devolve os problemas e o orquestrador replaneja.

**Operador.** O agente nunca manobra: propõe. A proposta só vira comando com aprovação identificada —
nível 2 de autonomia, que é como uma distribuidora aceitaria começar.

### O que é real e o que é simulado

A rede, os clientes, as chaves, os condutores e as cargas são dados reais da Light (BDGD 2025). A
física é real, calculada pelo OpenDSS a cada opção de restauração. O que não existe publicamente é
telemetria em tempo real: a falta é **injetada por um simulador**, mas se propaga pelo modelo real da
rede. A qualidade do dado aberto também aparece — ramais de centenas de metros, cargas monofásicas
concentradas numa fase, postes cadastrados a quilômetros da rede — e está documentada em
[`docs/bdgd-light-2025.md`](docs/bdgd-light-2025.md) e [`docs/spike-opendss.md`](docs/spike-opendss.md).

## Comandos

| comando | para quê |
|---|---|
| `export` | BDGD (.gdb) → GeoParquet/Parquet, em lotes |
| `inventario` · `vizinhos` | uma linha por alimentador (36 colunas, score) · com quem ele se interliga |
| `recortar` | um GeoPackage por alimentador e um do cluster, com as interligações calculadas |
| `grafo` | topologia: fonte, falta, isolamento, opções de restauração (`--score` valida no gêmeo) |
| `dss` | gera o modelo OpenDSS do recorte, roda fluxo de potência e aplica manobras |
| `tiles` | recorte → PMTiles para o console |
| `sim` · `agente` · `serve` | injeta eventos · roda o agente num evento · sobe o console com backend |
| `mcp` · `aprovar` · `audit` | servidor MCP · aprovação humana pela CLI · verifica a trilha de auditoria |
| `llm` · `bench` | testa o provedor de LLM · benchmark do agente (pass@k, tokens, US$) |

Detalhe de cada um, com exemplos e saídas reais, em [`docs/comandos.md`](docs/comandos.md).

## Console

`console/` é o front-end (Vite + TypeScript + [MapLibre GL JS](https://maplibre.org/) +
[PMTiles](https://protomaps.com/docs/pmtiles)): rede com simbologia de operador, estado energizado,
fila de eventos, proposta do agente e aprovação. Sem backend ele funciona como mapa estático — é assim
que está publicado no Pages. Com `bdgd-light serve` ativo, o painel do COD aparece. Detalhes em
[`console/README.md`](console/README.md).

## Rigor e números

A suíte tem **292 testes** e roda sem dados reais (fixtures sintéticas). O agente é avaliado por um
benchmark de **34 tarefas** com gabarito recalculado pelas próprias ferramentas, medindo pass@k,
ordenação das chamadas, tokens e custo em dólares por acerto: o operador determinístico acerta 100 %,
o Gemini 2.5 Flash fica em 99 % (284 execuções por US$ 1,69) e o gpt-4.1-mini resolve os três cenários
em 4–5 rodadas. Metodologia e tabelas em [`docs/bench.md`](docs/bench.md); leitura dos resultados do
agente em [`docs/agent.md`](docs/agent.md).

## Documentação

| documento | conteúdo |
|---|---|
| [`docs/demo-roteiro.md`](docs/demo-roteiro.md) | roteiro de aula de 15 min, com tempos e plano B |
| [`docs/escopo-cidade.md`](docs/escopo-cidade.md) | por que Tijuca e Ipanema, e o panorama do Rio por bairro |
| [`docs/bdgd-light-2025.md`](docs/bdgd-light-2025.md) · [`docs/bdgd-relacoes.md`](docs/bdgd-relacoes.md) | o que a BDGD da Light tem de particular · como as camadas se ligam |
| [`docs/gd-light.md`](docs/gd-light.md) | MMGD ANEEL × BDGD Light: chave de junção, penetração por alimentador, conjuntos e divergências |
| [`docs/grid-modelo.md`](docs/grid-modelo.md) · [`docs/spike-opendss.md`](docs/spike-opendss.md) | BDGD → grafo · BDGD → OpenDSS, convergência e qualidade de dado |
| [`docs/mcp-ferramentas.md`](docs/mcp-ferramentas.md) · [`docs/agent.md`](docs/agent.md) | as 12 ferramentas · o agente, prompt e resultados |
| [`docs/console.md`](docs/console.md) · [`docs/sim.md`](docs/sim.md) | backend do console e HITL · simulador de eventos |
| [`docs/review/`](docs/review/) | diários das rodadas de desenvolvimento e revisões de cada PR |

## Fluxo de trabalho

Backlog em Issues; cada issue é especificada com critérios de aceite, implementada pelo GitHub Copilot
em PR próprio e revisada antes do merge (as revisões ficam em `docs/review/`). Convenções em
[`.github/copilot-instructions.md`](.github/copilot-instructions.md). Ambiente sempre com `uv`
(`uv sync`, `uv run`, `uv add`); dados nunca entram no git.

## Dados e licença

Código sob licença MIT. Os dados são abertos da ANEEL (BDGD da Light, distribuidora 382, ano-base
2025) e **não** são redistribuídos aqui: `scripts/baixar_bdgd.py` baixa a BDGD e
`scripts/baixar_gd.py` baixa a MMGD diretamente da fonte. Este projeto não tem vínculo com a Light
nem com a ANEEL.

## Referências

- ANEEL — [BDGD (Módulo 10 do PRODIST)](https://dadosabertos.aneel.gov.br/dataset/base-de-dados-geografica-da-distribuidora-bdgd) e [Manual da BDGD](https://dadosabertos-aneel.opendata.arcgis.com/documents/f0d5c43ac67d4f5eb2ddffa4589501b2)
- Badmus et al., *PowerChain: A Verifiable Agentic AI System for Automating Distribution Grid Analyses* — [arXiv:2508.17094](https://arxiv.org/abs/2508.17094)
- [bdgd2opendss](https://github.com/PauloRadatz/bdgd2opendss) (MIT) — conversão BDGD → OpenDSS
- [OpenDSSDirect.py](https://github.com/dss-extensions/OpenDSSDirect.py)
