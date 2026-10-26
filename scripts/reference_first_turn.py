"""Referência operacional de 1º turno: amostra aleatória fixa de até 200 seções por UF.
Lê apenas intervalos HTTP dos ZIPs oficiais; não transfere os pacotes estaduais inteiros.
"""
import collections
import concurrent.futures
import hashlib
import io
import json
import math
import pathlib
import random
import re
import sqlite3
import threading
import time
import urllib.request
import zipfile
from datetime import datetime,timedelta,timezone
import asn1tools
import numpy as np
from analyze import logs,section_vota,offset

ROOT=pathlib.Path(__file__).resolve().parents[1]
STOP=threading.Event();LOCK=threading.Lock();STARTS=collections.deque()
STATUS=dict(state='starting',planned=5400,processed=0,downloaded_bytes=0,completed_ufs=[],errors=[],per_uf={})
SCHEMAS=threading.local()

def status():
    with LOCK:
        d=dict(STATUS,updated_utc=datetime.now(timezone.utc).isoformat())
        p=ROOT/'output/reference-status.json';p.with_suffix('.tmp').write_text(json.dumps(d,ensure_ascii=False,indent=2));p.with_suffix('.tmp').replace(p)

def request(url,headers=None,method='GET'):
    while True:
        if STOP.is_set():raise RuntimeError('Reference collection stopped')
        with LOCK:
            now=time.monotonic()
            while STARTS and STARTS[0]<now-1.01:STARTS.popleft()
            if len(STARTS)<10:STARTS.append(now);break
        time.sleep(.02)
    for attempt in range(3):
        try:
            r=urllib.request.urlopen(urllib.request.Request(url,headers=headers or {},method=method),timeout=60)
            b=r.read()
            with LOCK:STATUS['downloaded_bytes']+=len(b)
            return r.status,dict(r.headers),b
        except Exception as e:
            if getattr(e,'code',None) in (403,429):STOP.set();raise
            if attempt==2 or getattr(e,'code',None) in (404,412):raise
            time.sleep(2**attempt)

class RemoteZipFile(io.RawIOBase):
    block=1024*1024
    def __init__(self,url):
        self.url=url;self.pos=0;self.cache=collections.OrderedDict()
        _,h,_=request(url,method='HEAD');self.size=int(h['Content-Length']);self.etag=h.get('ETag');self.modified=h.get('Last-Modified')
    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.pos
    def seek(self,n,whence=0):
        self.pos=n if whence==0 else (self.pos+n if whence==1 else self.size+n)
        if self.pos<0:raise ValueError('Negative seek')
        return self.pos
    def get(self,start,end):
        headers={'Range':f'bytes={start}-{end}'}
        if self.etag:headers['If-Match']=self.etag
        code,h,b=request(self.url,headers)
        content_range=h.get('Content-Range','')
        if code!=206 or not content_range.startswith(f'bytes {start}-{end}/') or len(b)!=end-start+1:
            raise ValueError('Server did not honor exact HTTP range')
        return b
    def read(self,n=-1):
        n=self.size-self.pos if n<0 else min(n,self.size-self.pos)
        if n<=0:return b''
        if n>self.block:
            b=self.get(self.pos,self.pos+n-1);self.pos+=n;return b
        out=[]
        while n:
            start=self.pos//self.block*self.block
            if start not in self.cache:
                self.cache[start]=self.get(start,min(self.size-1,start+self.block-1))
                if len(self.cache)>8:self.cache.popitem(last=False)
            block=self.cache[start];begin=self.pos-start;take=min(n,len(block)-begin)
            out.append(block[begin:begin+take]);self.pos+=take;n-=take
        return b''.join(out)

