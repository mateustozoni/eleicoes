(() => {
  let busy = false;
  const number = value => value == null ? '—' : Number(value).toLocaleString('pt-BR');
  const put = (id, value) => { const el = document.getElementById(id); if (el) el.textContent = value; };
  async function tick() {
    if (busy || document.hidden) return;
    busy = true;
    try {
      const main = document.querySelector('main');
      const prefix = main.dataset.prefix || '';
      const get = async name => { const r = await fetch(name, {cache: 'no-store'}); if (!r.ok) throw new Error(name); return r.json(); };
      const [download, analysis, meta, reference, firstFull, timing, metadata, finalization] = await Promise.allSettled([
        get('collection-status.json'), get('analysis-status.json'), get(prefix + 'report-meta.json'),get('reference-status.json'),
        get('first-turn-download-status.json'),get('timing-profile-status.json'),get('metadata-progress.json'),get('finalization-status.json')
      ]);
      if (download.status === 'rejected' && analysis.status === 'rejected') throw new Error('Local status unavailable');
      if (meta.status === 'fulfilled' && meta.value.generation !== main.dataset.generation) {
        const response = await fetch(meta.value.html_name, {cache: 'no-store'});
        if (response.ok) {
          const next = new DOMParser().parseFromString(await response.text(), 'text/html').querySelector('main');
          if (next) {
            const y = window.scrollY;
            const opened = new Set([...main.querySelectorAll('details[open]')].map(d => d.querySelector('summary')?.textContent));
            main.replaceWith(next);
            for (const d of next.querySelectorAll('details')) if (opened.has(d.querySelector('summary')?.textContent)) d.open = true;
            window.scrollTo(0, y);
          }
        }
      }
      if (download.status === 'fulfilled') {
        const s = download.value;
        put('live-downloaded', number(s.sections.done));
        put('live-pending', number(s.sections.pending || 0));
        put('live-errors', number(s.sections.error || 0));
        put('live-volume', number(s.saved_gib) + ' GiB');
        put('live-rate', number(s.recent_requests_per_second) + ' req/s');
        put('live-download-time', s.updated_brasilia || s.updated_utc);
        put('live-percent', number(s.progress_percent) + '%');
        const bar = document.getElementById('live-progress'); if (bar) bar.value = s.progress_percent || 0;
        put('live-message', s.stopped ? 'Coleta interrompida: ' + s.stopped : 'Estado recebido do coletor local');
      }
      if (analysis.status === 'fulfilled') {
        put('live-analyzed', number(analysis.value.processed_sections));
        put('live-analysis-time', new Date(analysis.value.updated_utc).toLocaleString('pt-BR', {timeZone:'America/Sao_Paulo'}));
      }
      if (reference.status === 'fulfilled') {
        const r=reference.value;
        put('live-reference', number(r.processed)+' / '+number(r.planned)+' seções · '+number(r.completed_ufs.length)+' / 27 UFs · '+r.state);
      }
      if (firstFull.status==='fulfilled') {
        const r=firstFull.value;
        put('live-first-full',number(r.completed)+' / '+number(r.planned)+' ZIPs · '+number(r.downloaded_gib)+' GiB · '+number(r.errors)+' erros');
      }
      if (timing.status==='fulfilled') {
        const r=timing.value;
        put('live-timing-first',number(r.turns['1'].processed_sections)+' seções · '+number(r.turns['1'].session_records)+' registros de sessão');
        put('live-timing-second',number(r.turns['2'].processed_sections)+' seções · '+number(r.turns['2'].session_records)+' registros de sessão');
      }
      if (metadata.status==='fulfilled') { const r=metadata.value;put('live-metadata',number(r.processed)+' / '+number(r.planned)+' consultas · '+number(r.confirmed_count)+' confirmações · '+r.state); }
      if (finalization.status==='fulfilled') put('live-finalization',finalization.value.note || finalization.value.state);
      put('live-poll-time', new Date().toLocaleTimeString('pt-BR', {timeZone:'America/Sao_Paulo'}));
    } catch (e) {
      put('live-message', location.protocol === 'file:' ? 'Para acompanhar ao vivo, abra este relatório pelo servidor local: http://127.0.0.1:8765/report.html' : 'Não foi possível consultar o estado local; nova tentativa em 5 segundos.');
    } finally { busy = false; }
  }
  setInterval(tick, 5000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) tick(); });
  tick();
})();
