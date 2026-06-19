import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import en from './locales/en/common.json'
import es from './locales/es/common.json'

// Single namespace ("common") for now. As the UI grows, split into per-feature
// namespaces (e.g. demos.json, hltv.json) and lazy-load them.
export const resources = {
  en: { common: en },
  es: { common: es },
} as const

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'en',
    supportedLngs: ['en', 'es'],
    defaultNS: 'common',
    interpolation: { escapeValue: false },
  })

export default i18n
