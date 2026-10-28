'use client'
import { useEffect, useState } from 'react'
import HeaderNav from './HeaderNav'
import WidgetView from './WidgetView'

// Theme management: Light Mode is strictly the default.
// Storage can throw (private browsing, blocked cookies), so every access is guarded.
const readTheme = () => {
  try { return window.localStorage.getItem('xo_theme') } catch (e) { return null }
}

// Sync data-theme attribute on document root for global CSS variables
const applyTheme = (theme) => {
  document.documentElement.setAttribute('data-theme', theme)
  try { window.localStorage.setItem('xo_theme', theme) } catch (e) {}
}

export default function App() {
  const [currentLanguage, setCurrentLanguage] = useState('en')
  const [currentTheme, setCurrentTheme] = useState(() => (readTheme() === 'dark' ? 'dark' : 'light'))

  useEffect(() => { applyTheme(currentTheme) }, [currentTheme])

  return (
    <div className="app-root" data-theme={currentTheme}>
      {/* Master Header Navigation */}
      <HeaderNav
        currentLanguage={currentLanguage}
        currentTheme={currentTheme}
        onLanguageChange={setCurrentLanguage}
        onThemeChange={setCurrentTheme}
      />

      <main className="main-viewport">
        <WidgetView
          currentLanguage={currentLanguage}
          currentTheme={currentTheme}
          onLanguageChanged={setCurrentLanguage}
          onThemeChange={setCurrentTheme}
        />
      </main>

      {/* Footer with Authoritative Compliance Reference */}
      <footer className="app-footer">
        <p>XO — UAE real estate &amp; mortgage assistant &bull; All financial outputs are <em>estimates, not offers</em>.</p>
      </footer>
    </div>
  )
}
