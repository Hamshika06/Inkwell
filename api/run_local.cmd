@echo off
rem Double-click or run: api\run_local.cmd  (add -SvmOnly to skip torch)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_local.ps1" %*
