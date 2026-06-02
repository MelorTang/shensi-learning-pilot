# 慎思｜AI 学习诊断与复盘系统产品文档

> 版本：v0.1 MVP 产品与技术方案  
> 日期：2026-06-01  
> 目标用户：七年级学生家长  
> 开发方式：Codex 辅助开发  
> 核心入口：飞书家长端  
> 主系统：FastAPI + LangGraph + SQLite + Obsidian  
> 副驾驶：Hermes  
> 后续增强：LlamaIndex

---

## 0. 命名与产品精神

### 产品名

**慎思**

### 出处

出自《礼记·中庸》：

> 博学之，审问之，慎思之，明辨之，笃行之。

### 产品定位

**慎思** 是一个面向家长的 AI 学习诊断与复盘系统。它通过飞书接收孩子的错题图片，自动完成错题识别、知识点归类、错因分析、家长确认、错题入库、复习计划、日报周报和学习清单生成。

系统的目标不是替孩子刷题，也不是做一个普通错题本，而是帮助家长持续回答三个问题：

1. 孩子今天学到了什么？
2. 孩子真正卡在哪里？
3. 明天最应该抓哪一件事？

### 三个核心模块

| 模块 | 含义 | 系统职责 |
|---|---|---|
| **明辨** | 明辨其失 | 错题识别、知识点归类、错因分析、家长确认 |
| **温故** | 温故而知新 | 错题复习计划、D+1/D+3/D+7 复盘、相似错题回顾 |
| **笃行** | 笃行其改 | 每日学习清单、日报、周报、行动建议 |

一句话表达：

> 从错题中慎思其因，明辨其失，温故其法，笃行其改。

---

## 1. 背景与问题

当前家庭学习场景中，家长常见痛点是：

1. 孩子有学习机，但主要用来看视频，主动做题和整理错题意愿低。
2. 家长看到分数下降，但不知道具体短板在哪里。
3. 错题本容易流于形式：整理了，但不复习；记录了，但不归因。
4. AI 能讲题，但缺少长期学习画像和复习闭环。
5. 家长每天焦虑，但缺少一份可执行的学习清单。

因此需要一个系统，把“错题图片”转化为“可追踪的学习诊断数据”，再转化为“每日可执行的学习动作”。

---

## 2. 产品目标

### 2.1 MVP 目标

第一版只追求打通最小闭环：

```text
家长在飞书上传错题图片
→ AI 分析题目、答案、知识点、错因
→ 家长确认或修正
→ 写入 SQLite + Obsidian
→ 晚上生成日报
→ 周日生成周报
→ 飞书推送明日学习清单
```

### 2.2 非目标

MVP 阶段暂不做：

- 孩子端 App
- 积分系统
- 自动出题系统
- 多孩子账号体系
- 复杂网页后台
- 自动从学习机抓取数据
- 完整知识图谱可视化
- 大规模 RAG 检索

### 2.3 核心原则

1. **先准确，后自动。**
2. **先家长可用，后孩子参与。**
3. **先结构化账本，后智能检索。**
4. **先稳定闭环，后复杂 Agent。**
5. **AI 可以建议，但关键写入必须可确认。**

---

## 3. 用户角色

### 3.1 家长

家长是主要用户。

家长需要：

- 上传错题图片
- 确认 AI 分析是否正确
- 查看日报、周报和明日清单
- 查询孩子近期短板
- 调整学习计划
- 用温和、具体的问题陪孩子复盘

### 3.2 孩子

孩子不是第一版系统的直接操作用户。

孩子只需要完成三个动作：

```text
1. 拍错题或让家长拍错题
2. 重做一遍
3. 口头说明：我错在哪里，下次怎么办
```

### 3.3 AI 系统

AI 系统承担：

- 识别错题图片
- 分析知识点
- 归因错误
- 生成复习计划
- 生成日报周报
- 辅助家长查询和改写报告

---

## 4. 总体架构

### 4.1 推荐架构

