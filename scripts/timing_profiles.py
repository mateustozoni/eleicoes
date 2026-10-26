"""Tempos anônimos do fluxo de identificação e votação, sem identidade ou escolha de voto."""
import collections
import json
import os
import pathlib
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import asn1tools
from analyze import logs,section_vota,offset

ROOT=pathlib.Path(__file__).resolve().parents[1]
PROFILE_VERSION=1
SCHEMA=None
METRICS=['identification_seconds','voting_seconds','pres_stage_seconds','session_seconds','confirmation_gap_seconds','activation_gap_seconds','active_confirmation_gap_seconds']
STRINGS=['id','uf','municipality','zone','section','device','archive_entry','source','auth_kind','end_reason','flags']
INTS=['ordinal','identifier_local','enabled_local','presidential_local','computed_local','enabled_bsb','presidential_bsb','computed_bsb',
      'cargo_confirmations','pres_markers','clock_segment']+METRICS
BOOLS=['completed','valid_timing','section_eligible','was_suspended','gap_crosses_restart']
EVENT_SCHEMA=pa.schema([pa.field('turn',pa.int8())]+[pa.field(k,pa.string()) for k in STRINGS]+[pa.field(k,pa.int32()) for k in INTS]+[pa.field(k,pa.bool_()) for k in BOOLS])

def auth_type(current,msg):
    if msg=='Tipo de habilitação do eleitor [biométrica]':return 'elector_biometric'
    if 'não possui biometria' in msg or 'Ano de nascimento digitado é igual ao do cadastro' in msg:return 'no_elector_biometric'
    if 'Solicitação de dado pessoal do eleitor para habilitação manual' in msg:return 'manual_pending'
    if msg.startswith('Mesário ') and ' habilitou o eleitor' in msg:return 'pollworker_biometric'
    if 'Digital coletada bate com uma digital gravada após o registro inicial de mesário' in msg:return 'pollworker_unassigned_fingerprint'
    if msg=='Capturada a digital do mesário':return 'pollworker_captured_fingerprint'
    if 'Tipo de habilitação do eleitor [biográfica]' in msg:return 'biographic'
    return current

def seconds(stamp):
    h,m,s=int(stamp[11:13]),int(stamp[14:16]),int(stamp[17:19])
    if not (0<=h<24 and 0<=m<60 and 0<=s<60):raise ValueError('Invalid log clock: '+stamp)
    return h*3600+m*60+s

