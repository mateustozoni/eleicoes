"""Etapas explícitas da reprodução; downloads grandes só com --stage download/all."""
import argparse,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
STAGES={
 'metadata':[('bootstrap.py',)],
 'download':[('bootstrap.py',),('collect.py',),('download_first_turn.py',),('context_locations.py',)],
 'process':[('analyze.py',),('profile_jobs.py',),('operation_profiles.py','--workers','6'),('recount_first_turn_types.py',),('verify_official_layout.py',)],
 'report':[('check_national_reference.py',),('refresh_metadata.py',),('recut_1705.py',),('report.py',),('verify_active_cutoff.py',),('documentary_analysis.py',),('verify_documentary.py',),('documentary_report.py',),('final_audit.py',),('publication_figures.py',),('build_pdf.py',)]}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=list(STAGES)+['all'],default='metadata');a=p.parse_args()
 stages=list(STAGES) if a.stage=='all' else [a.stage]
 for stage in stages:
  for script,*args in STAGES[stage]:
   command=[sys.executable,str(ROOT/'scripts'/script),*args];print('RUN',stage,script,*args,flush=True);subprocess.run(command,cwd=str(ROOT),check=True)
 if a.stage in ['report','all']:print('PDF gerado. Renderize e confira a apresentação antes de registrar a revisão e exportar public/.',flush=True)
if __name__=='__main__':main()