```text
飞书家长端
  ↓
FastAPI
  ↓
LangGraph 主系统
  ├── 接收图片
  ├── 下载原图
  ├── AI 识别错题
  ├── 检索 Obsidian/SQLite 上下文
  ├── 归因分析
  ├── 发送确认卡片
  ├── 家长确认/修改
  ├── 写入 SQLite
  ├── 写入 Obsidian
  └── 更新复习计划
  ↓
定时任务
  ├── 每晚日报
  └── 每周周报
  ↓
Hermes 副驾驶
  ├── 飞书自然语言查询
  ├── 报告改写
  ├── 学习清单重排
  └── 短板解释
  ↓
后续增强
  └── LlamaIndex 语义检索
```

### 4.2 组件分工

| 组件 | 职责 |
|---|---|
| 飞书 | 家长上传图片、确认分析、接收日报周报、自然语言查询 |
| FastAPI | Webhook、认证、路由、权限、API 层 |
| LangGraph | 主流程编排、状态管理、家长确认、人机协同 |
| SQLite | 结构化账本，记录错题、知识点、错因、复习、报告 |
| Obsidian | 人类可读知识库，保存错题卡、知识点、日报周报 |
| Hermes | 副驾驶，处理自然语言查询、报告改写、计划调整 |
| LlamaIndex | 后续加入，提供语义检索、相似错题召回、RAG 能力 |
| Codex | 辅助开发、生成代码、重构、测试、文档维护 |

---

## 5. 模块设计

## 5.1 明辨模块

### 5.1.1 模块目标

明辨模块负责从错题图片中识别和判断：

- 题目是什么
- 孩子答案是什么
- 正确答案是什么
- 涉及哪些知识点
- 孩子为什么错
- 错因是否可信
- 是否值得进入错题库

### 5.1.2 输入

家长通过飞书上传：

- 错题图片
- 可选文字说明，例如：
  - “数学，今天作业”
  - “英语周测，孩子选了 B”
  - “这道题孩子说是粗心”

### 5.1.3 输出

AI 输出结构化 JSON：

```json
{
  "subject": "数学",
  "grade": "七年级",
  "question_text": "题目识别文本",
  "student_answer": "孩子答案",
  "correct_answer": "正确答案",
  "solution_summary": "5行以内解题思路",
  "knowledge_points": ["一元一次方程应用题", "等量关系"],
  "surface_error": "方程没有列出来",
  "root_cause": "孩子没有从题干中提取等量关系",
  "error_types": ["审题漏条件", "方法不会"],
  "severity": 4,
  "confidence": 0.82,
  "need_parent_confirmation": true,
  "recommended_action": "明天安排1道同类题，要求先口述等量关系",
  "parent_questions": [
    "题目问的是什么？",
    "哪个量是未知数？",
    "哪句话能列出等量关系？"
  ],
  "review_plan": ["D+1", "D+3", "D+7"]
}
```

### 5.1.4 固定错因标签

MVP 阶段只允许以下错因标签：

| 错因标签 | 说明 |
|---|---|
| 概念不清 | 概念边界、定义、规则没有掌握 |
| 审题漏条件 | 没读完整题，漏掉限制条件 |
| 方法不会 | 不知道该用哪种方法或模型 |
| 计算错误 | 算术、符号、移项、化简等错误 |
| 记忆不牢 | 单词、公式、定义、古诗文等记忆问题 |
| 表达不规范 | 过程、单位、答题格式、语文表达不规范 |
| 步骤跳跃 | 中间步骤缺失，导致推理不稳 |
| 注意力/粗心 | 确实是偶发性低级错误，但需谨慎使用 |
| 知识迁移困难 | 会基础题，但不会应用到新题型 |
| 时间管理问题 | 会做但因时间分配或考试节奏导致错误 |

### 5.1.5 粗心处理原则

不要轻易归因为“粗心”。

系统应优先判断：

