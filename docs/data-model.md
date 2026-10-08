# 数据约定 v2

日期为ISO8601；新记录自动附加北京时间created_at、updated_at，迁移记录只知日期时使用YYYY-MM-DD及time_precision，不伪造具体时刻。null表示未知，不等于0。

JSONL每一行都是完整实体版本。同ID新revision覆盖查询视图但不删除旧行。questions及achievements不可替换。外键仅使用ID；chapter/subject由topic目录关联取得。历史原题ID保留，新题建议P四位数字，答案A、错题E、复测R同理。Session使用S日期+可选序号。

## 样例：接收当前题的回答（示意，不代表用户已经作答）

```json
{"id":"A0019","question_id":"S001-1","attempt":1,"answer":"这里必须是用户原文","verdict":"pending","score":null}
```

正式写入时替换answer，不要将样例当真实回答。批改追加同ID及原created_at等不可变字段，verdict改为correct/partial/incorrect/incomplete；feedback保存判断依据，explanation保存AI讲解。可另加mistake_type、confidence、grader、rubric字段。score仅有评分标准时填写0..1，否则null。每次新回答新ID/attempt。

## 各表字段

| 表 | 必填或主要字段 |
|---|---|
| questions | id, topic_id, question；建议type, difficulty, source, tags |
| answers | id, question_id, attempt, answer, verdict；建议score, feedback, explanation, time_precision |
| mistakes | id, question_id, answer_id, topic_id, reason, status(open/review/resolved)；建议mistake_type, error_count, first_seen, last_seen, resolution_answer_id |
| reviews | id, mistake_id, due_date, status(scheduled/completed/cancelled)；建议reason, review_count, last_result, result_answer_id |
| topics | id（目录内知识点）, status, covered, evidence（回答ID列表）；建议lecture_source |
| sessions | id, date, effective, duration_minutes, evidence, summary, next_task |
| achievements | id, title, earned_at；建议type |

重复错因保持原mistake ID追加新版本，error_count递增，last_seen更新并保留首次日期。复习完成必须有result_answer_id且已经批改；完成一次复习不等于错题解决。失败后创建新的R ID/日期安排下一次，保留已完成复测。resolved需要后续日期完整正确回答；助教另核对该题是否真正覆盖错因。

知识点状态：not_started / learning / practicing / reviewing / mastered。covered是讲解已完成的布尔标志。只有mastered计稳定掌握；不能因为立即变式通过就设置mastered。新错误出现后建议追加reviewing，统计也会排除该知识点掌握率。

追加session是结束小节时的动作；有学习但没做题时可以用 `knowledge/c_language/C10.md` 作为证据，并在summary说明实际完成的学习活动。打开首页不算有效session。

当前进度由 `current` 命令切换到已有question；不会自动出题或代替助教决策。新增大纲知识点时先更新syllabus/topics.yaml，填稳定ID及knowledge_file，再记录教学状态。
