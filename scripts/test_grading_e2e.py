# -*- coding: utf-8 -*-
"""
完整端到端测试：模拟前端 app.py 的完整批改流程
1. 清除代理（和 config.py 一样）
2. 用 A2AClient(timeout=300) 发送批改请求
3. 验证 OCR + LLM 返回结果
"""
import os, sys, json

# 清除代理（和 config.py 一致）
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]:
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "localhost,127.0.0.1,0.0.0.0"
os.environ["no_proxy"] = "localhost,127.0.0.1,0.0.0.0"

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_a2a import A2AClient, Message, TextContent, MessageRole, Task
import asyncio, uuid

IMAGE = "D:/python_code/EnglishTeachingAssistant/homework_data/学生作业.png"

async def test_grading():
    print(f"=" * 60)
    print(f"  端到端批改测试")
    print(f"=" * 60)
    print(f"图片: {IMAGE}")
    print(f"图片存在: {os.path.exists(IMAGE)}")
    
    # 模拟 app.py 的行为：创建 A2AClient + 发送 JSON 请求
    client = A2AClient("http://localhost:5012", timeout=300)
    
    # 构建和 app.py 一样的 JSON 请求
    grading_request = json.dumps({
        "image_path": IMAGE,
        "query": "帮我批改作业"
    }, ensure_ascii=False)
    
    message = Message(
        content=TextContent(text=grading_request),
        role=MessageRole.USER
    )
    task = Task(id=f"task-{uuid.uuid4()}", message=message.to_dict())
    
    print(f"\n发送请求到 A2A 批改服务 (timeout=300s)...")
    print(f"请求内容: {grading_request}")
    
    try:
        response = await client.send_task_async(task)
        
        if response.status.state == 'completed':
            result = response.artifacts[0]['parts'][0]['text']
            print(f"\n[PASS] 批改成功!")
            print(f"\n{'='*60}")
            print(f"批改结果 (前1000字):")
            print(f"{'='*60}")
            print(result[:1000])
            return True
        else:
            err = response.status.message
            print(f"\n[FAIL] 状态: {response.status.state}")
            print(f"错误: {err}")
            return False
    except Exception as e:
        print(f"\n[FAIL] 异常: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_grading())
    print(f"\n{'='*60}")
    print(f"最终结果: {'✅ 通过' if result else '❌ 失败'}")
