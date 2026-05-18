# -*- coding: utf-8 -*-
"""
教案生成 Agent - A2A Server

端口: 5010
功能: 接收教案生成请求，调用 MCP 工具完成 RAG 检索、LLM 生成、Word 导出
"""
import os
import sys
import asyncio
import json
from typing import Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_a2a import A2AServer, AgentCard, AgentSkill, Message, TextContent, MessageRole, Task, TaskStatus, TaskState
from langchain_openai import ChatOpenAI
from mcp import ClientSession
from mcp.client.sse import sse_client

from config import Config
from create_logger import logger

conf = Config()


# Agent Card 定义
agent_card = AgentCard(
    name="DocGenAssistant",
    description="教案生成智能助手，支持根据课本内容生成高质量教案并导出 Word 文档",
    skills=[
        AgentSkill(
            name="lesson_plan_generation",
            description="根据教学要求生成详细的教案并导出 Word（支持指定年级、单元、主题）"
        ),
        AgentSkill(
            name="textbook_search",
            description="检索课本内容（需要 query）"
        )
    ],
    url=f"http://localhost:{conf.docgen_agent_port}"
)


class DocGenServer(A2AServer):
    """教案生成Agent服务"""
    
    def __init__(self):
        super().__init__(agent_card=agent_card)
        self.llm = ChatOpenAI(
            model=conf.model_name,
            api_key=conf.api_key,
            base_url=conf.base_url,
            temperature=0.3
        )
        self.mcp_url = f"http://localhost:{conf.mcp_docgen_port}/sse"
    
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
                logger.warning(f"MCP SSE 连接关闭时异常（已忽略）: {e}")
                return mcp_result
            logger.error(f"MCP调用失败: {e}")
            return json.dumps({"error": str(e)})
        return mcp_result
    
    def parse_request(self, text: str) -> Dict[str, Any]:
        """解析用户请求，提取年级、单元、上下册等信息"""
        import re
        
        params = {
            "grade": "七年级",
            "semester": "",  # 上册/下册
            "unit": "Unit 1",
            "topic": None,
            "requirements": None
        }

        # 只解析「最后一次」用户表述，避免多轮对话里历史中的单元号被 re.search 先匹配到
        parse_text = text.strip()
        if "User:" in parse_text:
            parse_text = parse_text.rsplit("User:", 1)[-1].strip()
        
        _cn_digit = {
            "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
        }
        
        # 提取年级
        grade_match = re.search(r'(七|八|九|高一|高二|高三|[789])[年]?级', parse_text)
        if grade_match:
            grade_map = {"七": "七年级", "八": "八年级", "九": "九年级", 
                        "7": "七年级", "8": "八年级", "9": "九年级",
                        "高一": "高一", "高二": "高二", "高三": "高三"}
            matched = grade_match.group(1)
            params["grade"] = grade_map.get(matched, f"{matched}年级")
        
        # 提取上册/下册
        semester_match = re.search(r'(上|下)[册]', parse_text)
        if semester_match:
            params["semester"] = f"{semester_match.group(1)}册"
        
        # 提取单元：阿拉伯数字 / 中文「第一单元」/ Unit N
        unit_num = None
        m_ar = re.search(r'[Uu]nit\s*(\d+)', parse_text)
        m_cn = re.search(r'第([一二三四五六七八九十两\d]+)单元', parse_text)
        m_plain = re.search(r'第\s*(\d+)\s*单元', parse_text)
        m_alt = re.search(r'单元\s*(\d+)', parse_text)
        if m_ar:
            unit_num = int(m_ar.group(1))
        elif m_plain:
            unit_num = int(m_plain.group(1))
        elif m_alt:
            unit_num = int(m_alt.group(1))
        elif m_cn:
            g = m_cn.group(1)
            if g.isdigit():
                unit_num = int(g)
            elif g in _cn_digit:
                unit_num = _cn_digit[g]
            elif len(g) == 2 and g[0] == "十" and g[1] in _cn_digit:
                unit_num = 10 + _cn_digit[g[1]]
        if unit_num is not None:
            params["unit"] = f"Unit {unit_num}"
        
        # 提取主题（如果有）
        topic_match = re.search(r'主题[：:]\s*(.+?)(?:\s|$)', parse_text)
        if topic_match:
            params["topic"] = topic_match.group(1)
        
        return params
    
    async def generate_lesson_plan(self, query: str) -> str:
        """生成教案的完整流程"""
        logger.info(f"[DocGenAgent] 开始处理请求: {query[:100]}...")
        
        # 1. 解析请求参数
        params = self.parse_request(query)
        logger.info(f"[DocGenAgent] 解析参数: {params}")
        
        # 2. RAG 检索课本内容（使用 metadata 过滤提高精度）
        logger.info(f"[DocGenAgent] 步骤1: RAG 检索课本内容")
        search_query = f"{params['grade']}{params['semester']} {params['unit']} {params.get('topic', '')}"

        import re as _re
        unit_num_match = _re.search(r"(\d+)", params["unit"])
        # 拼接教材 UNIT 标题与 Big Question，与向量库中 enhanced_content 对齐，提高召回
        try:
            from utils.text_chunker import UNIT_INFO
            if unit_num_match:
                _un = int(unit_num_match.group(1))
                _info = UNIT_INFO.get(_un)
                if _info:
                    search_query = (
                        f"{search_query.strip()} {_info['title']} {_info['big_question']}"
                    )
        except Exception:
            pass

        mcp_params = {"query": search_query, "limit": 5}
        if unit_num_match:
            mcp_params["unit"] = int(unit_num_match.group(1))

        textbook_result = await self.call_mcp_tool("search_textbook", mcp_params)
        
        # 解析检索结果
        sections: list = []
        try:
            textbook_data = json.loads(textbook_result)
            sections = textbook_data.get("sections", [])
            if sections:
                # 合并检索到的内容
                textbook_content = "\n\n".join([
                    f"【片段{i+1}】\n{s.get('parent_content', s.get('content', ''))}"
                    for i, s in enumerate(sections[:3])
                ])
            else:
                textbook_content = "（未检索到相关课本内容，将根据通用知识生成教案）"
        except Exception:
            textbook_content = textbook_result
        
        logger.info(f"[DocGenAgent] 检索到 {len(sections)} 个相关片段")
        
        # 3. 调用 MCP 生成教案
        logger.info(f"[DocGenAgent] 步骤2: 调用 LLM 生成教案并导出 Word")
        gen_result = await self.call_mcp_tool("generate_lesson_plan", {
            "grade": params["grade"],
            "unit": params["unit"],
            "topic": params.get("topic") or "",
            "textbook_content": textbook_content or "",
            "requirements": (params.get("requirements") or query) or ""
        })
        
        # 4. 格式化输出
        try:
            result_data = json.loads(gen_result)
            if result_data.get("status") == "success":
                word_path = result_data.get("word_path", "")
                lesson_plan = result_data.get("lesson_plan", {})
                
                # 构建友好的输出
                output = f"""## 教案生成完成！

### 基本信息
- **标题**: {lesson_plan.get('title', '')}
- **年级**: {lesson_plan.get('grade', '')}
- **单元**: {lesson_plan.get('unit', '')}
- **课题**: {lesson_plan.get('topic', '')}

### 教学目标
"""
                objectives = lesson_plan.get('objectives', [])
                if objectives:
                    for obj in objectives:
                        output += f"- {obj}\n"
                
                output += f"""
### 教学重难点
- **重点**: {lesson_plan.get('key_points', '')}
- **难点**: {lesson_plan.get('difficult_points', '')}

### Word 文档
📄 **已生成**: {word_path}

---
教案已保存为 Word 文档，请在上述路径查看完整内容。
"""
                return output
            else:
                return f"教案生成失败: {result_data.get('error', '未知错误')}"
        except:
            return gen_result
            
    def handle_message(self, message: Message) -> Message:
        """处理 send_message 请求（支持直接在前端调用测试）"""
        text = message.content.text if hasattr(message.content, 'text') else str(message.content)
        logger.info(f"[DocGenAgent] 收到普通消息: {text[:100]}...")
        
        async def _run_with_timeout():
            return await asyncio.wait_for(self.generate_lesson_plan(text), timeout=300)
        
        result = asyncio.run(_run_with_timeout())
        
        return Message(
            content=TextContent(text=result),
            role=MessageRole.AGENT,
            parent_message_id=getattr(message, 'message_id', None),
            conversation_id=getattr(message, 'conversation_id', None)
        )
    
    def handle_task(self, task: Task) -> Task:
        """处理任务"""
        try:
            # 提取消息内容，兼容不同格式
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
            
            logger.info(f"[DocGenAgent] 收到任务: {text[:100]}...")
            
            # 生成教案加超时控制，防止死锁
            async def _run_with_timeout():
                return await asyncio.wait_for(self.generate_lesson_plan(text), timeout=300)
                
            result = asyncio.run(_run_with_timeout())
            
            # 设置响应
            task.artifacts = [{"parts": [{"type": "text", "text": result}]}]
            task.status = TaskStatus(state=TaskState.COMPLETED)
            
            logger.info("[DocGenAgent] 教案生成完成")
            
        except Exception as e:
            logger.error(f"[DocGenAgent] 处理失败: {e}")
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message={"content": {"text": f"处理失败: {str(e)}"}}
            )
        
        return task


def main():
    """启动服务"""
    from flask import Flask
    app = Flask(__name__)
    server = DocGenServer()
    server.setup_routes(app)
    logger.info(f"教案生成Agent服务启动在端口 {conf.docgen_agent_port}")
    app.run(host="0.0.0.0", port=conf.docgen_agent_port)


if __name__ == "__main__":
    main()
