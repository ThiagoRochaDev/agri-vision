# Insumos externos

## Dataset selecionado

Foi baixada a versão 4 do conjunto [A Multi-Stage, Pixel-Level Annotated Apple Dataset for Precision Agriculture Research](https://data.mendeley.com/datasets/gfcmdbvw65/4), DOI `10.17632/gfcmdbvw65.4`.

- Licença declarada: CC BY 4.0.
- Conteúdo: 1.406 imagens de maçãs em condições naturais de pomar, com máscaras poligonais e três estágios de maturação.
- Divisão publicada: 1.041 treino, 126 validação e 239 teste.
- Arquivo local: `data/external/apple_maturity/MANIFEST.json`.
- Integridade: o manifesto registra os SHA-256 do download e do arquivo interno.

Para gerar o manifesto JSONL de pesquisa a partir das anotações VIA:

```powershell
python external_dataset_to_jsonl.py `
  --root data/external/apple_maturity/dataset/dataset-20260508 `
  --dataset-version-id apple-maturity-gfcmdbvw65-v4 `
  --output data/external/apple_maturity/apple-maturity-original.jsonl
```

O conversor preserva as regiões e rótulos em `external_annotation`, calcula o SHA-256 de cada imagem e transforma `train` em `train`; `val` e `test` entram como `evaluation`. Todas as amostras ficam marcadas como `external_unreviewed`.

Para preparar um pacote YOLO de segmentação, sem treinar ou validar o modelo:

```powershell
python external_dataset_to_yolo.py `
  --root data/external/apple_maturity/dataset/dataset-20260508 `
  --output data/external/apple_maturity/yolo
```

O pacote gerado contém `images/`, `labels/` e `dataset.yaml`, com polígonos normalizados e classes `immature apple`, `semi-mature apple` e `mature apple`. O treino e a avaliação independente continuam sendo gates separados.

O treino curto de baseline pode ser executado com `train_research_baseline.py`. Ele baixa o peso inicial somente se necessário, gera `best.pt` e `baseline_report.json`, calcula SHA-256 e marca o resultado como `candidate`. O runtime Ultralytics é AGPL-3.0; para produto fechado/comercial é necessária decisão de licenciamento ou licença Enterprise, conforme a documentação oficial do projeto.

## Limite de uso

Este material é um **bootstrap de pesquisa**, não uma autorização para liberar o produto em campo. A origem externa não representa automaticamente a propriedade do usuário, sua cultivar, câmera, iluminação, estação ou protocolo agronômico. O conjunto não substitui:

1. a definição da cultura e da variável visual do piloto;
2. anotações revisadas por especialista local;
3. um conjunto independente por propriedade/data/campanha;
4. a validação do modelo no ambiente real de implantação.

O sistema continua configurado para não gerar recomendação agronômica nem extrapolação fora da cobertura observada.

## Candidatos descartados

- MinneApple é tecnicamente relevante para detecção e contagem, mas sua licença publicada é CC BY-NC-SA 3.0, incompatível com uma decisão automática de uso comercial sem autorização adicional.
- MegaFruits informa restrição para uso não comercial e não redistribuição.

Por isso, o primeiro insumo baixado usa CC BY 4.0, mantendo a atribuição e as ressalvas do manifesto.
