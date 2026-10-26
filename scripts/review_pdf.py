"""Renderiza o PDF e registra uma revisão visual explicitamente confirmada."""
import argparse,hashlib,json,pathlib,shutil,subprocess
from datetime import datetime,timezone
from pypdf import PdfReader
ROOT=pathlib.Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--render',action='store_true');mode.add_argument('--confirm-reviewed',action='store_true',help='Use somente depois de inspecionar todas as páginas renderizadas.');a=p.parse_args()
 pdf=ROOT/'output/pdf/relatorio-presidencial-2026.pdf';pages=len(PdfReader(pdf).pages);sha=hashlib.sha256(pdf.read_bytes()).hexdigest();folder=ROOT/'tmp/pdfs/review';manifest=folder/'render-manifest.json'
 if a.render:
  if not shutil.which('pdftoppm'):p.error('pdftoppm ausente; instale Poppler conforme docs/RUNNING.md.')
  folder.mkdir(parents=True,exist_ok=True)
  subprocess.run(['pdftoppm','-scale-to','1400','-png',str(pdf),str(folder/'page')],check=True)
  names=[folder/f'page-{i:0{len(str(pages))}}.png' for i in range(1,pages+1)]
  # Poppler usa pelo menos dois dígitos quando o documento tem dez ou mais páginas.
  assert all(v.exists() for v in names)
  manifest.write_text(json.dumps(dict(pdf_sha256=sha,pages=pages,images=[v.name for v in names]),indent=2))
  print(f'{pages} páginas renderizadas em {folder}. Inspecione-as antes de usar --confirm-reviewed.');return
 data=json.loads(manifest.read_text());assert data['pdf_sha256']==sha,'O PDF mudou depois da renderização.';assert data['pages']==pages and all((folder/n).exists() for n in data['images'])
 audit=json.loads((ROOT/'output/final-audit.json').read_text());assert audit['passed'],'Auditoria dos dados não aprovada.'
 status_path=ROOT/'output/finalization-status.json';status=json.loads(status_path.read_text()) if status_path.exists() else {}
 status.update(state='finished',pdf_ready=True,verified=True,pdf='pdf/relatorio-presidencial-2026.pdf',pdf_pages=pages,pdf_sha256=sha,updated_utc=datetime.now(timezone.utc).isoformat(),note=f'PDF de {pages} páginas com revisão visual registrada.')
 status_path.write_text(json.dumps(status,ensure_ascii=False,indent=2));(ROOT/'output/pdf-review.json').write_text(json.dumps(dict(pages=pages,rendered_pages=pages,all_pages_visually_reviewed=True,sha256=sha,signature_verification=False),indent=2));print('Revisão registrada. A exportação compacta agora pode ser executada.')
if __name__=='__main__':main()
