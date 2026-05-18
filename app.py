# -*- coding: utf-8 -*-
"""
英语教学助手 - Streamlit 前端

功能：
1. 对话式交互界面
2. 文件上传（作业图片）
3. Agent 状态展示
"""
import os
import sys
import asyncio
import uuid
import json
import re
from datetime import datetime

import streamlit as st
import pytz
from python_a2a import AgentNetwork, A2AClient, Message, TextContent, MessageRole, Task
from langchain_openai import ChatOpenAI

from config import Config
from create_logger import logger
from main_prompts import EnglishTeachingPrompts

conf = Config()

# 页面配置
st.set_page_config(
    page_title="英语教学智能助手",
    layout="wide",
    page_icon="📚"
)

# 自定义CSS样式
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&display=swap');

/* 全局字体 */
html, body, [class*="css"] {
    font-family: 'Noto Sans SC', sans-serif;
}

/* 聊天消息框样式 */
.stChatMessage {
    background: linear-gradient(135deg, #1e2a3a 0%, #2c3e50 100%) !important;
    border-radius: 16px !important;
    padding: 18px !important;
    margin-bottom: 16px !important;
    box-shadow: 0 4px 15px rgba(0,0,0,0.25) !important;
    border: 1px solid rgba(255,255,255,0.05) !important;
    transition: transform 0.2s ease, box-shadow 0.2s ease !important;
}
.stChatMessage:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(0,0,0,0.35) !important;
}

/* 文字颜色 */
.stChatMessage .stMarkdown, 
.stChatMessage .stMarkdown p, 
.stChatMessage .stMarkdown span, 
.stChatMessage .stMarkdown div, 
.stChatMessage .stMarkdown strong,
.stChatMessage .stMarkdown em,
.stChatMessage .stMarkdown code {
    color: #e8eaf0 !important; 
}

/* 页面标题样式 */
.main-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
    padding: 28px 20px;
    border-radius: 16px;
    margin-bottom: 24px;
    color: white;
    text-align: center;
    box-shadow: 0 8px 32px rgba(102, 126, 234, 0.35);
    position: relative;
    overflow: hidden;
}
.main-header::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle, rgba(255,255,255,0.08) 0%, transparent 60%);
    animation: headerShine 6s ease-in-out infinite;
}
@keyframes headerShine {
    0%, 100% { transform: translate(0, 0); }
    50% { transform: translate(25%, 25%); }
}
.main-header h1 {
    font-size: 1.8em;
    font-weight: 700;
    margin-bottom: 4px;
    position: relative;
}
.main-header p {
    opacity: 0.9;
    font-size: 0.95em;
    position: relative;
}

/* 侧栏按钮美化 */
.stButton > button {
    border: none !important;
    border-radius: 10px !important;
    padding: 10px 16px !important;
    font-weight: 500 !important;
    transition: all 0.3s ease !important;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
    box-shadow: 0 3px 10px rgba(102, 126, 234, 0.3) !important;
}
.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5) !important;
}

/* Expander 卡片效果 */
.streamlit-expanderHeader {
    border-radius: 10px !important;
    font-weight: 500 !important;
}

