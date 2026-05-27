// EvalCard — single evaluator result card in Trace Inspector
// Props: evaluation ({ evaluator, score, severity, passed, skipped, rationale,
//                       confidence, reasoning_chain, flagged_claims })

const SEV = {
  critical: { border: '#E05555', scoreColor: '#E05555', chipBg: '#FFF1F1', chipBorder: '#FFD4D4', chipText: '#C43434' },
  warning:  { border: '#C07818', scoreColor: '#C07818', chipBg: '#FFFBEB', chipBorder: '#FEE9A0', chipText: '#C07818' },
  info:     { border: '#1A9652', scoreColor: '#1A9652', chipBg: '#EDFBF3', chipBorder: '#D6F5E3', chipText: '#1A9652' },
  skipped:  { border: '#E2E8F0', scoreColor: '#94A3B8', chipBg: '#F1F5F9', chipBorder: '#E2E8F0', chipText: '#475569' },
};

function EvalCard({ evaluation = {} }) {
  const [open, setOpen] = React.useState(false);
  const {
    evaluator = 'unknown',
    score,
    severity = 'info',
    skipped = false,
    rationale = '',
    confidence = 1.0,
    reasoning_chain = [],
    flagged_claims = [],
  } = evaluation;

  const sev = skipped ? 'skipped' : severity;
  const s = SEV[sev] || SEV.info;
  const confLow = confidence < 0.6;

  return (
    <div style={{
      background: '#FFFFFF', border: '1px solid #E2E8F0',
      borderTop: `3px solid ${s.border}`, borderRadius: 8,
      padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8,
      overflow: 'hidden',
    }}>
      {/* Name */}
      <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#0F172A', wordBreak: 'break-word' }}>
        {evaluator}
      </div>

      {/* Score + severity chip */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: '1.375rem', fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: s.scoreColor }}>
          {skipped ? '—' : score != null ? score.toFixed(1) : '—'}
        </span>
        <span style={{
          display: 'inline-flex', alignItems: 'center', padding: '1px 7px',
          background: s.chipBg, color: s.chipText, border: `1px solid ${s.chipBorder}`,
          borderRadius: 4, fontSize: '0.625rem', fontWeight: 600,
        }}>
          {sev.toUpperCase()}
        </span>
      </div>

      {/* Rationale */}
      {rationale && (
        <div style={{ fontSize: '0.75rem', color: '#64748B', lineHeight: 1.5, wordBreak: 'break-word' }}>
          {rationale}
        </div>
      )}

      {/* Flagged claims */}
      {flagged_claims.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {flagged_claims.map((claim, i) => (
            <span key={i} style={{
              display: 'inline-flex', padding: '2px 7px', borderRadius: 4,
              fontSize: '0.6875rem', color: '#0F172A',
              background: 'transparent', border: '1px solid #E05555', wordBreak: 'break-word',
            }}>
              {claim}
            </span>
          ))}
        </div>
      )}

      {/* Reasoning chain (collapsible) */}
      {reasoning_chain.length > 0 && (
        <details onToggle={e => setOpen(e.target.open)} style={{ marginTop: 2 }}>
          <summary style={{ fontSize: '0.6875rem', fontWeight: 500, color: '#94A3B8', cursor: 'pointer', userSelect: 'none', listStyle: 'none' }}>
            {open ? '− ' : '+ '}Reasoning chain ({reasoning_chain.length} steps)
          </summary>
          <ol style={{ margin: '6px 0 0 16px', fontSize: '0.6875rem', color: '#64748B', lineHeight: 1.7 }}>
            {reasoning_chain.map((step, i) => <li key={i}>{step}</li>)}
          </ol>
        </details>
      )}

      {/* Confidence bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: '0.5625rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#94A3B8', whiteSpace: 'nowrap' }}>
          Conf
        </span>
        <div style={{ flex: 1, height: 3, background: '#E2E8F0', borderRadius: 2 }}>
          <div style={{ width: `${confidence * 100}%`, height: '100%', background: confLow ? '#E05555' : '#1A9652', borderRadius: 2 }} />
        </div>
        <span style={{ fontSize: '0.625rem', fontVariantNumeric: 'tabular-nums', color: confLow ? '#C43434' : '#94A3B8' }}>
          {confidence.toFixed(2)}
        </span>
      </div>
    </div>
  );
}

// EvalCardGrid — 4-column grid of EvalCards
function EvalCardGrid({ evaluations = [] }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
      {evaluations.map((ev, i) => <EvalCard key={ev.evaluator || i} evaluation={ev} />)}
    </div>
  );
}
