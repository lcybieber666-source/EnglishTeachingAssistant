# -*- coding: utf-8 -*-
"""
作业批改 Agent - A2A Server

端口: 5012
功能: OCR识别、答案比对、自动评分、学情更新
"""
import os
import sys
import asyncio
import json
import re
from typing import Dict, Any

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
    name="GradingAssistant",
    description="作业批改智能助手，支持OCR识别和自动评分",
    skills=[
        AgentSkill(
            name="homework_grading",
            description="批改作业（需要 homework_id, student_id, image_path）"
        ),
        AgentSkill(
            name="ocr_recognition",
            description="OCR识别手写内容（需要 image_path）"
        )
    ],
    url=f"http://localhost:{conf.grading_agent_port}"
)


class GradingServer(A2AServer):
    """作业批改Agent服务"""
    
    def __init__(self):
        super().__init__(agent_card=agent_card)
        self.llm = ChatOpenAI(
            model=conf.model_name,
            api_key=conf.api_key,
            base_url=conf.base_url,
            temperature=0.1
        )
        self.mcp_url = f"http://localhost:{conf.mcp_grading_port}/sse"
        # A2A客户端，用于调用学情分析Agent写入批改结果
        self.analysis_client = A2AClient(f"http://localhost:{conf.analysis_agent_port}")
    
    def handle_message(self, message):
        """处理 send_message 请求"""
        text = message.content.text if hasattr(message.content, 'text') else str(message.content)
        logger.info(f"[GradingAgent] 收到消息: {text[:100]}...")
        
        params = self._parse_request(text)
        
        async def _run_with_timeout():
            return await asyncio.wait_for(self.grade_homework(params), timeout=240)
        
        result = asyncio.run(_run_with_timeout())
        
        return Message(
            content=TextContent(text=result),
            role=MessageRole.AGENT,
            parent_message_id=getattr(message, 'message_id', None),
            conversation_id=getattr(message, 'conversation_id', None)
        )
    
    async def call_mcp_tool(self, tool_name: str, params: Dict[str, Any]) -> str:
        """调用MCP工具"""
        mcp_result = None
        try:
            async with sse_client(self.mcp_url, timeout=120) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, params)
                    mcp_result = result.content[0].text if result.content else ""
        except BaseException as e:
            # MCP SSE client 的 post_writer 在 SSE 连接关闭时会抛出 ReadError，
            # 被 anyio TaskGroup 包装为 ExceptionGroup。
            # 如果工具调用结果已经拿到了，忽略此异常直接返回结果。
            if mcp_result is not None:
                logger.warning(f"MCP SSE 连接关闭时异常（已忽略，结果已获取）: {e}")
                return mcp_result
            logger.error(f"MCP调用失败: {e}")
            return json.dumps({"status": "error", "message": f"MCP调用失败: {str(e)}"})
        return mcp_result
    
    async def save_grading_to_analysis(self, grading_data: Dict[str, Any]) -> bool:
        """通过A2A调用学情分析Agent保存批改结果"""
        try:
            request_data = json.dumps({
                "action": "save_grading_result",
                **grading_data
            })
            
            message = Message(content=TextContent(text=request_data), role=MessageRole.USER)
            task = Task(id=f"task-grade-save", message=message.to_dict())
            
            response = await self.analysis_client.send_task_async(task)
            
            return response.status.state == 'completed'
        except Exception as e:
            logger.error(f"通知学情分析Agent失败: {e}")
            return False
    
    def _parse_request(self, text: str) -> Dict[str, Any]:
        """从请求文本中提取参数"""
        params = {}
        
        # 尝试解析JSON格式
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass
        
        # 从文本中提取参数
        patterns = {
            "homework_id": r'homework_id[:\s]+(\d+)',
            "student_id": r'student_id[:\s]+(\d+)',
            "image_path": r'image_path[:\s]+(\S+)',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                value = match.group(1)
                params[key] = int(value) if key.endswith("_id") else value
        
        params["query"] = text
        return params
    
    async def _grade_by_image_only(self, image_path: str, query: str) -> str:
        """仅通过图片进行通用批改（无标准答案，OCR + LLM）"""
        logger.info(f"[GradingAgent] 纯图片批改模式: {image_path}")
        
        # 1. OCR 识别
        ocr_text = ""
        ocr_result = await self.call_mcp_tool("ocr_recognize", {"image_path": image_path})
        try:
            ocr_data = json.loads(ocr_result)
            if ocr_data.get("status") == "success":
                ocr_text = ocr_data.get("full_text", "")
                logger.info(f"OCR识别成功: {len(ocr_data.get('lines', []))} 行")
            else:
                return f"OCR识别失败: {ocr_data.get('message', '未知错误')}"
        except Exception:
            ocr_text = ocr_result
        
        if not ocr_text.strip():
            return "OCR未能识别出有效文字内容，请确保图片清晰且包含手写或打印文字。"
        
        # 2. 让 LLM 根据识别内容直接批改
        chain = EnglishTeachingPrompts.grading_prompt() | self.llm
        result = chain.invoke({
            "standard_answers": "（未提供标准答案，请根据英语语法和知识自行判断正确性）",
            "student_answers": ocr_text,
            "query": query
        }).content
        
        return result
    
    async def grade_homework(self, params: Dict[str, Any]) -> str:
        """批改作业 — 完整流程"""
        homework_id = params.get("homework_id")
        student_id = params.get("student_id")
        image_path = params.get("image_path")
        query = params.get("query", "批改作业")
        
        # 如果没有 homework_id 但有图片，走简化的 OCR + LLM 通用批改
        if not homework_id and image_path and os.path.exists(image_path):
            return await self._grade_by_image_only(image_path, query)
        
        if not homework_id:
            return "缺少参数: homework_id（作业ID）。请提供作业ID以进行批改，或上传作业图片进行通用批改。"
        
        # ===== 1. 创建提交记录 =====
        submission_id = None
        if student_id:
            sub_result = await self.call_mcp_tool("create_submission", {
                "student_id": student_id,
                "homework_id": homework_id,
                "image_path": image_path
            })
            try:
                sub_data = json.loads(sub_result)
                submission_id = sub_data.get("submission_id")
                logger.info(f"创建提交记录: submission_id={submission_id}")
            except Exception:
                logger.warning(f"创建提交记录解析失败: {sub_result}")
        
        # ===== 2. OCR识别学生答案 =====
        ocr_text = ""
        ocr_data = None
        if image_path and os.path.exists(image_path):
            ocr_result = await self.call_mcp_tool("ocr_recognize", {"image_path": image_path})
            try:
                ocr_data = json.loads(ocr_result)
                if ocr_data.get("status") == "success":
                    ocr_text = ocr_data.get("full_text", "")
                    logger.info(f"OCR识别成功: {len(ocr_data.get('lines', []))} 行")
                else:
                    ocr_text = f"OCR识别失败: {ocr_data.get('message', '未知错误')}"
            except Exception:
                ocr_text = ocr_result
        else:
            ocr_text = params.get("student_answers", "未提供作业图片")
        
        # ===== 3. 获取标准答案 =====
        answers_result = await self.call_mcp_tool("get_standard_answers", {"homework_id": homework_id})
        try:
            answers_data = json.loads(answers_result)
            if answers_data.get("status") != "success":
                return f"获取标准答案失败: {answers_data.get('message', '作业ID不存在')}"
        except Exception:
            return f"获取标准答案失败: {answers_result}"
        
        # ===== 4. LLM 批改 =====
        chain = EnglishTeachingPrompts.grading_prompt() | self.llm
        result = chain.invoke({
            "standard_answers": json.dumps(answers_data, ensure_ascii=False, default=str),
            "student_answers": ocr_text,
            "query": query
        }).content
        
        # ===== 5. 保存批改结果到数据库 =====
        total_score = 0
        if submission_id and student_id:
            try:
                full_score = answers_data.get("total_score", 100)
                
                # 尝试从 LLM 结果中提取分数（去除 Markdown 标记后匹配）
                clean_result = re.sub(r'\*+', '', result)  # 去掉 ** 加粗
                score_patterns = [
                    r'总[分得]\s*[：:]\s*(\d+(?:\.\d+)?)',       # 总分：8
                    r'得分\s*[：:]\s*(\d+(?:\.\d+)?)',           # 得分：8
                    r'得分率\s*[：:]\s*(\d+(?:\.\d+)?)%',       # 得分率：80%
                    r'(\d+(?:\.\d+)?)\s*/\s*\d+',              # 8 / 10
                ]
                total_score = 0
                for pattern in score_patterns:
                    score_match = re.search(pattern, clean_result)
                    if score_match:
                        val = float(score_match.group(1))
                        # 如果匹配到的是得分率（百分比），转换为实际分数
                        if '得分率' in pattern:
                            val = val / 100 * full_score
                        total_score = val
                        break
                
                # 尝试从 LLM 结果中解析结构化错题信息
                errors = []
                questions = answers_data.get("questions", [])
                for q in questions:
                    q_no = str(q.get("question_no", ""))
                    correct_answer = q.get("answer", "")
                    # 在 LLM 返回中搜索每道题的判定结果
                    wrong_pattern = rf'第\s*{q_no}\s*题.*?[错✗×]'
                    if re.search(wrong_pattern, result):
                        errors.append({
                            "question_id": q.get("question_id"),
                            "knowledge_point_id": q.get("knowledge_point_id"),
                            "student_answer": "",
                            "correct_answer": correct_answer,
                            "error_type": "concept_error"
                        })
                
                # 保存到数据库
                save_result = await self.call_mcp_tool("save_grading_result", {
                    "submission_id": submission_id,
                    "student_id": student_id,
                    "homework_id": homework_id,
                    "total_score": total_score,
                    "full_score": full_score,
                    "ocr_result": ocr_data,
                    "errors": errors
                })
                logger.info(f"批改结果已保存: {save_result}，错题数: {len(errors)}")
                
            except Exception as e:
                logger.warning(f"保存批改结果失败: {e}")
        
        # ===== 6. 通知学情分析Agent =====
        if student_id:
            try:
                await self.save_grading_to_analysis({
                    "student_id": student_id,
                    "homework_id": homework_id,
                    "total_score": total_score,
                })
                logger.info("已通知学情分析Agent")
            except Exception as e:
                logger.warning(f"通知学情分析Agent失败: {e}")
        
        return result
    
    def handle_task(self, task: Task) -> Task:
        """处理任务"""
        try:
            # 从 task.message 中提取文本（兼容多种格式）
            text = ""
            message = task.message
            if message and isinstance(message, dict):
                content = message.get("content", {})
                if isinstance(content, dict):
                    text = content.get("text", "")
                elif isinstance(content, str):
                    text = content
                # Google A2A format
                if not text:
                    for part in message.get("parts", []):
                        if isinstance(part, dict) and part.get("type") == "text":
                            text = part.get("text", "")
                            break
            elif message:
                text = str(message)
            
            logger.info(f"[GradingAgent] 收到请求: {text[:100]}...")
            
            # 解析请求参数
            params = self._parse_request(text)
            
            async def _run_with_timeout():
                return await asyncio.wait_for(self.grade_homework(params), timeout=240)
            
            result = asyncio.run(_run_with_timeout())
            
            task.artifacts = [{"parts": [{"type": "text", "text": result}]}]
            task.status = TaskStatus(state=TaskState.COMPLETED)
            
            logger.info("[GradingAgent] 批改完成")
            
        except Exception as e:
            logger.error(f"[GradingAgent] 处理失败: {e}")
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message={"content": {"text": f"处理失败: {str(e)}"}}
            )
        
        return task


def main():
    from flask import Flask
    app = Flask(__name__)
    server = GradingServer()
    server.setup_routes(app)
    logger.info(f"作业批改Agent服务启动在端口 {conf.grading_agent_port}")
    app.run(host="0.0.0.0", port=conf.grading_agent_port)


if __name__ == "__main__":
    main()
