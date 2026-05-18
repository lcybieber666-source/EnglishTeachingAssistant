# -*- coding: utf-8 -*-
"""
MySQL 数据库工具类

封装数据库连接和 CRUD 操作，供 MCP 工具层调用。
"""
import pymysql
from typing import Dict, Any, List, Optional
from config import Config
from create_logger import logger

conf = Config()


def get_connection():
    """获取 MySQL 连接"""
    return pymysql.connect(
        host=conf.db_host,
        port=conf.db_port,
        user=conf.db_user,
        password=conf.db_password,
        database=conf.db_name,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )


def query_questions(
    knowledge_point_ids: List[int] = None,
    question_type: str = None,
    difficulty: int = None,
    keyword: str = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    从题库中检索题目
    
    Args:
        knowledge_point_ids: 知识点ID列表
        question_type: 题型 (choice/fill/short_answer/essay/reading)
        difficulty: 难度等级 1-5
        keyword: 内容关键词
        limit: 返回数量
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        sql = """
            SELECT q.id, q.question_code, q.question_type, q.content, 
                   q.options, q.answer, q.answer_explanation, 
                   q.difficulty, q.source,
                   kp.name AS knowledge_point_name,
                   kp.category AS knowledge_point_category
            FROM questions q
            JOIN knowledge_points kp ON q.knowledge_point_id = kp.id
            WHERE 1=1
        """
        params = []
        
        if knowledge_point_ids:
            placeholders = ','.join(['%s'] * len(knowledge_point_ids))
            sql += f" AND q.knowledge_point_id IN ({placeholders})"
            params.extend(knowledge_point_ids)
        
        if question_type:
            sql += " AND q.question_type = %s"
            params.append(question_type)
        
        if difficulty:
            sql += " AND q.difficulty = %s"
            params.append(difficulty)
        
        if keyword:
            sql += " AND q.content LIKE %s"
            params.append(f"%{keyword}%")
        
        sql += " ORDER BY RAND() LIMIT %s"
        params.append(limit)
        
        cursor.execute(sql, params)
        results = cursor.fetchall()
        
        # 处理 options 字段（JSON 字符串 → dict）
        import json
        for r in results:
            if r.get('options') and isinstance(r['options'], str):
                try:
                    r['options'] = json.loads(r['options'])
                except:
                    pass
        
        return results
    finally:
        conn.close()


def query_questions_by_weak_points(
    weak_point_names: List[str],
    limit: int = 10
) -> List[Dict[str, Any]]:
    """根据薄弱知识点名称检索题目"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        if not weak_point_names:
            return []
        
        placeholders = ','.join(['%s'] * len(weak_point_names))
        cursor.execute(
            f"SELECT id FROM knowledge_points WHERE name IN ({placeholders})",
            weak_point_names
        )
        kp_ids = [row['id'] for row in cursor.fetchall()]
        
        if not kp_ids:
            # 模糊匹配
            conditions = ' OR '.join(['name LIKE %s'] * len(weak_point_names))
            cursor.execute(
                f"SELECT id FROM knowledge_points WHERE {conditions}",
                [f"%{name}%" for name in weak_point_names]
            )
            kp_ids = [row['id'] for row in cursor.fetchall()]
        
        if not kp_ids:
            return []
        
        return query_questions(knowledge_point_ids=kp_ids, limit=limit)
    finally:
        conn.close()


def query_knowledge_points(category: str = None) -> List[Dict[str, Any]]:
    """查询知识点列表"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        if category:
            cursor.execute(
                "SELECT id, code, name, category, difficulty, description FROM knowledge_points WHERE category = %s ORDER BY id",
                (category,)
            )
        else:
            cursor.execute(
                "SELECT id, code, name, category, difficulty, description FROM knowledge_points ORDER BY category, id"
            )
        
        return cursor.fetchall()
    finally:
        conn.close()


def save_homework_template(
    title: str,
    question_ids: List[int],
    target_grade: str = "",
    total_score: int = 100,
    created_by: str = "AI助手"
) -> Dict[str, Any]:
    """保存作业模板到数据库"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        import random
        homework_code = f"HW-{random.randint(10000, 99999)}"
        
        cursor.execute(
            """INSERT INTO homework_templates 
               (homework_code, title, target_grade, total_score, created_by)
               VALUES (%s, %s, %s, %s, %s)""",
            (homework_code, title, target_grade, total_score, created_by)
        )
        homework_id = cursor.lastrowid
        
        score_per_q = total_score // max(len(question_ids), 1)
        for seq, q_id in enumerate(question_ids, 1):
            cursor.execute(
                """INSERT INTO homework_template_questions 
                   (homework_id, question_id, sequence, score)
                   VALUES (%s, %s, %s, %s)""",
                (homework_id, q_id, seq, score_per_q)
            )
        
        conn.commit()
        
        return {
            "homework_id": homework_id,
            "homework_code": homework_code,
            "title": title,
            "question_count": len(question_ids),
            "total_score": total_score
        }
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_homework_answers(homework_id: int) -> List[Dict[str, Any]]:
    """
    根据作业模板ID查询标准答案
    
    联查 homework_template_questions + questions + knowledge_points，
    返回该作业下所有题目的标准答案、分值、知识点等信息。
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                htq.sequence AS question_no,
                htq.score,
                htq.question_id,
                q.question_code,
                q.question_type,
                q.content,
                q.options,
                q.answer,
                q.answer_explanation,
                kp.id AS knowledge_point_id,
                kp.name AS knowledge_point
            FROM homework_template_questions htq
            JOIN questions q ON htq.question_id = q.id
            JOIN knowledge_points kp ON q.knowledge_point_id = kp.id
            WHERE htq.homework_id = %s
            ORDER BY htq.sequence
        """, (homework_id,))
        
        results = cursor.fetchall()
        
        # 处理 options 字段
        import json as _json
        for r in results:
            if r.get('options') and isinstance(r['options'], str):
                try:
                    r['options'] = _json.loads(r['options'])
                except Exception:
                    pass
        
        return results
    finally:
        conn.close()


def create_submission(
    student_id: int,
    homework_id: int,
    image_path: str = None
) -> Dict[str, Any]:
    """
    创建作业提交记录
    
    向 homework_submissions 表插入一条记录，状态为 pending。
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        import random
        import datetime
        now = datetime.datetime.now()
        submission_code = f"SUB-{now.strftime('%Y%m%d%H%M%S')}-{random.randint(100000, 999999)}"
        
        cursor.execute("""
            INSERT INTO homework_submissions 
                (submission_code, student_id, homework_id, image_path, grading_status)
            VALUES (%s, %s, %s, %s, 'pending')
        """, (submission_code, student_id, homework_id, image_path))
        
        submission_id = cursor.lastrowid
        conn.commit()
        
        return {
            "submission_id": submission_id,
            "submission_code": submission_code,
            "student_id": student_id,
            "homework_id": homework_id
        }
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def save_grading_result(
    submission_id: int,
    student_id: int,
    homework_id: int,
    total_score: float,
    full_score: float,
    ocr_result: Dict = None,
    errors: List[Dict] = None
) -> Dict[str, Any]:
    """
    保存批改结果（事务性写入）
    
    1. 更新 homework_submissions 的分数、OCR结果、批改状态
    2. 遍历 errors 列表写入 error_records
    3. 向 score_records 写入一条成绩记录
    """
    import json as _json
    import datetime
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # 1. 更新提交记录
        cursor.execute("""
            UPDATE homework_submissions 
            SET total_score = %s,
                ocr_result = %s,
                grading_status = 'completed',
                graded_at = NOW()
            WHERE id = %s
        """, (total_score, _json.dumps(ocr_result, ensure_ascii=False) if ocr_result else None, submission_id))
        
        # 2. 写入错题记录
        if errors:
            for err in errors:
                cursor.execute("""
                    INSERT INTO error_records 
                        (student_id, question_id, knowledge_point_id, submission_id,
                         student_answer, correct_answer, error_type, error_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
                """, (
                    student_id,
                    err.get("question_id"),
                    err.get("knowledge_point_id"),
                    submission_id,
                    err.get("student_answer", ""),
                    err.get("correct_answer", ""),
                    err.get("error_type", "unknown")
                ))
        
        # 3. 写入成绩记录
        cursor.execute("""
            INSERT INTO score_records 
                (student_id, homework_id, score, full_score, exam_date)
            VALUES (%s, %s, %s, %s, %s)
        """, (student_id, homework_id, total_score, full_score, datetime.date.today()))
        
        conn.commit()
        
        return {
            "submission_id": submission_id,
            "total_score": total_score,
            "full_score": full_score,
            "error_count": len(errors) if errors else 0,
            "status": "completed"
        }
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# ========== 学情分析相关查询函数 ==========

def get_student_by_name(name: str) -> Optional[Dict]:
    """
    按姓名查询学生信息
    
    返回: {id, student_id, name, class_name, grade} 或 None
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, student_id, name, class_name, grade FROM students WHERE name = %s",
                (name,)
            )
            return cursor.fetchone()
    finally:
        conn.close()


def get_student_weak_points(student_id: int, limit: int = 5) -> List[Dict]:
    """
    查询学生薄弱知识点（按错误次数降序）
    
    联查 error_records + knowledge_points，按知识点分组统计错误次数。
    
    返回: [{knowledge_point_id, name, category, error_count, last_error_time}, ...]
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    kp.id AS knowledge_point_id,
                    kp.name,
                    kp.category,
                    COUNT(er.id) AS error_count,
                    MAX(er.last_error_time) AS last_error_time
                FROM error_records er
                JOIN knowledge_points kp ON er.knowledge_point_id = kp.id
                WHERE er.student_id = %s
                GROUP BY kp.id, kp.name, kp.category
                ORDER BY error_count DESC
                LIMIT %s
            """, (student_id, limit))
            return cursor.fetchall()
    finally:
        conn.close()


def get_student_scores(student_id: int, limit: int = 10) -> List[Dict]:
    """
    查询学生历次成绩（按日期降序）
    
    联查 score_records + homework_templates。
    
    返回: [{score, full_score, exam_date, title, rank_in_class}, ...]
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    sr.score,
                    sr.full_score,
                    sr.exam_date,
                    sr.rank_in_class,
                    ht.title
                FROM score_records sr
                JOIN homework_templates ht ON sr.homework_id = ht.id
                WHERE sr.student_id = %s
                ORDER BY sr.exam_date DESC
                LIMIT %s
            """, (student_id, limit))
            return cursor.fetchall()
    finally:
        conn.close()


def get_student_analysis_data(student_name: str) -> Dict:
    """
    综合学情数据汇总
    
    聚合学生信息 + 薄弱知识点 + 历次成绩 + 统计指标。
    """
    # 1. 查学生
    student = get_student_by_name(student_name)
    if not student:
        return {"status": "not_found", "message": f"未找到学生: {student_name}"}
    
    student_id = student["id"]
    
    # 2. 查薄弱知识点
    weak_points = get_student_weak_points(student_id, limit=5)
    
    # 3. 查历次成绩
    scores = get_student_scores(student_id, limit=10)
    
    # 4. 计算统计指标
    if scores:
        score_values = [float(s["score"]) for s in scores]
        avg_score = round(sum(score_values) / len(score_values), 2)
        best_score = max(score_values)
        worst_score = min(score_values)
    else:
        avg_score = 0
        best_score = 0
        worst_score = 0
    
    return {
        "status": "success",
        "student_name": student["name"],
        "student_id": student["student_id"],
        "class_name": student["class_name"],
        "grade": student["grade"],
        "statistics": {
            "total_homeworks": len(scores),
            "avg_score": avg_score,
            "best_score": best_score,
            "worst_score": worst_score
        },
        "weak_points": [
            {
                "name": wp["name"],
                "category": wp["category"],
                "error_count": wp["error_count"],
                "last_error_time": wp["last_error_time"]
            }
            for wp in weak_points
        ],
        "score_trend": [float(s["score"]) for s in reversed(scores)],
        "recent_homeworks": [
            {
                "title": s["title"],
                "score": float(s["score"]),
                "full_score": s["full_score"],
                "date": s["exam_date"],
                "rank": s.get("rank_in_class")
            }
            for s in scores[:5]
        ]
    }


def execute_readonly_sql(sql: str) -> Dict:
    """
    安全执行只读 SQL（仅允许 SELECT）
    
    用于 Text-to-SQL 功能，防止数据篡改。
    """
    # 安全检查：仅允许 SELECT
    sql_stripped = sql.strip().upper()
    if not sql_stripped.startswith("SELECT"):
        return {"status": "error", "message": "仅允许 SELECT 查询"}
    
    # 禁止危险关键字
    dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "GRANT"]
    for keyword in dangerous:
        if keyword in sql_stripped:
            return {"status": "error", "message": f"禁止使用 {keyword} 语句"}
    
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
            return {
                "status": "success",
                "sql": sql,
                "rows": rows,
                "row_count": len(rows)
            }
    except Exception as e:
        return {"status": "error", "message": f"SQL 执行失败: {str(e)}"}
    finally:
        conn.close()


# ========== 班级学情分析 ==========

def get_class_analysis_data(class_name: str) -> Dict:
    """
    班级学情分析数据汇总

    聚合班级所有学生的成绩 + 薄弱知识点分布 + 排名。
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 1. 查询班级学生列表
            cursor.execute(
                "SELECT id, student_id, name FROM students WHERE class_name = %s",
                (class_name,)
            )
            students = cursor.fetchall()

            if not students:
                return {"status": "not_found", "message": f"未找到班级: {class_name}"}

            student_ids = [s["id"] for s in students]
            placeholders = ','.join(['%s'] * len(student_ids))

            # 2. 班级成绩统计
            cursor.execute(f"""
                SELECT
                    AVG(sr.score) AS avg_score,
                    MAX(sr.score) AS max_score,
                    MIN(sr.score) AS min_score,
                    COUNT(DISTINCT sr.student_id) AS active_students,
                    COUNT(sr.id) AS total_submissions
                FROM score_records sr
                WHERE sr.student_id IN ({placeholders})
            """, student_ids)
            class_stats = cursor.fetchone()

            # 3. 各学生平均分排名
            cursor.execute(f"""
                SELECT
                    s.name,
                    s.student_id,
                    ROUND(AVG(sr.score), 2) AS avg_score,
                    COUNT(sr.id) AS homework_count
                FROM score_records sr
                JOIN students s ON sr.student_id = s.id
                WHERE sr.student_id IN ({placeholders})
                GROUP BY sr.student_id, s.name, s.student_id
                ORDER BY avg_score DESC
            """, student_ids)
            student_ranking = cursor.fetchall()

            # 4. 班级薄弱知识点分布（所有学生的错题汇总）
            cursor.execute(f"""
                SELECT
                    kp.name,
                    kp.category,
                    COUNT(er.id) AS total_errors,
                    COUNT(DISTINCT er.student_id) AS affected_students
                FROM error_records er
                JOIN knowledge_points kp ON er.knowledge_point_id = kp.id
                WHERE er.student_id IN ({placeholders})
                GROUP BY kp.id, kp.name, kp.category
                ORDER BY total_errors DESC
                LIMIT 10
            """, student_ids)
            class_weak_points = cursor.fetchall()

            return {
                "status": "success",
                "class_name": class_name,
                "total_students": len(students),
                "statistics": {
                    "avg_score": round(float(class_stats["avg_score"]), 2) if class_stats["avg_score"] else 0,
                    "max_score": float(class_stats["max_score"]) if class_stats["max_score"] else 0,
                    "min_score": float(class_stats["min_score"]) if class_stats["min_score"] else 0,
                    "active_students": class_stats["active_students"] or 0,
                    "total_submissions": class_stats["total_submissions"] or 0
                },
                "student_ranking": [
                    {
                        "name": r["name"],
                        "student_id": r["student_id"],
                        "avg_score": float(r["avg_score"]),
                        "homework_count": r["homework_count"]
                    }
                    for r in student_ranking
                ],
                "weak_points": [
                    {
                        "name": wp["name"],
                        "category": wp["category"],
                        "total_errors": wp["total_errors"],
                        "affected_students": wp["affected_students"]
                    }
                    for wp in class_weak_points
                ]
            }
    except Exception as e:
        logger.error(f"班级学情分析失败: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

