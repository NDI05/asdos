import csv,hashlib,json
from PIL import Image
from scripts.export_ai_experiment import export


def test_experimental_export_keeps_ai_provenance_and_excludes_header(tmp_path):
    root=tmp_path/'source';(root/'pages').mkdir(parents=True);(root/'ai-review-v3').mkdir()
    image=root/'pages/p.png';Image.new('RGB',(100,100),'white').save(image)
    digest=hashlib.sha256(image.read_bytes()).hexdigest()
    with (root/'pages.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['page_id','image_path']);w.writeheader();w.writerow({'page_id':'p','image_path':'pages/p.png'})
    review={'complete':True,'image_sha256':digest,'source_sha256':'a'*64,'lines':[
        {'line_id':'header','text_proposal':'name','second_reader_text':'name','bbox_pixels':[0,0,80,10],'flags':['possible_identity']},
        {'line_id':'body','text_proposal':'abc','second_reader_text':'abc','bbox_pixels':[0,60,80,80],'flags':[]}]}
    (root/'ai-review-v3/p.json').write_text(json.dumps(review))
    output=tmp_path/'export';report=export(root,output)
    assert report['samples']==report['consensus_samples']==1 and report['excluded']==1
    assert not report['human_verified'] and not report['valid_for_gold_evaluation']
    sample=json.loads((output/'annotations.jsonl').read_text())
    assert sample['status']=='ai_proposal' and sample['split']=='train_only_unverified'
    assert sample['image_sha256']==hashlib.sha256((output/sample['image_path']).read_bytes()).hexdigest()
