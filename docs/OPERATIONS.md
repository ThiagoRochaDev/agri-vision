# Operação de produção

## Antes do piloto

- Definir uma cultura, uma ocorrência visual e um agrônomo responsável.
- Preencher `docs/PILOT_CONFIG.example.json` em uma cópia real e executar `python pilot_check.py caminho\para\pilot-config.json`; o gate rejeita placeholders, ausência de grupos independentes e qualquer tentativa de habilitar extrapolação.
- Registrar protocolo de coleta, consentimento, retenção e propriedade dos dados.
- Criar uma versão de dataset com separação por propriedade, tempo ou campanha.
- Exportar somente depois de informar `evaluation_groups`; amostras rejeitadas não podem entrar no treino ou avaliação.
- Executar `python validate_dataset.py` no JSONL exportado antes de entregar o dataset ao treinamento; falhas de hash, mídia ausente, amostra rejeitada ou split vazio interrompem o fluxo.
- Deixar `AGRI_VISION_INFERENCE_URL` vazio até existir um modelo validado em conjunto independente; quando configurado, o serviço usa o adaptador HTTP e só aceita resposta com predição numérica, confiança entre 0 e 1 e versão identificada.
- Registrar a versão com dataset e grupos de avaliação completos antes de usar o worker; sem o estado `validated` compatível com a tarefa da campanha, a resposta permanece `model_not_validated` e nenhuma previsão é gravada. O worker também precisa devolver exatamente a versão configurada; divergências viram `invalid_model_response`.
- Registrar a versão do modelo e o SHA-256 do artefato; somente o estado `validated` pode ser promovido para um worker real.
- Configurar `AGRI_VISION_API_KEY` em um secret store; nunca colocar a chave em código ou `.env` versionado.
- Aceitar somente JPEG, PNG ou WebP; o servidor valida a assinatura do arquivo e o hash antes de persistir a mídia.
- A interface mantém amostras não enviadas em IndexedDB até a sincronização; orientar o operador sobre retenção local e limpar a fila após confirmar o recebimento.

## Execução

1. Montar `/data` em armazenamento persistente com permissão de escrita para o usuário não-root `agri` do container.
2. Configurar `AGRI_VISION_DATABASE=/data/agri_vision.sqlite3` e `AGRI_VISION_MEDIA_DIR=/data/media`.
3. Configurar `AGRI_VISION_API_KEY`; o processo recusa bind não-loopback sem chave, inclusive quando iniciado com `--host 0.0.0.0`.
4. Permitir que a inicialização aplique migrações SQLite versionadas; fazer backup antes de atualizar uma base existente.
5. Colocar TLS, autenticação de identidade e controle de rede em um proxy ou gateway.
6. Monitorar `/health`, `/ready` e `/metrics`.
7. Rotacionar logs sem incluir imagens, chaves ou conteúdo de `capture_metadata` além do necessário.
8. Correlacionar incidentes pelo header `X-Request-ID`, presente nas respostas e nos logs de acesso.
9. Usar `docker-compose.yml` apenas com `AGRI_VISION_API_KEY` fornecida pelo secret store, nunca com a chave do exemplo.
10. Executar `production_check.py --api-key "$AGRI_VISION_API_KEY"` após iniciar uma nova versão e antes de liberar tráfego; o check falha se a chave não for fornecida e confirma bloqueio sem chave e acesso autorizado. Use `--allow-unauthenticated` somente para desenvolvimento local.

## Backup e recuperação

Criar backups periódicos com `backup.py`, armazená-los fora da máquina e testar `restore.py` em diretório separado. O backup é escrito em arquivo temporário e só substitui o destino após o ZIP ser fechado; ele inclui `MANIFEST.sha256.json`, e a restauração recusa arquivos ausentes ou alterados. Uma restauração só deve substituir o ambiente após validação do snapshot e decisão registrada.

Executar `retention.py` primeiro sem `--execute` para revisar a quantidade. A exclusão remove amostras, revisões e mídia expiradas, registra o evento de purge e exige backup prévio.

## Critérios de liberação

- Testes de isolamento entre organizações aprovados.
- Testes de upload duplicado, hash, GPS ausente e cultura fora do domínio aprovados.
- Campanhas congeladas não aceitam novas amostras; retries idempotentes devem continuar aprovados.
- Backup e restauração comprovados.
- Baseline agronômico e métrica definidos pelo parceiro.
- Modelo avaliado em propriedade/data não usados no treino.
- Avaliação por campanha mostra cobertura, MAE e erro relativo mediano; não usar uma métrica sem referência humana independente.
- Manual de revisão humana, limites e reversão aprovado.
- CI verde em uma revisão limpa antes de publicar uma imagem.
- O CI também precisa concluir o job `container`, que constrói o `Dockerfile`; se o Docker local estiver indisponível, essa verificação deve ser feita no runner do CI.

O serviço não diagnostica doença, recomenda defensivo, promete produtividade ou extrapola uma amostra para toda a lavoura sem método validado.
