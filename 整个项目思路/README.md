# 英语教学智能助手

> 基于 Agent2Agent (A2A) 与 MCP (Model Context Protocol) 的智能英语教学助手系统

## 功能特性

- 📚 **教案生成** - 根据课本内容自动生成教学设计
- 📝 **智能出题** - 基于学生薄弱点生成针对性练习题
- ✅ **作业批改** - OCR识别 + 自动评分 + 错题分析
- 📊 **学情分析** - 学习数据统计 + 个性化建议

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit 前端 (8501)                     │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    主应用 API (8000)                         │
│              意图识别 + Agent 路由 + 结果汇总                  │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    A2A Agent 层                              │
│  教案Agent(5010) | 出题Agent(5011) | 批改Agent(5012) | 学情Agent(5013) │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    MCP 工具层                                │
│   MCP-DocGen(8010) | MCP-Question(8011) | MCP-Grading(8012) | MCP-Analysis(8013) │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    MySQL 数据库                              │
└─────────────────────────────────────────────────────────────┘
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入 API Key 和数据库配置
```

### 3. 初始化数据库

```bash
# 登录 MySQL 执行建表语句
mysql -u root -p < sql/schema.sql
mysql -u root -p < sql/sample_data.sql
```

### 4. 启动服务

**方式一：一键启动（Windows）**
```bash
start_all.bat
```

**方式二：手动启动**
```bash
# 1. 启动 MCP 服务
python -m mcp_server.mcp_docgen_server    # 端口 8010
python -m mcp_server.mcp_question_server  # 端口 8011
python -m mcp_server.mcp_grading_server   # 端口 8012
python -m mcp_server.mcp_analysis_server  # 端口 8013

# 2. 启动 A2A Agent 服务
python -m a2a_server.docgen_server    # 端口 5010
python -m a2a_server.question_server  # 端口 5011
python -m a2a_server.grading_server   # 端口 5012
python -m a2a_server.analysis_server  # 端口 5013

# 3. 启动主应用
python main.py  # 端口 8000

# 4. 启动前端
streamlit run app.py  # 端口 8501
```

### 5. 访问系统

打开浏览器访问: http://localhost:8501

## 项目结构

```
EnglishTeachingAssistant/
├── app.py                 # Streamlit 前端
├── main.py                # 后端主服务
├── main_prompts.py        # 提示词模板
├── config.py              # 配置文件
├── create_logger.py       # 日志工具
├── requirements.txt       # 依赖列表
├── start_all.bat          # Windows 启动脚本
├── .env.example           # 环境变量模板
│
├── a2a_server/            # A2A Agent 服务
│   ├── docgen_server.py   # 教案生成 Agent
│   ├── question_server.py # 出题 Agent
│   ├── grading_server.py  # 批改 Agent
│   └── analysis_server.py # 学情分析 Agent
│
├── mcp_server/            # MCP 工具服务
│   ├── mcp_docgen_server.py
│   ├── mcp_question_server.py
│   ├── mcp_grading_server.py
│   └── mcp_analysis_server.py
│
├── utils/                 # 工具函数
│   └── db_helper.py       # 数据库助手
│
└── sql/                   # 数据库
    ├── schema.sql         # 建表语句
    └── sample_data.sql    # 示例数据
```

## 技术栈

- **前端**: Streamlit
- **后端**: FastAPI + python-a2a + MCP
- **LLM**: LangChain + OpenAI
- **数据库**: MySQL + SQLAlchemy
- **向量检索**: FAISS

## License

MIT
