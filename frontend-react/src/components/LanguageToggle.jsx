import { useI18n } from '../context/I18nContext'

export default function LanguageToggle() {
  const { language, changeLanguage } = useI18n()

  return (
    <div style={{
      position: 'fixed',
      bottom: 20,
      right: 20,
      zIndex: 1100,
      background: 'rgba(15,23,42,0.85)',
      backdropFilter: 'blur(8px)',
      border: '1px solid rgba(255,255,255,0.12)',
      borderRadius: 999,
      padding: '6px 12px',
      display: 'flex',
      alignItems: 'center',
      gap: 8,
    }}>
      <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', color: '#64748b', textTransform: 'uppercase' }}>
        Lang
      </span>
      <select
        value={language}
        onChange={e => changeLanguage(e.target.value)}
        style={{
          background: 'transparent',
          border: 'none',
          color: '#e2e8f0',
          fontSize: 12,
          fontWeight: 700,
          cursor: 'pointer',
          outline: 'none',
          padding: 0,
        }}
      >
        <option value="en" style={{ background: '#0f172a' }}>EN</option>
        <option value="te" style={{ background: '#0f172a' }}>తె</option>
      </select>
    </div>
  )
}
