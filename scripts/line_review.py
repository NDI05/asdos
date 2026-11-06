"""Versioned human line review and private export; originals and AI drafts stay immutable."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

SPLITS = ('train', 'development', 'calibration', 'locked_test')


def atomic_revision(folder, key, record):
    folder.mkdir(mode=0o700, exist_ok=True)
    path = folder / f"{key}.{record['revision']:08d}.json"
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder, delete=False) as f:
            temp = Path(f.name)
            json.dump(record, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.link(temp, path)
    finally:
        if temp:
            temp.unlink(missing_ok=True)
    return record


def current(store, key):
    store.page(key)
    files = sorted((store.root / 'line-reviews').glob(key + '.*.json'))
    return json.loads(files[-1].read_text()) if files else None


def progress(store, key):
    page, review = store.current(key), current(store, key)
    valid_identity = bool(page and page['identity_confirmed'] and review and review['page_review_revision'] == page['revision'])
    lines = review['lines'] if review else []
    confirmed = sum(line['confirmed'] for line in lines)
    reviewed = bool(valid_identity and lines and confirmed == len(lines) and review['coverage_confirmed'] and review['split'] in SPLITS)
    return {'page_id': key, 'reviewed': reviewed, 'confirmed_lines': confirmed if valid_identity else 0,
            'review_line_count': len(lines), 'identity_confirmed': bool(page and page['identity_confirmed'])}


def details(store, key):
    row = store.page(key)
    old = current(store, key)
    page_review = store.current(key)
    if old:
        return {**old, 'stale_identity': old['page_review_revision'] != (page_review['revision'] if page_review else 0)}
    draft_path = store.root / 'vision-drafts' / (key + '.json')
    draft = json.loads(draft_path.read_text()) if draft_path.exists() else {'lines': []}
    if draft.get('image_sha256', row['image_sha256']) != row['image_sha256']:
        raise ValueError('Draft image mismatch')
    w, h = int(row['image_width_px']), int(row['image_height_px'])
    lines = []
    for i, line in enumerate(draft['lines']):
        x0, y0, x1, y1 = line['bbox_normalized']
        box = [max(0, math.floor(x0*w)), max(0, math.floor((1-y1)*h)), min(w, math.ceil(x1*w)), min(h, math.ceil((1-y0)*h))]
        lines.append({'line_id': f'line-{i:04d}', 'text': line['text'], 'bbox_pixels': box,
                      'kind': 'unreviewed', 'confirmed': False, 'reason': ''})
    return {'revision': 0, 'page_review_revision': page_review['revision'] if page_review else 0,
            'split': '', 'coverage_confirmed': False, 'lines': lines, 'stale_identity': False}


def save(store, key, payload):
    row = store.page(key)
    required = {'revision', 'page_review_revision', 'split', 'coverage_confirmed', 'lines'}
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError('Field review baris tidak valid')
    if type(payload['revision']) is not int or type(payload['page_review_revision']) is not int or type(payload['coverage_confirmed']) is not bool:
        raise ValueError('Status revisi tidak valid')
    if payload['split'] not in ('', *SPLITS) or not isinstance(payload['lines'], list) or len(payload['lines']) > 500:
        raise ValueError('Split atau jumlah baris tidak valid')
    ids = set()
    w, h = int(row['image_width_px']), int(row['image_height_px'])
    for line in payload['lines']:
        if not isinstance(line, dict) or set(line) != {'line_id','text','bbox_pixels','kind','confirmed','reason'}:
            raise ValueError('Field baris tidak valid')
        key_id = line['line_id']
        if not isinstance(key_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', key_id) or key_id in ids:
            raise ValueError('ID baris duplikat/tidak valid')
        ids.add(key_id)
        if not isinstance(line['text'], str) or len(line['text']) > 10000 or not isinstance(line['reason'], str) or len(line['reason']) > 1000:
            raise ValueError('Teks baris tidak valid')
        if line['kind'] not in ('unreviewed', 'answer', 'identity', 'exclude', 'unreadable') or type(line['confirmed']) is not bool:
            raise ValueError('Jenis/status baris tidak valid')
        b = line['bbox_pixels']
        if not isinstance(b, list) or len(b) != 4 or any(type(v) is not int for v in b) or not (0 <= b[0] < b[2] <= w and 0 <= b[1] < b[3] <= h):
            raise ValueError('Kotak harus berada di dalam gambar dengan luas positif')
        if line['confirmed']:
            if line['kind'] == 'unreviewed' or (line['kind'] == 'answer' and (not line['text'].strip() or '[tidak terbaca]' in line['text'].lower())):
                raise ValueError('Jawaban kosong/tidak terbaca belum dapat menjadi label training')
            if line['kind'] in ('exclude','unreadable') and not line['reason'].strip():
                raise ValueError('Isi alasan pengecualian/tidak terbaca')
    with store.lock:
        old = current(store, key)
        revision = old['revision'] if old else 0
        if revision != payload['revision']:
            raise RuntimeError('Review baris sudah berubah; muat ulang.')
        page = store.current(key)
        if payload['page_review_revision'] != (page['revision'] if page else 0):
            raise RuntimeError('Review identitas berubah; muat ulang dan periksa kembali.')
        store.image(key)  # Verify exact source before persisting confirmations.
        record = {**payload, 'revision': revision+1, 'page_id': key,
                  'image_sha256': row['image_sha256'], 'source_sha256': row['source_sha256'],
                  'schema_version': 'asdos-line-review.v1'}
        return atomic_revision(store.root / 'line-reviews', key, record)


def export(store, output):
    """Freeze all reviewed pages, refusing partial or conflicting writer assignments."""
    if output.exists():
        raise ValueError('Output sudah ada; gunakan versi baru')
    samples, blockers, writers, images = [], [], {}, {}
    read_versions = {}
    provenance = []
    with store.lock:
        for key, row in store.pages.items():
            page, review = store.current(key), current(store, key)
            read_versions[key] = (page['revision'] if page else 0, review['revision'] if review else 0)
            if not page or not page['identity_confirmed'] or not review or not review['coverage_confirmed']:
                blockers.append(key + ': identitas/cakupan belum dikonfirmasi')
                continue
            if review['page_review_revision'] != page['revision'] or review['split'] not in SPLITS:
                blockers.append(key + ': identitas berubah atau split belum diisi')
                continue
            if not review['lines'] or any(not l['confirmed'] or l['kind'] == 'unreviewed' for l in review['lines']):
                blockers.append(key + ': masih ada baris belum ditinjau')
                continue
            writer = page['writer_id'].strip()
            split = review['split']
            for groups, group in ((writers, writer), (images, row['image_sha256'])):
                if group in groups and groups[group] != split:
                    blockers.append(key + ': penulis/gambar melintasi split')
                groups[group] = split
            store.image(key)
            identity_boxes = [l['bbox_pixels'] for l in review['lines'] if l['kind'] == 'identity']
            for line in review['lines']:
                if line['kind'] != 'answer':
                    continue
                b = line['bbox_pixels']
                if any(min(b[2], i[2]) > max(b[0], i[0]) and min(b[3], i[3]) > max(b[1], i[1]) for i in identity_boxes):
                    blockers.append(key + ': kotak jawaban bertumpang tindih identitas')
                samples.append({'sample_id': key + '-' + line['line_id'], 'page_id': key,
                    'image_path': str((store.root / row['image_path']).resolve()),
                    'image_sha256': row['image_sha256'], 'source_sha256': row['source_sha256'],
                    'bbox_pixels': b, 'text': line['text'], 'status': 'human_confirmed',
                    'label_source': 'human_reviewed_ai_or_manual', 'identity_free_crop_confirmed': True,
                    'writer_id': writer, 'split': split,
                    'page_review_revision': page['revision'], 'line_review_revision': review['revision']})
            provenance.append({'page_id': key, 'page_review_revision': page['revision'], 'line_review_revision': review['revision']})
    for key, expected in read_versions.items():
        page, review = store.current(key), current(store, key)
        actual = (page['revision'] if page else 0, review['revision'] if review else 0)
        if actual != expected:
            blockers.append(key + ': revisi berubah saat ekspor; ulangi')
    if blockers:
        raise ValueError(f'{len(blockers)} blocker. Contoh: ' + '; '.join(blockers[:5]))
    if not samples:
        raise ValueError('Tidak ada baris jawaban')
    output.mkdir(parents=True, mode=0o700)
    raw = ''.join(json.dumps(s, ensure_ascii=False)+'\n' for s in samples)
    (output / 'annotations.jsonl').write_text(raw)
    report = {'schema_version': 'asdos-reviewed-lines.v1', 'samples': len(samples), 'writers': len(writers),
              'manifest_sha256': hashlib.sha256(raw.encode()).hexdigest(), 'page_revisions': provenance,
              'human_reviewed': True, 'double_annotation_adjudication_verified': False,
              'model_release_gate': 'not_assessed', 'original_pages_contain_private_identity': True}
    (output / 'snapshot.json').write_text(json.dumps(report, indent=2))
    return report
