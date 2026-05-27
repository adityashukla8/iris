// StatRow — 6-card KPI row at top of Overview tab
// Props: stats (object with keys: traces, hallucinations, selfHeals, escalations, passRate, criticalRate)

const STAT_CARDS = [
  { key: 'traces',       label: 'Total Traces',      sub: 'this session',          rail: 'neutral' },
  { key: 'hallucinations', label: 'Hallucinations',  sub: 'caught this shift',     rail: 'critical' },
  { key: 'selfHeals',    label: 'Self-Heals',        sub: 'prompt versions deployed', rail: 'warning' },
  { key: 'escalations', label: 'Escalations',        sub: 'low-confidence evals',  rail: 'neutral' },
  { key: 'passRate',     label: 'Pass Rate',         sub: 'info / total',          rail: 'pass' },
  { key: 'criticalRate', label: 'Critical Rate',     sub: 'critical / total',      rail: 'critical' },
];

const RAIL_COLORS = {
  critical: '#E05555',
  warning:  '#C07818',
  pass:     '#1A9652',
  neutral:  '#94A3B8',
};

function StatRow({ stats = {} }) {
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)',
      gap: 12, marginBottom: 16,
    }}>
      {STAT_CARDS.map(card => (
        <StatCard
          key={card.key}
          label={card.label}
          value={stats[card.key] ?? '—'}
          sub={card.sub}
          railColor={RAIL_COLORS[card.rail]}
        />
      ))}
    </div>
  );
}

function StatCard({ label, value, sub, railColor }) {
  return (
    <div style={{
      position: 'relative',
      background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: 10,
      padding: '14px 16px 14px 20px',
      boxShadow: '0 1px 3px rgba(15,23,42,.06), 0 1px 2px rgba(15,23,42,.04)',
      overflow: 'hidden',
    }}>
      {/* 3px left rail via absolutely-positioned element — never border-left */}
      <div style={{
        position: 'absolute', left: 0, top: 12, bottom: 12,
        width: 3, borderRadius: '0 2px 2px 0', background: railColor,
      }} />
      <div style={{
        fontSize: '0.625rem', fontWeight: 600, textTransform: 'uppercase',
        letterSpacing: '0.08em', color: '#94A3B8', marginBottom: 5,
      }}>
        {label}
      </div>
      <div style={{
        fontSize: '1.625rem', fontWeight: 700, lineHeight: 1,
        marginBottom: 3, fontVariantNumeric: 'tabular-nums', color: '#0F172A',
      }}>
        {value}
      </div>
      <div style={{ fontSize: '0.6875rem', color: '#94A3B8' }}>{sub}</div>
    </div>
  );
}
