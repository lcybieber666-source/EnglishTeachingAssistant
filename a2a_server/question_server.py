# -*- coding: utf-8 -*-
"""
出题 Agent - A2A Server

端口: 5011
功能: 智能出题、题库检索、针对性练习生成
"""
import os
import sys
import asyncio
import json
from typing import Dict, Any, List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_a2a import A2AServer, A2AClient, AgentCard, AgentSkill, Message, TextContent, MessageRole, Task, TaskStatus, TaskState
from langchain_openai import ChatOpenAI
from mcp import ClientSession
from mcp.client.sse import sse_client

from config import Config
from create_logger import logger
from main_prompts import EnglishTeachingPrompts

conf = Config()


agent_card = AgentCard(
    name="QuestionAssistant",
    description="智能出题助手，支持根据学生薄弱点生成针对性练习题",
    skills=[
        AgentSkill(
            name="question_generation",
            description="生成练习题或试卷（支持指定题型、知识点、数量）"
        ),
        AgentSkill(
            name="personalized_questions",
            description="根据学生薄弱点生成个性化练习（需要 student_name）"
        )
    ],
    url=f"http://localhost:{conf.question_agent_port}"
)


class QuestionServer(A2AServer):
    """出题Agent服务"""
    
    def __init__(self):
        super().__init__(agent_card=agent_card)
        self.llm = ChatOpenAI(
            model=conf.model_name,
            api_key=conf.api_key,
            base_url=conf.base_url,
            temperature=0.5
        )
        self.mcp_url = f"http://localhost:{conf.mcp_question_port}/sse"
        # A2A客户端，用于调用学情分析Agent
        self.analysis_client = A2AClient(f"http://localhost:{conf.analysis_agent_port}")
    
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
    
    async def get_student_weak_points(self, student_name: str) -> List[str]:
        """通过A2A调用学情分析Agent获取学生薄弱点"""
        try:
            request_data = json.dumps({
                "action": "query_weak_points",
                "student_name": student_name,
                "limit": 5
            })
            
            message = Message(content=TextContent(text=request_data), role=MessageRole.USER)
            task = Task(id=f"task-weak-{student_name}", message=message.to_dict())
            
            response = await self.analysis_client.send_task_async(task)
            
            if response.status.state == 'completed':
                result_text = response.artifacts[0]['parts'][0]['text']
                result_data = json.loads(result_text)
                return result_data.get("weak_points", [])
            else:
                return []
        except Exception as e:
            logger.error(f"获取学生薄弱点失败: {e}")
            return []
    
    async def generate_questions(self, query: str) -> str:
        """生成题目"""
        # 解析请求，检查是否需要个性化出题
        student_name = None
        if "给" in query and ("出" in query or "练习" in query):
            # 尝试提取学生姓名
            import re
            match = re.search(r'给(\w+)出', query)
            if match:
                student_name = match.group(1)
        
        # 获取薄弱点
        weak_points = []
        if student_name:
            weak_points = await self.get_student_weak_points(student_name)
            logger.info(f"学生 {student_name} 的薄弱点: {weak_points}")
        
        weak_points_str = ", ".join(weak_points) if weak_points else "无特定薄弱点"
        
        # 调用MCP检索题库
        question_bank = await self.call_mcp_tool("search_questions", {
            "query": query,
            "weak_points": weak_points
        })
        
        # 使用LLM生成题目
        chain = EnglishTeachingPrompts.question_generation_prompt() | self.llm
        result = chain.invoke({
            "weak_points": weak_points_str,
            "question_bank": question_bank,
            "query": query
        }).content
        
        return result
    
    def handle_message(self, message: Message) -> Message:
        """处理 send_message 请求"""
        text = message.content.text if hasattr(message.content, 'text') else str(message.content)
        logger.info(f"[QuestionAgent] 收到普通消息: {text[:100]}...")
        
        async def _run():
            return await asyncio.wait_for(self.generate_questions(text), timeout=300)
        
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
            
            logger.info(f"[QuestionAgent] 收到任务: {text[:100]}...")
            
            async def _run():
                return await asyncio.wait_for(self.generate_questions(text), timeout=300)
            
            result = asyncio.run(_run())
            
            task.artifacts = [{"parts": [{"type": "text", "text": result}]}]
            task.status = TaskStatus(state=TaskState.COMPLETED)
            
            logger.info("[QuestionAgent] 出题完成")
            
        except Exception as e:
            logger.error(f"[QuestionAgent] 处理失败: {e}")
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message={"content": {"text": f"处理失败: {str(e)}"}}
            )
        
        return task


def main():
    from flask import Flask
    app = Flask(__name__)
    server = QuestionServer()
    server.setup_routes(app)
    logger.info(f"出题Agent服务启动在端口 {conf.question_agent_port}")
    app.run(host="0.0.0.0", port=conf.question_agent_port)


if __name__ == "__main__":
    main()
