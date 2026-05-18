# -*- coding: utf-8 -*-
"""
教案生成 MCP Server

端口: 8010
工具:
1. search_textbook - RAG 课本检索（Milvus 混合检索）
2. generate_lesson_plan - 生成教案（LLM + Word）
"""
import os
import sys
import json
from typing import Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import Response
from langchain_openai import ChatOpenAI

from config import Config
from create_logger import logger

conf = Config()

# 创建MCP服务器
server = Server("mcp-docgen")

# 延迟加载的服务
_milvus_client = None
_embedding_service = None
_reranker_service = None
_llm = None


def get_milvus_client():
    """获取 Milvus 客户端（延迟加载）"""
    global _milvus_client
    if _milvus_client is None:
        from utils.milvus_client import get_milvus_client as create_client
        _milvus_client = create_client(
            host=conf.milvus_host,
            port=conf.milvus_port,
            collection_name=conf.milvus_collection
        )
        _milvus_client.load()
    return _milvus_client


def get_embedding_service():
    """获取 Embedding 服务（延迟加载）"""
    global _embedding_service
    if _embedding_service is None:
        from utils.embedding_service import get_embedding_service as create_service
        _embedding_service = create_service(model_name=conf.embedding_model)
    return _embedding_service


def get_reranker_service():
    """获取 Reranker 服务（延迟加载）"""
    global _reranker_service
    if _reranker_service is None:
        from utils.reranker_service import get_reranker_service as create_reranker
        _reranker_service = create_reranker(model_name=conf.reranker_model)
    return _reranker_service


def get_llm():
    """获取 LLM（延迟加载）"""
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            model=conf.model_name,
            api_key=conf.api_key,
            base_url=conf.base_url,
            temperature=0.3
        )
    return _llm


@server.list_tools()
async def list_tools():
    """列出可用工具"""
    return [
        Tool(
            name="search_textbook",
            description="检索课本内容，使用 RAG 从向量数据库中检索相关课本片段。支持按 Unit 和内容类型过滤。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词，如 'Unit 1 动物对话'"},
                    "limit": {"type": "integer", "description": "返回数量", "default": 5},
                    "unit": {"type": "integer", "description": "按 Unit 过滤（1-8），不传则不过滤"},
                    "content_type": {
                        "type": "string",
                        "description": "按内容类型过滤: grammar, vocabulary, listening_script, reading, reading_plus, pronunciation, content, project, unit_overview",
                    },
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="generate_lesson_plan",
            description="生成教案并导出为 Word 文档",
            inputSchema={
                "type": "object",
                "properties": {
                    "grade": {"type": "string", "description": "年级，如 '七年级'"},
                    "unit": {"type": "string", "description": "单元，如 'Unit 1'"},
                    "topic": {"type": "string", "description": "课题"},
                    "textbook_content": {"type": "string", "description": "课本相关内容（RAG 检索结果）"},
                    "requirements": {"type": "string", "description": "其他要求"}
                },
                "required": ["grade", "unit"]
            }
        )
    ]


