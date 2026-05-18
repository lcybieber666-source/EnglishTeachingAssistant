# -*- coding: utf-8 -*-
"""
测试脚本 - 验证 PDF 处理和向量化功能

测试内容:
1. 文本切分功能
2. Embedding 服务（需要 BGE-M3 模型）
3. Milvus 连接（需要 Milvus 服务）
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_text_chunker():
    """测试文本切分"""
    print("\n" + "=" * 60)
    print("测试 1: 文本切分器")
    print("=" * 60)
    
    from utils.text_chunker import create_chunker
    
    test_content = """
    Unit 1: Making Friends
    
    In this unit, we will learn how to make friends and introduce ourselves. 
    Friendship is one of the most important things in our lives. 
    A good friend can help us when we are in trouble and share happiness with us.
    
    Vocabulary:
    - friend: 朋友
    - introduce: 介绍
    - happiness: 幸福
    - trouble: 麻烦
    
    Grammar:
    We use "Nice to meet you" when we meet someone for the first time.
    We can also say "How do you do?" which is more formal.
    
    Listening:
    Listen to the dialogue and answer the questions.
    1. What is the girl's name?
    2. Where does she come from?
    3. What does she like to do?
    
    Reading:
    Read the passage and complete the following tasks.
    Anne Frank was born in Germany in 1929. She was a Jewish girl who lived during World War II.
    """
    
    chunker = create_chunker(
        parent_size=500,
        parent_overlap=50,
        child_size=100,
        child_overlap=50
    )
    
    chunks = chunker.chunk_document("test_doc_1", test_content, {"source": "test"})
    
    print(f"✅ 切分完成，共生成 {len(chunks)} 个子块")
    
    # 验证格式
    if chunks:
        chunk = chunks[0]
        print(f"\n示例子块:")
        print(f"  - id: {chunk['id']}")
        print(f"  - parent_id: {chunk['parent_id']}")
        print(f"  - content: {chunk['content'][:60]}...")
        print(f"  - parent_content: {chunk['parent_content'][:60]}...")
        
        # 验证 ID 格式
        assert chunk['id'].startswith("test_doc_1_parent_"), "ID 格式错误"
        assert "_child_" in chunk['id'], "ID 格式错误，缺少 _child_"
        assert chunk['parent_id'] in chunk['id'], "parent_id 不匹配"
        print("\n✅ ID 格式验证通过")
    
    return True


def test_embedding_service():
    """测试 Embedding 服务"""
    print("\n" + "=" * 60)
    print("测试 2: BGE-M3 Embedding 服务")
    print("=" * 60)
    
    try:
        from utils.embedding_service import get_embedding_service
        
        service = get_embedding_service()
        
        test_texts = [
            "What is friendship?",
            "友谊是什么？",
        ]
        
        result = service.encode(test_texts)
        
        print(f"✅ 编码完成")
        print(f"  - 稠密向量维度: {result['dense_vecs'].shape}")
        print(f"  - 稀疏权重数量: {len(result['lexical_weights'])}")
        
        # 验证维度
        assert result['dense_vecs'].shape[0] == 2, "向量数量错误"
        assert result['dense_vecs'].shape[1] == 1024, "向量维度错误"
        print("\n✅ 向量维度验证通过")
        
        return True
        
    except ImportError as e:
        print(f"⚠️ 跳过 Embedding 测试: {e}")
        print("   请先安装: pip install FlagEmbedding")
        return False


def test_milvus_connection():
    """测试 Milvus 连接"""
    print("\n" + "=" * 60)
    print("测试 3: Milvus 连接")
    print("=" * 60)
    
    try:
        from utils.milvus_client import get_milvus_client
        import numpy as np
        
        client = get_milvus_client(collection_name="test_collection")
        client.create_collection(drop_if_exists=True)
        
        # 测试插入
        test_chunks = [
            {
                "id": "test_parent_0_child_0",
                "content": "This is test content.",
                "parent_id": "test_parent_0",
                "parent_content": "This is test parent content with more context.",
                "metadata": {"source": "test"}
            }
        ]
        
        test_dense = [np.random.randn(1024).astype(np.float32).tolist()]
        test_sparse = [{1: 0.5, 100: 0.3}]
        
        client.insert(test_chunks, test_dense, test_sparse)
        client.load()
        
        print("✅ Milvus 连接成功")
        print("✅ 数据插入成功")
        
        # 测试检索
        results = client.hybrid_search(
            query_dense=np.random.randn(1024).astype(np.float32).tolist(),
            query_sparse={1: 0.5},
            limit=5
        )
        
        print(f"✅ 混合检索成功，返回 {len(results)} 条结果")
        
        return True
        
    except Exception as e:
        print(f"⚠️ Milvus 测试失败: {e}")
        print("   请确保 Milvus 服务已启动 (docker-compose up -d)")
        return False


def test_pdf_processor():
    """测试 PDF 处理器"""
    print("\n" + "=" * 60)
    print("测试 4: PDF 处理器 (PaddleOCR)")
    print("=" * 60)
    
    pdf_path = r"D:\python_code\EnglishTeachingAssistant\data\英语七下（2025春）.pdf"
    
    if not os.path.exists(pdf_path):
        print(f"⚠️ PDF 文件不存在: {pdf_path}")
        return False
    
    try:
        from utils.pdf_processor import PDFProcessor
        
        processor = PDFProcessor(use_gpu=False)
        
        # 只处理前2页作为测试
        print("正在测试 PDF 转图片...")
        images = processor.pdf_to_images(pdf_path, dpi=150)
        print(f"✅ PDF 共 {len(images)} 页")
        
        # 测试第一页 OCR
        print("正在测试 OCR 识别（第1页）...")
        text = processor.ocr_image(images[0])
        print(f"✅ OCR 识别完成，第一页提取 {len(text)} 字符")
        print(f"   预览: {text[:100]}...")
        
        return True
        
    except ImportError as e:
        print(f"⚠️ 跳过 PDF 测试: {e}")
        print("   请先安装: pip install paddleocr paddlepaddle pdf2image")
        return False
    except Exception as e:
        print(f"⚠️ PDF 测试失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("教案生成功能测试")
    print("=" * 60)
    
    results = {}
    
    # 测试 1: 文本切分（无外部依赖）
    results['text_chunker'] = test_text_chunker()
    
    # 测试 2: Embedding（需要 BGE-M3）
    results['embedding'] = test_embedding_service()
    
    # 测试 3: Milvus（需要 Milvus 服务）
    results['milvus'] = test_milvus_connection()
    
    # 测试 4: PDF（需要 PaddleOCR）
    results['pdf'] = test_pdf_processor()
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败/跳过"
        print(f"  {name}: {status}")
    
    passed_count = sum(results.values())
    total_count = len(results)
    print(f"\n总计: {passed_count}/{total_count} 通过")
    
    if passed_count == total_count:
        print("\n🎉 所有测试通过！可以运行入库脚本了。")
    else:
        print("\n⚠️ 部分测试未通过，请检查依赖和服务。")


if __name__ == "__main__":
    main()
