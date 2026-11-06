import csv
import hashlib
import json
import sys
from types import SimpleNamespace

from PIL import Image

from apps.api.asdos_api.model_adapters import ModelProvenance, TranscriptSegment
from scripts import draft_handwriting_annotations as draft


def test_drafts_keep_proposals_unconfirmed_and_resume(tmp_path, monkeypatch):
    image = tmp_path / 'page.png'
    Image.new('RGB', (100, 100), 'white').save(image)
    with (tmp_path / 'pages.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['page_id', 'image_path', 'image_sha256', 'source_sha256'])
        writer.writeheader()
        writer.writerow({'page_id': 'p1', 'image_path': 'page.png',
                         'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest(), 'source_sha256': 'a' * 64})
    provenance = ModelProvenance('model', 'revision', 'prompt', 'schema', 'cpu', 'runtime', 'b' * 64)
    monkeypatch.setattr(draft.qwen_adapter, 'propose_identity', lambda _: ({'name': 'test', 'student_id': '001'}, provenance))
    region = SimpleNamespace(bbox=(100, 200, 500, 600), label='1', continuation=False, flags=[])
    monkeypatch.setattr(draft.qwen_adapter, 'locate_answers', lambda *_: (SimpleNamespace(regions=[region], flags=[]), provenance))
    monkeypatch.setattr(draft.qwen_adapter, 'transcribe', lambda *_: ([TranscriptSegment('literal')], provenance))
    monkeypatch.setattr(sys, 'argv', ['draft', '--dataset', str(tmp_path)])
    draft.main()
    path = tmp_path / 'drafts/p1.json'
    result = json.loads(path.read_text())
    assert result['identity']['status'] == 'unconfirmed'
    assert result['status'] == result['regions'][0]['status'] == 'needs_human_review'
    assert result['regions'][0]['bbox_pixels'] == [10, 20, 50, 60]
    assert result['regions'][0]['text'] == 'literal'
    monkeypatch.setattr(draft.qwen_adapter, 'propose_identity', lambda _: (_ for _ in ()).throw(AssertionError('must resume')))
    draft.main()
    assert json.loads(path.read_text()) == result
