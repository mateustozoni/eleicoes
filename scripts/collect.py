"""Coleta retomável: somente endpoints oficiais; payloads preservados em SQLite por UF."""
import asyncio
import collections
import hashlib
import json
import pathlib
import sqlite3
import time
from datetime import datetime, timezone,timedelta
import aiohttp

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = 'https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3221'
UFS = 'ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to zz'.split()

def select_hash(aux):
    totalized=[h for h in aux.get('hashes',[]) if h.get('st')=='Totalizado']
    if len(totalized)==1: return totalized[0]
    received=[h for h in aux.get('hashes',[]) if h.get('st')=='Recebido']
    if not totalized and len(received)==1: return received[0]
    raise ValueError('Ambiguous or unavailable accepted hash: '+str([(h.get('st'),h.get('hash')) for h in aux.get('hashes',[])]))

class Collector:
    def __init__(self):
        self.starts = collections.deque()
        self.db = {}
        self.stats = collections.Counter()
        self.started = time.time()
        self.previous_checkpoint=(self.started,0)
        self.stored_bytes=0
        self.rate=95
        for uf in UFS:
            p = ROOT / 'data' / 'raw' / (uf + '.sqlite')
            c = sqlite3.connect(str(p))
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('CREATE TABLE IF NOT EXISTS files(url TEXT PRIMARY KEY, fetched TEXT, sha256 TEXT, payload BLOB)')
            c.execute('CREATE TABLE IF NOT EXISTS sections(id TEXT PRIMARY KEY, municipality TEXT, zone TEXT, section TEXT, name TEXT, available INTEGER, status TEXT, error TEXT)')
            self.db[uf] = c
            self.stored_bytes+=c.execute('SELECT coalesce(sum(length(payload)),0) FROM files').fetchone()[0]

    async def get(self, uf, url):
        c = self.db[uf]
        row = c.execute('SELECT payload FROM files WHERE url=?', (url,)).fetchone()
        if row:
            self.stats['cached'] += 1
            return row[0]
        for attempt in range(4):
            if self.stop:
                raise RuntimeError(self.stop)
            # Sliding window; below TSE's documented 100 requests/IP/second.
            while True:
                if self.stop:
                    raise RuntimeError(self.stop)
                now = time.monotonic()
                while self.starts and self.starts[0] < now - 1.01:
                    self.starts.popleft()
                if len(self.starts) < self.rate:
                    self.starts.append(now)
                    break
                await asyncio.sleep(.025)
            try:
                async with self.session.get(url) as r:
                    self.stats['requests'] += 1
                    if r.status in (403, 429):
                        raise RuntimeError('BLOCKED: HTTP ' + str(r.status))
                    if r.status == 404:
                        raise FileNotFoundError(url)
                    r.raise_for_status()
                    b = await r.read()
                self.stats['bytes'] += len(b)
                c.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?)',
                          (url, datetime.now(timezone.utc).isoformat(), hashlib.sha256(b).hexdigest(), b))
                return b
            except (FileNotFoundError, RuntimeError):
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt == 3:
                    raise
                await asyncio.sleep(2 ** attempt)

    async def config(self, uf):
        d = json.loads(await self.get(uf, f'{BASE}/config/{uf}/{uf}-p003221-cs.json'))
        sections = []
        for a in d['abr']:
            for m in a.get('mu', []):
                for z in m['zon']:
                    for s in z['sec']:
                        key = f"{uf}/{m['cd']}/{z['cd']}/{s['ns']}"
                        available = bool(s.get('da'))
                        self.db[uf].execute('INSERT OR IGNORE INTO sections VALUES(?,?,?,?,?,?,?,?)',
                            (key,m['cd'],z['cd'],s['ns'],m['nm'],available,'pending' if available else 'unavailable',None))
                        if available:
                            status = self.db[uf].execute('SELECT status FROM sections WHERE id=?',(key,)).fetchone()[0]
                            if status != 'done': sections.append((uf,m['cd'],z['cd'],s['ns'],key))
        return sections

    async def section(self, item):
        uf, m, z, s, key = item
        c = self.db[uf]
        base = f'{BASE}/dados/{uf}/{m}/{z}/{s}'
        aux = json.loads(await self.get(uf, f'{base}/p003221-{uf}-m{m}-z{z}-s{s}-aux.json'))
        h = select_hash(aux)
        targets = [a for a in h['arq'] if a['tp'] in ('log','logsa','bu','busa')]
        if not any(a['tp'] in ('bu','busa') for a in targets):
            raise ValueError('No BU in totalized hash')
        for a in targets:
            await self.get(uf, base + '/' + h['hash'] + '/' + a['nm'])
        c.execute('UPDATE sections SET status=?,error=NULL WHERE id=?',('done',key))
        self.stats['done_run'] += 1

    async def worker(self, queue):
        while True:
            item = await queue.get()
            if item is None:
                queue.task_done()
                return
            try:
                await self.section(item)
            except RuntimeError as e:
                if 'BLOCKED' in str(e):
                    self.stop = str(e)
                    queue.task_done()
                    return
                raise
            except Exception as e:
                self.stats['errors'] += 1
                self.db[item[0]].execute('UPDATE sections SET status=?,error=? WHERE id=?',('error',str(e),item[-1]))
            queue.task_done()

    def checkpoint(self):
        budget=ROOT/'data/network-budget.json'
        if budget.exists():
            self.rate=max(1,min(95,int(json.loads(budget.read_text()).get('primary',95))))
        counts = collections.Counter()
        for c in self.db.values():
            c.commit()
            for status,n in c.execute('SELECT status,count(*) FROM sections GROUP BY status'):
                counts[status] += n
        d = dict(self.stats)
        now=time.time();previous,requests=self.previous_checkpoint
        rate=(self.stats['requests']-requests)/max(.001,now-previous)
        self.previous_checkpoint=(now,self.stats['requests'])
        total=counts['done']+counts['pending']+counts['error']
        d.update(total_sections=total,progress_percent=round(100*counts['done']/max(1,total),2),
            saved_gib=round((self.stored_bytes+self.stats['bytes'])/1024**3,2),
            recent_requests_per_second=round(rate,1),updated_brasilia=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M:%S'))
        d.update(sections=dict(counts), elapsed_seconds=round(time.time()-self.started), updated_utc=datetime.now(timezone.utc).isoformat(), stopped=self.stop, concurrent_workers=64, requests_per_second_limit=self.rate)
        p = ROOT/'output'/'collection-status.json'
        p.with_suffix('.tmp').write_text(json.dumps(d,ensure_ascii=False,indent=2))
        p.with_suffix('.tmp').replace(p)
        print(json.dumps(d),flush=True)

    async def run(self):
        self.stop = None
        timeout = aiohttp.ClientTimeout(total=90)
        async with aiohttp.ClientSession(timeout=timeout,connector=aiohttp.TCPConnector(limit=64)) as self.session:
            lists = await asyncio.gather(*(self.config(uf) for uf in UFS))
            # Round robin across states; partial reports must still disclose incomplete coverage.
            queue = asyncio.Queue()
            for i in range(max(map(len,lists))):
                for sections in lists:
                    if i < len(sections): queue.put_nowait(sections[i])
            for _ in range(64): queue.put_nowait(None)
            workers = [asyncio.create_task(self.worker(queue)) for _ in range(64)]
            while not all(w.done() for w in workers):
                self.checkpoint()
                if self.stop:
                    for w in workers: w.cancel()
                    break
                await asyncio.sleep(5)
            await asyncio.gather(*workers,return_exceptions=True)
            self.checkpoint()
        for c in self.db.values(): c.close()

if __name__ == '__main__':
    asyncio.run(Collector().run())
