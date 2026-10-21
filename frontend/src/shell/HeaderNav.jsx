import { languages } from '@/xo/i18n'

export default function HeaderNav({ currentView = 'widget', currentLanguage = 'en', currentTheme = 'light', onViewChange, onLanguageChange, onThemeChange }) {
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

      <div className="header-center">
        <nav className="nav-tabs" role="tablist">
          <button
            role="tab"
            aria-selected={currentView === 'widget'}
            className={currentView === 'widget' ? 'nav-tab active' : 'nav-tab'}
            onClick={() => onViewChange?.('widget')}
            title="Conversational Property & Mortgage Agent"
            data-tooltip="Conversational Agent & Discovery"
            data-tooltip-pos="bottom"
          >
            <span className="tab-icon">💬</span>
            <span>Conversational Agent</span>
          </button>
          <button
            role="tab"
            aria-selected={currentView === 'admin'}
            className={currentView === 'admin' ? 'nav-tab active' : 'nav-tab'}
            onClick={() => onViewChange?.('admin')}
            title="Bank Rate Sheets & CRM Admin Portal"
            data-tooltip="Rate Sheets & CRM Admin"
            data-tooltip-pos="bottom"
          >
            <span className="tab-icon">⚙️</span>
            <span>Rate Sheets &amp; CRM Admin</span>
          </button>
        </nav>
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
      </div>
    </header>
  )
}
