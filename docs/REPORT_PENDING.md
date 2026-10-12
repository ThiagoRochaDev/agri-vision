# Pendências cruzadas com o relatório TGR

Última revisão: 2026-10-12.

Este documento separa o que já está implementado neste repositório do que depende de
decisão, autorização, dado externo ou operação fora do código. Ele complementa
`docs/ACCEPTANCE.md` e evita apresentar o piloto agronômico como produção concluída.

## Estado deste projeto

| Item | Estado | Próximo passo | Responsável |
|---|---|---|---|
| Serviço local, API, persistência e revisão humana | IMPLEMENTADO | Executar homologação com configuração real | Equipe técnica |
| Dataset público de maçãs e conversor reprodutível | IMPLEMENTADO COMO PESQUISA | Repetir com dados da propriedade | Equipe técnica |
| Baseline Ultralytics de pesquisa | CANDIDATO | Decidir licença de uso comercial e validar em dados independentes | Técnico + jurídico |
| Protocolo agronômico | PROPOSTA | Aprovar cultura, pergunta, unidade, amostragem e critérios | Responsável agronômico |
| `PILOT_CONFIG` | TEMPLATE | Preencher propriedade, talhões, datas, revisores e consentimentos | Operação |
| Dados reais com consentimento e anotações | BLOQUEADO | Coletar campanha real e registrar proveniência | Propriedade + agrônomo |
| Avaliação independente por propriedade/data/campanha | BLOQUEADO | Separar grupo de avaliação antes do treino | Equipe técnica |
| Modelo `validated` com SHA-256 | BLOQUEADO | Treinar, medir cobertura/MAE/erro relativo e registrar artefato | Equipe técnica |
| Piloto com rollback e aprovação | BLOQUEADO | Executar campanha, revisar amostras e assinar aceite | Agrônomo responsável |
| Produção pública | NÃO AUTORIZADA | Configurar gateway/TLS/secrets/banco/backups/monitoramento/CI | Operação + proprietário |

## O que não é pendência deste repositório

O relatório vinculado também lista pendências de outros produtos TGR: republicação de
sites, revisão de PRs, Load Balancer dos produtos `detect-*`, Directions API do
`easy-food`, exigência municipal do Move Easy, teste em Raspberry Pi do NetSentinel,
termos jurídicos e parceria para raio-X real. Esses itens não foram marcados como
resolvidos aqui porque pertencem a outros repositórios ou exigem autorização humana.

## Bloqueios externos que permanecem

1. **Dado agronômico real:** o dataset público de maçãs é somente referência técnica;
   não comprova desempenho na propriedade, cultura ou condição de captura do piloto.
2. **Licença do runtime/modelo:** o baseline usa Ultralytics para pesquisa. A licença
   AGPL-3.0 ou Enterprise deve ser analisada antes de uma implantação comercial.
3. **Aprovação agronômica:** cultura, pergunta visual, protocolo, critérios de aceite e
   revisão humana não podem ser inferidos automaticamente pelo software.
4. **Infraestrutura:** o `docker-compose.yml` serve homologação. Exposição pública exige
   gateway de identidade, TLS, secrets manager, banco persistente, backup testado,
   monitoramento, rotação de credenciais e CI com publicação controlada.
5. **Autorização do GitHub Actions:** o repositório pode ser criado e o código enviado,
   mas a publicação do workflow exige que a conta GitHub autorize o escopo `workflow`.

## Critério de encerramento

Não declarar este projeto “finalizado para produção” enquanto houver qualquer estado
`BLOQUEADO`, `CANDIDATO` ou `NÃO AUTORIZADA` acima. O encerramento ocorre quando o gate
do piloto retorna `OK pilot gate`, o modelo está `validated`, a avaliação independente
foi aprovada, o piloto teve revisão/rollback testados e a checklist de produção foi
assinada pelo responsável técnico e agronômico.
