# -*- coding: utf-8 -*-
"""
学情分析 Agent - A2A Server

端口: 5013
功能: 学情分析、薄弱点查询、成绩统计、批改结果存储、班级学情分析
"""
import os
import sys
import asyncio
import json
from typing import Dict, Any, List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_a2a import A2AServer, AgentCard, AgentSkill, Message, TextContent, MessageRole, Task, TaskStatus, TaskState
from langchain_openai import ChatOpenAI
from mcp import ClientSession
from mcp.client.sse import sse_client

from config import Config
from create_logger import logger
from main_prompts import EnglishTeachingPrompts

conf = Config()


agent_card = AgentCard(
    name="AnalysisAssistant",
    description="学情分析智能助手，支持学习数据分析和个性化建议",
    skills=[
        AgentSkill(
            name="query_weak_points",
            description="查询学生薄弱知识点（需要 student_name）"
        ),
        AgentSkill(
            name="save_grading_result",
            description="保存批改结果到学情系统（需要 student_id, homework_id, scores, errors）"
        ),
        AgentSkill(
            name="generate_report",
            description="生成学情分析报告（需要 student_name）"
        ),
        AgentSkill(
            name="get_class_analysis",
            description="班级学情分析：查询班级平均分、成绩排名、薄弱知识点分布（需要 class_name）"
        )
    ],
    url=f"http://localhost:{conf.analysis_agent_port}"
)


class AnalysisServer(A2AServer):
    """学情分析Agent服务"""
    
    def __init__(self):
        super().__init__(agent_card=agent_card)
        self.llm = ChatOpenAI(
            model=conf.model_name,
            api_key=conf.api_key,
            base_url=conf.base_url,
            temperature=0.2
        )
        self.mcp_url = f"http://localhost:{conf.mcp_analysis_port}/sse"
    
    async def call_mcp_tool(self, tool_name: str, params: Dict[str, Any]) -> str:
        """调用MCP工具"""
        mcp_result = None
        try:
            async with sse_client(self.mcp_url, timeout=30) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, params)
                    mcp_result = result.content[0].text if result.content else ""
        except BaseException as e:
            if mcp_result is not None:
                logger.warning(f"MCP SSE 连接关闭时异常（已忽略）: {e}")
                return mcp_result
            logger.error(f"MCP调用失败: {e}")
            return json.dumps({"error": str(e)})
        return mcp_result
    
    async def query_weak_points(self, student_name: str, limit: int = 5) -> Dict[str, Any]:
        """查询学生薄弱知识点"""
        result = await self.call_mcp_tool("query_weak_points", {
            "student_name": student_name,
            "limit": limit
        })
        
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            logger.error(f"薄弱点查询结果解析失败: {result}")
            return {
                "status": "error",
                "message": f"查询失败: {result}"
            }
    
    async def save_grading_result(self, grading_data: Dict[str, Any]) -> Dict[str, Any]:
        """保存批改结果"""
        result = await self.call_mcp_tool("save_grading_result", grading_data)
        
        return {"status": "success", "message": "批改结果已保存"}
    
    async def get_class_analysis(self, class_name: str) -> Dict[str, Any]:
        """班级学情分析"""
        result = await self.call_mcp_tool("get_class_analysis", {
            "class_name": class_name
        })
        
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            logger.error(f"班级学情分析结果解析失败: {result}")
            return {
                "status": "error",
                "message": f"查询失败: {result}"
            }
    
    async def generate_analysis_report(self, student_name: str) -> str:
        """生成学情分析报告"""
        # 获取学生数据
        student_data = await self.call_mcp_tool("get_student_analysis_data", {
            "student_name": student_name
        })
        
        # 使用LLM生成报告
        chain = EnglishTeachingPrompts.analysis_prompt() | self.llm
        result = chain.invoke({
            "student_data": student_data,
            "query": f"分析学生{student_name}的学习情况"
        }).content
        
        return result
    
    def handle_message(self, message: Message) -> Message:
        """处理 send_message 请求"""
        text = message.content.text if hasattr(message.content, 'text') else str(message.content)
        logger.info(f"[AnalysisAgent] 收到普通消息: {text[:100]}...")
        
        async def _run():
            return await asyncio.wait_for(self.generate_analysis_report(text.replace('分析', '').replace('学情', '').strip() or '张三'), timeout=300)
        
        result = asyncio.run(_run())
        
        return Message(
            content=TextContent(text=result),
            role=MessageRole.AGENT,
            parent_message_id=getattr(message, 'message_id', None),
            conversation_id=getattr(message, 'conversation_id', None)
        )
    
    def handle_task(self, task: Task) -> Task:
        """处理任务"""
        try:
            if task.message:
                content = task.message.get("content", {}) if isinstance(task.message, dict) else getattr(task.message, "content", {})
                if isinstance(content, dict):
                    text = content.get("text", "")
                elif hasattr(content, "text"):
                    text = content.text
                else:
                    text = str(content)
            else:
                text = str(task.params) if hasattr(task, 'params') else ""
            
            logger.info(f"[AnalysisAgent] 收到任务: {text[:100]}...")
            
            # 尝试解析JSON请求
            try:
                request_data = json.loads(text)
                action = request_data.get("action", "")
            except json.JSONDecodeError:
                request_data = {}
                action = ""
            
            # 根据action处理不同请求
            if action == "query_weak_points":
                student_name = request_data.get("student_name", "")
                limit = request_data.get("limit", 5)
                
                async def _run_weak():
                    return await asyncio.wait_for(self.query_weak_points(student_name, limit), timeout=120)
                
                result = asyncio.run(_run_weak())
                result_text = json.dumps(result, ensure_ascii=False)
                
            elif action == "save_grading_result":
                async def _run_save():
                    return await asyncio.wait_for(self.save_grading_result(request_data), timeout=120)
                
                result = asyncio.run(_run_save())
                result_text = json.dumps(result, ensure_ascii=False)
                
            elif action == "get_class_analysis":
                class_name = request_data.get("class_name", "")
                
                async def _run_class():
                    return await asyncio.wait_for(self.get_class_analysis(class_name), timeout=120)
                
                result = asyncio.run(_run_class())
                result_text = json.dumps(result, ensure_ascii=False)
                
            else:
                # 默认生成学情报告
                import re
                match = re.search(r'(分析|查询|看看).*?(\w{2,4})(的|学习)', text)
                student_name = match.group(2) if match else "张三"
                
                async def _run_report():
                    return await asyncio.wait_for(self.generate_analysis_report(student_name), timeout=300)
                
                result_text = asyncio.run(_run_report())
            
            task.artifacts = [{"parts": [{"type": "text", "text": result_text}]}]
            task.status = TaskStatus(state=TaskState.COMPLETED)
            
            logger.info("[AnalysisAgent] 处理完成")
            
        except Exception as e:
            logger.error(f"[AnalysisAgent] 处理失败: {e}")
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message={"content": {"text": f"处理失败: {str(e)}"}}
            )
        
        return task


def main():
    from flask import Flask
    app = Flask(__name__)
    server = AnalysisServer()
    server.setup_routes(app)
    logger.info(f"学情分析Agent服务启动在端口 {conf.analysis_agent_port}")
    app.run(host="0.0.0.0", port=conf.analysis_agent_port)


if __name__ == "__main__":
    main()