```text
表层错误：算错了
深层原因：移项规则不稳 / 草稿不规范 / 审题漏条件 / 步骤跳跃
```

只有在 AI 明确判断知识点掌握稳定、方法正确、步骤完整，仅存在偶发低级错误时，才可使用“注意力/粗心”。

### 5.1.6 低置信度兜底

当出现以下情况时，不得自动入库：

- 图片模糊
- 题干不完整
- 孩子答案缺失
- 科目无法判断
- 正确答案无法确认
- 置信度低于阈值

此时状态应为：

```text
待补充信息
```

飞书返回：

```text
图片信息不足，暂不入库。建议补拍完整题目和孩子解题过程。
```

---

## 5.2 温故模块

### 5.2.1 模块目标

温故模块负责把错题变成复习计划，而不是让错题沉睡在错题本里。

### 5.2.2 复习规则

MVP 使用简单规则：

| 节点 | 时间 |
|---|---|
| D+1 | 错题入库后第 1 天 |
| D+3 | 错题入库后第 3 天 |
| D+7 | 错题入库后第 7 天 |
| 考前 | 周测/月考/期中期末前 |

### 5.2.3 复习任务

复习任务不是“再看一遍”，而是：

```text
重做
口述错因
讲出第一步
做一道同类题
```

### 5.2.4 复习状态

每个复习任务有状态：

| 状态 | 含义 |
|---|---|
| pending | 待复习 |
| done_correct | 重做正确 |
| done_wrong | 重做仍错 |
| skipped | 跳过 |
| postponed | 延后 |

### 5.2.5 温故输出

每日生成：

```text
今日应复习错题
今日新增错题
今日高优先级短板
明日复习清单
```

---

## 5.3 笃行模块

### 5.3.1 模块目标

笃行模块负责把分析结果转化为家长和孩子能执行的学习动作。

### 5.3.2 每日日报

推送时间建议：

```text
每天 21:30
```

日报格式：

```markdown
# 慎思日报｜2026-06-01

## 今日概览
- 新增错题：3 道
- 已复习错题：1 道
- 主要科目：数学、英语
- 今日重点短板：一元一次方程应用题中的等量关系

## 今日判断
孩子不是计算能力整体差，而是在文字题中找等量关系不稳定。

## 明日清单
- [ ] 数学：重做 1 道方程应用题
- [ ] 数学：新做 1 道同类题，先口述等量关系
- [ ] 英语：默写 10 个动词过去式

## 家长今晚只问三句话
1. 这题问什么？
2. 哪个量未知？
3. 哪句话能列出等式？

## 不建议
不要额外刷大量计算题。当前问题不是题量不足，而是建模第一步不稳定。
```

### 5.3.3 每周周报

推送时间建议：

```text
周日 20:30
```

周报格式：

```markdown
# 慎思周报｜2026年第23周

## 本周结论
本周最主要短板是数学应用题建模，错误集中在“找不到等量关系”。

## 高频错因
| 错因 | 次数 | 科目 | 说明 |
|---|---:|---|---|
| 方法不会 | 5 | 数学 | 文字条件无法转成方程 |
| 记忆不牢 | 4 | 英语 | 动词过去式反复错 |
| 表达不规范 | 2 | 语文 | 阅读题答案缺少依据 |

## 薄弱知识点排行
| 排名 | 知识点 | 错题数 | 趋势 |
|---:|---|---:|---|
| 1 | 一元一次方程应用题 | 5 | 上升 |
| 2 | 动词过去式 | 4 | 持平 |
| 3 | 阅读理解依据题 | 2 | 下降 |

## 下周只抓三件事
1. 数学：每天 1 道应用题，只练“找等量关系”。
2. 英语：每天 10 个动词过去式，第二天回测。
3. 语文：每周 2 篇阅读，只练“答案从原文找依据”。

## 给孩子的正反馈
本周愿意重做错题，并能说出部分错因，这是进步。
```

---

## 6. Obsidian 设计

### 6.1 Vault 目录结构

