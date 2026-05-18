# -*- coding: utf-8 -*-
"""
评测 1：意图识别 Agent 评测

评测 main.py 中的 intent_agent 意图识别准确性：
- 是否识别到正确的意图
- 多意图场景是否都能识别
- 超出范围请求是否正确拒绝
"""
import sys
import os
import json
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepeval import evaluate
from deepeval.test_case import LLMTestCase
from deepeval.metrics import GEval
from deepeval.test_case import SingleTurnParams

from qwen_judge import QwenJudge
from test_data import INTENT_TEST_CASES
from config import Config
from main_prompts import EnglishTeachingPrompts
from langchain_openai import ChatOpenAI

conf = Config()
judge = QwenJudge()


def run_intent_recognition(user_input: str, history: str = "") -> str:
    """调用意图识别 LLM，返回原始 JSON 响应"""
    llm = ChatOpenAI(
        model=conf.model_name,
        api_key=conf.api_key,
        base_url=conf.base_url,
        temperature=0.1,
    )
    chain = EnglishTeachingPrompts.intent_prompt() | llm

    from datetime import datetime
    import pytz

    current_date = datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%Y-%m-%d")

    response = chain.invoke(
        {
            "conversation_history": history,
            "query": user_input,
            "current_date": current_date,
        }
    ).content.strip()

    # 清理 Markdown 代码块标记
    response = re.sub(r"^```json\s*|\s*```$", "", response).strip()
    return response


def build_intent_test_cases():
    """构建意图识别测试用例"""
    test_cases = []

    for data in INTENT_TEST_CASES:
        user_input = data["input"]
        expected_intents = data["expected_intents"]

        # 实际调用意图识别
        print(f"  🔍 测试: {data['description']} — 输入: {user_input}")
        try:
            actual_output = run_intent_recognition(user_input)
        except Exception as e:
            actual_output = json.dumps({"error": str(e)}, ensure_ascii=False)

        expected_output = json.dumps(
            {"intents": expected_intents}, ensure_ascii=False
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
    print("📋 评测 1：意图识别 Agent")
    print("=" * 60)

    # ---------- 指标定义 ----------
    # 指标 1：意图识别准确性
    intent_accuracy = GEval(
        name="意图识别准确性",
        criteria=(
            "判断 actual_output 中识别到的意图（intents 字段）是否与 expected_output 中的意图一致。"
            "如果所有意图都正确识别则满分，漏识别或错误识别则扣分。"
            "注意：actual_output 和 expected_output 都是 JSON 格式，请比较其中的 intents 数组。"
        ),
        evaluation_params=[
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.EXPECTED_OUTPUT,
        ],
        model=judge,
        threshold=0.7,
    )

    # 指标 2：JSON 格式正确性
    json_format = GEval(
        name="输出格式正确性",
        criteria=(
            "判断 actual_output 是否是有效的 JSON 格式，"
            "并且包含 intents（数组）、user_queries（对象）、follow_up_message（字符串）三个字段。"
            "格式完全正确得满分，缺少字段或 JSON 无效则扣分。"
        ),
        evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT],
        model=judge,
        threshold=0.7,
    )

    # ---------- 运行评测 ----------
    print("\n⏳ 正在运行意图识别测试...")
    test_cases = build_intent_test_cases()

    print(f"\n📊 共 {len(test_cases)} 个测试用例，开始评测...\n")
    results = evaluate(
        test_cases=test_cases,
        metrics=[intent_accuracy, json_format],
    )

    # ---------- 输出结果 ----------
    print("\n" + "=" * 60)
    print("📊 意图识别评测结果汇总")
    print("=" * 60)
    for i, result in enumerate(results.test_results):
        data = INTENT_TEST_CASES[i]
        print(f"\n用例 {i+1}: {data['description']}")
        print(f"  输入: {data['input']}")
        print(f"  期望意图: {data['expected_intents']}")
        for metric_data in result.metrics_data:
            status = "✅" if metric_data.success else "❌"
            print(
                f"  {status} {metric_data.name}: {metric_data.score:.2f} "
                f"(阈值: {metric_data.threshold})"
            )
            if metric_data.reason:
                print(f"     原因: {metric_data.reason[:100]}")

    return results


if __name__ == "__main__":
    main()
