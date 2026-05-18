# -*- coding: utf-8 -*-
"""
题库检索 MCP Server

端口: 8011
工具: 题库检索、知识点查询、作业保存
"""
import os
import sys
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import Response

from config import Config
from create_logger import logger

conf = Config()

server = Server("mcp-question")


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="search_questions",
            description="从MySQL题库中检索题目，支持按知识点、题型、难度筛选",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词"},
                    "weak_points": {"type": "array", "items": {"type": "string"}, "description": "薄弱知识点名称列表"},
                    "question_type": {"type": "string", "description": "题型: choice/fill/short_answer/essay/reading"},
                    "difficulty": {"type": "integer", "description": "难度等级1-5"},
                    "limit": {"type": "integer", "description": "返回数量", "default": 10}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_knowledge_points",
            description="查询所有知识点分类列表",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "分类: grammar/vocabulary/reading/writing，为空则返回全部"}
                }
            }
        ),
        Tool(
            name="save_homework",
            description="将组卷结果保存到MySQL数据库",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "作业标题"},
                    "question_ids": {"type": "array", "items": {"type": "integer"}, "description": "题目ID列表"},
                    "target_grade": {"type": "string", "description": "目标年级"},
                    "total_score": {"type": "integer", "description": "总分", "default": 100}
                },
                "required": ["title", "question_ids"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    logger.info(f"[MCP-Question] 调用工具: {name}, 参数: {arguments}")
    
    if name == "search_questions":
        return await handle_search_questions(arguments)
    elif name == "get_knowledge_points":
        return await handle_get_knowledge_points(arguments)
    elif name == "save_homework":
        return await handle_save_homework(arguments)
    else:
        return [TextContent(type="text", text=f"未知工具: {name}")]


async def handle_search_questions(arguments: dict):
    """从 MySQL 题库检索题目"""
    from utils.db_helper import query_questions, query_questions_by_weak_points
    
    query = arguments.get("query", "")
    weak_points = arguments.get("weak_points", [])
    question_type = arguments.get("question_type")
    difficulty = arguments.get("difficulty")
    limit = arguments.get("limit", 10)
    
    try:
        # 优先按薄弱知识点检索
        if weak_points:
            logger.info(f"[MCP-Question] 按薄弱知识点检索: {weak_points}")
            questions = query_questions_by_weak_points(weak_points, limit=limit)
        else:
            # 按关键词/题型/难度检索
            logger.info(f"[MCP-Question] 按条件检索: keyword={query}, type={question_type}, diff={difficulty}")
            questions = query_questions(
                question_type=question_type,
                difficulty=difficulty,
                keyword=query if query else None,
                limit=limit
            )
        
        logger.info(f"[MCP-Question] 检索到 {len(questions)} 道题目")
        
        result = {
            "query": query,
            "weak_points": weak_points,
            "questions": questions,
            "total": len(questions),
            "source": "mysql"
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    
    except Exception as e:
        logger.error(f"[MCP-Question] 检索失败: {e}")
        return [TextContent(type="text", text=json.dumps({
            "error": str(e), "query": query, "questions": [], "total": 0
        }, ensure_ascii=False))]


async def handle_get_knowledge_points(arguments: dict):
    """查询知识点列表"""
    from utils.db_helper import query_knowledge_points
    
    category = arguments.get("category")
    
    try:
        points = query_knowledge_points(category=category)
        logger.info(f"[MCP-Question] 查询到 {len(points)} 个知识点")
        
        result = {
            "knowledge_points": points,
            "total": len(points)
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    
    except Exception as e:
        logger.error(f"[MCP-Question] 查询知识点失败: {e}")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]


async def handle_save_homework(arguments: dict):
    """保存作业到数据库"""
    from utils.db_helper import save_homework_template
    
    title = arguments.get("title", "")
    question_ids = arguments.get("question_ids", [])
    target_grade = arguments.get("target_grade", "")
    total_score = arguments.get("total_score", 100)
    
    if not title or not question_ids:
        return [TextContent(type="text", text=json.dumps({
            "status": "error", "message": "标题和题目ID不能为空"
        }, ensure_ascii=False))]
    
    try:
        result = save_homework_template(
            title=title,
            question_ids=question_ids,
            target_grade=target_grade,
            total_score=total_score
        )
        result["status"] = "success"
        result["message"] = f"作业 '{title}' 已保存，包含 {len(question_ids)} 道题目"
        
        logger.info(f"[MCP-Question] 作业已保存: {result}")
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    
    except Exception as e:
        logger.error(f"[MCP-Question] 保存作业失败: {e}")
        return [TextContent(type="text", text=json.dumps({
            "status": "error", "message": str(e)
        }, ensure_ascii=False))]


sse_transport = SseServerTransport("/messages/")


async def handle_sse(request):
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())
    return Response()


async def handle_messages(request):
    await sse_transport.handle_post_message(request.scope, request.receive, request._send)
    return Response()


app = Starlette(routes=[
    Route("/sse", endpoint=handle_sse, methods=["GET"]),
    Mount("/messages/", app=sse_transport.handle_post_message),
])


if __name__ == "__main__":
    import uvicorn
    logger.info(f"题库检索MCP服务启动在端口 {conf.mcp_question_port}")
    uvicorn.run(app, host="0.0.0.0", port=conf.mcp_question_port)
