# 三个核心 Agent 功能详解

> 本文档详细说明出题Agent、作业批改Agent、学情分析Agent的具体功能、数据需求和工作流程。

---

## 一、学情分析 Agent（AnalysisServer:5013）

### 1.1 学情分析是什么？

学情分析是一个**数据中心 Agent**，负责收集、存储和分析学生的学习数据，帮助教师了解学生的学习状况，并为其他 Agent（出题、批改）提供数据支持。

### 1.2 学情分析需要哪些数据？

| 数据来源 | 表名 | 提供的信息 |
|---------|------|-----------|
| **错题记录** | `error_records` | 学生做错的题目、错误类型、错误次数、涉及的知识点 |
| **成绩记录** | `score_records` | 每次作业/考试的得分、得分率、班级排名 |
| **知识点表** | `knowledge_points` | 知识点分类（语法/词汇/阅读/写作）、难度等级 |
| **学生信息** | `students` | 学生基本信息、班级 |

### 1.3 学情分析具体做什么？

#### 功能1：查询学生薄弱知识点（被出题Agent调用）

```sql
-- 按错误次数排序，找出张三最薄弱的知识点
SELECT kp.name, SUM(er.error_count) AS total_errors
FROM error_records er
JOIN knowledge_points kp ON er.knowledge_point_id = kp.id
WHERE er.student_id = 1  -- 张三
GROUP BY kp.id
ORDER BY total_errors DESC
LIMIT 5;
```

**返回示例：**

| 知识点 | 累计错误次数 |
|--------|-------------|
| 定语从句 | 5 |
| 虚拟语气 | 3 |
| 时态 | 2 |

#### 功能2：写入批改结果（被批改Agent调用）

批改Agent完成批改后，会调用学情分析Agent写入：
- **错题记录**：哪道题错了、错在哪个知识点、学生答案 vs 正确答案
- **成绩记录**：本次作业得分、班级排名

```python
grading_data = {
    "action": "save_grading_result",
    "student_id": 1,
    "homework_id": 1,
    "total_score": 75.5,
    "errors": [
        {"question_id": 1, "knowledge_point_id": 1, "student_answer": "B", "correct_answer": "A"},
        {"question_id": 2, "knowledge_point_id": 2, "student_answer": "was", "correct_answer": "were"}
    ]
}
```

#### 功能3：生成学情报告（被主应用调用）

当教师说"分析一下张三的学习情况"时，学情分析Agent会：

1. **统计薄弱知识点**：按错误次数排序
2. **分析成绩趋势**：最近5次作业的得分曲线
3. **对比班级平均**：与班级平均分的差距
4. **生成建议**：基于薄弱点给出针对性学习建议

**返回的学情报告示例：**
```
📊 学生：张三（高一3班）学情分析报告

【薄弱知识点】
1. 定语从句 - 累计错误5次 ⚠️ 需重点关注
2. 虚拟语气 - 累计错误3次
3. 时态 - 累计错误2次

【成绩趋势】
最近5次作业：68 → 72 → 75 → 73 → 75.5（略有上升）

【班级对比】
本次成绩：75.5分，班级排名：3/30，班级平均：74.2分

【学习建议】
建议重点复习定语从句中关系代词的使用规则（which/that/who区别）
```

### 1.4 学情分析功能总结

| 功能 | 调用方 | 作用 |
|------|--------|------|
| **查询薄弱点** | 出题Agent | 让出题更有针对性 |
| **写入批改结果** | 批改Agent | 积累学习数据 |
| **生成学情报告** | 主应用 | 让教师了解学生情况 |

**本质上**：学情分析是整个系统的"数据大脑"，它不直接服务用户，而是为其他Agent提供数据支撑，实现"数据驱动的智能教学"。

---

## 二、出题 Agent（QuestionServer:5011）

### 2.1 出题Agent是什么？

出题Agent是一个**智能出题服务**，能够根据用户需求（学生姓名、题目类型、知识点范围）自动生成练习题或试卷，并且可以基于学生的薄弱点进行**针对性出题**。

### 2.2 出题Agent需要哪些数据？

| 数据来源 | 表名 | 提供的信息 |
|---------|------|-----------|
| **题目库** | `questions` | 所有可用题目、题型、答案、知识点关联 |
| **知识点表** | `knowledge_points` | 知识点分类、难度等级 |
| **课本内容** | `textbook_contents` | 课本章节内容（用于RAG检索相关题目） |
| **学情数据** | 通过A2A调用学情分析Agent | 学生薄弱知识点 |

### 2.3 出题Agent具体做什么？

#### 功能1：基于用户需求出题

当教师说"出一套定语从句练习题"时：

```
用户输入 → 提取题目要求 → 从题库RAG检索 → 组装试卷 → 返回
```

