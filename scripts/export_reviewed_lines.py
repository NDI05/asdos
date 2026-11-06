"""Freeze reviewed line labels and split assignments into a private manifest."""
import argparse,os
from pathlib import Path
from scripts.dataset_review import ReviewStore
from scripts.line_review import export

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();os.umask(0o077)
    try:
        result=export(ReviewStore(a.dataset),a.output)
        print(f"Exported {result['samples']} reviewed lines from {result['writers']} writers.")
    except ValueError as exc:p.exit(2,str(exc)+'\n')

if __name__=='__main__':main()
