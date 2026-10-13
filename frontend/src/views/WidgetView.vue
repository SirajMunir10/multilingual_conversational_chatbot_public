<template>
  <div class="widget-view-container">
    <!-- Marketing Page Simulation Context -->
    <div class="demo-website-surface glass-panel">
      <div class="hero-layout-grid">
        <div class="surface-hero">
          <span class="brand-eyebrow">
            <span class="eyebrow-dot"></span>
            Prime UAE Real Estate &amp; Mortgages
          </span>
          <h2 class="hero-title">Experience Smarter Property Discovery &amp; Instant Mortgages</h2>
          <p class="hero-desc">
            Meet XO, your dedicated futuristic AI companion for discovering premier luxury properties, calculating real-time mortgage affordability, and navigating UAE Central Bank regulations in English, Arabic, Hindi, and Urdu.
          </p>
          
          <div class="hero-actions">
            <button class="btn-luxury-purple" @click="openWidget" data-tooltip="Open XO Assistant" data-tooltip-pos="bottom">
              <span>✨ Launch XO Assistant</span>
            </button>
            <div class="compliance-badge">
              <span>UAE Central Bank &amp; DIFC Aligned &bull; Deterministic Math</span>
            </div>
          </div>
        </div>

        <!-- Hero Mascot Showcase Card -->
        <div class="hero-mascot-card">
          <div class="mascot-card-badge">
            <span class="live-dot-green"></span>
            <span>XO AI v4.2 &bull; ONLINE</span>
          </div>
          <div class="mascot-glow-circle">
            <img src="/xo-mascot.png" alt="XO Mascot" class="mascot-showcase-img" />
          </div>
          <div class="mascot-card-info">
            <h4>XO Assistant</h4>
            <p>Ready to compute EMI &amp; showcase Dubai penthouses</p>
          </div>
        </div>
      </div>

      <!-- Quick Discovery Chips for Demo -->
      <div class="feature-highlights">
        <div class="feature-card">
          <div class="feature-icon">🏙️</div>
          <h3>Property Discovery</h3>
          <p>Real-time luxury inventory across Downtown, Palm Jumeirah, Business Bay, and Dubai Hills.</p>
        </div>

        <div class="feature-card">
          <div class="feature-icon">🧮</div>
          <h3>Deterministic Mortgages</h3>
          <p>Exact mathematical formulas calculating monthly EMI, Central Bank 50% DBR limits, and 4% DLD fees.</p>
        </div>

        <div class="feature-card">
          <div class="feature-icon">🎙️</div>
          <h3>Voice &amp; Multilingual</h3>
          <p>Seamless voice-to-voice with native speech synthesis across English, Arabic (العربية), Hindi, and Urdu.</p>
        </div>
      </div>
    </div>

    <!-- Embedded Floating Widget Shell -->
    <div class="embedded-widget-shell" :class="{ 'open': isWidgetOpen, 'expanded': isExpanded }">
      <ChatWidget 
        v-show="isWidgetOpen" 
        :current-language="currentLanguage"
        :current-theme="currentTheme"
        :is-expanded="isExpanded"
        @close="isWidgetOpen = false"
        @toggle-expand="isExpanded = !isExpanded"
        @language-changed="$emit('language-changed', $event)"
        @update:current-theme="$emit('update:currentTheme', $event)"
      />
      <!-- Floating Launcher Button with 3D XO Mascot -->
      <button 
        v-show="!isWidgetOpen" 
        class="floating-launcher-btn animate-pulse-glow" 
        @click="isWidgetOpen = true"
        aria-label="Open XO Assistant"
        data-tooltip="Chat with XO AI Assistant"
        data-tooltip-pos="left"
      >
        <div class="launcher-mascot-wrapper">
          <img src="/xo-mascot.png" alt="XO Mascot" class="launcher-mascot-img" />
          <span class="launcher-live-dot"></span>
        </div>
        <div class="launcher-text-col">
          <span class="launcher-title">Chat with XO AI</span>
          <span class="launcher-subtitle">Online &bull; Instant Response</span>
        </div>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import ChatWidget from '../components/chat/ChatWidget.vue'

defineProps({
  currentLanguage: {
    type: String,
    default: 'en'
  },
  currentTheme: {
    type: String,
    default: 'light'
  }
})

defineEmits(['language-changed', 'update:currentTheme'])

