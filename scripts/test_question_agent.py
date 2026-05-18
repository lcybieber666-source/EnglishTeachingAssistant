# -*- coding: utf-8 -*-
"""
出题 Agent 测试脚本

直接调用 db_helper 验证 MySQL 查询功能。
"""
import os
import sys
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_query_knowledge_points():
    """测试1: 查询知识点"""
    from utils.db_helper import query_knowledge_points
    
    print("=" * 60)
    print("测试 1: 查询知识点")
    print("=" * 60)
    
    points = query_knowledge_points()
    print(f"共 {len(points)} 个知识点:\n")
    for p in points:
        print(f"  [{p['code']}] {p['name']} (分类: {p['category']}, 难度: {p['difficulty']})")
    
    assert len(points) > 0, "知识点为空"
    print(f"\n[PASS] 通过\n")
    return True


def test_query_questions():
    """测试2: 按条件查询题目"""
    from utils.db_helper import query_questions
    
    print("=" * 60)
    print("测试 2: 按条件查询题目")
    print("=" * 60)
    
    # 查选择题
    questions = query_questions(question_type="choice", limit=5)
    print(f"\n选择题: {len(questions)} 道")
    for q in questions:
        print(f"  [{q['question_code']}] {q['content'][:60]}... (知识点: {q['knowledge_point_name']}, 难度: {q['difficulty']})")
    
    assert len(questions) > 0, "没有查到选择题"
    print(f"\n[PASS] 通过\n")
    return True


def test_query_by_weak_points():
    """测试3: 按薄弱知识点查询"""
    from utils.db_helper import query_questions_by_weak_points
    
    print("=" * 60)
    print("测试 3: 按薄弱知识点查询题目")
    print("=" * 60)
    
    weak_points = ["定语从句", "虚拟语气", "时态"]
    questions = query_questions_by_weak_points(weak_points, limit=10)
    print(f"\n薄弱点 {weak_points} -> {len(questions)} 道题目:")
    for q in questions:
        print(f"  [{q['question_code']}] {q['content'][:60]}... (知识点: {q['knowledge_point_name']})")
    
    assert len(questions) > 0, "薄弱知识点没有查到题目"
    print(f"\n[PASS] 通过\n")
    return True


def main():
    print("\n" + "=" * 60)
    print("          出题 Agent 功能测试")
    print("=" * 60 + "\n")
    
    results = {}
    
    for name, func in [
        ("query_knowledge_points", test_query_knowledge_points),
        ("query_questions", test_query_questions),
        ("query_by_weak_points", test_query_by_weak_points),
    ]:
        try:
            results[name] = func()
        except Exception as e:
            print(f"  [FAIL] 失败: {e}\n")
            results[name] = False
    
    # 汇总
    print("=" * 60)
    print("测试汇总:")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, ok in results.items():
        print(f"  {name}: {'[PASS]' if ok else '[FAIL]'}")
    print(f"\n总计: {passed}/{total} 通过")
    print("=" * 60)


if __name__ == "__main__":
    main()
