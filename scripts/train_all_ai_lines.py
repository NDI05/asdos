"""One complete, resumable local TrOCR epoch on explicit AI labels; training-fit metrics only."""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import random
import time

from PIL import Image
from scripts.trocr_runtime import load_model, sha, metrics


def write_json(path, value):
    temp=path.with_suffix('.tmp')
    with temp.open('w') as f:
        json.dump(value,f,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)


def load_samples(root):
    manifest=root/'annotations.jsonl';meta=json.loads((root/'report.json').read_text())
    if sha(manifest)!=meta['manifest_sha256']:raise ValueError('Manifest hash changed')
    samples=[json.loads(l) for l in manifest.read_text().splitlines() if l.strip()]
    if len(samples)!=meta['samples'] or len({s['sample_id'] for s in samples})!=len(samples):
        raise ValueError('Sample count/IDs invalid')
    for s in samples:
        path=(root/s['image_path']).resolve()
        if not path.is_relative_to(root) or sha(path)!=s['image_sha256']:raise ValueError('Image path/hash invalid')
        if s['label_source']!='ai_ocr_unverified' or s['status']!='ai_proposal' or s['split']!='train_only_unverified':
            raise ValueError('Unexpected label provenance')
        if not isinstance(s['text'],str) or not s['text'].strip():raise ValueError('Empty label')
        with Image.open(path) as image:image.verify()
    return samples,sha(manifest)


def batch_order(count,batch_size,seed):
    indices=list(range(count));random.Random(seed).shuffle(indices)
    return [indices[i:i+batch_size] for i in range(0,count,batch_size)]


def images(root, batch):
    result=[]
    for s in batch:
        with Image.open(root/s['image_path']) as image:result.append(image.convert('RGB'))
    return result


