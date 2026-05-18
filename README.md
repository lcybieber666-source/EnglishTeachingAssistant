# EnglishTeachingAssistant

一个面向英语教学场景的本地化助手项目，包含教案生成、题目生成、作业批改和教学分析等能力。

## 主要功能

- `app.py` / `main.py`：主入口与服务编排
- `a2a_server/`：各教学能力对应的 Agent 服务
- `mcp_server/`：MCP 服务封装
- `scripts/`：索引构建、教案生成与测试脚本
- `templates/`：教案模板与文本模板
- `utils/`：数据库、向量检索、PDF 处理、重排与文档生成工具

## 环境配置

1. 复制 `.env.example` 为 `.env`
2. 按需填写以下配置：
   - `DASHSCOPE_API_KEY`
   - MySQL 连接信息
   - Milvus 连接信息
   - 本地模型目录
   - PaddleOCR 模型目录

## 安装依赖

```bash
pip install -r requirements.txt
```

## 说明

为了便于公开托管，以下内容未纳入仓库版本控制：

- 本地模型文件 `models/`
- 运行日志 `logs/`
- 生成结果 `output/`
- 上传与样例作业图片
- 本地缓存、编译产物和 IDE 配置

如需完整运行项目，请在本地自行准备上述资源。
