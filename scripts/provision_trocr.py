"""Download pinned public TrOCR weights only; no student data is read or uploaded."""
import argparse
import hashlib
import json
import os
from pathlib import Path

MODEL_ID = 'microsoft/trocr-base-handwritten'
REVISION = 'eaacaf452b06415df8f10bb6fad3a4c11e609406'
FILES = ['README.md','config.json','generation_config.json','merges.txt','model.safetensors',
         'preprocessor_config.json','special_tokens_map.json','tokenizer_config.json','vocab.json']


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=Path('models/trocr-base-handwritten'))
    a=p.parse_args();os.umask(0o077)
    from huggingface_hub import snapshot_download
    a.output.mkdir(parents=True,exist_ok=True)
    snapshot_download(MODEL_ID,revision=REVISION,local_dir=a.output,allow_patterns=FILES,max_workers=2)
    hashes={name:digest(a.output/name) for name in FILES}
    (a.output/'asdos-trocr-manifest.json').write_text(json.dumps({'model_id':MODEL_ID,'revision':REVISION,'license':'MIT','files':hashes},indent=2)+'\n')
    print('TrOCR pinned checkpoint downloaded and hashed.',flush=True)

if __name__=='__main__':main()
