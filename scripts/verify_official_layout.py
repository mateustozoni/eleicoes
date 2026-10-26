"""Compara decodificações do leiaute anterior e do ZIP oficial entregue pelo usuário."""
import concurrent.futures
import json
import os
import pathlib
import sqlite3
import asn1tools

ROOT=pathlib.Path(__file__).resolve().parents[1]
SCHEMAS=None
RENAMES={'reservaSecao':'contingenciaSecao','reservaEncerrandoSecao':'contingenciaEncerrandoSecao',
         'urnaChegouAposInicioVotacao':'urnaEncerradaComEleitoresNaFila'}

def normalized(x):
    if isinstance(x,str):return RENAMES.get(x,x)
    if isinstance(x,dict):return {k:normalized(v) for k,v in x.items()}
    if isinstance(x,list):return [normalized(v) for v in x]
    if isinstance(x,tuple):return tuple(normalized(v) for v in x)
    return x

def check(item):
    global SCHEMAS
    if SCHEMAS is None:
        SCHEMAS=[asn1tools.compile_files(str(ROOT/'docs'/n),'ber') for n in ['mirror-bu.asn1','bu.asn1']]
    url,b=item
    try:
        decoded=[s.decode('EntidadeBoletimUrna',s.decode('EntidadeEnvelopeGenerico',b)['conteudo']) for s in SCHEMAS]
        return None if normalized(decoded[0])==decoded[1] else dict(url=url,error='Different content after documented enum-name normalization')
    except Exception as e:return dict(url=url,error=repr(e))

def run():
    n=0;errors=[]
    with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        for p in sorted((ROOT/'data/raw').glob('??.sqlite')):
            c=sqlite3.connect(str(p))
            cur=c.execute("SELECT url,payload FROM files WHERE url LIKE '%-bu.dat' OR url LIKE '%-busa.dat'")
            while True:
                batch=cur.fetchmany(1000)
                if not batch:break
                errors.extend(r for r in pool.map(check,batch,chunksize=32) if r)
                n+=len(batch)
            c.close()
    report=dict(checked=n,errors=errors,normalizations=RENAMES,
        meaning='Identidade de todos os demais campos, incluindo votos, aptos, comparecimento, horários e identificação; não valida assinatura digital.')
    (ROOT/'output/layout-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(dict(checked=n,errors=len(errors))),flush=True)

if __name__=='__main__':run()
