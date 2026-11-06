"""Summarize completed AI proposals without claiming gold quality or OCR accuracy."""
import argparse,csv,json,os,re
from pathlib import Path


def summarize(folder):
    report=json.loads((folder/'report.json').read_text())
    groups=json.loads((folder/'groups-and-splits.json').read_text())
    unresolved=set(groups['unresolved_pages'])
    rows=[]
    for path in sorted(folder.glob('doc-*.json')):
        d=json.loads(path.read_text())
        if not d['complete']:raise ValueError('Incomplete page')
        critical=0
        for line in d['lines']:
            a=line['text_proposal'].lower();b=(line['second_reader_text'] or '').lower()
            tokens=lambda t:re.findall(r'\d+|\b(?:tidak|bukan|tanpa|minus|not|no)\b',t)
            if tokens(a)!=tokens(b):critical+=1
        rows.append({'page_id':d['page_id'],'lines':len(d['lines']),
            'reader_disagreements':sum('readers_disagree' in l['flags'] for l in d['lines']),
            'number_or_negation_disagreements':critical,
            'box_flags':sum(any(f in l['flags'] for f in ['overlapping_boxes','possible_same_line_fragment','very_small_crop']) for l in d['lines']),
            'unresolved_identity':d['page_id'] in unresolved})
    if len(rows)!=report['pages']:raise ValueError('Page count mismatch')
    rows.sort(key=lambda r:(not r['unresolved_identity'],-r['number_or_negation_disagreements'],-r['box_flags']))
    with (folder/'review-queue.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    summary={**report,'proposed_writer_groups':len(groups['groups']),
        'number_or_negation_disagreement_lines':sum(r['number_or_negation_disagreements'] for r in rows),
        'notes':['Second-reader disagreement is not CER/WER against human gold.',
                 'Do not treat reader agreement as identity confirmation.',
                 'Generation bound: 96 new tokens. Per-line truncation was not captured in this run; check crop coverage and literal completeness.',
                 'All results are unconfirmed AI proposals; unresolved identities remain in quarantine.',
                 'First page also has a separate visual AI correction revision. Other pages have automated cross-reading and issue flags, not exhaustive visual corrections.']}
    (folder/'review-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ai-review',type=Path,required=True)
    a=p.parse_args();os.umask(0o077);print(json.dumps(summarize(a.ai_review)))