```sql
-- 检索定语从句相关的选择题，难度3-4
SELECT * FROM questions 
WHERE knowledge_point_id = 1  -- 定语从句
  AND question_type = 'choice'
  AND difficulty BETWEEN 3 AND 4
LIMIT 10;
```

#### 功能2：基于学情的智能出题（核心功能）⭐

当教师说"给张三出一套针对性练习题"时：

**步骤1：A2A调用学情分析Agent，获取薄弱点**
```python
# 调用学情分析Agent
self.analysis_client = A2AClient("http://localhost:5013")
message = Message(content=TextContent(text=json.dumps({
    "action": "query_weak_points",
    "student_name": "张三",
    "limit": 3
})), role=MessageRole.USER)
task = Task(id="task-xxx", message=message.to_dict())
result = asyncio.run(self.analysis_client.send_task_async(task))
# 返回: {"weak_points": ["定语从句", "虚拟语气", "时态"]}
```

**步骤2：基于薄弱点从题库检索**
```sql
-- 检索薄弱知识点相关的题目
SELECT * FROM questions 
WHERE knowledge_point_id IN (1, 2, 3)  -- 定语从句、虚拟语气、时态
ORDER BY 
    CASE knowledge_point_id 
        WHEN 1 THEN 1  -- 定语从句优先（错最多）
        WHEN 2 THEN 2  
        WHEN 3 THEN 3 
    END
LIMIT 20;
```

**步骤3：组装试卷，按薄弱程度分配题量**
```
定语从句：8题（最薄弱，多练）
虚拟语气：6题
时态：6题
```

#### 功能3：保存作业到作业库

生成的作业会被保存到 `homework_templates` 和 `homework_template_questions` 表，供后续批改时使用。

```python
# 保存作业模板
INSERT INTO homework_templates (homework_code, title, target_grade, total_score) 
VALUES ('HW-2024-0201', '张三专项练习', '高一', 100);

# 保存作业-题目关联
INSERT INTO homework_template_questions (homework_id, question_id, sequence, score)
VALUES (6, 1, 1, 5), (6, 2, 2, 5), ...
```

### 2.4 出题Agent工作流程图

```
用户: "给张三出一套语法练习题"
        │
        ▼
┌──────────────────────────────┐
│ 1. 提取学生姓名和题目要求     │
└──────────────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│ 2. A2A调用学情分析Agent       │
│    获取张三的薄弱知识点        │
│    → 返回: [定语从句, 虚拟语气] │
└──────────────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│ 3. 调用MCP工具 (RAG题库检索)  │
│    根据薄弱点检索相关题目      │
└──────────────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│ 4. 组装试卷                   │
│    按薄弱程度分配题量          │
└──────────────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│ 5. 保存到作业库，返回试卷      │
└──────────────────────────────┘
```

### 2.5 出题Agent功能总结

| 功能 | 输入 | 输出 | A2A调用 |
|------|------|------|---------|
| **普通出题** | 题目类型、知识点、数量 | 试卷 | 无 |
| **智能出题** | 学生姓名 + 题目要求 | 针对性试卷 | 调用学情分析Agent |
| **保存作业** | 生成的试卷 | 作业ID | 无 |

---

## 三、作业批改 Agent（GradingServer:5012）

### 3.1 作业批改Agent是什么？

作业批改Agent是一个**自动批改服务**，能够接收学生提交的作业图片，通过OCR识别学生答案，与标准答案进行比对，自动评分，并将批改结果同步到学情分析系统。

### 3.2 作业批改Agent需要哪些数据？

| 数据来源 | 表名 | 提供的信息 |
|---------|------|-----------|
| **作业提交** | `homework_submissions` | 学生提交的作业图片路径 |
| **作业模板** | `homework_templates` | 作业总分、包含的题目 |
| **作业-题目关联** | `homework_template_questions` | 每道题的分值 |
| **题目库** | `questions` | 标准答案 |
| **学情分析** | 通过A2A调用 | 写入批改结果 |

### 3.3 作业批改Agent具体做什么？

#### 功能1：OCR识别学生答案

通过MCP工具调用OCR服务，识别作业图片中的学生答案。

```python
# 调用MCP OCR工具
async with ClientSession(read, write) as session:
    result = await session.call_tool("ocr_recognize", {
        "image_path": "/uploads/hw/2024/02/15/001.jpg"
    })
# 返回: {"answers": {"1": "B", "2": "was", "3": "A", ...}}
```

#### 功能2：比对标准答案，生成批改结果

```sql
-- 获取作业对应的标准答案
SELECT htq.sequence, q.answer, q.knowledge_point_id, htq.score
FROM homework_template_questions htq
JOIN questions q ON htq.question_id = q.id
WHERE htq.homework_id = 1
ORDER BY htq.sequence;
```

