# Simulador de eventos (`bdgd_light.sim`)

Gera eventos operacionais sobre um cluster do recorte e os publica numa fila simples (JSON Lines) que o
agente ([#34](https://github.com/ViniciusAguiar15/bdgd-light/issues/34)) consome e o console
([#35](https://github.com/ViniciusAguiar15/bdgd-light/issues/35)) mostra. Issue
[#33](https://github.com/ViniciusAguiar15/bdgd-light/issues/33); referência conceitual: a camada de
"event injection" do PowerChain (arXiv 2508.17094).

O simulador **não altera o estado da rede**: ele só descreve o que aconteceu (e o que aconteceria se
o religador abrisse). Quem muda o gêmeo é o agente, via `inject_fault`/`set_switch` do
[servidor MCP](mcp-ferramentas.md), sempre com aprovação humana para manobras.

## Tipos de evento

| `tipo` | Alvo | O que representa | Ação esperada do agente |
|---|---|---|---|
| `falta_permanente` | `trecho` (COD_ID de um SSDMT) | curto no trecho; o religador do CTMT abre e **não** religa | `inject_fault(trecho)` → `locate_fault` → `isolate_fault` → `restore_options` → `propose_plan` → aprovação humana → `set_switch` |
| `falta_transitoria` | `trecho` | curto que se extingue; o religador religa após o tempo morto | só registrar (sem manobra) |
| `pico_carga` | `ctmt` | demanda acima do caso base por alguns minutos (`loadmult` 1,15–1,6) | `run_powerflow(loadmult=…)` e checar violações de tensão/carregamento |
| `chave_indisponivel` | `chave` (telecomandada, `TLCD`) | telecomando fora (comunicação, bateria, manutenção) | não contar com a chave nos planos; manobra só por equipe |

Sem `--tipo`, o sorteio usa os pesos 5:3:2:1 (permanente : transitória : pico : chave) — faltas
permanentes dominam porque são o caso de uso da demo (FLISR).

## Formato da mensagem

Uma linha JSON por evento. Campos fixos: `tipo`, `cluster`, `hora` (ISO 8601, UTC), `detalhes`.
Campos opcionais entram só quando fazem sentido: `trecho` **ou** `ctmt` **ou** `chave` (o alvo;
faltas também trazem `ctmt`), `cenario` (quando veio de um cenário nomeado), `seed` (quando houve
semente) e `id` (`E-0001`, `E-0002`… atribuído pela fila ao publicar).

Exemplo real gerado sobre o cluster sintético dos testes (`tests/fixtures/parquet_mini`,
`bdgd-light sim --cluster … --tipo falta --trecho SEG002 --seed 1 --json`):

```json
{
  "id": "E-0001",
  "tipo": "falta_permanente",
  "cluster": "cluster_RJO001-RJO002",
  "hora": "2026-09-10T16:24:25+00:00",
  "trecho": "SEG002",
  "ctmt": "RJO001",
  "seed": 1,
  "detalhes": {
    "ctmt": "RJO001",
    "comp_m": 102.5,
    "tip_cnd": "CAB001",
    "pac": ["RJO001_MT_3", "RJO001_MT_4"],
    "religador": "CH008",
    "chaves_com_indicacao": ["CH008", "CH001"],
    "sem_tensao_se_religador_abrir": {
      "n_nos": 7,
      "clientes": {"total": 5, "ucbt": 4, "ucmt": 1, "trafos": 2, "kva": 120.0}
    },
    "acao_esperada": "religador abre e não religa: localizar, isolar e restaurar (inject_fault no MCP)"
  }
}
```

`detalhes` por tipo (todos trazem `acao_esperada`; os campos de rede só existem quando o cluster foi
carregado — sem recorte disponível o evento sai "magro", só com o cenário):

| tipo | campos de `detalhes` |
|---|---|
| faltas | `ctmt`, `comp_m`, `tip_cnd`, `pac` (os dois PACs do trecho), `religador` (primeira chave fechada no caminho fonte→trecho), `chaves_com_indicacao` (chaves fechadas no caminho, na ordem fonte→falta — o que a telemetria de proteção "veria"), `sem_tensao_se_religador_abrir` (`n_nos` + `clientes` de `Rede.customers`) |
| `falta_transitoria` | os acima + `tempo_morto_s` (0,5/1/2/5 s) e `religou: true` |
| `pico_carga` | `loadmult` (uniforme 1,15–1,6, 2 casas), `duracao_min` (30/60/120), `clientes` do CTMT |
| `chave_indisponivel` | `motivo`, `normal` (`NA`/`NF`), `estado` (`aberta`/`fechada`), `tlcd: true` |
| cenário nomeado | + `descricao` do cenário |

## Sorteios e reprodutibilidade

- Trecho em falta: sorteado **ponderado pelo comprimento** (`comp`, em metros) entre os SSDMT do
  cluster — um trecho de 270 m sai ~2,6× mais que um de 102 m; trechos sem comprimento nunca saem
  se houver outros com comprimento (se todos tiverem 0, o sorteio vira uniforme).
- CTMT do pico: uniforme entre os alimentadores do cluster. Chave indisponível: uniforme entre as
  chaves com `TLCD` (cluster sem chave telecomandada é erro — o evento não faz sentido nele).
- Tudo sai de um único `random.Random(seed)`: **mesma semente, mesmo cluster e mesma sequência de
  chamadas ⇒ mesmos eventos** (só `hora` e `id` mudam). Sem semente, a sequência é aleatória e o
  campo `seed` não é gravado.
- O simulador só lê o grafo (`Rede.trechos`, `chaves`, `ctmts`, `caminho_da_fonte`, `downstream`,
  `customers`); nada do que ele produz depende do estado atual de chaves além do campo `estado`.

## Cenários nomeados

Os alvos vêm de [`escopo-cidade.md`](escopo-cidade.md) (v3) e do [spike OpenDSS](spike-opendss.md):

| cenário | cluster | evento | por que importa |
|---|---|---|---|
| `tijuca_cabofrio_tronco` | `tijuca` | falta permanente no trecho `11304252` de **ALC9925** (LDA CABOFRIO, SE Aldeia Campista) | isolar abrindo `10927447` e `11035901`; 4.036 UCBT restauráveis por ALC9946, RCP9882 ou URG29983 — o gêmeo ranqueia as três SEs (URG29983 é inviável por um gargalo de 20 m) |
| `ipanema_9210` | `ipanema` | falta permanente no trecho `11409068` de **PTS0001** (LDS 9210, a 144 m da SE Posto Seis) | **cenário negativo**: as 35 NA são pátio de manobra da SE; nenhuma chave de campo restaura — o agente deve reconhecer a ausência de opção e recomendar despacho de equipe |
| `taquara_bocari` | `taquara` | falta permanente no trecho `11798327` de **TQR33862** (LDA BOCARI) | regressão do cluster TQR: 4 chaves isolam, 2.023 UCBT restauráveis por PARNAIBA (tie `1007642983`) ou CURUMAU (`789941518`) |
| `aleatorio` | o que estiver carregado | tipo e alvo sorteados com os pesos acima | carga de trabalho contínua para agente e console |

Com o recorte do cluster disponível, `Simulador.cenario()` confere que o trecho existe nele (um cenário
da Tijuca sobre o cluster de Ipanema é erro) e enriquece os detalhes. Sem o recorte (por exemplo no
CI ou numa máquina sem `data/`), `bdgd-light sim --cenario …` emite o evento com um aviso e sem os
campos de rede — suficiente para o agente chamar `load_cluster` + `inject_fault` pelo `trecho`.

## Fila

`FilaEventos(caminho)` é um arquivo JSON Lines **só de acréscimo** (`data/eventos/eventos.jsonl` por
padrão; a pasta `data/` não é versionada). `publicar(evento)` atribui o próximo `id` (`E-%04d`,
continuando a numeração de instâncias anteriores), grava a linha e devolve o evento; `listar(desde=n)`
devolve os eventos com índice ≥ `n`; `ultimo()` o mais recente. O consumidor guarda o índice (ou o
`id`) do último evento tratado — não há remoção nem ack, o que é suficiente para a demo local e mantém
o arquivo como registro do que foi injetado.

## CLI

```bash
uv run bdgd-light sim --listar                                   # cenários nomeados
uv run bdgd-light sim --cluster tijuca --emitir 1 --tipo falta    # 1 falta permanente sorteada por km
uv run bdgd-light sim --cenario tijuca_cabofrio_tronco            # o cenário A da demo, na fila
uv run bdgd-light sim --cenario ipanema_9210 --json               # cenário negativo, em JSON Lines
uv run bdgd-light sim --cluster ipanema --emitir 5 --seed 42      # 5 eventos reprodutíveis
uv run bdgd-light sim --cluster taquara --tipo pico --ctmt TQR33862
uv run bdgd-light sim --cluster tijuca --tipo chave --sem-publicar --json   # só imprime
uv run bdgd-light sim --mostrar 5                                 # últimos 5 da fila
```

Opções: `--cluster` (nome da demo `tijuca`/`ipanema`/`taquara`, ou caminho de um `.gpkg` do recorte;
resolvido por `bdgd_light.mcp_server.resolver_cluster` em `--feeders`, padrão `data/feeders`),
`--cenario`, `--tipo` (`falta`, `transitoria`, `pico`, `chave` e sinônimos), `--trecho`/`--ctmt`/`--chave`
(alvo fixo), `--emitir N`, `--seed`, `--fila` (padrão `data/eventos/eventos.jsonl`), `--sem-publicar`,
`--json`, `--listar`, `--mostrar N`. Erros de uso (tipo inválido, cluster inexistente, cenário de outro
cluster) saem com código 1 e nada é publicado.

## Em Python

```python
from bdgd_light.grid import Cluster
from bdgd_light.sim import FilaEventos, Simulador

rede = Cluster.from_gpkg("data/feeders/cluster_tijuca.gpkg")
sim = Simulador(rede, "tijuca", seed=7)
ev = sim.cenario("tijuca_cabofrio_tronco")  # ou sim.gerar(), sim.falta_permanente("11304252"), …
fila = FilaEventos("data/eventos/eventos.jsonl")
fila.publicar(ev)  # ev.id == "E-0001"
for e in fila.listar(desde=0):
    print(e.id, e.tipo, e.alvo, e.detalhes.get("acao_esperada"))
```

## Decisões e pendências

- Fila em arquivo (JSONL) em vez de broker: zero dependência, inspecionável com `tail -f`, e o mesmo
  arquivo serve de registro do que foi injetado. Se o console precisar de *push*, o servidor HTTP do
  MCP pode expor a fila (`GET /eventos?desde=n`) — fica para #35.
- A "telemetria" de uma falta é a lista de chaves fechadas no caminho fonte→falta
  (`chaves_com_indicacao`); não há modelagem de fusíveis, religadores intermediários nem de
  indicadores de falta em campo — o mesmo simplificador da `locate_fault` do MCP.
- Picos de carga não são propagados ao gêmeo pelo simulador; `run_powerflow(loadmult=…)` faz isso
  quando o agente decide checar.
- Sem `--seed`, o gerador usa a entropia do sistema e o evento não leva `seed`; para reproduzir um
  incidente da demo, publique com semente ou use um cenário nomeado (alvo fixo).
