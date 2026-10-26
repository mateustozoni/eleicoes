"""Conclui a análise e prepara o PDF para inspeção visual, sem declarar verificação sozinho."""
import json,pathlib,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
PDF_PYTHON=sys.executable
def state(phase,note):
 d=dict(state=phase,note=note,pdf_ready=False,verified=False);p=ROOT/'output/finalization-status.json';p.with_suffix('.tmp').write_text(json.dumps(d,ensure_ascii=False));p.with_suffix('.tmp').replace(p);print(note,flush=True)
def run(script,python=None):
 with (ROOT/'output'/('final-'+pathlib.Path(script).stem+'.log')).open('w') as log:
  subprocess.run([python or sys.executable,str(ROOT/'scripts'/script)],cwd=str(ROOT),stdout=log,stderr=subprocess.STDOUT,check=True)
def main():
 state('waiting_metadata','Auditoria de cobertura aprovada; concluindo revalidação dos metadados oficiais.')
 while True:
  m=json.loads((ROOT/'output/metadata-status.json').read_text())
  if m['state']=='finished':break
  if m['state']=='stopped':raise RuntimeError('Metadata stopped')
  time.sleep(5)
 if m['errors'] or m['changed']:raise RuntimeError('Revisar erros ou mudanças nos metadados')
 state('vote_type_review','Revalidação concluída; conferindo a ponte entre tipos de voto do primeiro turno.')
 while not (ROOT/'output/first-turn-vote-type-audit.json').exists():time.sleep(5)
 state('final_audit','Revalidação concluída; conferindo novamente os arquivos e totais.')
 run('final_audit.py')
 state('final_html','Auditoria integral aprovada; consolidando as duas versões do relatório HTML.')
 run('report.py')
 state('publication_figures','Preparando as figuras estáticas de publicação.')
 run('publication_figures.py')
 state('pdf_build','Análises consolidadas; gerando o relatório completo em PDF.')
 run('build_pdf.py',PDF_PYTHON)
 state('pdf_visual_review','PDF gerado; verificando apresentação e legibilidade de todas as páginas.')
 folder=ROOT/'tmp/pdfs/rendered';folder.mkdir(parents=True,exist_ok=True)
 subprocess.run(['pdftoppm','-scale-to','1400','-png',str(ROOT/'output/pdf/relatorio-presidencial-2026.pdf'),str(folder/'page')],check=True)
 print('PDF_RENDERED_FOR_REVIEW',flush=True)
if __name__=='__main__':
 try:main()
 except BaseException as e:
  state('review_required','Finalização requer revisão: '+repr(e));raise
