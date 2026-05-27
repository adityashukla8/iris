// TraceInspector — two-column Traces tab: list (left) + detail (right)
// Props: traces (array), onSelect (fn), selectedId

const SEV_DOT = { critical: '#E05555', warning: '#C07818', info: '#3B82F6' };
const CTX_BORDER = { critical: '1px solid #E05555', warning: '1px solid #C07818', default: '1px solid #E2E8F0' };

function TraceInspector({ traces = [], selectedId, onSelect }) {
  const [filter, setFilter] = React.useState('');
  const selected = traces.find(t => t.trace_id === selectedId);

  const filtered = filter
    ? traces.filter(t => t.severity === filter)
    : traces;

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Left: trace list */}
      <div style={{
        width: 300, flexShrink: 0, borderRight: '1px solid #E2E8F0',
        background: '#FFFFFF', display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>
        {/* Filter */}
        <div style={{ padding: '10px 12px', borderBottom: '1px solid #E2E8F0', background: '#F8FAFC', flexShrink: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
          <select
            value={filter}
            onChange={e => setFilter(e.target.value)}
            style={{
              flex: 1, fontSize: '0.75rem', fontFamily: 'inherit', color: '#334155',
              border: '1px solid #E2E8F0', background: '#FFFFFF', borderRadius: 5, padding: '4px 7px', cursor: 'pointer',
            }}
          >
            <option value="">All severities</option>
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="info">Info</option>
          </select>
          <span style={{ fontSize: '0.625rem', color: '#94A3B8', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
            {filtered.length} traces
          </span>
        </div>

        {/* Items */}
        <div style={{ overflowY: 'auto', flex: 1 }}>
          {filtered.map(t => (
            <div
              key={t.trace_id}
              onClick={() => onSelect(t.trace_id)}
              style={{
                padding: '10px 12px', borderBottom: '1px solid #F1F5F9', cursor: 'pointer',
                background: t.trace_id === selectedId ? '#EFF6FF' : 'transparent',
                borderLeft: t.trace_id === selectedId ? '3px solid #1D4ED8' : '3px solid transparent',
                paddingLeft: t.trace_id === selectedId ? 9 : 12,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                <div style={{ width: 7, height: 7, borderRadius: '50%', background: SEV_DOT[t.severity] || '#3B82F6', flexShrink: 0 }} />
                <span style={{ fontSize: '0.8125rem', fontWeight: 500, color: '#0F172A', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {(t.query_type || 'general').replace(/_/g, ' ')}
                </span>
                <span style={{ fontSize: '0.6rem', color: '#94A3B8', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
                  {t.timestamp ? t.timestamp.slice(11, 19) : ''}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: '0.6875rem', color: '#64748B', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {t.agent_name || '—'}
                </span>
                <span style={{ fontSize: '0.6rem', color: '#94A3B8', fontVariantNumeric: 'tabular-nums' }}>
                  {(t.evaluations || []).length} evals
                </span>
              </div>
            </div>
          ))}
          {filtered.length === 0 && (
            <div style={{ padding: '32px 16px', textAlign: 'center', color: '#94A3B8', fontSize: '0.8125rem' }}>
              No traces
            </div>
          )}
        </div>
      </div>

      {/* Right: trace detail */}
      <div style={{ flex: 1, overflowY: 'auto', background: '#F8FAFC' }}>
        {selected ? <TraceDetail trace={selected} /> : (
          <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#CBD5E1', gap: 12 }}>
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            <p style={{ fontSize: '0.875rem', color: '#94A3B8' }}>Select a trace to inspect</p>
          </div>
        )}
      </div>
    </div>
  );
}

function TraceDetail({ trace }) {
  const sev = trace.severity || 'info';
  const ctx = trace.retrieved_context || {};
  const evaluations = trace.evaluations || [];

  return (
    <div>
      {/* Sticky header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '12px 20px', background: '#FFFFFF', borderBottom: '1px solid #E2E8F0',
        position: 'sticky', top: 0, zIndex: 10, flexWrap: 'wrap', gap: 8,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{
            display: 'inline-flex', padding: '1px 7px', borderRadius: 4, fontSize: '0.625rem', fontWeight: 600,
            background: sev === 'critical' ? '#FFF1F1' : sev === 'warning' ? '#FFFBEB' : '#EDFBF3',
            color: sev === 'critical' ? '#C43434' : sev === 'warning' ? '#C07818' : '#1A9652',
            border: `1px solid ${sev === 'critical' ? '#FFD4D4' : sev === 'warning' ? '#FEE9A0' : '#D6F5E3'}`,
          }}>
            {sev.toUpperCase()}
          </span>
          <span style={{ fontSize: '0.875rem', fontWeight: 600, color: '#0F172A', textTransform: 'capitalize' }}>
            {(trace.query_type || 'general').replace(/_/g, ' ')}
          </span>
          <span style={{ fontSize: '0.75rem', color: '#94A3B8' }}>·</span>
          <span style={{ fontSize: '0.8125rem', color: '#64748B' }}>{trace.agent_name}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: '0.6875rem', color: '#94A3B8', fontVariantNumeric: 'tabular-nums', background: '#F1F5F9', padding: '2px 8px', borderRadius: 4 }}>
            #{(trace.trace_id || '').slice(0, 8)}
          </span>
          {trace.latency_ms && (
            <span style={{ fontSize: '0.6875rem', color: '#64748B', fontVariantNumeric: 'tabular-nums', background: '#F1F5F9', padding: '2px 8px', borderRadius: 4 }}>
              {trace.latency_ms} ms
            </span>
          )}
        </div>
      </div>

      {/* Case body */}
      <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        {/* I/O + context grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <CaseSection label="Input Prompt">
            <CaseText>{trace.input_prompt || 'No prompt recorded'}</CaseText>
          </CaseSection>
          <CaseSection label="Patient Context">
            <ContextChips ctx={ctx} />
          </CaseSection>
        </div>

        <CaseSection label={`AI Output ${sev !== 'info' ? '— ' + sev.toUpperCase() : ''}`}>
          <CaseText severity={sev}>{trace.output_text || 'No output recorded'}</CaseText>
        </CaseSection>

        {/* Eval cards */}
        {evaluations.length > 0 && (
          <div>
            <div style={{ fontSize: '0.625rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#94A3B8', marginBottom: 10 }}>
              Evaluator Results ({evaluations.length})
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
              {evaluations.map((ev, i) => <EvalCard key={ev.evaluator || i} evaluation={ev} />)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function CaseSection({ label, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ fontSize: '0.625rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#94A3B8' }}>
        {label}
      </div>
      {children}
    </div>
  );
}

function CaseText({ children, severity }) {
  const borderMap = { critical: '1px solid #E05555', warning: '1px solid #C07818' };
  return (
    <div style={{
      fontFamily: 'inherit', fontSize: '0.8125rem', color: '#334155',
      background: '#FFFFFF', border: borderMap[severity] || '1px solid #E2E8F0',
      borderRadius: 7, padding: '12px 14px', whiteSpace: 'pre-wrap',
      wordBreak: 'break-word', lineHeight: 1.5, maxHeight: 160, overflowY: 'auto',
    }}>
      {children}
    </div>
  );
}

function ContextChips({ ctx }) {
  const chips = [];
  if (ctx.patient_id) chips.push(ctx.patient_id);
  if (ctx.age && ctx.weight_kg) chips.push(`${ctx.age}yr · ${ctx.weight_kg} kg`);
  if (ctx.creatinine_clearance) chips.push(`CrCl ${ctx.creatinine_clearance} mL/min`);
  (ctx.medications || []).forEach(m => chips.push(m));
  (ctx.allergies || []).forEach(a => chips.push(`${a} allergy`));
  (ctx.diagnoses || []).forEach(d => chips.push(d));

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
      {chips.map((chip, i) => (
        <span key={i} style={{
          display: 'inline-flex', alignItems: 'center', padding: '3px 8px',
          borderRadius: 4, fontSize: '0.6875rem', fontWeight: 500,
          background: '#F1F5F9', color: '#334155', border: '1px solid #E2E8F0',
        }}>
          {chip}
        </span>
      ))}
      {chips.length === 0 && (
        <span style={{ fontSize: '0.8125rem', color: '#94A3B8' }}>No context</span>
      )}
    </div>
  );
}
