# Agri Vision MVP

Primeira implementação isolada do item 5 do Radar: uma ocorrência visual mensurável em uma cultura, organizada por fazenda, talhão e campanha.

## Escopo entregue

- Cadastro de fazendas, talhões e campanhas com cultura e protocolo.
- Upload em lote ou sincronização posterior por `client_event_id` idempotente.
- Armazenamento local dos arquivos recebidos e metadados de captura.
- Upload de JPEG, PNG ou WebP com hash SHA-256; formatos arbitrários são rejeitados.
- Fila offline no navegador via IndexedDB, sincronizada por `POST /sync-batches`; a chave API nunca é persistida pela interface.
- Validação de resolução, nitidez, cultura e localização no talhão.
- Observação com versão de modelo explícita e estado `pending_model` até existir um modelo validado.
- Revisão humana com valor corrigido, responsável, nota e data.
- Relatório por talhão/campanha com tamanho da amostra e bloqueio explícito de extrapolação.
- Isolamento por organização via `X-Organization-ID`; a interface local usa `default`.
- Auditoria de ações críticas via `X-Actor-ID`; consulte `GET /audit-events`.
- Registro de versões de dataset com proveniência, consentimento e grupo de separação explícito (`property`, `time` ou `campaign`).
- Registro de versões de modelo com hash SHA-256, tarefa, dataset de origem e estado de validação.
- Estados de campanha com transições auditadas para coleta, revisão, pausa e fechamento.
- Campanhas em revisão, pausa ou fechamento rejeitam novas amostras; retries de eventos já recebidos continuam idempotentes.

O serviço não inventa uma inferência: sem cultura, tarefa, dados anotados e baseline agronômico definidos, a observação permanece pendente de modelo.

## Executar

```powershell
python run.py
```

O serviço usa somente a biblioteca padrão do Python 3.12, limita requisições a 10 MiB e mídias a 6 MiB, e abre `http://127.0.0.1:8765`.

Verifique a execução em `GET /health` e a prontidão do banco em `GET /ready`.
Métricas Prometheus básicas ficam em `GET /metrics`.

Abra `http://127.0.0.1:8765/` para usar a interface local do fluxo completo.

## Fluxo mínimo

1. `POST /farms` com `{"name":"Fazenda teste","region":"SP"}`.
2. `POST /plots` com `farm_id`, `name`, `crop` e, opcionalmente, `geometry` como caixa `min_lat`, `min_lon`, `max_lat`, `max_lon`.
3. `POST /campaigns` com `plot_id`, `protocol_version`, `captured_period` e `task`.
4. `POST /campaigns/{id}/samples` com `client_event_id`, `content_hash` e `capture_metadata`.
5. Consulte `GET /campaigns/{id}/observations` e revise em `POST /observations/{id}/reviews`.
6. Consulte `GET /plots/{id}/reports`.
7. Consulte `GET /plots/{id}/coverage` para pontos GPS e contagens de cobertura; localização ausente permanece pendente.
8. Execute `POST /campaigns/{id}/inference`; enquanto não houver modelo validado, o resultado permanece `pending_model`.
9. Registre o dataset antes de treinar com `POST /dataset-versions` e consulte em `GET /dataset-versions`.
10. Consulte `GET /campaigns/{id}/evaluation` depois de haver previsões e revisões humanas.
11. Consulte o histórico em `GET /observations/{id}/reviews`; cada correção gera uma versão imutável.
12. Registre modelos em `POST /model-versions`; um modelo `validated` exige `dataset_version_id`.
13. Mova campanhas com `POST /campaigns/{id}/transition` usando `collecting`, `review`, `closed` ou `paused`.

Para exportar dados, crie a versão com `evaluation_groups` explícitos no `split_definition` e execute `export_dataset.py`; amostras rejeitadas nunca entram no JSONL.
Valide o arquivo exportado antes de treinar com `python validate_dataset.py caminho\para\dataset.jsonl`; o comando verifica os dois splits, a existência das mídias e os hashes.

Relatórios comparam médias revisadas entre campanhas consecutivas, mas mantêm `extrapolation_allowed: false` e não tratam amostras pequenas como estimativa da lavoura inteira.
O mesmo relatório pode ser exportado para o técnico em `GET /plots/{id}/reports.csv`.

## Limites conhecidos

O MVP ainda não treina nem executa um detector. O endpoint de inferência usa um worker pendente para manter o contrato e não fabricar resultados. A próxima etapa correta é fechar uma pergunta agronômica, protocolo de coleta, anotação especializada e baseline independente antes de trocar esse worker. Mesmo com `AGRI_VISION_INFERENCE_URL`, o serviço só aceita previsões quando a versão e a tarefa também estão registradas como `validated` no registry local, e rejeita respostas que informem outra versão.

