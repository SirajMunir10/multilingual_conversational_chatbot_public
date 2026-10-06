<template>
  <div class="admin-view-container glass-panel">
    <!-- Admin Sidebar Navigation -->
    <aside class="admin-sidebar">
      <div class="admin-profile">
        <div class="admin-avatar">AD</div>
        <div>
          <h3 class="admin-name">Admin Portal</h3>
          <span class="role-badge">Super Admin</span>
        </div>
      </div>

      <nav class="admin-nav" role="tablist">
        <button 
          v-for="item in navItems" 
          :key="item.id"
          class="admin-nav-item"
          :class="{ active: activeSection === item.id }"
          @click="activeSection = item.id"
          role="tab"
          :aria-selected="activeSection === item.id"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </button>
      </nav>
    </aside>

    <!-- Admin Content Area -->
    <main class="admin-content">
      <div class="content-header">
        <div>
          <h2>{{ currentNav?.label }}</h2>
          <p class="section-desc">{{ currentNav?.description }}</p>
        </div>

        <div class="admin-status-pill">
          <span>Versioned Control Mode: <strong>v1.2.0</strong></span>
        </div>
      </div>

      <!-- Module Summary Cards -->
      <div class="admin-grid">
        <div class="metric-card glass-card">
          <span class="metric-label">Total Conversations</span>
          <span class="metric-value">1,428</span>
          <span class="metric-trend positive">↑ 18.4% vs last week</span>
        </div>

        <div class="metric-card glass-card">
          <span class="metric-label">Resolution Rate</span>
          <span class="metric-value">84.2%</span>
          <span class="metric-trend positive">Target: ≥40% (Met)</span>
        </div>

        <div class="metric-card glass-card">
          <span class="metric-label">Language Accuracy</span>
          <span class="metric-value">99.1%</span>
          <span class="metric-trend positive">Target: ≥98% (Met)</span>
        </div>

        <div class="metric-card glass-card">
          <span class="metric-label">LLM Token Spend</span>
          <span class="metric-value">$42.80</span>
          <span class="metric-trend neutral">Cap: $250.00 / month</span>
        </div>
      </div>

      <!-- Placeholder content for Phase 7 complete implementation -->
      <div class="module-placeholder glass-card">
        <div class="placeholder-icon">🛠️</div>
        <h4>{{ currentNav?.label }} Architecture Ready</h4>
        <p>
          This control surface is wired to backend scoped gateways. Full interactive management (knowledge base uploader, prompt editor, rule tables, escalation triggers, and translation CMS) will be fully developed in <strong>Phase 7 (Admin Module & Back Office)</strong>.
        </p>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const activeSection = ref('analytics')

const navItems = [
  { id: 'analytics', label: 'Analytics Dashboard', icon: '📈', description: 'Real-time conversation volume, resolution rates, drop-offs, and token spend.' },
  { id: 'knowledge', label: 'Knowledge Base (CMS)', icon: '📚', description: 'Upload documents (PDF/DOCX/CSV), crawl URLs, manage FAQs, and version history.' },
  { id: 'bot_tuning', label: 'Prompt & Persona Tuning', icon: '🧠', description: 'Manage system persona, conversation scripts, guardrails, and locale tone.' },
  { id: 'conversation_review', label: 'Conversation Review', icon: '🔍', description: 'Browse transcripts, tag responses, thumbs feedback, and 1-click KB creation.' },
  { id: 'calculator_rules', label: 'Mortgage Rules & Rates', icon: '🧮', description: 'Manage interest rates, LTV caps, DBR limits, and fee schedules without code deploys.' },
  { id: 'integrations', label: 'Integrations & Models', icon: '🔌', description: 'Configure OpenAI keys, model selection (gpt-5-mini), GRID & Vault gateways.' },
  { id: 'escalation_rules', label: 'Escalation & Routing', icon: '🚨', description: 'Configure human handoff triggers (sentiment, low confidence, VIP leads) and queues.' },
  { id: 'rbac', label: 'Role-Based Access (RBAC)', icon: '🛡️', description: 'Manage permissions: Content Editors, Bot Trainers, Admins, Read-Only Analysts.' },
  { id: 'ab_testing', label: 'A/B Experimentation', icon: '⚖️', description: 'Test prompt variants, flows, and persona tones against conversion metrics.' },
  { id: 'multilingual', label: 'Multilingual CMS', icon: '🌐', description: 'Manage and translate KB content and canned responses for EN, AR, HI, and UR.' }
]

const currentNav = computed(() => navItems.find(item => item.id === activeSection.value))
</script>

<style scoped>
.admin-view-container {
  display: flex;
  min-height: 800px;
  max-width: 1400px;
  margin: 0 auto;
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.admin-sidebar {
  width: 300px;
  background: var(--bg-surface);
  border-right: 1px solid var(--border-subtle);
  padding: 24px 16px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

[dir="rtl"] .admin-sidebar {
  border-right: none;
  border-left: 1px solid var(--border-subtle);
}

.admin-profile {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.admin-avatar {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, var(--brand-purple-light), var(--brand-purple));
  color: #fff;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.admin-name {
  font-size: 1rem;
  font-weight: 700;
  color: var(--text-primary);
}

.role-badge {
  font-size: 0.75rem;
  color: var(--brand-purple);
  background: rgba(92, 3, 155, 0.1);
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

[data-theme="dark"] .role-badge {
  color: var(--brand-cyan);
  background: rgba(3, 164, 244, 0.15);
}

.admin-nav {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.admin-nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  text-align: left;
  transition: all var(--transition-fast);
}

[dir="rtl"] .admin-nav-item {
  text-align: right;
}

.admin-nav-item:hover {
  background: var(--bg-surface-hover);
  color: var(--text-primary);
}

.admin-nav-item.active {
  background: var(--bg-surface-elevated);
  color: var(--brand-purple);
  border-left: 3px solid var(--brand-purple);
}

[dir="rtl"] .admin-nav-item.active {
  border-left: none;
  border-right: 3px solid var(--brand-purple);
}

[data-theme="dark"] .admin-nav-item.active {
  color: var(--brand-cyan);
  border-color: var(--brand-cyan);
}

.admin-content {
  flex: 1;
  padding: 32px;
  background: var(--bg-primary);
}

.content-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 28px;
}

.content-header h2 {
  font-family: var(--font-heading);
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.section-desc {
  font-size: 0.95rem;
  color: var(--text-muted);
}

.admin-status-pill {
  font-size: 0.8rem;
  padding: 6px 14px;
  border-radius: var(--radius-full);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border-prominent);
  color: var(--text-secondary);
}

.admin-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
  margin-bottom: 32px;
}

.metric-card {
  padding: 20px;
}

.metric-label {
  display: block;
  font-size: 0.8rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}

.metric-value {
  display: block;
  font-family: var(--font-heading);
  font-size: 1.75rem;
  font-weight: 800;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.metric-trend {
  font-size: 0.8rem;
}

.metric-trend.positive {
  color: #34d399;
}

.metric-trend.neutral {
  color: var(--text-muted);
}

.module-placeholder {
  padding: 40px;
  text-align: center;
  max-width: 600px;
  margin: 40px auto 0;
}

.placeholder-icon {
  font-size: 3rem;
  margin-bottom: 16px;
}

.module-placeholder h4 {
  font-size: 1.25rem;
  margin-bottom: 12px;
  color: var(--gold-light);
}

.module-placeholder p {
  font-size: 0.925rem;
  color: var(--text-secondary);
  line-height: 1.6;
}
</style>