```text
Shensi-Learning-Vault/
  00-Dashboard/
    今日学习清单.md
    本周复习清单.md
    薄弱知识点排行.md
  01-Daily/
    2026-06-01.md
  02-Mistakes/
    数学/
    英语/
    语文/
  03-Concepts/
    数学/
    英语/
    语文/
  04-Reports/
    Daily/
    Weekly/
  05-Curriculum/
    数学/
    英语/
    语文/
  06-Methods/
    数学/
    英语/
    语文/
  07-Parent-QA/
  08-Raw-Images/
  09-AI-Raw-JSON/
  99-System/
    config.yaml
    prompts/
    templates/
```

### 6.2 错题卡模板

```markdown
---
type: mistake
mistake_id: "{{mistake_id}}"
student: child
grade: 七年级
subject: "{{subject}}"
date: "{{date}}"
source: "{{source}}"
knowledge_points:
  - "{{knowledge_point}}"
error_types:
  - "{{error_type}}"
severity: {{severity}}
confidence: {{confidence}}
status: confirmed
review_dates:
  - "{{d1}}"
  - "{{d3}}"
  - "{{d7}}"
image_path: "{{image_path}}"
raw_json_path: "{{raw_json_path}}"
---

# {{title}}

## 原图
![[{{image_file}}]]

## AI识别题目
{{question_text}}

## 孩子的答案
{{student_answer}}

## 正确答案
{{correct_answer}}

## 正确思路
{{solution_summary}}

## 错因分析
### 表层错误
{{surface_error}}

### 深层原因
{{root_cause}}

## 关联知识点
{{concept_links}}

## 家长追问
{{parent_questions}}

## 复习计划
- [ ] D+1：
- [ ] D+3：
- [ ] D+7：

## 家长确认记录
- 确认人：
- 确认时间：
- 修改说明：
```

### 6.3 知识点页模板

```markdown
---
type: concept
subject: "{{subject}}"
grade: 七年级
chapter: "{{chapter}}"
status: "{{status}}"
---

# {{concept_name}}

## 知识点说明
{{description}}

## 孩子需要掌握
1.
2.
3.

## 常见错误
- 
- 
- 

## 家长讲解口径
{{parent_guidance}}

## 关联错题
{{related_mistakes}}

## 推荐练习方式
{{practice_suggestion}}
```

### 6.4 方法库模板

```markdown
---
type: method
subject: "{{subject}}"
applies_to:
  - "{{concept}}"
---

# {{method_name}}

## 使用场景
{{scenario}}

## 步骤
1.
2.
3.

## 家长追问
- 
- 
- 

## 适合纠正的错因
- 
```

---

## 7. SQLite 数据模型

### 7.1 表：mistakes