**比对逻辑：**
```python
grading_result = {
    "student_id": 1,
    "homework_id": 1,
    "total_score": 0,
    "full_score": 100,
    "correct_count": 0,
    "error_count": 0,
    "errors": []
}

for seq, student_ans in student_answers.items():
    correct_ans = standard_answers[seq]
    score = question_scores[seq]
    
    if student_ans == correct_ans:
        grading_result["total_score"] += score
        grading_result["correct_count"] += 1
    else:
        grading_result["error_count"] += 1
        grading_result["errors"].append({
            "question_id": question_ids[seq],
            "knowledge_point_id": knowledge_points[seq],
            "student_answer": student_ans,
            "correct_answer": correct_ans
        })
```

#### 功能3：A2A调用学情分析Agent，写入批改结果（核心功能）⭐

批改完成后，自动将结果同步到学情分析系统：

```python
# 调用学情分析Agent写入结果
self.analysis_client = A2AClient("http://localhost:5013")

grading_data = {
    "action": "save_grading_result",
    "student_id": 1,
    "homework_id": 1,
    "total_score": 75.5,
    "full_score": 100,
    "errors": [
        {
            "question_id": 1, 
            "knowledge_point_id": 1, 
            "student_answer": "B", 
            "correct_answer": "A",
            "error_type": "concept_error"
        }
    ]
}

message = Message(content=TextContent(text=json.dumps(grading_data)), role=MessageRole.USER)
task = Task(id="task-xxx", message=message.to_dict())
asyncio.run(self.analysis_client.send_task_async(task))
```

这样学情分析系统就会更新：
- `error_records` 表：新增错题记录
- `score_records` 表：新增成绩记录

#### 功能4：返回批改结果给用户

```
✅ 作业批改完成

学生：张三
作业：定语从句专项练习
得分：75.5 / 100 分
正确：15 题
错误：5 题

【错题详情】
1. 第5题 - 知识点：定语从句
   你的答案：B    正确答案：A
   解析：此处应使用which引导非限制性定语从句...

2. 第8题 - 知识点：虚拟语气
   你的答案：was    正确答案：were
   解析：虚拟语气中，be动词一律用were...
```

### 3.4 作业批改Agent工作流程图

```
用户: "批改张三的作业" + [上传作业图片]
        │
        ▼
┌──────────────────────────────┐
│ 1. 接收作业图片               │
│    保存到 homework_submissions │
└──────────────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│ 2. 调用MCP工具 (OCR识别)      │
│    识别学生手写/打印答案       │
└──────────────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│ 3. 从作业库获取标准答案        │
│    查询 questions 表          │
└──────────────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│ 4. 逐题比对，计算得分          │
│    记录错题和对应知识点        │
└──────────────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│ 5. A2A调用学情分析Agent       │
│    写入错题记录 + 成绩记录     │
└──────────────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│ 6. 返回批改结果给用户          │
└──────────────────────────────┘
```

### 3.5 作业批改Agent功能总结

| 功能 | 输入 | 输出 | 调用的服务 |
|------|------|------|-----------|
| **OCR识别** | 作业图片 | 学生答案列表 | MCP OCR工具 |
| **答案比对** | 学生答案 + 标准答案 | 批改结果 | 数据库查询 |
| **写入学情** | 批改结果 | 确认信息 | A2A调用学情分析Agent |
| **返回结果** | 批改结果 | 格式化报告 | LLM总结 |

---

## 四、三个Agent的协作关系总结

```
┌─────────────────────────────────────────────────────────────────────┐
│                           智能教学闭环                               │
│                                                                     │
│   📝 出题Agent                                   ✅ 批改Agent        │
│       │                                              │              │
│       │ A2A: 请求薄弱点                              │ A2A: 写入错题 │
│       │                                              │              │
│       └──────────────► 📊 学情分析Agent ◄────────────┘              │
│                              │                                      │
│                              │ 数据积累                              │
│                              ▼                                      │
│                     ┌─────────────────┐                             │
│                     │   数据库存储     │                             │
│                     │ - 错题记录       │                             │
│                     │ - 成绩记录       │                             │
│                     └─────────────────┘                             │
└─────────────────────────────────────────────────────────────────────┘
```

| Agent | 角色 | A2A调用关系 |
|-------|------|------------|
| **出题Agent** | 生产者 | 调用学情分析Agent（读取薄弱点） |
| **批改Agent** | 生产者 | 调用学情分析Agent（写入批改结果） |
| **学情分析Agent** | 数据中心 | 被调用（不主动调用其他Agent） |

**核心理念**：学情分析Agent作为数据中心，出题和批改Agent围绕它进行数据的读取和写入，形成"数据驱动的智能教学"闭环。
