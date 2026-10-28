import { languages } from '@/xo/i18n'

export default function HeaderNav({ currentLanguage = 'en', currentTheme = 'light', onLanguageChange, onThemeChange }) {
  return (
    <header className="app-header glass-panel">
      <div className="header-left">
        <div className="brand-container">
          {/* 3D XO Mascot Avatar */}
          <div className="brand-avatar-wrap">
            <img src="/xo-mascot.png" alt="XO Mascot" className="brand-mascot-img" />
            <span className="mascot-online-dot" />
          </div>
          <div className="brand-info">
            <div className="brand-title-row">
              <h1 className="brand-title">XO</h1>
              <span className="badge-live">
                <span className="pulse-dot" />
                ONLINE
              </span>
            </div>
            <p className="brand-subtitle">UAE Real Estate &amp; Mortgage Assistant</p>
          </div>
        </div>
      </div>

      <div className="header-right">
        {/* Theme Switcher: Light / Dark Mode Toggle */}
        <div className="theme-switcher-pill" role="radiogroup" aria-label="Theme Selection">
          <button
            type="button"
            className={currentTheme === 'light' ? 'theme-btn active' : 'theme-btn'}
            onClick={() => onThemeChange?.('light')}
            title="Switch to Light Mode"
            aria-label="Light Mode"
            data-tooltip="Light Mode Default"
            data-tooltip-pos="bottom"
          >
            <span className="theme-icon">☀️</span>
            <span className="theme-text">Light</span>
          </button>
          <button
            type="button"
            className={currentTheme === 'dark' ? 'theme-btn active' : 'theme-btn'}
            onClick={() => onThemeChange?.('dark')}
            title="Switch to Dark Mode"
            aria-label="Dark Mode"
            data-tooltip="Switch to Dark Theme"
            data-tooltip-pos="bottom"
          >
            <span className="theme-icon">🌙</span>
            <span className="theme-text">Dark</span>
          </button>
        </div>

        <div className="language-selector">
          <label htmlFor="lang-select" className="visually-hidden">Select Language</label>
          <select
            id="lang-select"
            value={currentLanguage}
            onChange={(e) => onLanguageChange?.(e.target.value)}
            className="lang-dropdown"
          >
            {languages.map((lang) => <option key={lang.code} value={lang.code}>{lang.native} ({lang.code.toUpperCase()})</option>)}
          </select>
        </div>

        {/* The XOTO team's way into the admin module; it opens the sign-in page, so it gives visitors nothing. */}
        <a href="/admin" className="header-admin-link" title="Admin sign-in for the XOTO team" data-tooltip="XOTO team sign-in" data-tooltip-pos="bottom">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="4" y="11" width="16" height="10" rx="2" />
            <path d="M8 11V7a4 4 0 0 1 8 0v4" />
          </svg>
          <span>Admin</span>
        </a>
      </div>
    </header>
  )
}
