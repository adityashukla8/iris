// AnalyticsGrid — 3-column analytics row: EvalHeatmap | SeverityTimeline | QueryTypeBreakdown
// Props: analytics (object from GET /analytics)

function AnalyticsGrid({ analytics = {} }) {
  const { evaluator_stats = {}, severity_timeline = [], query_type_breakdown = {} } = analytics;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14, marginBottom: 14 }}>
      <EvalHeatmap stats={evaluator_stats} />
      <SeverityTimeline buckets={severity_timeline} />
      <QueryTypeBreakdown breakdown={query_type_breakdown} />
    </div>
  );
}

// ── Evaluator Heatmap ────────────────────────────────────────────────────────

function EvalHeatmap({ stats }) {
  const rows = Object.entries(stats);
  return (
    <AnalyticsPanel title="Evaluator Heatmap" dotColor="#E05555">
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
        <thead>
          <tr>
            {['Evaluator', 'Runs', 'Fail', 'Avg', 'Crit'].map(h => (
              <th key={h} style={{
                padding: '7px 12px', fontSize: '0.625rem', fontWeight: 600,
                textTransform: 'uppercase', letterSpacing: '0.08em', color: '#94A3B8',
                borderBottom: '1px solid #E2E8F0', background: '#F8FAFC',
                textAlign: h === 'Evaluator' ? 'left' : 'right',
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td colSpan={5} style={{ padding: '16px 12px', textAlign: 'center', color: '#94A3B8', fontSize: '0.8125rem' }}>No data</td></tr>
          )}
          {rows.map(([name, s]) => {
            const failRate = s.runs > 0 ? s.failures / s.runs : 0;
            const rowBg = failRate > 0.4 ? '#FFF5F5' : failRate > 0.2 ? '#FFFCF0' : 'transparent';
            return (
              <tr key={name} style={{ background: rowBg }}>
                <td style={{ padding: '7px 12px', borderBottom: '1px solid #F1F5F9', fontSize: '0.75rem', fontWeight: 500, color: '#334155' }}>
                  {name.replace(/_/g, '_​')}
                </td>
                <td style={{ padding: '7px 12px', borderBottom: '1px solid #F1F5F9', textAlign: 'right', fontVariantNumeric: 'tabular-nums', fontSize: '0.75rem', color: '#64748B' }}>{s.runs}</td>
                <td style={{ padding: '7px 12px', borderBottom: '1px solid #F1F5F9', textAlign: 'right', fontVariantNumeric: 'tabular-nums', fontSize: '0.75rem', color: s.failures > 0 ? '#C43434' : '#64748B', fontWeight: s.failures > 0 ? 600 : 400 }}>{s.failures}</td>
                <td style={{ padding: '7px 12px', borderBottom: '1px solid #F1F5F9', textAlign: 'right', fontVariantNumeric: 'tabular-nums', fontSize: '0.75rem', color: '#64748B' }}>
                  {s.avg_score != null ? s.avg_score.toFixed(1) : '—'}
                </td>
                <td style={{ padding: '7px 12px', borderBottom: '1px solid #F1F5F9', textAlign: 'right', fontVariantNumeric: 'tabular-nums', fontSize: '0.75rem', color: s.critical_count > 0 ? '#C43434' : '#64748B' }}>{s.critical_count}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </AnalyticsPanel>
  );
}

// ── Severity Timeline (SVG line chart) ──────────────────────────────────────

const SERIES = [
  { key: 'info',    color: '#3B82F6', label: 'info' },
  { key: 'warning', color: '#C07818', label: 'warning' },
  { key: 'critical',color: '#E05555', label: 'critical' },
];

function SeverityTimeline({ buckets }) {
  if (!buckets || buckets.length === 0) {
    return (
      <AnalyticsPanel title="Severity Timeline" dotColor="#3B82F6" meta="by minute">
        <div style={{ padding: '32px 16px', textAlign: 'center', color: '#94A3B8', fontSize: '0.8125rem' }}>No data</div>
      </AnalyticsPanel>
    );
  }

  const W = 340, H = 120, PL = 8, PR = 8, PT = 12, PB = 24;
  const cW = W - PL - PR, cH = H - PT - PB;
  const n = buckets.length;
  const maxVal = Math.max(1, ...buckets.flatMap(b => SERIES.map(s => b[s.key] || 0)));

  const xOf = i => PL + (i / (n - 1 || 1)) * cW;
  const yOf = v => PT + cH - (v / maxVal) * cH;

  function smoothPath(pts) {
    if (pts.length < 2) return '';
    let d = `M ${pts[0].x},${pts[0].y}`;
    for (let i = 1; i < pts.length; i++) {
      const dx = (pts[i].x - pts[i - 1].x) * 0.42;
      d += ` C ${pts[i-1].x + dx},${pts[i-1].y} ${pts[i].x - dx},${pts[i].y} ${pts[i].x},${pts[i].y}`;
    }
    return d;
  }

  return (
    <AnalyticsPanel title="Severity Timeline" dotColor="#3B82F6" meta="by minute · last 12 min">
      <div style={{ padding: '8px 12px 4px' }}>
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }}>
          {/* Grid */}
          <line x1={PL} y1={PT} x2={PL} y2={PT + cH} stroke="#E2E8F0" strokeWidth={1}/>
          <line x1={W - PR} y1={PT} x2={W - PR} y2={PT + cH} stroke="#E2E8F0" strokeWidth={1}/>
          <line x1={PL} y1={PT + cH} x2={W - PR} y2={PT + cH} stroke="#E2E8F0" strokeWidth={1}/>

          {SERIES.map(({ key, color }) => {
            const pts = buckets.map((b, i) => ({ x: xOf(i), y: yOf(b[key] || 0) }));
            const path = smoothPath(pts);
            return (
              <g key={key}>
                <path d={path} fill="none" stroke={color} strokeWidth={key === 'info' ? 2 : 1.5} strokeLinecap="round"
                  strokeDasharray={key !== 'info' ? '4 2' : undefined}/>
                {pts.map((p, i) => {
                  const v = buckets[i][key] || 0;
                  if (v === 0 && key !== 'info') return null;
                  return (
                    <g key={i}>
                      <circle cx={p.x} cy={p.y} r={3} fill={color}/>
                      {v > 0 && (
                        <text x={p.x} y={p.y - 6} textAnchor="middle"
                          style={{ fontFamily: 'inherit', fontSize: 7, fill: color, fontVariantNumeric: 'tabular-nums' }}>
                          {v}
                        </text>
                      )}
                    </g>
                  );
                })}
              </g>
            );
          })}

          {/* X labels: first, mid, last */}
          {[0, Math.floor((n-1)/2), n-1].filter((v,i,a) => a.indexOf(v) === i).map(i => (
            <text key={i} x={xOf(i)} y={H - 2} textAnchor="middle"
              style={{ fontFamily: 'inherit', fontSize: 7, fill: '#94A3B8' }}>
              {(buckets[i]?.ts || '').slice(0, 5)}
            </text>
          ))}
        </svg>
        <div style={{ display: 'flex', gap: 12, padding: '4px 0' }}>
          {SERIES.map(s => (
            <div key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.6875rem', color: '#64748B' }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: s.color }} />
              {s.label}
            </div>
          ))}
        </div>
      </div>
    </AnalyticsPanel>
  );
}

// ── Query Type Breakdown ─────────────────────────────────────────────────────

function QueryTypeBreakdown({ breakdown }) {
  const rows = Object.entries(breakdown);
  return (
    <AnalyticsPanel title="Query Type Breakdown" dotColor="#C07818">
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
        <thead>
          <tr>
            {['Type', 'Count', 'Fail %'].map(h => (
              <th key={h} style={{
                padding: '7px 12px', fontSize: '0.625rem', fontWeight: 600,
                textTransform: 'uppercase', letterSpacing: '0.08em', color: '#94A3B8',
                borderBottom: '1px solid #E2E8F0', background: '#F8FAFC',
                textAlign: h === 'Type' ? 'left' : 'right',
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td colSpan={3} style={{ padding: '16px 12px', textAlign: 'center', color: '#94A3B8', fontSize: '0.8125rem' }}>No data</td></tr>
          )}
          {rows.map(([qt, v]) => (
            <tr key={qt}>
              <td style={{ padding: '7px 12px', borderBottom: '1px solid #F1F5F9', fontSize: '0.75rem', fontWeight: 500, color: '#334155' }}>
                {qt.replace(/_/g, ' ')}
              </td>
              <td style={{ padding: '7px 12px', borderBottom: '1px solid #F1F5F9', textAlign: 'right', fontVariantNumeric: 'tabular-nums', fontSize: '0.75rem', color: '#64748B' }}>{v.count}</td>
              <td style={{ padding: '7px 12px', borderBottom: '1px solid #F1F5F9', textAlign: 'right', fontVariantNumeric: 'tabular-nums', fontSize: '0.75rem', color: v.failure_rate > 0.3 ? '#C43434' : '#64748B' }}>
                <div style={{ display: 'inline-block', height: 3, width: `${v.failure_rate * 60}px`, background: '#E05555', borderRadius: 2, verticalAlign: 'middle', marginRight: 4, opacity: 0.6 }}/>
                {(v.failure_rate * 100).toFixed(0)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </AnalyticsPanel>
  );
}

// Shared panel wrapper
function AnalyticsPanel({ title, dotColor = '#94A3B8', meta, children }) {
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
        {meta && <span style={{ fontSize: '0.6875rem', color: '#94A3B8' }}>{meta}</span>}
      </div>
      {children}
    </div>
  );
}
