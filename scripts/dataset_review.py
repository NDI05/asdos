"""Private single-user review server for ASDOS page inventories."""
import argparse
import csv
import hashlib
import hmac
import json
import os
import re
from pathlib import Path
import secrets
import threading
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from scripts import line_review

ROOT = Path(__file__).resolve().parent.parent
HTML = Path(__file__).with_name('dataset_review.html').read_bytes()

class ReviewStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        with (self.root / 'pages.csv').open(newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        self.pages = {r['page_id']: r for r in rows}
        if any(not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', key) for key in self.pages):
            raise ValueError('Invalid page ID')
        if len(self.pages) != len(rows):
            raise ValueError('Duplicate page ID')
        self.reviews = self.root / 'reviews'
        self.reviews.mkdir(mode=0o700, exist_ok=True)
        self.lock = threading.Lock()

    def page(self, key):
        if key not in self.pages:
            raise KeyError(key)
        return self.pages[key]

    def image(self, key):
        row = self.page(key)
        path = (self.root / row['image_path']).resolve()
        if not path.is_relative_to(self.root / 'pages'):
            raise ValueError('Invalid image path')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != row['image_sha256']:
            raise ValueError('Image hash mismatch')
        return data

    def current(self, key):
        self.page(key)
        versions = sorted(self.reviews.glob(key + '.*.json'))
        return json.loads(versions[-1].read_text(encoding='utf-8')) if versions else None

    def details(self, key):
        row = self.page(key)
        ocr = self.root / 'vision-drafts' / (key + '.json')
        draft = json.loads(ocr.read_text(encoding='utf-8')) if ocr.exists() else None
        if draft and (draft.get('page_id') != key or draft.get('image_sha256') != row['image_sha256']):
            raise ValueError('Draft does not match page')
        ai_path = self.root / 'ai-review-v3' / (key + '.json')
        ai_review = json.loads(ai_path.read_text()) if ai_path.exists() else None
        if ai_review and (not ai_review.get('complete') or ai_review.get('image_sha256') != row['image_sha256']):
            ai_review = None
        return {'page': row, 'draft': draft, 'review': self.current(key), 'ai_review': ai_review}

    def save(self, key, payload):
        row = self.page(key)
        allowed = {'revision', 'writer_id', 'submission_id', 'student_name', 'student_id', 'identity_confirmed', 'transcript', 'transcript_reviewed', 'notes'}
        if set(payload) != allowed:
            raise ValueError('Invalid fields')
        for field in ('writer_id', 'submission_id', 'student_name', 'student_id', 'transcript', 'notes'):
            if not isinstance(payload[field], str) or len(payload[field]) > (100000 if field == 'transcript' else 1000):
                raise ValueError('Invalid text')
        if type(payload['revision']) is not int or any(type(payload[k]) is not bool for k in ('identity_confirmed', 'transcript_reviewed')):
            raise ValueError('Invalid status')
        if payload['identity_confirmed'] and not all(payload[k].strip() for k in ('writer_id', 'submission_id', 'student_id')):
            raise ValueError('Konfirmasi identitas memerlukan NIM, ID penulis, dan ID submission.')
        if payload['transcript_reviewed'] and not payload['transcript'].strip():
            raise ValueError('Transkripsi kosong tidak dapat ditandai selesai.')
        with self.lock:
            old = self.current(key)
            revision = old['revision'] if old else 0
            if revision != payload['revision']:
                raise RuntimeError('Data sudah berubah. Muat ulang sebelum menyimpan.')
            if payload['identity_confirmed']:
                for other_key in self.pages:
                    if other_key == key:
                        continue
                    other = self.current(other_key)
                    if not other or not other['identity_confirmed']:
                        continue
                    same_writer = other['writer_id'].strip() == payload['writer_id'].strip()
                    same_nim = other['student_id'].strip() == payload['student_id'].strip()
                    same_submission = other['submission_id'].strip() == payload['submission_id'].strip()
                    if same_writer != same_nim or (same_submission and not same_writer):
                        raise ValueError('Pengelompokan bertentangan dengan identitas terkonfirmasi lain.')
            record = {**payload, 'revision': revision + 1, 'page_id': key, 'source_sha256': row['source_sha256'], 'image_sha256': row['image_sha256'], 'schema_version': 'asdos-page-review.v1'}
            path = self.reviews / f'{key}.{revision + 1:08d}.json'
            temp = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.reviews, delete=False) as f:
                    temp = Path(f.name)
                    json.dump(record, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.link(temp, path)  # Atomic and refuses to replace an existing revision.
            finally:
                if temp is not None:
                    temp.unlink(missing_ok=True)
            return record


def make_handler(store, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Paths, identities and transcripts must not enter access logs.

        def send(self, code, data, mime='application/json'):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def valid_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def authorized(self):
            return hmac.compare_digest(self.headers.get('X-Review-Token', ''), token)

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {'error':'Host tidak diizinkan'})
            uri = urlsplit(self.path)
            if uri.path == '/review.js':
                return self.send(200, Path(__file__).with_name('dataset_review.js').read_bytes(), 'application/javascript')
            if uri.path == '/':
                return self.send(200, HTML, 'text/html; charset=utf-8')
            # Images use a short-lived token in the query because <img> cannot send a header.
            image_token = parse_qs(uri.query).get('token', [''])[0]
            if not self.authorized() and not (uri.path.startswith('/image/') and hmac.compare_digest(image_token, token)):
                return self.send(403, {'error':'Token diperlukan'})
            try:
                if uri.path == '/api/pages':
                    return self.send(200, [line_review.progress(store, k) for k in store.pages])
                if uri.path.startswith('/api/lines/'):
                    return self.send(200, line_review.details(store, uri.path.removeprefix('/api/lines/')))
                if uri.path.startswith('/api/page/'):
                    return self.send(200, store.details(uri.path.removeprefix('/api/page/')))
                if uri.path.startswith('/image/'):
                    return self.send(200, store.image(uri.path.removeprefix('/image/')), 'image/png')
                return self.send(404, {'error':'Tidak ditemukan'})
            except (KeyError, ValueError, OSError):
                return self.send(404, {'error':'Halaman atau artefak tidak valid'})

        def do_POST(self):
            if not self.valid_host() or self.headers.get('Origin') != f'http://127.0.0.1:{self.server.server_port}' or not self.authorized():
                return self.send(403, {'error':'Permintaan tidak diizinkan'})
            if not (self.path.startswith('/api/page/') or self.path.startswith('/api/lines/')):
                return self.send(404, {'error':'Tidak ditemukan'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length <= 0 or length > 200000:
                    raise ValueError('Ukuran permintaan tidak valid')
                payload = json.loads(self.rfile.read(length))
                if self.path.startswith('/api/lines/'):
                    result = line_review.save(store, self.path.removeprefix('/api/lines/'), payload)
                else:
                    result = store.save(self.path.removeprefix('/api/page/'), payload)
                return self.send(200, result)
            except RuntimeError as exc:
                return self.send(409, {'error': str(exc)})
            except ValueError as exc:
                return self.send(400, {'error': str(exc)})
            except (KeyError, TypeError, OSError):
                return self.send(400, {'error':'Data tidak valid atau gagal disimpan'})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'data/private/handwriting-dataset-v1')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    os.umask(0o077)
    store = ReviewStore(args.dataset)
    token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(store, token))
    print(f'Buka http://127.0.0.1:{server.server_port}/#{token}', flush=True)
    print('Lokal saja. Hentikan dengan Ctrl+C.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
