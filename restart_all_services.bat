@echo off
echo ========================================
echo 英语教学助手 - 服务重启脚本
echo ========================================

set PYTHON=F:\conda\envs\lang_env\python.exe
set PROJECT_DIR=d:\python_code\EnglishTeachingAssistant
cd /d %PROJECT_DIR%

echo.
echo [1/4] 正在停止所有 Python 服务...
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul

echo.
echo [2/4] 启动 MCP 服务...
start "MCP-DocGen" cmd /c "%PYTHON% mcp_server\mcp_docgen_server.py"
start "MCP-Question" cmd /c "%PYTHON% mcp_server\mcp_question_server.py"
start "MCP-Grading" cmd /c "%PYTHON% mcp_server\mcp_grading_server.py"
start "MCP-Analysis" cmd /c "%PYTHON% mcp_server\mcp_analysis_server.py"
timeout /t 5 /nobreak >nul

echo.
echo [3/4] 启动 A2A Agent 服务...
start "A2A-DocGen" cmd /c "%PYTHON% a2a_server\docgen_server.py"
start "A2A-Question" cmd /c "%PYTHON% a2a_server\question_server.py"
start "A2A-Grading" cmd /c "%PYTHON% a2a_server\grading_server.py"
start "A2A-Analysis" cmd /c "%PYTHON% a2a_server\analysis_server.py"
timeout /t 5 /nobreak >nul

echo.
echo [4/4] 启动主应用 API...
start "Main-API" cmd /c "%PYTHON% main.py"
timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo 所有后端服务已重启！
echo ========================================
echo.
echo 服务端口:
echo   - 主应用 API:      http://localhost:8000
echo   - A2A Agents:      5010-5013
echo   - MCP Servers:     8010-8013
echo.
echo Streamlit 前端请单独运行: start_all.bat
echo.
pause
