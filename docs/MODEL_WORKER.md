# Contrato do worker de inferência

O serviço principal não treina modelos nem inventa previsões. Quando `AGRI_VISION_INFERENCE_URL` está configurada e existe um registro `validated` compatível, ele envia a captura ao worker externo.

## Requisição

`POST` para `AGRI_VISION_INFERENCE_URL`, com `Content-Type: application/json` e, quando configurado, `Authorization: Bearer <AGRI_VISION_INFERENCE_API_KEY>`:

```json
{
  "task": "contagem de frutos",
  "model_version": "modelo-2026-01",
  "capture_metadata": {
    "width": 1280,
    "height": 720,
    "crop": "café",
    "latitude": -23.05,
    "longitude": -47.05
  },
  "media_base64": "..."
}
```

O worker deve tratar a imagem e os metadados como dados potencialmente sensíveis. Não deve registrar a imagem, a chave ou os metadados completos em logs.

## Resposta aceita

Resposta HTTP `2xx` em JSON, com todos os campos abaixo:

```json
{
  "prediction": 12.0,
  "confidence": 0.87,
  "model_version": "modelo-2026-01",
  "status": "predicted"
}
```

Regras aplicadas pelo serviço principal:

- `prediction` precisa ser numérica e finita;
- `confidence` precisa estar entre `0` e `1`;
- `model_version` precisa ser exatamente a versão registrada e validada;
- a resposta não autoriza extrapolar a amostra para o talhão;
- a previsão permanece sujeita à revisão humana e ao protocolo da campanha.

## Respostas não aceitas

Timeout, indisponibilidade, JSON inválido, versão divergente, valores fora do contrato ou HTTP não-`2xx` não geram previsão. O serviço grava um estado explícito, como `inference_unavailable` ou `invalid_model_response`.

Sem worker configurado, ou sem modelo `validated` para a organização, tarefa e versão, o resultado é `pending_model` ou `model_not_validated`.

## Gate antes de produção

Antes de configurar a URL:

1. Escolher uma única cultura e variável visual mensurável.
2. Registrar dataset com separação por propriedade, tempo ou campanha.
3. Avaliar em grupos independentes não usados no treino.
4. Registrar SHA-256 do artefato e versão do modelo.
5. Obter aprovação do responsável agronômico e executar os gates de `docs/ACCEPTANCE.md`.

Uma resposta `predicted` demonstra apenas que o contrato técnico foi atendido; não demonstra desempenho agronômico suficiente para recomendar manejo ou produtividade.
