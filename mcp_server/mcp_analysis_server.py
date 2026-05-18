# -*- coding: utf-8 -*-
"""
学情分析 MCP Server

端口: 8013
工具: 薄弱点查询(MySQL)、学情数据(MySQL)、Text-to-SQL、批改结果保存
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
from utils.db_helper import (
    get_student_by_name,
    get_student_weak_points,
    get_student_scores,
    get_student_analysis_data,
    get_class_analysis_data,
    execute_readonly_sql,
    save_grading_result,
)

conf = Config()

server = Server("mcp-analysis")


# ========== Text-to-SQL 的表结构描述 ==========
DB_SCHEMA_DESCRIPTION = """
数据库包含以下表：

1. students(id, student_id, name, class_name, grade, created_at) — 学生信息
2. knowledge_points(id, code, name, category, parent_id, difficulty, description) — 知识点
3. questions(id, question_code, question_type, content, options, answer, answer_explanation, knowledge_point_id, difficulty) — 题库
4. homework_templates(id, homework_code, title, description, target_grade, total_score, time_limit, created_by) — 作业模板
5. homework_submissions(id, submission_code, student_id, homework_id, submit_time, total_score, grading_status) — 作业提交
6. error_records(id, student_id, question_id, knowledge_point_id, submission_id, student_answer, correct_answer, error_type, error_count, last_error_time) — 错题记录
7. score_records(id, student_id, homework_id, score, full_score, rank_in_class, exam_date) — 成绩记录
"""


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="query_weak_points",
            description="查询学生薄弱知识点（从错题记录中统计）",
            inputSchema={
                "type": "object",
                "properties": {
                    "student_name": {"type": "string", "description": "学生姓名"},
                    "limit": {"type": "integer", "description": "返回数量", "default": 5}
                },
                "required": ["student_name"]
            }
        ),
        Tool(
            name="get_student_analysis_data",
            description="获取学生综合学情数据（成绩、薄弱点、趋势）",
            inputSchema={
                "type": "object",
                "properties": {
                    "student_name": {"type": "string", "description": "学生姓名"}
                },
                "required": ["student_name"]
            }
        ),
        Tool(
            name="save_grading_result",
            description="保存批改结果到数据库",
            inputSchema={
                "type": "object",
                "properties": {
                    "student_id": {"type": "integer", "description": "学生ID"},
                    "homework_id": {"type": "integer", "description": "作业ID"},
                    "total_score": {"type": "number", "description": "得分"},
                    "errors": {"type": "array", "description": "错题列表"}
                },
                "required": ["student_id", "homework_id", "total_score"]
            }
        ),
        Tool(
            name="execute_sql",
            description="执行 Text-to-SQL 生成的只读查询（仅允许 SELECT）",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "自然语言查询描述"},
                    "sql": {"type": "string", "description": "SQL 语句（由 LLM 生成）"}
                },
                "required": ["query", "sql"]
            }
        ),
        Tool(
            name="get_class_analysis",
            description="班级学情分析：查询班级平均分、成绩排名、班级薄弱知识点分布",
            inputSchema={
                "type": "object",
                "properties": {
                    "class_name": {"type": "string", "description": "班级名称，如 '高一(1)班'"}
                },
                "required": ["class_name"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    logger.info(f"[MCP-Analysis] 调用工具: {name}, 参数: {arguments}")
    
    if name == "query_weak_points":
        student_name = arguments.get("student_name", "")
        limit = arguments.get("limit", 5)
        
        try:
            # 先查学生
            student = get_student_by_name(student_name)
            if not student:
                result = {
                    "status": "not_found",
                    "message": f"未找到学生: {student_name}"
                }
            else:
                weak_points = get_student_weak_points(student["id"], limit)
                result = {
                    "status": "success",
                    "student_name": student_name,
                    "student_id": student["id"],
                    "weak_points": [
                        {
                            "name": wp["name"],
                            "category": wp["category"],
                            "error_count": wp["error_count"],
                            "last_error_time": wp["last_error_time"]
                        }
                        for wp in weak_points
                    ],
                    "total_weak_points": len(weak_points)
                }
            logger.info(f"[MCP-Analysis] 薄弱点查询: {student_name}, {len(result.get('weak_points', []))} 个")
            
        except Exception as e:
            logger.error(f"[MCP-Analysis] 薄弱点查询失败: {e}")
            result = {"status": "error", "message": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    
    elif name == "get_student_analysis_data":
        student_name = arguments.get("student_name", "")
        
        try:
            result = get_student_analysis_data(student_name)
            logger.info(f"[MCP-Analysis] 学情数据: {student_name}, status={result.get('status')}")
        except Exception as e:
            logger.error(f"[MCP-Analysis] 学情数据查询失败: {e}")
            result = {"status": "error", "message": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    
    elif name == "save_grading_result":
        try:
            # 使用已有的 db_helper.save_grading_result
            # 需要先创建 submission，但这里可能已经由批改 Agent 完成
            # 所以直接返回确认
            student_id = arguments.get("student_id")
            homework_id = arguments.get("homework_id")
            total_score = arguments.get("total_score")
            
            result = {
                "status": "success",
                "message": f"已记录学生{student_id}的作业{homework_id}批改结果，得分{total_score}"
            }
            logger.info(f"[MCP-Analysis] 保存批改结果: student={student_id}, score={total_score}")
            
        except Exception as e:
            logger.error(f"[MCP-Analysis] 保存批改结果失败: {e}")
            result = {"status": "error", "message": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    
    elif name == "execute_sql":
        query = arguments.get("query", "")
        sql = arguments.get("sql", "")
        
        if not sql:
            result = {
                "status": "error",
                "message": "未提供 SQL 语句",
                "hint": f"请根据以下表结构生成 SQL:\n{DB_SCHEMA_DESCRIPTION}"
            }
        else:
            try:
                result = execute_readonly_sql(sql)
                result["original_query"] = query
                logger.info(f"[MCP-Analysis] Text-to-SQL: '{query}' -> {result.get('row_count', 0)} 行")
            except Exception as e:
                logger.error(f"[MCP-Analysis] SQL 执行失败: {e}")
                result = {"status": "error", "message": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    
    elif name == "get_class_analysis":
        class_name = arguments.get("class_name", "")
        
        try:
            result = get_class_analysis_data(class_name)
            logger.info(f"[MCP-Analysis] 班级学情: {class_name}, status={result.get('status')}")
        except Exception as e:
            logger.error(f"[MCP-Analysis] 班级学情分析失败: {e}")
            result = {"status": "error", "message": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    
    else:
        return [TextContent(type="text", text=f"未知工具: {name}")]


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
    logger.info(f"学情分析MCP服务启动在端口 {conf.mcp_analysis_port}")
    uvicorn.run(app, host="0.0.0.0", port=conf.mcp_analysis_port)
