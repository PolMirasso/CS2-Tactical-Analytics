import { useTranslation } from 'react-i18next'

export function LanguageSwitcher() {
  const { i18n } = useTranslation()
  return (
    <select
      className="m-0 w-auto px-2 py-1"
      value={i18n.resolvedLanguage}
      onChange={(e) => void i18n.changeLanguage(e.target.value)}
      aria-label="Language"
    >
      <option value="en">EN</option>
      <option value="es">ES</option>
    </select>
  )
}
