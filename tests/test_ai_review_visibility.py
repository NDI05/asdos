import csv
import hashlib
import json
from scripts.dataset_review import ReviewStore


def test_only_completed_matching_ai_results_are_exposed(tmp_path):
    (tmp_path/'pages').mkdir()
    image=tmp_path/'pages/p.png';image.write_bytes(b'synthetic')
    row={'page_id':'p1','image_path':'pages/p.png','image_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'source_sha256':'a'*64}
    with (tmp_path/'pages.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=row);writer.writeheader();writer.writerow(row)
    folder=tmp_path/'ai-review-v3';folder.mkdir()
    file=folder/'p1.json'
    file.write_text(json.dumps({'complete':False,'image_sha256':row['image_sha256']}))
    store=ReviewStore(tmp_path)
    assert store.details('p1')['ai_review'] is None
    file.write_text(json.dumps({'complete':True,'image_sha256':row['image_sha256'],'lines':[]}))
    assert store.details('p1')['ai_review']['complete']
    file.write_text(json.dumps({'complete':True,'image_sha256':'b'*64}))
    assert store.details('p1')['ai_review'] is None


def test_staging_never_overwrites_existing_review_or_creates_confirmation(tmp_path):
    from scripts.line_review import current
    from scripts.stage_ai_review import stage
    from scripts.line_review import save
    (tmp_path/'pages').mkdir()
    image=tmp_path/'pages/p.png';image.write_bytes(b'synthetic')
    row={'page_id':'p1','image_path':'pages/p.png','image_width_px':'100','image_height_px':'100','image_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'source_sha256':'a'*64}
    with (tmp_path/'pages.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=row);w.writeheader();w.writerow(row)
    folder=tmp_path/'ai-review-v3';folder.mkdir()
    (folder/'groups-and-splits.json').write_text(json.dumps({'groups':[],'unresolved_pages':['p1']}))
    (folder/'p1.json').write_text(json.dumps({'complete':True,'image_sha256':row['image_sha256'],'lines':[
        {'line_id':'l0','text_proposal':'test','bbox_pixels':[0,0,50,20],'kind_proposal':'unreviewed','flags':['readers_disagree']}]}))
    store=ReviewStore(tmp_path)
    assert stage(store,folder)['new_ai_draft_pages']==1
    record=current(store,'p1')
    assert not record['coverage_confirmed'] and not record['lines'][0]['confirmed']
    assert record['split']==''
    from scripts.line_review import details
    assert not details(store,'p1')['stale_identity']
    assert stage(store,folder)['existing_reviews_preserved']==1
    assert current(store,'p1')==record
