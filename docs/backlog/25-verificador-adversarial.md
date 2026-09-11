---
title: "test: suíte adversarial do verificador — os planos que ele precisa reprovar"
labels: area:agent, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
O argumento central do projeto é que o verificador determinístico, e não o LLM, é quem garante a
segurança da manobra. Hoje isso está espalhado em testes por funcionalidade; não existe um lugar
que mostre, de uma vez, **o que o verificador reprova e por quê**. É a evidência mais forte que a
dissertação e a apresentação podem ter — e também a defesa contra "e se o modelo alucinar?".

## Tarefa
- `tests/test_verificador_adversarial.py`: uma matriz de planos inválidos, cada um com o gate que
  deve reprová-lo, montados **sem LLM** (plano construído à mão e passado ao verificador):
  1. chave que não existe no cluster → `chaves_existem`
  2. chave com telecomando indisponível (evento `chave_indisponivel`) → `chaves_disponiveis`
  3. chave proibida por rejeição anterior → `restricoes_operacionais`
  4. fechamento antes da abertura na sequência → `abre_antes_de_fechar`
  5. opção que não está em `restore_options` → `opcao_em_restore_options`
  6. rota eletricamente inviável (AMALIA/`11051956`, condutor 132 A a ~180 %) → gate elétrico
  7. proposta sem falta registrada (ex.: durante `pico_carga`) → `falta_registrada`
  8. plano que deixa a fronteira da falta fechada (não isola) → o gate correspondente
- Para cada caso, assertar **o nome do gate** e que `ok is False` — não só que falhou.
- Gerar `docs/verificador.md` a partir da mesma matriz (tabela: situação → gate → mensagem), para
  a doc não descolar do teste. Se a tabela for gerada por script, versionar o script.

## Critérios de aceite
- [ ] Os 8 casos passam, cada um apontando o gate esperado.
- [ ] `docs/verificador.md` com a tabela e um parágrafo explicando por que o gate é determinístico.
- [ ] Nenhum caso depende de provider de LLM (roda com `--provider fake` ou sem cliente).
