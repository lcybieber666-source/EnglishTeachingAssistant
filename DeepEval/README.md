# 英语教学助手 — DeepEval 多 Agent 评测套件

## 📁 文件结构

```
DeepEval/
├── qwen_judge.py        # 自定义 LLM Judge（基于 qwen3-max）
├── test_data.py         # 评测数据集（所有测试用例）
├── test_intent.py       # 评测 1：意图识别
├── test_docgen.py       # 评测 2：教案生成（含 RAG 指标）
├── test_question.py     # 评测 3：智能出题
├── test_grading.py      # 评测 4：作业批改
├── test_analysis.py     # 评测 5：学情分析
├── run_all_evals.py     # 一键运行所有评测
└── README.md            # 本文件
```

## 🚀 快速开始

### 1. 安装 DeepEval

```bash
pip install deepeval
```

### 2. 运行全部评测

```bash
cd d:\python_code\EnglishTeachingAssistant\DeepEval
python run_all_evals.py
```

### 3. 运行单个模块评测

```bash
python run_all_evals.py intent      # 仅意图识别
python run_all_evals.py docgen      # 仅教案生成
python run_all_evals.py question    # 仅智能出题
python run_all_evals.py grading     # 仅作业批改
python run_all_evals.py analysis    # 仅学情分析
```

### 4. 单独运行某个评测文件

```bash
python test_intent.py
python test_docgen.py
python test_question.py
python test_grading.py
python test_analysis.py
```

## 📊 评测指标说明

### 意图识别 (test_intent.py)
| 指标 | 说明 |
|------|------|
| 意图识别准确性 | 识别到的意图是否与期望意图一致 |
| 输出格式正确性 | 输出是否为有效 JSON，包含必要字段 |

### 教案生成 (test_docgen.py)
| 指标 | 说明 |
|------|------|
| Faithfulness (忠实度) | 教案内容是否忠于课本内容，无幻觉 |
| Answer Relevancy (相关性) | 教案是否切合用户请求 |
| Contextual Relevancy (上下文相关性) | RAG 检索的课本内容是否相关 |
| 教案教学质量 | 教案结构、目标、步骤是否符合教学规范 |

### 智能出题 (test_question.py)
| 指标 | 说明 |
|------|------|
| Answer Relevancy (相关性) | 题目是否切合用户需求 |
| 出题质量 | 题目清晰度、答案解析、难度分布 |
| 知识点覆盖度 | 是否覆盖用户要求的知识点 |

### 作业批改 (test_grading.py)
| 指标 | 说明 |
|------|------|
| 批改准确性 | 对错判断是否正确，总分计算是否准确 |
| 反馈质量 | 错误分析是否有针对性、有教学价值 |
| Answer Relevancy (相关性) | 批改结果是否切合用户请求 |

### 学情分析 (test_analysis.py)
| 指标 | 说明 |
|------|------|
| Answer Relevancy (相关性) | 分析报告是否切合用户请求 |
| 分析深度 | 是否基于数据深入分析，而非泛泛而谈 |
| 建议可行性 | 学习建议是否具体、可操作、有优先级 |

## ⚙️ 技术说明

### LLM Judge
- 使用 **qwen3-max** 作为评判模型（通过 DashScope OpenAI 兼容接口）
- 不需要 OpenAI API Key
- 配置在 `qwen_judge.py` 中，继承 `DeepEvalBaseLLM`

### 评测模式
- **离线评测**：不需要启动 A2A/MCP 服务，直接调用 LLM + Prompt 模拟各 Agent
- **优势**：随时可运行，不依赖完整服务环境
- **局限**：不覆盖 MCP 工具调用、Agent 间通信等集成层面

### 评分标准
- 所有指标输出 0~1 的分数
- 默认阈值 0.6（可在代码中调整）
- 分数 ≥ 阈值 → ✅ 通过
- 分数 < 阈值 → ❌ 未通过

## 📝 自定义测试用例

在 `test_data.py` 中添加新的测试用例即可。例如添加一个教案生成用例：

```python
DOCGEN_TEST_CASES.append({
    "input": "帮我生成一份关于定语从句的教案",
    "expected_keywords": ["定语从句", "教学目标", "教学过程"],
    "retrieval_context_sample": ["定语从句是修饰名词或代词的从句..."],
    "description": "语法专题教案 - 定语从句",
})
```

## ❓ 常见问题

**Q: 评测需要多久？**
A: 单个模块约 1-3 分钟（取决于 qwen3-max API 响应速度），全部运行约 5-15 分钟。

**Q: 评测消耗多少 Token？**
A: 每次完整评测大约消耗 30,000-50,000 tokens（包括生成 + 评判）。

**Q: 如何调整评判标准？**
A: 修改各 test_*.py 中 GEval 的 `criteria` 参数和 `threshold` 阈值。
