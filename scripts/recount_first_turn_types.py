"""Releitura direta de todos os BUs de primeiro turno, sem logs, por tipo e código."""
import collections,concurrent.futures,hashlib,json,pathlib,zipfile,re
import asn1tools,pyarrow as pa,pyarrow.parquet as pq
ROOT=pathlib.Path(__file__).resolve().parents[1]
def process(uf):
 schema=asn1tools.compile_files(str(ROOT/'docs/bu.asn1'),'ber');counts=collections.Counter();sections=0;extra=[]
 with zipfile.ZipFile(ROOT/'data/first-turn-archives'/(uf+'.zip')) as z:
  for name in z.namelist():
   if not name.endswith(('-bu.dat','-busa.dat')):continue
   bu=schema.decode('EntidadeBoletimUrna',schema.decode('EntidadeEnvelopeGenerico',z.read(name))['conteudo']);sections+=1
   for election in bu['resultadosVotacaoPorEleicao']:
    if election['idEleicao']!=6257:continue
    for r in election['resultadosVotacao']:
     for cargo in r['totaisVotosCargo']:
      if cargo['codigoCargo']!=('cargoConstitucional','presidente'):continue
      for v in cargo['votosVotaveis']:
       code=v.get('identificacaoVotavel',{}).get('codigo');kind=v['tipoVoto'];counts[(kind,str(code))]+=v['quantidadeVotos']
       if code==28:
        ident=bu['identificacaoSecao'];m=ident['municipioZona'];key=f"{uf}/{m['municipio']:05}/{m['zona']:04}/{ident['secao']:04}"
        extra.append(dict(id=key,uf=uf,code=28,kind=kind,votes=v['quantidadeVotos'],source_member=name,sha256=hashlib.sha256(z.read(name)).hexdigest()))
 return dict(uf=uf,sections=sections,counts=[dict(kind=k[0],code=k[1],votes=v) for k,v in counts.items()],extra=extra)
def run():
 ufs='ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to zz'.split();counts=collections.Counter();rows=[];summaries=[]
 with concurrent.futures.ProcessPoolExecutor(max_workers=8) as pool:
  for r in pool.map(process,ufs):
   for x in r['counts']:counts[(x['kind'],x['code'])]+=x['votes']
   rows.extend(r.pop('extra'));summaries.append(r);print(r['uf'],r['sections'],flush=True)
 national=json.loads((ROOT/'data/raw/first-turn-national.json').read_text());candidates={x['n']:int(x['vap']) for cargo in national['carg'] if cargo['cd']=='1' for a in cargo['agr'] for p in a['par'] for x in p['cand']}
 checks={k:dict(bu=counts['nominal',k],national=v,difference=counts['nominal',k]-v) for k,v in candidates.items()}
 data=dict(sections=sum(r['sections'] for r in summaries),counts=[dict(kind=k[0],code=k[1],votes=v) for k,v in sorted(counts.items())],candidate_checks=checks,
   nominal_code28=counts['nominal','28'],official_vn=int(national['v']['vn']),official_vnt=int(national['v']['vnt']),official_tvn=int(national['v']['tvn']),
   total=sum(counts.values()),official_total=int(national['v']['tv']),by_state=summaries,
   explanation='BU nominal code28 is preserved separately; it is absent from the national candidate list. Its total equals field vnt. No legal cause inferred from this arithmetic alone.')
 data['reconciled']=(data['total']==data['official_total'] and not any(r['difference'] for r in checks.values()) and counts['nulo','None']==data['official_vn'] and counts['nominal','28']==data['official_vnt'] and data['official_vn']+data['official_vnt']==data['official_tvn'])
 (ROOT/'output/first-turn-vote-type-audit.json').write_text(json.dumps(data,ensure_ascii=False,indent=2));pq.write_table(pa.Table.from_pylist(rows),ROOT/'output/first-turn-code28-sections.parquet',compression='zstd');print('RECONCILED',data['reconciled'],flush=True)
 if not data['reconciled']:raise SystemExit('Unreconciled first-turn vote types')
if __name__=='__main__':run()
