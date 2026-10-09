#!/usr/bin/env python3
"""Extract local sources, preserving page provenance; resume by content hash."""
import argparse
import concurrent.futures
import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from study import atomic
VERSION = 1
_local = threading.local()


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def classify(path):
    name = str(path)
    if '复试资料' in name: return 'excluded', '复试资料，超出830初试范围'
    if path.suffix.lower() == '.md': return 'excluded', '历史学习档案，不重复导入作答或知识证据'
    if path.suffix.lower() not in ('.pdf', '.doc', '.docx', '.ppt', '.pptx'): return 'excluded', '不支持的附件格式'
    if '[补充]' in name: return 'supplement', '其他科目真题，仅显式补充检索'
    if path.name == '中国地质大学资料合集.pdf': return 'mixed', '混合合集，默认不检索，避免混入非830内容'
    if '考试大纲' in name: return 'outline', '用户提供的大纲；年份及官方发布状态未独立核验'
    if '历年真题' in name: return 'exam', '用户提供的真题/回忆版，未独立核验官方版本'
    if '课件' in name: return 'slides', '教学课件'
    return 'notes', '复习笔记或题库，答案需交叉核验'


def converted_path(path):
    return ROOT / '.cache/materials_pdf' / sha(path) / (path.stem + '.pdf')


def convert():
    for path in sorted((ROOT / 'materiel').rglob('*')):
        if not path.is_file() or path.suffix.lower() not in ('.doc', '.docx', '.ppt', '.pptx'): continue
        if classify(path)[0] == 'excluded': continue
        target = converted_path(path)
        if target.exists(): continue
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['libreoffice', '-env:UserInstallation=file:///tmp/830-rag-libreoffice',
                        '--headless', '--convert-to', 'pdf', '--outdir', str(target.parent), str(path)], check=True, timeout=120)
        if not target.exists(): raise RuntimeError(f'Conversion failed: {path}')


def clean(text):
    return unicodedata.normalize('NFKC', text).replace('\x00', '').strip()


def ocr(pdf, number):
    if not hasattr(_local, 'engine'):
        from rapidocr_onnxruntime import RapidOCR
        _local.engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
    with tempfile.TemporaryDirectory(prefix='830-ocr-') as tmp:
        out = Path(tmp) / 'page'
        subprocess.run(['pdftoppm', '-f', str(number), '-l', str(number), '-scale-to', '1800',
                        '-singlefile', '-png', str(pdf), str(out)], check=True, capture_output=True, timeout=90)
        result, _ = _local.engine(str(out) + '.png')
    if not result: return '', None
    return clean('\n'.join(row[1] for row in result)), round(sum(float(row[2]) for row in result) / len(result), 4)


