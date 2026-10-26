"""Cache incremental das etapas de encerramento, separado das sessões de eleitores."""
import json
import pathlib

ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE=ROOT/'data/operations/v1'

def published():return sorted(p for t in ['1t','2t'] for p in (BASE/t).glob('*/*/manifest.json'))

def ingest(con,paths=None):
    con.execute('CREATE TABLE IF NOT EXISTS operation_batches(path VARCHAR PRIMARY KEY,sections BIGINT)')
    known={r[0] for r in con.execute('SELECT path FROM operation_batches').fetchall()}
    todo=[p for p in (published() if paths is None else paths) if str(p) not in known]
    for start in range(0,len(todo),40):
        batch=todo[start:start+40];files=[str(p.parent/'operations.parquet') for p in batch]
        con.execute('BEGIN')
        try:
            if not con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name='operation_sections'").fetchone()[0]:
                con.execute('CREATE TABLE operation_sections AS SELECT * FROM read_parquet(?,union_by_name=true) WHERE false',[files]);con.execute('ALTER TABLE operation_sections ADD PRIMARY KEY(turn,id)')
            con.execute('INSERT INTO operation_sections SELECT * FROM read_parquet(?,union_by_name=true)',[files])
            con.executemany('INSERT INTO operation_batches VALUES (?,?)',[(str(p),json.loads(p.read_text())['sections']) for p in batch])
            con.execute('COMMIT')
        except BaseException:con.execute('ROLLBACK');raise

def exists(con):return bool(con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name='operation_sections'").fetchone()[0])
