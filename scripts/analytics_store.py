"""DuckDB incremental: cada lote JSONL é ingerido uma vez, com a revisão mais nova por seção."""
import json
import os
import time
import pathlib
import duckdb
from profile_store import ingest as ingest_profiles
from operation_store import ingest as ingest_operations

ROOT=pathlib.Path(__file__).resolve().parents[1]
SCHEMA={k:'VARCHAR' for k in 'id uf municipality zone section name local source hash_status bu_kind opening_local closing_local error'.split()}
SCHEMA.update({k:'BIGINT' for k in '''parser_version total v13 v22 blank null aptos_president bu_bio bu_biography bu_no_bio log_votes pre at17 post
    unknown_time clock_backwards unknown_auth pre1735 at1735 post1735 first last offset_hours log_files raw_log_votes foreign_section_events binding_unknown_votes'''.split()})
SCHEMA.update({k:'BOOLEAN' for k in ['full_turnout','match','time_eligible']})
SCHEMA['bins']=[dict(second='BIGINT',kind='VARCHAR',n='BIGINT')]
SCHEMA['auth_cuts']=[dict(period='VARCHAR',kind='VARCHAR',n='BIGINT')]
SCHEMA['auth_cuts1735']=[dict(period='VARCHAR',kind='VARCHAR',n='BIGINT')]
SCHEMA['foreign_sections']=[dict(section='VARCHAR',votes='BIGINT')]

def open_store(paths=None,profile_paths=None,operation_paths=None):
    for attempt in range(60):
        try:
            con=duckdb.connect(str(ROOT/'data/analytics.duckdb'));break
        except duckdb.IOException as exc:
            if 'lock' not in str(exc).lower() or attempt==59:raise
            time.sleep(.5)
    con.execute("SET memory_limit='8GB'");con.execute('SET threads='+str(os.cpu_count() or 4))
    con.execute('CREATE TABLE IF NOT EXISTS ingested_files(path VARCHAR PRIMARY KEY,size BIGINT)')
    exists=con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name='sections'").fetchone()[0]
    if not exists:
        con.execute("CREATE TABLE sections AS SELECT s.* FROM (SELECT from_json('{}',?) s) WHERE false",[json.dumps(SCHEMA)])
        con.execute('ALTER TABLE sections ADD PRIMARY KEY(id)')
    known=dict(con.execute('SELECT path,size FROM ingested_files').fetchall())
    files=paths if paths is not None else sorted((ROOT/'data/derived').glob('part-*.jsonl'))
    todo=[p for p in files if str(p) not in known]
    for p in files:
        if str(p) in known and known[str(p)]!=p.stat().st_size:
            raise ValueError('Previously ingested batch was modified: '+str(p))
    for start in range(0,len(todo),20):
        batch=todo[start:start+20]
        con.execute('BEGIN')
        try:
            con.execute('CREATE OR REPLACE TEMP TABLE incoming AS SELECT s.* FROM (SELECT from_json(json,?) s FROM read_ndjson_objects(?))',
                [json.dumps(SCHEMA),[str(p) for p in batch]])
            con.execute('''INSERT OR REPLACE INTO sections SELECT i.* FROM incoming i LEFT JOIN sections old USING(id)
                WHERE old.id IS NULL OR coalesce(i.parser_version,0)>=coalesce(old.parser_version,0)
                QUALIFY row_number() OVER(PARTITION BY i.id ORDER BY i.parser_version DESC NULLS LAST)=1''')
            con.executemany('INSERT INTO ingested_files VALUES (?,?)',[(str(p),p.stat().st_size) for p in batch])
            con.execute('COMMIT')
        except BaseException:
            con.execute('ROLLBACK');raise
    ingest_profiles(con,profile_paths)
    ingest_operations(con,operation_paths)
    return con

if __name__=='__main__':
    con=open_store();print(con.execute('SELECT count(*) FROM sections').fetchone()[0]);con.close()
