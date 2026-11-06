import csv
import hashlib
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest
from scripts.dataset_review import ReviewStore, make_handler


def fixture_store(tmp_path):
    (tmp_path / 'pages').mkdir()
    image = b'synthetic-image'
    (tmp_path / 'pages' / 'page.png').write_bytes(image)
    row = {'page_id': 'doc-001-p0001', 'image_path': 'pages/page.png',
           'image_sha256': hashlib.sha256(image).hexdigest(), 'source_sha256': 'a' * 64}
    with (tmp_path / 'pages.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        writer.writeheader()
        writer.writerow(row)
    return ReviewStore(tmp_path)


def payload():
    return {'revision': 0, 'writer_id': 'w-1', 'submission_id': 's-1', 'student_name': '',
            'student_id': '001', 'identity_confirmed': True, 'transcript': 'literal',
            'transcript_reviewed': True, 'notes': ''}


def test_review_versions_preserve_identity_and_reject_stale_updates(tmp_path):
    store = fixture_store(tmp_path)
    key = 'doc-001-p0001'
    assert store.image(key) == b'synthetic-image'
    first = store.save(key, payload())
    assert first['student_id'] == '001' and first['revision'] == 1
    with pytest.raises(RuntimeError):
        store.save(key, payload())
    data = payload() | {'revision': 1, 'transcript': 'corrected'}
    assert store.save(key, data)['revision'] == 2
    assert len(list(store.reviews.glob('*.json'))) == 2
    assert json.loads(sorted(store.reviews.glob('*.json'))[0].read_text())['transcript'] == 'literal'
    with pytest.raises(ValueError):
        store.save(key, data | {'revision': 2, 'student_id': ''})


def test_http_requires_token_and_same_origin(tmp_path):
    store = fixture_store(tmp_path)
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(store, 'secret'))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
        conn.request('GET', '/api/pages')
        assert conn.getresponse().status == 403
        conn.request('GET', '/api/pages', headers={'X-Review-Token': 'secret'})
        response = conn.getresponse()
        assert response.status == 200
        response.read()
        conn.request('POST', '/api/page/doc-001-p0001', body=json.dumps(payload()), headers={'X-Review-Token': 'secret', 'Origin': 'http://evil.example'})
        assert conn.getresponse().status == 403
        conn.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def test_confirmed_writer_and_submission_cannot_mix_students(tmp_path):
    store = fixture_store(tmp_path)
    key = 'doc-001-p0001'
    store.pages['doc-002-p0001'] = store.pages[key] | {'page_id': 'doc-002-p0001'}
    store.save(key, payload())
    with pytest.raises(ValueError, match='bertentangan'):
        store.save('doc-002-p0001', payload() | {'student_id': '002'})
    with pytest.raises(ValueError, match='bertentangan'):
        store.save('doc-002-p0001', payload() | {'writer_id': 'w-2'})
    assert store.save('doc-002-p0001', payload() | {'submission_id': 's-2'})['identity_confirmed']
