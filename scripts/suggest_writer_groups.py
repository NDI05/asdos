"""Suggest identity matches from private OCR; never confirm or assign writers."""
import csv
import json
import os
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])
os.umask(0o077)
with (root / 'pages.csv').open(newline='', encoding='utf-8') as stream:
    pages = list(csv.DictReader(stream))
proposals = []
for page in pages:
    source = root / 'vision-drafts' / (page['page_id'] + '.json')
    result = json.loads(source.read_text(encoding='utf-8'))
    candidates = set()
    for line in result.get('lines', []):
        text = line['text']
        if line['bbox_normalized'][3] < 0.55 or not re.search(r'\bN\s*I\s*M\b', text, re.I):
            continue
        for match in re.findall(r'(?<!\d)(?:\d[ \t]*){8,16}(?!\d)', text):
            candidates.add(re.sub(r'\s+', '', match))
    proposals.append({'page_id': page['page_id'], 'source_sha256': page['source_sha256'],
                      'image_sha256': page['image_sha256'], 'nim_candidates': sorted(candidates),
                      'status': 'unconfirmed', 'writer_id': None, 'submission_id': None})
out = {'schema_version': 'asdos-identity-candidates.v1', 'status': 'requires_human_review',
       'notice': 'OCR candidates are not identity confirmation or writer groups.', 'pages': proposals}
path = root / 'identity-candidates.json'
if path.exists():
    raise RuntimeError('Output exists; preserve prior review.')
path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('Pages:', len(proposals), '; with candidates:', sum(bool(p['nim_candidates']) for p in proposals))
