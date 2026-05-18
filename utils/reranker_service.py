# -*- coding: utf-8 -*-
"""
重排序服务 - 使用 BGE-Reranker-Large 进行二阶段精排

架构:
第一阶段: BGE-M3 混合检索 (快速召回 top-k)
第二阶段: BGE-Reranker-Large (精细重排序)
"""
from typing import List, Dict, Any, Tuple
from create_logger import logger


class BGERerankerService:
    """BGE-Reranker-Large 重排序服务"""
    
    def __init__(self, model_name: str = "./models/bge-reranker-large"):
        """
        初始化重排序模型
        
        Args:
            model_name: 模型名称或本地路径
        """
        self.model_name = model_name
        self._reranker = None
    
    @property
    def reranker(self):
        """延迟加载 Reranker 模型"""
        if self._reranker is None:
            from FlagEmbedding import FlagReranker
            
            logger.info(f"正在加载 Reranker 模型: {self.model_name}")
            self._reranker = FlagReranker(
                self.model_name,
                use_fp16=True
            )
            logger.info("Reranker 模型加载完成")
        return self._reranker
    
    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        content_key: str = "parent_content",
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        对检索结果进行重排序
        
        Args:
            query: 用户查询
            documents: 第一阶段检索结果列表
            content_key: 用于重排序的文本字段名（使用 parent_content 获得更多上下文）
            top_k: 返回前 k 个结果
            
        Returns:
            重排序后的结果列表（附带 rerank_score）
        """
        if not documents:
            return []
        
        # 构建 query-document 配对
        pairs = []
        for doc in documents:
            text = doc.get(content_key) or doc.get("content", "")
            pairs.append([query, text])
        
        # 计算重排序分数
        logger.info(f"[Reranker] 正在对 {len(pairs)} 条结果重排序...")
        scores = self.reranker.compute_score(pairs, normalize=True)
        
        # 如果只有一个结果，compute_score 返回单个 float
        if isinstance(scores, (int, float)):
            scores = [scores]
        
        # 将分数附加到文档并排序
        scored_docs = []
        for doc, score in zip(documents, scores):
            doc_copy = doc.copy()
            doc_copy["rerank_score"] = float(score)
            scored_docs.append(doc_copy)
        
        # 按重排序分数降序排列
        scored_docs.sort(key=lambda x: x["rerank_score"], reverse=True)
        
        # 返回 top_k
        result = scored_docs[:top_k]
        
        if result:
            logger.info(f"[Reranker] 重排序完成，最高分: {result[0]['rerank_score']:.4f}，最低分: {result[-1]['rerank_score']:.4f}")
        
        return result


# 单例模式
_reranker_instance = None


def get_reranker_service(model_name: str = "./models/bge-reranker-large") -> BGERerankerService:
    """获取 Reranker 服务的便捷函数（单例）"""
    global _reranker_instance
    if _reranker_instance is None:
        _reranker_instance = BGERerankerService(model_name=model_name)
    return _reranker_instance