const isWidgetOpen = ref(true)
const isExpanded = ref(false)

const openWidget = () => {
  isWidgetOpen.value = true
}
</script>

<style scoped>
.widget-view-container {
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 16px;
  position: relative;
}

.demo-website-surface {
  padding: 40px;
  margin-bottom: 32px;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-normal);
}

[data-theme="dark"] .demo-website-surface {
  background: radial-gradient(circle at top right, rgba(92, 3, 155, 0.2) 0%, transparent 60%),
              radial-gradient(circle at bottom left, rgba(3, 164, 244, 0.12) 0%, transparent 50%),
              var(--bg-glass);
  border-color: var(--border-purple);
}

.hero-layout-grid {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 36px;
  align-items: center;
}

.brand-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 14px;
  border-radius: 999px;
  background: rgba(92, 3, 155, 0.08);
  border: 1px solid var(--border-purple);
  color: var(--brand-purple);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  margin-bottom: 18px;
}

[data-theme="dark"] .brand-eyebrow {
  background: rgba(92, 3, 155, 0.25);
  color: var(--brand-cyan);
}

.eyebrow-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--brand-lime-vivid);
  box-shadow: 0 0 6px var(--brand-lime-vivid);
}

.hero-title {
  font-family: var(--font-heading);
  font-size: 2.75rem;
  font-weight: 800;
  line-height: 1.15;
  margin-bottom: 18px;
  background: linear-gradient(135deg, #0F172A 30%, var(--brand-purple) 90%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

[data-theme="dark"] .hero-title {
  background: linear-gradient(135deg, #ffffff 40%, var(--brand-cyan) 85%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.hero-desc {
  font-size: 1.05rem;
  line-height: 1.6;
  color: var(--text-secondary);
  max-width: 720px;
  margin-bottom: 28px;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
}

.compliance-badge {
  font-size: 0.8rem;
  color: var(--text-muted);
  border-left: 2px solid var(--brand-purple);
  padding-left: 14px;
}

/* Mascot Showcase Card */
.hero-mascot-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 24px;
  background: var(--bg-surface);
  border: 1px solid var(--border-purple);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-normal);
}

[data-theme="dark"] .hero-mascot-card {
  background: var(--bg-surface-elevated);
}

.mascot-card-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: rgba(22, 163, 74, 0.12);
  border: 1px solid var(--border-lime);
  color: var(--brand-lime);
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  padding: 3px 10px;
  border-radius: 999px;
  margin-bottom: 14px;
}

[data-theme="dark"] .mascot-card-badge {
  background: rgba(100, 239, 10, 0.15);
  color: var(--brand-lime-vivid);
}

.live-dot-green {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand-lime-vivid);
  box-shadow: 0 0 6px var(--brand-lime-vivid);
  animation: pulseLive 2s infinite;
}

.mascot-glow-circle {
  position: relative;
  width: 140px;
  height: 140px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(92, 3, 155, 0.12) 0%, rgba(3, 164, 244, 0.08) 70%, transparent 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}

.mascot-showcase-img {
  width: 125px;
  height: 125px;
  object-fit: contain;
  animation: floatMascot 4s ease-in-out infinite;
}

.mascot-card-info h4 {
  margin: 0 0 4px;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text-primary);
  font-family: var(--font-heading);
}

.mascot-card-info p {
  margin: 0;
  font-size: 0.76rem;
  color: var(--text-muted);
}

.feature-highlights {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 20px;
  margin-top: 40px;
}

.feature-card {
  padding: 24px;
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  transition: all var(--transition-normal);
}

.feature-card:hover {
  background: var(--bg-surface-hover);
  border-color: var(--brand-purple);
  box-shadow: var(--shadow-sm);
  transform: translateY(-2px);
}

.feature-icon {
  font-size: 2rem;
  margin-bottom: 12px;
}

.feature-card h3 {
  font-family: var(--font-heading);
  font-size: 1.12rem;
  color: var(--text-primary);
  margin-bottom: 8px;
  font-weight: 700;
}

.feature-card p {
  font-size: 0.88rem;
  line-height: 1.5;
  color: var(--text-muted);
}

/* Embedded Widget Shell */
.embedded-widget-shell {
  position: fixed;
  bottom: 20px;
  right: 20px;
  width: 450px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 40px);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  transition: width 0.3s cubic-bezier(0.16, 1, 0.3, 1), max-height 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.embedded-widget-shell.expanded {
  width: 820px;
  max-width: calc(100vw - 40px);
}

