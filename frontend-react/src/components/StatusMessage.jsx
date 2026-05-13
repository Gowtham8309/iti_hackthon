export default function StatusMessage({ message, type }) {
  if (!message) return null
  const cls = type === 'error' ? 'errorText' : type === 'success' ? 'successText' : ''
  return <div className={`status ${cls}`}>{message}</div>
}
