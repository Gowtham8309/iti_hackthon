export default function KpiCard({ color = 'blue', label, value, sub }) {
  return (
    <div className={`kpi-card ${color}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value ?? '--'}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  )
}