def metrics(uf,key,name,bu_bytes,log_bytes):
    if not hasattr(SCHEMAS,'bu'):SCHEMAS.bu=asn1tools.compile_files(str(ROOT/'docs/bu.asn1'),'ber')
    schema=SCHEMAS.bu;bu=schema.decode('EntidadeBoletimUrna',schema.decode('EntidadeEnvelopeGenerico',bu_bytes)['conteudo'])
    expected=tuple(map(int,key.split('/')[1:]));ident=bu['identificacaoSecao']
    actual=(ident['municipioZona']['municipio'],ident['municipioZona']['zona'],ident['secao'])
    if actual!=expected:raise ValueError('Reference BU identity mismatch')
    total=sum(v['quantidadeVotos'] for e in bu['resultadosVotacaoPorEleicao'] if e['idEleicao']==6257 for r in e['resultadosVotacao'] for c in r['totaisVotosCargo'] if c['codigoCargo']==('cargoConstitucional','presidente') for v in c['votosVotaveis'])
    ds=bu['dadosSecaoSA'];seen=set();votes=[];clock=0;unknown=0
    for _,text in logs(log_bytes):
        records,_,_,missing=section_vota(text,expected,seen,'04/10/2026 ');unknown+=missing;previous=None
        for p in records:
            dt=datetime.strptime(p[0],'%d/%m/%Y %H:%M:%S')
            if previous and dt<previous:clock+=1
            previous=dt
            if p[4]=='Voto confirmado para [Presidente]' or 'voto nulo por suspensão [Presidente]' in p[4]:votes.append(dt)
    closing=ds[1].get('dataHoraEncerramento');off=offset(uf,name)
    valid=bool(total==len(votes) and votes and closing and not clock and not unknown and off is not None)
    gap=None;last_bsb=None;close_bsb=None
    if valid:
        last_bsb=max(votes)+timedelta(hours=off);close_bsb=datetime.strptime(closing,'%Y%m%dT%H%M%S')+timedelta(hours=off)
        gap=(close_bsb-max(datetime(2026,10,4,17),last_bsb)).total_seconds()
        valid=gap>=0
    return dict(id=key,uf=uf,name=name,total=total,log_votes=len(votes),clock_regressions=clock,unknown_binding=unknown,
        eligible=valid,operational_tail_seconds=gap,last_vote_brasilia=last_bsb.isoformat() if last_bsb else None,
        closing_brasilia=close_bsb.isoformat() if close_bsb else None)