def sessions(records,turn,key,name,filename,source):
    uf,m,z,s=key.split('/');off=offset(uf,name);out=[];current=None;auth='unknown';previous=None;last_time=None;segment=0;restart=False
    diagnostics=collections.Counter()
    def fresh(t=None):
        return dict(identifier=t,enabled=None,pres=[],computed=None,last_other=None,cargos=0,method='unknown',suspended=False,segment=segment)
    def finish(reason,completed=False):
        nonlocal current,previous,restart
        if current is None:return
        if current['enabled'] is None and not current['pres']:
            diagnostics['identification_attempts_without_enablement']+=1;current=None;return
        c=current;pres=c['pres'][-1] if c['pres'] else None
        flags=[]
        if c['enabled'] is None:flags.append('missing_enablement')
        if len(c['pres'])!=1:flags.append('presidential_marker_count_'+str(len(c['pres'])))
        if not completed:flags.append('not_completed')
        if c['segment']!=segment or reason=='clock_regression':flags.append('clock_transition')
        def diff(end,start):
            if end is None or start is None:return None
            value=end-start
            if value<0:flags.append('negative_duration');return None
            return value
        id_time=diff(c['enabled'],c['identifier'])
        voting=diff(pres,c['enabled']);stage=diff(pres,c.get('pres_start'));total=diff(c['computed'],c['enabled'])
        gap=None;activation=None
        if previous and previous['segment']==segment:
            gap=diff(pres,previous['pres']);activation=diff(c['enabled'],previous['computed'])
        valid=bool(completed and len(c['pres'])==1 and voting is not None and total is not None and c['segment']==segment and 'negative_duration' not in flags)
        r=dict(turn=turn,id=key,uf=uf,municipality=m,zone=z,section=s,device=c.get('device'),archive_entry=filename,source=source,
            auth_kind=c['method'],end_reason=reason,flags='|'.join(sorted(set(flags))),ordinal=len(out)+1,
            identifier_local=c['identifier'],enabled_local=c['enabled'],presidential_local=pres,computed_local=c['computed'],
            enabled_bsb=c['enabled']+off*3600 if off is not None and c['enabled'] is not None else None,
            presidential_bsb=pres+off*3600 if off is not None and pres is not None else None,
            computed_bsb=c['computed']+off*3600 if off is not None and c['computed'] is not None else None,
            cargo_confirmations=c['cargos'],pres_markers=len(c['pres']),clock_segment=c['segment'],
            identification_seconds=id_time,voting_seconds=voting,pres_stage_seconds=stage,session_seconds=total,
            confirmation_gap_seconds=gap,activation_gap_seconds=activation,active_confirmation_gap_seconds=gap if not restart else None,
            completed=completed,valid_timing=valid,section_eligible=False,was_suspended=c['suspended'],gap_crosses_restart=restart)
        out.append(r)
        if completed and len(c['pres'])==1:
            previous=dict(pres=pres,computed=c['computed'],segment=segment);restart=False
        current=None
    for p in records:
        t=seconds(p[0]);msg=p[4]
        if last_time is not None and t<last_time:
            diagnostics['clock_regressions']+=1;finish('clock_regression');segment+=1;previous=None
        last_time=t
        if msg.startswith('Iniciando aplicação'):
            finish('application_restart');restart=True;auth='unknown';diagnostics['application_starts']+=1
        if msg=='Aguardando digitação do identificador do eleitor':
            finish('return_to_waiting');auth='unknown'
        if msg=='Identificador do eleitor digitado pelo mesário':
            if current and (current['enabled'] is not None or current['pres']):finish('new_identification_before_completion')
            if current is None:current=fresh(t)
            elif current['identifier'] is None:current['identifier']=t
            auth='unknown'
        auth=auth_type(auth,msg)
        if msg.startswith('Habilitação cancelada'):diagnostics['cancelled_enablement_events']+=1
        if msg=='Eleitor foi habilitado':
            diagnostics['enablement_events']+=1
            if current is None:current=fresh()
            current['enabled']=t;current['method']=auth;current['device']=p[2]
        if 'foi suspenso' in msg and current:current['suspended']=True
        confirmation=msg.startswith('Voto confirmado para [') or 'voto nulo por suspensão [' in msg
        if confirmation:
            if current is None:current=fresh()
            current['device']=p[2];current['cargos']+=1
            if '[Presidente]' in msg:
                current['pres'].append(t);current['pres_start']=current['last_other'] if current['last_other'] is not None else current['enabled']
                diagnostics['presidential_confirmations']+=1
            else:current['last_other']=t
        if msg=='O voto do eleitor foi computado':
            diagnostics['computed_messages']+=1
            if current is None:current=fresh()
            current['computed']=t;current['device']=p[2];finish('computed',True)
        if msg=='Eleitor foi suspenso e não confirmou nenhum voto':finish('fully_suspended')
    finish('end_of_log')
    return out,diagnostics

