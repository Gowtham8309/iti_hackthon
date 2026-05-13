export default function MetricCard({ color = '', label, value, sub }) {
  return (
    <div className={`metric-card${color ? ' ' + color : ''}`}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value ?? '--'}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  )
}
