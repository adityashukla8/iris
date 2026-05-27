// Hero — IRIS marketing homepage hero section
// Props: onDashboardClick, onGithubClick

function Hero({ onDashboardClick, onGithubClick }) {
  return (
    <section style={{ background: '#FFFFFF', padding: '80px 0 72px' }}>
      <div style={{ maxWidth: 1160, margin: '0 auto', padding: '0 24px' }}>
        {/* Eyebrow */}
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          fontSize: '0.6875rem', fontWeight: 600, letterSpacing: '0.09em',
          textTransform: 'uppercase', color: '#475569', marginBottom: 22,
        }}>
          <span style={{ width: 18, height: 2, background: '#475569', borderRadius: 2, flexShrink: 0, display: 'inline-block' }}/>
          Real-time Clinical AI Safety
        </div>

        {/* Headline */}
        <h1 style={{
          fontSize: 'clamp(2rem, 5vw, 3rem)', fontWeight: 800, lineHeight: 1.12,
          letterSpacing: '-0.03em', color: '#0F172A',
          maxWidth: 820, marginBottom: 24,
        }}>
          Clinical AI Shouldn't Operate Without a Supervisor.
        </h1>

        {/* Body */}
        <p style={{
          fontSize: '1.0625rem', color: '#475569', lineHeight: 1.75,
          maxWidth: 600, marginBottom: 36,
        }}>
          IRIS is a multi-agent safety layer that evaluates every AI response in real time, catches hallucinations before they reach the clinician, and autonomously heals failure patterns by rewriting prompts.
        </p>

        {/* CTAs */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 64 }}>
          <button
            onClick={onDashboardClick}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 7,
              padding: '11px 22px', borderRadius: 10,
              fontFamily: 'inherit', fontSize: '0.9375rem', fontWeight: 600,
              background: '#0F172A', color: '#FFFFFF',
              border: 'none', cursor: 'pointer',
            }}
          >
            <IconShield size={16} color="#fff"/> Live Dashboard
          </button>
          <a
            href="https://github.com"
            onClick={onGithubClick}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 7,
              padding: '11px 22px', borderRadius: 10,
              fontFamily: 'inherit', fontSize: '0.9375rem', fontWeight: 600,
              background: '#FFFFFF', color: '#1E293B',
              border: '1.5px solid #E2E8F0', cursor: 'pointer', textDecoration: 'none',
            }}
          >
            <IconGithub size={16}/> View on GitHub
          </a>
        </div>

        {/* Problem stats */}
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 32, maxWidth: 720,
          borderTop: '1px solid #E2E8F0', paddingTop: 40,
        }}>
          {[
            { value: '91.8%', label: 'of LLMs generate dangerous medication errors', source: 'MIT Media Lab, 2025' },
            { value: '83%',   label: 'of ICU medication errors involve polypharmacy', source: 'RxSafeBench 2025'   },
            { value: '$42B',  label: 'annual cost of preventable medication errors',  source: 'FDA PCCP Analysis'  },
          ].map(s => (
            <div key={s.value} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div style={{ fontSize: 'clamp(1.75rem, 4vw, 2.5rem)', fontWeight: 800, lineHeight: 1, fontVariantNumeric: 'tabular-nums', color: '#0F172A' }}>
                {s.value}
              </div>
              <div style={{ fontSize: '0.8125rem', color: '#475569', lineHeight: 1.45 }}>{s.label}</div>
              <div style={{ fontSize: '0.625rem', color: '#94A3B8' }}>{s.source}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function IconShield({ size = 16, color = 'currentColor' }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>;
}
function IconGithub({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>
    </svg>
  );
}
