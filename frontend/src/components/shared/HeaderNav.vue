<template>
  <header class="app-header glass-panel">
    <div class="header-left">
      <div class="brand-container">
        <!-- 3D XO Mascot Avatar -->
        <div class="brand-avatar-wrap">
          <img src="/xo-mascot.png" alt="XO Mascot" class="brand-mascot-img" />
          <span class="mascot-online-dot"></span>
        </div>
        <div class="brand-info">
          <div class="brand-title-row">
            <h1 class="brand-title">XO</h1>
            <span class="badge-live">
              <span class="pulse-dot"></span>
              ONLINE &amp; READY
            </span>
          </div>
          <p class="brand-subtitle">UAE Luxury Real Estate &amp; Mortgage Assistant</p>
        </div>
      </div>
    </div>

    <div class="header-center">
      <nav class="nav-tabs" role="tablist">
        <button 
          role="tab" 
          :aria-selected="currentView === 'widget'"
          class="nav-tab" 
          :class="{ active: currentView === 'widget' }"
          @click="$emit('update:currentView', 'widget')"
          title="Conversational Property & Mortgage Agent"
          data-tooltip="Conversational Agent & Discovery"
          data-tooltip-pos="bottom"
        >
          <span class="tab-icon">💬</span>
          <span>Conversational Agent</span>
        </button>
        <button 
          role="tab" 
          :aria-selected="currentView === 'admin'"
          class="nav-tab" 
          :class="{ active: currentView === 'admin' }"
          @click="$emit('update:currentView', 'admin')"
          title="Bank Rate Sheets & CRM Admin Portal"
          data-tooltip="Rate Sheets & CRM Admin"
          data-tooltip-pos="bottom"
        >
          <span class="tab-icon">⚙️</span>
          <span>Rate Sheets &amp; CRM Admin</span>
        </button>
      </nav>
    </div>

    <div class="header-right">
      <HealthIndicator />

      <!-- Theme Switcher: Light / Dark Mode Toggle -->
      <div class="theme-switcher-pill" role="radiogroup" aria-label="Theme Selection">
        <button 
          type="button" 
          class="theme-btn" 
          :class="{ active: currentTheme === 'light' }"
          @click="$emit('update:currentTheme', 'light')"
          title="Switch to Light Mode"
          aria-label="Light Mode"
          data-tooltip="Light Mode Default"
          data-tooltip-pos="bottom"
        >
          <span class="theme-icon">☀️</span>
          <span class="theme-text">Light</span>
        </button>
        <button 
          type="button" 
          class="theme-btn" 
          :class="{ active: currentTheme === 'dark' }"
          @click="$emit('update:currentTheme', 'dark')"
          title="Switch to Dark Mode"
          aria-label="Dark Mode"
          data-tooltip="Switch to Dark Theme"
          data-tooltip-pos="bottom"
        >
          <span class="theme-icon">🌙</span>
          <span class="theme-text">Dark</span>
        </button>
      </div>

      <!-- Human Advisor Escalation Button (From Official UI Layout) -->
      <button 
        class="btn-advisor-top" 
        @click="handleSpeakWithAdvisor" 
        aria-label="Speak with Advisor"
        title="Connect with a licensed human mortgage specialist"
        data-tooltip="Speak with a licensed advisor"
        data-tooltip-pos="bottom"
      >
        <span class="advisor-icon">🎧</span>
        <span>Speak with Advisor</span>
      </button>
      
      <div class="language-selector">
        <label for="lang-select" class="visually-hidden">Select Language</label>
        <select 
          id="lang-select" 
          :value="currentLanguage" 
          @change="$emit('update:currentLanguage', $event.target.value)"
          class="lang-dropdown"
        >
          <option value="en">🌐 English (EN)</option>
          <option value="ar">🇦🇪 العربية (AR)</option>
          <option value="hi">🇮🇳 हिन्दी (HI)</option>
          <option value="ur">🇵🇰 اردو (UR)</option>
          <option value="ru">🇷🇺 Русский (RU)</option>
          <option value="fr">🇫🇷 Français (FR)</option>
          <option value="de">🇩🇪 Deutsch (DE)</option>
          <option value="es">🇪🇸 Español (ES)</option>
          <option value="tr">🇹🇷 Türkçe (TR)</option>
          <option value="ta">🇮🇳 தமிழ் (TA)</option>
          <option value="te">🇮🇳 తెలుగు (TE)</option>
          <option value="bn">🇧🇩 বাংলা (BN)</option>
          <option value="pa">🇮🇳 ਪੰਜਾਬੀ (PA)</option>
          <option value="gu">🇮🇳 ગુજરાતી (GU)</option>
          <option value="mwr">🇮🇳 मारवाड़ी (MWR)</option>
          <option value="or">🇮🇳 ଓଡ଼ିଆ (OR)</option>
        </select>
      </div>
    </div>
  </header>
</template>

<script setup>
import HealthIndicator from './HealthIndicator.vue'

