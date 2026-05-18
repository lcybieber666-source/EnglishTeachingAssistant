# -*- coding: utf-8 -*-
"""
评测 5：学情分析 Agent (AnalysisAssistant) 评测

评测维度：
1. 答案相关性 — 分析报告是否切合用户需求
2. 分析深度（自定义 GEval）— 报告是否有深度和实际价值
3. 建议可行性（自定义 GEval）— 学习建议是否具体可操作
"""
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepeval import evaluate
from deepeval.test_case import LLMTestCase
from deepeval.metrics import AnswerRelevancyMetric, GEval
from deepeval.test_case import SingleTurnParams

from qwen_judge import QwenJudge
from test_data import ANALYSIS_TEST_CASES
from config import Config
from main_prompts import EnglishTeachingPrompts
from langchain_openai import ChatOpenAI

conf = Config()
judge = QwenJudge()


def simulate_analysis(user_input: str, student_data: dict) -> str:
    """模拟学情分析 Agent 核心流程"""
    llm = ChatOpenAI(
        model=conf.model_name,
        api_key=conf.api_key,
        base_url=conf.base_url,
        temperature=0.2,
    )
    chain = EnglishTeachingPrompts.analysis_prompt() | llm

    result = chain.invoke(
        {
            "student_data": json.dumps(student_data, ensure_ascii=False),
            "query": user_input,
        }
    ).content

    return result


def build_analysis_test_cases():
    """构建学情分析测试用例"""
    test_cases = []

    for data in ANALYSIS_TEST_CASES:
        user_input = data["input"]
        student_data = data["student_data_sample"]

        print(f"  📊 测试: {data['description']} — 输入: {user_input}")
        try:
            actual_output = simulate_analysis(user_input, student_data)
        except Exception as e:
            actual_output = f"学情分析失败: {str(e)}"

        test_case = LLMTestCase(
            input=user_input,
            actual_output=actual_output,
            retrieval_context=[
                json.dumps(student_data, ensure_ascii=False)
            ],
        )
        test_cases.append(test_case)

    return test_cases


def main():
    print("=" * 60)
    print("📊 评测 5：学情分析 Agent (AnalysisAssistant)")
    print("=" * 60)

    # ---------- 指标定义 ----------
    # 指标 1：答案相关性
    relevancy = AnswerRelevancyMetric(
        model=judge,
        threshold=0.6,
    )

    # 指标 2：分析深度
    analysis_depth = GEval(
        name="分析深度",
        criteria=(
            "评估学情分析报告的深度和专业性："
            "1. 是否包含总体学习情况概述；"
            "2. 是否对各知识点的掌握程度进行了具体分析；"
            "3. 是否明确列出了薄弱知识点及排名；"
            "4. 是否有成绩趋势分析（进步/退步/稳定）；"
            "5. 分析是否基于提供的数据，而非泛泛而谈。"
        ),
        evaluation_params=[
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.INPUT,
        ],
        model=judge,
        threshold=0.6,
    )

    # 指标 3：建议可行性
    suggestion_quality = GEval(
        name="建议可行性",
        criteria=(
            "评估学情分析中学习建议的质量："
            "1. 建议是否针对学生的具体薄弱点（而非通用建议）；"
            "2. 建议是否具体可操作（如：建议每天练习5道定语从句题，而非'多做题'）；"
            "3. 建议是否分优先级（先攻克哪个薄弱点）；"
            "4. 建议是否考虑了学生的当前水平和进步空间。"
        ),
        evaluation_params=[
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.INPUT,
        ],
        model=judge,
        threshold=0.6,
    )

    # ---------- 运行评测 ----------
    print("\n⏳ 正在生成分析报告并评测...")
    test_cases = build_analysis_test_cases()

    print(f"\n📊 共 {len(test_cases)} 个测试用例，开始评测...\n")
    results = evaluate(
        test_cases=test_cases,
        metrics=[relevancy, analysis_depth, suggestion_quality],
    )

    # ---------- 输出结果 ----------
    print("\n" + "=" * 60)
    print("📊 学情分析评测结果汇总")
    print("=" * 60)
    for i, result in enumerate(results.test_results):
        data = ANALYSIS_TEST_CASES[i]
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
