"""Limites determinísticos: o BU não vincula candidato ao horário."""

def interval(candidate_votes,total_votes,period_votes):
    if not 0<=candidate_votes<=total_votes or not 0<=period_votes<=total_votes:
        raise ValueError('Invalid ballot counts')
    return max(0,candidate_votes-(total_votes-period_votes)),min(candidate_votes,period_votes)

def build_bounds(con,national_candidates):
    # Received-only files remain provisional and cannot support a national proof.
    eligible="time_eligible AND coalesce(hash_status,'Totalizado')='Totalizado'"
    known=con.execute(f'SELECT coalesce(sum(v13),0),coalesce(sum(v22),0),count(*) FROM good WHERE {eligible}').fetchone()
    known=dict(zip(('13','22','sections'),known))
    if any(known[c]>national_candidates[c] for c in ('13','22')):
        return dict(valid=False,reason='A soma do corpus excede a referência nacional; é necessário conciliar as versões.')
    result=dict(valid=True,known_sections=known['sections'],periods={})
    for period in ('pre','at17','post'):
        cells={}
        for c in ('13','22'):
            lo,hi=con.execute(f'''SELECT coalesce(sum(greatest(0,v{c}-(total-{period}))),0),
                coalesce(sum(least(v{c},{period})),0) FROM good WHERE {eligible}''').fetchone()
            unknown=national_candidates[c]-known[c]
            cells[c]=dict(minimum=int(lo),maximum=int(hi+unknown),unresolved_candidate_votes=int(unknown))
        winner='13' if cells['13']['minimum']>cells['22']['maximum'] else ('22' if cells['22']['minimum']>cells['13']['maximum'] else None)
        result['periods'][period]=dict(candidates=cells,provable_winner=winner)
    return result