[dir="rtl"] .embedded-widget-shell {
  right: auto;
  left: 20px;
}

/* Floating Launcher Button with Mascot */
.floating-launcher-btn {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 18px 8px 8px;
  border-radius: 999px;
  cursor: pointer;
  background: linear-gradient(135deg, var(--brand-purple-light), var(--brand-purple));
  border: 1.5px solid rgba(255, 255, 255, 0.25);
  color: #FFFFFF;
  box-shadow: var(--shadow-lg), 0 0 20px var(--brand-purple-glow);
  transition: all var(--transition-normal);
}

.floating-launcher-btn:hover {
  transform: translateY(-2px) scale(1.02);
  box-shadow: var(--shadow-lg), 0 0 30px var(--brand-purple-glow);
}

.launcher-mascot-wrapper {
  position: relative;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.25) 0%, rgba(92, 3, 155, 0.6) 100%);
  border: 1.5px solid rgba(255, 255, 255, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: visible;
}

.launcher-mascot-img {
  width: 38px;
  height: 38px;
  object-fit: cover;
  border-radius: 50%;
}

.launcher-live-dot {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--brand-lime-vivid);
  border: 2px solid var(--bg-surface);
  box-shadow: 0 0 6px var(--brand-lime-vivid);
  animation: pulseLive 2s infinite;
}

.launcher-text-col {
  display: flex;
  flex-direction: column;
  text-align: left;
}

[dir="rtl"] .launcher-text-col {
  text-align: right;
}

.launcher-title {
  font-size: 0.94rem;
  font-weight: 700;
  color: #FFFFFF;
  line-height: 1.2;
}

.launcher-subtitle {
  font-size: 0.70rem;
  color: rgba(255, 255, 255, 0.85);
  font-weight: 500;
}

@keyframes floatMascot {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}

@keyframes pulseLive {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.85); }
}

@media (max-width: 900px) {
  .hero-layout-grid {
    grid-template-columns: 1fr;
  }

  .hero-mascot-card {
    display: none;
  }
}

@media (max-width: 600px) {
  .widget-view-container {
    padding: 0 4px;
  }

  .demo-website-surface {
    padding: 16px 12px;
    margin-bottom: 16px;
    border-radius: var(--radius-md);
  }

  .brand-eyebrow {
    font-size: 0.70rem;
    padding: 4px 10px;
    margin-bottom: 12px;
  }

  .hero-title {
    font-size: 1.55rem;
    line-height: 1.25;
    margin-bottom: 12px;
  }

  .hero-desc {
    font-size: 0.88rem;
    line-height: 1.5;
    margin-bottom: 20px;
  }

  .hero-actions {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }

  .btn-luxury-purple {
    width: 100%;
    justify-content: center;
    padding: 12px 18px;
  }

  .compliance-badge {
    border-left: none;
    border-top: 1px solid var(--border-subtle);
    padding: 8px 0 0;
    text-align: center;
    font-size: 0.72rem;
  }

  .feature-highlights {
    grid-template-columns: 1fr;
    gap: 12px;
    margin-top: 24px;
  }

  .feature-card {
    padding: 16px 14px;
  }

  .feature-card h3 {
    font-size: 1rem;
  }

  .feature-card p {
    font-size: 0.82rem;
  }

  /* Full-bleed mobile sheet for embedded widget */
  .embedded-widget-shell.open {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    width: 100% !important;
    max-width: 100% !important;
    height: 100% !important;
    height: 100dvh !important;
    max-height: 100dvh !important;
    margin: 0 !important;
    padding: 0 !important;
    border-radius: 0 !important;
    z-index: 999999 !important;
  }

  .floating-launcher-btn {
    bottom: 14px;
    right: 14px;
    padding: 6px 14px 6px 6px;
    max-width: calc(100vw - 28px);
  }

  [dir="rtl"] .floating-launcher-btn {
    right: auto;
    left: 14px;
  }

  .launcher-mascot-wrapper {
    width: 38px;
    height: 38px;
  }

  .launcher-mascot-img {
    width: 32px;
    height: 32px;
  }

  .launcher-title {
    font-size: 0.84rem;
  }

  .launcher-subtitle {
    font-size: 0.65rem;
  }
}
</style>
