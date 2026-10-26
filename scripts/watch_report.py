"""Atualiza o artefato durante esta coleta local; não agenda tarefas externas."""
import json
import pathlib
import subprocess
import sys
import time
ROOT=pathlib.Path(__file__).resolve().parents[1]
previous=None
def status(name):
    p=ROOT/'output'/(name+'.json')
    return json.loads(p.read_text()) if p.exists() else {}
while True:
    try:
        s=json.loads((ROOT/'output/collection-status.json').read_text())
        done=s['sections'].get('done',0)
        finished=not s['sections'].get('pending',0)
        timing=status('timing-profile-status');operations=status('operations-profile-status');final=status('finalization-status')
        key=(done,status('analysis-status').get('processed_sections'),
             tuple(timing.get('turns',{}).get(str(t),{}).get('processed_sections',0) for t in [1,2]),
             tuple(operations.get('turns',{}).get(str(t),{}).get('processed_sections',0) for t in [1,2]),
             status('metadata-status').get('processed'),final.get('state'),final.get('verified'))
        if key!=previous:
            r=subprocess.run([sys.executable,str(ROOT/'scripts/report.py')],cwd=str(ROOT))
            if r.returncode==0:previous=key
        if finished:
            summary=json.loads((ROOT/'output/summary.json').read_text())
            errors=json.loads((ROOT/'output/analysis-errors.json').read_text())
            if summary['sums']['sections']+len(errors)>=done and timing.get('state')=='finished' and operations.get('state')=='finished' and final.get('verified'):break
    except (FileNotFoundError,json.JSONDecodeError):pass
    time.sleep(5)
