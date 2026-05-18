# -*- coding: utf-8 -*-
"""
Milvus 客户端 - 向量数据库操作

功能:
- 创建集合（稠密 + 稀疏向量 + JSON metadata）
- 插入数据
- 混合检索（支持 metadata 过滤）
- 删除集合
"""
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from create_logger import logger


@dataclass
class MilvusConfig:
    """Milvus 配置"""
    host: str = "localhost"
    port: int = 19530
    collection_name: str = "textbook_chunks"
    dense_dim: int = 1024  # BGE-M3 维度


class MilvusClient:
    """Milvus 向量数据库客户端"""

    def __init__(self, config: MilvusConfig = None):
        self.config = config or MilvusConfig()
        self._client = None
        self._collection = None

    def connect(self):
        """连接到 Milvus"""
        from pymilvus import connections

        logger.info(f"正在连接 Milvus: {self.config.host}:{self.config.port}")
        connections.connect(
            alias="default",
            host=self.config.host,
            port=self.config.port,
        )
        logger.info("Milvus 连接成功")

    def drop_collection(self):
        """删除集合"""
        from pymilvus import utility

        name = self.config.collection_name
        if utility.has_collection(name):
            logger.info(f"正在删除集合: {name}")
            utility.drop_collection(name)
            self._collection = None
            logger.info(f"集合已删除: {name}")
        else:
            logger.info(f"集合不存在，无需删除: {name}")

    def create_collection(self, drop_if_exists: bool = False):
        """创建集合"""
        from pymilvus import (
            Collection, FieldSchema, CollectionSchema, DataType, utility,
        )

        name = self.config.collection_name

        if utility.has_collection(name):
            if drop_if_exists:
                logger.info(f"删除已存在的集合: {name}")
                utility.drop_collection(name)
            else:
                logger.info(f"集合已存在: {name}")
                self._collection = Collection(name)
                return

        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=512, is_primary=True),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="parent_id", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="parent_content", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="dense_vector", dtype=DataType.FLOAT_VECTOR, dim=self.config.dense_dim),
            FieldSchema(name="sparse_vector", dtype=DataType.SPARSE_FLOAT_VECTOR),
            FieldSchema(name="metadata", dtype=DataType.JSON),
        ]

        schema = CollectionSchema(
            fields=fields,
            description="Textbook chunks with structural metadata",
        )

        logger.info(f"创建集合: {name}")
        self._collection = Collection(name=name, schema=schema)
        self._create_indexes()
        logger.info(f"集合创建完成: {name}")

    def _create_indexes(self):
        """创建向量索引"""
        # 稠密向量: HNSW
        self._collection.create_index("dense_vector", {
            "metric_type": "IP",
            "index_type": "HNSW",
            "params": {"M": 16, "efConstruction": 256},
        })
        logger.info("稠密向量索引创建完成 (HNSW)")

        # 稀疏向量: SPARSE_INVERTED_INDEX
        self._collection.create_index("sparse_vector", {
            "metric_type": "IP",
            "index_type": "SPARSE_INVERTED_INDEX",
            "params": {"drop_ratio_build": 0.2},
        })
        logger.info("稀疏向量索引创建完成 (SPARSE_INVERTED_INDEX)")

    def insert(self, chunks: List[Dict[str, Any]], dense_vecs: List, sparse_vecs: List):
        """插入数据"""
        if not chunks:
            logger.warning("没有数据需要插入")
            return

        ids = [c["id"] for c in chunks]
        contents = [c["content"][:65000] for c in chunks]
        parent_ids = [c["parent_id"] for c in chunks]
        parent_contents = [c["parent_content"][:65000] for c in chunks]
        metadata_list = [c.get("metadata", {}) for c in chunks]

        sparse_vectors = []
        for sv in sparse_vecs:
            sparse_vectors.append(sv if isinstance(sv, dict) else {})

        data = [ids, contents, parent_ids, parent_contents, dense_vecs, sparse_vectors, metadata_list]

        logger.info(f"正在插入 {len(chunks)} 条数据...")
        self._collection.insert(data)
        self._collection.flush()
        logger.info(f"插入完成，当前集合共 {self._collection.num_entities} 条数据")

    def load(self):
        """加载集合到内存"""
        if self._collection:
            self._collection.load()
            logger.info("集合已加载到内存")

    def hybrid_search(
        self,
        query_dense: List[float],
        query_sparse: Dict[int, float],
        limit: int = 10,
        dense_weight: float = 0.7,
        sparse_weight: float = 0.3,
        expr: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        混合检索（稠密 + 稀疏），支持 metadata 过滤。

        Args:
            expr: Milvus 过滤表达式，如 'metadata["unit"] == 3'
        """
        from pymilvus import AnnSearchRequest, WeightedRanker

        if not self._collection:
            raise RuntimeError("集合未初始化")

        dense_kwargs = {
            "data": [query_dense],
            "anns_field": "dense_vector",
            "param": {"metric_type": "IP", "params": {"ef": 100}},
            "limit": limit,
        }
        sparse_kwargs = {
            "data": [query_sparse],
            "anns_field": "sparse_vector",
            "param": {"metric_type": "IP"},
            "limit": limit,
        }

        if expr:
            dense_kwargs["expr"] = expr
            sparse_kwargs["expr"] = expr

        dense_req = AnnSearchRequest(**dense_kwargs)
        sparse_req = AnnSearchRequest(**sparse_kwargs)

        reranker = WeightedRanker(dense_weight, sparse_weight)

        results = self._collection.hybrid_search(
            reqs=[dense_req, sparse_req],
            rerank=reranker,
            limit=limit,
            output_fields=["id", "content", "parent_id", "parent_content", "metadata"],
        )

        formatted = []
        for hits in results:
            for hit in hits:
                formatted.append({
                    "id": hit.entity.get("id"),
                    "content": hit.entity.get("content"),
                    "parent_id": hit.entity.get("parent_id"),
                    "parent_content": hit.entity.get("parent_content"),
                    "metadata": hit.entity.get("metadata"),
                    "score": hit.score,
                })

        return formatted

    def get_collection(self):
        """获取集合对象"""
        from pymilvus import Collection
        if self._collection is None:
            self._collection = Collection(self.config.collection_name)
        return self._collection


def get_milvus_client(
    host: str = "localhost",
    port: int = 19530,
    collection_name: str = "textbook_chunks",
) -> MilvusClient:
    """获取 Milvus 客户端的便捷函数"""
    config = MilvusConfig(host=host, port=port, collection_name=collection_name)
    client = MilvusClient(config)
    client.connect()
    return client


if __name__ == "__main__":
    import numpy as np

    print("正在测试 Milvus 客户端...")
    try:
        client = get_milvus_client()
        client.create_collection(drop_if_exists=True)

        test_chunks = [{
            "id": "unit1_sectionA_grammar_0",
            "content": "Unit 1: Animal Friends | Section A | grammar\nWh- questions; Adjectives; Plurals",
            "parent_id": "unit1_sectionA",
            "parent_content": "Full section A content...",
            "metadata": {"source": "test", "unit": 1, "section": "A", "content_type": "grammar"},
        }]
        test_dense = [np.random.randn(1024).astype(np.float32).tolist()]
        test_sparse = [{1: 0.5, 100: 0.3, 500: 0.2}]

        client.insert(test_chunks, test_dense, test_sparse)
        client.load()

        results = client.hybrid_search(
            query_dense=np.random.randn(1024).astype(np.float32).tolist(),
            query_sparse={1: 0.5, 100: 0.3},
            limit=5,
            expr='metadata["unit"] == 1',
        )
        print(f"检索结果: {len(results)} 条")
        for r in results:
            print(f"  ID={r['id']}, score={r['score']:.4f}, meta={r['metadata']}")

    except Exception as e:
        print(f"测试失败: {e}")
