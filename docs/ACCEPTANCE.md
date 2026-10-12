# Matriz de aceite N06

Última revisão: 2026-10-11. Os testes abaixo são evidência do MVP técnico local; não substituem piloto de campo, parceiro agronômico ou avaliação em produção.

| Critério | Estado | Evidência | Limite |
|---|---|---|---|
| N06-T01 — generalização por propriedade/data | BLOCKED | `docs/MODEL_BASELINE.md`, `tests/test_store.py:test_dataset_export_requires_evaluation_groups_and_excludes_rejected_samples` | Há apenas baseline de 1 época em dataset externo; ainda não há conjunto independente real nem decisão de licença/modelo. |
| N06-T02 — qualidade e fora do domínio | PASS | `tests/test_store.py:test_quality_rejects_out_of_domain_and_duplicate_sync_is_idempotent`, `test_invalid_capture_metadata_is_rejected_explicitly`, `test_upload_rejects_non_image_media` | Blur é metadado/protocolo; não é uma medição visual automática. |
| N06-T03 — sincronização offline | PASS | `tests/test_store.py:test_quality_rejects_out_of_domain_and_duplicate_sync_is_idempotent`, fluxo de `POST /sync-batches` | Evidência local, sem rede móvel real. |
| N06-T04 — referência humana e erro | PASS | `tests/test_store.py:test_campaign_evaluation_reports_error_and_coverage_against_review` | Retorna MAE e erro relativo global e por faixas `0-9`, `10-49`, `50+`; valores são fixtures e não representam desempenho agronômico. |
| N06-T05 — GPS ausente/fora do talhão | PASS | `tests/test_store.py:test_missing_location_stays_pending_instead_of_being_assigned_to_a_plot` | Geometria do MVP é caixa delimitadora. |
| N06-T06 — revisão versionada | PASS | `tests/test_store.py:test_review_is_traceable_and_report_does_not_extrapolate` | Requer operador responsável no piloto. |
| N06-T07 — isolamento entre organizações | PASS | `tests/test_store.py:test_organization_scope_blocks_cross_tenant_access`, `test_api.py:test_health_is_public_but_data_requires_api_key` | Identidade forte deve ser fornecida pelo gateway em produção. |
| N06-T08 — relatório sem extrapolação | PASS | `tests/test_store.py:test_report_compares_campaign_means_without_extrapolating`, `test_api.py:test_report_csv_requires_authentication` | `extrapolation_allowed` permanece `false`. |

## Gates antes de produção

1. Copiar `docs/PILOT_CONFIG.example.json`, preencher os campos reais e executar `python pilot_check.py <configuração>`; o comando deve retornar `OK pilot gate`.
2. Preencher e aprovar `docs/PILOT_PROTOCOL.md`.
3. Coletar e anotar dados reais com consentimento e proveniência.
4. Separar avaliação por propriedade, tempo ou campanha.
5. Registrar modelo e artefato com SHA-256; somente `validated` pode inferir.
6. Reexecutar T01 com evidência datada, responsável, revisão de código/modelo e decisão agronômica.

Enquanto o primeiro gate de modelo não for concluído, o worker permanece em `pending_model` e nenhum resultado sintético é produzido.

## Pendências externas

O quadro consolidado de decisões, dependências de dados, licença do modelo,
infraestrutura e autorização de publicação está em
[`docs/REPORT_PENDING.md`](REPORT_PENDING.md). Itens de outros produtos citados no
relatório TGR não são considerados evidência de aceite deste projeto.
