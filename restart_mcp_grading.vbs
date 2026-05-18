' 静默重启 MCP-Grading 服务
Set WshShell = CreateObject("WScript.Shell")
' 设置环境变量
WshShell.Environment("PROCESS")("FLAGS_use_mkldnn") = "0"
WshShell.Environment("PROCESS")("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION") = "python"
' 启动服务
WshShell.Run "cmd /c cd /d d:\python_code\EnglishTeachingAssistant && F:\conda\envs\lang_env\python.exe mcp_server\mcp_grading_server.py", 0, False
Set WshShell = Nothing
