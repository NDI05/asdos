"""Local-only TrOCR fine-tuning with reviewed, writer-disjoint line manifests."""
import argparse, hashlib, json, os, random
from pathlib import Path

def validate(samples):
    writers={}; images={}; ids=set()
    for s in samples:
        if s['sample_id'] in ids:raise ValueError('Duplicate sample')
        ids.add(s['sample_id'])
        if s.get('status')!='human_confirmed' or not s.get('identity_free_crop_confirmed'):
            raise ValueError('Unconfirmed labels or identity removal')
        if not s.get('writer_id') or s.get('split') not in ('train','development'):
            raise ValueError('Writer and train/development split required')
        for groups,key in ((writers,s['writer_id']),(images,s['image_sha256'])):
            if key in groups and groups[key]!=s['split']:raise ValueError('Split leakage')
            groups[key]=s['split']
    if {s['split'] for s in samples}!={'train','development'}:raise ValueError('Both train and development required')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path);p.add_argument('--model-dir',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--epochs',type=int,default=3)
    p.add_argument('--smoke',action='store_true')
    a=p.parse_args();os.umask(0o077)
    if a.output.exists():p.error('Output exists; preserve prior runs')
    a.output.mkdir(parents=True)
    report={'status':'blocked','model_promoted':False}
    try:
        import torch
        random.seed(42);torch.manual_seed(42)
        device='mps' if torch.backends.mps.is_available() else 'cpu'
        report['device']=device;report['torch_version']=torch.__version__
        if a.smoke:
            model=torch.nn.Linear(8,1).to(device)
            x=torch.randn(16,8,device=device);y=x.sum(1,keepdim=True)
            opt=torch.optim.SGD(model.parameters(),lr=0.05)
            losses=[]
            for _ in range(10):
                opt.zero_grad();loss=((model(x)-y)**2).mean();loss.backward();opt.step();losses.append(loss.item())
            report.update(status='synthetic_optimizer_smoke_completed',loss_before=losses[0],loss_after=losses[-1],handwriting_accuracy_measured=False)
        else:
            if not a.manifest or not a.model_dir:raise ValueError('Manifest and local model directory required')
            from scripts.trocr_runtime import load_manifest, load_model, pixels, evaluate, sha
            samples=load_manifest(a.manifest)
            train=[s for s in samples if s['split']=='train']
            dev=[s for s in samples if s['split']=='development']
            if not train or not dev:raise ValueError('Both train and development required')
            if a.epochs < 1:raise ValueError('Epochs must be positive')
            report.update(input_samples=len(samples),train_samples=len(train),development_samples=len(dev),
                          manifest_sha256=sha(a.manifest),base_weights_sha256=sha(a.model_dir/'model.safetensors'))
            processor,model,device=load_model(a.model_dir)
            report['baseline'],_=evaluate(model,processor,dev,device)
            if report['baseline']['failures'] or report['baseline']['generation_limit_reached']:
                raise ValueError('Baseline inference failed or reached generation limit')
            opt=torch.optim.AdamW(model.parameters(),lr=5e-5)
            best=float('inf');history=[]
            for epoch in range(a.epochs):
                model.train();total=0;random.shuffle(train)
                for sample in train:
                    tokens=processor.tokenizer(sample['text'],return_tensors='pt').input_ids.to(device)
                    if tokens.shape[1]>model.decoder.config.max_position_embeddings:raise ValueError('Line too long')
                    loss=model(pixel_values=pixels(processor,sample,device),labels=tokens).loss
                    if not torch.isfinite(loss):raise ValueError('Nonfinite loss')
                    opt.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1);opt.step()
                    total+=loss.item()
                measured,predictions=evaluate(model,processor,dev,device)
                if measured['failures'] or measured['generation_limit_reached']:
                    raise ValueError('Development inference failed or reached generation limit')
                history.append({'epoch':epoch+1,'train_loss':total/len(train),'development':measured})
                report['history']=history
                if measured['cer_micro']<best:
                    best=measured['cer_micro'];model.save_pretrained(a.output/'best');processor.save_pretrained(a.output/'best')
                    (a.output/'development-predictions.jsonl').write_text(''.join(json.dumps(s,ensure_ascii=False)+'\n' for s in predictions))
                    report['best_development']=measured
                else:break
                (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
            report.update(status='training_completed',evaluation_metrics_measured=True,
                handwriting_accuracy_measured=not any('fixture' in sample for sample in samples),
                data_kind='synthetic_fixture' if any('fixture' in sample for sample in samples) else 'reviewed_lines',
                improvement_development_cer=report['baseline']['cer_micro']-best,
                notes='Development comparison only; locked-test evaluation and release gate remain separate.')

    except Exception as exc:
        report.update(status='blocked_or_failed',reason=str(exc))
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report));return 0 if report['status'] in ('training_completed','synthetic_optimizer_smoke_completed') else 2

if __name__=='__main__':raise SystemExit(main())
