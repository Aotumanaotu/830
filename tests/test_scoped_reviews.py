import shutil
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from study import Store


class ScopedReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        root=Path(self.tmp.name)/'study'
        shutil.copytree(Path(__file__).resolve().parents[1]/'study',root)
        self.s=Store(root)
        self.mistakes={}
        with self.s.lock():
            self.s.append('questions',{'id':'Q_SCOPE_OLD','topic_id':'C10.T1','question':'原错题'})
            self.s.append('answers',{'id':'A_SCOPE_OLD','question_id':'Q_SCOPE_OLD','attempt':1,'answer':'原始错误','verdict':'incorrect','created_at':'2026-10-10'})
            for suffix in ('A','B'):
                m={'id':'M_SCOPE_'+suffix,'question_id':'Q_SCOPE_OLD','answer_id':'A_SCOPE_OLD','topic_id':'C10.T1','reason':'不同考点','status':'review','created_at':'2026-10-10'}
                self.s.append('mistakes',m); self.mistakes[suffix]=m
                self.s.append('reviews',{'id':'R_SCOPE_'+suffix,'mistake_id':m['id'],'due_date':'2026-10-12','status':'scheduled'})
            self.s.append('questions',{'id':'Q_SCOPE_JOINT','topic_id':'C10.T1','question':'合并复测，A正确、B错误','review_targets':[{'review_id':'R_SCOPE_A','mistake_id':'M_SCOPE_A','question_items':[1]},{'review_id':'R_SCOPE_B','mistake_id':'M_SCOPE_B','question_items':[2]}]})
            self.answer={'id':'A_SCOPE_JOINT','question_id':'Q_SCOPE_JOINT','attempt':1,'answer':'完整原文同时包含正确与错误部分','verdict':'partial','created_at':'2026-10-12','review_results':{'R_SCOPE_A':'correct','R_SCOPE_B':'incorrect'}}
            self.s.append('answers',self.answer)

    def tearDown(self): self.tmp.cleanup()

    def resolution(self,suffix,rid):
        return {**self.mistakes[suffix],'status':'resolved','resolution_answer_id':'A_SCOPE_JOINT','resolution_review_id':rid}

    def test_correct_target_resolves_without_rewriting_joint_answer(self):
        with self.s.lock(): self.s.append('mistakes',self.resolution('A','R_SCOPE_A'))
        self.assertEqual(self.s.get('mistakes','M_SCOPE_A')['status'],'resolved')
        self.assertEqual(self.s.get('mistakes','M_SCOPE_B')['status'],'review')
        self.assertEqual(self.s.get('answers','A_SCOPE_JOINT')['verdict'],'partial')
        self.assertEqual(self.s.get('answers','A_SCOPE_JOINT')['answer'],self.answer['answer'])

    def test_other_target_or_failed_target_cannot_resolve(self):
        for rid in ('R_SCOPE_A','R_SCOPE_B'):
            with self.subTest(rid=rid),self.s.lock(),self.assertRaises(ValueError):
                self.s.append('mistakes',self.resolution('B',rid))

    def test_partial_without_explicit_scope_cannot_resolve(self):
        row=self.resolution('A','R_SCOPE_A'); row.pop('resolution_review_id')
        with self.s.lock(),self.assertRaises(ValueError): self.s.append('mistakes',row)

    def test_same_day_target_still_cannot_resolve(self):
        answer={**self.answer,'id':'A_SCOPE_SAME_DAY','attempt':2,'created_at':'2026-10-10'}
        with self.s.lock():
            self.s.append('answers',answer)
            row={**self.resolution('A','R_SCOPE_A'),'resolution_answer_id':answer['id']}
            with self.assertRaises(ValueError): self.s.append('mistakes',row)

    def test_pending_or_undeclared_scope_cannot_claim_result(self):
        for changes in ({'verdict':'pending'},{'review_results':{'R0016':'correct'}}):
            with self.subTest(changes=changes),self.s.lock(),self.assertRaises(ValueError):
                self.s.append('answers',{**self.answer,'id':'A_SCOPE_INVALID','attempt':2,**changes})


if __name__=='__main__': unittest.main()
