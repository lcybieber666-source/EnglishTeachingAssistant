@echo off
REM 英语教学助手 - Windows 启动脚本
REM 使用 lang_env 环境运行

echo ========================================
echo 英语教学助手系统启动脚本
echo ========================================

REM 设置 Python 路径
set PYTHON=F:\conda\envs\lang_env\python.exe

REM 禁用 OneDNN 避免 PaddlePaddle 兼容问题
set FLAGS_use_mkldnn=0

REM 检查 Python 环境
%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请检查路径: %PYTHON%
    pause
    exit /b 1
)

REM 设置项目根目录
set PROJECT_DIR=%~dp0
cd /d %PROJECT_DIR%

echo.
echo [1/5] 启动 MCP 服务...
start "MCP-DocGen" cmd /c "%PYTHON% mcp_server\mcp_docgen_server.py"
start "MCP-Question" cmd /c "%PYTHON% mcp_server\mcp_question_server.py"
start "MCP-Grading" cmd /c "%PYTHON% mcp_server\mcp_grading_server.py"
start "MCP-Analysis" cmd /c "%PYTHON% mcp_server\mcp_analysis_server.py"
timeout /t 5 /nobreak >nul

echo.
echo [2/5] 启动 A2A Agent 服务...
start "A2A-DocGen" cmd /c "%PYTHON% a2a_server\docgen_server.py"
start "A2A-Question" cmd /c "%PYTHON% a2a_server\question_server.py"
start "A2A-Grading" cmd /c "%PYTHON% a2a_server\grading_server.py"
start "A2A-Analysis" cmd /c "%PYTHON% a2a_server\analysis_server.py"
timeout /t 5 /nobreak >nul

echo.
echo [3/5] 启动主应用 API 服务...
start "Main-API" cmd /c "%PYTHON% main.py"
timeout /t 2 /nobreak >nul

echo.
echo [4/5] 启动 Streamlit 前端...
start "Streamlit" cmd /c "%PYTHON% -m streamlit run app.py --server.port 8501 --server.headless true"
timeout /t 5 /nobreak >nul

echo.
echo [5/5] 自动打开浏览器...
timeout /t 3 /nobreak >nul
start http://localhost:8501

echo.
echo ========================================
echo 所有服务已启动！
echo ========================================
echo.
echo 服务端口:
echo   - Streamlit 前端:  http://localhost:8501
echo   - 主应用 API:      http://localhost:8000
echo   - A2A Agents:      5010-5013
echo   - MCP Servers:     8010-8013
echo.
echo 按任意键关闭此窗口（不会关闭服务）...
pause >nul

