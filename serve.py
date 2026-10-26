"""Servidor da cópia compacta; não requer pacotes de terceiros nem dados eleitorais brutos."""
import argparse,pathlib,subprocess,sys,urllib.parse
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
ROOT=pathlib.Path(__file__).resolve().parent
class SnapshotHandler(SimpleHTTPRequestHandler):
 def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT/'public'),**kwargs)
 def do_GET(self):
  parsed=urllib.parse.urlparse(self.path)
  if parsed.path=='/':self.send_response(302);self.send_header('Location','/report.html');self.end_headers();return
  if parsed.path in ('/section','/api/section'):
   self.send_response(302);self.send_header('Location','/data-not-included.html?feature=section');self.end_headers();return
  return super().do_GET()
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8765);parser.add_argument('--mode',choices=['snapshot','full'],default='snapshot');args=parser.parse_args()
 if args.mode=='full':
  if not (ROOT/'output/report.html').exists():parser.error('Modo completo requer coleta e processamento locais; consulte docs/RUNNING.md.')
  return subprocess.call([sys.executable,str(ROOT/'scripts/local_report_server.py'),'--port',str(args.port)],cwd=str(ROOT))
 if not (ROOT/'public/report.html').exists():parser.error('Snapshot ausente. Execute scripts/export_public_snapshot.py no ambiente de análise.')
 print(f'Relatório: http://127.0.0.1:{args.port}/report.html\nModo snapshot: sem coleta nem consulta das bases locais.',flush=True)
 server=ThreadingHTTPServer(('127.0.0.1',args.port),SnapshotHandler)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
 return 0
if __name__=='__main__':sys.exit(main())
