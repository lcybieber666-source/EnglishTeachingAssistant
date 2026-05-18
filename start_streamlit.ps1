# 单独启动 Streamlit 前端
# 用法: 右键 -> 用 PowerShell 运行，或 powershell -ExecutionPolicy Bypass -File start_streamlit.ps1

$PYTHON = "F:\conda\envs\lang_env\python.exe"
$PROJECT = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "启动 Streamlit 前端 (8501)..." -ForegroundColor Green
Set-Location $PROJECT
& $PYTHON -m streamlit run app.py --server.port 8501