/* 页脚样式 */
.footer {
    text-align: center;
    color: #888;
    padding: 16px;
    font-size: 12px;
    letter-spacing: 0.5px;
}
</style>
""", unsafe_allow_html=True)


# ============= 初始化会话状态 =============
if "messages" not in st.session_state:
    st.session_state.messages = []

if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = ""

if "agent_network" not in st.session_state:
    # Agent URL配置
    st.session_state.agent_urls = {
        "DocGenAssistant": f"http://localhost:{conf.docgen_agent_port}",
        "QuestionAssistant": f"http://localhost:{conf.question_agent_port}",
        "GradingAssistant": f"http://localhost:{conf.grading_agent_port}",
        "AnalysisAssistant": f"http://localhost:{conf.analysis_agent_port}"
    }
    
    # 初始化Agent网络（手动创建A2AClient以设置超时300秒，默认30秒不够OCR+LLM处理）
    network = AgentNetwork(name="英语教学助手网络")
    for name, port in [
        ("DocGenAssistant", conf.docgen_agent_port),
        ("QuestionAssistant", conf.question_agent_port),
        ("GradingAssistant", conf.grading_agent_port),
        ("AnalysisAssistant", conf.analysis_agent_port),
    ]:
        client = A2AClient(f"http://localhost:{port}", timeout=300)
        network.add(name, client)
    st.session_state.agent_network = network
    
    # 初始化LLM
    st.session_state.llm = ChatOpenAI(
        model=conf.model_name,
        api_key=conf.api_key,
        base_url=conf.base_url,
        temperature=0.1
    )


def intent_agent(user_input: str):
    """意图识别"""
    chain = EnglishTeachingPrompts.intent_prompt() | st.session_state.llm
    
    current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')
    recent_history = '\n'.join(st.session_state.conversation_history.split("\n")[-6:])
    
    intent_response = chain.invoke({
        "conversation_history": recent_history,
        "query": user_input,
        "current_date": current_date
    }).content.strip()
    
    # 清理JSON
    intent_response = re.sub(r'^```json\s*|\s*```$', '', intent_response).strip()
    intent_output = json.loads(intent_response)
    
    return (
        intent_output.get("intents", []),
        intent_output.get("user_queries", {}),
        intent_output.get("follow_up_message", "")
    )


def get_agent_description(agent_name: str) -> dict:
    """获取Agent描述信息"""
    descriptions = {
        "DocGenAssistant": {
            "icon": "📚",
            "name": "教案生成助手",
            "skills": "教案生成、课本检索、Word模板",
            "port": conf.docgen_agent_port
        },
        "QuestionAssistant": {
            "icon": "📝",
            "name": "智能出题助手",
            "skills": "智能出题、题库检索、针对性练习",
            "port": conf.question_agent_port
        },
        "GradingAssistant": {
            "icon": "✅",
            "name": "作业批改助手",
            "skills": "OCR识别、答案比对、自动评分",
            "port": conf.grading_agent_port
        },
        "AnalysisAssistant": {
            "icon": "📊",
            "name": "学情分析助手",
            "skills": "学情分析、薄弱点分析、成绩统计、班级学情分析",
            "port": conf.analysis_agent_port
        }
    }
    return descriptions.get(agent_name, {})


# ============= 主界面布局 =============

# 页面标题
st.markdown("""
<div class="main-header">
    <h1>📚 英语教学智能助手</h1>
    <p>支持教案生成 | 智能出题 | 作业批改 | 学情分析</p>
