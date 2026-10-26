"""Processa tempos dos dois turnos em Parquet, publicando lotes atômicos e retomáveis."""
import concurrent.futures
import json
import os
import pathlib
import re
import sqlite3
import time
import uuid
import zipfile
from datetime import datetime,timezone
from analyze import UFS,items
from timing_profiles import process_batch,PROFILE_VERSION

ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE=ROOT/'data/timing'/('v'+str(PROFILE_VERSION))
BATCH=64
FRAMES={}

def source_second(reserved):
    for uf in UFS:
        c=sqlite3.connect(str(ROOT/'data/raw'/(uf+'.sqlite')))
        rows=c.execute("SELECT id FROM sections WHERE status='done'").fetchall()
        n=sum(key not in reserved for key, in rows)
        pending=c.execute("SELECT count(*) FROM sections WHERE status='pending'").fetchone()[0];c.close()
        if not n or (n<BATCH and pending):continue
        for key,name,bu,blobs,source,status in items(uf,reserved):
            yield (2,key,name,bu,blobs,source)

def frame(uf,z):
    if uf in FRAMES:return FRAMES[uf]
    pattern=re.compile(r'o03220'+uf+r'(\d{5})(\d{4})(\d{4})-(bu|busa)\.dat$')
    entries={}
    for n in z.namelist():
        basename=pathlib.PurePosixPath(n).name
        m=pattern.fullmatch(basename)
        if m:
            key=uf+'/'+'/'.join(m.groups()[:3]);entries.setdefault(key,dict(bu=[],log=[]))['bu'].append(n)
    by_base={}
    for n in z.namelist():by_base.setdefault(pathlib.PurePosixPath(n).name,[]).append(n)
    for key,r in entries.items():
        _,m,zone,s=key.split('/');prefix='o03220'+uf+m+zone+s
        r['log']=[n for suffix in ['-log.jez','-logsa.jez'] for n in by_base.get(prefix+suffix,[])]
    FRAMES[uf]=entries
    p=BASE/'frames';p.mkdir(exist_ok=True)
    (p/(uf+'.json')).write_text(json.dumps(entries,ensure_ascii=False))
    return entries

def source_first(reserved):
    status_path=ROOT/'output/first-turn-download-status.json'
    if not status_path.exists():return
    status=json.loads(status_path.read_text())
    for uf,row in sorted(status['files'].items()):
        if row['state']!='complete':continue
        if uf in FRAMES and all(key in reserved for key in FRAMES[uf]):continue
        path=ROOT/'data/first-turn-archives'/(uf+'.zip')
        c=sqlite3.connect(str(ROOT/'data/raw'/(uf+'.sqlite')))
        names=dict(c.execute('SELECT municipality,name FROM sections GROUP BY municipality,name'));c.close()
        with zipfile.ZipFile(path) as z:
            entries=frame(uf,z)
            for key,r in sorted(entries.items()):
                if key in reserved:continue
                name=names.get(key.split('/')[1],key.split('/')[1])
                source=row['url']+'#'+'|'.join(r['bu'])
                if len(r['bu'])!=1:
                    yield (1,key,name,b'',[],source+' [ambiguous BU selection]');continue
                yield (1,key,name,z.read(r['bu'][0]),[z.read(n) for n in r['log']],source)

def run(base=None,worker=None,worker_count=None,status_name='timing-profile-status.json'):
    global BASE
    if base is not None:BASE=pathlib.Path(base)
    task_worker=worker or process_batch
    BASE.mkdir(parents=True,exist_ok=True);(BASE/'staging').mkdir(exist_ok=True)
    done={1:set(),2:set()};reserved={1:set(),2:set()};events={1:0,2:0};errors=[]
    for turn in [1,2]:
        for p in (BASE/(str(turn)+'t')).glob('*/*/manifest.json'):
            m=json.loads(p.read_text());done[turn].update(m['ids']);events[turn]+=m['events'];errors.extend(m['errors'])
        reserved[turn].update(done[turn])
    streams={1:None,2:None};carry={1:None,2:None};last_empty={1:0,2:0};pending={};next_turn=2;last_status=0
    workers=worker_count or max(1,(os.cpu_count() or 4)-2)
    state='running'
    stop_file=BASE/'stop.request'
    def publish():
        nonlocal last_status
        d=dict(state=state,profile_version=PROFILE_VERSION,workers=workers,
            turns={str(t):dict(processed_sections=len(done[t]),session_records=events[t]) for t in [1,2]},
            first_turn_frames_indexed=sum(len(v) for v in FRAMES.values()),first_turn_ufs_indexed=len(FRAMES),
            running_batches=len(pending),errors=errors,updated_utc=datetime.now(timezone.utc).isoformat())
        p=ROOT/'output'/status_name;p.with_suffix('.tmp').write_text(json.dumps(d,ensure_ascii=False,indent=2));p.with_suffix('.tmp').replace(p)
        last_status=time.monotonic()
    def batch(turn):
        if streams[turn] is None:
            if time.monotonic()-last_empty[turn]<5:return []
            streams[turn]=iter(source_first(reserved[turn]) if turn==1 else source_second(reserved[turn]))
        result=[];uf=None
        while len(result)<BATCH:
            if carry[turn] is not None:item=carry[turn];carry[turn]=None
            else:
                try:item=next(streams[turn])
                except StopIteration:streams[turn]=None;last_empty[turn]=time.monotonic();break
            key=item[1]
            if key in reserved[turn]:continue
            if uf is not None and key.split('/')[0]!=uf:carry[turn]=item;break
            uf=key.split('/')[0];result.append(item);reserved[turn].add(key)
        return result
    publish()
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        while True:
            stopping=stop_file.exists()
            while len(pending)<workers+2 and not stopping:
                selected=[]
                for _ in range(2):
                    turn=next_turn;next_turn=1 if next_turn==2 else 2
                    selected=batch(turn)
                    if selected:break
                if not selected:break
                tag=uuid.uuid4().hex;staging=BASE/'staging'/tag
                future=pool.submit(task_worker,selected,str(staging))
                pending[future]=(turn,selected[0][1].split('/')[0],tag,staging)
            if pending:
                completed,_=concurrent.futures.wait(pending,timeout=1,return_when=concurrent.futures.FIRST_COMPLETED)
                for f in completed:
                    turn,uf,tag,staging=pending.pop(f)
                    try:m=f.result()
                    except BaseException as e:
                        state='failed';errors.append(dict(turn=turn,uf=uf,error=repr(e)));publish();raise
                    destination=BASE/(str(turn)+'t')/uf/tag;destination.parent.mkdir(parents=True,exist_ok=True);staging.replace(destination)
                    done[turn].update(m['ids']);events[turn]+=m['events'];errors.extend(m['errors'])
            else:time.sleep(1)
            if time.monotonic()-last_status>=5:publish()
            primary=json.loads((ROOT/'output/collection-status.json').read_text())
            first=json.loads((ROOT/'output/first-turn-download-status.json').read_text())
            first_complete=(first['state']=='finished' and first['errors']==0 and len(FRAMES)==len(first['files']) and all(key in done[1] for values in FRAMES.values() for key in values))
            second_complete=(not primary['sections'].get('pending',0) and not primary['sections'].get('error',0) and len(done[2])>=primary['sections'].get('done',0))
            if not pending and stopping:state='stopped_for_update';break
            if not pending and first_complete and second_complete:state='finished';break
    publish()

if __name__=='__main__':run()
