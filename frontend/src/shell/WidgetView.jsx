'use client'
import { useState } from 'react'
import ChatWidget from '@/xo/components/ChatWidget'

export default function WidgetView({ currentLanguage = 'en', currentTheme = 'light', onLanguageChanged, onThemeChange }) {
  const [isWidgetOpen, setIsWidgetOpen] = useState(true)
  const [isExpanded] = useState(false)
  const openWidget = () => setIsWidgetOpen(true)

  return (
    <div className="widget-view-container">
      {/* Marketing Page Simulation Context */}
      <div className="demo-website-surface glass-panel">
        <div className="hero-layout-grid">
          <div className="surface-hero">
            <span className="brand-eyebrow">
              <span className="eyebrow-dot" />
              Prime UAE Real Estate &amp; Mortgages
            </span>
            <h2 className="hero-title">Experience Smarter Property Discovery &amp; Instant Mortgages</h2>
            <p className="hero-desc">
              Meet XO, your assistant for discovering UAE properties, estimating mortgage affordability and understanding the buying process — in 15 languages, by text or voice.
            </p>

            <div className="hero-actions">
              <button className="btn-luxury-purple" onClick={openWidget} data-tooltip="Open XO Assistant" data-tooltip-pos="bottom">
                <span>✨ Launch XO Assistant</span>
              </button>
              <div className="compliance-badge">
                <span>Estimates, not offers &bull; Calculated by XOTO&apos;s rule tables</span>
              </div>
            </div>
          </div>

          {/* Hero Mascot Showcase Card */}
          <div className="hero-mascot-card">
            <div className="mascot-card-badge">
              <span className="live-dot-green" />
              <span>XO &bull; ONLINE</span>
            </div>
            <div className="mascot-glow-circle">
              <img src="/xo-mascot.png" alt="XO Mascot" className="mascot-showcase-img" />
            </div>
            <div className="mascot-card-info">
              <h4>XO Assistant</h4>
              <p>Ask about properties, mortgages and fees</p>
            </div>
          </div>
        </div>

        {/* Quick Discovery Chips for Demo */}
        <div className="feature-highlights">
          <div className="feature-card">
            <div className="feature-icon">🏙️</div>
            <h3>Property Discovery</h3>
            <p>Live off-plan projects across the UAE, plus sample ready homes, filtered by budget, area and bedrooms.</p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">🧮</div>
            <h3>Deterministic Mortgages</h3>
            <p>Monthly payments, affordability and buying costs from XOTO&apos;s lending rules (50% debt-burden cap, KB fee tables).</p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">🎙️</div>
            <h3>Voice &amp; Multilingual</h3>
            <p>Talk or type in English, Arabic, Hindi, Urdu and 11 more languages.</p>
          </div>
        </div>
      </div>

      {/* Embedded Floating Widget Shell */}
      <div className={['embedded-widget-shell', isWidgetOpen && 'open', isExpanded && 'expanded'].filter(Boolean).join(' ')}>
        {/* Hidden rather than removed when closed (Vue v-show), so the conversation and voice state survive */}
        <ChatWidget
          visible={isWidgetOpen}
          currentLanguage={currentLanguage}
          currentTheme={currentTheme}
          isExpanded={isExpanded}
          onClose={() => setIsWidgetOpen(false)}
          onLanguageChanged={onLanguageChanged}
          onThemeChange={onThemeChange}
        />
        {/* Floating Launcher Button with 3D XO Mascot */}
        <button
          style={isWidgetOpen ? { display: 'none' } : undefined}
          className="floating-launcher-btn animate-pulse-glow"
          onClick={() => setIsWidgetOpen(true)}
          aria-label="Open XO Assistant"
          data-tooltip="Chat with XO AI Assistant"
          data-tooltip-pos="left"
        >
          <div className="launcher-mascot-wrapper">
            <img src="/xo-mascot.png" alt="XO Mascot" className="launcher-mascot-img" />
            <span className="launcher-live-dot" />
          </div>
          <div className="launcher-text-col">
            <span className="launcher-title">Chat with XO</span>
            <span className="launcher-subtitle">Online</span>
          </div>
        </button>
      </div>
    </div>
  )
}
