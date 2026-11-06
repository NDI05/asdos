import csv
import hashlib
import json
from PIL import Image
import pytest
from scripts.dataset_review import ReviewStore
from scripts import line_review
from scripts.trocr_runtime import metrics,load_manifest


def store_fixture(tmp_path):
    (tmp_path/'pages').mkdir();rows=[]
    for i in range(2):
        path=tmp_path/'pages'/f'{i}.png'
        Image.new('RGB',(100,80),('white','gray')[i]).save(path)
        rows.append({'page_id':f'p{i}','image_path':f'pages/{i}.png','image_width_px':'100','image_height_px':'80','image_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source_sha256':str(i)*64})
    with (tmp_path/'pages.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
    store=ReviewStore(tmp_path)
    for i in range(2):
        store.save(f'p{i}',{'revision':0,'writer_id':f'w{i}','submission_id':f's{i}','student_name':'','student_id':f'00{i}',
            'identity_confirmed':True,'transcript':'','transcript_reviewed':False,'notes':''})
    return store


def review(split='train'):
    return {'revision':0,'page_review_revision':1,'split':split,'coverage_confirmed':True,'lines':[
        {'line_id':'header','text':'private name','bbox_pixels':[0,0,80,15],'kind':'identity','confirmed':True,'reason':''},
        {'line_id':'answer','text':'RAM sementara','bbox_pixels':[0,20,90,40],'kind':'answer','confirmed':True,'reason':''}]}


def test_export_consumed_by_trainer_preserves_leading_zeros_and_excludes_identity(tmp_path):
    store=store_fixture(tmp_path)
    line_review.save(store,'p0',review());line_review.save(store,'p1',review('development'))
    report=line_review.export(store,tmp_path/'export')
    samples=load_manifest(tmp_path/'export/annotations.jsonl')
    assert len(samples)==report['samples']==2
    assert all(s['text']=='RAM sementara' for s in samples)
    assert store.current('p0')['student_id']=='000'
    assert {s['split'] for s in samples}=={'train','development'}


def test_box_conflict_revision_and_identity_overlap(tmp_path):
    store=store_fixture(tmp_path)
    bad=review();bad['lines'][1]['bbox_pixels']=[0,-1,10,20]
    with pytest.raises(ValueError,match='Kotak'):line_review.save(store,'p0',bad)
    line_review.save(store,'p0',review())
    with pytest.raises(RuntimeError):line_review.save(store,'p0',review())
    old=store.current('p0');payload={k:v for k,v in old.items() if k in {'revision','writer_id','submission_id','student_name','student_id','identity_confirmed','transcript','transcript_reviewed','notes'}}
    store.save('p0',payload)
    assert line_review.details(store,'p0')['stale_identity']
    with pytest.raises(ValueError,match='identitas berubah'):line_review.export(store,tmp_path/'export')


def test_export_rejects_answer_intersecting_identity(tmp_path):
    store=store_fixture(tmp_path);r=review();r['lines'][1]['bbox_pixels']=[0,5,90,40]
    line_review.save(store,'p0',r);line_review.save(store,'p1',review('development'))
    with pytest.raises(ValueError,match='bertumpang'):line_review.export(store,tmp_path/'export')
    assert not (tmp_path/'export').exists()


def test_literal_metrics_empty_reference_and_word_errors():
    result=metrics([('abc','adc'),('a b','a'),('','x')])
    assert result['character_edits']==4 and result['reference_characters']==6
    assert result['word_edits']==3 and result['reference_words']==3
    assert result['empty_reference_false_positives']==1
    assert metrics([('','')])['cer_micro'] is None
    assert metrics([('Tidak','tidak')])['cer_micro']==0.2


def test_snapshot_rejects_writer_split_conflict_and_changed_source(tmp_path):
    store=store_fixture(tmp_path)
    line_review.save(store,'p0',review());line_review.save(store,'p1',review('development'))
    # Same page image hash across splits is refused even if writer metadata differs.
    store.pages['p1']['image_sha256']=store.pages['p0']['image_sha256']
    with pytest.raises(ValueError,match='hash'):
        line_review.export(store,tmp_path/'export')
    assert not (tmp_path/'export').exists()


def test_draft_bottom_left_conversion_and_manual_box_persistence(tmp_path):
    store=store_fixture(tmp_path)
    (tmp_path/'vision-drafts').mkdir()
    (tmp_path/'vision-drafts/p0.json').write_text(json.dumps({'image_sha256':store.pages['p0']['image_sha256'],'lines':[
        {'text':'abc','bbox_normalized':[0.1,0.25,0.9,0.5]}]}))
    d=line_review.details(store,'p0')
    assert d['lines'][0]['bbox_pixels']==[10,40,90,60]
    assert not d['lines'][0]['confirmed']
    r=review();r['lines'].append({'line_id':'manual-1','text':'missing line','bbox_pixels':[0,50,80,70],'kind':'answer','confirmed':True,'reason':''})
    line_review.save(store,'p0',r)
    assert line_review.details(store,'p0')['lines'][-1]['text']=='missing line'


def test_line_http_round_trip_and_origin_guard(tmp_path):
    import http.client
    import threading
    from http.server import ThreadingHTTPServer
    from scripts.dataset_review import make_handler
    store=store_fixture(tmp_path)
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(store,'test-token'))
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        c=http.client.HTTPConnection('127.0.0.1',server.server_port)
        c.request('GET','/api/lines/p0');r=c.getresponse();assert r.status==403;r.read()
        c.request('GET','/api/lines/p0',headers={'X-Review-Token':'test-token'})
        r=c.getresponse();assert r.status==200;assert json.loads(r.read())['revision']==0
        headers={'X-Review-Token':'test-token','Content-Type':'application/json','Origin':f'http://127.0.0.1:{server.server_port}'}
        c.request('POST','/api/lines/p0',body=json.dumps(review()),headers=headers)
        r=c.getresponse();assert r.status==200;assert json.loads(r.read())['revision']==1
        c.request('POST','/api/lines/p0',body=json.dumps(review()),headers=headers)
        r=c.getresponse();assert r.status==409;r.read()
        c.close()
    finally:
        server.shutdown();server.server_close();worker.join()
