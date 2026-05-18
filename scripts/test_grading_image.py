# -*- coding: utf-8 -*-
"""端到端测试: 通过 A2A 发送图片批改请求"""
import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config  # 触发代理清除
import requests, json

url = "http://localhost:5012/tasks/send"
payload = {
    "jsonrpc": "2.0",
    "method": "tasks/send",
    "params": {
        "message": {
            "role": "user",
            "content": {
                "type": "text",
                "text": json.dumps({
                    "image_path": "d:/python_code/EnglishTeachingAssistant/uploads/homework/学生作业.png",
                    "query": "帮我批改这份作业"
                }, ensure_ascii=False)
            }
        }
    },
    "id": "test-grading-1"
}

print("发送批改请求到 A2A ...")
try:
    r = requests.post(url, json=payload, timeout=300)
    result = r.json()
    
    if "result" in result:
        task = result["result"]
        state = task.get("status", {}).get("state", "unknown")
        print(f"状态: {state}")
        
        if task.get("artifacts"):
            text = task["artifacts"][0]["parts"][0]["text"]
            print(f"\n批改结果:\n{text[:800]}")
        elif state == "failed":
            msg = task.get("status", {}).get("message", {})
            print(f"失败信息: {msg}")
    else:
        print(f"响应: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}")
except Exception as e:
    print(f"请求失败: {e}")
