import datetime as dt
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from study import Store, read_yaml, save_yaml, countdown
from scripts.migrate_study_archive import migrate

BASE=Path(__file__).resolve().parents[1]/'study'
class StudyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'study'; shutil.copytree(BASE,self.root); self.s=Store(self.root); self.day=dt.date(2026,10,8)
        state=read_yaml(self.root/'state.yaml'); state['last_motivation_date']=None; save_yaml(self.root/'state.yaml',state)
    def tearDown(self): self.tmp.cleanup()
    def test_truth_and_links(self):
        answers=self.s.all('answers'); questions={q['id'] for q in self.s.all('questions')}
        self.assertTrue(all(a['question_id'] in questions for a in answers))
        self.assertTrue(all(a['submitted_values_correct'] for a in answers if a['verdict']=='correct'))
        self.assertEqual([a['id'] for a in answers if a['question_id']=='S001-1'],['A0019'])
        for k in ('questions','answers','mistakes','reviews','topics','sessions'):
            for r in self.s.all(k): self.s.validate(k,r)
    def test_dates_streak_motivation(self):
        self.s.refresh(self.day)
        self.assertIn('72 天',self.s.panel(self.day))
        due=sum(1 for d in read_yaml(self.root/'state.yaml')['review']['schedule'].values() if d<=(self.day+dt.timedelta(days=1)).isoformat())
        self.assertIn(f'今日复习 {due} 项',self.s.panel(self.day+dt.timedelta(days=1)))
        self.assertIn('连续学习 0 天',self.s.panel(self.day+dt.timedelta(days=2)))
        self.assertGreater(len(self.s.panel(self.day,True)),len(self.s.panel(self.day,True)))
        profile=read_yaml(self.root/'profile.yaml'); profile['exam']['exam_date']=None
        self.assertIsNone(countdown(profile,self.day))
    def test_streak_same_day_and_gap(self):
        base=self.s.all('sessions')[0]
        # Isolate these dates from later real learning sessions in the repository.
        self.s.path('sessions').write_text(json.dumps({**base,'date':self.day.isoformat()},ensure_ascii=False)+'\n',encoding='utf-8')
        self.s.append('sessions',{**base,'id':'S_extra','summary':'第二课'})
        self.assertEqual(self.s.refresh(self.day)['study_streak']['current'],1)
        self.s.append('sessions',{**base,'id':'S20261009','date':'2026-10-09'})
        self.assertEqual(self.s.refresh(dt.date(2026,10,9))['study_streak']['current'],2)
        self.assertEqual(self.s.refresh(dt.date(2026,10,11))['study_streak']['current'],0)
    def test_raw_immutable_and_revision(self):
        a=self.s.get('answers','A0001'); old=self.s.path('answers').read_bytes(); n=len(self.s.all('answers'))
        with self.assertRaises(ValueError): self.s.append('answers',{**a,'answer':'fake'})
        self.assertEqual(old,self.s.path('answers').read_bytes())
        self.s.append('answers',{**a,'feedback':'补充核对说明'})
        self.assertTrue(self.s.path('answers').read_bytes().startswith(old))
        self.assertEqual(self.s.get('answers','A0001')['answer'],a['answer'])
        self.assertEqual(len(self.s.all('answers')),n)
    def test_tail_recovery(self):
        p=self.s.path('answers'); original=p.read_bytes(); n=len(self.s.all('answers')); p.write_bytes(original+b'{"id":')
        with self.assertRaises(ValueError): self.s.index('answers')
        self.s.repair('answers'); self.assertEqual(p.read_bytes(),original)
        self.assertEqual(len(self.s.all('answers')),n)
        self.assertEqual(next((self.root/'archive').glob('answers-tail-*')).read_bytes(),original+b'{"id":')
    def test_no_false_mastery(self):
        with self.assertRaises(ValueError): self.s.append('topics',{'id':'C09.T4','status':'mastered','covered':True,'evidence':['A0014','A0015']})
    def test_context_bounded(self):
        c=self.s.context(dt.date(2026,10,9)); self.assertEqual(c['current_question']['id'],read_yaml(self.root/'state.yaml')['current_course']['next_task']); self.assertLessEqual(len(c['reviews']),5); self.assertLessEqual(len(c['recent_sessions']),2)
        self.assertNotIn('版本变更',c['knowledge'])
    def test_snapshot_idempotent(self):
        self.s.close_day(self.day); first=(self.root/'stats/history.jsonl').read_text('utf-8'); self.s.close_day(self.day)
        self.assertEqual(first,(self.root/'stats/history.jsonl').read_text('utf-8'))
        self.assertEqual(sum(json.loads(line)['date']==self.day.isoformat() for line in first.splitlines()),1)
    def test_archive_and_migration(self):
        m=json.loads((self.root/'archive/migration_manifest.json').read_text('utf-8')); src=self.root/m['archive']
        self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(),m['sha256'])
        self.assertIn('无重复',migrate(src,self.root))
        fresh=Path(self.tmp.name)/'fresh'; migrate(src,fresh)
        self.assertEqual(len(Store(fresh).all('answers')),18)
        unknown=Path(self.tmp.name)/'unknown.md'; unknown.write_text('未知档案：不能编造记录',encoding='utf-8')
        other=Path(self.tmp.name)/'unknown'; self.assertIn('仅归档',migrate(unknown,other)); self.assertFalse((other/'profile.yaml').exists())
if __name__=='__main__': unittest.main()
