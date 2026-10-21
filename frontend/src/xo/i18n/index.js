import ui from './ui.json'

export const languages = ui.languages
export const defaultLanguage = ui.default

export function languageInfo(code) {
  return languages.find(l => l.code === code) || languages.find(l => l.code === defaultLanguage)
}

export function isRtl(code) {
  return languageInfo(code).dir === 'rtl'
}

export function t(lang, key, vars = {}) {
  const table = ui.strings[lang] || ui.strings[defaultLanguage]
  const template = table[key] ?? ui.strings[defaultLanguage][key] ?? key
  return Object.entries(vars).reduce((s, [k, v]) => s.split(`{${k}}`).join(String(v)), template)
}

export function formatAed(value, lang) {
  if (value === null || value === undefined || value === '') return ''
  return Math.round(Number(value)).toLocaleString(languageInfo(lang).locale)
}
