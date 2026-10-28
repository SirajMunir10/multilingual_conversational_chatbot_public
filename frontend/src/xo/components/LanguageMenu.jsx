'use client'
import { forwardRef, useEffect, useRef, useState } from 'react'
import XoIcon from './XoIcon'
import { languages } from '../i18n'

// Lowercase without accents, so "turkce" finds Türkçe and "русс" finds Русский.
const fold = (s) => s.normalize('NFD').replace(/\p{M}/gu, '').toLocaleLowerCase()

/**
 * The language list, with a search box at the top: 21 languages are quicker to find by typing a few letters of
 * either the native or the English name. Enter picks the first match. On phones the box is not focused on open,
 * so the keyboard does not cover the list.
 */
const LanguageMenu = forwardRef(function LanguageMenu({ current, onChoose, t, className }, ref) {
  const [query, setQuery] = useState('')
  const searchRef = useRef(null)
  const q = fold(query.trim())
  const shown = q ? languages.filter((l) => [l.native, l.name, l.code].some((s) => fold(s).includes(q))) : languages

  useEffect(() => {
    if (window.matchMedia?.('(pointer: fine)').matches) searchRef.current?.focus()
  }, [])

  return (
    <div ref={ref} className={className ? `lang-menu ${className}` : 'lang-menu'}>
      <div className="lang-search">
        <XoIcon name="search" size={15} />
        <input ref={searchRef} type="search" value={query} onChange={(e) => setQuery(e.target.value)}
               onKeyDown={(e) => { if (e.key === 'Enter' && shown[0]) { e.preventDefault(); onChoose(shown[0].code) } }}
               placeholder={t('search_languages')} aria-label={t('search_languages')} autoComplete="off" spellCheck={false} />
      </div>
      <ul role="listbox" aria-label={t('change_language')}>
        {shown.map((lang) => (
          <li key={lang.code}>
            <button type="button" role="option" aria-selected={lang.code === current}
                    className={lang.code === current ? 'active' : undefined} onClick={() => onChoose(lang.code)}>
              <span className="lang-native" dir={lang.dir}>{lang.native}</span>
              {lang.name !== lang.native && <span className="lang-name">{lang.name}</span>}
              {lang.code === current && <XoIcon name="check" size={16} className="lang-check" />}
            </button>
          </li>
        ))}
      </ul>
      {shown.length === 0 && <p className="lang-empty" role="status">{t('no_languages_found')}</p>}
    </div>
  )
})

export default LanguageMenu
