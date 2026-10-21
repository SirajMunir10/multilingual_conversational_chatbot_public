'use client'
import { useState } from 'react'

const navItems = [
  { id: 'analytics', label: 'Analytics Dashboard', icon: '📈', description: 'Real-time conversation volume, resolution rates, drop-offs, and token spend.' },
  { id: 'knowledge', label: 'Knowledge Base (CMS)', icon: '📚', description: 'Upload documents (PDF/DOCX/CSV), crawl URLs, manage FAQs, and version history.' },
  { id: 'bot_tuning', label: 'Prompt & Persona Tuning', icon: '🧠', description: 'Manage system persona, conversation scripts, guardrails, and locale tone.' },
  { id: 'conversation_review', label: 'Conversation Review', icon: '🔍', description: 'Browse transcripts, tag responses, thumbs feedback, and 1-click KB creation.' },
  { id: 'calculator_rules', label: 'Mortgage Rules & Rates', icon: '🧮', description: 'Manage interest rates, LTV caps, DBR limits, and fee schedules without code deploys.' },
  { id: 'integrations', label: 'Integrations & Models', icon: '🔌', description: 'Configure OpenAI keys, model selection, GRID & Vault gateways.' },
  { id: 'escalation_rules', label: 'Escalation & Routing', icon: '🚨', description: 'Configure human handoff triggers (sentiment, low confidence, VIP leads) and queues.' },
  { id: 'rbac', label: 'Role-Based Access (RBAC)', icon: '🛡️', description: 'Manage permissions: Content Editors, Bot Trainers, Admins, Read-Only Analysts.' },
  { id: 'ab_testing', label: 'A/B Experimentation', icon: '⚖️', description: 'Test prompt variants, flows, and persona tones against conversion metrics.' },
  { id: 'multilingual', label: 'Multilingual CMS', icon: '🌐', description: 'Manage and translate KB content and canned responses for EN, AR, HI, and UR.' }
]

export default function AdminView() {
  const [activeSection, setActiveSection] = useState('analytics')
  const currentNav = navItems.find(item => item.id === activeSection)

  return (
    <div className="admin-view-container glass-panel">
      {/* Admin Sidebar Navigation */}
      <aside className="admin-sidebar">
        <div className="admin-profile">
          <div className="admin-avatar">AD</div>
          <div>
            <h3 className="admin-name">Admin Portal</h3>
            <span className="role-badge">Preview</span>
          </div>
        </div>

        <nav className="admin-nav" role="tablist">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={activeSection === item.id ? 'admin-nav-item active' : 'admin-nav-item'}
              onClick={() => setActiveSection(item.id)}
              role="tab"
              aria-selected={activeSection === item.id}
            >
              <span className="nav-icon">{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
      </aside>

      {/* Admin Content Area */}
      <main className="admin-content">
        <div className="content-header">
          <div>
            <h2>{currentNav?.label}</h2>
            <p className="section-desc">{currentNav?.description}</p>
          </div>

          <div className="admin-status-pill">
            <span>Phase 7 — not yet built</span>
          </div>
        </div>

        <div className="module-placeholder glass-card">
          <div className="placeholder-icon">🛠️</div>
          <h4>{currentNav?.label} Architecture Ready</h4>
          <p>
            The admin module (PRD §5.6) is planned for Phase 7. Today, rule, rate, fee, community and prompt tables are edited as versioned files in <code>backend/app/data/config</code> and applied without a redeploy via the key-protected <code>/api/admin/reload-config</code> endpoint. Transcripts, leads, usage and audit logs are available through key-protected <code>/api/admin/*</code> APIs.
          </p>
        </div>
      </main>
    </div>
  )
}
