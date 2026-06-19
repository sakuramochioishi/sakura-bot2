@echo off
:loop
echo Botを起動します...
:: 仮想環境(venv)のPythonを使ってmain.pyを実行する設定
call venv\Scripts\activate
python main.py
echo Botが停止しました。3秒後に自動再起動します...
timeout /t 3
goto loop