def collect_uf(uf,url):
    p=ROOT/'data/reference-first-turn';p.mkdir(exist_ok=True)
    c=sqlite3.connect(str(p/(uf+'.sqlite')));c.execute('CREATE TABLE IF NOT EXISTS files(etag TEXT,member TEXT,sha256 TEXT,payload BLOB,PRIMARY KEY(etag,member))')
    c.execute('CREATE TABLE IF NOT EXISTS metrics(etag TEXT,id TEXT,payload TEXT,PRIMARY KEY(etag,id))')
    main=sqlite3.connect(str(ROOT/'data/raw'/(uf+'.sqlite')));names=dict(main.execute('SELECT municipality,name FROM sections GROUP BY municipality,name'));main.close()
    remote=RemoteZipFile(url);results=[]
    with zipfile.ZipFile(remote) as z:
        by_base=collections.defaultdict(list)
        for name in z.namelist():by_base[pathlib.PurePosixPath(name).name].append(name)
        pattern=re.compile(r'o03220'+uf+r'(\d{5})(\d{4})(\d{4})-bu\.dat$')
        choices=[]
        for basename,paths in by_base.items():
            m=pattern.fullmatch(basename)
            if not m or len(paths)!=1:continue
            logbase=basename.replace('-bu.dat','-log.jez')
            if len(by_base.get(logbase,[]))==1:choices.append((m.groups(),paths[0],by_base[logbase][0]))
        choices.sort();seed=20261004+int.from_bytes(uf.encode(),'big')
        sample=random.Random(seed).sample(choices,min(200,len(choices)))
        if not sample:raise ValueError('No unambiguous BU/log pairs in official archive')
        for ids,buname,logname in sample:
            if STOP.is_set():break
            key=uf+'/'+'/'.join(ids)
            prior=c.execute('SELECT payload FROM metrics WHERE etag=? AND id=?',(remote.etag,key)).fetchone()
            if prior:r=json.loads(prior[0])
            else:
                payloads=[]
                for member in [buname,logname]:
                    cached=c.execute('SELECT payload FROM files WHERE etag=? AND member=?',(remote.etag,member)).fetchone()
                    b=cached[0] if cached else z.read(member)
                    if not cached:c.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?)',(remote.etag,member,hashlib.sha256(b).hexdigest(),b))
                    payloads.append(b)
                r=metrics(uf,key,names.get(ids[0],''),*payloads)
                r.update(archive=url,etag=remote.etag,bu_member=buname,log_member=logname,seed=seed)
                c.execute('INSERT OR REPLACE INTO metrics VALUES(?,?,?)',(remote.etag,key,json.dumps(r,ensure_ascii=False)))
            results.append(r)
            with LOCK:STATUS['processed']+=1;STATUS['per_uf'][uf]=dict(processed=len(results),planned=len(sample))
            c.commit();status()
    c.close()
    valid=[r['operational_tail_seconds'] for r in results if r['eligible']]
    summary=dict(uf=uf,sampled=len(results),available_pairs=len(choices),eligible=len(valid),seed=seed,archive=url,etag=remote.etag)
    if valid:
        a=np.array(valid);rng=np.random.default_rng(seed)
        bootstrap=np.quantile(rng.choice(a,size=(1000,len(a)),replace=True),.95,axis=1,method='higher')
        summary.update(mean_seconds=float(a.mean()),median_seconds=float(np.median(a)),p95_seconds=float(np.quantile(a,.95,method='higher')),
            p95_interval=[float(np.quantile(bootstrap,.025)),float(np.quantile(bootstrap,.975))],min_seconds=float(a.min()),max_seconds=float(a.max()),
            sufficient=(len(valid)>=100 and len(valid)>=.8*len(results)))
        summary['indicative_closing_cutoff_seconds']=61200+math.ceil(summary['p95_seconds']/60)*60 if summary['sufficient'] else None
    (p/(uf+'-metrics.json')).write_text(json.dumps(dict(summary=summary,sections=results),ensure_ascii=False,indent=2))
    return summary

def budget(primary,reference):
    p=ROOT/'data/network-budget.json';p.with_suffix('.tmp').write_text(json.dumps(dict(primary=primary,reference=reference)));p.with_suffix('.tmp').replace(p)

def run():
    catalog=json.loads((ROOT/'data/raw/ckan.json').read_text())
    package=next(p for p in catalog['result']['results'] if p['name']=='resultados-2026-arquivos-transmitidos-para-totalizacao')
    urls={re.search(r'_1t_([A-Z]{2})\.zip$',r['url']).group(1).lower():r['url'] for r in package['resources'] if re.search(r'_1t_([A-Z]{2})\.zip$',r['url'])}
    urls.pop('zz',None);summaries=[];budget(85,10);status()
    try:
        # Wait for the primary collector to acknowledge the shared budget.
        for _ in range(25):
            d=json.loads((ROOT/'output/collection-status.json').read_text())
            if d.get('requests_per_second_limit',95)<=85:break
            time.sleep(1)
        else:raise RuntimeError('Primary collector did not acknowledge shared request budget')
        STATUS['state']='running';status()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures={pool.submit(collect_uf,uf,url):uf for uf,url in sorted(urls.items())}
            for future in concurrent.futures.as_completed(futures):
                uf=futures[future]
                try:summaries.append(future.result());STATUS['completed_ufs'].append(uf)
                except Exception as e:STATUS['errors'].append(dict(uf=uf,error=repr(e)))
                (ROOT/'output/reference-calibration.json').write_text(json.dumps(dict(election=6257,date='2026-10-04',method='closure - max(17h Brasília,last presidential vote)',states=summaries),ensure_ascii=False,indent=2));status()
        STATUS['state']='finished' if not STATUS['errors'] else 'finished_with_errors';status()
    finally:budget(95,0)

if __name__=='__main__':run()