def evaluation(root, samples, model, processor, device, output, phase, progress, config):
    import torch
    model.eval();path=output/(phase+'-predictions.jsonl')
    predictions=[json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []
    if len(predictions)>len(samples) or any(p['sample_id']!=s['sample_id'] for p,s in zip(predictions,samples)):
        raise ValueError('Prediction resume order mismatch')
    batch_size=config['evaluation_batch_size']
    with path.open('a') as stream:
        for start in range(len(predictions),len(samples),batch_size):
            batch=samples[start:start+batch_size];opened=images(root,batch)
            try:
                pixels=processor(images=opened,return_tensors='pt').pixel_values.to(device)
                with torch.inference_mode():
                    generated=model.generate(pixels,max_new_tokens=config['max_new_tokens'],num_beams=1,do_sample=False)
                texts=processor.batch_decode(generated,skip_special_tokens=True)
                results=[]
                for row,s,text in zip(generated,batch,texts):
                    ids=row.tolist();eos=processor.tokenizer.eos_token_id
                    # Decoder starts with CLS (not EOS); inspect only newly generated tokens.
                    limited=eos not in ids[1:] and len(ids)-1>=config['max_new_tokens']
                    results.append({'sample_id':s['sample_id'],'predicted_text':text,'generation_limit_reached':limited})
            finally:
                for image in opened:image.close()
            for result in results:stream.write(json.dumps(result,ensure_ascii=False)+'\n')
            stream.flush();os.fsync(stream.fileno());predictions.extend(results)
            progress.update(phase=phase,evaluated_samples=len(predictions),evaluation_total=len(samples))
            write_json(output/'progress.json',progress)
            if len(predictions)%128<batch_size or len(predictions)==len(samples):
                print(f'{phase}: {len(predictions)}/{len(samples)}',flush=True)
    pairs=[(s['text'],p['predicted_text']) for s,p in zip(samples,predictions)]
    report={**metrics(pairs),'coverage':len(predictions)/len(samples),'failures':0,
        'generation_limit_reached':sum(p['generation_limit_reached'] for p in predictions),
        'comparison_scope':'training_data_vs_unverified_ai_labels','human_accuracy_measured':False,
        'per_tier':{tier:metrics([pair for pair,s in zip(pairs,samples) if s['tier']==tier]) for tier in ('ai_consensus','ai_disagreement')}}
    write_json(output/(phase+'-metrics.json'),report)
    return report


def checkpoint(output, model, processor, optimizer, next_batch, seen, token_loss_sum, tokens, updates):
    import torch
    folder=output/f'resume-step-{next_batch:04d}'
    attempt=0
    while folder.exists():
        attempt+=1;folder=output/f'resume-step-{next_batch:04d}-attempt-{attempt}'
    folder.mkdir();model.save_pretrained(folder);processor.save_pretrained(folder)
    state={'optimizer':optimizer.state_dict(),'next_batch':next_batch,'seen':seen,'token_loss_sum':token_loss_sum,
           'tokens':tokens,'updates':updates,'cpu_rng':torch.get_rng_state(),
           'mps_rng':torch.mps.get_rng_state() if torch.backends.mps.is_available() else None}
    torch.save(state,folder/'optimizer-state.pt')
    write_json(folder/'complete.json',{'next_batch':next_batch,'seen':seen,'weights_sha256':sha(folder/'model.safetensors')})
    write_json(output/'resume-pointer.json',{'checkpoint':folder.name})
    return folder


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--model-dir',type=Path,default=Path('models/trocr-base-handwritten'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--batch-size',type=int,default=4)
    p.add_argument('--eval-batch-size',type=int,default=16);p.add_argument('--resume',action='store_true')
    p.add_argument('--allow-ai-labels',action='store_true',required=True)
    a=p.parse_args();os.umask(0o077)
    if not 1<=a.batch_size<=16 or not 1<=a.eval_batch_size<=32:p.error('Batch size out of bounds')
    if a.output.exists() and not a.resume:p.error('Use new output or explicit --resume')
    root=a.dataset.resolve();samples,manifest_hash=load_samples(root)
    config={'manifest_sha256':manifest_hash,'base_weights_sha256':sha(a.model_dir/'model.safetensors'),
        'samples':len(samples),'epochs':1,'seed':42,'batch_size':a.batch_size,
        'evaluation_batch_size':a.eval_batch_size,'max_new_tokens':128,'learning_rate':1e-5,
        'optimizer':'AdamW','gradient_clip':1.0,'label_source':'ai_unverified',
        'evaluation_scope':'training_fit_only_no_held_out_test'}
    a.output.mkdir(parents=True,exist_ok=True)
    config_path=a.output/'config.json'
    if config_path.exists() and json.loads(config_path.read_text())!=config:raise ValueError('Resume configuration mismatch')
    write_json(config_path,config)
    if (a.output/'report.json').exists():
        old=json.loads((a.output/'report.json').read_text())
        if old.get('status')=='completed':print(json.dumps(old));return 0
    import torch
    torch.manual_seed(42);random.seed(42)
    progress={'status':'running','samples':len(samples),'started_unix':time.time()}
    write_json(a.output/'progress.json',progress)
    try:
        processor,model,device=load_model(a.model_dir)
        model.generation_config.decoder_start_token_id=processor.tokenizer.cls_token_id
        model.generation_config.eos_token_id=processor.tokenizer.eos_token_id
        model.generation_config.pad_token_id=processor.tokenizer.pad_token_id
        progress['device']=device
        baseline=evaluation(root,samples,model,processor,device,a.output,'before',progress,config)
        batches=batch_order(len(samples),a.batch_size,42)
        optimizer=torch.optim.AdamW(model.parameters(),lr=1e-5)
        first=seen=tokens=0;token_loss_sum=0.;updates=0
        pointer=a.output/'resume-pointer.json'
        if pointer.exists():
            folder=a.output/json.loads(pointer.read_text())['checkpoint']
            complete=json.loads((folder/'complete.json').read_text())
            if sha(folder/'model.safetensors')!=complete['weights_sha256']:raise ValueError('Resume weights changed')
            del model,optimizer;gc.collect()
            if device=='mps':torch.mps.empty_cache()
            processor,model,device=load_model(folder)
            optimizer=torch.optim.AdamW(model.parameters(),lr=1e-5)
            state=torch.load(folder/'optimizer-state.pt',map_location='cpu',weights_only=True)
            optimizer.load_state_dict(state['optimizer']);torch.set_rng_state(state['cpu_rng'])
            if device=='mps' and state['mps_rng'] is not None:torch.mps.set_rng_state(state['mps_rng'])
            first=state['next_batch'];seen=state['seen'];tokens=state['tokens'];token_loss_sum=state['token_loss_sum'];updates=state['updates']
            del state
        order=[samples[i]['sample_id'] for b in batches for i in b]
        write_json(a.output/'training-order.json',order)
        model.train()
        for step in range(first,len(batches)):
            batch=[samples[i] for i in batches[step]];opened=images(root,batch)
            try:pixels=processor(images=opened,return_tensors='pt').pixel_values.to(device)
            finally:
                for image in opened:image.close()
            encoded=processor.tokenizer([s['text'] for s in batch],padding=True,return_tensors='pt')
            if encoded.input_ids.shape[1]>model.decoder.config.max_position_embeddings:raise ValueError('Label too long')
            labels=encoded.input_ids.masked_fill(encoded.attention_mask==0,-100).to(device)
            loss=model(pixel_values=pixels,labels=labels).loss
            if not torch.isfinite(loss):raise ValueError('Nonfinite loss')
            optimizer.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1);optimizer.step()
            valid_tokens=int(encoded.attention_mask.sum());token_loss_sum+=loss.item()*valid_tokens;tokens+=valid_tokens
            seen+=len(batch);updates+=1
            with (a.output/'training-log.jsonl').open('a') as stream:
                stream.write(json.dumps({'update':step+1,'seen':seen,'loss':loss.item(),'tokens':valid_tokens})+'\n')
            progress.update(phase='training',trained_samples=seen,optimizer_updates=updates,mean_token_loss=token_loss_sum/tokens)
            write_json(a.output/'progress.json',progress)
            if (step+1)%25==0 or seen==len(samples):print(f'training: {seen}/{len(samples)} samples; update {step+1}/{len(batches)}; mean token loss {token_loss_sum/tokens:.4f}',flush=True)
            if (step+1)%200==0 or step+1==len(batches):
                folder=checkpoint(a.output,model,processor,optimizer,step+1,seen,token_loss_sum,tokens,updates)
        if seen!=len(samples):raise ValueError('Full epoch coverage mismatch')
        # Save distinct final model, then actually reload it for the after comparison.
        final=a.output/'model-final'
        if not final.exists():
            model.save_pretrained(final);processor.save_pretrained(final)
        final_hash=sha(final/'model.safetensors')
        del model,optimizer;gc.collect()
        if device=='mps':torch.mps.empty_cache()
        processor,model,device=load_model(final)
        after=evaluation(root,samples,model,processor,device,a.output,'after',progress,config)
        result={'status':'completed','samples_trained':seen,'epochs':1,'optimizer_updates':updates,'device':device,
            'manifest_sha256':manifest_hash,'final_weights_sha256':final_hash,'model_directory':str(final.resolve()),
            'mean_training_token_loss':token_loss_sum/tokens,'before':baseline,'after':after,
            'cer_change_before_minus_after':baseline['cer_micro']-after['cer_micro'],
            'wer_change_before_minus_after':baseline['wer_micro']-after['wer_micro'],
            'human_accuracy_measured':False,'held_out_evaluation':False,'model_promoted':False,
            'notes':'Full training-set fit against AI labels only. No writer-disjoint/generalization or human accuracy claim.'}
        write_json(a.output/'report.json',result);progress.update(status='completed',phase='finished');write_json(a.output/'progress.json',progress)
        print(json.dumps(result),flush=True);return 0
    except Exception as exc:
        progress.update(status='failed',error_type=type(exc).__name__,error=str(exc));write_json(a.output/'progress.json',progress)
        print(json.dumps(progress),flush=True);return 2

if __name__=='__main__':raise SystemExit(main())
