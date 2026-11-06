"""Generate resumable, local-only, unreviewed page OCR; not training labels."""
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
engine = Path(sys.argv[2]).resolve()
os.umask(0o077)
out = root / 'vision-drafts'
out.mkdir(exist_ok=True, mode=0o700)
with (root / 'pages.csv').open(newline='', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))
process = subprocess.Popen([str(engine)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
for index, row in enumerate(rows, 1):
    output = out / (row['page_id'] + '.json')
    if output.exists():
        continue
    image = root / row['image_path']
    if hashlib.sha256(image.read_bytes()).hexdigest() != row['image_sha256']:
        raise RuntimeError('Page hash mismatch: ' + row['page_id'])
    process.stdin.write(f"{row['page_id']}\t{image}\n")
    process.stdin.flush()
    raw = process.stdout.readline()
    if not raw:
        raise RuntimeError('Local OCR process stopped; rerun to resume.')
    result = json.loads(raw)
    if result.get('page_id') != row['page_id']:
        raise RuntimeError('Page mismatch')
    result.update(source_sha256=row['source_sha256'], image_sha256=row['image_sha256'])
    temporary = output.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(temporary, output)
    if index % 20 == 0:
        print(f'{index}/{len(rows)} pages processed', flush=True)
process.stdin.close()
if process.wait() != 0:
    raise RuntimeError('Local OCR failed')
print('Draft OCR completed; all pages require review.', flush=True)
