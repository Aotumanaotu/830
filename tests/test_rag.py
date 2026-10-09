import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import yaml
import rag
from scripts.ingest_materials import classify
from scripts.readme_progress import update

BASE = Path(__file__).resolve().parents[1]

class RagTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name); self.kb = self.root / 'knowledge_base'; self.study = self.root / 'study'
        (self.kb / 'corpus').mkdir(parents=True); (self.study / 'knowledge').mkdir(parents=True)
        (self.kb / 'taxonomy.yaml').write_text((BASE / 'knowledge_base/taxonomy.yaml').read_text('utf-8'), encoding='utf-8')
        self.sources = []
        self.add_source('SRC-a', 'notes', '结构体通过指针访问成员。p->x 等价于 (*p).x。', '结构体笔记', 'text')
        self.add_source('SRC-b', 'slides', '循环队列 队列判空 front 等于 rear。', '队列课件', 'text')
        self.add_source('SRC-c', 'supplement', '结构体 成员 指针 struct 成员访问。', '其他考试结构体', 'ocr')
        self.write_manifest()
    def tearDown(self): self.tmp.cleanup()
    def add_source(self, sid, kind, text, title, method):
        row = dict(source_id=sid, source_sha256='x', page=1, locator='page', method=method,
                   quality='needs_visual_check' if method == 'ocr' else 'text_extracted', ocr_confidence=.8 if method == 'ocr' else None, text=text)
        raw = json.dumps(row, ensure_ascii=False) + '\n'
        (self.kb / f'corpus/{sid}.jsonl').write_text(raw, encoding='utf-8')
        self.sources.append(dict(id=sid, sha256='x', title=title, path=f'materiel/{title}.pdf', kind=kind, status='indexed', pages=1, corpus=f'corpus/{sid}.jsonl', corpus_sha256=hashlib.sha256(raw.encode()).hexdigest()))
    def write_manifest(self): (self.kb / 'sources.json').write_text(json.dumps({'sources': self.sources}), encoding='utf-8')
    def search(self, query, **kwargs): return rag.search(query, kb=self.kb, study_root=self.study, **kwargs)
    def test_chinese_retrieval_citation_and_scope(self):
        r = self.search('成员访问', topic='C10.T1')
        self.assertEqual(r['hits'][0]['source_id'], 'SRC-a')
        self.assertIn('p1:c0', r['hits'][0]['citation'])
        self.assertEqual(r['hits'][0]['page'], 1)
        self.assertNotIn('SRC-c', [x['source_id'] for x in r['hits']])
        r = self.search('结构体', include_supplement=True, kind='supplement')
        self.assertEqual(r['hits'][0]['method'], 'ocr')
        self.assertEqual(self.search('结构体', topic='D03')['hits'], [])
        self.assertEqual(self.search('zxqv_nonexistent')['status'], 'no_match')
    def test_safe_query_limits_and_lookup(self):
        self.assertLessEqual(sum(len(x['text']) for x in self.search('结构体', max_chars=120)['hits']), 120)
        self.search('" OR * - : NEAR(')
        with self.assertRaises(ValueError): self.search('结构体', limit=0)
        hit = self.search('结构体')['hits'][0]
        self.assertEqual(rag.get_chunk(hit['id'], self.kb, self.study)['text'], hit['text'])
        with self.assertRaises(ValueError): rag.get_chunk('missing', self.kb, self.study)
    def test_explicit_algorithm_name_beats_expanded_alias(self):
        text = '最短路径 Dijkstra Floyd 图算法。'
        self.add_source('SRC-dijkstra', 'slides', text, 'Dijkstra算法', 'text')
        self.add_source('SRC-floyd', 'slides', text + '比较。', 'Floyd算法', 'text')
        self.write_manifest()
        result = self.search('最短路径 Dijkstra', topic='D07')
        self.assertEqual(result['hits'][0]['source_id'], 'SRC-dijkstra')
    def test_rebuild_after_change_and_integrity(self):
        self.search('结构体')
        (self.study / 'knowledge/C10.md').write_text('结构体 新增独立检索用词 uniqueword', encoding='utf-8')
        self.assertEqual(self.search('uniqueword')['hits'][0]['kind'], 'knowledge')
        self.assertEqual(rag.check(self.kb, self.study)['status'], 'ok')
        self.sources[0]['pages'] = 2; self.write_manifest()
        with self.assertRaises(ValueError): rag.check(self.kb, self.study)
    def test_exclusion_and_page_chunks(self):
        self.assertEqual(classify(Path('materiel/复试资料/结构体.pdf'))[0], 'excluded')
        self.assertEqual(classify(Path('materiel/地大2027初试学习档案.md'))[0], 'excluded')
        self.assertEqual(classify(Path('materiel/中国地质大学资料合集.pdf'))[0], 'mixed')
        text = 'abcdef\n' * 900
        chunks = list(rag.split_text(text))
        self.assertTrue(all(len(s) <= 1000 for _, s in chunks))
        self.assertTrue(all(a[0] < b[0] for a,b in zip(chunks, chunks[1:])))
        self.assertTrue(chunks[-1][1].endswith('abcdef'))
    def test_missing_corpus_does_not_block_study(self):
        result = rag.search('结构体', kb=self.root / 'missing', study_root=self.study)
        self.assertEqual(result['status'], 'not_built')
    def test_interrupted_extraction_resumes_pages(self):
        from unittest.mock import patch, Mock
        from scripts import ingest_materials as ingest
        entry = dict(id='SRC-resume', sha256='digest', path='materiel/scan.pdf')
        source = self.root / entry['path']
        converted = Mock(stdout=b'\x0c\x0c')
        with patch.object(ingest, 'ROOT', self.root), patch.object(ingest.subprocess, 'run', return_value=converted):
            with patch.object(ingest, 'ocr', side_effect=[('page one', .9), RuntimeError('interrupted')]):
                with self.assertRaises(RuntimeError): ingest.extract((source, entry))
            with patch.object(ingest, 'ocr', return_value=('page two', .9)) as recognize:
                _, rows = ingest.extract((source, entry))
                self.assertEqual([r['text'] for r in rows], ['page one', 'page two'])
                recognize.assert_called_once_with(source, 2)
    def test_corpus_tampering_detected(self):
        p = self.kb / 'corpus/SRC-a.jsonl'
        p.write_text(p.read_text('utf-8').replace('结构体', '错误内容'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '语料指纹'):
            rag.check(self.kb, self.study)
    def test_parallel_extraction_preserves_page_provenance(self):
        import concurrent.futures
        from unittest.mock import patch, Mock
        from scripts import ingest_materials as ingest
        def recognize(path, page): return (f'{path.stem} page {page}', .9)
        entries = [dict(id=f'SRC-{n}', sha256=f'hash-{n}', path=f'materiel/{n}.pdf') for n in range(2)]
        with patch.object(ingest, 'ROOT', self.root), patch.object(ingest.subprocess, 'run', return_value=Mock(stdout=b'\x0c' * 5)), patch.object(ingest, 'ocr', side_effect=recognize):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pages, concurrent.futures.ThreadPoolExecutor(max_workers=2) as files:
                jobs = [files.submit(ingest.extract, (self.root/e['path'], e), 2, pages) for e in entries]
                for n, job in enumerate(jobs):
                    entry, rows = job.result()
                    self.assertEqual([r['page'] for r in rows], list(range(1, 6)))
                    self.assertTrue(all(r['source_id'] == entry['id'] for r in rows))
                    self.assertEqual([r['text'] for r in rows], [f'{n} page {i}' for i in range(1, 6)])
    def test_due_review_reference_priority_and_no_learning_mutation(self):
        import shutil
        from study import Store, TABLES
        shutil.rmtree(self.study)
        shutil.copytree(BASE / 'study', self.study)
        s = Store(self.study)
        before = {k: s.path(k).read_bytes() for k in TABLES}
        with s.lock():
            current = s.context(dt.date(2026, 10, 8))
            due = s.context(dt.date(2026, 10, 9))
        self.assertEqual(current['reference_topic'], current['current_question']['topic_id'])
        self.assertEqual(due['reference_topic'], due['mistakes'][0]['topic_id'])
        self.assertEqual(before, {k: s.path(k).read_bytes() for k in TABLES})
    def test_readme_derived_snapshot(self):
        import shutil
        for path in ('state.yaml', 'stats/summary.json'):
            dest = self.study / path; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy(BASE / 'study' / path, dest)
        readme = self.root / 'README.md'
        readme.write_text('before\n<!-- STUDY_PROGRESS_START -->old<!-- STUDY_PROGRESS_END -->\nafter', encoding='utf-8')
        before = (self.study / 'state.yaml').read_bytes()
        self.assertTrue(update(self.study))
        value = readme.read_text('utf-8')
        state = yaml.safe_load(before)
        self.assertIn(f"{state['statistics']['questions_answered']} 题", value)
        self.assertIn(format(state['progress']['coverage'], '.1%'), value)
        self.assertTrue(value.startswith('before')); self.assertTrue(value.endswith('after'))
        self.assertEqual(before, (self.study / 'state.yaml').read_bytes())
        update(self.study); self.assertEqual(value, readme.read_text('utf-8'))

if __name__ == '__main__': unittest.main()
