# Deploy de produção

Este procedimento publica o serviço atrás de Caddy com TLS automático. Ele não
substitui a aprovação do piloto, a validação agronômica nem o registro de um
modelo `validated`.

## Pré-requisitos

- Host Linux ou VM com Docker Compose v2.
- DNS `AGRI_VISION_DOMAIN` apontando para o IP público do host.
- Portas TCP `80` e `443` liberadas; a porta `8765` deve permanecer bloqueada
  no firewall porque o serviço fica acessível somente pelo Caddy.
- Secret store para `AGRI_VISION_API_KEY` e, se usado, as credenciais do worker.
- Volume persistente para o volume Docker `agri_vision_data`.

## Publicação

```bash
cp .env.example .env
# edite .env: chave longa, domínio real e e-mail operacional
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.production.yml ps
python production_check.py --url https://$AGRI_VISION_DOMAIN --api-key "$AGRI_VISION_API_KEY"
```

O primeiro start pode levar alguns segundos para o Caddy emitir o certificado.
Não use `--allow-unauthenticated` neste ambiente.

## Backup, atualização e rollback

Antes de atualizar, crie e copie um snapshot para armazenamento externo:

```bash
docker compose exec agri-vision python backup.py \
  --database /data/agri_vision.sqlite3 \
  --media-dir /data/media \
  --output /data/backups/pre-deploy.zip
```

Valide o snapshot com `restore.py` em um diretório separado. Para rollback,
retorne à imagem anterior, restaure somente depois de validar o backup e rode
`production_check.py` novamente.

## Monitoramento

- `GET /health`: processo vivo.
- `GET /ready`: SQLite e diretório de mídia disponíveis.
- `GET /metrics`: contadores Prometheus mínimos; proteja o endpoint no gateway
  se ele for exposto fora da rede de monitoramento.
- `X-Request-ID`: correlaciona resposta e log sem registrar imagem ou segredo.

Configure alertas para falha de healthcheck, respostas `401`, `5xx`, disco cheio,
backup atrasado e expiração/renovação de certificado. A rotação da API key exige
janela controlada e atualização simultânea do secret store e dos clientes.

## Gates que continuam obrigatórios

O deploy técnico não transforma o modelo experimental em modelo agronômico
validado. Antes de liberar inferência real, conclua `docs/PILOT_PROTOCOL.md`,
`docs/PILOT_CONFIG.example.json`, avaliação independente, revisão humana,
rollback e aprovação do responsável agronômico.