def extract(item, page_workers=1, page_executor=None):
    path, entry = item
    target = ROOT / 'knowledge_base/corpus' / (entry['id'] + '.jsonl')
    if target.exists():
        first = json.loads(target.open(encoding='utf-8').readline())
        if first.get('source_sha256') == entry['sha256'] and first.get('extractor_version') == VERSION:
            return entry, [json.loads(s) for s in target.read_text('utf-8').splitlines()]
    pdf = path if path.suffix.lower() == '.pdf' else converted_path(path)
    result = subprocess.run(['pdftotext', '-layout', str(pdf), '-'], capture_output=True, check=True, timeout=120)
    pages = result.stdout.decode('utf-8', errors='replace').split('\f')
    if not pages[-1].strip(): pages.pop()
    def extract_page(pair):
        i, text = pair
        checkpoint = ROOT / '.cache/ingest_pages' / f"v{VERSION}" / entry['id'] / entry['sha256'] / f'{i}.json'
        if checkpoint.exists():
            cached = json.loads(checkpoint.read_text('utf-8'))
            if (cached.get('source_id') == entry['id'] and cached.get('source_sha256') == entry['sha256']
                    and cached.get('extractor_version') == VERSION and cached.get('page') == i):
                return cached
        text = clean(text); method = 'text'; confidence = None
        # OCR sparse pages as well as complete scans. Keep the original text if OCR adds nothing.
        if len(''.join(text.split())) < 40 or text.count('\ufffd') > 5:
            recognized, confidence = ocr(pdf, i)
            if len(recognized) > len(text): text, method = recognized, 'ocr'
        row = {'source_id': entry['id'], 'source_sha256': entry['sha256'], 'extractor_version': VERSION,
                     'page': i, 'locator': 'slide' if path.suffix.lower() in ('.ppt', '.pptx') else 'page',
                     'method': method, 'ocr_confidence': confidence,
                     'quality': 'sparse' if len(''.join(text.split())) < 40 else 'needs_visual_check' if method == 'ocr' else 'text_extracted',
                     'text': text}
        atomic(checkpoint, json.dumps(row, ensure_ascii=False) + '\n')
        return row
    executor_context = (contextlib.nullcontext(page_executor) if page_executor is not None
                        else concurrent.futures.ThreadPoolExecutor(max_workers=page_workers))
    with executor_context as page_pool:
        rows = []
        # map preserves physical page order even when OCR finishes out of order.
        for i, row in enumerate(page_pool.map(extract_page, enumerate(pages, 1)), 1):
            rows.append(row)
            if i % 30 == 0: print(f"  {entry['path']}: {i}/{len(pages)}", flush=True)
    atomic(target, ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    return entry, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--convert', action='store_true')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--page-workers', type=int, default=4, help='所有文件共享的最大页面并发数')
    args = parser.parse_args()
    if args.workers < 1 or args.page_workers < 1: parser.error('并发数必须为正整数')
    if args.convert: convert(); return
    files = sorted(p for p in (ROOT / 'materiel').rglob('*') if p.is_file())
    if not files: raise SystemExit('materiel/ 无原始文件；保留已有语料。仅重建索引请用 python3 rag.py build')
    entries = []; jobs = []; seen = {}
    for path in files:
        rel = path.relative_to(ROOT).as_posix(); kind, note = classify(path); digest = sha(path)
        entry = {'id': 'SRC-' + hashlib.sha256(rel.encode()).hexdigest()[:12], 'path': rel, 'title': path.stem,
                 'sha256': digest, 'bytes': path.stat().st_size, 'kind': kind, 'note': note}
        entries.append(entry)
        if kind == 'excluded': entry['status'] = 'excluded'; continue
        if (digest, kind) in seen:
            entry['status'] = 'duplicate'; entry['duplicate_of'] = seen[(digest, kind)]; continue
        seen[(digest, kind)] = entry['id']; jobs.append((path, entry))
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.page_workers) as page_pool, concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(extract, job, args.page_workers, page_pool): job[1] for job in jobs}
        for f in concurrent.futures.as_completed(futures):
            entry = futures[f]
            try:
                _, rows = f.result()
                entry.update(status='indexed', pages=len(rows), ocr_pages=sum(r['method'] == 'ocr' for r in rows),
                             sparse_pages=[r['page'] for r in rows if r['quality'] == 'sparse'],
                             corpus='corpus/' + entry['id'] + '.jsonl',
                             corpus_sha256=sha(ROOT / 'knowledge_base/corpus' / (entry['id'] + '.jsonl')))
                print(f"OK {entry['path']} ({len(rows)} pages)", flush=True)
            except Exception as e:
                entry.update(status='error', error=str(e)); print(f"ERROR {entry['path']}: {e}", flush=True)
    atomic(ROOT / 'knowledge_base/sources.json', json.dumps({'version': VERSION, 'sources': entries}, ensure_ascii=False, indent=2) + '\n')
    if any(e['status'] == 'error' for e in entries): raise SystemExit('存在提取失败，详见 sources.json；重跑将复用成功语料')

if __name__ == '__main__': main()
