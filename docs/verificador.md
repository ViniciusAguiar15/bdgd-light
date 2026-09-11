# Verificador determinístico: planos que precisam ser reprovados

Este documento é gerado a partir da mesma matriz usada em `tests/test_verificador_adversarial.py`. Os planos são montados diretamente como estruturas Python e passados ao `Verificador`, sem qualquer cliente de LLM.

O gate é determinístico porque depende apenas do estado da `SessaoCOD`, da sequência de manobras proposta e, quando existe score elétrico, dos campos numéricos já calculados para a opção. O modelo pode sugerir qualquer plano, mas a aprovação final continua condicionada a essas checagens booleanas reproduzíveis.

| Situação | Gate reprovado | Mensagem esperada |
|---|---|---|
| Plano usa uma chave que não existe no cluster da Tijuca. | `chaves_existem` | `chave(s) inexistente(s) no cluster: CHAVE_FANTASMA` |
| Evento `chave_indisponivel`: a sequência tenta manobrar a tie indisponível. | `chaves_disponiveis` | `a sequência usa chave(s) indisponível(is): 974020904` |
| Rejeição anterior proibiu a mesma chave e o plano insiste nela. | `restricoes_operacionais` | `rejeição anterior: usa chave proibida 974020904` |
| A sequência fecha a tie antes de abrir a fronteira da falta. | `abre_antes_de_fechar` | `há fechamento antes de uma abertura na sequência` |
| A chave escolhida não consta entre as opções correntes de `restore_options`. | `opcao_em_restore_options` | `a chave CHAVE_FORA_DAS_OPCOES não está entre as opções de restore_options` |
| Rota por AMALIA/URG29983 deixa o trecho `11051956` em ~180 % de carregamento. | `sem_sobrecarga_mt` | `elemento(s) MT acima de 100 %: Line.smt_11051956` |
| Evento sem falta registrada (ex.: `pico_carga`) tenta propor manobra. | `falta_registrada` | `não há falta registrada na sessão; nada a propor` |
| A proposta não abre toda a fronteira e deixa a falta conectada. | `fronteira_isolada` | `a sequência não abre toda a fronteira da falta: falta(m) 11035901` |

Regeneração: `uv run python scripts/gerar_verificador_doc.py`.
