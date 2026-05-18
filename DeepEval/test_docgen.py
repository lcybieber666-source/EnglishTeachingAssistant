# -*- coding: utf-8 -*-
"""
评测 2：教案生成 Agent (DocGenAssistant) 评测

评测维度：
1. 忠实度 (Faithfulness) — 教案内容是否忠于检索到的课本内容
2. 答案相关性 (AnswerRelevancy) — 教案是否切合用户需求
3. 上下文相关性 (ContextualRelevancy) — RAG 检索内容是否相关
4. 教案教学质量 (自定义 GEval) — 教案是否符合教学规范
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepeval import evaluate
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    AnswerRelevancyMetric,
    FaithfulnessMetric,
    ContextualRelevancyMetric,
    GEval,
)
from deepeval.test_case import SingleTurnParams

from qwen_judge import QwenJudge
from test_data import DOCGEN_TEST_CASES
from config import Config
from main_prompts import EnglishTeachingPrompts
from langchain_openai import ChatOpenAI

conf = Config()
judge = QwenJudge()


def simulate_docgen(user_input: str, textbook_content: str) -> str:
    """
    模拟教案生成 Agent 的核心流程（不依赖 MCP/A2A 服务运行）：
    直接调用 LLM + 教案 Prompt 生成教案
    """
    llm = ChatOpenAI(
        model=conf.model_name,
        api_key=conf.api_key,
        base_url=conf.base_url,
        temperature=0.3,
    )
    chain = EnglishTeachingPrompts.lesson_plan_prompt() | llm

    result = chain.invoke(
        {"textbook_content": textbook_content, "query": user_input}
    ).content

    return result


def build_docgen_test_cases():
    """构建教案生成测试用例"""
    test_cases = []

    for data in DOCGEN_TEST_CASES:
        user_input = data["input"]
        retrieval_context = data["retrieval_context_sample"]
        textbook_content = "\n".join(retrieval_context)

        print(f"  📚 测试: {data['description']} — 输入: {user_input}")
        try:
            actual_output = simulate_docgen(user_input, textbook_content)
        except Exception as e:
            actual_output = f"教案生成失败: {str(e)}"

        test_case = LLMTestCase(
            input=user_input,
            actual_output=actual_output,
            retrieval_context=retrieval_context,
        )
        test_cases.append(test_case)

    return test_cases


def main():
    print("=" * 60)
    print("📚 评测 2：教案生成 Agent (DocGenAssistant)")
    print("=" * 60)

    # ---------- 指标定义 ----------
    # 指标 1：忠实度 — 教案内容是否基于课本内容生成（无幻觉）
    faithfulness = FaithfulnessMetric(
        model=judge,
        threshold=0.6,
    )

    # 指标 2：答案相关性 — 教案是否回答了用户的需求
    relevancy = AnswerRelevancyMetric(
        model=judge,
        threshold=0.6,
    )

    # 指标 3：上下文相关性 — 检索到的课本内容是否相关
    context_relevancy = ContextualRelevancyMetric(
        model=judge,
        threshold=0.6,
    )

    # 指标 4：教案教学质量（自定义 GEval）
    teaching_quality = GEval(
        name="教案教学质量",
        criteria=(
            "评估生成的英语教案质量，从以下维度综合打分："
            "1. 是否包含完整的教案结构（教学目标、重难点、教学过程、作业布置）；"
            "2. 教学目标是否明确具体（知识目标、能力目标、情感目标）；"
            "3. 教学步骤是否合理有序（导入→新课→练习→小结）；"
            "4. 语言表达是否专业规范，适合教师备课使用；"
            "5. 内容是否与请求的年级和单元匹配。"
        ),
        evaluation_params=[
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.INPUT,
        ],
        model=judge,
        threshold=0.6,
    )

    # ---------- 运行评测 ----------
    print("\n⏳ 正在生成教案并评测...")
    test_cases = build_docgen_test_cases()

    print(f"\n📊 共 {len(test_cases)} 个测试用例，开始评测...\n")
    results = evaluate(
        test_cases=test_cases,
        metrics=[faithfulness, relevancy, context_relevancy, teaching_quality],
    )

    # ---------- 输出结果 ----------
    print("\n" + "=" * 60)
    print("📊 教案生成评测结果汇总")
    print("=" * 60)
    for i, result in enumerate(results.test_results):
        data = DOCGEN_TEST_CASES[i]
        print(f"\n用例 {i+1}: {data['description']}")
        print(f"  输入: {data['input']}")
        for metric_data in result.metrics_data:
            status = "✅" if metric_data.success else "❌"
            print(
                f"  {status} {metric_data.name}: {metric_data.score:.2f} "
                f"(阈值: {metric_data.threshold})"
            )
            if metric_data.reason:
                print(f"     原因: {metric_data.reason[:120]}")

    return results


if __name__ == "__main__":
    main()
