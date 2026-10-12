# Protocolo do piloto agronômico

Este documento precisa ser preenchido e aprovado por um responsável agronômico antes de registrar um modelo como `validated`.

## Escopo único

- Cultura: **maçã** — escopo proposto a partir do insumo público; requer aprovação do responsável agronômico.
- Pergunta mensurável: **quantos frutos de maçã visíveis existem na imagem e quais máscaras/estágios foram detectados?**
- Unidade da saída: **contagem de frutos visíveis por imagem**, com máscaras e estágio como evidência auxiliar.
- O que não será inferido: doenças, defensivos, produtividade, frutos ocultos, total da lavoura ou qualquer extrapolação fora da cobertura observada.
- Escopo de consentimento e finalidade de uso: `[preencher com propriedade e finalidade reais antes do piloto]`
- Protocolo de revisão humana: `[quem revisa, como resolve divergências e como versiona a referência]`
- Talhões e período: `[definir população e janela reais]`

## Coleta

- Resolução mínima: `640x480`; registrar aparelho, data, hora e localização quando disponíveis.
- Capturar exemplos aceitos, fora do domínio, desfocados e sem localização para medir rejeições.
- Obter consentimento, autorização de uso e política de retenção antes do upload.
- Identificar a propriedade usada exclusivamente para avaliação antes do treinamento.

## Anotação e avaliação

- Anotador responsável: `[nome/identificador]`
- Regra de contagem ou marcação: `[descrever casos limítrofes]`
- Amostra de revisão independente: `[quantidade e grupos]`
- Métricas mínimas: cobertura, MAE e erro relativo mediano.
- Critério de liberação: `[limiar e decisão do responsável]`
- Plano de rollback: desativar o worker externo e retornar a `pending_model`.

## Gates

1. Aprovar este protocolo antes da coleta.
2. Exportar dataset com grupos de avaliação explícitos.
3. Avaliar por propriedade, tempo ou campanha não usados no treino.
4. Registrar artefato, SHA-256, dataset e versão no registry.
5. Promover para `validated` somente após revisão humana e decisão registrada.

O serviço não diagnostica doença, recomenda defensivo, promete produtividade nem extrapola uma imagem para toda a lavoura sem método validado.
