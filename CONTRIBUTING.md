# Contribuindo

1. Explique o problema, o comportamento esperado e o limite agronômico afetado.
2. Não inclua credenciais, imagens reais, dados de propriedades ou respostas privadas.
3. Mantenha mudanças pequenas e adicione testes para alterações de API, persistência, segurança ou conversão de dataset.
4. Diferencie claramente funcionalidades implementadas, experimentais e planejadas.
5. Execute a suíte de testes e a compilação antes de abrir um pull request.

```powershell
python -m unittest discover -s tests -q
python -m compileall -q agri_vision run.py backup.py restore.py retention.py production_check.py export_dataset.py pilot_check.py validate_dataset.py external_dataset_to_jsonl.py external_dataset_to_yolo.py train_research_baseline.py
```

Contribuições não devem promover um modelo para `validated` sem conjunto independente, revisão humana e decisão agronômica documentada.
