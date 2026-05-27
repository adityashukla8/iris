// HowItWorks — 6-step pipeline walkthrough section

const STEPS = [
  { n: '01', title: 'AI Generates Response',          body: 'An upstream clinical AI (ORION) responds to a clinician query. The response is intercepted before reaching the end user.' },
  { n: '02', title: 'Parallel Evaluation',             body: '7 specialized evaluators run in parallel via Google ADK — checking dosage, hallucinations, drug interactions, allergies, attribution, context gaps, and surgical phase.' },
  { n: '03', title: 'OTel Tracing to Phoenix',         body: 'Every evaluation result is exported as an OpenInference span to Arize Phoenix Cloud, with per-evaluator scores, severity, confidence, and reasoning chains.' },
  { n: '04', title: 'Pattern Detection via MCP',       body: 'The Pattern Detector agent queries Phoenix through the MCP server — reading recent spans to identify recurring failure clusters across traces.' },
  { n: '05', title: 'Autonomous Prompt Mutation',      body: 'When a failure cluster exceeds the threshold, the Self-Healer agent fetches the current prompt via MCP, logs failing examples to a Phoenix dataset, and generates a candidate patch using TextGrad.' },
  { n: '06', title: 'Validate → Gate → Deploy',        body: 'The candidate prompt is validated against real failing examples. If improvement exceeds the gate threshold, it is deployed as a new Phoenix prompt version — or queued for human approval.' },
];

function HowItWorks() {
  return (
    <section style={{ background: '#F8FAFC', padding: '80px 0' }}>
      <div style={{ maxWidth: 1160, margin: '0 auto', padding: '0 24px' }}>
        {/* Header */}
        <div style={{ marginBottom: 48 }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            fontSize: '0.6875rem', fontWeight: 600, letterSpacing: '0.09em',
            textTransform: 'uppercase', color: '#475569', marginBottom: 14,
          }}>
            <span style={{ width: 18, height: 2, background: '#475569', borderRadius: 2, flexShrink: 0, display: 'inline-block' }}/>
            How It Works
          </div>
          <h2 style={{ fontSize: 'clamp(1.625rem, 3.5vw, 2.375rem)', fontWeight: 700, lineHeight: 1.2, letterSpacing: '-0.02em', color: '#0F172A', marginBottom: 14 }}>
            End-to-end observability loop
          </h2>
          <p style={{ fontSize: '1rem', color: '#475569', lineHeight: 1.75, maxWidth: 560 }}>
            From AI response to deployed fix — every step is traced, evaluated, and stored in Phoenix.
          </p>
        </div>

        {/* Steps grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20 }}>
          {STEPS.map(s => (
            <div key={s.n} style={{
              background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: 14,
              padding: 24, boxShadow: '0 1px 3px rgba(15,23,42,.06)',
            }}>
              <div style={{
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                width: 32, height: 32, borderRadius: 8,
                background: '#F1F5F9', marginBottom: 14,
                fontSize: '0.75rem', fontWeight: 700, fontVariantNumeric: 'tabular-nums',
                color: '#475569',
              }}>
                {s.n}
              </div>
              <div style={{ fontSize: '1rem', fontWeight: 600, color: '#0F172A', marginBottom: 8, lineHeight: 1.3 }}>
                {s.title}
              </div>
              <p style={{ fontSize: '0.875rem', color: '#64748B', lineHeight: 1.65 }}>
                {s.body}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
