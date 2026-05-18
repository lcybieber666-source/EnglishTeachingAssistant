# -*- coding: utf-8 -*-
"""
出题 Agent 端到端测试

前置条件: 先启动 MCP question server (8011) 和 A2A question server (5011)
"""
import os
import sys
import json
import uuid

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 强制 Windows 环境下的标准输出使用 utf-8
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests
from config import Config

conf = Config()

A2A_URL = f"http://localhost:{conf.question_agent_port}"


def send_task(query: str, timeout: int = 300) -> dict:
    """发送任务到 A2A 出题服务"""
    task_id = str(uuid.uuid4())
    resp = requests.post(
        f"{A2A_URL}/tasks/send",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tasks/send",
            "params": {
                "id": task_id,
                "message": {
                    "content": {"type": "text", "text": query},
                    "role": "user"
                }
            }
        },
        timeout=timeout
    )
    resp.raise_for_status()
    return resp.json()


def extract_text(result: dict) -> str:
    """从 JSON-RPC 结果中提取文本"""
    task_result = result.get("result", result)
    text = ""
    for artifact in task_result.get("artifacts", []):
        for part in artifact.get("parts", []):
            if part.get("type") == "text":
                text += part.get("text", "")
    return text


def test_generate_grammar_questions():
    """测试 1: 生成语法练习题"""
    print("\n" + "=" * 60)
    print("测试 1: 生成语法练习题")
    print("=" * 60)

    query = "请出5道关于定语从句的选择题，难度中等"
    print(f"请求: {query}")
    print("正在等待出题 Agent 处理 (可能需要 30-60 秒)...\n")

    try:
        result = send_task(query)
        text = extract_text(result)

        if text:
            print("✅ 出题成功！")
            print("-" * 40)
            print(text[:500] + ("..." if len(text) > 500 else ""))
            print("-" * 40)
            return True
        else:
            print("❌ 返回结果为空")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return False

    except requests.ConnectionError:
        print(f"❌ 无法连接到出题 Agent (端口 {conf.question_agent_port})")
        print("   请先启动 MCP question server 和 A2A question server")
        return False
    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


def test_generate_mixed_questions():
    """测试 2: 生成综合练习"""
    print("\n" + "=" * 60)
    print("测试 2: 生成综合练习")
    print("=" * 60)

    query = "请出一套包含选择题和填空题的英语练习，涵盖时态和被动语态，每种题型3道"
    print(f"请求: {query}")
    print("正在等待出题 Agent 处理...\n")

    try:
        result = send_task(query)
        text = extract_text(result)

        if text:
            print("✅ 出题成功！")
            print("-" * 40)
            print(text[:500] + ("..." if len(text) > 500 else ""))
            print("-" * 40)
            return True
        else:
            print("❌ 返回结果为空")
            return False

    except requests.ConnectionError:
        print(f"❌ 无法连接到出题 Agent")
        return False
    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


def main():
    print("=" * 60)
    print("  出题 Agent 端到端测试 (A2A)")
    print("=" * 60)
    print(f"\nA2A 服务地址: {A2A_URL}")
    print(f"MCP 服务端口: {conf.mcp_question_port}\n")

    results = {}

    results['grammar_questions'] = test_generate_grammar_questions()
    results['mixed_questions'] = test_generate_mixed_questions()

    # 汇总
    print("\n" + "=" * 60)
    print("测试汇总:")
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {name}: {status}")

    passed_count = sum(results.values())
    total_count = len(results)
    print(f"\n总计: {passed_count}/{total_count} 通过")
    print("=" * 60)


if __name__ == "__main__":
    main()
