# -*- coding: utf-8 -*-
"""
Embedding 服务 - 使用 BGE-M3 生成稠密和稀疏向量

BGE-M3 特点:
- 多语言支持
- 同时生成稠密向量和稀疏向量（ColBERT + BM25 like）
- 最大 8192 tokens
"""
import os
from typing import List, Dict, Any, Tuple
import numpy as np

from create_logger import logger


class BGEM3EmbeddingService:
    """BGE-M3 Embedding 服务"""
    
    def __init__(self, model_name: str = "./models/bge-m3", use_fp16: bool = True, device: str = None):
        """
        初始化 BGE-M3 模型
        
        Args:
            model_name: 模型名称或路径
            use_fp16: 是否使用 FP16 加速
            device: 设备，None 则自动选择
        """
        self.model_name = model_name
        self.use_fp16 = use_fp16
        self.device = device
        self._model = None
    
    @property
    def model(self):
        """延迟加载模型"""
        if self._model is None:
            from FlagEmbedding import BGEM3FlagModel
            
            logger.info(f"正在加载 BGE-M3 模型: {self.model_name}")
            self._model = BGEM3FlagModel(
                self.model_name,
                use_fp16=self.use_fp16,
                device=self.device
            )
            logger.info("BGE-M3 模型加载完成")
        return self._model
    
    def encode(self, texts: List[str], batch_size: int = 12, max_length: int = 8192) -> Dict[str, Any]:
        """
        生成稠密和稀疏向量
        
        Args:
            texts: 文本列表
            batch_size: 批处理大小
            max_length: 最大长度
            
        Returns:
            包含 dense_vecs 和 lexical_weights 的字典
        """
        if not texts:
            return {"dense_vecs": [], "lexical_weights": []}
        
        logger.info(f"正在编码 {len(texts)} 个文本...")
        
        output = self.model.encode(
            texts,
            batch_size=batch_size,
            max_length=max_length,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False  # ColBERT 向量太大，暂不使用
        )
        
        logger.info(f"编码完成，稠密向量维度: {output['dense_vecs'].shape}")
        
        return {
            "dense_vecs": output['dense_vecs'],
            "lexical_weights": output['lexical_weights']
        }
    
    def encode_single(self, text: str) -> Tuple[np.ndarray, Dict[str, float]]:
        """
        编码单个文本
        
        Args:
            text: 文本
            
        Returns:
            (稠密向量, 稀疏权重字典)
        """
        result = self.encode([text])
        return result['dense_vecs'][0], result['lexical_weights'][0]
    
    def get_dense_dim(self) -> int:
        """获取稠密向量维度"""
        return 1024  # BGE-M3 固定维度
    
    def sparse_to_dict(self, lexical_weights: Dict[str, float]) -> Dict[int, float]:
        """
        将词汇权重转换为 token_id -> weight 的格式（用于 Milvus 稀疏向量）
        
        Args:
            lexical_weights: 词汇权重字典
            
        Returns:
            token_id -> weight 字典
        """
        # BGE-M3 返回的 lexical_weights 已经是 {token_id: weight} 格式
        if isinstance(lexical_weights, dict):
            # 如果 key 是字符串数字，转换为 int
            return {int(k) if isinstance(k, str) and k.isdigit() else k: v 
                    for k, v in lexical_weights.items()}
        return lexical_weights


class EmbeddingServiceFactory:
    """Embedding 服务工厂"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls, model_name: str = "./models/bge-m3") -> BGEM3EmbeddingService:
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = BGEM3EmbeddingService(model_name=model_name)
        return cls._instance


def get_embedding_service(model_name: str = "./models/bge-m3") -> BGEM3EmbeddingService:
    """获取 Embedding 服务的便捷函数"""
    return EmbeddingServiceFactory.get_instance(model_name)


if __name__ == "__main__":
    # 测试代码
    print("正在测试 BGE-M3 Embedding 服务...")
    
    service = get_embedding_service()
    
    test_texts = [
        "What is friendship?",
        "友谊是什么？",
        "Unit 1: Making Friends - In this unit, we will learn vocabulary about friendship."
    ]
    
    # 测试批量编码
    result = service.encode(test_texts)
    
    print(f"\n稠密向量形状: {result['dense_vecs'].shape}")
    print(f"稀疏权重数量: {len(result['lexical_weights'])}")
    
    # 显示第一个文本的结果
    print(f"\n第一个文本的稠密向量前10维: {result['dense_vecs'][0][:10]}")
    print(f"第一个文本的稀疏权重（前5个）: {dict(list(result['lexical_weights'][0].items())[:5])}")
    
    # 测试单个编码
    dense, sparse = service.encode_single("Hello world")
    print(f"\n单个编码 - 稠密向量形状: {dense.shape}")
    print(f"单个编码 - 稀疏权重数量: {len(sparse)}")
