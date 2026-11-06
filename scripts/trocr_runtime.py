"""Local TrOCR runtime, literal metrics and reviewed manifest validation."""
import hashlib
import json
import math
import os
from pathlib import Path
from PIL import Image

SPLITS = ('train','development','calibration','locked_test')


def edit_distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        new=[i]
        for j,y in enumerate(b,1):new.append(min(new[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=new
    return row[-1]


def metrics(pairs):
    ce=we=chars=words=empty=empty_errors=0
    for reference,prediction in pairs:
        ce+=edit_distance(reference,prediction);chars+=len(reference)
        we+=edit_distance(reference.split(),prediction.split());words+=len(reference.split())
        if not reference:
            empty+=1;empty_errors+=bool(prediction)
    return {'cer_micro':ce/chars if chars else None,'wer_micro':we/words if words else None,
            'character_edits':ce,'reference_characters':chars,'word_edits':we,'reference_words':words,
            'empty_references':empty,'empty_reference_false_positives':empty_errors,'samples':len(pairs),
            'normalization':'none; WER uses whitespace tokenization'}


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def load_manifest(path):
    samples=[json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    if not samples:raise ValueError('Manifest kosong')
    ids=set();groups={'writer':{},'image':{},'crop':{}};cache={}
    for s in samples:
        if s['sample_id'] in ids:raise ValueError('Duplicate sample')
        ids.add(s['sample_id'])
        if s.get('status')!='human_confirmed' or s.get('identity_free_crop_confirmed') is not True:
            raise ValueError('Unconfirmed labels or identity removal')
        if not isinstance(s.get('writer_id'),str) or not s['writer_id'].strip() or s.get('split') not in SPLITS:
            raise ValueError('Writer/split required')
        if not isinstance(s.get('text'),str) or not s['text'].strip() or '[tidak terbaca]' in s['text'].lower():
            raise ValueError('Label kosong/tidak terbaca')
        image=Path(s['image_path']).resolve()
        if image not in cache:
            if sha(image)!=s['image_sha256']:raise ValueError('Image hash changed')
            with Image.open(image) as im:cache[image]=(s['image_sha256'],im.size)
        digest,size=cache[image]
        if digest!=s['image_sha256']:raise ValueError('Inconsistent image hash')
        b=s['bbox_pixels'];w,h=size
        if not isinstance(b,list) or len(b)!=4 or any(type(v) is not int for v in b) or not(0<=b[0]<b[2]<=w and 0<=b[1]<b[3]<=h):
            raise ValueError('Invalid crop')
        with Image.open(image) as im:
            crop=im.convert('RGB').crop(b)
            crop_digest=hashlib.sha256(str(crop.size).encode()+crop.tobytes()).hexdigest()
        for name,key in (('writer',s['writer_id']),('image',s['image_sha256']),('crop',crop_digest)):
            prev=groups[name].get(key)
            if prev and prev!=s['split']:raise ValueError('Split leakage: '+name)
            groups[name][key]=s['split']
    return samples


def load_model(path):
    path=Path(path)
    manifest=path/'asdos-trocr-manifest.json'
    if manifest.exists():
        for name,expected in json.loads(manifest.read_text())['files'].items():
            file=(path/name).resolve()
            if not file.is_relative_to(path.resolve()) or sha(file)!=expected:
                raise ValueError('Checkpoint hash mismatch')
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    import torch
    from transformers import TrOCRProcessor,VisionEncoderDecoderModel
    processor=TrOCRProcessor.from_pretrained(str(path),local_files_only=True,trust_remote_code=False)
    model=VisionEncoderDecoderModel.from_pretrained(str(path),local_files_only=True,trust_remote_code=False)
    model.config.decoder_start_token_id=processor.tokenizer.cls_token_id
    model.config.pad_token_id=processor.tokenizer.pad_token_id
    device='mps' if torch.backends.mps.is_available() else 'cpu'
    return processor,model.to(device),device


def pixels(processor,sample,device):
    with Image.open(sample['image_path']) as im:
        crop=im.convert('RGB').crop(sample['bbox_pixels'])
        return processor(images=crop,return_tensors='pt').pixel_values.to(device)


def evaluate(model,processor,samples,device,max_tokens=128):
    import torch
    model.eval();pairs=[];predictions=[];failures=0;limited=0
    for s in samples:
        try:
            with torch.inference_mode():
                generated=model.generate(pixels(processor,s,device),max_new_tokens=max_tokens,do_sample=False,num_beams=1)
            prediction=processor.batch_decode(generated,skip_special_tokens=True)[0]
            hit_limit=generated.shape[1]>=max_tokens+1 and generated[0,-1].item()!=processor.tokenizer.eos_token_id
            limited+=hit_limit
            pairs.append((s['text'],prediction))
            predictions.append({'sample_id':s['sample_id'],'predicted_text':prediction,'generation_limit_reached':hit_limit})
        except (RuntimeError,ValueError) as exc:
            failures+=1;predictions.append({'sample_id':s['sample_id'],'error_type':type(exc).__name__})
    report={**metrics(pairs),'requested_samples':len(samples),'failures':failures,
            'coverage':len(pairs)/len(samples) if samples else 0,'generation_limit_reached':limited,
            'max_new_tokens':max_tokens,'gate_decision':'not_assessed'}
    return report,predictions
