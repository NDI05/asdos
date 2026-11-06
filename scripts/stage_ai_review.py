"""Expose completed AI proposals in the line editor, without human confirmations."""
import argparse,csv,json,os
from pathlib import Path
from scripts.dataset_review import ReviewStore
from scripts.line_review import current,save


def stage(store,folder):
    grouping=json.loads((folder/'groups-and-splits.json').read_text())
    known={}
    for key in store.pages:
        page=store.current(key)
        if page and page['identity_confirmed']:
            known[page['student_id'].strip()]=page['writer_id'].strip()
    for group in grouping['groups']:
        if group['nim_candidate'] in known:
            group['writer_id_proposal']=known[group['nim_candidate']]
            group['anchor']='matches_existing_confirmed_identity; other pages still unconfirmed'
    (folder/'anchored-group-proposals.json').write_text(json.dumps(grouping,ensure_ascii=False,indent=2)+'\n')
    assigned={p:g for g in grouping['groups'] for p in g['pages']}
    staged=skipped=0;dispositions=[]
    for key in store.pages:
        data=json.loads((folder/(key+'.json')).read_text())
        if not data.get('complete') or data['image_sha256']!=store.pages[key]['image_sha256']:
            raise ValueError('AI review incomplete or source changed')
        proposal=assigned.get(key)
        dispositions.append({'page_id':key,'writer_id_proposal':proposal['writer_id_proposal'] if proposal else '',
            'split_proposal':proposal['split_proposal'] if proposal else 'quarantine',
            'status':'unconfirmed_ai_proposal' if proposal else 'unresolved_identity'})
        if current(store,key):
            skipped+=1;continue  # Never replace an existing human or AI revision.
        page=store.current(key)
        lines=[{'line_id':l['line_id'],'text':l['text_proposal'],'bbox_pixels':l['bbox_pixels'],
                'kind':l['kind_proposal'],'confirmed':False,
                'reason':'Usulan AI; perlu konfirmasi. '+', '.join(dict.fromkeys(l['flags']))} for l in data['lines']]
        try:
            save(store,key,{'revision':0,'page_review_revision':page['revision'] if page else 0,
                'split':proposal['split_proposal'] if proposal else '', 'coverage_confirmed':False,'lines':lines})
            staged+=1
        except (RuntimeError, FileExistsError):
            skipped+=1  # A concurrent reviewer wins; never overwrite their revision.
    with (folder/'page-dispositions.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=dispositions[0]);w.writeheader();w.writerows(dispositions)
    report={'new_ai_draft_pages':staged,'existing_reviews_preserved':skipped,'human_confirmations_created':0,
            'pages_in_identity_quarantine':sum(d['split_proposal']=='quarantine' for d in dispositions),
            'split_status':'proposals_only_not_frozen'}
    (folder/'staging-report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--ai-review',type=Path,required=True)
    a=p.parse_args();os.umask(0o077);print(json.dumps(stage(ReviewStore(a.dataset),a.ai_review)))
