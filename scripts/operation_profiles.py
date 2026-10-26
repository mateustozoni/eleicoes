"""Etapas observadas de encerramento: tentativa, confirmação, geração e impressão de BU."""
import collections
import json
import pathlib
from datetime import datetime
import asn1tools
import pyarrow as pa
import pyarrow.parquet as pq
from analyze import logs,section_vota,offset
from timing_profiles import seconds

ROOT=pathlib.Path(__file__).resolve().parents[1]
SCHEMA=None
TEXT_FIELDS=['id','uf','name','source','bu_kind','selected_device','start_event','error']
NUMBER_FIELDS=['turn','total','last_vote_local','last_vote_bsb','declared_close_local','declared_close_bsb','bu_emission_local',
    'bu_emission_bsb','procedure_confirmed_local','procedure_confirmed_bsb','protocol_start_local','protocol_start_bsb',
    'bu_generation_local','bu_generation_bsb','first_print_start_local','first_print_start_bsb','first_print_end_local','first_print_end_bsb',
    'closing_confirmation_events','closing_attempt_events','early_attempt_events','foreign_section_votes','unknown_binding_votes','clock_regressions',
    'declared_minus_confirmed_seconds','protocol_span_seconds','generation_after_confirmation_seconds','print_after_confirmation_seconds',
    'first_print_seconds','deadline_tail_seconds','offset_hours']
BOOL_FIELDS=['single_confirmation','section_reconciled','timing_eligible','start_after_last_vote','procedure_matches_bu']
OPS_SCHEMA=pa.schema([pa.field(k,pa.string()) for k in TEXT_FIELDS]+[pa.field(k,pa.int64()) for k in NUMBER_FIELDS]+[pa.field(k,pa.bool_()) for k in BOOL_FIELDS])

