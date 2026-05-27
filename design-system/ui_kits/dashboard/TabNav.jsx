// TabNav — tab strip below topbar
// Props: tabs (array of {id, label}), activeTab, onChange
function TabNav({ tabs, activeTab, onChange }) {
  return (
    <div style={{
      background: '#FFFFFF', borderBottom: '1px solid #E2E8F0',
      display: 'flex', alignItems: 'stretch',
      padding: '0 24px', height: 40, flexShrink: 0,
    }}>
      {tabs.map(tab => {
        const active = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            style={{
              padding: '0 18px', height: 40,
              fontFamily: 'inherit', fontSize: '0.8125rem',
              fontWeight: active ? 600 : 500,
              color: active ? '#1D4ED8' : '#94A3B8',   // accent ONLY for active
              background: 'none', border: 'none',
              borderBottom: active ? '2px solid #1D4ED8' : '2px solid transparent',
              cursor: 'pointer', whiteSpace: 'nowrap',
              transition: 'color .15s, border-color .15s',
            }}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
