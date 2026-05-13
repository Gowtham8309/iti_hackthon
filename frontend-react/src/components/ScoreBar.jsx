function scoreColor(score) {
  if (score >= 75) return 'green'
  if (score >= 50) return 'orange'
  return 'red'
}

export default function ScoreBar({ label, score }) {
  const pct = Math.max(4, Math.min(100, Math.round(Number(score) || 0)))
  const cls = scoreColor(pct)

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '2px 0', fontSize: 12 }}>
      <span style={{ width: 72, fontSize: 11, color: '#64748b' }}>{label}</span>
      <div style={{ flex: 1, height: 6, background: '#e2e8f0', borderRadius: 4, overflow: 'hidden' }}>
        <div
          style={{
            height: '100%',
            borderRadius: 4,
            width: `${pct}%`,
            transition: 'width .3s',
            background: cls === 'green' ? '#22c55e' : cls === 'orange' ? '#f59e0b' : '#ef4444',
          }}
        />
      </div>
      <span style={{ fontSize: 11, fontWeight: 700, width: 28 }}>{pct}</span>
    </div>
  )
}