async def search_textbook_impl(
    query: str, limit: int = 5,
    unit: int = None, content_type: str = None,
) -> Dict[str, Any]:
    """
    两阶段 RAG 课本检索（支持 metadata 过滤）
    第一阶段: BGE-M3 混合检索 (快速召回 top-k*4)
    第二阶段: BGE-Reranker-Large 精细重排序 (返回 top-k)
    """
    try:
        embedding_service = get_embedding_service()
        milvus_client = get_milvus_client()
        reranker = get_reranker_service()

        # MCP/JSON 可能传入 float，统一为 int，避免 Milvus expr 与 JSON 整型不一致
        if unit is not None:
            unit = int(unit)

        # 构建 metadata 过滤表达式
        expr_parts = []
        if unit is not None:
            expr_parts.append(f'metadata["unit"] == {unit}')
        if content_type:
            expr_parts.append(f'metadata["content_type"] == "{content_type}"')
        expr = " and ".join(expr_parts) if expr_parts else None

        logger.info(f"[RAG] 查询: {query}, unit={unit}, content_type={content_type}, expr={expr}")
        dense_vec, sparse_vec = embedding_service.encode_single(query)

        # === 第一阶段: 混合检索（扩大召回量） ===
        recall_limit = limit * 4
        logger.info(f"[RAG-阶段1] BGE-M3 混合检索，召回 top-{recall_limit}...")
        results = milvus_client.hybrid_search(
            query_dense=dense_vec.tolist(),
            query_sparse=sparse_vec,
            limit=recall_limit,
            dense_weight=0.7,
            sparse_weight=0.3,
            expr=expr,
        )

        logger.info(f"[RAG-阶段1] 召回 {len(results)} 条结果")

        if not results:
            return {"query": query, "total": 0, "sections": [], "filter": {"unit": unit, "content_type": content_type}}

        # === 第二阶段: Reranker 精排 ===
        logger.info(f"[RAG-阶段2] BGE-Reranker-Large 精排，返回 top-{limit}...")
        reranked_results = reranker.rerank(
            query=query,
            documents=results,
            content_key="parent_content",
            top_k=limit,
        )

        logger.info(f"[RAG-阶段2] 精排后 {len(reranked_results)} 条结果")

        sections = []
        for r in reranked_results:
            sections.append({
                "id": r["id"],
                "content": r["content"],
                "parent_content": r["parent_content"],
                "retrieval_score": r.get("score", 0),
                "rerank_score": r.get("rerank_score", 0),
                "metadata": r.get("metadata", {}),
            })

        return {
            "query": query,
            "total": len(sections),
            "recall_count": len(results),
            "filter": {"unit": unit, "content_type": content_type},
            "sections": sections,
        }

    except Exception as e:
        logger.error(f"[RAG] 检索失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            "query": query,
            "total": 0,
            "sections": [],
            "error": str(e),
            "fallback": True,
        }


