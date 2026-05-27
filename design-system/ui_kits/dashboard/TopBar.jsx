// TopBar — IRIS dashboard header
// Props: onRefresh, onScan, lastRefreshed, scanLoading
function TopBar({ onRefresh, onScan, lastRefreshed, scanLoading }) {
  return (
    <div style={{
      background: '#FFFFFF', borderBottom: '1px solid #E2E8F0',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 24px', height: 58, boxShadow: '0 1px 2px rgba(15,23,42,.04)',
      flexShrink: 0,
    }}>
      {/* Left: logo + page title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 28, height: 28, background: '#0F172A', borderRadius: 6,
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
          }}>
            <IrisMark size={18} />
          </div>
          <span style={{ fontSize: '0.9375rem', fontWeight: 700, color: '#0F172A' }}>IRIS</span>
        </div>
        <div style={{ width: 1, height: 18, background: '#E2E8F0' }} />
        <span style={{ fontSize: '0.8125rem', fontWeight: 500, color: '#64748B' }}>Shift Commander</span>
      </div>

      {/* Right: status + buttons */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: '0.75rem', fontWeight: 500, color: '#1A9652' }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#1A9652', display: 'inline-block' }} />
          Live
        </div>
        {lastRefreshed && (
          <span style={{ fontSize: '0.7rem', color: '#94A3B8', fontVariantNumeric: 'tabular-nums' }}>
            {lastRefreshed}
          </span>
        )}
        <button onClick={onRefresh} style={{
          display: 'inline-flex', alignItems: 'center', gap: 5,
          padding: '5px 12px', borderRadius: 6, fontSize: '0.8125rem', fontWeight: 600,
          background: '#FFFFFF', color: '#475569', border: '1px solid #E2E8F0', cursor: 'pointer',
        }}>
          <IconRefresh size={12} /> Refresh
        </button>
        <button onClick={onScan} disabled={scanLoading} style={{
          display: 'inline-flex', alignItems: 'center', gap: 5,
          padding: '5px 12px', borderRadius: 6, fontSize: '0.8125rem', fontWeight: 600,
          background: '#0F172A', color: '#FFFFFF', border: 'none', cursor: scanLoading ? 'not-allowed' : 'pointer',
          opacity: scanLoading ? 0.45 : 1,
        }}>
          <IconCpu size={12} /> {scanLoading ? 'Scanning…' : 'Scan'}
        </button>
        <a href="/" style={{
          display: 'inline-flex', alignItems: 'center', gap: 5,
          padding: '5px 12px', borderRadius: 6, fontSize: '0.8125rem', fontWeight: 600,
          background: '#FFFFFF', color: '#475569', border: '1px solid #E2E8F0',
        }}>
          Home
        </a>
      </div>
    </div>
  );
}

// Inline micro-icons (no external dependency)
function IrisMark({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none">
      <circle cx="20" cy="20" r="11" stroke="#fff" strokeWidth="1.5" strokeDasharray="17 52.83" strokeDashoffset="-4" strokeLinecap="round"/>
      <circle cx="20" cy="20" r="7.5" stroke="#fff" strokeWidth="1.5" strokeDasharray="12 47.12" strokeDashoffset="-2.5" strokeLinecap="round"/>
      <circle cx="20" cy="20" r="2.5" fill="#fff"/>
    </svg>
  );
}
function IconRefresh({ size = 14, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
    </svg>
  );
}
function IconCpu({ size = 14, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/>
      <line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/>
      <line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/>
      <line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/>
      <line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>
    </svg>
  );
}