</div>
""", unsafe_allow_html=True)

# 两栏布局
col1, col2 = st.columns([2, 1])

# 左侧：对话区域
with col1:
    st.subheader("💬 对话")
    
    # 文件上传（作业图片）
    uploaded_file = st.file_uploader(
        "📎 上传作业图片（用于批改）",
        type=["jpg", "jpeg", "png"],
        help="支持JPG、JPEG、PNG格式的作业图片"
    )
    
    if uploaded_file:
        # 保存上传的文件（使用绝对路径，确保 A2A Agent 能找到）
        upload_dir = os.path.abspath(os.path.join(conf.upload_dir, "homework"))
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success(f"✅ 文件已上传: {uploaded_file.name}")
        st.session_state.uploaded_homework = file_path
    
    # 显示对话历史
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # 用户输入
    if prompt := st.chat_input("请输入您的问题..."):
        # 显示用户消息
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.conversation_history += f"\nUser: {prompt}"
        
        # 处理用户输入
        with st.spinner("正在分析您的需求..."):
            try:
                # 意图识别
                intents, user_queries, follow_up_message = intent_agent(prompt)
                # 判断是否有已上传的作业图片
                has_uploaded = hasattr(st.session_state, 'uploaded_homework') and st.session_state.uploaded_homework
                
                # 如果有上传文件且用户提到批改相关词，确保 grading 意图存在
                grading_keywords = ['批改', '改作业', '批阅', '评分', '打分']
                if has_uploaded and any(kw in prompt for kw in grading_keywords) and "grading" not in intents:
                    intents.append("grading")
                    follow_up_message = ""  # 清除追问
                
                response = None  # 初始化为 None，表示还没有确定响应
                
                # 处理超出范围的意图
                if "out_of_scope" in intents:
                    response = follow_up_message
                # 需要追问 —— 但如果是批改意图且已上传文件，跳过追问直接路由
                elif follow_up_message:
                    if "grading" in intents and has_uploaded:
                        pass  # 有图片，不用追问，继续路由到Agent
                    else:
                        response = follow_up_message
                
                # 如果还没有确定响应，走 Agent 路由
                if response is None:
                    responses = []
                    routed_agents = []
                    
                    for intent in intents:
                        # 意图到Agent映射
                        intent_agent_map = {
                            "lesson_plan": "DocGenAssistant",
                            "question": "QuestionAssistant",
                            "grading": "GradingAssistant",
                            "analysis": "AnalysisAssistant"
                        }
                        
                        agent_name = intent_agent_map.get(intent)
                        if agent_name:
                            query = user_queries.get(intent, prompt)
                            # 教案生成：必须用用户原话。意图模型改写常会丢掉「七年级下册第一单元」等关键信息，
                            # 导致 DocGen 解析不到单元、RAG 过滤错误或检索词不准，表现为「不走知识库」。
                            if intent == "lesson_plan":
                                query = prompt
                            
                            # 获取Agent
                            agent = st.session_state.agent_network.get_agent(agent_name)
                            
                            # 构建消息内容
                            chat_history = '\n'.join(
                                st.session_state.conversation_history.split("\n")[-7:-1]
                            ) + f'\nUser: {query}'
                            
                            # 如果是批改意图且有上传文件，将文件路径以JSON格式传给Agent
                            if intent == "grading" and hasattr(st.session_state, 'uploaded_homework') and st.session_state.uploaded_homework:
                                grading_request = json.dumps({
                                    "image_path": st.session_state.uploaded_homework,
                                    "query": query
                                }, ensure_ascii=False)
                                chat_history = grading_request
                            
                            message = Message(
                                content=TextContent(text=chat_history),
                                role=MessageRole.USER
                            )
                            task = Task(id=f"task-{uuid.uuid4()}", message=message.to_dict())
                            
                            # 调用Agent
                            raw_response = asyncio.run(agent.send_task_async(task))
                            
                            # 处理响应
                            if raw_response.status.state == 'completed':
                                agent_result = raw_response.artifacts[0]['parts'][0]['text']
                            else:
                                # 提取详细错误信息
                                err_msg = '处理失败'
                                if raw_response.status.message:
                                    if isinstance(raw_response.status.message, dict):
                                        err_msg = raw_response.status.message.get('content', {}).get('text', str(raw_response.status.message))
                                    else:
                                        err_msg = str(raw_response.status.message)
                                logger.error(f"Agent {agent_name} 返回失败: state={raw_response.status.state}, msg={err_msg}")
                                agent_result = f"处理失败: {err_msg}"
                            
                            responses.append(agent_result)
                            routed_agents.append(agent_name)
                        else:
                            responses.append(f"暂不支持该意图: {intent}")
                    
                    response = "\n\n".join(responses)
                    if routed_agents:
                        logger.info(f"路由到Agent: {routed_agents}")
                
                st.session_state.conversation_history += f"\nAssistant: {response}"
                
                # 显示助手响应
                with st.chat_message("assistant"):
                    st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
                
            except json.JSONDecodeError:
                error_msg = "意图识别失败，请重新描述您的需求。"
                with st.chat_message("assistant"):
                    st.markdown(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
            except Exception as e:
                logger.error(f"处理用户输入异常: {type(e).__name__}: {e}")
                error_msg = f"处理失败: {type(e).__name__}: {str(e)}"
                with st.chat_message("assistant"):
                    st.markdown(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})

# 右侧：Agent Card
with col2:
    st.subheader("🛠️ Agent 状态")
    
    for agent_name in st.session_state.agent_network.agents.keys():
        info = get_agent_description(agent_name)
        agent_url = st.session_state.agent_urls.get(agent_name, "")
        
        with st.expander(f"{info.get('icon', '🤖')} {info.get('name', agent_name)}", expanded=False):
            st.markdown(f"**技能**: {info.get('skills', '-')}")
            st.markdown(f"**端口**: {info.get('port', '-')}")
            st.markdown(f"**地址**: `{agent_url}`")
            st.markdown("**状态**: 🟢 在线")
    
    # 快捷操作
    st.markdown("---")
    st.subheader("⚡ 快捷操作")
    
    if st.button("📚 生成教案", use_container_width=True):
        st.session_state.messages.append({
            "role": "user",
            "content": "请帮我生成一份高一英语教案"
        })
        st.rerun()
    
    if st.button("📝 智能出题", use_container_width=True):
        st.session_state.messages.append({
            "role": "user",
            "content": "请帮我出一套语法练习题"
        })
        st.rerun()
    
    if st.button("✅ 批改作业", use_container_width=True):
        st.session_state.messages.append({
            "role": "user",
            "content": "请帮我批改上传的作业"
        })
        st.rerun()
    
    if st.button("📊 学情分析", use_container_width=True):
        st.session_state.messages.append({
            "role": "user",
            "content": "请分析学生的学习情况"
        })
        st.rerun()
    
    if st.button("🏫 班级学情分析", use_container_width=True):
        st.session_state.messages.append({
            "role": "user",
            "content": "请分析高一(1)班的班级学情"
        })
        st.rerun()
    
    # 清空对话
    st.markdown("---")
    if st.button("🗑️ 清空对话", use_container_width=True):
        st.session_state.messages = []
        st.session_state.conversation_history = ""
        st.rerun()

# 页脚
st.markdown("---")
st.markdown(
    '<div class="footer">Powered by A2A | 英语教学智能助手系统 | 基于多智能体协作</div>',
    unsafe_allow_html=True
)
