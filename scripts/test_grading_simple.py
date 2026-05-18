# -*- coding: utf-8 -*-
"""用 requests 直接发 A2A HTTP 请求测试批改（绕过 python_a2a 导入问题）"""
import os, json, requests

# 清除代理
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]:
    os.environ.pop(k, None)

IMAGE = "D:/python_code/EnglishTeachingAssistant/homework_data/学生作业.png"
print(f"图片存在: {os.path.exists(IMAGE)}")

payload = {
    "jsonrpc": "2.0", "id": "test-1",
    "method": "tasks/send",
    "params": {
        "id": "task-test-001",
        "message": {
            "role": "user",
            "content": {"text": json.dumps({"image_path": IMAGE, "query": "帮我批改作业"}, ensure_ascii=False)}
        }
    }
}

print("发送请求 (timeout=300s)...")
r = requests.post("http://localhost:5012/tasks/send", json=payload, timeout=300)
data = r.json()

if "result" in data:
    task = data["result"]
    state = task.get("status", {}).get("state", "?")
    print(f"状态: {state}")
    if task.get("artifacts"):
        text = task["artifacts"][0]["parts"][0]["text"]
        print(f"\n[PASS] 批改成功!\n{'='*60}\n{text[:1000]}")
    else:
        print(f"[FAIL] 无结果: {json.dumps(task.get('status'), ensure_ascii=False)}")
else:
    print(f"[FAIL] {json.dumps(data, ensure_ascii=False)[:500]}")
