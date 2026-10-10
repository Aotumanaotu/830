import datetime as dt
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from study import Store, TABLES, read_yaml
from scripts.readme_progress import update

BASE=Path(__file__).resolve().parents[1]


class FastWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'study'
        shutil.copytree(BASE/'study',self.root)
        self.s=Store(self.root); self.day=dt.date(2026,10,10)
    def tearDown(self): self.tmp.cleanup()
    def payload(self):
        q={'id':'P_TEST_BATCH','topic_id':'C09.T4','question':'测试隔离副本里的题目'}
        a={'id':'A_TEST_BATCH','question_id':q['id'],'attempt':1,'answer':'真实测试输入','verdict':'pending'}
        return {'records':[{'kind':'questions','record':q},{'kind':'answers','record':a},{'kind':'answers','record':{**a,'verdict':'correct','submitted_values_correct':True}}], 'current_question':q['id']}
    def test_batch_preserves_pending_and_grading_one_refresh(self):
        raw=self.s.path('answers').read_text()
        with self.s.lock(),patch.object(self.s,'refresh',wraps=self.s.refresh) as refresh:
            result=self.s.record_batch(self.payload(),self.day)
        self.assertEqual(result['saved_records'],3); self.assertEqual(refresh.call_count,1)
        added=[json.loads(line) for line in self.s.path('answers').read_text()[len(raw):].splitlines()]
        self.assertEqual([a['verdict'] for a in added],['pending','correct'])
        self.assertEqual(added[0]['answer'],added[1]['answer']); self.assertEqual(added[0]['created_at'],added[1]['created_at'])
        self.assertEqual(read_yaml(self.root/'state.yaml')['current_course']['next_task'],'P_TEST_BATCH')
    def test_invalid_late_entry_writes_nothing(self):
        payload=self.payload(); payload['records'].append({'kind':'reviews','record':{'id':'R_BAD','mistake_id':'missing','due_date':'2026-10-11','status':'scheduled'}})
        before={k:self.s.path(k).read_bytes() for k in TABLES}; state=(self.root/'state.yaml').read_bytes()
        with self.s.lock(),self.assertRaises(ValueError): self.s.record_batch(payload,self.day)
        self.assertEqual(before,{k:self.s.path(k).read_bytes() for k in TABLES}); self.assertEqual(state,(self.root/'state.yaml').read_bytes())
    def test_batch_cannot_rewrite_raw_answer_or_bad_current(self):
        for change in ('answer','current'):
            p=self.payload()
            if change=='answer': p['records'][2]['record']['answer']='偷偷改写原文'
            else: p['current_question']='missing'
            before=self.s.path('questions').read_bytes()
            with self.s.lock(),self.assertRaises(ValueError): self.s.record_batch(p,self.day)
            self.assertEqual(before,self.s.path('questions').read_bytes())
    def test_compact_no_rag_and_retains_unabridged_question(self):
        with patch('rag.search',side_effect=AssertionError('不应默认检索')):
            compact=self.s.compact_context(self.day)
        q=self.s.get('questions',read_yaml(self.root/'state.yaml')['current_course']['next_task'])
        self.assertEqual(compact['current_question']['question'],q['question'])
        self.assertNotIn('knowledge',compact); self.assertNotIn('original_answers',compact)
        self.assertLessEqual(len(compact['due_reviews']),3)
    def test_svg_exact_metrics_valid_xml_and_idempotent(self):
        readme=self.root.parent/'README.md'; readme.write_text('<!-- STUDY_PROGRESS_START -->old<!-- STUDY_PROGRESS_END -->')
        state_before=(self.root/'state.yaml').read_bytes();update(self.root)
        assets=list((self.root.parent/'assets').glob('*.svg')); self.assertEqual(len(assets),2)
        for p in assets: ElementTree.fromstring(p.read_text())
        overview=(self.root.parent/'assets/study-progress.svg').read_text()
        self.assertIn(f"{read_yaml(self.root/'state.yaml')['progress']['coverage']*100:.1f}%",overview)
        self.assertIn('assets/study-progress.svg',readme.read_text())
        before={p:p.stat().st_mtime_ns for p in [readme,*assets]};update(self.root)
        self.assertEqual(before,{p:p.stat().st_mtime_ns for p in before})
        self.assertEqual(state_before,(self.root/'state.yaml').read_bytes())


if __name__=='__main__': unittest.main()
