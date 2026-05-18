# -*- coding: utf-8 -*-
"""
学情分析 Agent 功能测试

验证: 学生查询、薄弱点统计、成绩查询、综合学情、Text-to-SQL、班级学情分析
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db_helper import (
    get_student_by_name,
    get_student_weak_points,
    get_student_scores,
    get_student_analysis_data,
    get_class_analysis_data,
    execute_readonly_sql,
)


def test_get_student_by_name():
    """测试 1: 按姓名查学生"""
    print("\n" + "=" * 60)
    print("测试 1: 按姓名查学生")
    print("=" * 60)
    
    student = get_student_by_name("张三")
    if student:
        print(f"\n  找到学生:")
        print(f"    ID: {student['id']}")
        print(f"    学号: {student['student_id']}")
        print(f"    姓名: {student['name']}")
        print(f"    班级: {student['class_name']}")
        print(f"    年级: {student['grade']}")
        print(f"\n[PASS] 通过\n")
        return True
    else:
        # 尝试查数据库里有哪些学生
        from utils.db_helper import execute_readonly_sql
        result = execute_readonly_sql("SELECT name FROM students LIMIT 5")
        if result.get("rows"):
            names = [r["name"] for r in result["rows"]]
            print(f"\n  未找到'张三'，数据库中有: {names}")
            # 用第一个学生重试
            student = get_student_by_name(names[0])
            if student:
                print(f"  使用 '{names[0]}' 重试成功: id={student['id']}")
                print(f"\n[PASS] 通过\n")
                return True
        print(f"\n[FAIL] 失败\n")
        return False


def test_get_student_weak_points():
    """测试 2: 查薄弱知识点"""
    print("\n" + "=" * 60)
    print("测试 2: 查薄弱知识点")
    print("=" * 60)
    
    # 先找一个学生
    student = get_student_by_name("张三")
    if not student:
        result = execute_readonly_sql("SELECT id, name FROM students LIMIT 1")
        if result.get("rows"):
            student = result["rows"][0]
        else:
            print("\n  数据库中无学生数据")
            print(f"\n[SKIP] 跳过\n")
            return None
    
    student_id = student["id"]
    weak_points = get_student_weak_points(student_id, limit=5)
    
    print(f"\n  学生 {student.get('name', student_id)} 的薄弱知识点:")
    if weak_points:
        for i, wp in enumerate(weak_points, 1):
            print(f"    {i}. {wp['name']} ({wp['category']}) - 错 {wp['error_count']} 次")
    else:
        print("    (暂无错题记录)")
    
    print(f"\n[PASS] 通过 (共 {len(weak_points)} 个薄弱点)\n")
    return True


def test_get_student_scores():
    """测试 3: 查历次成绩"""
    print("\n" + "=" * 60)
    print("测试 3: 查历次成绩")
    print("=" * 60)
    
    student = get_student_by_name("张三")
    if not student:
        result = execute_readonly_sql("SELECT id, name FROM students LIMIT 1")
        if result.get("rows"):
            student = result["rows"][0]
        else:
            print("\n  数据库中无学生数据")
            print(f"\n[SKIP] 跳过\n")
            return None
    
    student_id = student["id"]
    scores = get_student_scores(student_id, limit=5)
    
    print(f"\n  学生 {student.get('name', student_id)} 的成绩记录:")
    if scores:
        for s in scores:
            print(f"    {s.get('title', '未知')} | {s['score']}/{s['full_score']} | {s['exam_date']}")
    else:
        print("    (暂无成绩记录)")
    
    print(f"\n[PASS] 通过 (共 {len(scores)} 条记录)\n")
    return True


def test_get_student_analysis_data():
    """测试 4: 综合学情数据"""
    print("\n" + "=" * 60)
    print("测试 4: 综合学情数据")
    print("=" * 60)
    
    # 查找一个有效的学生名
    student_name = "张三"
    student = get_student_by_name(student_name)
    if not student:
        result = execute_readonly_sql("SELECT name FROM students LIMIT 1")
        if result.get("rows"):
            student_name = result["rows"][0]["name"]
        else:
            print("\n  数据库中无学生数据")
            print(f"\n[SKIP] 跳过\n")
            return None
    
    data = get_student_analysis_data(student_name)
    
    if data.get("status") == "success":
        stats = data["statistics"]
        print(f"\n  学生: {data['student_name']} ({data['class_name']})")
        print(f"  作业次数: {stats['total_homeworks']}")
        print(f"  平均分: {stats['avg_score']}")
        print(f"  最高分: {stats['best_score']} | 最低分: {stats['worst_score']}")
        print(f"  薄弱点: {len(data['weak_points'])} 个")
        for wp in data['weak_points']:
            print(f"    - {wp['name']} (错 {wp['error_count']} 次)")
        print(f"\n[PASS] 通过\n")
        return True
    elif data.get("status") == "not_found":
        print(f"\n  未找到学生: {student_name}")
        print(f"\n[FAIL] 失败\n")
        return False
    else:
        print(f"\n  错误: {data.get('message')}")
        print(f"\n[FAIL] 失败\n")
        return False


def test_execute_readonly_sql():
    """测试 5: Text-to-SQL (安全只读查询)"""
    print("\n" + "=" * 60)
    print("测试 5: Text-to-SQL (只读 SQL)")
    print("=" * 60)
    
    # 正常 SELECT
    result = execute_readonly_sql("SELECT name, class_name FROM students LIMIT 3")
    if result["status"] == "success":
        print(f"\n  SELECT 查询成功: {result['row_count']} 行")
        for row in result["rows"]:
            print(f"    {row}")
    else:
        print(f"\n  SELECT 查询失败: {result['message']}")
        print(f"\n[FAIL] 失败\n")
        return False
    
    # 安全拦截 DELETE
    result2 = execute_readonly_sql("DELETE FROM students WHERE id = 1")
    if result2["status"] == "error":
        print(f"  DELETE 拦截成功: {result2['message']}")
    else:
        print(f"  [!] DELETE 未被拦截!")
        print(f"\n[FAIL] 失败\n")
        return False
    
    # 安全拦截 DROP
    result3 = execute_readonly_sql("DROP TABLE students")
    if result3["status"] == "error":
        print(f"  DROP 拦截成功: {result3['message']}")
    else:
        print(f"  [!] DROP 未被拦截!")
        print(f"\n[FAIL] 失败\n")
        return False
    
    print(f"\n[PASS] 通过\n")
    return True


def test_get_class_analysis_data():
    """测试 6: 班级学情分析"""
    print("\n" + "=" * 60)
    print("测试 6: 班级学情分析")
    print("=" * 60)
    
    # 先查出一个有效的班级名
    class_name = "高一(1)班"
    result = execute_readonly_sql("SELECT DISTINCT class_name FROM students LIMIT 1")
    if result.get("rows"):
        class_name = result["rows"][0]["class_name"]
    
    data = get_class_analysis_data(class_name)
    
    if data.get("status") == "success":
        stats = data.get("statistics", {})
        print(f"\n  班级: {data.get('class_name', class_name)}")
        print(f"  学生人数: {data.get('total_students', 'N/A')}")
        print(f"  平均分: {stats.get('avg_score', 'N/A')}")
        print(f"  最高分: {stats.get('max_score', 'N/A')} | 最低分: {stats.get('min_score', 'N/A')}")
        print(f"  参与作业学生: {stats.get('active_students', 'N/A')} 人")
        print(f"  总提交次数: {stats.get('total_submissions', 'N/A')}")
        
        # 班级薄弱知识点
        weak_points = data.get("weak_points", [])
        if weak_points:
            print(f"  班级薄弱知识点: {len(weak_points)} 个")
            for wp in weak_points[:5]:
                print(f"    - {wp.get('name', '未知')} ({wp.get('category', '')}) - 错 {wp.get('total_errors', '?')} 次, 涉及 {wp.get('affected_students', '?')} 人")
        else:
            print("  班级薄弱知识点: (暂无错题记录)")
        
        # 学生排名
        rankings = data.get("student_ranking", [])
        if rankings:
            print(f"  学生排名 (前5):")
            for i, r in enumerate(rankings[:5], 1):
                print(f"    {i}. {r.get('name', '未知')} - 平均 {r.get('avg_score', '?')} 分 ({r.get('homework_count', 0)} 次作业)")
        else:
            print("  学生排名: (暂无成绩记录)")
        
        print(f"\n[PASS] 通过\n")
        return True
    elif data.get("status") == "not_found":
        print(f"\n  未找到班级: {class_name}")
        print(f"\n[FAIL] 失败\n")
        return False
    else:
        print(f"\n  错误: {data.get('message', data)}")
        print(f"\n[FAIL] 失败\n")
        return False


def main():
    print("\n" + "=" * 60)
    print("          学情分析 Agent 功能测试")
    print("=" * 60)
    
    results = {}
    results["get_student_by_name"] = test_get_student_by_name()
    results["get_student_weak_points"] = test_get_student_weak_points()
    results["get_student_scores"] = test_get_student_scores()
    results["get_student_analysis_data"] = test_get_student_analysis_data()
    results["get_class_analysis_data"] = test_get_class_analysis_data()
    results["execute_readonly_sql"] = test_execute_readonly_sql()
    
    # 汇总
    print("=" * 60)
    print("测试汇总:")
    passed = 0
    skipped = 0
    failed = 0
    for name, result in results.items():
        if result is True:
            status = "[PASS]"
            passed += 1
        elif result is None:
            status = "[SKIP]"
            skipped += 1
        else:
            status = "[FAIL]"
            failed += 1
        print(f"  {name}: {status}")
    
    print(f"\n总计: {passed} 通过 / {skipped} 跳过 / {failed} 失败 (共 {len(results)} 项)")
    print("=" * 60)


if __name__ == "__main__":
    main()
