"""Baixa os ZIPs estaduais oficiais do 1º turno, com retomada e identidade de arquivo."""
import collections
import concurrent.futures
import hashlib
import json
import pathlib
import re
import threading
import time
import urllib.request
import zipfile
from datetime import datetime,timezone

ROOT=pathlib.Path(__file__).resolve().parents[1]
FOLDER=ROOT/'data/first-turn-archives'
LOCK=threading.Lock();STARTS=collections.deque();FILES={}

def request(url,headers=None,method='GET'):
    while True:
        with LOCK:
            now=time.monotonic()
            while STARTS and STARTS[0]<now-1.01:STARTS.popleft()
            if len(STARTS)<2:STARTS.append(now);break
        time.sleep(.05)
    return urllib.request.urlopen(urllib.request.Request(url,headers=headers or {},method=method),timeout=90)

def publish(state):
    with LOCK:
        rows={k:dict(v) for k,v in FILES.items()}
    total=sum(r.get('total_bytes',0) for r in rows.values());downloaded=sum(r.get('downloaded_bytes',0) for r in rows.values())
    d=dict(state=state,planned=len(rows),completed=sum(r['state']=='complete' for r in rows.values()),
        errors=sum(r['state']=='error' for r in rows.values()),downloaded_gib=round(downloaded/1024**3,2),
        known_total_gib=round(total/1024**3,2),files=rows,updated_utc=datetime.now(timezone.utc).isoformat())
    p=ROOT/'output/first-turn-download-status.json';p.with_suffix('.tmp').write_text(json.dumps(d,ensure_ascii=False,indent=2));p.with_suffix('.tmp').replace(p)

def download(uf,url):
    target=FOLDER/(uf+'.zip');partial=FOLDER/(uf+'.partial');metadata=FOLDER/(uf+'.json')
    for attempt in range(4):
        try:
            with request(url,method='HEAD') as response:
                size=int(response.headers['Content-Length']);etag=response.headers.get('ETag');modified=response.headers.get('Last-Modified')
            old=json.loads(metadata.read_text()) if metadata.exists() else {}
            if old and old.get('etag')!=etag:
                suffix=hashlib.sha256(str(old.get('etag')).encode()).hexdigest()[:12]
                for p in [target,partial]:
                    if p.exists():p.rename(p.with_name(p.name+'.'+suffix+'.previous'))
            meta=dict(uf=uf,url=url,size=size,etag=etag,last_modified=modified)
            if old.get('etag')==etag:
                for key in ['sha256','downloaded_utc']:
                    if old.get(key):meta[key]=old[key]
            metadata.write_text(json.dumps(meta,indent=2))
            with LOCK:FILES[uf].update(total_bytes=size,etag=etag,last_modified=modified,state='downloading')
            if target.exists() and target.stat().st_size==size and zipfile.is_zipfile(target):
                if not meta.get('sha256'):
                    digest=hashlib.sha256()
                    with target.open('rb') as f:
                        for block in iter(lambda:f.read(8*1024*1024),b''):digest.update(block)
                    meta['sha256']=digest.hexdigest();metadata.write_text(json.dumps(meta,indent=2))
                with LOCK:FILES[uf].update(state='complete',downloaded_bytes=size,sha256=meta['sha256'])
                return
            offset=partial.stat().st_size if partial.exists() else 0
            if offset>size:raise ValueError('Partial archive is larger than current source')
            if offset<size:
                headers={'If-Match':etag} if etag else {}
                if offset:headers['Range']=f'bytes={offset}-'
                with request(url,headers) as response:
                    if offset and response.status!=206:raise ValueError('Server did not honor resume range')
                    with partial.open('ab' if offset else 'wb') as f:
                        while True:
                            chunk=response.read(1024*1024)
                            if not chunk:break
                            f.write(chunk);offset+=len(chunk)
                            with LOCK:FILES[uf]['downloaded_bytes']=offset
            if partial.stat().st_size!=size or not zipfile.is_zipfile(partial):raise ValueError('Archive is incomplete or its central directory is invalid')
            sha=hashlib.sha256()
            with partial.open('rb') as f:
                for block in iter(lambda:f.read(8*1024*1024),b''):sha.update(block)
            partial.replace(target)
            m=json.loads(metadata.read_text());m.update(sha256=sha.hexdigest(),downloaded_utc=datetime.now(timezone.utc).isoformat());metadata.write_text(json.dumps(m,indent=2))
            with LOCK:FILES[uf].update(state='complete',downloaded_bytes=size,sha256=sha.hexdigest())
            return
        except Exception as e:
            with LOCK:FILES[uf].update(error=repr(e),attempt=attempt+1)
            if attempt==3:
                with LOCK:FILES[uf]['state']='error'
                return
            time.sleep(2**attempt)

def run():
    FOLDER.mkdir(exist_ok=True)
    catalog=json.loads((ROOT/'data/raw/ckan.json').read_text())
    p=next(p for p in catalog['result']['results'] if p['name']=='resultados-2026-arquivos-transmitidos-para-totalizacao')
    urls={re.search(r'_1t_([A-Z]{2})\.zip$',r['url']).group(1).lower():r['url'] for r in p['resources'] if re.search(r'_1t_([A-Z]{2})\.zip$',r['url'])}
    for uf,url in urls.items():FILES[uf]=dict(state='pending',url=url,downloaded_bytes=0)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(download,uf,url) for uf,url in sorted(urls.items())]
        while not all(f.done() for f in futures):publish('running');time.sleep(5)
        for f in futures:f.result()
    publish('finished')

if __name__=='__main__':run()
