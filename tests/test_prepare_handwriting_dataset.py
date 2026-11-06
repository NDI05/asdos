import csv
import json
import subprocess
import sys

import pypdfium2 as pdfium


def test_private_page_inventory_preserves_boundaries_and_leaves_labels_unset(tmp_path):
    source = tmp_path / 'input'
    source.mkdir()
    document = pdfium.PdfDocument.new()
    for _ in range(2):
        page = document.new_page(72, 144)
        page.close()
    document.save(str(source / 'class.pdf'))
    document.close()
    output = tmp_path / 'output'
    command = [sys.executable, '-m', 'scripts.prepare_handwriting_dataset',
               '--source', str(source), '--output', str(output), '--dpi', '72']
    subprocess.run(command, check=True, capture_output=True)
    manifest = json.loads((output / 'documents.json').read_text())
    with (output / 'pages.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    assert manifest['documents'][0]['page_count'] == len(rows) == 2
    assert [row['page_index_zero_based'] for row in rows] == ['0', '1']
    for row in rows:
        assert (output / row['image_path']).is_file()
        assert row['source_sha256'] == manifest['documents'][0]['sha256']
        assert row['writer_id'] == row['submission_id'] == row['split'] == ''
        assert row['annotation_status'] == 'unlabeled'
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert len(list((output / 'pages').rglob('*.png'))) == 2
