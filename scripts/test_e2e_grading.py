# -*- coding: utf-8 -*-
"""
作业批改 Agent 端到端测试

前置条件: 先启动 MCP grading server (8012) 和 A2A grading server (5012)
"""
import os
import sys
import json

os.environ["FLAGS_use_mkldnn"] = "0"
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from config import Config  # 触发 NO_PROXY 环境变量设置


def main():
    print("=" * 60)
    print("  作业批改 Agent 端到端测试")
    print("=" * 60)
    
    # 配置
    image_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "homework_data", "学生作业.png"
    )
    
    if not os.path.exists(image_path):
        print(f"\n[错误] 未找到作业图片: {image_path}")
        return
    
    print(f"\n作业图片: {image_path}")
    print(f"作业ID: 1, 学生ID: 1")
    print(f"\n正在发送批改请求到 http://localhost:5012 ...")
    print("(首次调用 OCR 可能需要 30-60 秒，请耐心等待)\n")
    
    try:
        request_text = json.dumps({
            "homework_id": 1,
            "student_id": 1,
            "image_path": image_path
        }, ensure_ascii=False)
        
        # 通过 /tasks/send 端点发送任务
        import uuid
        task_id = str(uuid.uuid4())
        resp = requests.post(
            "http://localhost:5012/tasks/send",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tasks/send",
                "params": {
                    "id": task_id,
                    "message": {
                        "content": {"type": "text", "text": request_text},
                        "role": "user"
                    }
                }
            },
            timeout=300
        )
        resp.raise_for_status()
        result = resp.json()
        
        # 输出批改结果
        print("=" * 60)
        print("  批改结果")
        print("=" * 60)
        
        # 从 JSON-RPC 结果中提取文本
        task_result = result.get("result", result)
        text = ""
        for artifact in task_result.get("artifacts", []):
            for part in artifact.get("parts", []):
                if part.get("type") == "text":
                    text += part.get("text", "")
        
        if text:
            print(text)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        
        print("\n" + "=" * 60)
        print("  测试完成！可以去数据库查看结果:")
        print("  SELECT * FROM homework_submissions ORDER BY id DESC LIMIT 1;")
        print("  SELECT * FROM score_records ORDER BY id DESC LIMIT 1;")
        print("=" * 60)
        
    except requests.ConnectionError:
        print("[错误] 无法连接到批改Agent服务 (端口5012)")
        print("请先启动 MCP grading server 和 A2A grading server")
    except Exception as e:
        print(f"[错误] {e}")


if __name__ == "__main__":
    main()
