"""Generate local predictions and literal CER/WER against reviewed references."""
import argparse,json,os
from pathlib import Path
from scripts.trocr_runtime import load_manifest,load_model,evaluate,sha


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--model-dir',type=Path,required=True)
    p.add_argument('--split',choices=['development','calibration','locked_test'],default='development')
    p.add_argument('--allow-locked-test',action='store_true',help='Only after settings and gates have been frozen')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();os.umask(0o077)
    if a.output.exists():p.error('Output exists')
    if a.split=='locked_test' and not a.allow_locked_test:p.error('Locked test requires --allow-locked-test after experiment freeze')
    samples=load_manifest(a.manifest);selected=[s for s in samples if s['split']==a.split]
    if not selected:p.error('No samples in requested split')
    a.output.mkdir(parents=True)
    processor,model,device=load_model(a.model_dir)
    report,predictions=evaluate(model,processor,selected,device)
    report.update(data_kind='synthetic_fixture' if any('fixture' in s for s in selected) else 'reviewed_lines',model_promoted=False,split=a.split,device=device,manifest_sha256=sha(a.manifest),model_dir=str(a.model_dir.resolve()),model_weights_sha256=sha(a.model_dir/'model.safetensors'))
    (a.output/'predictions.jsonl').write_text(''.join(json.dumps(s,ensure_ascii=False)+'\n' for s in predictions))
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report));return 0 if not report['failures'] else 2

if __name__=='__main__':raise SystemExit(main())