## Operação

O checklist operacional está em [docs/OPERATIONS.md](docs/OPERATIONS.md).
O deploy com TLS automático está em [docs/PRODUCTION_DEPLOYMENT.md](docs/PRODUCTION_DEPLOYMENT.md);
use `docker-compose.production.yml` somente com domínio, DNS e secrets reais.
O contrato do worker externo está em [docs/MODEL_WORKER.md](docs/MODEL_WORKER.md).
O protocolo agronômico que deve ser aprovado antes do modelo está em [docs/PILOT_PROTOCOL.md](docs/PILOT_PROTOCOL.md).
Os insumos públicos baixados e seus limites estão em [docs/EXTERNAL_DATASETS.md](docs/EXTERNAL_DATASETS.md), com o manifesto em `data/external/apple_maturity/MANIFEST.json`.
Para gerar o JSONL de pesquisa a partir das anotações VIA: `python external_dataset_to_jsonl.py --root data/external/apple_maturity/dataset/dataset-20260508 --dataset-version-id apple-maturity-gfcmdbvw65-v4 --output data/external/apple_maturity/apple-maturity-original.jsonl`.
O baseline experimental e suas métricas estão em [docs/MODEL_BASELINE.md](docs/MODEL_BASELINE.md); ele permanece candidato e não é usado automaticamente pelo serviço.
O gate executável do piloto usa [docs/PILOT_CONFIG.example.json](docs/PILOT_CONFIG.example.json) e pode ser validado com `python pilot_check.py caminho\para\pilot-config.json`.
O estado dos critérios de aceite está em [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md).
O manual do operador está em [docs/USER_GUIDE.md](docs/USER_GUIDE.md).
As pendências cruzadas com o relatório TGR e os bloqueios externos estão em
[docs/REPORT_PENDING.md](docs/REPORT_PENDING.md).

As configurações `AGRI_VISION_HOST`, `AGRI_VISION_PORT`, `AGRI_VISION_DATABASE` e `AGRI_VISION_MEDIA_DIR` podem ser fornecidas por ambiente. Para uma cópia consistente:

Defina `AGRI_VISION_API_KEY` no secret store do ambiente de produção. Com essa variável, endpoints de dados exigem `X-API-Key` ou `Authorization: Bearer ...`; `/health` e `/ready` permanecem públicos para o monitoramento.
Cada resposta HTTP inclui `X-Request-ID`; o cliente pode enviar um identificador próprio para correlacionar logs. Respostas também usam `X-Content-Type-Options: nosniff` e `Cache-Control: no-store`.

```powershell
python backup.py --database data\agri_vision.sqlite3 --media-dir data\media --output backups\snapshot.zip
```

Restaure somente em diretório vazio:

```powershell
python restore.py backups\snapshot.zip restore\candidate
```

Uploads com `media_base64` precisam corresponder ao `content_hash` SHA-256 e têm limite de 6 MiB.

Retenção começa em modo de prévia; só use `--execute` após backup e aprovação:

```powershell
python retention.py --days 365 --organization-id default
python retention.py --days 365 --organization-id default --execute
```

O `Dockerfile` executa o serviço como usuário não-root em `0.0.0.0:8765`, com dados persistidos em `/data`. TLS, autenticação de identidade e publicação devem ficar em um proxy/ambiente controlado antes de expor a internet; o serviço local não deve ser publicado diretamente.

Para homologação local com autenticação:

```powershell
Copy-Item .env.example .env
# substitua o valor de AGRI_VISION_API_KEY antes de iniciar
docker compose up --build
```

Com o serviço em execução, valide a instância sem alterar dados:

```powershell
python production_check.py --url http://127.0.0.1:8765 --api-key "$env:AGRI_VISION_API_KEY"
```

Para uma checagem local sem autenticação, use `--allow-unauthenticated` explicitamente; essa opção não deve ser usada como gate de produção.

## Publicação e limites

O repositório segue a convenção dos projetos TGR: documentação de instalação, operação, segurança, contribuição e decisões técnicas ficam versionadas junto do código. O dataset, as imagens, os pesos e os artefatos de treino são insumos externos ignorados pelo Git; sua procedência e licença ficam nos manifestos e em `NOTICE`.

O baseline de maçãs é experimental. Antes de usar o sistema com uma propriedade real, preencha e aprove `docs/PILOT_PROTOCOL.md`, colete dados locais com consentimento, crie um grupo independente de avaliação e resolva a licença do runtime/modelo.
O pipeline de produtos está documentado em [docs/PRODUCT_BASELINE.md](docs/PRODUCT_BASELINE.md). Ele usa SKU-110K apenas como benchmark de pesquisa; não é uma autorização para uso comercial.
