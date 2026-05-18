# -*- coding: utf-8 -*-
"""
英语教学助手 - 后端主服务

功能：
1. 意图识别
2. Agent路由
3. 结果汇总
"""
import os
import sys
import asyncio
import uuid
import json
import re
from datetime import datetime
from typing import Tuple, List, Dict, Any

import pytz
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from python_a2a import AgentNetwork, Message, TextContent, MessageRole, Task

from config import Config
from create_logger import logger
from main_prompts import EnglishTeachingPrompts

# 初始化配置
conf = Config()

# 创建FastAPI应用
app = FastAPI(
    title="英语教学智能助手",
    description="基于A2A协议的多智能体英语教学系统",
    version="1.0.0"
)

# 全局变量
agent_network = None
llm = None
conversation_history = ""


def initialize_system():
    """初始化系统"""
    global agent_network, llm
    
    logger.info("正在初始化英语教学助手系统...")
    
    # 初始化LLM
    llm = ChatOpenAI(
        model=conf.model_name,
        api_key=conf.api_key,
        base_url=conf.base_url,
        temperature=0.1
    )
    
    # 创建Agent网络并注册所有Agent
    agent_network = AgentNetwork(name="英语教学助手网络")
    agent_network.add("DocGenAssistant", f"http://localhost:{conf.docgen_agent_port}")
    agent_network.add("QuestionAssistant", f"http://localhost:{conf.question_agent_port}")
    agent_network.add("GradingAssistant", f"http://localhost:{conf.grading_agent_port}")
    agent_network.add("AnalysisAssistant", f"http://localhost:{conf.analysis_agent_port}")
    
    logger.info("系统初始化完成")
    logger.info(f"已注册Agent: {list(agent_network.agents.keys())}")


def intent_agent(user_input: str, history: str = "") -> Tuple[List[str], Dict[str, str], str]:
    """
    意图识别Agent
    
    Args:
        user_input: 用户输入
        history: 对话历史
    
    Returns:
        (意图列表, 改写查询字典, 追问消息)
    """
    chain = EnglishTeachingPrompts.intent_prompt() | llm
    
    current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')
    
    # 调用LLM进行意图识别
    intent_response = chain.invoke({
        "conversation_history": history,
        "query": user_input,
        "current_date": current_date
    }).content.strip()
    
    logger.info(f"意图识别原始响应: {intent_response}")
    
    # 清理响应：移除可能的Markdown代码块标记
    intent_response = re.sub(r'^```json\s*|\s*```$', '', intent_response).strip()
    
    # 解析JSON
    intent_output = json.loads(intent_response)
    
    intents = intent_output.get("intents", [])
    user_queries = intent_output.get("user_queries", {})
    follow_up_message = intent_output.get("follow_up_message", "")
    
    logger.info(f"识别到意图: {intents}")
    
    return intents, user_queries, follow_up_message


async def route_to_agent(intent: str, query: str, history: str) -> str:
    """
    根据意图路由到对应Agent
    
    Args:
        intent: 意图类型
        query: 用户查询
        history: 对话历史
    
    Returns:
        Agent响应结果
    """
    # 意图到Agent的映射
    intent_agent_map = {
        "lesson_plan": "DocGenAssistant",
        "question": "QuestionAssistant",
        "grading": "GradingAssistant",
        "analysis": "AnalysisAssistant"
    }
    
    agent_name = intent_agent_map.get(intent)
    if not agent_name:
        return f"暂不支持该意图: {intent}"
    
    try:
        # 获取Agent实例
        agent = agent_network.get_agent(agent_name)
        
        # 构建消息
        chat_content = f"{history}\nUser: {query}"
        message = Message(content=TextContent(text=chat_content), role=MessageRole.USER)
        task = Task(id=f"task-{uuid.uuid4()}", message=message.to_dict())
        
        logger.info(f"正在调用Agent: {agent_name}")
        
        # 发送任务
        response = await agent.send_task_async(task)
        
        # 处理响应
        if response.status.state == 'completed':
            result = response.artifacts[0]['parts'][0]['text']
            logger.info(f"{agent_name} 处理完成")
        else:
            result = response.status.message.get('content', {}).get('text', '处理失败')
            logger.warning(f"{agent_name} 处理异常: {result}")
        
        return result
        
    except Exception as e:
        logger.error(f"调用Agent {agent_name} 失败: {str(e)}")
        return f"调用Agent失败: {str(e)}"


async def process_user_input(user_input: str) -> str:
    """
    处理用户输入
    
    Args:
        user_input: 用户输入文本
    
    Returns:
        处理结果
    """
    global conversation_history
    
    try:
        # 1. 意图识别
        recent_history = '\n'.join(conversation_history.split("\n")[-6:])
        intents, user_queries, follow_up_message = intent_agent(user_input, recent_history)
        
        # 2. 处理超出范围的意图
        if "out_of_scope" in intents:
            conversation_history += f"\nUser: {user_input}\nAssistant: {follow_up_message}"
            return follow_up_message
        
        # 3. 需要追问
        if follow_up_message:
            conversation_history += f"\nUser: {user_input}\nAssistant: {follow_up_message}"
            return follow_up_message
        
        # 4. 处理有效意图
        responses = []
        for intent in intents:
            query = user_queries.get(intent, user_input)
            result = await route_to_agent(intent, query, recent_history)
            responses.append(result)
        
        # 5. 汇总结果
        final_response = "\n\n".join(responses)
        conversation_history += f"\nUser: {user_input}\nAssistant: {final_response}"
        
        return final_response
        
    except json.JSONDecodeError as e:
        logger.error(f"意图识别JSON解析失败: {str(e)}")
        return "抱歉，我无法理解您的请求，请重新描述。"
    except Exception as e:
        logger.error(f"处理失败: {str(e)}")
        return f"处理失败: {str(e)}"


# API 请求模型
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    response: str
    session_id: str


@app.on_event("startup")
async def startup_event():
    """应用启动时初始化"""
    initialize_system()


@app.get("/")
async def root():
    """健康检查"""
    return {"status": "ok", "message": "英语教学助手API正在运行"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """聊天接口"""
    response = await process_user_input(request.message)
    return ChatResponse(response=response, session_id=request.session_id)


@app.get("/agents")
async def list_agents():
    """列出所有Agent"""
    if agent_network:
        return {"agents": list(agent_network.agents.keys())}
    return {"agents": []}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=conf.main_port)
