// AgentGrid — 6 IRIS agent cards section

const AGENTS = [
  {
    name: 'Supervisor',
    role: 'Coordinator',
    desc: 'Receives every AI response, dispatches evaluation tools in parallel, aggregates results, and escalates to healing when failure patterns emerge.',
    tags: ['Google ADK', 'Orchestrator'],
    dotColor: '#1A9652',
  },
  {
    name: 'Safety Evaluator',
    role: 'Evaluator',
    desc: 'Runs 7 parallel Gemini-powered evaluation tools — dosage, hallucination, drug interaction, allergy, attribution, context gap, surgical phase.',
    tags: ['Gemini 2.0 Flash', '7 tools'],
    dotColor: '#E05555',
  },
  {
    name: 'Pattern Detector',
    role: 'Observer',
    desc: 'Queries Phoenix via MCP to identify recurring failure clusters across recent spans. Triggers self-healing when hallucination rate exceeds threshold.',
    tags: ['MCP', 'Phoenix spans'],
    dotColor: '#C07818',
  },
  {
    name: 'Self-Healer',
    role: 'Healer',
    desc: 'Fetches the current failing prompt from Phoenix, logs examples to a dataset via MCP, and produces a HealingDiagnosis for the Python mutation pipeline.',
    tags: ['MCP', 'TextGrad'],
    dotColor: '#3B82F6',
  },
  {
    name: 'Alert Dispatcher',
    role: 'Notifier',
    desc: 'Translates evaluation results into structured alerts streamed to the dashboard via Server-Sent Events. Critical alerts trigger immediate notification.',
    tags: ['SSE', 'Real-time'],
    dotColor: '#94A3B8',
  },
  {
    name: 'MCP Probe',
    role: 'Debug',
    desc: 'Interactive Phoenix MCP query agent for live demonstrations. Queries spans, traces, datasets, and prompts on demand through the dashboard chat interface.',
    tags: ['MCP', 'Interactive'],
    dotColor: '#475569',
  },
];

function AgentGrid() {
  return (
    <section style={{ background: '#FFFFFF', padding: '80px 0' }}>
      <div style={{ maxWidth: 1160, margin: '0 auto', padding: '0 24px' }}>
        {/* Header */}
        <div style={{ marginBottom: 48 }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            fontSize: '0.6875rem', fontWeight: 600, letterSpacing: '0.09em',
            textTransform: 'uppercase', color: '#475569', marginBottom: 14,
          }}>
            <span style={{ width: 18, height: 2, background: '#475569', borderRadius: 2, flexShrink: 0, display: 'inline-block' }}/>
            Agent Architecture
          </div>
          <h2 style={{ fontSize: 'clamp(1.625rem, 3.5vw, 2.375rem)', fontWeight: 700, lineHeight: 1.2, letterSpacing: '-0.02em', color: '#0F172A', marginBottom: 14 }}>
            Six agents. One safety loop.
          </h2>
          <p style={{ fontSize: '1rem', color: '#475569', lineHeight: 1.75, maxWidth: 560 }}>
            Each agent has a narrow, auditable responsibility — no monolith, no black box.
          </p>
        </div>

        {/* Cards grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
          {AGENTS.map(a => (
            <AgentCard key={a.name} agent={a} />
          ))}
        </div>
      </div>
    </section>
  );
}

function AgentCard({ agent }) {
  return (
    <div style={{
      background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: 14,
      padding: '20px', boxShadow: '0 1px 3px rgba(15,23,42,.06)',
      display: 'flex', flexDirection: 'column', gap: 12,
      transition: 'box-shadow .15s',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: agent.dotColor, flexShrink: 0 }} />
          <span style={{ fontSize: '1rem', fontWeight: 600, color: '#0F172A' }}>{agent.name}</span>
        </div>
        <span style={{
          display: 'inline-flex', padding: '2px 9px', borderRadius: 20,
          fontSize: '0.6875rem', fontWeight: 500,
          background: '#F1F5F9', color: '#475569', border: '1px solid #E2E8F0',
        }}>
          {agent.role}
        </span>
      </div>

      {/* Description */}
      <p style={{ fontSize: '0.875rem', color: '#64748B', lineHeight: 1.65, flex: 1 }}>
        {agent.desc}
      </p>

      {/* Tags */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {agent.tags.map(t => (
          <span key={t} style={{
            display: 'inline-flex', padding: '2px 8px', borderRadius: 4,
            fontSize: '0.6875rem', fontWeight: 500,
            background: '#F8FAFC', color: '#334155', border: '1px solid #E2E8F0',
          }}>
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}
