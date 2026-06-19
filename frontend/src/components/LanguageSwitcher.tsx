import { useTranslation } from 'react-i18next'

export function LanguageSwitcher() {
  const { i18n } = useTranslation()
  return (
    <select
      className="lang-switch"
      value={i18n.resolvedLanguage}
      onChange={(e) => void i18n.changeLanguage(e.target.value)}
      aria-label="Language"
    >
      <option value="en">EN</option>
      <option value="es">ES</option>
    </select>
  )
}
