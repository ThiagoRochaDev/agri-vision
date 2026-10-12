# Registro de decisões

Este documento registra as decisões que encerram cada etapa do produto. Uma etapa só deve ser marcada como liberada quando houver evidência verificável no repositório, nos testes ou no protocolo de campo.

## 2026-10-11 — Base operacional

- **Decisão:** manter o produto restrito a um fluxo de captura, revisão humana e relatório por campanha.
- **Motivo:** evita transformar uma estimativa visual ainda não validada em recomendação agronômica ou extrapolação operacional.
- **Evidência:** `docs/PILOT_PROTOCOL.md`, `docs/ACCEPTANCE.md` e os testes automatizados de isolamento, qualidade, revisão, sincronização e relatório.
- **Status:** implementado em ambiente de desenvolvimento.

## 2026-10-11 — Inferência

- **Decisão:** não gerar previsão quando não existir um modelo validado para a organização, tarefa e versão solicitadas.
- **Motivo:** uma previsão simulada ou fora do domínio criaria falsa confiança no piloto.
- **Evidência:** registro de modelos, exigência de conjunto de avaliação e contrato do worker HTTP em `agri_vision/inference.py`.
- **Status:** implementado; depende de um modelo real e de sua validação independente.

## 2026-10-11 — GPS e cobertura

- **Decisão:** exibir cobertura por talhão, mas manter `extrapolation_allowed=false` até existir método agronômico validado.
- **Motivo:** pontos coletados permitem auditar a campanha, mas não autorizam inferir áreas não observadas.
- **Evidência:** endpoint de cobertura, tela de cobertura e testes de isolamento organizacional.
- **Status:** implementado.

## 2026-10-11 — Gate de produção

- **Decisão:** não declarar produção liberada nesta etapa.
- **Bloqueios externos:** ainda faltam parceiro agronômico, cultura e variável visual escolhidas, protocolo de captura, anotações de especialista, conjunto independente por propriedade/data/campanha, modelo treinado e validação no ambiente de implantação.
- **Critério de liberação:** preencher o protocolo de piloto, executar os gates N06-T01 a N06-T08 com evidências reais e executar o checklist de `docs/OPERATIONS.md`.
- **Status:** aguardando evidências de campo; o software permanece pronto para receber esses artefatos sem mascarar a ausência deles.

## 2026-10-11 — Recuperação

- **Decisão:** todo backup inclui manifesto SHA-256 e toda restauração valida o manifesto antes de copiar os arquivos.
- **Motivo:** um snapshot corrompido ou adulterado não pode substituir a base operacional silenciosamente.
- **Evidência:** `backup.py`, `restore.py` e `tests/test_store.py:test_backup_contains_consistent_database_snapshot_and_media`; a gravação também é atômica para não deixar um ZIP parcial no destino.
- **Status:** implementado e validado.

## 2026-10-11 — Gate de piloto

- **Decisão:** exigir uma configuração preenchida e validada antes de iniciar o piloto de campo.
- **Motivo:** cultura, tarefa, referência humana, baseline e grupo independente não podem ficar implícitos ou ser substituídos por placeholders.
- **Evidência:** `pilot_check.py`, `docs/PILOT_CONFIG.example.json` e `tests/test_pilot_check.py`.
- **Status:** implementado; o arquivo de exemplo é intencionalmente rejeitado até ser preenchido.

## 2026-10-12 — Insumo público para bootstrap

- **Decisão:** usar um dataset público de maçãs com licença CC BY 4.0 apenas para bootstrap de pesquisa e preparação do pipeline.
- **Motivo:** permite exercitar a conversão de anotações e o worker sem inventar dados de campo do usuário.
- **Evidência:** `docs/EXTERNAL_DATASETS.md` e `data/external/apple_maturity/MANIFEST.json`, com DOI, URL, licença e SHA-256.
- **Limite:** o insumo externo não libera produção, recomendação agronômica ou extrapolação; ainda é obrigatório um conjunto independente local.
- **Status:** baixado e auditado; bloqueado para uso produtivo até validação agronômica e avaliação independente.

### Evidência técnica atualizada

- `python -m compileall -q agri_vision run.py backup.py restore.py retention.py production_check.py export_dataset.py`: concluído sem erros.
- `python -m unittest discover -s tests -q`: 44 testes executados, 44 aprovados.
- `pilot_check.py` foi validado no caminho de sucesso e rejeita o arquivo de exemplo enquanto houver placeholders.
- `validate_dataset.py` verifica splits, mídias, hashes e amostras rejeitadas antes do treinamento; cobertura em `tests/test_validate_dataset.py`.
- `external_dataset_to_jsonl.py` converteu 1.406 imagens VIA do insumo externo e `validate_dataset.py` retornou `OK dataset`; o resultado permanece marcado como `external_unreviewed`.
- `external_dataset_to_yolo.py` prepara segmentação YOLO com polígonos normalizados; a geração do pacote não equivale a treino nem validação do modelo.
- `train_research_baseline.py` prepara e registra um baseline candidato com SHA-256; a licença do runtime/pesos e a avaliação local continuam gates antes de qualquer promoção.
- O smoke test operacional de `health`, `ready` e `metrics` já foi executado anteriormente com sucesso; a prontidão continua condicionada à disponibilidade do diretório persistente de mídia.
- `production_check.py` agora falha com `api_key_missing` quando executado sem chave; o bypass exige a opção explícita `--allow-unauthenticated` e é reservado ao desenvolvimento local.
- Smoke test local em 2026-10-11: servidor iniciado com `AGRI_VISION_API_KEY`, `production_check.py --api-key` retornou `OK health ready metrics`, e o processo foi encerrado ao final do teste.

## Como atualizar

Ao fechar uma etapa, adicionar uma entrada com data, decisão, motivo, evidência e status. Não marcar como aprovado um item cuja evidência ainda seja apenas teste sintético.
