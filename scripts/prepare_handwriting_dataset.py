"""Create a private, unlabeled page inventory from class PDFs (no model calls)."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path

import pypdfium2 as pdfium


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dpi', type=int, default=150)
    args = parser.parse_args()
    if not 36 <= args.dpi <= 300:
        parser.error('dpi must be between 36 and 300')
    sources = sorted(args.source.glob('*.pdf'))
    if not sources:
        parser.error('no PDF files found')
    if args.output.exists():
        parser.error('output already exists; choose a new directory to preserve existing work')
    os.umask(0o077)
    args.output.mkdir(parents=True, mode=0o700)
    (args.output / 'pages').mkdir(mode=0o700)
    documents, rows = [], []
    for index, source in enumerate(sources, 1):
        doc_id = f'doc-{index:03d}'
        document = pdfium.PdfDocument(source)
        doc_hash = sha256(source)
        documents.append({'document_id': doc_id, 'source_filename': source.name,
                          'sha256': doc_hash, 'page_count': len(document)})
        folder = args.output / 'pages' / doc_id
        folder.mkdir(mode=0o700)
        try:
            for page_index in range(len(document)):
                page = document[page_index]
                try:
                    width, height = page.get_size()
                    scale = args.dpi / 72
                    if not (math.isfinite(width) and math.isfinite(height) and width > 0 and height > 0) or math.ceil(width * scale) * math.ceil(height * scale) > 25_000_000:
                        raise ValueError(f'{doc_id} page {page_index + 1} exceeds pixel limit')
                    bitmap = page.render(scale=scale)
                    try:
                        image = bitmap.to_pil()
                        path = folder / f'page-{page_index + 1:04d}.png'
                        image.save(path)
                        pixel_width, pixel_height = image.size
                    finally:
                        bitmap.close()
                    rows.append({'page_id': f'{doc_id}-p{page_index + 1:04d}',
                                 'document_id': doc_id, 'source_sha256': doc_hash,
                                 'page_index_zero_based': page_index,
                                 'image_path': str(path.relative_to(args.output)),
                                 'image_sha256': sha256(path), 'pdf_width_points': width,
                                 'pdf_height_points': height, 'image_width_px': pixel_width,
                                 'image_height_px': pixel_height, 'render_dpi': args.dpi,
                                 'writer_id': '', 'submission_id': '', 'split': '',
                                 'paper_type': '', 'handwriting_quality': '',
                                 'identity_reviewed': 'no', 'annotation_status': 'unlabeled'})
                finally:
                    page.close()
        finally:
            document.close()
        print(f'{doc_id}: {len([r for r in rows if r["document_id"] == doc_id])} pages', flush=True)
    (args.output / 'documents.json').write_text(json.dumps({'schema_version': 'asdos-private-pages.v1',
        'documents': documents}, indent=2) + '\n', encoding='utf-8')
    with (args.output / 'pages.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f'Prepared {len(rows)} unlabeled pages. Human verification and annotation are required.')


if __name__ == '__main__':
    main()
