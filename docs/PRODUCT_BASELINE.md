# Baseline de produtos

O projeto possui um pipeline reprodutível para treinar um detector genérico de
produtos em imagens de prateleira:

```powershell
python train_product_baseline.py --device 0 --epochs 50 --batch -1
```

O script converte as anotações CSV do SKU-110K para YOLO, treina na GPU `0` e
grava `product_baseline_report.json` com hashes, configuração, contagens e
métricas. Dados, pesos e execuções permanecem fora do Git por serem artefatos
grandes.

## Execução validada localmente

Em 12/10/2026, o pipeline foi executado na RTX 4090 local com YOLO11n,
640 px, batch 16 e 5 epochs. O conjunto usado teve 8.219 imagens de treino,
588 de validação e 2.936 de teste. Na validação, o resultado foi:

- Precisão: `0,867`
- Recall: `0,801`
- mAP50: `0,872`
- mAP50-95: `0,509`

O artefato candidato ficou em
`data/external/sku110k/runs/product_baseline/weights/best.pt`, com SHA-256
`5553078008c84cec6d6c085f7e52e79562247a70926c8384cedcedcbf4fd0e14`. O
arquivo original baixado foi verificado com SHA-256
`fd40deee21044af97804d6583e62d43f7b317c46c70153a5fb427bd26438c226`.

## Limite de licença

O SKU-110K é um benchmark de detecção genérica de objetos em prateleiras, com
uma classe `product`, e a documentação pública o identifica como
`Research-Only`. Portanto, este baseline valida o encanamento e mede desempenho
técnico, mas não pode ser promovido para produto comercial sem autorização ou
licença compatível. Para produção, substitua-o por imagens do cliente ou por um
dataset com licença comercial explícita e registre a proveniência em
`POST /dataset-versions`.

## Limites técnicos

- Localiza produtos individuais em prateleiras densas.
- Não identifica SKU, marca ou produto específico.
- Não comprova generalização para embalagens brasileiras ou para a propriedade.
- Não deve ser registrado como `validated` sem avaliação independente e revisão
  humana, conforme `docs/ACCEPTANCE.md`.