def profile(item):
    global SCHEMA
    turn,key,name,bu_bytes,blobs,source=item
    if SCHEMA is None:SCHEMA=asn1tools.compile_files(str(ROOT/'docs/bu.asn1'),'ber')
    bu=SCHEMA.decode('EntidadeBoletimUrna',SCHEMA.decode('EntidadeEnvelopeGenerico',bu_bytes)['conteudo'])
    election=6257 if turn==1 else 6258;day=datetime(2026,10,4 if turn==1 else 25)
    prefix='04/10/2026 ' if turn==1 else '25/10/2026 ';expected=tuple(map(int,key.split('/')[1:]))
    total=sum(v['quantidadeVotos'] for e in bu['resultadosVotacaoPorEleicao'] if e['idEleicao']==election for r in e['resultadosVotacao'] for c in r['totaisVotosCargo'] if c['codigoCargo']==('cargoConstitucional','presidente') for v in c['votosVotaveis'])
    uf=key.split('/')[0];off=offset(uf,name);seen=set();events=[];vote_times=[];foreign=0;unknown=0;clock=0
    for b in blobs:
        for filename,text in logs(b):
            records,_,other,missing=section_vota(text,expected,seen,prefix);foreign+=sum(other.values());unknown+=missing;previous=None;print_kind=None;print_start=None
            for p in records:
                t=seconds(p[0]);msg=p[4]
                if previous is not None and t<previous:clock+=1
                previous=t;kind=None
                if msg=='Voto confirmado para [Presidente]' or 'voto nulo por suspensão [Presidente]' in msg:vote_times.append(t)
                if msg=='Operador selecionou: Encerrar votação':kind='menu_start'
                elif msg=='Operador indagado se todas as pessoas presentes votaram':kind='queue_prompt'
                elif msg=='Todas as pessoas presentes já votaram? SIM':kind='queue_empty_confirmation'
                elif msg=='Procedimento de encerramento confirmado':kind='procedure_confirmed'
                elif msg in ('Inicio do Encerramento','Início do Encerramento'):kind='begin_closing'
                elif 'Gerando relatório [BU]' in msg and '[INÍCIO]' in msg:kind='bu_generation'
                if msg.startswith('Imprimindo relatório ['):
                    print_kind='BU' if 'relatório [BU]' in msg else 'other'
                    print_start=None
                if msg=='Início de impressão' and print_kind=='BU':print_start=t;kind='bu_print_start'
                if msg=='Fim de impressão' and print_kind=='BU' and print_start is not None:
                    kind='bu_print_end';events.append(dict(kind='bu_print_pair',time=t,start=print_start,device=p[2],file=filename));print_start=None
                if kind:events.append(dict(kind=kind,time=t,device=p[2],file=filename))
    def date_seconds(value):return int((datetime.strptime(value,'%Y%m%dT%H%M%S')-day).total_seconds()) if value else None
    close=date_seconds(bu['dadosSecaoSA'][1].get('dataHoraEncerramento'));emission=date_seconds(bu.get('dataHoraEmissao'))
    confirmations=[e for e in events if e['kind']=='procedure_confirmed']
    confirmed=min(confirmations,key=lambda e:abs(e['time']-close)) if confirmations and close is not None else (confirmations[-1] if confirmations else None)
    starts=[e for e in events if confirmed and e['device']==confirmed['device'] and e['file']==confirmed['file'] and e['time']<=confirmed['time'] and e['kind'] in ('menu_start','queue_prompt')]
    start=max(starts,key=lambda e:e['time']) if starts else None
    after=lambda kind:[e for e in events if confirmed and e['device']==confirmed['device'] and e['time']>=confirmed['time'] and e['kind']==kind]
    generation=min(after('bu_generation'),key=lambda e:e['time']) if after('bu_generation') else None
    prints=after('bu_print_pair');first_print=min(prints,key=lambda e:e['start']) if prints else None
    last_vote=max(vote_times) if vote_times else None
    r=dict(id=key,uf=uf,name=name,turn=turn,total=total,source=source,bu_kind=bu['dadosSecaoSA'][0],
        selected_device=confirmed['device'] if confirmed else None,start_event=start['kind'] if start else None,
        last_vote_local=last_vote,declared_close_local=close,bu_emission_local=emission,
        procedure_confirmed_local=confirmed['time'] if confirmed else None,protocol_start_local=start['time'] if start else None,
        bu_generation_local=generation['time'] if generation else None,first_print_start_local=first_print['start'] if first_print else None,
        first_print_end_local=first_print['time'] if first_print else None,
        closing_confirmation_events=len(confirmations),closing_attempt_events=sum(e['kind'] in ('menu_start','queue_prompt') for e in events),
        early_attempt_events=sum(e['kind'] in ('menu_start','queue_prompt') and e['time']+(off or 0)*3600<61200 for e in events),
        foreign_section_votes=foreign,unknown_binding_votes=unknown,clock_regressions=clock,offset_hours=off,
        single_confirmation=len(confirmations)==1,section_reconciled=len(vote_times)==total,
        timing_eligible=bool(len(vote_times)==total and not clock and not unknown and bu['dadosSecaoSA'][0]=='dadosSecao'),error=None)
    for field in ['last_vote','declared_close','bu_emission','procedure_confirmed','protocol_start','bu_generation','first_print_start','first_print_end']:
        value=r.get(field+'_local');r[field+'_bsb']=value+off*3600 if value is not None and off is not None else None
    r['declared_minus_confirmed_seconds']=close-confirmed['time'] if close is not None and confirmed else None
    r['procedure_matches_bu']=bool(r['declared_minus_confirmed_seconds'] is not None and abs(r['declared_minus_confirmed_seconds'])<=1)
    r['start_after_last_vote']=bool(start and last_vote is not None and start['time']>=last_vote)
    r['protocol_span_seconds']=confirmed['time']-start['time'] if confirmed and start and r['start_after_last_vote'] else None
    r['generation_after_confirmation_seconds']=generation['time']-confirmed['time'] if confirmed and generation else None
    r['print_after_confirmation_seconds']=first_print['time']-confirmed['time'] if confirmed and first_print else None
    r['first_print_seconds']=first_print['time']-first_print['start'] if first_print else None
    r['deadline_tail_seconds']=r['declared_close_bsb']-max(61200,r['last_vote_bsb']) if r['declared_close_bsb'] is not None and r['last_vote_bsb'] is not None else None
    return r,len(events)

def process_batch(inputs,folder):
    folder=pathlib.Path(folder);folder.mkdir(parents=True,exist_ok=True);rows=[];errors=[];events=0
    for item in inputs:
        try:r,n=profile(item);rows.append(r);events+=n
        except Exception as e:
            turn,key,name,_,_,source=item;r=dict(turn=turn,id=key,uf=key.split('/')[0],name=name,source=source,error=repr(e));rows.append(r);errors.append(dict(turn=turn,id=key,error=repr(e)))
    pq.write_table(pa.Table.from_pylist(rows,schema=OPS_SCHEMA),folder/'operations.parquet',compression='zstd')
    m=dict(profile_version=1,turn=inputs[0][0],uf=inputs[0][1].split('/')[0],ids=[r['id'] for r in rows],sections=len(rows),events=events,errors=errors)
    (folder/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2));return m

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=2);args=parser.parse_args()
    from profile_jobs import run
    run(ROOT/'data/operations/v1',process_batch,args.workers,'operations-profile-status.json')
