# -*- coding: utf-8 -*-
"""
评测 3：智能出题 Agent (QuestionAssistant) 评测

评测维度：
1. 答案相关性 — 题目是否切合用户需求
2. 出题质量（自定义 GEval）— 题目结构、难度分布、答案解析
3. 知识点覆盖度（自定义 GEval）— 是否覆盖指定知识点
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepeval import evaluate
from deepeval.test_case import LLMTestCase
from deepeval.metrics import AnswerRelevancyMetric, GEval
from deepeval.test_case import SingleTurnParams

from qwen_judge import QwenJudge
from test_data import QUESTION_TEST_CASES
from config import Config
from main_prompts import EnglishTeachingPrompts
from langchain_openai import ChatOpenAI

conf = Config()
judge = QwenJudge()


def simulate_question_gen(user_input: str) -> str:
    """模拟出题 Agent 核心流程"""
    llm = ChatOpenAI(
        model=conf.model_name,
        api_key=conf.api_key,
        base_url=conf.base_url,
        temperature=0.5,
    )
    chain = EnglishTeachingPrompts.question_generation_prompt() | llm

    result = chain.invoke(
        {
            "weak_points": "无特定薄弱点",
            "question_bank": "（无题库参考，请自行生成）",
            "query": user_input,
        }
    ).content

    return result


def build_question_test_cases():
    """构建出题测试用例"""
    test_cases = []

    for data in QUESTION_TEST_CASES:
        user_input = data["input"]

        print(f"  📝 测试: {data['description']} — 输入: {user_input}")
        try:
            actual_output = simulate_question_gen(user_input)
        except Exception as e:
            actual_output = f"出题失败: {str(e)}"

        test_case = LLMTestCase(
            input=user_input,
            actual_output=actual_output,
        )
        test_cases.append(test_case)

    return test_cases


def main():
    print("=" * 60)
    print("📝 评测 3：智能出题 Agent (QuestionAssistant)")
    print("=" * 60)

    # ---------- 指标定义 ----------
    # 指标 1：答案相关性
    relevancy = AnswerRelevancyMetric(
        model=judge,
        threshold=0.6,
    )

    # 指标 2：出题质量
    question_quality = GEval(
        name="出题质量",
        criteria=(
            "评估 AI 生成的英语试题质量："
            "1. 题目表述是否清晰、无歧义；"
            "2. 每道题是否附带正确答案和解析说明；"
            "3. 难度分布是否合理（不全是简单题或难题）；"
            "4. 题型是否多样（如选择题、填空题等）；"
            "5. 选项设计是否合理，干扰项有一定迷惑性但不刁钻。"
        ),
        evaluation_params=[
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.INPUT,
        ],
        model=judge,
        threshold=0.6,
    )

    # 指标 3：知识点覆盖度
    knowledge_coverage = GEval(
        name="知识点覆盖度",
        criteria=(
            "评估生成的题目是否覆盖了用户请求中提到的知识点。"
            "如果用户要求考察「一般过去时」，则所有题目都应围绕一般过去时展开。"
            "如果用户要求综合测试，则应覆盖多个知识点（词汇、语法、阅读等）。"
            "覆盖度高得满分，偏题或遗漏核心知识点则扣分。"
        ),
        evaluation_params=[
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.INPUT,
        ],
        model=judge,
        threshold=0.6,
    )

    # ---------- 运行评测 ----------
    print("\n⏳ 正在生成题目并评测...")
    test_cases = build_question_test_cases()

    print(f"\n📊 共 {len(test_cases)} 个测试用例，开始评测...\n")
    results = evaluate(
        test_cases=test_cases,
        metrics=[relevancy, question_quality, knowledge_coverage],
    )

    # ---------- 输出结果 ----------
    print("\n" + "=" * 60)
    print("📊 智能出题评测结果汇总")
    print("=" * 60)
    for i, result in enumerate(results.test_results):
        data = QUESTION_TEST_CASES[i]
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
