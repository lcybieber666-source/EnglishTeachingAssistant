# -*- coding: utf-8 -*-
"""
一键运行所有评测 — 英语教学助手 DeepEval 评测套件

运行方式：
    python run_all_evals.py            运行全部评测
    python run_all_evals.py intent     仅运行意图识别评测
    python run_all_evals.py docgen     仅运行教案生成评测
    python run_all_evals.py question   仅运行智能出题评测
    python run_all_evals.py grading    仅运行作业批改评测
    python run_all_evals.py analysis   仅运行学情分析评测
"""
import sys
import os
import time
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_eval(name: str, module_func):
    """运行单个评测并捕获异常"""
    print(f"\n{'#' * 70}")
    print(f"#  开始: {name}")
    print(f"#  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#' * 70}\n")

    start = time.time()
    try:
        results = module_func()
        elapsed = time.time() - start

        # 统计通过/失败
        total = len(results.test_results)
        passed = 0
        failed = 0
        for result in results.test_results:
            all_passed = all(m.success for m in result.metrics_data)
            if all_passed:
                passed += 1
            else:
                failed += 1

        return {
            "name": name,
            "status": "completed",
            "total": total,
            "passed": passed,
            "failed": failed,
            "elapsed": elapsed,
        }

    except Exception as e:
        elapsed = time.time() - start
        print(f"\n❌ {name} 评测出错: {type(e).__name__}: {e}")
        return {
            "name": name,
            "status": "error",
            "error": str(e),
            "elapsed": elapsed,
        }


def main():
    # 评测模块注册
    eval_modules = {
        "intent": ("📋 意图识别评测", lambda: __import__("test_intent").main()),
        "docgen": ("📚 教案生成评测", lambda: __import__("test_docgen").main()),
        "question": ("📝 智能出题评测", lambda: __import__("test_question").main()),
        "grading": ("✅ 作业批改评测", lambda: __import__("test_grading").main()),
        "analysis": ("📊 学情分析评测", lambda: __import__("test_analysis").main()),
    }

    # 解析命令行参数
    if len(sys.argv) > 1:
        target = sys.argv[1].lower()
        if target in eval_modules:
            modules_to_run = {target: eval_modules[target]}
        else:
            print(f"❌ 未知的评测模块: {target}")
            print(f"   可选: {', '.join(eval_modules.keys())}")
            sys.exit(1)
    else:
        modules_to_run = eval_modules

    # 打印头部
    print("╔" + "═" * 68 + "╗")
    print("║" + "英语教学助手 — DeepEval 多 Agent 评测套件".center(48) + "║")
    print("║" + f"评测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(58) + "║")
    print("║" + f"评判模型: qwen3-max (DashScope)".center(58) + "║")
    print("║" + f"待评测模块: {len(modules_to_run)} 个".center(55) + "║")
    print("╚" + "═" * 68 + "╝")

    # 运行所有评测
    all_results = []
    total_start = time.time()

    for key, (name, func) in modules_to_run.items():
        result = run_eval(name, func)
        all_results.append(result)

    total_elapsed = time.time() - total_start

    # ========== 汇总报告 ==========
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + "📊 评测总结报告".center(54) + "║")
    print("╚" + "═" * 68 + "╝")
    print()

    print(f"{'模块':<20} {'状态':<10} {'通过':<8} {'失败':<8} {'耗时':<10}")
    print("-" * 60)

    total_passed = 0
    total_failed = 0
    total_cases = 0

    for r in all_results:
        if r["status"] == "completed":
            status_icon = "✅ 完成"
            total_passed += r["passed"]
            total_failed += r["failed"]
            total_cases += r["total"]
            print(
                f"{r['name']:<18} {status_icon:<10} {r['passed']:<8} "
                f"{r['failed']:<8} {r['elapsed']:.1f}s"
            )
        else:
            status_icon = "❌ 出错"
            print(f"{r['name']:<18} {status_icon:<10} {'—':<8} {'—':<8} {r['elapsed']:.1f}s")
            print(f"  └─ 错误: {r['error'][:60]}")

    print("-" * 60)
    print(
        f"{'合计':<18} {'—':<10} {total_passed:<8} "
        f"{total_failed:<8} {total_elapsed:.1f}s"
    )

    if total_cases > 0:
        pass_rate = total_passed / total_cases * 100
        print(f"\n🎯 总体通过率: {pass_rate:.1f}% ({total_passed}/{total_cases})")
    else:
        print("\n⚠️ 没有运行任何测试用例")

    print(f"⏱️ 总耗时: {total_elapsed:.1f} 秒")
    print()


if __name__ == "__main__":
    main()
