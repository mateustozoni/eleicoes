"""Figuras estáticas de publicação, geradas a partir dos agregados congelados."""
import json,pathlib,collections
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from matplotlib.collections import PatchCollection
from matplotlib.colors import Normalize
import duckdb
ROOT=pathlib.Path(__file__).resolve().parents[1];OUT=ROOT/'output/figures';OUT.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold','figure.facecolor':'white','axes.labelcolor':'#243e52','text.color':'#20374a','savefig.facecolor':'white'})
COL=['#177e89','#be7e1c']
def load(n):return json.loads((ROOT/'output'/(n+'.json')).read_text())
def save(name,fig):fig.savefig(OUT/(name+'.png'),dpi=180,bbox_inches='tight');plt.close(fig)
def run():
 a,b=load('1700-summary'),load('summary');t=load('timing-summary');op=load('operations-summary');sc=load('isonomy-scenarios')
 bins=collections.defaultdict(dict)
 for r in b['bins']:bins[r['kind']][r['second']]=r['n']
 timeline_end=max(68400,b['closing']['last_closing_for_timeline'] or 68400)//300*300+300
 times=list(range(min(28800,min(bins['vote'])),timeline_end+1,300));x=np.array(times)/3600;y=np.array([bins['vote'].get(s,0) for s in times])
 fig,axs=plt.subplots(2,1,figsize=(10,6.4));axs[0].step(x,y,where='post',color=COL[0]);axs[0].set_ylabel('Confirmações / 5 minutos');axs[0].set_title('Presidente - confirmações observadas, Brasil')
 axs[1].step(x,y,where='post',color=COL[0]);axs[1].set_xlim(16.5,19.3);axs[1].set_ylim(0,max([v for s,v in bins['vote'].items() if s>=59400]+[1])*1.08);axs[1].set_ylabel('Confirmações / 5 minutos');axs[1].set_title('Ampliação da cauda do dia')
 for ax in axs:
  ax.axvline(17,color='#657c8e',ls='--',label='17h');ax.axvline(17+5/60,color=COL[1],ls=':',label='17h05');ax.set_xlabel('Hora de Brasília');ax.grid(alpha=.15);ax.legend(fontsize=8)
 fig.tight_layout();save('01-series',fig)
 geo=json.loads((ROOT/'data/raw/brazil-states.geojson').read_text());ibge=dict(zip('11 12 13 14 15 16 17 21 22 23 24 25 26 27 28 29 31 32 33 35 41 42 43 50 51 52 53'.split(),'ro ac am rr pa ap to ma pi ce rn pb pe al se ba mg es rj sp pr sc rs ms mt go df'.split()))
 fig,axs=plt.subplots(1,2,figsize=(10.2,6))
 for ax,d,label in zip(axs,[a,b],['Após 17h','Após 17h05']):
  vals={r['uf']:r['post'] for r in d['states']};patches=[];v=[]
  for f in geo['features']:
   uf=ibge[str(f['properties']['codarea'])];coords=f['geometry']['coordinates'];polys=coords if f['geometry']['type']=='MultiPolygon' else [coords]
   for poly in polys:patches.append(Polygon(poly[0],closed=True));v.append(vals[uf])
  pc=PatchCollection(patches,cmap='Blues',edgecolor='white',linewidth=.35);pc.set_array(np.array(v));ax.add_collection(pc);ax.autoscale_view();ax.set_aspect(1.05);ax.set_axis_off();ax.set_title(label);fig.colorbar(pc,ax=ax,shrink=.6,label='Confirmações (escala própria)')
 save('02-maps',fig)
 states=[r for r in a['states'] if r['uf']!='zz'];ufs=[r['uf'] for r in states];vals={r['uf']:r for r in b['states']}
 fig,axs=plt.subplots(1,2,figsize=(10,7));ind=np.arange(len(ufs))
 for ax,rate,title in [(axs[0],False,'Quantidade absoluta'),(axs[1],True,'Por 10 mil votos conciliados')]:
  for j,d in enumerate([a,b]):
   lookup={r['uf']:r for r in d['states']};ys=[lookup[u]['post']*(10000/max(1,lookup[u]['votes']) if rate else 1) for u in ufs];ax.barh(ind+(j-.5)*.35,ys,height=.35,color=COL[j],label=['Após 17h','Após 17h05'][j])
  ax.set_yticks(ind);ax.set_yticklabels([u.upper() for u in ufs]);ax.invert_yaxis();ax.set_title(title);ax.legend(fontsize=8);ax.grid(axis='x',alpha=.15)
 fig.tight_layout();save('03-state-rates',fig)
 for num,metric,title in [('04','identification_seconds','Entrada do identificador até habilitação'),('05','voting_seconds','Habilitação até confirmação de Presidente'),('06','confirmation_gap_seconds','Intervalo entre confirmações sucessivas'),('07','pres_stage_seconds','Etapa aproximada de Presidente')]:
  fig,ax=plt.subplots(figsize=(10,4.2))
  for turn in [1,2]:
   rows=[r for r in t['by_time'] if r['turn']==turn and r['metric']==metric and r['n']>=30];ax.plot([r['second']/3600 for r in rows],[r['mean'] for r in rows],color=COL[turn-1],label=str(turn)+'º turno')
  ax.set_title(title+' - média por intervalo');ax.set_ylabel('Segundos');ax.set_xlabel('Hora de Brasília');ax.axvline(17,color='gray',ls='--');ax.axvline(17+5/60,color=COL[1],ls=':');ax.legend();ax.grid(alpha=.2);save(num+'-duration',fig)
 fig,axs=plt.subplots(2,1,figsize=(10,9));timegrid=np.arange(28800,72000,300)
 for ax,turn in zip(axs,[1,2]):
  matrix=np.full((27,len(timegrid)),np.nan);ix={u:i for i,u in enumerate(ufs)};tx={s:i for i,s in enumerate(timegrid)}
  for r in t['by_state_time']:
   if r['turn']==turn and r['metric']=='identification_seconds' and r['n']>=20 and r['second'] in tx:matrix[ix[r['uf']],tx[r['second']]]=r['mean']
  im=ax.imshow(matrix,aspect='auto',cmap='YlGnBu',vmin=0,vmax=80,extent=[8,20,26.5,-.5]);ax.set_yticks(range(27));ax.set_yticklabels([u.upper() for u in ufs],fontsize=7);ax.set_title(str(turn)+'º turno - identificação média');ax.set_xlabel('Hora de Brasília');fig.colorbar(im,ax=ax,label='Segundos (80 ou mais no teto)')
 fig.tight_layout();save('08-heatmap',fig)
 fig,axs=plt.subplots(2,2,figsize=(10,7.2))
 for col,(name,label) in enumerate([('1700-correlations','17h'),('correlations','17h05')]):
  d=load(name)
  label_ufs={r['uf'] for r in sorted(d['states'],key=lambda r:r['late_rate'],reverse=True)[:7]}
  for row,period in enumerate(['pre','post']):
   ax=axs[row,col];xx=[];yy=[]
   for r in d['states']:
    share=r['nonbio_share_'+period]
    if share is not None:
     xx.append(share*100);yy.append(r['late_rate']*10000)
     if r['uf'] in label_ufs:ax.annotate(r['uf'].upper(),(xx[-1],yy[-1]),xytext=(3,3),textcoords='offset points',fontsize=7)
   ax.scatter(xx,yy,s=22,c=COL[col]);ax.set_title(('Pré ' if row==0 else 'Pós ')+label);ax.set_xlabel('Identificação sem reconhecimento do eleitor (%)');ax.set_ylabel('Votos pós-corte / 10 mil');ax.grid(alpha=.2)
 fig.tight_layout();save('09-bio-state',fig)
 recognition=t.get('method_recognition_summary',[])
 if recognition:
  fig,ax=plt.subplots(figsize=(10,4));kinds=['Digital do eleitor reconhecida','Sem reconhecimento biométrico do eleitor'];groups=['1º turno','2º turno','2º turno · 17h05+'];ind=np.arange(2)
  for j,(group,color) in enumerate(zip(groups,['#3a6793','#b87510','#804b95'])):
   selected=[next(r for r in recognition if r['cohort']==group and r['recognition']==kind) for kind in kinds]
   bars=ax.bar(ind+(j-1)*.23,[r['mean'] for r in selected],.23,label=group,color=color)
   ax.bar_label(bars,labels=[f'{r["mean"]:.1f}s' for r in selected],padding=3,fontsize=9)
  ax.set_xticks(ind);ax.set_xticklabels(['Digital do eleitor reconhecida','Sem reconhecimento do eleitor']);ax.set_ylim(0,max(r['mean'] for r in recognition)*1.25);ax.set_ylabel('Tempo médio de identificação (s)');ax.legend();ax.set_title('Identificação: turnos completos e confirmações após 17h05');save('15-method-comparison',fig)
 c=duckdb.connect()
 for prefix,label,num in [('1700-','17h','10'),('','17h05','11')]:
  path=ROOT/'output'/(prefix+'section-correlations.parquet');cols=c.execute('DESCRIBE SELECT * FROM read_parquet(?)',[str(path)]).fetchall();names=[r[0] for r in cols]
  # Schema is recorded in the manifest; choose the explicit ratio columns.
  data=c.execute('SELECT * FROM read_parquet(?)',[str(path)]).fetch_arrow_table().to_pydict()
  xname='nonbio_rate';yname='late_rate'
  if xname in names and yname in names:
   fig,axs=plt.subplots(2,1,figsize=(9,7.8))
   for ax,period,title in zip(axs,['pre','post'],['Composição pré-corte','Composição pós-corte']):
    subset=[(x,y) for x,y in zip(data['nonbio_share_'+period],data[yname]) if x is not None and y is not None];xy=np.array(subset);image=ax.hexbin(xy[:,0]*100,xy[:,1]*100,gridsize=50,bins='log',mincnt=1,cmap='viridis');fig.colorbar(image,ax=ax,label='Seções (log)')
    ax.set_xlabel('Sem reconhecimento do eleitor no período (%)');ax.set_ylabel('Confirmações após '+label+' (%)');ax.set_title(title+' - '+label+'; n='+str(len(subset)))
   fig.tight_layout();save(num+'-density',fig)
 fig,axs=plt.subplots(1,2,figsize=(10,7))
 for ax,field,title in zip(axs,['protocol','print'],['Etapa final até confirmação','Confirmação até fim da 1ª impressão']):
  for turn in [1,2]:
   rows={r['uf']:r for r in op['by_state'] if r['turn']==turn}
   for i,u in enumerate(ufs):
    r=rows[u];y=i+(turn-1.5)*.22;ax.plot([r[field+'_median']/60,r[field+'_p95']/60],[y,y],color=COL[turn-1]);ax.scatter(r[field+'_median']/60,y,c=COL[turn-1],s=9)
  ax.set_yticks(range(27));ax.set_yticklabels([u.upper() for u in ufs]);ax.invert_yaxis();ax.set_title(title);ax.set_xlabel('Minutos; ponto=P50, linha até P95')
 fig.tight_layout();save('12-protocol',fig)
 margin=sc['baseline_margin_13_minus_22'];maxextra=sc['covered_abstention_stock'];extra=np.linspace(0,maxextra,250);share=np.linspace(0,1,200);z=margin+extra[None,:]*(2*share[:,None]-1)
 fig,ax=plt.subplots(figsize=(10,5.5));im=ax.pcolormesh(extra/1e6,share*100,z/1e6,cmap='BrBG',shading='auto',norm=matplotlib.colors.TwoSlopeNorm(vcenter=0,vmin=-np.max(np.abs(z))/1e6,vmax=np.max(np.abs(z))/1e6));ax.contour(extra/1e6,share*100,z,levels=[0],colors='#243747',linewidths=1);ax.set_xlabel('Votos nominais adicionais hipotéticos (milhões)');ax.set_ylabel('Parcela hipotética dos adicionais no 13 (%)');ax.set_title('Sensibilidade aritmética - votos realizados mantidos');fig.colorbar(im,ax=ax,label='Diferença final 13 - 22 (milhões)');save('13-sensitivity',fig)
 rows=sc['scenarios'];fig,ax=plt.subplots(figsize=(10,6));labels=[]
 for i,r in enumerate(rows):
  label=r['window']+' / '+r['pace']+' / '+str(int(r['realization']*100))+'%';labels.append(label);lo=r['margin_all_extra_22']/1e6;hi=r['margin_all_extra_13']/1e6;ax.plot([lo,hi],[i,i],c='#becbd3',lw=3);ax.scatter(r['margin_local_first_finalists_share']/1e6,i,s=16,color=COL[1]);ax.scatter(r['margin_local_second_share']/1e6,i,s=16,color=COL[0])
 ax.axvline(0,color='gray',ls='--');ax.set_yticks(range(len(rows)));ax.set_yticklabels(labels,fontsize=8);ax.invert_yaxis();ax.set_xlabel('Diferença 13 - 22 (milhões)');ax.set_title('Cenários: extremos e projeções ecológicas');save('14-scenarios',fig)
 pairs=c.execute('SELECT nonbio_share,identification_second,identification_residual_mix FROM read_parquet(?)',[str(ROOT/'output/timing-paired-sections.parquet')]).fetchall() if False else None
 c.close()
 manifest={p.name:dict(bytes=p.stat().st_size) for p in OUT.glob('*.png')};(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest))
if __name__=='__main__':run()
