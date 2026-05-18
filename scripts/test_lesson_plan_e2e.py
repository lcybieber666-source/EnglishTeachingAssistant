# -*- coding: utf-8 -*-
"""
教案生成端到端测试

测试完整流程:
1. 调用 MCP DocGen Server
2. RAG 检索课本内容
3. LLM 生成教案
4. 导出 Word 文档
"""
import os
import sys
import asyncio
import json
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 强制 Windows 环境下的标准输出使用 utf-8，防止 emoji 报错
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from config import Config

conf = Config()


async def test_mcp_search_textbook():
    """测试 MCP 课本检索"""
    print("\n" + "=" * 60)
    print("测试 1: MCP 课本检索（RAG）")
    print("=" * 60)
    
    try:
        from mcp import ClientSession
        from mcp.client.sse import sse_client
        
        mcp_url = f"http://localhost:{conf.mcp_docgen_port}/sse"
        
        try:
            async with sse_client(mcp_url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    
                    # 调用检索工具
                    result = await session.call_tool("search_textbook", {
                        "query": "七年级 Unit 1 友谊",
                        "limit": 3
                    })
                    
                    content = result.content[0].text if result.content else ""
                    data = json.loads(content)
                    
                    print(f"✅ 检索成功")
                    print(f"   查询: {data.get('query')}")
                    print(f"   结果数: {data.get('total')}")
                    
                    
                    if data.get('sections'):
                        print(f"   第一个结果预览: {data['sections'][0].get('content', '')[:100]}...")
                    
                    return True
                    
        except BaseException as e:
            # 兼容 MCP SSE 结束时的 ReadError
            err_str = str(e)
            if "ReadError" in err_str or "post_writer" in err_str or "TaskGroup" in err_str:
                if 'data' in locals() and data:
                    return True
            raise e
                    
    except Exception as e:
        print(f"❌ 检索失败: {e}")
        print("   请确保 MCP DocGen Server 已启动")
        return False


async def test_mcp_generate_lesson_plan():
    """测试 MCP 生成教案"""
    print("\n" + "=" * 60)
    print("测试 2: MCP 生成教案（LLM + Word）")
    print("=" * 60)
    
    try:
        from mcp import ClientSession
        from mcp.client.sse import sse_client
        
        mcp_url = f"http://localhost:{conf.mcp_docgen_port}/sse"
        
        try:
            async with sse_client(mcp_url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    
                    # 调用生成工具
                    result = await session.call_tool("generate_lesson_plan", {
                        "grade": "七年级",
                        "unit": "Unit 1",
                        "topic": "Making Friends",
                        "textbook_content": "Unit 1 is about making friends and self-introduction.",
                        "requirements": "生成一份完整的教案，包含教学目标、重难点、教学过程等"
                    })
                    
                    content = result.content[0].text if result.content else ""
                    data = json.loads(content)
                    
                    if data.get("status") == "success":
                        print(f"✅ 教案生成成功")
                        print(f"   标题: {data.get('lesson_plan', {}).get('title')}")
                        print(f"   Word 文件: {data.get('word_path')}")
                        
                        # 验证文件是否存在
                        word_path = data.get('word_path', '')
                        if os.path.exists(word_path):
                            print(f"   ✅ Word 文件已创建，大小: {os.path.getsize(word_path)} 字节")
                        else:
                            print(f"   ⚠️ Word 文件路径不存在")
                        
                        return True
                    else:
                        print(f"❌ 生成失败: {data.get('error')}")
                        return False
                        
        except BaseException as e:
            # 兼容 MCP SSE 结束时的 ReadError
            err_str = str(e)
            if "ReadError" in err_str or "post_writer" in err_str or "TaskGroup" in err_str:
                if 'data' in locals() and data and data.get("status") == "success":
                    return True
            raise e
                
    except Exception as e:
        print(f"❌ 生成失败: {e}")
        print("   请确保 MCP DocGen Server 已启动")
        return False


async def test_word_generator_standalone():
    """独立测试 Word 生成器"""
    print("\n" + "=" * 60)
    print("测试 3: Word 生成器（独立测试）")
    print("=" * 60)
    
    try:
        from utils.word_generator import generate_lesson_plan
        
        test_data = {
            "title": "Unit 1 Making Friends",
            "grade": "七年级",
            "unit": "Unit 1",
            "topic": "Making Friends",
            "duration": "1课时",
            "objectives": [
                "能够听懂并使用日常交际用语进行自我介绍",
                "能够正确使用 Nice to meet you 等问候语",
                "了解西方国家的见面礼仪"
            ],
            "key_points": "掌握自我介绍的基本表达",
            "difficult_points": "在真实情境中灵活运用所学句型",
            "teaching_aids": "多媒体课件、录音机、图片",
            "procedures": [
                {"step": "Step 1: Warm-up (5分钟)", "content": "播放英语歌曲，营造轻松的课堂氛围。"},
                {"step": "Step 2: Presentation (15分钟)", "content": "教师展示图片，引入新词汇和句型。"},
                {"step": "Step 3: Practice (15分钟)", "content": "学生两人一组进行对话练习。"},
                {"step": "Step 4: Production (8分钟)", "content": "请学生上台表演对话。"},
                {"step": "Step 5: Summary (2分钟)", "content": "总结本节课所学内容。"}
            ],
            "homework": "1. 抄写本课生词5遍\n2. 完成课后练习",
            "reflection": ""
        }
        
        output_path = generate_lesson_plan(test_data)
        
        if os.path.exists(output_path):
            print(f"✅ Word 生成成功")
            print(f"   文件路径: {output_path}")
            print(f"   文件大小: {os.path.getsize(output_path)} 字节")
            return True
        else:
            print(f"❌ 文件未创建")
            return False
            
    except Exception as e:
        print(f"❌ Word 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_a2a_generate_lesson_plan():
    """测试 A2A 层面的端到端生成（模拟前端请求）"""
    print("\n" + "=" * 60)
    print("测试 4: A2A 生成教案（端到端）")
    print("=" * 60)
    
    import requests
    import uuid
    
    try:
        query = "请帮我生成一份七年级 Unit 1 的教案，主题是 Making Friends，要求包含详细的教学过程。"
        print(f"发送请求: {query}")
        print("正在等待 DocGen Agent 处理 (这可能需要 30-60 秒)...")
        
        task_id = str(uuid.uuid4())
        resp = requests.post(
            f"http://localhost:{conf.docgen_agent_port}/tasks/send",
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
            timeout=300
        )
        resp.raise_for_status()
        result = resp.json()
        
        # 从 JSON-RPC 结果中提取文本
        task_result = result.get("result", result)
        text = ""
        for artifact in task_result.get("artifacts", []):
            for part in artifact.get("parts", []):
                if part.get("type") == "text":
                    text += part.get("text", "")
        
        if text:
            print(f"✅ A2A 请求成功！")
            print("=" * 60)
            print(text)
            print("=" * 60)
            return True
        else:
            print(f"❌ 解析结果失败: 收到空响应或格式错误")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return False
            
    except Exception as e:
        print(f"❌ A2A 请求失败: {e}")
        print(f"   请确保 A2A DocGen Server ({conf.docgen_agent_port}) 已启动")
        return False


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("教案生成功能端到端测试")
    print("=" * 60)
    
    results = {}
    
    # 测试 1: Word 生成器（独立，无需服务）
    results['word_generator'] = await test_word_generator_standalone()
    
    # 测试 2: MCP 课本检索（需要 MCP 服务 + Milvus）
    print("\n⚠️ 以下测试需要启动 MCP DocGen Server")
    print("   运行: python mcp_server/mcp_docgen_server.py")
    
    try:
        results['mcp_search'] = await test_mcp_search_textbook()
    except:
        results['mcp_search'] = False
    
    # 测试 3: MCP 生成教案（需要 MCP 服务 + LLM）
    try:
        results['mcp_generate'] = await test_mcp_generate_lesson_plan()
    except:
        results['mcp_generate'] = False
        
    # 测试 4: A2A 端到端测试（需要 A2A 服务）
    print("\n⚠️ 以下测试需要启动 A2A DocGen Server")
    print("   运行: python -m a2a_server.docgen_server")
    try:
        results['a2a_generate'] = await test_a2a_generate_lesson_plan()
    except:
        results['a2a_generate'] = False
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败/跳过"
        print(f"  {name}: {status}")
    
    passed_count = sum(results.values())
    total_count = len(results)
    print(f"\n总计: {passed_count}/{total_count} 通过")


if __name__ == "__main__":
    asyncio.run(main())
