"""Render a bounded README snapshot from derived learning state, never invent evidence."""
import json
from pathlib import Path
import yaml

START = '<!-- STUDY_PROGRESS_START -->'
END = '<!-- STUDY_PROGRESS_END -->'


def update(study_root):
    root = Path(study_root)
    readme = root.parent / 'README.md'
    if not readme.exists(): return False
    text = readme.read_text('utf-8')
    if START not in text or END not in text: return False
    state = yaml.safe_load((root / 'state.yaml').read_text('utf-8'))
    summary = json.loads((root / 'stats/summary.json').read_text('utf-8'))
    from scripts.progress_charts import render
    render(root,state,summary)
    course = state['current_course']; stats = state['statistics']
    lines = [START, f"统计日期：**{summary['date']}**（由学习记录生成；实时数据见 `python3 study.py panel`）。", '',
             '![总体与分科覆盖率、稳定掌握率](assets/study-progress.svg)', '',
             '![总体进度历史趋势](assets/study-trend.svg)', '',
             '<details>', '<summary>查看精确数值与当前任务</summary>', '',
             '| 范围 | 已讲解覆盖 | 稳定掌握 |', '|---|---:|---:|']
    for title, values in [('总体', state['progress']), *state['progress']['subjects'].items()]:
        pct = lambda value: '待建立大纲' if value is None else f'{value:.1%}'
        lines.append(f"| {title} | {pct(values['coverage'])} | {pct(values['mastery'])} |")
    correct = '未知' if summary['correct_rate'] is None else format(summary['correct_rate'], '.0%')
    lines += ['', f"已答 **{stats['questions_answered']} 题**；完整正确率 **{correct}**；开放错题 **{stats['open_mistakes']}**；已完成复测 **{summary['completed_reviews']}**。",
              f"当前任务指针：**{course['next_task']} · {course['lesson']}**。", '']
    schedule = state['review']['schedule']
    if schedule:
        date = min(schedule.values()); ids = sorted(i for i,d in schedule.items() if d == date)
        lines += [f"最早待复测：**{date}**，{', '.join(ids)}；到期复习优先，教学下一步以当前上下文和学习小结共同判断。", '']
    lines += ['资料入库、检索和维护不计学习；即时答对不等于稳定掌握。未报告学习时长保持未知。', '', '</details>', END]
    replacement = text[:text.index(START)] + '\n'.join(lines) + text[text.index(END) + len(END):]
    from study import atomic
    if replacement!=text: atomic(readme, replacement)
    return True
