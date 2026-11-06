"""Offline second-reader review of every OCR line; all results remain unconfirmed AI proposals."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time

from PIL import Image
from scripts.dataset_review import ReviewStore
from scripts.line_review import details
from scripts.trocr_runtime import load_model, edit_distance, sha


def save(path,data):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    os.replace(temp,path)


def run(root,model_dir,output,batch_size):
    import torch
    os.umask(0o077)
    output.mkdir(parents=True,exist_ok=True)
    model_hash=sha(model_dir/'model.safetensors')
    settings={'model_weights_sha256':model_hash,'version':'ai-second-reader.v1','batch_size':batch_size}
    config=output/'run.json'
    if config.exists() and json.loads(config.read_text())!=settings:
        raise ValueError('Existing run configuration differs')
    save(config,settings)
    store=ReviewStore(root)
    processor,model,device=load_model(model_dir);model.eval()
    summaries=[];started=time.monotonic()
    for number,(key,row) in enumerate(store.pages.items(),1):
        path=output/(key+'.json')
        image_data=store.image(key)
        existing=json.loads(path.read_text()) if path.exists() else None
        if existing and existing.get('complete'):
            if existing['image_sha256']!=row['image_sha256']:raise ValueError('Image changed')
            summaries.append(existing);continue
        page=details(store,key)
        record={'page_id':key,'image_sha256':row['image_sha256'],'source_sha256':row['source_sha256'],
                'model_weights_sha256':model_hash,'status':'ai_review_requires_confirmation','complete':False,
                'lines':[],'flags':['confirm_full_page_coverage','confirm_identity_and_writer','confirm_every_crop'],
                'base_line_review_revision':page['revision']}
        with Image.open(Path(root)/row['image_path']) as original:
            image=original.convert('RGB');w,h=image.size
            lines=page['lines']
            for start in range(0,len(lines),batch_size):
                chunk=lines[start:start+batch_size];crops=[]
                for line in chunk:crops.append(image.crop(line['bbox_pixels']))
                try:
                    pixels=processor(images=crops,return_tensors='pt').pixel_values.to(device)
                    with torch.inference_mode():generated=model.generate(pixels,max_new_tokens=96,num_beams=1,do_sample=False)
                    predictions=processor.batch_decode(generated,skip_special_tokens=True)
                    errors=[None]*len(chunk)
                except (RuntimeError,ValueError) as exc:
                    predictions=[None]*len(chunk);errors=[type(exc).__name__]*len(chunk)
                    if device=='mps':torch.mps.empty_cache()
                finally:
                    for crop in crops:crop.close()
                for line,prediction,error in zip(chunk,predictions,errors):
                    b=line['bbox_pixels'];text=line['text'];flags=[]
                    identity=bool(re.search(r'\b(nama|nim|kelas|name|student\s*id)\b',text,re.I)) and b[1]<h*.4
                    if identity:flags.append('possible_identity')
                    if b[1]<h*.35:flags.append('inspect_header_privacy')
                    if b[3]-b[1]<10 or b[2]-b[0]<25:flags.append('very_small_crop')
                    if error:flags.append('second_reader_failed')
                    elif text!=prediction:flags.append('readers_disagree')
                    if prediction and '[tidak terbaca]' in prediction.lower():flags.append('unreadable')
                    if not prediction:flags.append('empty_second_reader')
                    # Retain the original literal proposal on disagreement; no automatic gold promotion.
                    record['lines'].append({'line_id':line['line_id'],'bbox_pixels':b,'text_proposal':text,
                        'second_reader_text':prediction,'edit_distance_between_readers':edit_distance(text,prediction) if prediction is not None else None,
                        'kind_proposal':'identity' if identity else 'unreviewed','confirmed':False,'flags':flags,
                        'second_reader_error':error})
                save(path,record)
            image.close()
        for i,line in enumerate(record['lines']):
            a=line['bbox_pixels']
            for j,other in enumerate(record['lines']):
                if i>=j:continue
                b=other['bbox_pixels'];inter=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
                if inter:
                    line['flags'].append('overlapping_boxes');other['flags'].append('overlapping_boxes')
                vertical=max(0,min(a[3],b[3])-max(a[1],b[1]))/min(a[3]-a[1],b[3]-b[1])
                if vertical>.6 and not inter:
                    line['flags'].append('possible_same_line_fragment');other['flags'].append('possible_same_line_fragment')
        record['complete']=True;save(path,record);summaries.append(record)
        print(f"{number}/{len(store.pages)} pages; {sum(len(s['lines']) for s in summaries)} lines compared; {round(time.monotonic()-started)}s",flush=True)
    candidates=defaultdict(list);unresolved=[]
    for record in summaries:
        ids=set()
        for line in record['lines']:
            if 'possible_identity' not in line['flags']:continue
            values=[]
            for text in (line['text_proposal'],line['second_reader_text'] or ''):
                if re.search(r'\bN\s*I\s*M\b',text,re.I):
                    values.append(set(re.sub(r'\s','',m) for m in re.findall(r'(?<!\d)(?:\d[ \t]*){8,16}(?!\d)',text)))
                else:values.append(set())
            ids.update(values[0]&values[1])
        if len(ids)==1:candidates[next(iter(ids))].append(record['page_id'])
        else:unresolved.append(record['page_id'])
    groups=[]
    for nim,pages in sorted(candidates.items()):
        # All occurrences of an exact candidate share one proposed split. Never freeze unconfirmed identities.
        bucket=int(hashlib.sha256(('asdos-split-v1:'+nim).encode()).hexdigest()[:8],16)%10
        split='train' if bucket<4 else 'development' if bucket<6 else 'calibration' if bucket<8 else 'locked_test'
        groups.append({'writer_id_proposal':'writer-'+hashlib.sha256(nim.encode()).hexdigest()[:12],
                       'nim_candidate':nim,'pages':pages,'split_proposal':split,'status':'unconfirmed_identity_consensus'})
    save(output/'groups-and-splits.json',{'status':'proposals_only_not_frozen','groups':groups,'unresolved_pages':unresolved,
         'warning':'Reader agreement does not confirm identity. Unresolved pages have no assigned split.'})
    report={'pages':len(summaries),'lines':sum(len(s['lines']) for s in summaries),
        'reader_disagreements':sum('readers_disagree' in l['flags'] for s in summaries for l in s['lines']),
        'reader_failures':sum(bool(l['second_reader_error']) for s in summaries for l in s['lines']),
        'identity_consensus_pages':sum(len(g['pages']) for g in groups),'unresolved_identity_pages':len(unresolved),
        'human_confirmed_by_this_run':0,'training_ready':False,'device':device,'model_weights_sha256':model_hash,
        'seconds':round(time.monotonic()-started),'status':'ai_review_completed'}
    save(output/'report.json',report);print(json.dumps(report),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--model-dir',type=Path,default=Path('models/trocr-base-handwritten'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--batch-size',type=int,default=8)
    a=p.parse_args()
    if not 1<=a.batch_size<=32:p.error('batch-size must be 1..32')
    run(a.dataset,a.model_dir,a.output,a.batch_size)