async def generate_lesson_plan_impl(
    grade: str,
    unit: str,
    topic: str = None,
    textbook_content: str = None,
    requirements: str = None
) -> Dict[str, Any]:
    """生成教案实现"""
    from utils.word_generator import generate_lesson_plan
    
    # 构建 Prompt（适配教案生成模板格式）
    prompt = f"""你是一位经验丰富的英语教师，请根据以下信息生成一份详细的英语教案。

## 基本信息
- 年级: {grade}
- 单元: {unit}
- 课题: {topic or unit}

## 课本内容参考
{textbook_content or "（无课本内容参考，请根据教学经验生成）"}

## 其他要求
{requirements or "无特殊要求"}

## 输出要求
请以 JSON 格式输出教案，严格包含以下所有字段（全部用英文书写教学内容）：
{{
    "topic_content": "课题内容，如 Unit 1 Section A Making Friends (1a-2d)",
    "lesson_type": "课型，如 Reading / Listening / Speaking / Grammar",
    "situation_analysis": "教情学情分析，分析学生现有水平、该课时内容特点和学生可能的困难",
    "teaching_objectives": "教学目标，包含4维度：1.Language ability 2.Learning ability 3.Thinking quality 4.Cultural awareness",
    "key_points": "教学重点，列出2-3个重点",
    "difficult_points": "教学难点",
    "teaching_methods": "教法，如 Task-based teaching, Communicative approach, Situational teaching",
    "learning_methods": "学法，如 Group-work, Pair-work, Independent learning",
    "lead_in_teacher": "导入部分-教师活动，详细描述教师在导入环节的具体操作",
    "lead_in_student": "导入部分-学生活动，描述学生在导入环节的具体活动",
    "lead_in_purpose": "导入部分-设计意图，说明设计导入活动的目的",
    "new_lesson_teacher": "新课学习-教师活动，详细描述 Pre-reading/While-reading/Post-reading 或其他阶段的教师活动",
    "new_lesson_student": "新课学习-学生活动，描述每个阶段学生的具体活动",
    "new_lesson_purpose": "新课学习-设计意图，说明各阶段活动的设计目的",
    "summary": "课堂小结，描述如何总结本课所学",
    "summary_purpose": "课堂小结-设计意图",
    "homework": "作业布置，分 Must-do 和 Choose-to-do 两部分",
    "homework_purpose": "作业设计意图",
    "board_design": "板书设计，简要列出板书内容",
    "board_purpose": "板书设计意图",
    "reflection": ""
}}

请直接输出 JSON，不要有其他内容。注意：教学过程（导入、新课学习）要尽量详细具体。
"""
    
    try:
        # 调用 LLM 生成教案
        logger.info(f"[LLM] 正在生成教案: {grade} {unit}")
        llm = get_llm()
        response = llm.invoke(prompt)
        content = response.content.strip()
        
        # 解析 JSON
        # 移除可能的 Markdown 代码块标记
        import re
        content = re.sub(r'^```json\s*|\s*```$', '', content).strip()
        lesson_data = json.loads(content)
        
        # 补充不在 LLM 输出中的字段
        lesson_data["title"] = lesson_data.get("topic_content", f"{unit} {topic or ''}")
        lesson_data["grade"] = grade
        lesson_data["unit"] = unit
        if topic:
            lesson_data["topic"] = topic
        
        # 生成 Word 文档
        logger.info(f"[Word] 正在生成 Word 文档...")
        word_path = generate_lesson_plan(lesson_data)
        
        logger.info(f"[DocGen] 教案生成完成: {word_path}")
        
        return {
            "status": "success",
            "lesson_plan": lesson_data,
            "word_path": word_path,
            "message": f"教案已生成并保存到: {word_path}"
        }
        
    except json.JSONDecodeError as e:
        logger.error(f"[LLM] JSON 解析失败: {e}")
        return {
            "status": "error",
            "error": f"LLM 输出格式错误: {str(e)}",
            "raw_content": content if 'content' in dir() else ""
        }
    except Exception as e:
        logger.error(f"[DocGen] 生成失败: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """调用工具"""
    logger.info(f"[MCP-DocGen] 调用工具: {name}, 参数: {arguments}")
    
    if name == "search_textbook":
        query = arguments.get("query", "")
        limit = arguments.get("limit", 5)
        unit = arguments.get("unit")
        content_type = arguments.get("content_type")
        result = await search_textbook_impl(query, limit, unit=unit, content_type=content_type)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "generate_lesson_plan":
        grade = arguments.get("grade", "七年级")
        unit = arguments.get("unit", "Unit 1")
        topic = arguments.get("topic")
        textbook_content = arguments.get("textbook_content")
        requirements = arguments.get("requirements")
        
        result = await generate_lesson_plan_impl(
            grade=grade,
            unit=unit,
            topic=topic,
            textbook_content=textbook_content,
            requirements=requirements
        )
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    else:
        return [TextContent(type="text", text=f"未知工具: {name}")]


# SSE 传输
sse_transport = SseServerTransport("/messages/")


async def handle_sse(request):
    async with sse_transport.connect_sse(
        request.scope,
        request.receive,
        request._send
    ) as streams:
        await server.run(
            streams[0],
            streams[1],
            server.create_initialization_options()
        )
    return Response()


async def handle_messages(request):
    await sse_transport.handle_post_message(request.scope, request.receive, request._send)
    return Response()


# Starlette 应用
app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Mount("/messages/", app=sse_transport.handle_post_message),
    ]
)


if __name__ == "__main__":
    import uvicorn
    logger.info(f"教案生成MCP服务启动在端口 {conf.mcp_docgen_port}")
    uvicorn.run(app, host="0.0.0.0", port=conf.mcp_docgen_port)
