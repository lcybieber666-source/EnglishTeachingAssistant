# -*- coding: utf-8 -*-
"""
教案生成命令行工具

用法:
    python scripts/generate_lesson.py

流程:
    用户输入 → RAG 课本检索 → LLM 生成教案 → docxtpl 渲染 Word
"""
import os
import sys
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from create_logger import logger


def main():
    conf = Config()
    
    print("=" * 60)
    print("          英语教案生成工具")
    print("=" * 60)
    print()
    
    # 用户输入
    grade = input("请输入年级 (如 七年级): ").strip() or "七年级"
    semester = input("请输入上册/下册: ").strip() or "下册"
    unit = input("请输入单元 (如 Unit 1): ").strip() or "Unit 1"
    
    # 组合查询信息
    grade_full = f"{grade}{semester}"  # 如 "七年级下册"
    
    print()
    print("-" * 60)
    print(f"  年级: {grade_full}")
    print(f"  单元: {unit}")
    print("-" * 60)
    print()
    
    # === 第一步: RAG 课本检索（支持 metadata 过滤） ===
    print("📚 正在检索课本内容...")
    textbook_content = ""

    try:
        import re as _re
        from utils.embedding_service import get_embedding_service
        from utils.milvus_client import get_milvus_client as create_milvus_client
        from utils.reranker_service import get_reranker_service

        # 从 unit 字符串中提取数字用于 metadata 过滤
        unit_num = None
        unit_num_match = _re.search(r"(\d+)", unit)
        if unit_num_match:
            unit_num = int(unit_num_match.group(1))

        query = f"{grade_full} {unit}"

        embedding_service = get_embedding_service(model_name=conf.embedding_model)
        milvus_client = create_milvus_client(
            host=conf.milvus_host,
            port=conf.milvus_port,
            collection_name=conf.milvus_collection,
        )
        milvus_client.load()
        reranker = get_reranker_service(model_name=conf.reranker_model)

        # 构建 metadata 过滤表达式
        expr = f'metadata["unit"] == {unit_num}' if unit_num else None
        if expr:
            print(f"  [过滤] 使用 metadata 过滤: {expr}")

        # 第一阶段: BGE-M3 混合检索
        print("  [阶段1] BGE-M3 混合检索...")
        dense_vec, sparse_vec = embedding_service.encode_single(query)
        results = milvus_client.hybrid_search(
            query_dense=dense_vec.tolist(),
            query_sparse=sparse_vec,
            limit=20,
            dense_weight=0.7,
            sparse_weight=0.3,
            expr=expr,
        )
        print(f"  [阶段1] 召回 {len(results)} 条候选")

        # 第二阶段: Reranker 精排
        if results:
            print("  [阶段2] BGE-Reranker-Large 精排...")
            reranked = reranker.rerank(
                query=query,
                documents=results,
                content_key="parent_content",
                top_k=5,
            )
            print(f"  [阶段2] 精排后 {len(reranked)} 条结果")

            for i, r in enumerate(reranked):
                content = r.get("parent_content") or r.get("content", "")
                score = r.get("rerank_score", 0)
                meta = r.get("metadata", {})
                ct = meta.get("content_type", "")
                sec = meta.get("section", "")
                label = f"Unit {meta.get('unit', '?')} {f'Section {sec}' if sec else ''} [{ct}]".strip()
                textbook_content += f"\n### 参考片段 {i+1} ({label}, 相关度: {score:.2f})\n{content}\n"

            print(f"  ✅ 检索到 {len(reranked)} 段相关课本内容")
        else:
            print("  ⚠️ 未检索到相关内容，将由 LLM 自行生成")

    except Exception as e:
        print(f"  ⚠️ RAG 检索失败: {e}")
        print("  将由 LLM 根据自身知识生成教案")
    
    # === 第二步: LLM 生成教案 ===
    print()
    print("🤖 正在调用 LLM 生成教案...")
    
    from langchain_openai import ChatOpenAI
    
    llm = ChatOpenAI(
        model=conf.model_name,
        api_key=conf.api_key,
        base_url=conf.base_url,
        temperature=0.3
    )
    
    prompt = f"""你是一位经验丰富的英语教师，请根据以下信息生成一份详细的英语教案。

## 基本信息
- 年级: {grade_full}
- 单元: {unit}

## 课本内容参考
{textbook_content or "（无课本内容参考，请根据教学经验生成）"}

## 输出要求
请以 JSON 格式输出教案，严格包含以下所有字段（全部用英文书写教学内容）：
{{
    "topic_content": "课题内容，如 Unit 1 Section A Making Friends (1a-2d)",
    "lesson_type": "课型，如 Reading / Listening / Speaking / Grammar",
    "situation_analysis": "教情学情分析，分析学生现有水平、该课时内容特点和学生可能的困难",
    "teaching_objectives": "教学目标，包含4维度：1.Language ability 2.Learning ability 3.Thinking quality 4.Cultural awareness",
    "key_points": "教学重点，列出2-3个重点",
    "difficult_points": "教学难点",
    "teaching_methods": "教法，如 Task-based teaching, Communicative approach, Situational teaching",
    "learning_methods": "学法，如 Group-work, Pair-work, Independent learning",
    "lead_in_teacher": "导入部分-教师活动，详细描述教师在导入环节的具体操作",
    "lead_in_student": "导入部分-学生活动，描述学生在导入环节的具体活动",
    "lead_in_purpose": "导入部分-设计意图，说明设计导入活动的目的",
    "new_lesson_teacher": "新课学习-教师活动，详细描述 Pre-reading/While-reading/Post-reading 或其他阶段的教师活动",
    "new_lesson_student": "新课学习-学生活动，描述每个阶段学生的具体活动",
    "new_lesson_purpose": "新课学习-设计意图，说明各阶段活动的设计目的",
    "summary": "课堂小结，描述如何总结本课所学",
    "summary_purpose": "课堂小结-设计意图",
    "homework": "作业布置，分 Must-do 和 Choose-to-do 两部分",
    "homework_purpose": "作业设计意图",
    "board_design": "板书设计，简要列出板书内容",
    "board_purpose": "板书设计意图",
    "reflection": ""
}}

请直接输出 JSON，不要有其他内容。注意：教学过程（导入、新课学习）要尽量详细具体。
"""
    
    try:
        response = llm.invoke(prompt)
        content = response.content.strip()
        
        # 解析 JSON
        import re
        content = re.sub(r'^```json\s*|\s*```$', '', content).strip()
        lesson_data = json.loads(content)
        
        # 补充字段
        lesson_data["title"] = f"{grade_full}_{unit}"
        lesson_data["grade"] = grade_full
        lesson_data["unit"] = unit
        
        print("  ✅ LLM 生成完成")
        
    except json.JSONDecodeError as e:
        print(f"  ❌ LLM 输出格式错误: {e}")
        print(f"  原始输出: {content[:200]}...")
        return
    except Exception as e:
        print(f"  ❌ LLM 调用失败: {e}")
        return
    
    # === 第三步: 生成 Word 文档 ===
    print()
    print("📄 正在生成 Word 文档...")
    
    from utils.word_generator import LessonPlanGenerator
    
    generator = LessonPlanGenerator()
    word_path = generator.generate(lesson_data)
    
    file_size = os.path.getsize(word_path)
    
    print()
    print("=" * 60)
    print(f"  ✅ 教案已生成！")
    print(f"  📁 文件: {word_path}")
    print(f"  📊 大小: {file_size:,} 字节")
    print("=" * 60)


if __name__ == "__main__":
    main()
