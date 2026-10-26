"""Ingestão incremental de estatísticas de sessões e histogramas, calculados no servidor."""
import json
import pathlib
import sqlite3
from timing_profiles import PROFILE_VERSION,METRICS
from period_store import ingest as ingest_periods

ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE=ROOT/'data/timing'/('v'+str(PROFILE_VERSION))
KNOWN_NONBIO="'no_elector_biometric','pollworker_biometric','pollworker_unassigned_fingerprint','pollworker_captured_fingerprint','biographic'"

def published():
    return sorted(p for turn in ['1t','2t'] for p in (BASE/turn).glob('*/*/manifest.json'))

def ingest(con,manifests=None):
    con.execute('CREATE TABLE IF NOT EXISTS profile_batches(path VARCHAR PRIMARY KEY,sections BIGINT,events BIGINT)')
    known={r[0] for r in con.execute('SELECT path FROM profile_batches').fetchall()}
    paths=published() if manifests is None else manifests
    index=sqlite3.connect(str(ROOT/'data/timing/profile-lookup.sqlite'))
    index.execute('CREATE TABLE IF NOT EXISTS lookup(turn INTEGER,id TEXT,batch TEXT,PRIMARY KEY(turn,id)) WITHOUT ROWID')
    index.execute('CREATE TABLE IF NOT EXISTS indexed_batches(path TEXT PRIMARY KEY)')
    indexed={p for p, in index.execute('SELECT path FROM indexed_batches')}
    for p in paths:
        if str(p) in indexed:continue
        try:relative=str(p.parent.relative_to(BASE))
        except ValueError:continue
        m=json.loads(p.read_text())
        index.executemany('INSERT OR IGNORE INTO lookup VALUES (?,?,?)',[(m['turn'],key,relative) for key in m['ids']])
        index.execute('INSERT INTO indexed_batches VALUES (?)',(str(p),))
    index.commit();index.close()
    todo=[p for p in paths if str(p) not in known]
    for start in range(0,len(todo),8):
        batch=todo[start:start+8]
        section_files=[str(p.parent/'sections.parquet') for p in batch]
        event_files=[str(p.parent/'events.parquet') for p in batch]
        con.execute('BEGIN')
        try:
            exists=con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name='timing_sections'").fetchone()[0]
            if not exists:
                con.execute('CREATE TABLE timing_sections AS SELECT * FROM read_parquet(?,union_by_name=true) WHERE false',[section_files])
                con.execute('ALTER TABLE timing_sections ADD PRIMARY KEY(turn,id)')
            con.execute('INSERT INTO timing_sections SELECT * FROM read_parquet(?,union_by_name=true)',[section_files])
            con.execute('CREATE OR REPLACE TEMP TABLE profile_events_incoming AS SELECT * FROM read_parquet(?,union_by_name=true)',[event_files])
            flow_sql=f'''SELECT turn,id,count(*)::BIGINT session_records,
                count(*) FILTER(WHERE completed)::BIGINT completed_sessions,
                count(*) FILTER(WHERE valid_timing)::BIGINT valid_sessions,
                count(*) FILTER(WHERE valid_timing AND section_eligible)::BIGINT strict_sessions,
                count(*) FILTER(WHERE NOT completed AND pres_markers>0)::BIGINT unfinished_presidential_sessions,
                count(DISTINCT device)::BIGINT device_count,
                min(presidential_bsb) first_presidential_bsb,max(presidential_bsb) last_presidential_bsb,
                max(presidential_bsb-presidential_local) offset_seconds,
                avg(cargo_confirmations) FILTER(WHERE valid_timing) mean_cargo_confirmations,
                count(*) FILTER(WHERE valid_timing AND auth_kind='elector_biometric')::BIGINT biometric_sessions,
                count(*) FILTER(WHERE valid_timing AND auth_kind IN ({KNOWN_NONBIO}))::BIGINT nonbiometric_sessions,
                count(*) FILTER(WHERE gap_crosses_restart AND confirmation_gap_seconds IS NOT NULL)::BIGINT gaps_with_restart,
                count(*) FILTER(WHERE completed AND cargo_confirmations=1)::BIGINT completed_one_stage,
                count(*) FILTER(WHERE completed AND cargo_confirmations=2)::BIGINT completed_two_stages,
                count(*) FILTER(WHERE completed AND cargo_confirmations>=6)::BIGINT completed_six_or_more_stages
                FROM profile_events_incoming GROUP BY turn,id'''
            if not con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name='timing_flows'").fetchone()[0]:
                con.execute('CREATE TABLE timing_flows AS '+flow_sql+' LIMIT 0');con.execute('ALTER TABLE timing_flows ADD PRIMARY KEY(turn,id)')
            con.execute('INSERT INTO timing_flows '+flow_sql)
            statistics=[]
            for metric in METRICS:
                statistics.extend([f'count({metric})::BIGINT {metric}_n',f'avg({metric}) {metric}_mean',
                    f'median({metric}) {metric}_median',f'quantile_cont({metric},.9) {metric}_p90',f'max({metric}) {metric}_max'])
            method_sql='''SELECT turn,id,auth_kind,count(*)::BIGINT sessions,avg(cargo_confirmations) mean_cargo_confirmations,
                '''+','.join(statistics)+''' FROM profile_events_incoming WHERE valid_timing AND section_eligible GROUP BY turn,id,auth_kind'''
            if not con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name='timing_methods'").fetchone()[0]:
                con.execute('CREATE TABLE timing_methods AS '+method_sql+' LIMIT 0');con.execute('ALTER TABLE timing_methods ADD PRIMARY KEY(turn,id,auth_kind)')
            con.execute('INSERT INTO timing_methods '+method_sql)
            con.execute('''CREATE TABLE IF NOT EXISTS timing_hist(turn TINYINT,uf VARCHAR,second INTEGER,auth_kind VARCHAR,
                cargos INTEGER,metric VARCHAR,value INTEGER,n BIGINT,PRIMARY KEY(turn,uf,second,auth_kind,cargos,metric,value))''')
            value_rows=[]
            for metric in METRICS:
                when='enabled_bsb' if metric in ('identification_seconds','activation_gap_seconds') else 'presidential_bsb'
                value_rows.append(f"('{metric}',{metric},{when})")
            con.execute('''INSERT INTO timing_hist SELECT turn,uf,(floor(v.event_second/300)*300)::INTEGER AS "second",
                auth_kind,cargo_confirmations,v.metric,v.seconds_value,count(*)::BIGINT n
                FROM profile_events_incoming e CROSS JOIN LATERAL (VALUES '''+','.join(value_rows)+''') v(metric,seconds_value,event_second)
                WHERE valid_timing AND section_eligible AND v.seconds_value IS NOT NULL AND v.event_second IS NOT NULL
                GROUP BY turn,uf,"second",auth_kind,cargo_confirmations,v.metric,v.seconds_value
                ON CONFLICT(turn,uf,second,auth_kind,cargos,metric,value) DO UPDATE SET n=timing_hist.n+excluded.n''')
            records=[]
            for p in batch:
                m=json.loads(p.read_text());records.append((str(p),m['sections'],m['events']))
            con.executemany('INSERT INTO profile_batches VALUES (?,?,?)',records)
            con.execute('COMMIT')
        except BaseException:
            con.execute('ROLLBACK');raise
    ingest_periods(con,paths)

def exists(con):
    return bool(con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name='timing_sections'").fetchone()[0])
