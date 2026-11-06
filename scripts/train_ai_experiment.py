"""Explicit opt-in pseudo-label training; no evaluation or model promotion."""
import argparse,json,os,random
from pathlib import Path
from scripts.trocr_runtime import load_model,sha
from PIL import Image


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--model-dir',type=Path,default=Path('models/trocr-base-handwritten'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--steps',type=int,default=10)
    p.add_argument('--allow-ai-labels',action='store_true',required=True)
    p.add_argument('--include-disagreements',action='store_true')
    a=p.parse_args();os.umask(0o077)
    if a.steps<1 or a.output.exists():p.error('Positive steps and a new output directory required')
    root=a.dataset.resolve();manifest=root/'annotations.jsonl'
    report=json.loads((root/'report.json').read_text())
    if sha(manifest)!=report['manifest_sha256']:p.error('Manifest hash changed')
    samples=[json.loads(l) for l in manifest.read_text().splitlines() if l.strip()]
    samples=[s for s in samples if not s['duplicate_of'] and (a.include_disagreements or s['tier']=='ai_consensus')]
    if not samples:p.error('No eligible AI samples')
    for s in samples:
        path=(root/s['image_path']).resolve()
        if not path.is_relative_to(root) or sha(path)!=s['image_sha256']:p.error('Crop path/hash invalid')
        if s['status']!='ai_proposal' or s['split']!='train_only_unverified':p.error('Unexpected label provenance')
    import torch
    torch.manual_seed(42);random.seed(42)
    processor,model,device=load_model(a.model_dir);model.train()
    opt=torch.optim.AdamW(model.parameters(),lr=1e-5);losses=[]
    a.output.mkdir(parents=True)
    result={'status':'running','label_source':'ai_unverified','evaluation_performed':False,'model_promoted':False,
        'handwriting_accuracy_measured':False,'manifest_sha256':sha(manifest),'eligible_samples':len(samples),'device':device,
        'include_disagreements':a.include_disagreements}
    try:
        for step in range(a.steps):
            sample=random.choice(samples)
            with Image.open(root/sample['image_path']) as image:
                pixels=processor(images=image.convert('RGB'),return_tensors='pt').pixel_values.to(device)
            labels=processor.tokenizer(sample['text'],return_tensors='pt').input_ids.to(device)
            if labels.shape[1]>model.decoder.config.max_position_embeddings:raise ValueError('Label too long')
            loss=model(pixel_values=pixels,labels=labels).loss
            if not torch.isfinite(loss):raise ValueError('Nonfinite loss')
            opt.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1);opt.step()
            losses.append(loss.item())
        model.save_pretrained(a.output/'checkpoint');processor.save_pretrained(a.output/'checkpoint')
        result.update(status='ai_label_experiment_completed',steps=len(losses),training_losses=losses,
            notes='Training loss on AI labels only. No claim of improvement or student-label correctness; default model unchanged.')
    except Exception as exc:result.update(status='failed',error_type=type(exc).__name__)
    (a.output/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    return 0 if result['status']=='ai_label_experiment_completed' else 2

if __name__=='__main__':raise SystemExit(main())