def profile(item):
    global SCHEMA
    turn,key,name,bu_bytes,blobs,source=item
    if SCHEMA is None:SCHEMA=asn1tools.compile_files(str(ROOT/'docs/bu.asn1'),'ber')
    bu=SCHEMA.decode('EntidadeBoletimUrna',SCHEMA.decode('EntidadeEnvelopeGenerico',bu_bytes)['conteudo'])
    ident=bu['identificacaoSecao'];expected=tuple(map(int,key.split('/')[1:]))
    if expected!=(ident['municipioZona']['municipio'],ident['municipioZona']['zona'],ident['secao']):raise ValueError('Timing BU identity mismatch')
    election=6257 if turn==1 else 6258;date_prefix='04/10/2026 ' if turn==1 else '25/10/2026 '
    votes=collections.Counter();aptos=None;president_found=False
    for e in bu['resultadosVotacaoPorEleicao']:
        if e['idEleicao']!=election:continue
        aptos=e['qtdEleitoresAptos']
        for r in e['resultadosVotacao']:
            for cargo in r['totaisVotosCargo']:
                if cargo['codigoCargo']!=('cargoConstitucional','presidente'):continue
                president_found=True
                for v in cargo['votosVotaveis']:votes[str(v.get('identificacaoVotavel',{}).get('codigo',v['tipoVoto']))]+=v['quantidadeVotos']
    if not president_found:raise ValueError('Presidential contest absent in timing BU')
    rows=[];diag=collections.Counter();seen=set();foreign=0;unknown=0
    for blob in blobs:
        for filename,text in logs(blob):
            records,_,other,missing=section_vota(text,expected,seen,date_prefix)
            foreign+=sum(other.values());unknown+=missing
            events,counts=sessions(records,turn,key,name,filename,source);rows.extend(events);diag.update(counts)
    total=sum(votes.values());complete=sum(r['completed'] and r['pres_markers']==1 for r in rows)
    reconciled=diag['presidential_confirmations']==total
    eligible=bool(reconciled and complete==total and not diag['clock_regressions'] and not unknown and bu['dadosSecaoSA'][0]=='dadosSecao')
    for i,r in enumerate(rows):r['ordinal']=i+1;r['section_eligible']=eligible
    uf,m,z,s=key.split('/')
    meta=dict(profile_version=PROFILE_VERSION,turn=turn,id=key,uf=uf,municipality=m,zone=z,section=s,name=name,source=source,
        aptos=aptos,total=total,v13=votes['13'],v22=votes['22'],blank=votes['branco'],null=votes['nulo'],
        other_votes=total-votes['13']-votes['22']-votes['branco']-votes['nulo'],
        bu_kind=bu['dadosSecaoSA'][0],opening_local=bu['dadosSecaoSA'][1].get('dataHoraAbertura'),closing_local=bu['dadosSecaoSA'][1].get('dataHoraEncerramento'),
        presidential_markers=diag['presidential_confirmations'],computed_messages=diag['computed_messages'],completed_presidential_sessions=complete,
        enablement_events=diag['enablement_events'],cancelled_enablement_events=diag['cancelled_enablement_events'],
        identification_attempts_without_enablement=diag['identification_attempts_without_enablement'],clock_regressions=diag['clock_regressions'],
        foreign_section_events=foreign,unknown_binding=unknown,section_reconciled=reconciled,section_eligible=eligible,
        incomplete_sessions=sum(not r['completed'] for r in rows),suspended_sessions=sum(r['was_suspended'] for r in rows),
        valid_sessions=sum(r['valid_timing'] for r in rows),error=None)
    histogram=collections.Counter()
    for metric in METRICS:
        values=[r[metric] for r in rows if r['valid_timing'] and r[metric] is not None]
        meta[metric+'_n']=len(values)
        for stat in ['mean','median','p90','p95','max']:meta[metric+'_'+stat]=None
        if values:
            a=np.array(values);meta[metric+'_mean']=float(a.mean());meta[metric+'_median']=float(np.median(a));meta[metric+'_p90']=float(np.quantile(a,.9));meta[metric+'_p95']=float(np.quantile(a,.95));meta[metric+'_max']=float(a.max())
        for r in rows:
            when=r['enabled_bsb'] if metric in ('identification_seconds','activation_gap_seconds') else r['presidential_bsb']
            if eligible and r['valid_timing'] and r[metric] is not None and when is not None:histogram[(turn,uf,when//300*300,metric,r[metric])]+=1
    return meta,rows,histogram

def section_schema():
    fields=[]
    strings='id uf municipality zone section name source bu_kind opening_local closing_local error'.split()
    ints='profile_version turn aptos total v13 v22 blank null other_votes presidential_markers computed_messages completed_presidential_sessions enablement_events cancelled_enablement_events identification_attempts_without_enablement clock_regressions foreign_section_events unknown_binding incomplete_sessions suspended_sessions valid_sessions'.split()
    fields += [pa.field(k,pa.string()) for k in strings]+[pa.field(k,pa.int64()) for k in ints]
    fields += [pa.field(k,pa.bool_()) for k in ['section_reconciled','section_eligible']]
    for metric in METRICS:
        fields.append(pa.field(metric+'_n',pa.int64()))
        fields += [pa.field(metric+'_'+stat,pa.float64()) for stat in ['mean','median','p90','p95','max']]
    return pa.schema(fields)

def process_batch(inputs,folder):
    folder=pathlib.Path(folder);folder.mkdir(parents=True,exist_ok=True)
    metas=[];all_rows=[];hist=collections.Counter();errors=[]
    for item in inputs:
        try:
            meta,rows,counts=profile(item);metas.append(meta);all_rows.extend(rows);hist.update(counts)
        except Exception as e:
            turn,key,name,_,_,source=item;uf,m,z,s=key.split('/')
            metas.append(dict(profile_version=PROFILE_VERSION,turn=turn,id=key,uf=uf,municipality=m,zone=z,section=s,name=name,source=source,error=repr(e)))
            errors.append(dict(turn=turn,id=key,error=repr(e)))
    pq.write_table(pa.Table.from_pylist(metas,schema=section_schema()),folder/'sections.parquet',compression='zstd')
    pq.write_table(pa.Table.from_pylist(all_rows,schema=EVENT_SCHEMA),folder/'events.parquet',compression='zstd')
    hs=pa.schema([('turn',pa.int8()),('uf',pa.string()),('second',pa.int32()),('metric',pa.string()),('value',pa.int32()),('n',pa.int64())])
    hrows=[dict(zip(['turn','uf','second','metric','value','n'],(*key,n))) for key,n in hist.items()]
    pq.write_table(pa.Table.from_pylist(hrows,schema=hs),folder/'histograms.parquet',compression='zstd')
    manifest=dict(profile_version=PROFILE_VERSION,turn=inputs[0][0],uf=inputs[0][1].split('/')[0],ids=[r['id'] for r in metas],sections=len(metas),events=len(all_rows),errors=errors)
    (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    return manifest