```sql
CREATE TABLE mistakes (
  id TEXT PRIMARY KEY,
  subject TEXT NOT NULL,
  grade TEXT NOT NULL,
  date TEXT NOT NULL,
  title TEXT NOT NULL,
  source TEXT,
  image_path TEXT,
  note_path TEXT,
  raw_json_path TEXT,
  severity INTEGER,
  confidence REAL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### 7.2 表：concepts

```sql
CREATE TABLE concepts (
  id TEXT PRIMARY KEY,
  subject TEXT NOT NULL,
  grade TEXT,
  name TEXT NOT NULL,
  chapter TEXT,
  note_path TEXT,
  status TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### 7.3 表：mistake_concepts

```sql
CREATE TABLE mistake_concepts (
  mistake_id TEXT NOT NULL,
  concept_id TEXT NOT NULL,
  PRIMARY KEY (mistake_id, concept_id)
);
```

### 7.4 表：error_types

```sql
CREATE TABLE error_types (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT
);
```

### 7.5 表：mistake_error_types

```sql
CREATE TABLE mistake_error_types (
  mistake_id TEXT NOT NULL,
  error_type_id TEXT NOT NULL,
  PRIMARY KEY (mistake_id, error_type_id)
);
```

### 7.6 表：reviews

```sql
CREATE TABLE reviews (
  id TEXT PRIMARY KEY,
  mistake_id TEXT NOT NULL,
  review_date TEXT NOT NULL,
  review_type TEXT,
  status TEXT NOT NULL,
  result TEXT,
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### 7.7 表：reports

```sql
CREATE TABLE reports (
  id TEXT PRIMARY KEY,
  report_type TEXT NOT NULL,
  date TEXT NOT NULL,
  start_date TEXT,
  end_date TEXT,
  note_path TEXT,
  summary TEXT,
  created_at TEXT NOT NULL
);
```

### 7.8 表：feishu_messages

```sql
CREATE TABLE feishu_messages (
  message_id TEXT PRIMARY KEY,
  chat_id TEXT,
  sender_id TEXT,
  message_type TEXT,
  raw_payload_path TEXT,
  processed_status TEXT,
  created_at TEXT NOT NULL
);
```

### 7.9 表：ai_runs

```sql
CREATE TABLE ai_runs (
  id TEXT PRIMARY KEY,
  mistake_id TEXT,
  model_name TEXT,
  prompt_version TEXT,
  input_path TEXT,
  output_json_path TEXT,
  confidence REAL,
  created_at TEXT NOT NULL
);
```

---

## 8. LangGraph 主流程

### 8.1 错题处理 Graph

```text
ReceiveFeishuMessage
  ↓
DeduplicateMessage
  ↓
ClassifyMessage
  ├── image → DownloadImage
  ├── text → CommandRouter
  └── other → Ignore
  ↓
AnalyzeMistakeImage
  ↓
ValidateAnalysisJSON
  ↓
EnrichWithKnowledgeContext
  ↓
SendParentConfirmationCard
  ↓
WaitForParentAction
  ├── confirm → PersistMistake
  ├── edit → UpdateAnalysis
  ├── discard → ArchiveOnly
  └── need_more_info → RequestMoreInfo
  ↓
CreateReviewPlan
  ↓
WriteObsidianNote
  ↓
UpdateDashboard
  ↓
SendBriefSummary
```

### 8.2 日报 Graph

```text
ScheduledDailyReport
  ↓
LoadTodayMistakes
  ↓
LoadDueReviews
  ↓
CalculateErrorStats
  ↓
GenerateTomorrowChecklist
  ↓
GenerateDailyReportMarkdown
  ↓
SaveReportToObsidian
  ↓
PushReportToFeishu
```

### 8.3 周报 Graph

```text
ScheduledWeeklyReport
  ↓
LoadWeekMistakes
  ↓
LoadWeekReviews
  ↓
CalculateWeakConcepts
  ↓
CalculateFrequentErrorTypes
  ↓
GenerateNextWeekPlan
  ↓
GenerateWeeklyReportMarkdown
  ↓
SaveReportToObsidian
  ↓
PushReportToFeishu
```

---

## 9. 飞书交互设计

### 9.1 上传错题

家长发送图片给飞书机器人。

机器人回复：

```text
已收到错题图片，正在分析。
```

分析完成后返回确认卡片：

```text
【明辨】错题分析待确认

科目：数学
知识点：一元一次方程应用题
错因：审题漏条件、方法不会
严重程度：4/5
置信度：0.82

AI 判断：
孩子没有从题干中提取等量关系，而不是单纯计算错误。

请选择：
[确认入库] [修改错因] [修改科目] [丢弃]
```

### 9.2 自然语言查询

家长可以问：

```text
@慎思助手 最近两周数学短板是什么？
@慎思助手 一元一次方程应用题孩子现在怎么样？
@慎思助手 明天只有30分钟，帮我压缩学习清单
@慎思助手 把这周周报改得温和一点
```

处理原则：

```text
Hermes 可以查询和改写。
Hermes 不得直接修改 SQLite 或 Obsidian。
所有写入动作必须调用受控 API。
关键写入需要家长确认。
```

---

## 10. Hermes 副驾驶设计

### 10.1 定位

Hermes 是家长的自然语言副驾驶，不是主系统。

它负责：

- 查询学习数据
- 解释短板
- 改写日报周报
- 压缩学习清单
- 触发重新生成报告
- 给家长提供沟通话术

它不负责：

- 直接处理飞书原始事件
- 直接写数据库
- 直接改 Obsidian 文件
- 未确认删除或覆盖错题数据

### 10.2 受控 API

Hermes 只能调用以下 API：

```text
GET /stats/weekly
GET /stats/daily
GET /mistakes
GET /mistakes/{id}
GET /concepts/{id}
GET /reports/latest
POST /reports/regenerate
POST /plans/tomorrow/rewrite
POST /mistakes/{id}/suggest_update
```

所有危险操作必须二次确认：

```text
删除错题
修改错因
修改严重程度
覆盖周报
清空复习计划
```

---

## 11. LlamaIndex 后续接入设计

### 11.1 接入时机

第一版不需要接入 LlamaIndex。

建议在以下情况出现后再加入：

- Obsidian 中错题超过 100 道
- 知识点页超过 50 个
- 家长开始频繁问跨文件问题
- 需要相似错题召回
- 需要结合历史错题做复杂归因
- 简单 SQLite + Markdown 搜索不够用了

### 11.2 预留接口

从第一版开始，业务代码不得直接散落读取 Markdown 或 SQL。统一通过 `KnowledgeService`。

```python
class KnowledgeService:
    def get_concept(self, name: str): ...
    def search_related_mistakes(self, concept: str, days: int): ...
    def get_error_stats(self, subject: str, days: int): ...
    def get_parent_guidance(self, concept: str): ...
    def search_knowledge(self, query: str): ...
```

第一版：

```text
KnowledgeService = SQLite + Obsidian 简单搜索
```

后续：

```text
KnowledgeService.search_knowledge = LlamaIndex RAG
```

### 11.3 LlamaIndex 用途

后续加入后用于：

- 语义搜索知识点
- 相似错题召回
- 历史错因对比
- 跨文件总结
- 家长飞书问答
- LangGraph 分析错题时召回上下文

---

## 12. 安全与隐私

### 12.1 数据最小化

只保存学习相关数据：

- 错题图片
- 错题分析
- 复习记录
- 报告
- 家长确认记录

不保存无关个人隐私。

### 12.2 权限控制

- 飞书机器人只允许指定家长使用
- 家庭群白名单
- API 需要签名或 token
- Hermes 只能访问受控 API
- 不允许 Agent 访问全盘文件
- 不允许 Agent 自由执行 shell

### 12.3 数据追溯

每次 AI 分析保存：

- 原始图片
- 原始 AI JSON
- 家长修改后 JSON
- 最终 Markdown
- 模型名称
- prompt 版本
- 分析时间
- 确认时间

### 12.4 幂等处理

飞书消息可能重复推送。必须使用 `message_id` 做去重。

---

## 13. 项目结构建议

```text
shensi-learning-pilot/
  app/
    main.py
    config.py
    feishu/
      webhook.py
      client.py
      cards.py
    graph/
      mistake_graph.py
      daily_report_graph.py
      weekly_report_graph.py
      states.py
    services/
      ai_service.py
      knowledge_service.py
      obsidian_service.py
      sqlite_service.py
      report_service.py
      review_service.py
      hermes_service.py
    models/
      mistake.py
      concept.py
      review.py
      report.py
    prompts/
      mistake_analysis.md
      daily_report.md
      weekly_report.md
    templates/
      mistake_note.md
      concept_note.md
      daily_report.md
      weekly_report.md
    scheduler/
      jobs.py
    tests/
      test_mistake_graph.py
      test_report_generation.py
  vault/
    Shensi-Learning-Vault/
  data/
    shensi.db
    raw_payloads/
    ai_runs/
  scripts/
    init_db.py
    seed_error_types.py
    backfill_obsidian_index.py
  README.md
  pyproject.toml
  .env.example
```

---

## 14. Codex 开发任务拆解

### 阶段 1：项目骨架

任务：

```text
创建 Python FastAPI 项目 shensi-learning-pilot。
实现配置加载、日志、基础健康检查、SQLite 初始化、Obsidian vault 路径配置。
```

验收标准：

- `GET /health` 返回正常
- SQLite 数据库可初始化
- Obsidian vault 目录可自动创建

### 阶段 2：飞书 Webhook

任务：

```text
接入飞书消息事件 Webhook。
实现消息验签、message_id 去重、图片消息识别、文本消息识别。
```

验收标准：

- 能接收飞书图片消息
- 能保存原始 payload
- 重复 message_id 不重复处理

### 阶段 3：图片下载

任务：

```text
根据飞书图片消息下载原图，保存到 Obsidian vault 的 08-Raw-Images。
```

验收标准：

- 图片文件保存成功
- 文件名包含日期和 message_id
- SQLite 记录图片路径

### 阶段 4：AI 错题分析

任务：

```text
实现 AIService，输入图片路径和可选文本说明，输出结构化 JSON。
```

验收标准：

- JSON 符合 schema
- 低置信度进入待确认
- 原始 JSON 保存到 09-AI-Raw-JSON

### 阶段 5：LangGraph 明辨流程

任务：

```text
实现错题处理 graph：
接收消息、去重、下载图片、AI 分析、JSON 校验、发送飞书确认卡片。
```

验收标准：

- 飞书上传图片后收到确认卡片
- graph 状态可持久化
- 支持等待家长确认

### 阶段 6：家长确认与入库

任务：

```text
实现确认入库、修改错因、修改科目、丢弃。
确认后写入 SQLite 和 Obsidian 错题卡。
```

验收标准：

- 确认后生成错题卡 Markdown
- SQLite 写入 mistakes、concepts、reviews
- 丢弃后不进入错题库

### 阶段 7：温故复习计划

任务：

```text
根据 D+1/D+3/D+7 规则生成 reviews。
实现今日待复习查询。
```

验收标准：

- 每道确认错题生成 3 条复习任务
- 可查询今日待复习错题

### 阶段 8：笃行日报

任务：

```text
实现每日 21:30 日报生成和飞书推送。
```

验收标准：

- 日报 Markdown 保存到 Obsidian
- 飞书收到日报摘要
- 日报包含今日错题、今日复习、明日清单、家长追问

### 阶段 9：笃行周报

任务：

```text
实现周日 20:30 周报生成和飞书推送。
```

验收标准：

- 周报 Markdown 保存到 Obsidian
- 飞书收到周报摘要
- 周报包含高频错因、薄弱知识点、下周三件事

### 阶段 10：Hermes 副驾驶预留

任务：

```text
实现只读查询 API 和报告改写 API，供 Hermes 后续调用。
```

验收标准：

- 可查询最近两周错题统计
- 可查询某知识点错题
- 可重新生成日报/周报草稿
- 写操作需要确认

### 阶段 11：LlamaIndex 预留

任务：

```text
实现 KnowledgeService 抽象。
第一版用 SQLite + Markdown 简单搜索。
后续可替换为 LlamaIndex。
```

验收标准：

- 业务逻辑不直接依赖底层检索实现
- `search_knowledge(query)` 可返回相关知识点和方法页

---

## 15. Prompt 设计

### 15.1 错题分析 Prompt

```text
你是一名七年级学生的学习诊断助手。请根据上传的错题图片，完成错题分析。

你的目标不是单纯讲解题目，而是帮助家长判断孩子的学习短板。

请输出 JSON，字段包括：
subject, grade, question_text, student_answer, correct_answer,
solution_summary, knowledge_points, surface_error, root_cause,
error_types, severity, confidence, need_parent_confirmation,
recommended_action, parent_questions, review_plan。

要求：
1. 不要轻易归因为粗心。
2. 如果图片无法识别，请明确说明不确定部分。
3. 如果缺少孩子答案，请只分析题目知识点，不要猜测孩子错因。
4. 错因只能从固定标签中选择。
5. 明日建议必须是 15 分钟内能完成的动作。
6. 输出必须是合法 JSON。
```

### 15.2 日报 Prompt

```text
你是家长学习复盘助手。请根据今日错题、复习完成情况、知识点状态，生成一份简短日报。

要求：
1. 面向家长，不要说教。
2. 明确指出今日最重要短板。
3. 明日清单不超过 3 项。
4. 家长追问不超过 3 句。
5. 不建议做的事必须具体。
6. 语气温和、可执行。
```

### 15.3 周报 Prompt

```text
你是家长学习规划助手。请根据本周错题、错因、复习记录，生成一份周报。

要求：
1. 先给本周结论。
2. 列出高频错因和薄弱知识点。
3. 下周只抓三件事。
4. 明确不建议继续加码的方向。
5. 给出孩子值得表扬的具体行为。
6. 语气理性、温和、可执行。
```

---

## 16. MVP 验收标准

MVP 完成后，应满足：

1. 家长可以在飞书发送一张错题图片。
2. 系统能下载并保存图片。
3. AI 能输出结构化错题分析。
4. 家长能确认或丢弃分析结果。
5. 确认后系统写入 SQLite。
6. 确认后系统生成 Obsidian 错题卡。
7. 系统能生成 D+1/D+3/D+7 复习任务。
8. 每晚能生成日报并推送飞书。
9. 每周能生成周报并推送飞书。
10. 所有 AI 原始输出可追溯。
11. 所有核心写入动作可幂等。
12. 系统预留 Hermes 与 LlamaIndex 接入点。

---

## 17. 参考资料

以下资料用于校验技术选型方向，开发时应以官方文档最新版本为准：

- LangGraph durable execution：<https://docs.langchain.com/oss/python/langgraph/durable-execution>
- LangGraph GitHub：<https://github.com/langchain-ai/langgraph>
- LlamaIndex RAG introduction：<https://developers.llamaindex.ai/python/framework/understanding/rag/>
- 飞书接收消息事件：<https://open.feishu.cn/document/server-docs/im-v1/message/events/receive>
- 飞书机器人概览：<https://open.feishu.cn/document/client-docs/bot-v3/bot-overview>
- Obsidian 帮助文档：<https://obsidian.md/help>

---

## 18. 给 Codex 的启动指令

可以直接把下面这段交给 Codex：

```text
请根据 docs/PRD.md 开发 shensi-learning-pilot。

技术栈：
- Python
- FastAPI
- LangGraph
- SQLite
- Obsidian Markdown
- 飞书机器人 Webhook

第一阶段目标：
实现飞书上传错题图片 → AI 分析 → 家长确认 → SQLite 入库 → Obsidian 错题卡生成。

要求：
1. 代码模块化。
2. 所有配置放入 config.yaml 或 .env。
3. 所有写入动作幂等。
4. 所有 AI 输出保存原始 JSON。
5. 不要直接在业务逻辑中散落 SQL 和 Markdown 读写，统一封装在 service 层。
6. 预留 KnowledgeService，后续接 LlamaIndex。
7. 预留 Hermes API，后续做副驾驶。
8. 为核心流程写基础测试。
```

---

## 19. 下一步

推荐下一步立刻做：

1. 建立 Git 仓库：`shensi-learning-pilot`
2. 新建 `docs/PRD.md`
3. 新建 `vault/Shensi-Learning-Vault`
4. 让 Codex 先完成项目骨架和 SQLite schema
5. 再接飞书 Webhook
6. 最后接 AI 分析和 LangGraph 状态流

第一版只要跑通一条链路：

```text
飞书发图 → AI 分析 → 家长确认 → 入库 → 晚上日报
```

这条链路跑通后，慎思就已经有真实价值。
