#!/usr/bin/env python3
"""Local learning records. Python 3.10+, PyYAML; no network or model dependency."""
import argparse, contextlib, datetime as dt, json, os, sqlite3, sys, tempfile
if os.name=='nt':
    import msvcrt
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
else: import fcntl
from pathlib import Path
from zoneinfo import ZoneInfo
import yaml

TABLES = {'questions':'questions/questions.jsonl','answers':'questions/answers.jsonl',
 'mistakes':'mistakes/mistakes.jsonl','reviews':'reviews/review_queue.jsonl',
 'topics':'syllabus/topic_events.jsonl','sessions':'sessions/sessions.jsonl',
 'achievements':'motivation/achievements.jsonl'}
STATUSES = {'not_started','learning','practicing','reviewing','mastered'}
def today(): return dt.datetime.now(ZoneInfo('Asia/Shanghai')).date()
def stamp(): return dt.datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
def dump(x): return json.dumps(x, ensure_ascii=False, separators=(',',':'))
def read_yaml(p): return yaml.safe_load(p.read_text('utf-8'))
def atomic(p, text):
    p.parent.mkdir(parents=True,exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent,prefix='.'+p.name)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='') as f: f.write(text); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,p)
        if os.name!='nt': d=os.open(p.parent,os.O_RDONLY); os.fsync(d); os.close(d)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
def save_yaml(p,x): atomic(p,yaml.safe_dump(x,allow_unicode=True,sort_keys=False))