defineProps({
  currentView: {
    type: String,
    default: 'widget'
  },
  currentLanguage: {
    type: String,
    default: 'en'
  },
  currentTheme: {
    type: String,
    default: 'light'
  }
})

const emit = defineEmits(['update:currentView', 'update:currentLanguage', 'update:currentTheme', 'speak-with-advisor'])

const handleSpeakWithAdvisor = () => {
  emit('speak-with-advisor')
}
</script>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 20px;
  margin: 12px 16px 20px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-purple);
  background: var(--bg-glass);
  box-shadow: var(--shadow-sm);
  gap: 16px;
  flex-wrap: wrap;
  transition: all var(--transition-normal);
}

.brand-container {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-avatar-wrap {
  position: relative;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(92, 3, 155, 0.15), rgba(3, 164, 244, 0.10));
  border: 2px solid var(--brand-purple-light);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  transition: transform var(--transition-fast);
}

.brand-avatar-wrap:hover {
  transform: scale(1.06);
  border-color: var(--brand-purple);
}

.brand-mascot-img {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  object-fit: contain;
}

.mascot-online-dot {
  position: absolute;
  bottom: 0px;
  right: 0px;
  width: 11px;
  height: 11px;
  background: var(--brand-lime-vivid);
  border: 2px solid var(--bg-surface);
  border-radius: 50%;
  box-shadow: 0 0 6px var(--brand-lime-vivid);
}

.brand-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.brand-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-title {
  font-family: var(--font-heading);
  font-size: 1.25rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  background: linear-gradient(135deg, var(--brand-purple-dark), var(--brand-purple));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin: 0;
}

[data-theme="dark"] .brand-title {
  background: linear-gradient(135deg, #FFFFFF, var(--text-purple-light));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.brand-subtitle {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin: 0;
}

.nav-tabs {
  display: flex;
  align-items: center;
  background: var(--bg-surface-elevated);
  padding: 3px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-subtle);
  gap: 4px;
}

.nav-tab {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-muted);
  font-size: 0.84rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.nav-tab:hover {
  color: var(--text-primary);
  background: var(--bg-surface-hover);
}

.nav-tab.active {
  background: linear-gradient(135deg, var(--brand-purple-light), var(--brand-purple));
  color: #FFFFFF;
  border-color: rgba(255, 255, 255, 0.2);
  box-shadow: var(--shadow-sm);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* Theme Switcher Pill */
.theme-switcher-pill {
  display: flex;
  align-items: center;
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-full);
  padding: 2px;
  gap: 2px;
}

.theme-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border-radius: var(--radius-full);
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.theme-btn:hover {
  color: var(--text-primary);
}

.theme-btn.active {
  background: var(--bg-surface);
  color: var(--text-primary);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

[data-theme="dark"] .theme-btn.active {
  background: var(--brand-purple);
  color: #FFFFFF;
  box-shadow: 0 0 10px rgba(92, 3, 155, 0.5);
}

.theme-icon {
  font-size: 0.85rem;
  line-height: 1;
}

.btn-advisor-top {
  display: flex;
  align-items: center;
  gap: 6px;
  background: linear-gradient(135deg, var(--brand-purple-light), var(--brand-purple));
  color: #FFFFFF;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: var(--radius-full);
  padding: 6px 14px;
  font-size: 0.80rem;
  font-weight: 700;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-fast);
}

.btn-advisor-top:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-md), 0 0 14px var(--brand-purple-glow);
}

.lang-dropdown {
  background: var(--bg-surface-elevated);
  color: var(--text-primary);
  border: 1px solid var(--border-prominent);
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  font-size: 0.80rem;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.lang-dropdown:focus {
  border-color: var(--brand-purple);
  outline: none;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  border: 0;
}

@media (max-width: 900px) {
  .app-header {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
    padding: 10px 14px;
    margin: 8px 10px 16px;
  }

  .header-left, .header-center, .header-right {
    justify-content: center;
  }
}

@media (max-width: 600px) {
  .app-header {
    margin: 6px 6px 12px;
    padding: 8px 10px;
    gap: 10px;
    border-radius: var(--radius-md);
  }

  .brand-container {
    gap: 8px;
    justify-content: center;
  }

  .brand-avatar-wrap {
    width: 36px;
    height: 36px;
  }

  .brand-title {
    font-size: 1.1rem;
  }

  .brand-subtitle {
    font-size: 0.68rem;
    text-align: center;
  }

  .nav-tabs {
    width: 100%;
    display: flex;
  }

  .nav-tab {
    flex: 1;
    justify-content: center;
    padding: 6px 8px;
    font-size: 0.75rem;
    gap: 4px;
    white-space: nowrap;
  }

  .header-right {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: center;
    gap: 6px;
    width: 100%;
  }

  .theme-btn .theme-text {
    display: none;
  }

  .theme-btn {
    padding: 5px 8px;
  }

  .btn-advisor-top {
    padding: 5px 10px;
    font-size: 0.75rem;
  }

  .lang-dropdown {
    padding: 4px 6px;
    font-size: 0.75rem;
  }
}
</style>
