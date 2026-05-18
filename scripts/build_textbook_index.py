# -*- coding: utf-8 -*-
"""
教材向量化入库脚本（结构感知版）

流程:
1. PDF 增强提取（PyMuPDF sort=True + 文本清洗，或 PP-StructureV2 版面分析）
2. 教材结构感知切分（Unit / Section / Activity / Grammar / Vocabulary）
3. BGE-M3 稠密+稀疏 向量化
4. 删除旧集合 → 写入 Milvus

使用方法:
    # 默认模式（PyMuPDF 增强提取）
    python scripts/build_textbook_index.py --pdf "data/七年级下册.pdf" --drop

    # PP-StructureV2 版面分析模式（更精准但较慢）
    python scripts/build_textbook_index.py --pdf "data/七年级下册.pdf" --drop --use-layout
"""
import os
import sys
import argparse
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.pdf_processor import PDFProcessor
from utils.text_chunker import create_textbook_chunker
from utils.embedding_service import get_embedding_service
from utils.milvus_client import get_milvus_client
from create_logger import logger


def build_textbook_index(
    pdf_path: str,
    collection_name: str = "textbook_chunks",
    milvus_host: str = "localhost",
    milvus_port: int = 19530,
    drop_if_exists: bool = True,
    batch_size: int = 10,
    use_layout: bool = False,
    use_ocr: bool = False,
):
    logger.info("=" * 60)
    logger.info("教材向量化入库开始（结构感知版）")
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # 步骤 1: PDF 文本提取 + 清洗
    # ------------------------------------------------------------------
    mode_desc = "PP-StructureV2 版面分析" if use_layout else ("PaddleOCR" if use_ocr else "PyMuPDF 增强提取")
    logger.info(f"\n[步骤 1/4] PDF 文本提取 ({mode_desc})")

    processor = PDFProcessor(use_gpu=False)
    pages = processor.process_pdf_by_page(
        pdf_path, use_ocr=use_ocr, use_layout=use_layout,
    )

    non_empty = [p for p in pages if p["content"].strip()]
    logger.info(f"共提取 {len(pages)} 页，其中 {len(non_empty)} 页有内容")

    # ------------------------------------------------------------------
    # 步骤 2: 教材结构感知切分
    # ------------------------------------------------------------------
    logger.info("\n[步骤 2/4] 教材结构感知切分")

    chunker = create_textbook_chunker()
    source = os.path.basename(pdf_path)
    chunks = chunker.chunk_textbook(pages, source=source)

    logger.info(f"共生成 {len(chunks)} 个语义 chunk")

    # 打印切分统计
    content_types = {}
    units = set()
    for c in chunks:
        ct = c["metadata"].get("content_type", "unknown")
        content_types[ct] = content_types.get(ct, 0) + 1
        u = c["metadata"].get("unit", 0)
        if u > 0:
            units.add(u)

    logger.info(f"  覆盖 Unit: {sorted(units) if units else '无'}")
    for ct, count in sorted(content_types.items()):
        logger.info(f"  {ct}: {count} 个 chunk")

    # ------------------------------------------------------------------
    # 步骤 3: BGE-M3 向量化
    # ------------------------------------------------------------------
    logger.info("\n[步骤 3/4] BGE-M3 向量化")

    embedding_service = get_embedding_service()
    all_dense_vecs = []
    all_sparse_vecs = []

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c["content"] for c in batch]

        logger.info(f"编码第 {i+1} - {min(i+batch_size, len(chunks))} / {len(chunks)} ...")
        result = embedding_service.encode(texts)

        all_dense_vecs.extend(result["dense_vecs"].tolist())
        all_sparse_vecs.extend(result["lexical_weights"])

    logger.info(f"向量化完成，共 {len(all_dense_vecs)} 个向量")

    # ------------------------------------------------------------------
    # 步骤 4: 写入 Milvus（先删旧集合）
    # ------------------------------------------------------------------
    logger.info("\n[步骤 4/4] 写入 Milvus")

    milvus_client = get_milvus_client(
        host=milvus_host, port=milvus_port, collection_name=collection_name,
    )

    if drop_if_exists:
        milvus_client.drop_collection()

    milvus_client.create_collection(drop_if_exists=False)

    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i:i + batch_size]
        batch_dense = all_dense_vecs[i:i + batch_size]
        batch_sparse = all_sparse_vecs[i:i + batch_size]

        logger.info(f"插入第 {i+1} - {min(i+batch_size, len(chunks))} / {len(chunks)} ...")
        milvus_client.insert(batch_chunks, batch_dense, batch_sparse)

    milvus_client.load()

    logger.info("\n" + "=" * 60)
    logger.info("教材向量化入库完成！")
    logger.info(f"  PDF:       {pdf_path}")
    logger.info(f"  提取模式:  {mode_desc}")
    logger.info(f"  页数:      {len(pages)}")
    logger.info(f"  Chunk 数:  {len(chunks)}")
    logger.info(f"  集合:      {collection_name}")
    logger.info(f"  Units:     {sorted(units) if units else '无'}")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="教材向量化入库脚本（结构感知版）")
    parser.add_argument("--pdf", type=str, required=True, help="PDF 文件路径")
    parser.add_argument("--collection", type=str, default="textbook_chunks", help="Milvus 集合名称")
    parser.add_argument("--host", type=str, default="localhost", help="Milvus 主机")
    parser.add_argument("--port", type=int, default=19530, help="Milvus 端口")
    parser.add_argument("--drop", action="store_true", default=True, help="删除已存在的集合（默认开启）")
    parser.add_argument("--no-drop", action="store_false", dest="drop", help="不删除已存在的集合")
    parser.add_argument("--batch-size", type=int, default=10, help="批处理大小")
    parser.add_argument("--use-layout", action="store_true", help="使用 PP-StructureV2 版面分析")
    parser.add_argument("--use-ocr", action="store_true", help="使用 PaddleOCR 识别")

    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        logger.error(f"PDF 文件不存在: {args.pdf}")
        sys.exit(1)

    build_textbook_index(
        pdf_path=args.pdf,
        collection_name=args.collection,
        milvus_host=args.host,
        milvus_port=args.port,
        drop_if_exists=args.drop,
        batch_size=args.batch_size,
        use_layout=args.use_layout,
        use_ocr=args.use_ocr,
    )


if __name__ == "__main__":
    main()
