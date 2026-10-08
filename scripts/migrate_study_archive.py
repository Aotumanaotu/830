#!/usr/bin/env python3
"""Conservative importer for the known v1.18 archive; other formats are archived only."""
import argparse, hashlib, json, re, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from study import Store, TABLES, atomic, save_yaml, dt

KNOWN='07bbd138166949fe53d1a947e76692b20cff15c69e93fe6878ac913e5c899dc0'
def migrate(source,root):
    raw=source.read_bytes(); sha=hashlib.sha256(raw).hexdigest(); text=raw.decode('utf-8')
    root.mkdir(parents=True,exist_ok=True); archive=root/'archive'/f'study_archive_{sha[:12]}.md'
    archive.parent.mkdir(exist_ok=True)
    if archive.exists() and archive.read_bytes()!=raw: raise ValueError('归档冲突')
    if not archive.exists(): archive.write_bytes(raw)
    manifest=root/'archive/migration_manifest.json'
    if manifest.exists():
        if json.loads(manifest.read_text('utf-8'))['sha256']==sha: return '该快照已迁移，无重复写入。'
        raise ValueError('已有迁移记录，新档案已归档；需要人工核对增量，未覆盖学习数据。')
    if sha != KNOWN:
        atomic(root/'migration_report.md',f'# 迁移报告\n\n未知格式；仅归档，迁移0条。SHA256: {sha}\n'); return '仅归档；未知格式不自动关联。'
    if (root/'profile.yaml').exists(): raise ValueError('目标已有学习状态，拒绝初始化覆盖')
    for p in TABLES.values():
        path=root/p; path.parent.mkdir(parents=True,exist_ok=True); path.touch()
    for p in ['stats/history.jsonl','summaries/weekly/.gitkeep','summaries/milestone/.gitkeep']:
        path=root/p; path.parent.mkdir(parents=True,exist_ok=True); path.touch()
    save_yaml(root/'profile.yaml',{'version':2,'exam':{'name':'中国地质大学（武汉）2027研究生初试','subject':'830 计算机软件综合','exam_date':'2026-12-19','date_basis':'初试首日；沿用原档案官方日期来源，专业课具体场次未录入','date_source':'https://www.moe.gov.cn/jyb_xwfb/gzdt_gzdt/s5987/202609/t20260924_1451846.html'},'goal':{'target_score':None},'study':{'start_date':'2026-10-08','timezone':'Asia/Shanghai','weekday_daily_max_hours':4,'weekend_max_hours':12,'weekend_scope':'待确认：每天还是两天合计','scope':['830'],'excluded':['公共课','复试']}})
    save_yaml(root/'config/study_config.yaml',{'context_review_limit':5,'context_knowledge_chars':10000,'context_session_chars':3000,'mastery_rule':'至少两个不同日期完整正确回答且无未解决错题；由助教依据独立复测证据申请更新','progress_rule':'按大纲分解知识点等权计数，非试卷分值预测；提供提要不计覆盖','xp_enabled':False})
    save_yaml(root/'motivation/messages.yaml',{'normal':['今天先解决眼前这一小节。'],'hard_topic':['*p、p、&p 又见面了。今天看看是谁先认输。'],'mistake':['这些错现在出现正合适，考试还没开始。'],'streak':['已经开始形成习惯了，今天继续一小步。'],'return_after_break':['欢迎回来。记录还在，进度也没跑。'],'exam_near':['会的东西越来越稳，比临时多塞一章更有用。'],'good_progress':['昨天难住你的，今天少了一点。'],'milestone':['把“我见过”慢慢变成“我会做”。']})
    outline=text[text.index('## 4.'):text.index('## 5.')]; atomic(root/'syllabus/exam_outline.md',outline)
    atomic(root/'config/original_plan.md',text[text.index('## 2.'):text.index('## 4.')])
    topics=[]
    for line in outline.splitlines():
        if re.match(r'\| [CD]\d\d \|',line):
            _,code,name,contents,task,_=line.split('|')
            code=code.strip()
            for i,title in enumerate(contents.strip().split('、'),1):
                topics.append({'id':f'{code}.{i:02}','subject':'C语言' if code[0]=='C' else '数据结构','chapter':code,'chapter_title':name.strip(),'title':title,'weight':1,'knowledge_file':f'knowledge/{"c_language" if code[0]=="C" else "data_structure"}/{code}.md'})
    # Split broad list items where actual taught subtopics need independent evidence.
    extras={'C03':['整数除法与类型转换','后缀自增与复合赋值'],'C08':['值传递与指针参数','数组作为函数参数'],'C09':['地址与解引用','指针赋值与指向','数组指针移动','指针自增与元素自增'],'C10':['结构体定义与成员访问']}
    # Extra taught units are subdivisions with zero double counting: retain remaining broader syllabus items with an explicit remainder label.
    for chapter,titles in extras.items():
        for t in topics:
            if t['chapter']==chapter: t['title']+='（除下列已拆分入门专题外的其余要求）'
        for i,title in enumerate(titles,1): topics.append({'id':f'{chapter}.T{i}','subject':'C语言','chapter':chapter,'chapter_title':next(t['chapter_title'] for t in topics if t['chapter']==chapter),'title':title,'weight':1,'knowledge_file':f'knowledge/c_language/{chapter}.md'})
    save_yaml(root/'syllabus/topics.yaml',{'version':1,'weight_basis':'每个列出的知识点等权，非官方分值；入门专题与其余要求分别计数','topics':topics})
    chunks=re.split(r'(?=^### 5\.\d+ )',text[text.index('## 5.'):text.index('## 6.')],flags=re.M)[1:]
    mapping={'C01':0,'C02':0,'C03':1,'C04':1,'C05':2,'C06':2,'C07':3,'C08':4,'C09':5,'C10':6,'C11':6,'D01':0,'D02':7,'D03':7,'D04':8,'D05':8,'D06':9,'D07':10,'D08':11,'D09':12}
    lessons={m.group(1):m.group(0) for m in re.finditer(r'^### ((?:P\d{3}|S001|L001-1)) .*?(?=^### |^## |\Z)',text,flags=re.M|re.S)}
    for chapter,ix in mapping.items():
        subject='c_language' if chapter[0]=='C' else 'data_structure'
        extra='\n'.join(v.split('原创')[0] for k,v in lessons.items() if (chapter=='C09' and k.startswith('P') and k!='P009') or (chapter=='C08' and k=='P009') or (chapter=='C10' and k=='S001'))
        atomic(root/f'knowledge/{subject}/{chapter}.md',f'# {chapter} {next(t["chapter_title"] for t in topics if t["chapter"]==chapter)}\n\nSubject: {subject}\nTopic: {chapter}\n来源：历史档案第5节及对应讲解；提要不等于已掌握。\n\n'+chunks[ix]+'\n'+extra)
    save_yaml(root/'state.yaml',{'version':2,'current_course':{'subject':'C语言','chapter':'结构体','lesson':'结构体与结构体指针','topic_id':'C10.T1','next_task':'S001-1','knowledge_file':'knowledge/c_language/C10.md'},'last_motivation_date':None})
    s=Store(root)
    ids=['L001-1','L001-R1','P001-1','P002-1','P003-1','P004-1','P005-1','P005-R1','P006-1','P007-1','P008-1','P008-R1','P008-R2','P008-R3','P008-R4','P008-R5','P009-1','P009-R1','S001-1']
    topic_ids=['C03.T1']*2+['C09.T1','C09.T2','C09.T2','C08.T1','C08.T1','C08.T1','C08.T1','C09.T3','C09.T4','C03.T2','C09.T4','C09.T4','C09.T4','C09.T4','C08.T2','C08.T2','C10.T1']
    originals=['x=2,y=2.2222222222222222','x=3 y=3.5 z=3.0','a=30 b=10 *p=30','a=15 b=25 *p=25','a=30 b=40 *p=40 *q=30','10\n50','*x\n*y\na\nb','&n 9','a=10,b=50,*r=10 r最后指向a','10 99 30 *p=99 *(p+1)=30','x=20 y=21 分别是10 21 30 p指向a·[1] *p=21','5 6 7','x=4 y=8\n4 9 12\np指向a[1],*p=9','x=3 分别是4和7 p指向a[0] *p=4','6 6和9 p指向a[1] *p=9','1:x=2 {3, 5, 8} p指向a[0]\n2:y=3 {3, 5, 8} p指向a[1]','2 4 5 不会改变的原因是n的大小限制的每一个数据元素加一的进度','4 4 6、']
    partial={0,6,10,12,16}; incomplete={1,2,3,4,5,15}
    for i,(id,topic) in enumerate(zip(ids,topic_ids)):
        if id=='L001-1':
            question=re.search(r'^L001-1：.*',text,re.M).group(); evaluation=text[text.index('### L001-1 批改'):text.index('立即变式 L001-R1')]
        else:
            match=re.search(r'^(?:原创[^\n]*|立即变式) '+re.escape(id)+r'[（\s].*',text,re.M)
            if not match: raise ValueError(f'未识别题干 {id}')
            start=match.end(); end=text.find('\n'+id+' 批改',start)
            if id=='L001-R1': end=text.index('\n2026-10-08 用户原答案',start)
            if id=='S001-1': end=text.index('\n## 7.',start)
            if end<0: raise ValueError(f'未识别边界 {id}')
            question=text[start:end].strip(); evaluation='' if id=='S001-1' else text[end:text.find('\n\n',end+1)].strip()
            if id=='P009-R1': question='沿用函数：void update(int a[], int n) { for(int i=0;i<n;i++) a[i]+=2; }\n'+question
        s.append('questions',{'id':id,'topic_id':topic,'question':question,'type':'code','difficulty':None,'source':{'archive':str(archive.relative_to(root)),'sha256':sha,'original_id':id},'tags':['历史迁移'],'created_at':'2026-10-08'})
        if i<len(originals): s.append('answers',{'id':f'A{i+1:04}','question_id':id,'attempt':1,'answer':originals[i],'verdict':'partial' if i in partial else 'incomplete' if i in incomplete else 'correct','submitted_values_correct':i not in partial,'score':None,'feedback':evaluation,'explanation':evaluation,'created_at':'2026-10-08','time_precision':'day','source':'原档案批改＋当前对话原始回答（保留换行）；历史未提供标准分数'})
    mistake_lines=[l for l in text.splitlines() if re.match(r'\| E00[1-5] /',l)]
    answer_index=[0,6,10,12,16]
    for j,line in enumerate(mistake_lines):
        cells=[x.strip() for x in line.split('|')[1:-1]]; ai=answer_index[j]; id=f'E{j+1:03}'
        s.append('mistakes',{'id':id,'question_id':ids[ai],'answer_id':f'A{ai+1:04}','topic_id':topic_ids[ai],'mistake_type':'needs_confirmation' if j in (0,1,4) else 'state_tracking','reason':cells[3],'correction':cells[4],'status':'review','error_count':1,'first_seen':'2026-10-08','last_seen':'2026-10-08','created_at':'2026-10-08','immediate_review_note':cells[7]})
        s.append('reviews',{'id':f'R{j+1:04}','mistake_id':id,'reason':'即时变式后进行独立延迟复测','due_date':'2026-10-09','status':'scheduled','review_count':0,'last_result':None,'created_at':'2026-10-08'})
    for t in topics:
        taught='.T' in t['id']
        s.append('topics',{'id':t['id'],'status':'practicing' if taught and t['id']!='C10.T1' else 'learning' if taught else 'not_started','covered':taught,'evidence':[f'A{i+1:04}' for i,x in enumerate(topic_ids[:-1]) if x==t['id']],'lecture_source':str(archive.relative_to(root)) if taught else None,'created_at':'2026-10-08'})
    s.append('sessions',{'id':'S20261008','date':'2026-10-08','effective':True,'duration_minutes':None,'evidence':[f'A{i:04}' for i in range(1,19)],'summary':'表达式、指针、函数参数练习18次；5项错因待隔日复测；结构体入门已讲解，S001-1未答。','next_task':'S001-1','created_at':'2026-10-08'})
    s.close_day(dt.date(2026,10,8))
    atomic(manifest,json.dumps({'sha256':sha,'archive':str(archive.relative_to(root)),'questions':19,'answers':18,'mistakes':5,'reviews':5},ensure_ascii=False,indent=2))
    atomic(root/'migration_report.md',f'''# 迁移报告\n\n原档案完整保留，SHA256：{sha}\n\n- 19道当前训练题（18道已答，S001-1待答）；18份原始回答；5项错题；5项待延迟复测；1个有证据的学习日。\n- 没有可核实学习时长，保留 null；不从聊天间隔推断。历史成绩仅保留分类，不补分数。\n- 13次提交的数值结果正确，其中6次有遗漏要求，标为 incomplete；完整正确7次，部分正确5次。完整正确率按7/18计，仅反映已迁移练习。\n- 知识点等权覆盖率是目录计数，不代表试卷分值，也不代表历次真实正确率。稳定掌握尚无跨日证据。\n- 初始诊断8题、未提交L001-2～4、其他例题、版本日志和完整批改过程仍保留在archive；未强行认定为已完成题目。\n- 提要按大纲拆分；部分共用讲解保留，未来扩写时进一步拆细。原文件之外未推断新学习事实。\n- 原文个别回答使用斜杠代替换行，依据本次对话还原换行，原档案仍字节级保留。\n- 本迁移器只识别v1.18，未知格式仅归档。重复运行同SHA不重复写；新快照不覆盖现有状态。\n''')
    return '迁移完成'
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('source',type=Path); p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]/'study'); a=p.parse_args(); print(migrate(a.source,a.root))
