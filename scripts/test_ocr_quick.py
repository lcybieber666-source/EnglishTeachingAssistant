# -*- coding: utf-8 -*-
"""测试 MCP OCR - 强制绕过代理"""
import asyncio, json, os, sys

# 强制清除所有代理设置
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]:
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "localhost,127.0.0.1,0.0.0.0"
os.environ["no_proxy"] = "localhost,127.0.0.1,0.0.0.0"

sys.path.append("d:/python_code/EnglishTeachingAssistant")
from mcp import ClientSession
from mcp.client.sse import sse_client

async def main():
    image = "d:/python_code/EnglishTeachingAssistant/uploads/homework/学生作业.png"
    print(f"图片存在: {os.path.exists(image)}")
    print(f"代理环境变量: HTTP_PROXY={os.environ.get('HTTP_PROXY','无')}, HTTPS_PROXY={os.environ.get('HTTPS_PROXY','无')}")
    print(f"NO_PROXY={os.environ.get('NO_PROXY','无')}")
    
    mcp_result = None
    try:
        async with sse_client("http://localhost:8012/sse", timeout=120) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                print("MCP 已连接，开始 OCR ...")
                res = await s.call_tool("ocr_recognize", {"image_path": image})
                mcp_result = res.content[0].text if res.content else ""
                print(f"OCR 完成: {mcp_result[:200]}")
    except BaseException as e:
        if mcp_result is not None:
            print(f"[WARN] SSE关闭异常（已忽略），结果已拿到")
            print(f"结果: {mcp_result[:200]}")
        else:
            print(f"[FAIL] {type(e).__name__}: {e}")
            if hasattr(e, "exceptions"):
                for i, sub in enumerate(e.exceptions):
                    print(f"  子异常[{i}]: {type(sub).__name__}: {sub}")

asyncio.run(main())
