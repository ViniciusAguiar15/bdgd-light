# Roteiro de 12 minutos para um profissional do setor

Complementa [`demo-roteiro.md`](demo-roteiro.md) (aula, 15 min). Aqui o público conhece rede de
distribuição: corte o básico, vá para os dados, o verificador e a governança.

## Preparo (2 min, antes)
```bash
BDGD_CONSOLE_TOKEN=demo uv run bdgd-light serve --cluster tijuca --provider openai --porta 8010
```
Navegador em <http://127.0.0.1:8010/?cenario=tijuca>, com **operador** e **token** (`demo`) já
preenchidos. Segunda aba com o diagrama de arquitetura. Terminal visível numa terceira janela (a
saída do `serve` mostra o agente chamando as ferramentas — é bom que ele veja).

## 1. Abertura (1 min)
"Esta é a rede real da Light no Rio, vinda da BDGD da ANEEL, ano-base 2025. Vou injetar uma falta
num alimentador da Tijuca e deixar um agente de IA propor a manobra de restabelecimento. Eu aprovo
ou rejeito. Tudo que ele afirmar foi calculado por ferramentas, não pelo modelo."

## 2. A rede (1 min)
Aponte no mapa: quatro alimentadores aéreos de 13,2 kV, de **três** subestações (Aldeia Campista,
Uruguai, Rio Comprido), 1.662 nós, 148 chaves, 23 interligações. Mostre uma chave NA e diga que a
BDGD **não** declara interligação entre alimentadores — ela é calculada por geometria.

## 3. Injetar a falta (30 s + espera)
Clique em **injetar falta**. Enquanto roda, narre o que está acontecendo (dá para acompanhar no
terminal): localizar a falta pelas chaves no caminho da fonte, isolar abrindo a fronteira mínima,
listar as rotas de restauração e **rodar um fluxo de potência por rota** no OpenDSS.

## 4. A proposta — o coração da demo (3 min)
- Sequência de manobras e **4.036 clientes** a restabelecer.
- Abra as **alternativas**: dez rotas, cada uma com o motivo do descarte.
- Pare na rota por **AMALIA**: é boa pela topologia e é reprovada porque um trecho de 20 m, com
  condutor de 132 A, vai a **180 %**. "Nenhuma análise de grafo veria isso."
- Mostre o **verificador**: 11 checagens determinísticas (chave existe, abre antes de fechar,
  fronteira isolada, convergência, tensão, corrente). Se reprova, o agente replaneja.

## 5. Aprovação (1 min)
Aprove **uma manobra por clique**. O mapa recolore a cada uma: primeiro isola (tudo ainda apagado),
depois fecha a interligação (rede volta, sobra a zona da falta). Diga: sem token válido de uma
proposta aprovada, `set_switch` é recusado — o agente nunca manobra.

## 6. Trilha (30 s)
Auditoria encadeada por hash: evento, cada chamada e resultado, rotas descartadas e o porquê,
proposta, quem aprovou, comandos enviados. É o que permite reconstruir o incidente depois.

## 7. Se sobrar tempo: o outro Rio (1 min)
`?cenario=ipanema` — rede subterrânea. A resposta certa é que **não há rota**: isolar e despachar
equipe. E a razão é qualidade de dado: o que parecia 141 interligações telecomandadas eram barras de
pátio de subestação.

## Variações de 1 minuto no mesmo console
- **Pico de carga** — no seletor do painel, escolha **pico de carga** e injete. O agente roda
  `run_powerflow` com o `loadmult` do evento, relata subtensões/sobrecargas previstas e o console
  mostra explicitamente **veredito: sem manobra**. Use os botões de `COD_ID` para destacar no mapa
  os trechos MT violados.
- **Chave indisponível** — escolha **chave indisponível**. O agente registra a restrição
  operacional, informa quantos clientes a jusante passam a depender de equipe e também encerra com
  **veredito: sem manobra**. É a demonstração curta de que o sistema sabe quando **não** sugerir
  chaveamento.

## 8. Arquitetura (2 min, no diagrama)
Cinco camadas: dados → três modelos da mesma rede (grafo, gêmeo OpenDSS, tiles) → 12 ferramentas por
MCP → agente orquestrador/verificador → operador. A fronteira é o MCP: em vez de ensinar eletricidade
ao LLM, damos ferramentas que já sabem eletricidade.

## Perguntas que ele vai fazer

| pergunta | resposta curta |
|---|---|
| De onde vêm os dados? | BDGD da Light, ano-base 2025, pública na ANEEL. Nada de dado interno. |
| É tempo real? | Não. A falta é injetada por simulador; não há telemetria pública. Integração real seria pelo SCADA/ADMS, e o restante da arquitetura não muda. |
| O LLM pode mandar abrir a chave errada? | Ele não manobra. Propõe; o verificador determinístico reprova plano inválido; a execução exige token de aprovação humana e segue a ordem abre-antes-de-fecha. |
| E se ele inventar um número? | Os números vêm das ferramentas, não do modelo, e o benchmark pontua a correção numérica da resposta. |
| Quanto custa e quanto demora? | Menos de um centavo de dólar por evento; 25 a 40 s, dos quais ~10 são o OpenDSS. |
| Por que não um algoritmo FLISR clássico? | Para o caso padrão, resolve — e é literalmente o que roda por baixo, no verificador. O agente ganha ao explicar a decisão, ao lidar com casos fora do padrão e ao orquestrar ferramentas heterogêneas. |
| Está pronto para produção? | Não. É nível 2 de autonomia, sobre cadastro anual, sem telemetria. O caminho é piloto assistido em alimentador com muita chave telecomandada. |

## O que **não** prometer
Redução de DEC/FEC em X %, integração com SCADA existente, autonomia sem operador, ou que o cadastro
da BDGD reflete a rede de hoje. Os limites estão em `docs/spike-opendss.md` e `docs/escopo-cidade.md`.
