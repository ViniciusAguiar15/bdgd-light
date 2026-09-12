# Sensibilidade das premissas da restauração

Varredura real da issue #96: `loadmult` em {0,6; 0,8; 1,0; 1,2; 1,4}, carga por curva × carga nominal e `FAS_CON` cadastrado × rebalanceado com critério conservador (só em cargas BT monofásicas com mais de uma fase disponível no PAC).

CSV completo: `docs/bench/2026-09-12-sensibilidade-premissas.csv`.

## Casos analisados

- cenários fixos: `tijuca_cabofrio_tronco`, `ipanema_9210`, `taquara_bocari`
- alimentadores adicionais escolhidos da #91: `BRR38521`, `ALC683`, `PDG33010` (prioridade para casos com opções viáveis e regiões distintas).

## Ponto de virada por caso

| caso | base | loadmult nas premissas atuais | carga nominal | FAS_CON rebalanceado | conclusão |
|---|---|---|---|---|---|
| tijuca_cabofrio_tronco | base atual: 974020904 (loadmult 1,0) | premissas atuais: sem limiar único (0,6–1,0 mantém 974020904; 1,2 → 746851189; 1,4 → sem transferência) | carga nominal: vira em loadmult 0,8 (974020904 → sem transferência) | FAS_CON rebalanceado: sem limiar único (0,6–1,0 mantém 974020904; 1,2 → 746851189; 1,4 → sem transferência) | não há limiar único nas premissas atuais: 0,6–1,0 mantém 974020904; 1,2 → 746851189; 1,4 → sem transferência |
| ipanema_9210 | base atual: sem transferência (loadmult 1,0) | premissas atuais: não vira na faixa testada (0,6–1,4) | carga nominal: não vira na faixa testada (0,6–1,4) | FAS_CON rebalanceado: não vira na faixa testada (0,6–1,4) | a escolha sem transferência se mantém em toda a faixa 0,6–1,4 nas premissas atuais |
| taquara_bocari | base atual: 11053620 (loadmult 1,0) | premissas atuais: sem limiar único (0,6 → 789941518; 0,8 → 11056672; 1,0 mantém 11053620; 1,2–1,4 → 11056672) | carga nominal: sem limiar único (0,6–1,2 → 11056672; 1,4 mantém 11053620) | FAS_CON rebalanceado: sem limiar único (0,6 → 789941518; 0,8 mantém 11053620; 1,0 → 11056672; 1,2 mantém 11053620; 1,4 → 11056672) | não há limiar único nas premissas atuais: 0,6 → 789941518; 0,8 → 11056672; 1,0 mantém 11053620; 1,2–1,4 → 11056672 |
| BRR38521 | base atual: 462279321 (loadmult 1,0) | premissas atuais: sem limiar único (0,6 mantém 462279321; 0,8 → 470326292; 1,0–1,4 mantém 462279321) | carga nominal: sem limiar único (0,6 mantém 462279321; 0,8 → 470326292; 1,0 → 1004924862; 1,2–1,4 → sem transferência) | FAS_CON rebalanceado: não vira na faixa testada (0,6–1,4) | não há limiar único nas premissas atuais: 0,6 mantém 462279321; 0,8 → 470326292; 1,0–1,4 mantém 462279321 |
| ALC683 | base atual: 11121256 (loadmult 1,0) | premissas atuais: não vira na faixa testada (0,6–1,4) | carga nominal: não vira na faixa testada (0,6–1,4) | FAS_CON rebalanceado: não vira na faixa testada (0,6–1,4) | a escolha 11121256 se mantém em toda a faixa 0,6–1,4 nas premissas atuais |
| PDG33010 | base atual: 11009531 (loadmult 1,0) | premissas atuais: não vira na faixa testada (0,6–1,4) | carga nominal: não vira na faixa testada (0,6–1,4) | FAS_CON rebalanceado: não vira na faixa testada (0,6–1,4) | a escolha 11009531 se mantém em toda a faixa 0,6–1,4 nas premissas atuais |

## Leitura direta

### tijuca_cabofrio_tronco

- premissas atuais: sem limiar único (0,6–1,0 mantém 974020904; 1,2 → 746851189; 1,4 → sem transferência).
- carga nominal: vira em loadmult 0,8 (974020904 → sem transferência).
- FAS_CON rebalanceado: sem limiar único (0,6–1,0 mantém 974020904; 1,2 → 746851189; 1,4 → sem transferência).
- Conclusão: não há limiar único nas premissas atuais: 0,6–1,0 mantém 974020904; 1,2 → 746851189; 1,4 → sem transferência.

### ipanema_9210

- premissas atuais: não vira na faixa testada (0,6–1,4).
- carga nominal: não vira na faixa testada (0,6–1,4).
- FAS_CON rebalanceado: não vira na faixa testada (0,6–1,4).
- Conclusão: a escolha sem transferência se mantém em toda a faixa 0,6–1,4 nas premissas atuais.

### taquara_bocari

- premissas atuais: sem limiar único (0,6 → 789941518; 0,8 → 11056672; 1,0 mantém 11053620; 1,2–1,4 → 11056672).
- carga nominal: sem limiar único (0,6–1,2 → 11056672; 1,4 mantém 11053620).
- FAS_CON rebalanceado: sem limiar único (0,6 → 789941518; 0,8 mantém 11053620; 1,0 → 11056672; 1,2 mantém 11053620; 1,4 → 11056672).
- Conclusão: não há limiar único nas premissas atuais: 0,6 → 789941518; 0,8 → 11056672; 1,0 mantém 11053620; 1,2–1,4 → 11056672.

### BRR38521

- premissas atuais: sem limiar único (0,6 mantém 462279321; 0,8 → 470326292; 1,0–1,4 mantém 462279321).
- carga nominal: sem limiar único (0,6 mantém 462279321; 0,8 → 470326292; 1,0 → 1004924862; 1,2–1,4 → sem transferência).
- FAS_CON rebalanceado: não vira na faixa testada (0,6–1,4).
- Conclusão: não há limiar único nas premissas atuais: 0,6 mantém 462279321; 0,8 → 470326292; 1,0–1,4 mantém 462279321.

### ALC683

- premissas atuais: não vira na faixa testada (0,6–1,4).
- carga nominal: não vira na faixa testada (0,6–1,4).
- FAS_CON rebalanceado: não vira na faixa testada (0,6–1,4).
- Conclusão: a escolha 11121256 se mantém em toda a faixa 0,6–1,4 nas premissas atuais.

### PDG33010

- premissas atuais: não vira na faixa testada (0,6–1,4).
- carga nominal: não vira na faixa testada (0,6–1,4).
- FAS_CON rebalanceado: não vira na faixa testada (0,6–1,4).
- Conclusão: a escolha 11009531 se mantém em toda a faixa 0,6–1,4 nas premissas atuais.

## Observações metodológicas

- `tempo_reparo` não entrou na varredura porque **não participa do score elétrico nem da ordenação de `restore_options`**; hoje ele só altera o campo de impacto estimado.
- `FAS_CON rebalanceado` aqui **não** muda o comportamento do produto: é apenas um cenário de medição offline. Cargas em PAC de dois fios ficaram como cadastradas.
- Como houve inversões reais de decisão na faixa testada, a observação para o operador virou follow-up em **#112**. Nesta #96, **nenhum comportamento do agente ou da UI foi alterado**.
