// HealingPanel — candidates + history sections for Healing tab
// Props: candidates (array), history (array), onApprove (fn), onReject (fn)

function HealingPanel({ candidates = [], history = [], onApprove, onReject }) {
  return (
    <div style={{ padding: '18px 24px', display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Candidates */}
      <div style={{
        background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: 10,
        boxShadow: '0 1px 3px rgba(15,23,42,.06)', overflow: 'hidden',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 16px', borderBottom: '1px solid #E2E8F0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: '0.8125rem', fontWeight: 600, color: '#0F172A' }}>
            <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#C07818', flexShrink: 0 }} />
            Pending Approval
          </div>
          <span style={{ fontSize: '0.6875rem', color: '#94A3B8', fontVariantNumeric: 'tabular-nums' }}>
            {candidates.length} candidate{candidates.length !== 1 ? 's' : ''}
          </span>
        </div>
        {candidates.length === 0 ? (
          <div style={{ padding: '28px 16px', textAlign: 'center', color: '#94A3B8', fontSize: '0.8125rem' }}>
            No pending candidates
          </div>
        ) : (
          candidates.map(c => (
            <HealingCandidate key={c.candidate_id} candidate={c} onApprove={onApprove} onReject={onReject} />
          ))
        )}
      </div>

      {/* History */}
      <div style={{
        background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: 10,
        boxShadow: '0 1px 3px rgba(15,23,42,.06)', overflow: 'hidden',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 16px', borderBottom: '1px solid #E2E8F0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: '0.8125rem', fontWeight: 600, color: '#0F172A' }}>
            <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#1A9652', flexShrink: 0 }} />
            Healing History
          </div>
          <span style={{ fontSize: '0.6875rem', color: '#94A3B8', fontVariantNumeric: 'tabular-nums' }}>
            {history.length} entries
          </span>
        </div>
        {history.length === 0 ? (
          <div style={{ padding: '28px 16px', textAlign: 'center', color: '#94A3B8', fontSize: '0.8125rem' }}>
            No healing history yet
          </div>
        ) : (
          history.map((h, i) => <HistoryItem key={h.candidate_id || i} item={h} />)
        )}
      </div>
    </div>
  );
}

function HealingCandidate({ candidate, onApprove, onReject }) {
  const c = candidate;
  const improvement = c.improvement_score || 0;
  const deltaPos = improvement >= 0;

  return (
    <div style={{ padding: '13px 16px', borderBottom: '1px solid #F1F5F9' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 3 }}>
        <span style={{ fontSize: '0.875rem', fontWeight: 600, color: '#0F172A' }}>
          {(c.diagnosis?.current_prompt_name) || 'prompt'}
        </span>
        <span style={{
          display: 'inline-flex', padding: '1px 7px', borderRadius: 4, fontSize: '0.625rem', fontWeight: 600,
          background: '#FFFBEB', color: '#C07818', border: '1px solid #FEE9A0',
        }}>
          PENDING
        </span>
      </div>
      <div style={{ fontSize: '0.6875rem', color: '#94A3B8', fontVariantNumeric: 'tabular-nums', marginBottom: 8 }}>
        {(c.diagnosis?.query_type || '').replace(/_/g, ' ')} · {c.diagnosis?.hallucination_rate != null ? `${(c.diagnosis.hallucination_rate * 100).toFixed(0)}% failure rate` : ''}
      </div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 8 }}>
        <span style={{ fontSize: '0.6875rem', color: '#64748B', fontVariantNumeric: 'tabular-nums' }}>
          Before: <strong>{(c.validation_score_before ?? 0).toFixed(1)}</strong>
        </span>
        <span style={{ fontSize: '0.6875rem', color: '#64748B', fontVariantNumeric: 'tabular-nums' }}>
          After: <strong>{(c.validation_score_after ?? 0).toFixed(1)}</strong>
        </span>
        <span style={{ fontSize: '0.6875rem', fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: deltaPos ? '#1A9652' : '#E05555' }}>
          {deltaPos ? '+' : ''}{improvement.toFixed(2)}
        </span>
      </div>
      <div style={{ fontSize: '0.75rem', color: '#64748B', marginBottom: 8 }}>
        {c.mutation_rationale || c.injected_constraint || ''}
      </div>
      <div style={{ display: 'flex', gap: 7 }}>
        <button
          onClick={() => onApprove?.(c.candidate_id)}
          style={{ padding: '4px 11px', borderRadius: 5, fontSize: '0.75rem', fontWeight: 600, background: '#1A9652', color: '#FFFFFF', border: 'none', fontFamily: 'inherit', cursor: 'pointer' }}
        >
          Approve
        </button>
        <button
          onClick={() => onReject?.(c.candidate_id)}
          style={{ padding: '4px 11px', borderRadius: 5, fontSize: '0.75rem', fontWeight: 600, background: '#FFFFFF', color: '#E05555', border: '1px solid #FFD4D4', fontFamily: 'inherit', cursor: 'pointer' }}
        >
          Reject
        </button>
      </div>
    </div>
  );
}

function HistoryItem({ item }) {
  const [open, setOpen] = React.useState(false);
  const imp = item.improvement_score || 0;
  const pos = imp >= 0;

  return (
    <div style={{ borderBottom: '1px solid #F1F5F9' }}>
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '11px 16px',
          cursor: 'pointer', background: open ? '#F8FAFC' : 'transparent',
        }}
      >
        <span style={{
          display: 'inline-flex', padding: '1px 7px', borderRadius: 4, fontSize: '0.625rem', fontWeight: 700,
          fontVariantNumeric: 'tabular-nums',
          background: pos ? '#EDFBF3' : '#FFF1F1',
          color: pos ? '#1A9652' : '#C43434',
          border: `1px solid ${pos ? '#D6F5E3' : '#FFD4D4'}`,
        }}>
          {pos ? '+' : ''}{imp.toFixed(2)}
        </span>
        <span style={{ flex: 1, fontSize: '0.75rem', color: '#64748B', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {(item.diagnosis?.current_prompt_name || 'prompt')} · {item.status || ''} · {item.deployed_at ? item.deployed_at.slice(0, 16).replace('T', ' ') : ''}
        </span>
        <span style={{ fontSize: '0.7rem', color: '#94A3B8', transition: 'transform .15s', transform: open ? 'rotate(90deg)' : 'none' }}>›</span>
      </div>
      {open && (
        <div style={{ padding: '0 16px 14px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <div style={{ fontSize: '0.625rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#94A3B8', marginBottom: 6 }}>Before</div>
              <pre style={{
                fontFamily: 'inherit', fontSize: '0.6875rem', fontVariantNumeric: 'tabular-nums',
                color: '#475569', background: '#F8FAFC', border: '1px solid #E2E8F0',
                borderRadius: 6, padding: 10, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                maxHeight: 160, overflowY: 'auto',
              }}>
                {item.old_prompt_text || '—'}
              </pre>
            </div>
            <div>
              <div style={{ fontSize: '0.625rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#94A3B8', marginBottom: 6 }}>After</div>
              <pre style={{
                fontFamily: 'inherit', fontSize: '0.6875rem', fontVariantNumeric: 'tabular-nums',
                color: '#475569', background: '#F8FAFC', border: '1px solid #E2E8F0',
                borderRadius: 6, padding: 10, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                maxHeight: 160, overflowY: 'auto',
              }}>
                {item.new_prompt_text || '—'}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
