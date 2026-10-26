"""Extrai estatísticas dos arquivos locais. Nunca associa candidato ao evento de voto."""
import collections
import concurrent.futures
import io
import json
import os
import pathlib
import re
import sqlite3
import time
import unicodedata
import zipfile
from datetime import datetime, timedelta
import asn1tools
from collect import select_hash

ROOT = pathlib.Path(__file__).resolve().parents[1]
UFS = 'ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to zz'.split()
BASE = 'https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3221'
WEST_AM = {'AMATURA','ATALAIA DO NORTE','BENJAMIN CONSTANT','EIRUNEPE','ENVIRA','GUAJARA','IPIXUNA','ITAMARATI','JUTAI','TABATINGA','SAO PAULO DE OLIVENCA'}
DAY = datetime(2026,10,25)
SCHEMA = None

def write_status(done,state='running'):
    from datetime import timezone
    p=ROOT/'output/analysis-status.json'
    d=dict(parser_version=5,processed_sections=len(done),state=state,workers=os.cpu_count() or 4,updated_utc=datetime.now(timezone.utc).isoformat())
    p.with_suffix('.tmp').write_text(json.dumps(d));p.with_suffix('.tmp').replace(p)

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFD',s.upper()) if unicodedata.category(c)!='Mn')

def offset(uf, name):
    if uf == 'zz': return None
    if uf == 'ac' or (uf=='am' and norm(name) in WEST_AM): return 2
    if uf in ('am','mt','ms','ro','rr'): return 1
    if uf=='pe' and norm(name)=='FERNANDO DE NORONHA': return -1
    return 0

def logs(b, depth=0,prefix=''):
    if depth>12: raise ValueError('Nested logs depth > 12')
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        for n in z.namelist():
            if n.endswith('/') : continue
            data=z.read(n)
            if n.lower().endswith(('.jez','.zip')):
                yield from logs(data,depth+1,prefix+n+'/')
            elif n.lower().endswith(('.dat','.log')):
                try: yield prefix+n,data.decode('utf-8')
                except UnicodeDecodeError: yield prefix+n,data.decode('latin1')

def section_vota(text,expected,seen,day_prefix='25/10/2026 '):
    """Não soma log de outra seção que esteja arquivado no mesmo pacote."""
    states={};identities={};result=[];foreign=collections.Counter();unknown=0;raw=0
    header_patterns=[('municipality','Município:'),('zone','Zona Eleitoral:'),('section','Seção Eleitoral:')]
    prefixes=tuple(prefix for _,prefix in header_patterns)
    for line in text.splitlines():
        p=line.split('\t')
        if len(p)<6:continue
        message=p[4]
        if message.startswith(prefixes):
            state=states.setdefault(p[2],{})
            for field,prefix in header_patterns:
                if message.startswith(prefix):
                    value=message[len(prefix):].lstrip()
                    if value and value.isdecimal():state[field]=int(value)
                    break
            identities[p[2]]=tuple(state[k] for k in ('municipality','zone','section')) if len(state)==3 else None
        if p[3]!='VOTA' or not p[0].startswith(day_prefix):continue
        identity=tuple(p)
        if identity in seen:continue
        seen.add(identity)
        vote=(p[4]=='Voto confirmado para [Presidente]' or 'voto nulo por suspensão [Presidente]' in p[4])
        actual=identities.get(p[2]);known=actual is not None
        if vote:raw+=1
        if known and actual!=expected:
            if vote:foreign['/'.join(map(str,actual))]+=1
            continue
        if vote and not known:unknown+=1
        result.append(p)
    return result,raw,foreign,unknown

