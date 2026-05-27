// AlertFeed — live SSE alert stream panel
// Props: alerts (array), maxHeight

const SEV_STYLES = {
  critical: { bg: '#FFF1F1', border: '#FFD4D4', color: '#E05555' },
  warning:  { bg: '#FFFBEB', border: '#FEE9A0', color: '#C07818' },
  info:     { bg: '#EDFBF3', border: '#D6F5E3', color: '#1A9652' },
};

function AlertFeed({ alerts = [], maxHeight = 300 }) {
  const listRef = React.useRef(null);

  // Auto-scroll to bottom on new alerts
  React.useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [alerts.length]);

  return (
    <Panel
      title="Live Alert Feed"
      dotColor="#1A9652"
      meta={alerts.length > 0 ? `${alerts.length} events` : 'waiting…'}
    >
      <div ref={listRef} style={{ overflowY: 'auto', maxHeight }}>
        {alerts.length === 0 ? (
          <EmptyState icon={<IconBell />} text="Waiting for events…" />
        ) : (
          alerts.map((alert, i) => (
            <AlertItem key={alert.id || i} alert={alert} />
          ))
        )}
      </div>
    </Panel>
  );
}

function AlertItem({ alert }) {
  const sev = alert.severity || 'info';
  const s = SEV_STYLES[sev] || SEV_STYLES.info;
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 10,
      padding: '10px 16px', borderBottom: '1px solid #F1F5F9',
    }}>
      <div style={{
        width: 24, height: 24, borderRadius: 5, flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: s.bg, border: `1px solid ${s.border}`, color: s.color,
      }}>
        {sev === 'critical' ? <IconShield size={11} /> : sev === 'warning' ? <IconTriangle size={11} /> : <IconCheck size={11} />}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 1 }}>
          <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#0F172A' }}>
            {alert.agent_name || 'ORION'}
          </span>
          <span style={{ fontSize: '0.6rem', color: '#94A3B8', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
            {alert.time || ''}
          </span>
        </div>
        <div style={{ fontSize: '0.75rem', color: '#64748B', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {alert.message || ''}
        </div>
        {alert.badges && (
          <div style={{ display: 'flex', gap: 4, marginTop: 4, flexWrap: 'wrap' }}>
            {alert.badges.map((b, i) => <SevChip key={i} sev={b.sev} label={b.label} />)}
          </div>
        )}
      </div>
    </div>
  );
}

// Shared sub-components (also used by EvalCard, TraceInspector)
function Panel({ title, dotColor = '#94A3B8', meta, children }) {
  return (
    <div style={{
      background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: 10,
      boxShadow: '0 1px 3px rgba(15,23,42,.06)', overflow: 'hidden',
      display: 'flex', flexDirection: 'column',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 16px', borderBottom: '1px solid #E2E8F0', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: '0.8125rem', fontWeight: 600, color: '#0F172A' }}>
          <div style={{ width: 7, height: 7, borderRadius: '50%', background: dotColor, flexShrink: 0 }} />
          {title}
        </div>
        {meta && <span style={{ fontSize: '0.6875rem', color: '#94A3B8', fontVariantNumeric: 'tabular-nums' }}>{meta}</span>}
      </div>
      {children}
    </div>
  );
}

function SevChip({ sev, label }) {
  const s = SEV_STYLES[sev] || SEV_STYLES.info;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', padding: '1px 7px',
      background: s.bg, color: sev === 'critical' ? '#C43434' : sev === 'warning' ? '#C07818' : '#1A9652',
      border: `1px solid ${s.border}`, borderRadius: 4,
      fontSize: '0.625rem', fontWeight: 600,
    }}>
      {label || sev.toUpperCase()}
    </span>
  );
}

function EmptyState({ icon, text }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      gap: 6, padding: '32px 16px', color: '#94A3B8', textAlign: 'center',
    }}>
      <span style={{ color: '#CBD5E1' }}>{icon}</span>
      <p style={{ fontSize: '0.8125rem' }}>{text}</p>
    </div>
  );
}

function IconShield({ size = 14 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>;
}
function IconTriangle({ size = 14 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>;
}
function IconCheck({ size = 14 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>;
}
function IconBell({ size = 20 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>;
}
