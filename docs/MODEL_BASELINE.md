# Baseline experimental

## Resultado registrado

Foi executado um treino de 1 época em CPU usando o dataset público de maçãs convertido para YOLO. O resultado é somente um candidato técnico para verificar o pipeline.

- Artefato: `data/external/apple_maturity/runs/apple_baseline/weights/best.pt`
- Relatório: `data/external/apple_maturity/runs/apple_baseline/baseline_report.json`
- SHA-256: `bc61fab2fbeda5b22538f0a600a4918298b2df4b59e808e16896b15b8fd36d6d`
- Peso inicial local: `data/external/apple_maturity/weights/yolo11n-seg.pt`
- SHA-256 do peso inicial: `55ed65c56c91713d23e8402371c6c49a6fd84f257f7dce452e8d70e41dcbe152`
- Segmentação `mAP50`: `0.5502`
- Segmentação `mAP50-95`: `0.4579`
- Contagem `MAE`: `0.5230` fruto/imagem
- Cobertura técnica do conjunto de teste: `1.0`

Esses números são do conjunto externo, após apenas 1 época, e não medem desempenho na propriedade do usuário. O artefato permanece `candidate` e não pode ser registrado como `validated`.

## Licença

O runtime e os pesos Ultralytics usados no experimento estão sujeitos a AGPL-3.0 ou licença Enterprise. Antes de qualquer uso comercial, é necessária uma decisão jurídica/licenciamento; o baseline não é uma autorização de distribuição em produção.