class Store:
    def __init__(self,root): self.root=Path(root)
    @contextlib.contextmanager
    def lock(self):
        with (self.root/'.study.lock').open('a') as f:
            if os.name=='nt':
                f.seek(0); msvcrt.locking(f.fileno(),msvcrt.LK_LOCK,1)
                try: yield
                finally: f.seek(0); msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:
                fcntl.flock(f,fcntl.LOCK_EX)
                yield
    def path(self,k): return self.root/TABLES[k]
    def index(self,k):
        p=self.path(k); cache=self.root/'.cache'/f'{k}.json'
        signature=[p.stat().st_size,p.stat().st_mtime_ns]
        if cache.exists():
            c=json.loads(cache.read_text('utf-8'))
            if c['signature']==signature: return c['offsets']
        offsets={}
        with p.open('rb') as f:
            while True:
                offset=f.tell(); line=f.readline()
                if not line: break
                if not line.endswith(b'\n'): raise ValueError(f'{p}: 不完整尾行；运行 repair {k}')
                try: row=json.loads(line)
                except Exception as e: raise ValueError(f'{p} byte {offset}: 损坏记录，保留原文件等待修复') from e
                offsets[row['id']]=offset
        atomic(cache,dump({'signature':signature,'offsets':offsets}))
        return offsets
    def get(self,k,id):
        offsets=self.index(k)
        if id not in offsets: return None
        with self.path(k).open('rb') as f: f.seek(offsets[id]); return json.loads(f.readline())
    def all(self,k):
        offsets=self.index(k)
        with self.path(k).open('rb') as f:
            rows=[]
            for pos in offsets.values(): f.seek(pos); rows.append(json.loads(f.readline()))
        return rows
    def append(self,k,row):
        row=dict(row); old=self.get(k,row['id'])
        if old and all(old.get(a)==b for a,b in row.items()): return False
        if old and k in ('questions','achievements'): raise ValueError('该 ID 不可覆盖；使用新 ID')
        if old and k=='answers' and any(row.get(x)!=old.get(x) for x in ('question_id','answer','attempt','created_at')):
            raise ValueError('原始答案不可改写；批改修订须保留原文、题号、次数和提交日期')
        row.setdefault('created_at',stamp()); row['updated_at']=stamp(); row['revision']=(old or {}).get('revision',0)+1
        self.validate(k,row)
        # A single complete UTF-8 line under process lock; cache is disposable.
        offsets=self.index(k); pos=self.path(k).stat().st_size
        atomic(self.root/'.dirty','Derived state requires refresh\n')
        with self.path(k).open('ab') as f:
            f.write((dump(row)+'\n').encode()); f.flush(); os.fsync(f.fileno())
        offsets[row['id']]=pos
        p=self.path(k)
        atomic(self.root/'.cache'/f'{k}.json',dump({'signature':[p.stat().st_size,p.stat().st_mtime_ns],'offsets':offsets}))
        return True
    def validate(self,k,r):
        if not isinstance(r.get('id'),str) or not r['id']: raise ValueError('id 必填')
        dt.datetime.fromisoformat(r['created_at'])
        req={'questions':['topic_id','question'],'answers':['question_id','answer','attempt','verdict'],
             'mistakes':['answer_id','question_id','topic_id','reason','status'],
             'reviews':['mistake_id','due_date','status'], 'topics':['status','covered','evidence'],
             'sessions':['date','effective','summary','next_task','duration_minutes'],
             'achievements':['title','earned_at']}[k]
        for field in req:
            if field not in r: raise ValueError(f'{k}.{field} 必填')
        for field,table in [('question_id','questions'),('answer_id','answers'),('mistake_id','mistakes')]:
            if field in r and not self.get(table,r[field]): raise ValueError(f'无效关联 {field}: {r[field]}')
        if 'topic_id' in r and r['topic_id'] not in {t['id'] for t in read_yaml(self.root/'syllabus/topics.yaml')['topics']}: raise ValueError('未知 topic_id')
        if k=='answers':
            if not isinstance(r['answer'],str) or r['verdict'] not in ('pending','correct','partial','incorrect','incomplete'): raise ValueError('答案/判定无效')
            if not isinstance(r['attempt'],int) or r['attempt']<1: raise ValueError('attempt 必须为正整数')
            for a in self.all('answers'):
                if a['id']!=r['id'] and (a['question_id'],a['attempt'])==(r['question_id'],r['attempt']): raise ValueError('同题 attempt 重复')
            if r.get('score') is not None and not 0<=r['score']<=1: raise ValueError('score 需在 0..1')
        if k=='mistakes' and self.get('answers',r['answer_id'])['question_id']!=r['question_id']: raise ValueError('错题与答案题号不一致')
        if k=='reviews':
            dt.date.fromisoformat(r['due_date'])
            if r['status'] not in ('scheduled','completed','cancelled'): raise ValueError('复习状态无效')
            if r['status']=='completed':
                a=self.get('answers',r.get('result_answer_id',''))
                if not a or a['verdict']=='pending': raise ValueError('复测完成必须关联已批改回答')
                if not r.get('completed_at'): raise ValueError('复测完成需填写completed_at')
                dt.datetime.fromisoformat(r['completed_at'])
        if k=='topics':
            if r['id'] not in {t['id'] for t in read_yaml(self.root/'syllabus/topics.yaml')['topics']} or r['status'] not in STATUSES: raise ValueError('知识点/状态无效')
            if not isinstance(r['covered'],bool): raise ValueError('covered 必须为布尔值')
            if r['status']=='mastered':
                if not r['covered']: raise ValueError('稳定掌握必须已完成覆盖')
                evidence=[self.get('answers',x) for x in r['evidence']]
                if len({a['created_at'][:10] for a in evidence if a and a['verdict']=='correct' and self.get('questions',a['question_id'])['topic_id']==r['id']})<2: raise ValueError('稳定掌握至少需要两个不同日期的完整正确作答证据')
                if any(m['topic_id']==r['id'] and m['status']!='resolved' for m in self.all('mistakes')): raise ValueError('仍有未解决错题')
        if k=='sessions':
            dt.date.fromisoformat(r['date'])
            if r['duration_minutes'] is not None and (not isinstance(r['duration_minutes'],(int,float)) or r['duration_minutes']<0): raise ValueError('时长无效')
            if not isinstance(r['effective'],bool): raise ValueError('effective 必须为布尔值')
            if r['effective'] and not r.get('evidence'): raise ValueError('有效 session 需记录学习证据')
            for evidence in r.get('evidence',[]):
                if not self.get('answers',evidence) and not (evidence.startswith('knowledge/') and (self.root/evidence).is_file()): raise ValueError('session 证据应为回答 ID 或知识文件路径')
        if k=='mistakes' and r['status'] not in ('open','review','resolved'): raise ValueError('错题状态无效')
        if k=='mistakes' and r['status']=='resolved':
            a=self.get('answers',r.get('resolution_answer_id',''))
            if not a or a['verdict']!='correct' or a['created_at'][:10]<=r['created_at'][:10]: raise ValueError('解决错题需后续日期完整正确回答')
    def refresh(self,day):
        state=read_yaml(self.root/'state.yaml'); profile=read_yaml(self.root/'profile.yaml')
        topics=read_yaml(self.root/'syllabus/topics.yaml')['topics']; updates={t['id']:t for t in self.all('topics')}
        for m in self.all('mistakes'):
            if m['status']!='resolved' and updates.get(m['topic_id'],{}).get('status')=='mastered': updates[m['topic_id']]['status']='reviewing'
        def progress(ts):
            n=sum(t.get('weight',1) for t in ts)
            return {key:sum(t.get('weight',1)*bool(updates.get(t['id'],{}).get('covered') if key=='coverage' else updates.get(t['id'],{}).get('status')=='mastered') for t in ts)/n if n else None for key in ('coverage','mastery')}
        prog=progress(topics)
        prog['subjects']={s:progress([t for t in topics if t['subject']==s]) for s in sorted({t['subject'] for t in topics})}
        prog['chapters']={s:progress([t for t in topics if t['chapter']==s]) for s in sorted({t['chapter'] for t in topics})}
        answers=self.all('answers'); graded=[a for a in answers if a['verdict']!='pending']; mistakes=self.all('mistakes'); reviews=self.all('reviews'); sessions=self.all('sessions')
        dates=sorted({s['date'] for s in sessions if s['effective'] and s['date']<=day.isoformat()})
        run=longest=0; prev=None
        for d in dates:
            d=dt.date.fromisoformat(d); run=run+1 if prev and (d-prev).days==1 else 1; longest=max(longest,run); prev=d
        current=run if prev and (day-prev).days<=1 else 0
        stats={'learning_days':len(dates),'known_duration_minutes':sum(s['duration_minutes'] or 0 for s in sessions),'sessions_without_duration':sum(s['duration_minutes'] is None for s in sessions),
         'questions_answered':len({a['question_id'] for a in answers}),'attempts':len(answers),'graded_attempts':len(graded),
         'correct_rate':sum(a['verdict']=='correct' for a in graded)/len(graded) if graded else None,
         'open_mistakes':sum(m['status']!='resolved' for m in mistakes),'resolved_mistakes':sum(m['status']=='resolved' for m in mistakes),
         'repeated_mistakes':sum(m.get('error_count',1)>1 for m in mistakes),'completed_reviews':sum(r['status']=='completed' for r in reviews)}
        qs={q['id']:q for q in self.all('questions')}; tm={t['id']:t for t in topics}
        stats['chapter_correct_rate']={c:sum(a['verdict']=='correct' for a in graded if tm[qs[a['question_id']]['topic_id']]['chapter']==c)/len(aa) for c in prog['chapters'] if (aa:=[a for a in graded if tm[qs[a['question_id']]['topic_id']]['chapter']==c])}
        state.update(progress=prog,statistics=stats,study_streak={'current':current,'longest':longest,'last_study_date':dates[-1] if dates else None},last_session=dates[-1] if dates else None,
            review={'schedule':{r['id']:r['due_date'] for r in reviews if r['status']=='scheduled'}},updated_at=stamp())
        save_yaml(self.root/'state.yaml',state)
        summary={'date':day.isoformat(),**stats,**prog,**state['study_streak'],'days_to_exam':countdown(profile,day)}
        atomic(self.root/'stats/summary.json',json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        achieved={a['id'] for a in self.all('achievements')}
        candidates=[('ACH_STREAK_7','连续学习7天',longest>=7),('ACH_QUESTIONS_100','完成100道题',stats['questions_answered']>=100),('ACH_REVIEWS_50','完成50次复测',stats['completed_reviews']>=50)]
        candidates += [(f'ACH_COVERAGE_{s}',f'{s}首次完整覆盖',p['coverage']==1) for s,p in prog['subjects'].items()]
        for id,title,ok in candidates:
            if ok and id not in achieved: self.append('achievements',{'id':id,'title':title,'earned_at':day.isoformat(),'type':'milestone'})
        (self.root/'.dirty').unlink(missing_ok=True)
        return state
    def panel(self,day,start=False):
        profile=read_yaml(self.root/'profile.yaml'); s=read_yaml(self.root/'state.yaml'); n=countdown(profile,day)
        last=s['study_streak']['last_study_date']; streak=s['study_streak']['current'] if last and (day-dt.date.fromisoformat(last)).days<=1 else 0
        due=[id for id,d in s['review']['schedule'].items() if d<=day.isoformat()]
        pct=lambda x: '待建立大纲' if x is None else f'{x:.0%}'
        lines=[f"📚 {profile['exam']['name']} · {profile['exam']['subject']}", '🎯 考试日期待确认' if n is None else ('🎯 今天考试，稳住节奏。' if n==0 else f'🎯 距离考试：{n} 天' if n>0 else f'考试日期已过去 {-n} 天，请核对下一阶段目标。'),f"覆盖率 {pct(s['progress']['coverage'])} · 稳定掌握率 {pct(s['progress']['mastery'])}"]
        if n is not None and n>0:
            lines.insert(2,'稳定推进，先把基础补齐。' if n>60 else '进入强化阶段，继续按计划推进。' if n>30 else '减少知识盲区，重点处理错题。' if n>=15 else '优先高频知识、错题和稳定发挥。')
        lines += [f"{k}：覆盖 {pct(v['coverage'])} / 掌握 {pct(v['mastery'])}" for k,v in s['progress']['subjects'].items()]
        lines += [f"🔥 连续学习 {streak} 天 · 已答 {s['statistics']['questions_answered']} 题",f"待解决错题 {s['statistics']['open_mistakes']} · 今日复习 {len(due)} 项",'今天继续：'+ ' → '.join(str(s['current_course'][x]) for x in ('subject','chapter','lesson','next_task'))]
        if start and s.get('last_motivation_date')!=day.isoformat():
            category='return_after_break' if last and (day-dt.date.fromisoformat(last)).days>1 else 'exam_near' if n is not None and 0<=n<30 else 'streak' if streak in (7,14,30) else 'mistake' if s['statistics']['open_mistakes']>=5 else 'hard_topic' if '指针' in s['current_course']['lesson'] else 'normal'
            messages=read_yaml(self.root/'motivation/messages.yaml'); lines+=['',messages[category][day.toordinal()%len(messages[category])]]
            s['last_motivation_date']=day.isoformat(); save_yaml(self.root/'state.yaml',s)
        return '\n'.join(lines)
    def context(self,day):
        s=read_yaml(self.root/'state.yaml'); q=self.get('questions',s['current_course']['next_task']); cfg=read_yaml(self.root/'config/study_config.yaml')
        ids=sorted(s['review']['schedule'],key=s['review']['schedule'].get)
        due=[self.get('reviews',id) for id in ids if s['review']['schedule'][id]<=day.isoformat()][:cfg['context_review_limit']]
        mistakes=[self.get('mistakes',r['mistake_id']) for r in due]
        current=self.root/s['current_course']['knowledge_file']; content=current.read_text('utf-8')[:cfg['context_knowledge_chars']]
        recent=sorted((self.root/'sessions').glob('????-??-??.md'),reverse=True)[:2]
        from rag import search
        topic_id = mistakes[0]['topic_id'] if mistakes else s['current_course']['topic_id']
        topics = read_yaml(self.root/'syllabus/topics.yaml')['topics']
        topic = next(t for t in topics if t['id'] == topic_id)
        try:
            references = search(topic['title'], topic=topic_id, limit=3, max_chars=2400,
                                kb=self.root.parent/'knowledge_base', study_root=self.root)
        except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
            references = {'status': 'unavailable', 'hits': [], 'error': str(exc),
                          'hint': '资料索引暂不可用；运行 rag.py check 核对，不编造出处。'}
        return {'references': references, 'reference_topic': topic_id, 'current_question':q,'knowledge':content,'reviews':due,'mistakes':mistakes,'review_questions':[self.get('questions',m['question_id']) for m in mistakes], 'original_answers':[self.get('answers',m['answer_id']) for m in mistakes], 'recent_sessions':[p.read_text('utf-8')[:cfg['context_session_chars']] for p in recent], 'remaining_reviews':max(0,sum(d<=day.isoformat() for d in s['review']['schedule'].values())-len(due))}
    def close_day(self,day):
        s=self.refresh(day); p=self.root/'stats/history.jsonl'; rows=[json.loads(x) for x in p.read_text('utf-8').splitlines()]
        snapshot=json.loads((self.root/'stats/summary.json').read_text('utf-8'))
        # One logical snapshot/day; closing again updates that day's snapshot atomically.
        before=next((r for r in reversed(rows) if r['date']<day.isoformat()),None)
        rows=[r for r in rows if r['date']!=day.isoformat()]+[snapshot]
        atomic(p,'\n'.join(dump(r) for r in sorted(rows,key=lambda r:r['date']))+'\n')
        answers=[a for a in self.all('answers') if a['created_at'][:10]==day.isoformat()]
        sessions=[x for x in self.all('sessions') if x['date']==day.isoformat()]
        duration=sum(x['duration_minutes'] or 0 for x in sessions)
        time_text=f'{duration} 分钟（已报告部分）' if duration else '未报告'
        report=f"# {day} 学习小结\n\n学习时长：{time_text}；作答 {len(answers)} 次，完整正确 {sum(a['verdict']=='correct' for a in answers)} 次。\n\n"+'\n'.join(f"- {x['summary']}；下一步：{x['next_task']}" for x in sessions)
        atomic(self.root/f'sessions/{day}.md',report+'\n')
        new_errors=sum(m['created_at'][:10]==day.isoformat() for m in self.all('mistakes'))
        completed=sum(r['status']=='completed' and r.get('completed_at','')[:10]==day.isoformat() for r in self.all('reviews'))
        report+=f'\n\n新增错题 {new_errors}；完成复测 {completed}。下一步：{s["current_course"]["next_task"]}。'
        return report+f"\n\n覆盖率：{format(before['coverage'],'.0%') if before else '无前日快照'} → {s['progress']['coverage']:.0%}；连续 {s['study_streak']['current']} 天。"
    def repair(self,k):
        p=self.path(k); raw=p.read_bytes(); end=raw.rfind(b'\n')+1
        if end==len(raw): return '没有不完整尾行；中部损坏请依据备份人工核对。'
        backup=self.root/'archive'/f'{k}-tail-{dt.datetime.now().strftime("%Y%m%d%H%M%S%f")}.bin'
        backup.write_bytes(raw); atomic(p,raw[:end].decode('utf-8')); return f'完整原文件已备份：{backup}；不完整尾行已隔离，请人工核对。'

def countdown(profile,day):
    value=profile['exam'].get('exam_date'); return (dt.date.fromisoformat(value)-day).days if value else None

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--root',default=str(Path(__file__).parent/'study')); ap.add_argument('--date',type=dt.date.fromisoformat,default=today())
    sub=ap.add_subparsers(dest='cmd',required=True)
    for cmd in ('panel','start','context','refresh','close','check','readme'): sub.add_parser(cmd)
    rec=sub.add_parser('record'); rec.add_argument('kind',choices=TABLES); rec.add_argument('file',type=Path)
    get=sub.add_parser('get'); get.add_argument('kind',choices=TABLES); get.add_argument('id')
    current=sub.add_parser('current'); current.add_argument('question_id')
    fix=sub.add_parser('repair'); fix.add_argument('kind',choices=TABLES)
    args=ap.parse_args(); s=Store(args.root)
    with s.lock():
        if (s.root/'.dirty').exists() and args.cmd!='repair': s.refresh(args.date)
        if args.cmd in ('panel','start'): result=s.panel(args.date,args.cmd=='start')
        elif args.cmd=='context': result=s.context(args.date)
        elif args.cmd=='readme':
            from scripts.readme_progress import update
            result='README进度已更新。' if update(s.root) else 'README缺少进度标记，未修改。'
        elif args.cmd=='get': result=s.get(args.kind,args.id)
        elif args.cmd=='current':
            q=s.get('questions',args.question_id)
            if not q: raise ValueError('题目不存在')
            topic=next(t for t in read_yaml(s.root/'syllabus/topics.yaml')['topics'] if t['id']==q['topic_id'])
            state=read_yaml(s.root/'state.yaml'); state['current_course']={'subject':topic['subject'],'chapter':topic['chapter_title'],'lesson':topic['title'],'topic_id':topic['id'],'next_task':q['id'],'knowledge_file':topic['knowledge_file']}
            save_yaml(s.root/'state.yaml',state); result='已切换当前学习任务。'
        elif args.cmd=='record': s.append(args.kind,json.loads(args.file.read_text('utf-8'))); s.refresh(args.date); result='已保存，状态已更新。'
        elif args.cmd=='refresh': result=s.refresh(args.date)
        elif args.cmd=='close': result=s.close_day(args.date)
        elif args.cmd=='repair': result=s.repair(args.kind)
        else:
            for k in TABLES:
                for r in s.all(k): s.validate(k,r)
            result='所有最新记录格式与关联检查通过。'
        if args.cmd in ('record', 'refresh', 'close', 'current'):
            from scripts.readme_progress import update
            update(s.root)
    print(result if isinstance(result,str) else json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':
    try: main()
    except (ValueError,KeyError,OSError) as e: raise SystemExit(str(e))
