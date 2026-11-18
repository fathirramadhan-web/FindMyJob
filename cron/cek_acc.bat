@echo off
REM JobBot: cek Google Sheet, tarik editan ACC, notifikasi Windows bila ada yang di-ACC
cd /d C:\Users\fathi\jobbot
"C:\Users\fathi\AppData\Local\hermes\installs\7a45bc3a55e1c6b9\environments\26ce6ee9888f4a5c85911b930b8eb6ee\venv\Scripts\python.exe" main.py tarik >> cek_acc.log 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0notify_acc.ps1" >> cek_acc.log 2>&1
