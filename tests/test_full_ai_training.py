import csv,hashlib,json
from PIL import Image
import pytest
from scripts.train_all_ai_lines import batch_order,load_samples


def test_full_epoch_uses_every_sample_once_including_last_batch():
    batches=batch_order(2348,4,42)
    assert len(batches)==587
    flat=[i for batch in batches for i in batch]
    assert len(flat)==len(set(flat))==2348
    assert sorted(flat)==list(range(2348))
    assert batches==batch_order(2348,4,42)
    assert [len(b) for b in batch_order(5,4,42)]==[4,1]


def test_private_manifest_integrity_and_provenance(tmp_path):
    image=tmp_path/'sample.png';Image.new('RGB',(20,10),'white').save(image)
    record={'sample_id':'s1','image_path':'sample.png','image_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
            'text':'abc','status':'ai_proposal','label_source':'ai_ocr_unverified','split':'train_only_unverified'}
    raw=json.dumps(record)+'\n'
    (tmp_path/'annotations.jsonl').write_text(raw)
    (tmp_path/'report.json').write_text(json.dumps({'manifest_sha256':hashlib.sha256(raw.encode()).hexdigest(),'samples':1}))
    samples,digest=load_samples(tmp_path)
    assert samples[0]['status']=='ai_proposal'
    image.write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash'):load_samples(tmp_path)


def test_training_fit_evaluation_reports_limits_and_reuses_committed_predictions(tmp_path):
    import torch
    from types import SimpleNamespace
    from scripts.train_all_ai_lines import evaluation
    samples=[]
    for i in range(2):
        path=tmp_path/f'{i}.png';Image.new('RGB',(20,10),'white').save(path)
        samples.append({'sample_id':f's{i}','image_path':path.name,'text':'abc','tier':'ai_consensus'})
    class Processor:
        tokenizer=SimpleNamespace(eos_token_id=2)
        def __call__(self,images,return_tensors):return SimpleNamespace(pixel_values=torch.zeros(len(images),3,2,2))
        def batch_decode(self,generated,skip_special_tokens):return ['abc']*len(generated)
    class Model:
        calls=0
        def eval(self):pass
        def generate(self,pixels,**kwargs):
            self.calls+=1
            return torch.tensor([[0,9,2],[0,9,9]])
    model=Model();output=tmp_path/'run';output.mkdir()
    report=evaluation(tmp_path,samples,model,Processor(),'cpu',output,'before',{},
                      {'evaluation_batch_size':2,'max_new_tokens':2})
    assert report['cer_micro']==0 and report['coverage']==1
    assert report['generation_limit_reached']==1
    assert not report['human_accuracy_measured']
    assert model.calls==1
    again=evaluation(tmp_path,samples,model,Processor(),'cpu',output,'before',{},
                      {'evaluation_batch_size':2,'max_new_tokens':2})
    assert again==report and model.calls==1
