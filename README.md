# 🔊 Volume por App

Controla o volume de cada programa separadamente (como o mixer do Windows, só que melhor):
slider e mudo por app, medidor ao vivo, volume geral, **perfis** ("Jogo", "Reunião", "Noite")
e ícone na bandeja com slider rápido. Offline.

## Usar
```
pip install -r requirements.txt
python volume_apps.pyw
```
- Perfis ficam em `%LOCALAPPDATA%\VolumeApps\perfis.json`; são aplicados casando pelo nome do processo.
- Fechar a janela manda pra bandeja; clique no ícone para o slider do volume geral, "Sair" no menu.
- Só aparecem programas que já abriram uma sessão de áudio.

## Testes
`python test_va.py` (usa sessões falsas; o teste real só lista, não muda nada).

Licença MIT.
