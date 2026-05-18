# -*- coding: utf-8 -*-
"""
评测 4：作业批改 Agent (GradingAssistant) 评测

评测维度：
1. 批改准确性（自定义 GEval）— 对错判断是否正确
2. 反馈质量（自定义 GEval）— 错误分析和解释是否有帮助
3. 答案相关性 — 批改结果是否切合用户需求
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
from test_data import GRADING_TEST_CASES
from config import Config
from main_prompts import EnglishTeachingPrompts
from langchain_openai import ChatOpenAI

conf = Config()
judge = QwenJudge()


def simulate_grading(
    user_input: str, standard_answers: str, student_answers: str
) -> str:
    """模拟批改 Agent 核心流程（跳过 OCR，直接使用文本答案）"""
    llm = ChatOpenAI(
        model=conf.model_name,
        api_key=conf.api_key,
        base_url=conf.base_url,
        temperature=0.1,
    )
    chain = EnglishTeachingPrompts.grading_prompt() | llm

    if isinstance(standard_answers, dict):
        standard_answers = json.dumps(standard_answers, ensure_ascii=False)

    result = chain.invoke(
        {
            "standard_answers": standard_answers,
            "student_answers": student_answers,
            "query": user_input,
        }
    ).content

    return result


def build_grading_test_cases():
    """构建批改测试用例"""
    test_cases = []

    for data in GRADING_TEST_CASES:
        user_input = data["input"]
        standard_answers = data["standard_answers"]
        student_answers = data["student_answers"]

        print(f"  ✅ 测试: {data['description']} — 输入: {user_input}")
        try:
            actual_output = simulate_grading(
                user_input, standard_answers, student_answers
            )
        except Exception as e:
            actual_output = f"批改失败: {str(e)}"

        # expected_output 将标准答案和学生答案打包，用于 GEval 评判参考
        expected_output = (
            f"标准答案: {json.dumps(standard_answers, ensure_ascii=False, default=str)}\n"
            f"学生答案: {student_answers}"
        )

        test_case = LLMTestCase(
            input=user_input,
            actual_output=actual_output,
            expected_output=expected_output,
        )
        test_cases.append(test_case)

    return test_cases


def main():
    print("=" * 60)
    print("✅ 评测 4：作业批改 Agent (GradingAssistant)")
    print("=" * 60)

    # ---------- 指标定义 ----------
    # 指标 1：批改准确性
    grading_accuracy = GEval(
        name="批改准确性",
        criteria=(
            "评估 AI 批改结果的准确性："
            "1. 根据 expected_output 中的标准答案和学生答案，判断 AI 批改的对错判定是否正确；"
            "2. 对于选择题，标准答案明确的情况下，AI 是否正确标注了每道题的对错；"
            "3. 对于作文批改，AI 是否准确找出了语法错误（如主谓不一致、时态错误等）；"
            "4. 总分计算是否合理。"
        ),
        evaluation_params=[
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.EXPECTED_OUTPUT,
        ],
        model=judge,
        threshold=0.6,
    )

    # 指标 2：反馈质量
    feedback_quality = GEval(
        name="反馈质量",
        criteria=(
            "评估 AI 批改反馈的教学辅助价值："
            "1. 是否对每道错题给出了清晰的错误分析；"
            "2. 是否提供了正确答案和解释说明；"
            "3. 错误分析是否有针对性（指出了具体的知识点薄弱环节）；"
            "4. 反馈语言是否易于学生理解、有鼓励性；"
            "5. 是否总结了学生的主要薄弱知识点。"
        ),
        evaluation_params=[
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.INPUT,
        ],
        model=judge,
        threshold=0.6,
    )

    # 指标 3：答案相关性
    relevancy = AnswerRelevancyMetric(
        model=judge,
        threshold=0.6,
    )

    # ---------- 运行评测 ----------
    print("\n⏳ 正在模拟批改并评测...")
    test_cases = build_grading_test_cases()

    print(f"\n📊 共 {len(test_cases)} 个测试用例，开始评测...\n")
    results = evaluate(
        test_cases=test_cases,
        metrics=[grading_accuracy, feedback_quality, relevancy],
    )

    # ---------- 输出结果 ----------
    print("\n" + "=" * 60)
    print("📊 作业批改评测结果汇总")
    print("=" * 60)
    for i, result in enumerate(results.test_results):
        data = GRADING_TEST_CASES[i]
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
