# -*- coding: utf-8 -*-
"""
英语教学助手 - 配置文件
"""
import os
from dotenv import load_dotenv

load_dotenv()

# 绕过系统代理（Clash等）对 localhost 的拦截，避免 MCP SSE 连接 502 错误
# httpx 优先读取 HTTP_PROXY/HTTPS_PROXY，仅 NO_PROXY 不够，需要同时清除代理
for _proxy_key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]:
    os.environ.pop(_proxy_key, None)
os.environ["NO_PROXY"] = "localhost,127.0.0.1,0.0.0.0"
os.environ["no_proxy"] = "localhost,127.0.0.1,0.0.0.0"


class Config:
    """系统配置类"""
    
    # LLM 配置 - 通义千问
    model_name: str = os.getenv("MODEL_NAME", "qwen3-max")
    api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    base_url: str = os.getenv("BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    
    # 数据库配置
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "3306"))
    db_user: str = os.getenv("DB_USER", "root")
    db_password: str = os.getenv("DB_PASSWORD", "")
    db_name: str = os.getenv("DB_NAME", "english_teaching_assistant")
    
    # Agent 端口配置
    main_port: int = 8000
    docgen_agent_port: int = 5010
    question_agent_port: int = 5011
    grading_agent_port: int = 5012
    analysis_agent_port: int = 5013
    
    # MCP 端口配置
    mcp_docgen_port: int = 8010
    mcp_question_port: int = 8011
    mcp_grading_port: int = 8012
    mcp_analysis_port: int = 8013
    
    # 文件路径配置
    upload_dir: str = os.getenv("UPLOAD_DIR", "./uploads")
    template_dir: str = os.getenv("TEMPLATE_DIR", "./templates")
    log_dir: str = os.getenv("LOG_DIR", "./logs")
    output_dir: str = os.getenv("OUTPUT_DIR", "./output")
    
    # Milvus 向量数据库配置
    milvus_host: str = os.getenv("MILVUS_HOST", "localhost")
    milvus_port: int = int(os.getenv("MILVUS_PORT", "19530"))
    milvus_collection: str = os.getenv("MILVUS_COLLECTION", "textbook_chunks")
    
    # Embedding 模型配置（本地路径）
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "./models/bge-m3")
    reranker_model: str = os.getenv("RERANKER_MODEL", "./models/bge-reranker-large")
    
    # PaddleOCR 模型路径（需使用纯ASCII路径，避免中文用户名导致加载失败）
    ocr_det_model_dir: str = os.getenv("OCR_DET_MODEL_DIR", "D:/paddleocr_models/det/ch/ch_PP-OCRv4_det_infer")
    ocr_rec_model_dir: str = os.getenv("OCR_REC_MODEL_DIR", "D:/paddleocr_models/rec/ch/ch_PP-OCRv4_rec_infer")
    ocr_cls_model_dir: str = os.getenv("OCR_CLS_MODEL_DIR", "D:/paddleocr_models/cls/ch_ppocr_mobile_v2.0_cls_infer")
    
    @property
    def db_url(self) -> str:
        """获取数据库连接URL"""
        return f"mysql+pymysql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    def get_agent_url(self, agent_name: str) -> str:
        """获取Agent URL"""
        port_map = {
            "DocGenAssistant": self.docgen_agent_port,
            "QuestionAssistant": self.question_agent_port,
            "GradingAssistant": self.grading_agent_port,
            "AnalysisAssistant": self.analysis_agent_port,
        }
        port = port_map.get(agent_name, 8000)
        return f"http://localhost:{port}"
