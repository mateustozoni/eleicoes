"""Contexto cadastral oficial dos locais, sem telefones ou identificadores de pessoas."""
import csv
import hashlib
import io
import json
import pathlib
import time
import urllib.request
import zipfile
from datetime import datetime,timezone
import pyarrow as pa
import pyarrow.parquet as pq

ROOT=pathlib.Path(__file__).resolve().parents[1]
FOLDER=ROOT/'data/context'
URL='https://cdn.tse.jus.br/estatistica/sead/odsele/eleitorado_locais_votacao/eleitorado_local_votacao_2026.zip'
FIELDS={'municipality_name':'NM_MUNICIPIO','local_code':'NR_LOCAL_VOTACAO','local_name':'NM_LOCAL_VOTACAO',
    'local_type':'DS_TIPO_LOCAL','address':'DS_ENDERECO','neighborhood':'NM_BAIRRO',
    'accessibility_status':'DS_SITU_SECAO_ACESSIBILIDADE','section_status':'DS_SITU_SECAO','local_status':'DS_SITU_LOCAL_VOTACAO',
    'original_local_code':'NR_LOCAL_VOTACAO_ORIGINAL','original_local_name':'NM_LOCAL_VOTACAO_ORIGINAL',
    'data_generation_date':'DT_GERACAO','data_generation_time':'HH_GERACAO','election_date':'DT_ELEICAO'}
SCHEMA=pa.schema([('turn',pa.int8()),('id',pa.string()),('uf',pa.string()),('municipality',pa.string()),('zone',pa.string()),('section',pa.string())]+
    [(k,pa.string()) for k in FIELDS]+[('latitude',pa.float64()),('longitude',pa.float64())])

def run():
    FOLDER.mkdir(exist_ok=True);archive=FOLDER/'eleitorado_locais_votacao_2026.zip';metadata=FOLDER/'locations-source.json'
    status=dict(state='downloading',source=URL,rows=0,errors=0)
    def publish():
        status['updated_utc']=datetime.now(timezone.utc).isoformat();p=ROOT/'output/location-context-status.json';p.with_suffix('.tmp').write_text(json.dumps(status,ensure_ascii=False));p.with_suffix('.tmp').replace(p)
    publish()
    if not archive.exists():
        sha=hashlib.sha256();partial=archive.with_suffix('.partial')
        with urllib.request.urlopen(URL,timeout=90) as r:
            headers=dict(r.headers)
            with partial.open('wb') as f:
                while True:
                    b=r.read(1024*1024)
                    if not b:break
                    f.write(b);sha.update(b)
        partial.replace(archive);metadata.write_text(json.dumps(dict(url=URL,sha256=sha.hexdigest(),headers=headers),indent=2))
    status['state']='extracting';publish();target=FOLDER/'locations.parquet';temporary=target.with_suffix('.tmp');buffer=[];counts={};last=time.monotonic()
    def numeric(value):
        try:return float(value.replace(',','.'))
        except (ValueError,AttributeError):return None
    with zipfile.ZipFile(archive) as z,pq.ParquetWriter(temporary,SCHEMA,compression='zstd') as writer:
        name=next(n for n in z.namelist() if n.upper().endswith('_BRASIL.CSV'))
        with z.open(name) as raw:
            for row in csv.DictReader(io.TextIOWrapper(raw,encoding='latin1',newline=''),delimiter=';'):
                try:
                    uf=row['SG_UF'].lower();m=str(int(row['CD_MUNICIPIO'])).zfill(5);zone=str(int(row['NR_ZONA'])).zfill(4);section=str(int(row['NR_SECAO'])).zfill(4);turn=int(row['NR_TURNO'])
                    r=dict(turn=turn,id=f'{uf}/{m}/{zone}/{section}',uf=uf,municipality=m,zone=zone,section=section)
                    for key,column in FIELDS.items():
                        v=row.get(column);r[key]=None if v in ('#NULO#','#NE#','',None) else v
                    lat,lon=numeric(row.get('NR_LATITUDE')),numeric(row.get('NR_LONGITUDE'))
                    if lat is None or lon is None or not (-90<=lat<=90 and -180<=lon<=180) or (lat==0 and lon==0):lat=lon=None
                    r.update(latitude=lat,longitude=lon);buffer.append(r);status['rows']+=1;counts[str(turn)]=counts.get(str(turn),0)+1
                except (ValueError,KeyError):status['errors']+=1
                if len(buffer)>=20000:writer.write_table(pa.Table.from_pylist(buffer,schema=SCHEMA));buffer=[]
                if time.monotonic()-last>=5:status['by_turn']=counts;publish();last=time.monotonic()
        if buffer:writer.write_table(pa.Table.from_pylist(buffer,schema=SCHEMA))
    temporary.replace(target);status.update(state='finished',by_turn=counts,output=str(target));publish()

if __name__=='__main__':run()
