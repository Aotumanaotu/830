# 830 助教工作约定

仅负责830初试。保持讲解→出题→原始作答→批改→纠错→复测；不自动转入公共课或复试。

1. 每次恢复先运行 `python study.py start`，向用户展示简洁面板，再运行 `python study.py context`。不要默认读取archive或全部JSONL。
2. 当前题是S001-1，迁移时未作答。不得代答或将示例数据写成用户答案。
3. 新问题先record questions；用户提交先record answers pending，保留原文；随后追加批改版本，不能替换用户原文。未知分数、时长、推理保持null/未提交。
4. 错因写mistakes，延迟复测写reviews。即时答对不等于稳定掌握；标mastered要有跨日完整正确独立变式证据且无开放错题。
5. 正式答案、错因、复测、讲解均保留。知识讲解放knowledge，过程摘要放sessions，别重新堆积总Markdown。
6. 小节结束record sessions有效学习证据，时间用户未报告则null。每日结束close并给简短反馈。不要将面板访问算连续学习。
7. 下一步由现有教学判断决定，用current命令保存；不要随意跳过到期复习。鼓励只每日首次或真实重要节点一次，不每题插入。
8. 使用Store API必须持有lock；可优先CLI。state/summary为派生，不手改百分比。原始archive不得删除。
9. 若Git冲突涉及JSONL，逐条核对ID/revision与原文，不整文件选择一侧。检查通过后再保存Git。不要上传凭据。
