# Distribuição para Windows

## Pré-requisitos de build

- Python 3 instalado com o comando `py` disponível.
- Inno Setup 6 com o comando `iscc` disponível para gerar o instalador.

## Gerar o aplicativo

```powershell
.\build.ps1
```

O script cria um ambiente isolado, instala versões fixas das dependências, executa os testes, gera o ícone e produz `dist\PIng\PIng.exe` com todos os recursos necessários.

## Gerar o instalador

```powershell
iscc installer.iss
```

O instalador é salvo em `installer-output`. Os dados do usuário ficam em `%LOCALAPPDATA%\PIng` e não são removidos em atualizações ou desinstalações. O arquivo `attendance.db` do repositório não faz parte do pacote.

O executável solicita elevação do Windows porque a criação do hotspot usa `netsh`. O servidor local e a interface continuam funcionando por Wi-Fi ou cabo quando o hotspot não é compatível.

## Depuração local

Os logs ficam em `%LOCALAPPDATA%\PIng\logs\ping.log`, com até cinco arquivos antigos de 2 MB cada. Para aumentar o detalhamento e abrir as ferramentas de desenvolvimento do WebView ao executar pelo Git Bash:

```bash
export PING_LOG_LEVEL=DEBUG
export PING_WEBVIEW_DEBUG=1
./.venv/Scripts/python.exe launcher.py
```

Para acompanhar o arquivo em tempo real no Git Bash:

```bash
tail -f "$LOCALAPPDATA/PIng/logs/ping.log"
```
