"""Package private AI-labeled crops for training-only experiments, never gold evaluation."""
import argparse,csv,hashlib,json,os
from pathlib import Path
from PIL import Image


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def export(root,output):
    if output.exists():raise ValueError('Output exists; choose a new version')
    os.umask(0o077);output.mkdir(parents=True);(output/'images').mkdir()
    with (root/'pages.csv').open(newline='') as f:pages=list(csv.DictReader(f))
    samples=[];excluded=[];seen={}
    for page in pages:
        review=json.loads((root/'ai-review-v3'/f"{page['page_id']}.json").read_text())
        source=root/page['image_path']
        if not review['complete'] or digest(source)!=review['image_sha256']:raise ValueError('Incomplete or changed source')
        with Image.open(source) as image:
            for line in review['lines']:
                flags=line['flags'];text=line['text_proposal'];box=line['bbox_pixels']
                reasons=[]
                if 'possible_identity' in flags or 'inspect_header_privacy' in flags:reasons.append('potential_identity_or_header')
                if not text.strip():reasons.append('empty_label')
                if 'second_reader_failed' in flags:reasons.append('reader_failed')
                if box[0]>=box[2] or box[1]>=box[3]:reasons.append('invalid_box')
                key=page['page_id']+'-'+line['line_id']
                if reasons:
                    excluded.append({'sample_id':key,'reasons':reasons});continue
                path=output/'images'/f'{key}.png'
                crop=image.convert('RGB').crop(box);crop.save(path);crop.close()
                image_hash=digest(path)
                # Keep duplicates out of the default training pool; preserve their provenance.
                duplicate_of=seen.get(image_hash);seen.setdefault(image_hash,key)
                tier='ai_consensus' if text==line['second_reader_text'] else 'ai_disagreement'
                samples.append({'sample_id':key,'image_path':str(path.relative_to(output)),'image_sha256':image_hash,
                    'page_id':page['page_id'],'source_sha256':review['source_sha256'],'source_image_sha256':review['image_sha256'],
                    'source_bbox_pixels':box,'text':text,'alternative_text':line['second_reader_text'],
                    'label_source':'ai_ocr_unverified','status':'ai_proposal','tier':tier,
                    'split':'train_only_unverified','writer_id':None,'duplicate_of':duplicate_of,
                    'identity_free_crop_confirmed':False,'flags':flags})
    raw=''.join(json.dumps(s,ensure_ascii=False)+'\n' for s in samples)
    (output/'annotations.jsonl').write_text(raw)
    (output/'excluded.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in excluded))
    # Verify encoded artifacts, not just metadata created in memory.
    for sample in samples:
        path=output/sample['image_path']
        assert digest(path)==sample['image_sha256']
        with Image.open(path) as image:image.verify()
    report={'schema_version':'asdos-ai-experiment.v1','status':'packaged_and_integrity_verified',
        'source_pages':len(pages),'samples':len(samples),'excluded':len(excluded),
        'consensus_samples':sum(s['tier']=='ai_consensus' and not s['duplicate_of'] for s in samples),
        'disagreement_samples':sum(s['tier']=='ai_disagreement' for s in samples),
        'manifest_sha256':hashlib.sha256(raw.encode()).hexdigest(),'human_verified':False,
        'identity_redaction_verified':False,'valid_for_gold_evaluation':False,'writer_disjoint_split_frozen':False,
        'use':'private training-only AI-label experiments; no accuracy or anonymization claim'}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    (output/'README.md').write_text('''# Dataset eksperimen berlabel AI\n\nSemua label adalah usulan AI, bukan gold. Crop kandidat memuat jawaban dari area di luar header; ini bukan bukti redaksi identitas menyeluruh. Simpan privat. Tidak ada split evaluasi atau klaim writer-disjoint. Nama/NIM yang mungkin tersisa perlu diperiksa sebelum penggunaan lain.\n\nDefault trainer hanya menggunakan baris yang dibaca identik kedua model dan bukan duplikat. Memasukkan label disagreement memerlukan opsi eksplisit. Kesepakatan model tidak membuktikan kebenaran. Jangan memakai paket ini untuk mengukur akurasi terhadap manusia atau mengganti model default. Asli, alternatif teks, flag dan koordinat sumber tetap terlacak.\n''')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(export(a.dataset,a.output)))
