"""Generate resumable, private model proposals; every proposal requires human review."""
import argparse
import csv
import hashlib
import io
import json
import math
import os
import time
from dataclasses import asdict
from pathlib import Path

from PIL import Image
from apps.api.asdos_api.model_adapters import qwen_adapter


def save(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=0, help='Maximum new pages; 0 means all')
    args = parser.parse_args()
    if args.limit < 0:
        parser.error('limit must be nonnegative')
    os.umask(0o077)
    output = args.dataset / 'drafts'
    output.mkdir(mode=0o700, exist_ok=True)
    with (args.dataset / 'pages.csv').open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    completed = failed = 0
    for row in rows:
        if args.limit and completed + failed >= args.limit:
            break
        path = output / (row['page_id'] + '.json')
        if path.exists():
            previous = json.loads(path.read_text(encoding='utf-8'))
            if previous.get('draft_complete') and not previous.get('errors') and all('error' not in r for r in previous.get('regions', [])):
                continue
        started = time.monotonic()
        image_path = args.dataset / row['image_path']
        data = image_path.read_bytes()
        if hashlib.sha256(data).hexdigest() != row['image_sha256']:
            raise ValueError('image hash mismatch: ' + row['page_id'])
        result = {'schema_version': 'asdos-annotation-draft.v1', 'page_id': row['page_id'],
                  'source_sha256': row['source_sha256'], 'image_sha256': row['image_sha256'],
                  'status': 'needs_human_review', 'identity': None, 'regions': [], 'errors': []}
        try:
            identity, provenance = qwen_adapter.propose_identity(data)
            result['identity'] = {'proposal': identity, 'status': 'unconfirmed', 'provenance': asdict(provenance)}
        except Exception as exc:
            result['errors'].append({'stage': 'identity', 'error': getattr(exc, 'code', type(exc).__name__)})
        save(path, result)
        try:
            located, provenance = qwen_adapter.locate_answers(data, 'id')
            result['localization'] = {'flags': located.flags, 'provenance': asdict(provenance)}
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                for index, region in enumerate(located.regions):
                    left, top, right, bottom = region.bbox
                    box = (math.floor(left * width / 1000), math.floor(top * height / 1000),
                           math.ceil(right * width / 1000), math.ceil(bottom * height / 1000))
                    item = {'region_id': f"{row['page_id']}-r{index + 1:03d}",
                            'label': region.label, 'bbox_normalized_1000': list(region.bbox),
                            'bbox_pixels': list(box), 'continuation': region.continuation,
                            'flags': region.flags, 'text': None, 'status': 'needs_human_review'}
                    try:
                        crop = image.crop(box)
                        buffer = io.BytesIO()
                        crop.save(buffer, format='PNG')
                        crop.close()
                        segments, text_provenance = qwen_adapter.transcribe([buffer.getvalue()], 'id')
                        item.update(text=segments[0].text, transcription_flags=segments[0].flags,
                                    transcription_provenance=asdict(text_provenance))
                    except Exception as exc:
                        item['error'] = getattr(exc, 'code', type(exc).__name__)
                    result['regions'].append(item)
                    save(path, result)
        except Exception as exc:
            result['errors'].append({'stage': 'localization', 'error': getattr(exc, 'code', type(exc).__name__)})
        result['duration_seconds'] = round(time.monotonic() - started, 1)
        result['draft_complete'] = True
        save(path, result)
        if result['errors']:
            failed += 1
        else:
            completed += 1
        print(f"{row['page_id']}: regions={len(result['regions'])}, errors={len(result['errors'])}, seconds={result['duration_seconds']}", flush=True)
    print(f'New drafts: {completed}; pages with errors: {failed}. All require review.', flush=True)


if __name__ == '__main__':
    main()
