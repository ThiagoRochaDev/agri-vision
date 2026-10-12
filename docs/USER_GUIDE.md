# Manual do operador

Este manual descreve o uso do MVP com dados fictícios ou autorizados. O responsável agronômico deve aprovar `docs/PILOT_PROTOCOL.md` antes de qualquer coleta real.

## Preparar a sessão

1. Abra `/` no mesmo endereço do serviço.
2. Informe a chave API somente no campo da sessão; a interface não a salva.
3. Informe a organização e o identificador do operador fornecidos pelo administrador.

## Criar uma campanha

1. Cadastre a fazenda e o talhão, informando uma única cultura.
2. Crie a campanha com a pergunta mensurável e o período de captura.
3. Use **Iniciar coleta** antes de enviar imagens.
4. Selecione uma imagem JPEG, PNG ou WebP de até 6 MiB e informe o GPS quando disponível.
5. Observe o resultado de qualidade: `accepted`, `rejected`, `out_of_domain` ou `pending_location`.

## Trabalhar sem conexão

- Se o envio falhar por falta de conexão, a amostra fica na fila local do navegador.
- A fila usa IndexedDB e não armazena a chave API.
- Use **Sincronizar pendências** ou aguarde o retorno da conexão.
- Confirme a quantidade pendente antes de limpar os dados do navegador; o servidor reconcilia repetições por `client_event_id`.

## Revisar e acompanhar

1. Consulte as observações da campanha.
2. Execute inferência somente depois de um modelo `validated`; sem ele, o estado será `pending_model`.
3. Compare a predição com a referência humana e registre nota e responsável.
4. Use **Enviar para revisão** para congelar novas amostras.
5. Consulte o relatório e a cobertura GPS do talhão. Amostras sem localização permanecem pendentes.

## Estados e erros comuns

- `client_event_conflict` (`409`): o identificador do dispositivo foi reutilizado com conteúdo diferente; não sobrescreva o evento original.
- `campaign_not_collecting` (`409`): a campanha está em revisão, pausa ou fechamento; retries idempotentes continuam permitidos.
- `model_not_validated`: versão/tarefa não foram aprovadas no registry.
- `invalid_model_response`: o worker respondeu com contrato ou versão divergente.

## Limites

O sistema mede somente a ocorrência visual definida no protocolo. Não diagnostica doenças, recomenda defensivos, promete produtividade, opera máquinas nem extrapola uma amostra para toda a lavoura. Toda decisão agronômica permanece com o responsável humano.
