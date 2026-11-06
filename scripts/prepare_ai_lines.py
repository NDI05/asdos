"""Prepare private AI line annotations; no annotation is promoted to gold."""
import argparse, csv, hashlib, json, math, os
from pathlib import Path

def prepare(root, output):
    if output.exists():
        raise ValueError('Output exists; choose a new version')
    os.umask(0o077)
    output.mkdir(parents=True)
    identities=json.loads((root/'identity-candidates.json').read_text())
    candidates={p['page_id']:p['nim_candidates'] for p in identities['pages']}
    with (root/'pages.csv').open(newline='') as f:
        pages=list(csv.DictReader(f))
    samples=[]
    for page in pages:
        path=root/'vision-drafts'/f"{page['page_id']}.json"
        draft=json.loads(path.read_text())
        image=root/page['image_path']
        if hashlib.sha256(image.read_bytes()).hexdigest()!=page['image_sha256']:
            raise ValueError('Source image changed')
        w,h=int(page['image_width_px']),int(page['image_height_px'])
        for index,line in enumerate(draft['lines']):
            x0,y0,x1,y1=line['bbox_normalized']
            box=[math.floor(x0*w),math.floor((1-y1)*h),math.ceil(x1*w),math.ceil((1-y0)*h)]
            if not (0<=box[0]<box[2]<=w and 0<=box[1]<box[3]<=h):
                box=[max(0,min(w,box[0])),max(0,min(h,box[1])),max(0,min(w,box[2])),max(0,min(h,box[3]))]
                if box[0]>=box[2] or box[1]>=box[3]:
                    continue
            samples.append({'sample_id':f"{page['page_id']}-line-{index:03d}",
                'page_id':page['page_id'],'image_path':str(image.resolve()),
                'image_sha256':page['image_sha256'],'source_sha256':page['source_sha256'],
                'bbox_pixels':box,'text':line['text'],'label_source':'apple-vision-ai',
                'status':'needs_human_confirmation','writer_id':None,'split':None,
                'flags':['confirm_literal_text','confirm_box_and_coverage','confirm_writer_and_split','confirm_no_identity_in_crop'],
                'possible_identity_area':y1>0.65,
                'confidence_uncalibrated':line.get('confidence_uncalibrated')})
    with (output/'annotations.jsonl').open('w') as f:
        for sample in samples:f.write(json.dumps(sample,ensure_ascii=False)+'\n')
    report={'pages':len(pages),'ai_line_annotations':len(samples),'gold_samples':0,
        'training_ready':False,'notes':['All lines require confirmation, including identity removal and writer-disjoint split.','OCR can omit lines; inspect full page coverage.']}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prepare(a.dataset,a.output)
