"""Small, dependency-free SVG charts for GitHub; only derived real records."""
import json
from html import escape
from pathlib import Path


def label(value):
    return '待确认' if value is None else f'{value * 100:.1f}%'


def shell(width, height, title, description, body):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">{escape(title)}</title><desc id="desc">{escape(description)}</desc>
<style>text{{font-family:system-ui,"Noto Sans CJK SC","Microsoft YaHei",sans-serif;fill:#24334b}}.muted{{fill:#65758b}}.blue{{fill:#2563eb}}.green{{fill:#059669}}</style>
<rect width="100%" height="100%" rx="16" fill="#f8fafc"/>
{body}
</svg>\n'''


def overview(state, summary):
    rows=[('总体', state['progress']), *state['progress']['subjects'].items()]
    stats=state['statistics']; height=238+len(rows)*86
    countdown=summary.get('days_to_exam')
    countdown_text='考试日期待确认' if countdown is None else f'距离考试 {countdown} 天' if countdown>=0 else '考试日期已过，请核对目标'
    b=[f'<text x="28" y="38" font-size="23" font-weight="700">830 · 学习进度</text>',
       f'<text x="28" y="65" class="muted" font-size="13">统计日期 {escape(summary["date"])} · {escape(countdown_text)}</text>']
    cards=[('已答题目',stats['questions_answered'],'题'),('连续学习',state['study_streak']['current'],'天'),('待解决错题',stats['open_mistakes'],'项'),('已完成复测',stats['completed_reviews'],'次')]
    for i,(name,value,unit) in enumerate(cards):
        x=28+i*180
        b += [f'<rect x="{x}" y="84" width="166" height="82" rx="10" fill="#fff" stroke="#e2e8f0"/>',f'<text x="{x+14}" y="109" class="muted" font-size="13">{name}</text>',f'<text x="{x+14}" y="144" font-size="27" font-weight="700">{value}<tspan font-size="13"> {unit}</tspan></text>']
    b += ['<circle cx="37" cy="193" r="5" fill="#2563eb"/><text x="49" y="198" font-size="13">已讲解覆盖</text>', '<circle cx="175" cy="193" r="5" fill="#059669"/><text x="187" y="198" font-size="13">稳定掌握</text>']
    for i,(name,values) in enumerate(rows):
        y=223+i*86
        b.append(f'<text x="28" y="{y+16}" font-size="15" font-weight="600">{escape(name)}</text>')
        for j,(metric,color) in enumerate([('coverage','#2563eb'),('mastery','#059669')]):
            value=values[metric]; by=y+j*23
            b += [f'<rect x="150" y="{by}" width="490" height="13" rx="4" fill="#e2e8f0"/>']
            if value is not None and value>0:
                b.append(f'<rect x="150" y="{by}" width="{490*value:.3f}" height="13" rx="3" fill="{color}"/>')
            b.append(f'<text x="660" y="{by+12}" font-size="13">{label(value)}</text>')
    b.append(f'<text x="28" y="{height-16}" class="muted" font-size="12">覆盖与掌握分别统计；即时订正不等于独立掌握。倒计时为统计日快照。</text>')
    desc='；'.join(f'{name}覆盖{label(v["coverage"])}，稳定掌握{label(v["mastery"])}' for name,v in rows)
    return shell(780,height,'学习进度',desc,'\n'.join(b))


def trend(root, summary):
    history=root/'stats/history.jsonl'; points={}
    if history.exists():
        for line in history.read_text('utf-8').splitlines():
            if line.strip():
                row=json.loads(line); points[row['date']]=row
    points[summary['date']]=summary
    rows=[points[d] for d in sorted(points)]
    # All real dated snapshots retained. x spacing reflects actual elapsed days.
    from datetime import date
    first=date.fromisoformat(rows[0]['date']); last=date.fromisoformat(rows[-1]['date'])
    span=(last-first).days
    x=lambda r: 80+620*(date.fromisoformat(r['date'])-first).days/span if span else 390
    y=lambda v: 216-140*v
    b=['<text x="28" y="35" font-size="19" font-weight="700">总体进度趋势</text>', '<text x="28" y="57" class="muted" font-size="12">已结束日快照 + 当前统计；仅连接真实记录日期，纵轴 0–100%。</text>']
    for value in (0,.25,.5,.75,1):
        b += [f'<line x1="80" y1="{y(value)}" x2="700" y2="{y(value)}" stroke="#e2e8f0"/>',f'<text x="25" y="{y(value)+4}" font-size="11" class="muted">{value*100:.0f}%</text>']
    for metric,color in [('coverage','#2563eb'),('mastery','#059669')]:
        segment=[]
        for row in rows+[None]:
            value=row.get(metric) if row else None
            if value is None:
                if segment: b.append(f'<polyline points="{" ".join(segment)}" fill="none" stroke="{color}" stroke-width="2.5"/>'); segment=[]
            else:
                segment.append(f'{x(row):.2f},{y(value):.2f}')
                b.append(f'<circle cx="{x(row):.2f}" cy="{y(value):.2f}" r="3" fill="{color}"><title>{row["date"]} {metric}: {label(value)}</title></circle>')
    # Keep date ticks legible for long histories; no data point is dropped.
    for row in ([rows[0],rows[-1]] if len(rows)>1 else rows):
        b.append(f'<text x="{x(row):.2f}" y="240" text-anchor="middle" font-size="12" class="muted">{row["date"]}</text>')
    b += ['<text x="80" y="273" font-size="13" class="blue">● 已讲解覆盖</text>','<text x="240" y="273" font-size="13" class="green">● 稳定掌握</text>']
    return shell(780,298,'总体进度趋势','所有真实日期的覆盖率与掌握率；未记录日期不补造数据。','\n'.join(b))


def render(study_root,state,summary):
    from study import atomic
    root=Path(study_root); assets=root.parent/'assets'
    for filename,svg in [('study-progress.svg',overview(state,summary)),('study-trend.svg',trend(root,summary))]:
        target=assets/filename
        if not target.exists() or target.read_text('utf-8')!=svg: atomic(target,svg)