def process(item, additional_cutoff=None):
    global SCHEMA
    if SCHEMA is None: SCHEMA=asn1tools.compile_files(str(ROOT/'docs'/'bu.asn1'),'ber')
    key,name,bu_bytes,log_bytes,source,hash_status = item
    uf,m,z,s=key.split('/')
    env=SCHEMA.decode('EntidadeEnvelopeGenerico',bu_bytes)
    bu=SCHEMA.decode('EntidadeBoletimUrna',env['conteudo'])
    ident=bu['identificacaoSecao']
    if (int(m),int(z),int(s)) != (ident['municipioZona']['municipio'],ident['municipioZona']['zona'],ident['secao']):
        raise ValueError('BU identity mismatch: '+key)
    votes=collections.Counter()
    total=0
    has_president=False
    aptos=None
    for e in bu['resultadosVotacaoPorEleicao']:
        if e['idEleicao'] != 6258: continue
        aptos=e.get('qtdEleitoresAptos')
        for r in e['resultadosVotacao']:
            for cargo in r['totaisVotosCargo']:
                if cargo['codigoCargo'] != ('cargoConstitucional','presidente'): continue
                has_president=True
                for v in cargo['votosVotaveis']:
                    code=str(v.get('identificacaoVotavel',{}).get('codigo',v['tipoVoto']))
                    votes[code]+=v['quantidadeVotos']
                    total+=v['quantidadeVotos']
    if not has_president: raise ValueError('Presidential contest absent in BU: '+key)
    off=offset(uf,name)
    out=dict(parser_version=5,id=key,uf=uf,municipality=m,zone=z,section=s,name=name,local=str(ident['local']),
             total=total,v13=votes['13'],v22=votes['22'],blank=votes['branco'],null=votes['nulo'],
             aptos_president=aptos,full_turnout=(total==aptos if aptos is not None else None),
             bu_bio=bu.get('detalhamentoComparecimento',{}).get('qtdEleitoresHabilitadosPorBiometria'),
             bu_biography=bu.get('detalhamentoComparecimento',{}).get('qtdEleitoresHabilitadosPorBiografia'),
             bu_no_bio=bu.get('detalhamentoComparecimento',{}).get('qtdEleitoresCompareceramSemBiometria'),
             log_votes=0,pre=0,at17=0,post=0,unknown_time=0,clock_backwards=0,unknown_auth=0,
             pre1735=0,at1735=0,post1735=0,
             first=None,last=None,offset_hours=off,source=source,hash_status=hash_status,bins=[],log_files=0)
    out.update(raw_log_votes=0,foreign_section_events=0,binding_unknown_votes=0,foreign_sections=[])
    bins=collections.Counter(); cuts=collections.Counter(); cuts35=collections.Counter(); extra=collections.Counter(); extra_auth=collections.Counter(); seen=set(); records=[];foreign=collections.Counter()
    for blob in log_bytes:
        for logname,txt in logs(blob):
            out['log_files']+=1
            lines,raw,other,unknown=section_vota(txt,(int(m),int(z),int(s)),seen)
            out['raw_log_votes']+=raw;foreign.update(other);out['binding_unknown_votes']+=unknown
            if lines: records.append(lines)
    # Each device's recorded order is preserved. Files ordered by first dated record.
    # Auth state never crosses an archive/device boundary.
    for lines in sorted(records,key=lambda ls:ls[0][0]):
        auth='unknown'; presidential=False; auth_time=None; prev=None
        for p in lines:
            dt=datetime.strptime(p[0],'%d/%m/%Y %H:%M:%S')
            if prev is not None and dt<prev: out['clock_backwards']+=1
            prev=dt
            sec=int((dt-DAY).total_seconds())+(off or 0)*3600
            msg=p[4]
            if msg in ('Aguardando digitação do identificador do eleitor','Identificador do eleitor digitado pelo mesário'):
                auth='unknown'; presidential=False; auth_time=None
            if msg=='Tipo de habilitação do eleitor [biométrica]': auth='elector_biometric'
            elif 'não possui biometria' in msg or 'Ano de nascimento digitado é igual ao do cadastro' in msg:
                auth='no_elector_biometric'
            elif 'Solicitação de dado pessoal do eleitor para habilitação manual' in msg:
                auth='manual_pending'
            elif re.search(r'Mesário .* habilitou o eleitor',msg): auth='pollworker_biometric'
            elif 'Digital coletada bate com uma digital gravada após o registro inicial de mesário' in msg:
                auth='pollworker_unassigned_fingerprint'
            elif msg=='Capturada a digital do mesário':
                auth='pollworker_captured_fingerprint'
            elif 'Tipo de habilitação do eleitor [biográfica]' in msg: auth='biographic'
            if msg=='Eleitor foi habilitado':
                auth_time=sec
                if off is not None: bins[(sec//300*300,'enabled_'+auth)]+=1
            # Count a presidential choice, including a null attributed on suspension.
            if msg=='Voto confirmado para [Presidente]' or ('voto nulo por suspensão [Presidente]' in msg):
                presidential=True
                out['log_votes']+=1
                if auth=='unknown': out['unknown_auth']+=1
                if off is None: out['unknown_time']+=1
                else:
                    bins[(sec//300*300,'vote')]+=1
                    bins[(sec//300*300,'vote_'+auth)]+=1
                    if sec<17*3600: out['pre']+=1; period='pre'
                    elif sec==17*3600: out['at17']+=1; period='at17'
                    else: out['post']+=1; period='post'
                    cuts[(period,auth)]+=1
                    if sec<63300: out['pre1735']+=1; period35='pre'
                    elif sec==63300: out['at1735']+=1; period35='at17'
                    else: out['post1735']+=1; period35='post'
                    cuts35[(period35,auth)]+=1
                    if additional_cutoff is not None:
                        ep='pre' if sec<additional_cutoff else ('at17' if sec==additional_cutoff else 'post')
                        extra[ep]+=1;extra_auth[(ep,auth)]+=1
                    out['first']=sec if out['first'] is None else min(sec,out['first'])
                    out['last']=sec if out['last'] is None else max(sec,out['last'])
            if msg=='O voto do eleitor foi computado':
                auth='unknown'; auth_time=None; presidential=False
    out['match']=out['log_votes']==total
    out['time_eligible']=bool(out['match'] and off is not None and out['clock_backwards']==0 and out['binding_unknown_votes']==0)
    out['foreign_section_events']=sum(foreign.values())
    out['foreign_sections']=[dict(section=k,votes=v) for k,v in foreign.items()]
    out['bins']=[dict(second=k[0],kind=k[1],n=v) for k,v in sorted(bins.items())]
    out['auth_cuts']=[dict(period=k[0],kind=k[1],n=v) for k,v in sorted(cuts.items())]
    out['auth_cuts1735']=[dict(period=k[0],kind=k[1],n=v) for k,v in sorted(cuts35.items())]
    ds=bu['dadosSecaoSA']
    if additional_cutoff is not None:
        out['additional_cutoff']=dict(seconds=additional_cutoff,pre=extra['pre'],at17=extra['at17'],post=extra['post'],auth_cuts=[dict(period=k[0],kind=k[1],n=v) for k,v in sorted(extra_auth.items())])
    out['bu_kind']=ds[0]
    out['opening_local']=ds[1].get('dataHoraAbertura')
    out['closing_local']=ds[1].get('dataHoraEncerramento')
    return out

def items(uf, done):
    c=sqlite3.connect(str(ROOT/'data'/'raw'/(uf+'.sqlite')))
    rows=c.execute("SELECT id,name FROM sections WHERE status='done'").fetchall()
    for key,name in rows:
        if key in done: continue
        _,m,z,s=key.split('/')
        base=f'{BASE}/dados/{uf}/{m}/{z}/{s}'
        auxurl=f'{base}/p003221-{uf}-m{m}-z{z}-s{s}-aux.json'
        aux=json.loads(c.execute('SELECT payload FROM files WHERE url=?',(auxurl,)).fetchone()[0])
        h=select_hash(aux)
        bu=None; lb=[]
        for a in h['arq']:
            url=f"{base}/{h['hash']}/{a['nm']}"
            if a['tp'] not in ('bu','busa','log','logsa'): continue
            row=c.execute('SELECT payload FROM files WHERE url=?',(url,)).fetchone()
            if not row: raise ValueError('Missing cached file '+url)
            if a['tp'] in ('bu','busa'): bu=row[0]
            else: lb.append(row[0])
        yield key,name,bu,lb,auxurl,h['st']
    c.close()

def safe_process(item):
    try: return process(item)
    except Exception as e: return dict(id=item[0],error=repr(e))

def run():
    derived=ROOT/'data'/'derived';derived.mkdir(exist_ok=True)
    done=set()
    for p in derived.glob('part-*.jsonl'):
        for l in p.open():
            r=json.loads(l)
            if r.get('parser_version')==5:done.add(r['id'])
    index=len(list(derived.glob('part-*.jsonl')))
    write_status(done)
    with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        while True:
            batch=[]
            for uf in UFS:
                for item in items(uf,done):
                    batch.append(item)
                    if len(batch)==500:
                        results=list(pool.map(safe_process,batch,chunksize=16))
                        p=derived/f'part-{index:06d}.jsonl';tmp=p.with_suffix('.tmp')
                        tmp.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in results));tmp.replace(p)
                        done.update(r['id'] for r in results); index+=1;batch=[]
                        write_status(done)
                        print('analyzed',len(done),'errors',sum('error' in r for r in results),flush=True)
            if batch:
                results=list(pool.map(safe_process,batch,chunksize=16))
                p=derived/f'part-{index:06d}.jsonl';tmp=p.with_suffix('.tmp')
                tmp.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in results));tmp.replace(p)
                done.update(r['id'] for r in results);index+=1
                write_status(done)
                print('analyzed',len(done),'errors',sum('error' in r for r in results),flush=True)
            status=json.loads((ROOT/'output'/'collection-status.json').read_text())
            if not status['sections'].get('pending',0):
                # Re-scan committed raw rows: collection can finish during this pass.
                remaining=False
                for uf in UFS:
                    with sqlite3.connect(str(ROOT/'data/raw'/(uf+'.sqlite'))) as check:
                        if any(key not in done for (key,) in check.execute("SELECT id FROM sections WHERE status='done'")):
                            remaining=True;break
                if not remaining:break
            write_status(done)
            time.sleep(5)
    write_status(done,'finished')

if __name__=='__main__': run()
