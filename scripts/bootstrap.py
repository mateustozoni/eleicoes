"""Inicializa diretórios e metadados pequenos; não baixa BUs nem logs."""
import argparse,hashlib,json,pathlib,shutil
ROOT=pathlib.Path(__file__).resolve().parents[1]
ASSETS=['catalog.json','national.json','first-turn-national.json','ckan.json']
def bootstrap(target):
 for name in ['data/raw','data/derived','data/reference-first-turn','data/first-turn-archives','data/timing','data/operations','data/context','output','output/figures','output/pdf','tmp']:(target/name).mkdir(parents=True,exist_ok=True)
 records=[]
 for name in ASSETS:
  path=target/'data/raw'/name
  if not path.exists():
   shutil.copyfile(ROOT/'assets/bootstrap'/name,path);origin='bundled_snapshot'
  else:origin='existing_local_file'
  records.append(dict(path=str(path.relative_to(target)),origin=origin,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
 geo=target/'data/raw/brazil-states.geojson'
 if not geo.exists():shutil.copyfile(ROOT/'assets/brazil-states.geojson',geo)
 (target/'data/bootstrap-manifest.json').write_text(json.dumps(dict(files=records,downloads_raw=False),indent=2))
 return records
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=pathlib.Path,default=ROOT);a=p.parse_args();rows=bootstrap(a.root.resolve());print(json.dumps(dict(root=str(a.root.resolve()),metadata_files=len(rows),raw_downloads=False)))
