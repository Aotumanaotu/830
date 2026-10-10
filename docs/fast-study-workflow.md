# 快速学习流程

目标是减少重复上下文和工具往返，沿用现有教学与JSONL数据格式。不会自动出题、自动评定掌握或编造学习时长。

## 恢复与按需读取

- 新会话/新学习日先核对远程，再运行 `start` 和 `context --compact`。精简输出保留完整当前题目、最多3项到期错因和最近700字符小结，不加载全文讲义、历史原始回答或默认RAG。
- 同一会话连续练同一考点，复用已读题目、讲解和来源，不重复面板或读取历史。缺少信息用 `get 表 ID` 精确取记录。
- 换考点、首次讲解、来源冲突或批改有疑问时运行完整 `context` 或指定 `rag.py search`，必要时核对原页。精简不是跳过核验。
- 优先输出简短判定和关键原因，随后在本轮保存并同步；同步状态只在完成或失败时说明。未同步不得声称已同步。

## 一轮一次批量保存

```bash
python3 study.py record-batch /path/to/turn.json
```

输入格式示意（只是格式，不能当用户回答直接写入）：

```json
{
  "records": [
    {"kind": "answers", "record": {"id": "A_NEW", "question_id": "已有题号", "attempt": 1, "answer": "用户原文", "verdict": "pending", "score": null}},
    {"kind": "answers", "record": {"id": "A_NEW", "question_id": "已有题号", "attempt": 1, "answer": "用户原文", "verdict": "correct", "submitted_values_correct": true, "feedback": "批改依据", "score": null}}
  ],
  "current_question": "已有或本批新增的下一题号"
}
```

支持现有全部表；前条可以被后条关联。后续批改省略created_at时继承同ID的原提交日期，显式改写原文、题号、attempt或日期仍拒绝。每批1–100条；全部先预检，格式/关联/不可变字段错误时不追加任何学习记录。通过后持同一把锁依次追加，统计刷新一次，README及SVG刷新一次。保留pending与批改两条版本，不减少历史证据。

批次不是跨文件数据库事务；磁盘失败或进程中断仍可能留下已追加行。保留既有`.dirty`恢复机制，恢复后核对ID/revision，勿盲目重放pending。老版单条record命令仍兼容。

## 同步与图表

每轮变更一次提交和一次推送；连接器将所有变更组成一个tree，用当前head为parent并以expected_sha更新main，出现并发更新先核对远程。同步前check与diff检查可放在同一次工具调用，推送后验证head。不要逐文件提交或强制推送。

README由state/summary生成覆盖率与掌握率图、连续天数等指标，并从真实日终快照及当前summary生成趋势。SVG无需在线图表服务或新运行依赖；精确数字保留在可折叠表格中。更新内容相同时不重写文件。趋势不补造缺失日期；倒计时是统计日快照。

减少的是读取字符和刷新/工具调用次数；模型响应时间、网络延迟和审批不在本工具控制范围内。字符数可复现比较，不能直接当作实际计费token或承诺固定倍数加速。
