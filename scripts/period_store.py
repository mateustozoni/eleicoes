"""Contagens temporais conservadoras por seção, sem atribuir candidato ao horário."""
import json

def ingest(con,manifests):
    con.execute('CREATE TABLE IF NOT EXISTS timing_period_batches(path VARCHAR PRIMARY KEY)')
    con.execute('''CREATE TABLE IF NOT EXISTS timing_periods(turn INTEGER,id VARCHAR,known_total BIGINT,
       pre17 BIGINT,at17 BIGINT,post17 BIGINT,pre1735 BIGINT,at1735 BIGINT,post1735 BIGINT,PRIMARY KEY(turn,id))''')
    known={r[0] for r in con.execute('SELECT path FROM timing_period_batches').fetchall()}
    todo=[p for p in manifests if str(p) not in known]
    for start in range(0,len(todo),50):
        batch=todo[start:start+50];files=[str(p.parent/'events.parquet') for p in batch]
        con.execute('BEGIN')
        try:
            con.execute('''INSERT INTO timing_periods SELECT turn,id,count(*)::BIGINT,
                count(*) FILTER(WHERE presidential_bsb<61200)::BIGINT,
                count(*) FILTER(WHERE presidential_bsb=61200)::BIGINT,
                count(*) FILTER(WHERE presidential_bsb>61200)::BIGINT,
                count(*) FILTER(WHERE presidential_bsb<63300)::BIGINT,
                count(*) FILTER(WHERE presidential_bsb=63300)::BIGINT,
                count(*) FILTER(WHERE presidential_bsb>63300)::BIGINT
                FROM read_parquet(?,union_by_name=true) WHERE section_eligible AND valid_timing AND presidential_bsb IS NOT NULL
                GROUP BY turn,id''',[files])
            con.executemany('INSERT INTO timing_period_batches VALUES (?)',[(str(p),) for p in batch]);con.execute('COMMIT')
        except BaseException:con.execute('ROLLBACK');raise
