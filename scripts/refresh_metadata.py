"""Revalida auxiliares provisórios sem modificar os arquivos brutos já capturados."""
import asyncio
import collections
import fcntl
import hashlib
import json
import pathlib
import sqlite3
import time
from datetime import datetime,timezone
import aiohttp
from analytics_store import open_store
from collect import select_hash

ROOT=pathlib.Path(__file__).resolve().parents[1]

def budget(primary,metadata):
    p=ROOT/'data/network-budget.json';p.with_suffix('.tmp').write_text(json.dumps(dict(primary=primary,reference=0,metadata=metadata)));p.with_suffix('.tmp').replace(p)

async def run():
    with (ROOT/'output/.report.lock').open('r') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        con=open_store()
        rows=con.execute("SELECT id,source FROM sections WHERE hash_status='Recebido' AND error IS NULL").fetchall();con.close()
    db=sqlite3.connect(str(ROOT/'data/metadata-refresh.sqlite'))
    db.execute('CREATE TABLE IF NOT EXISTS history(id TEXT,url TEXT,fetched TEXT,sha256 TEXT,payload BLOB,PRIMARY KEY(id,sha256))')
    previous=json.loads((ROOT/'output/metadata-status.json').read_text()) if (ROOT/'output/metadata-status.json').exists() else {}
    confirmed=list(previous.get('confirmed',[]));already={r['id'] for r in confirmed}
    rows=[r for r in rows if r[0] not in already]
    changed=[];errors=[];processed=0;starts=collections.deque();queue=asyncio.Queue()
    collection_finished=not json.loads((ROOT/'output/collection-status.json').read_text())['sections'].get('pending',0)
    rate=80 if collection_finished else 10
    workers=24 if collection_finished else 6
    for row in rows:queue.put_nowait(row)
    for _ in range(workers):queue.put_nowait(None)
    state='starting';stopped=None
    def publish():
        db.commit()
        d=dict(state=state,planned=len(rows),processed=processed,confirmed=confirmed,changed=changed,errors=errors,stopped=stopped,updated_utc=datetime.now(timezone.utc).isoformat())
        p=ROOT/'output/metadata-status.json';p.with_suffix('.tmp').write_text(json.dumps(d,ensure_ascii=False,indent=2));p.with_suffix('.tmp').replace(p)
        compact={k:v for k,v in d.items() if not isinstance(v,list)}
        compact.update(confirmed_count=len(confirmed),changed_count=len(changed),error_count=len(errors))
        cp=ROOT/'output/metadata-progress.json';cp.with_suffix('.tmp').write_text(json.dumps(compact));cp.with_suffix('.tmp').replace(cp)
    budget(0 if collection_finished else 85,rate);publish()
    try:
        for _ in range(25):
            s=json.loads((ROOT/'output/collection-status.json').read_text())
            if collection_finished or s.get('requests_per_second_limit',95)<=85:break
            await asyncio.sleep(1)
        else:raise RuntimeError('Primary collector did not acknowledge shared request budget')
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            async def worker():
                nonlocal processed,stopped
                while not stopped:
                    item=await queue.get()
                    if item is None:queue.task_done();return
                    key,url=item
                    try:
                        while True:
                            now=time.monotonic()
                            while starts and starts[0]<now-1.01:starts.popleft()
                            if len(starts)<rate:starts.append(now);break
                            await asyncio.sleep(.02)
                        if stopped:return
                        async with session.get(url) as response:
                            if response.status in (403,429):stopped='HTTP '+str(response.status);return
                            response.raise_for_status();payload=await response.read()
                        current=json.loads(payload)
                        c=sqlite3.connect(str(ROOT/'data/raw'/(key.split('/')[0]+'.sqlite')))
                        old=json.loads(c.execute('SELECT payload FROM files WHERE url=?',(url,)).fetchone()[0]);c.close()
                        old_hash=select_hash(old);new_hash=select_hash(current)
                        fetched=datetime.now(timezone.utc).isoformat();sha=hashlib.sha256(payload).hexdigest()
                        db.execute('INSERT OR IGNORE INTO history VALUES(?,?,?,?,?)',(key,url,fetched,sha,payload))
                        kinds=('bu','busa','log','logsa')
                        old_files={(a['tp'],a['nm']) for a in old_hash['arq'] if a['tp'] in kinds}
                        new_files={(a['tp'],a['nm']) for a in new_hash['arq'] if a['tp'] in kinds}
                        if old_hash['hash']==new_hash['hash'] and old_files==new_files and new_hash['st']=='Totalizado':
                            confirmed.append(dict(id=key,status='Totalizado',selected_hash=new_hash['hash'],fetched_utc=fetched,sha256=sha,source=url))
                        elif old_hash['hash']!=new_hash['hash'] or old_files!=new_files:
                            changed.append(dict(id=key,old_hash=old_hash['hash'],current_hash=new_hash['hash'],source=url))
                    except Exception as e:errors.append(dict(id=key,error=repr(e)))
                    finally:
                        processed+=1;queue.task_done()
            state='running';tasks=[asyncio.create_task(worker()) for _ in range(workers)]
            while not all(t.done() for t in tasks):
                publish()
                if stopped:
                    for t in tasks:t.cancel()
                    break
                await asyncio.sleep(5)
            await asyncio.gather(*tasks,return_exceptions=True)
        state='finished' if not stopped else 'stopped';publish()
    finally:
        db.commit();db.close();budget(95,0)

if __name__=='__main__':asyncio.run(run())
