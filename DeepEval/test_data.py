# -*- coding: utf-8 -*-
"""
评测数据集 — 英语教学助手

包含各 Agent 的测试用例，分为：
1. 意图识别测试数据
2. 教案生成 (DocGen) 测试数据
3. 智能出题 (Question) 测试数据
4. 作业批改 (Grading) 测试数据
5. 学情分析 (Analysis) 测试数据
6. 端到端 (E2E) 测试数据
"""

# ========== 1. 意图识别测试数据 ==========
INTENT_TEST_CASES = [
    {
        "input": "帮我生成一份七年级下册第三单元的教案",
        "expected_intents": ["lesson_plan"],
        "description": "明确的教案生成请求",
    },
    {
        "input": "帮我出10道关于一般过去时的选择题",
        "expected_intents": ["question"],
        "description": "明确的出题请求",
    },
    {
        "input": "帮我批改这份作业",
        "expected_intents": ["grading"],
        "description": "明确的批改请求",
    },
    {
        "input": "分析一下张三同学的英语学习情况",
        "expected_intents": ["analysis"],
        "description": "明确的学情分析请求",
    },
    {
        "input": "今天天气怎么样",
        "expected_intents": ["out_of_scope"],
        "description": "超出范围的请求",
    },
    {
        "input": "先帮我备课七年级上册Unit 1，然后出几道练习题",
        "expected_intents": ["lesson_plan", "question"],
        "description": "多意图请求：教案 + 出题",
    },
    {
        "input": "给李四出几道针对性练习题，他最近语法很差",
        "expected_intents": ["question"],
        "description": "含学生名称的个性化出题",
    },
    {
        "input": "看看高一(1)班的整体英语成绩",
        "expected_intents": ["analysis"],
        "description": "班级学情分析请求",
    },
]


# ========== 2. 教案生成测试数据 ==========
DOCGEN_TEST_CASES = [
    {
        "input": "帮我生成七年级下册第一单元的教案",
        "expected_keywords": ["教学目标", "教学重点", "教学过程", "作业"],
        "retrieval_context_sample": [
            "Unit 1 Can you play the guitar? Section A: 学习情态动词 can 的用法，"
            "掌握谈论个人能力的表达方式。重点词汇：guitar, sing, swim, dance, draw, chess, speak。"
        ],
        "description": "标准教案生成 - 七年级下册 Unit 1",
    },
    {
        "input": "请生成一份关于现在进行时的教案，适合八年级学生",
        "expected_keywords": ["现在进行时", "教学目标", "教学步骤"],
        "retrieval_context_sample": [
            "现在进行时 (Present Progressive Tense)：表示说话时正在进行的动作或当前一段时间正在进行的动作。"
            "结构：主语 + am/is/are + v-ing。"
        ],
        "description": "语法专题教案生成 - 现在进行时",
    },
    {
        "input": "帮我做一份九年级英语阅读理解教学设计",
        "expected_keywords": ["阅读", "教学目标", "教学过程"],
        "retrieval_context_sample": [
            "阅读理解教学策略：预测、略读(skimming)、扫读(scanning)、精读(intensive reading)。"
        ],
        "description": "阅读理解教案生成",
    },
]


# ========== 3. 智能出题测试数据 ==========
QUESTION_TEST_CASES = [
    {
        "input": "帮我出5道关于一般过去时的选择题",
        "expected_keywords": ["一般过去时", "选择", "答案", "解析"],
        "description": "语法选择题生成",
    },
    {
        "input": "出一套七年级英语综合测试卷，包含选择题、填空题和简答题",
        "expected_keywords": ["选择题", "填空题", "答案"],
        "description": "综合测试卷生成",
    },
    {
        "input": "根据 Unit 3 的内容出几道单词拼写题",
        "expected_keywords": ["拼写", "答案"],
        "description": "单词拼写题生成",
    },
]


# ========== 4. 作业批改测试数据 ==========
GRADING_TEST_CASES = [
    {
        "input": "批改这份作业",
        "standard_answers": {
            "questions": [
                {"question_no": 1, "answer": "B", "knowledge_point": "一般过去时"},
                {"question_no": 2, "answer": "A", "knowledge_point": "现在完成时"},
                {"question_no": 3, "answer": "C", "knowledge_point": "被动语态"},
                {"question_no": 4, "answer": "D", "knowledge_point": "定语从句"},
                {"question_no": 5, "answer": "A", "knowledge_point": "虚拟语气"},
            ],
            "total_score": 50,
        },
        "student_answers": "1. B  2. C  3. C  4. A  5. A",
        "expected_keywords": ["对", "错", "得分", "分析"],
        "description": "标准选择题批改 — 部分答对",
    },
    {
        "input": "请批改以下英语作文",
        "standard_answers": "(无标准答案，请根据英语语法和表达自行判断)",
        "student_answers": (
            "My Favorite Season\n"
            "My favorite season is summer. Because I can go swimming and eat ice cream. "
            "The weather is very hot but I like it. I always go to the beach with my friends. "
            "We plays volleyball and build sandcastles. It is very fun."
        ),
        "expected_keywords": ["语法", "评分"],
        "description": "英语作文批改 — 含语法错误",
    },
]


# ========== 5. 学情分析测试数据 ==========
ANALYSIS_TEST_CASES = [
    {
        "input": "分析张三同学的英语学习情况",
        "student_data_sample": {
            "student_name": "张三",
            "scores": [75, 80, 65, 82, 78],
            "weak_points": ["一般过去时", "定语从句", "被动语态"],
            "class_average": 80,
        },
        "expected_keywords": ["薄弱", "建议", "成绩"],
        "description": "个人学情分析",
    },
    {
        "input": "分析高一(1)班的班级学情",
        "student_data_sample": {
            "class_name": "高一(1)班",
            "average_score": 78.5,
            "pass_rate": 0.85,
            "top_weak_points": ["完形填空", "阅读理解", "写作"],
        },
        "expected_keywords": ["班级", "平均", "建议"],
        "description": "班级学情分析",
    },
]


# ========== 6. 端到端测试数据 ==========
E2E_TEST_CASES = [
    {
        "input": "帮我生成七年级下册第一单元的教案",
        "expected_agent": "DocGenAssistant",
        "expected_keywords": ["教学目标", "教学过程"],
        "description": "E2E - 教案生成流程",
    },
    {
        "input": "帮我出5道关于现在完成时的选择题",
        "expected_agent": "QuestionAssistant",
        "expected_keywords": ["选择", "答案"],
        "description": "E2E - 出题流程",
    },
    {
        "input": "分析一下李四同学最近的英语成绩",
        "expected_agent": "AnalysisAssistant",
        "expected_keywords": ["分析", "建议"],
        "description": "E2E - 学情分析流程",
    },
]
