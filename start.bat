@echo off
start /min "" powershell -NoLogo -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
