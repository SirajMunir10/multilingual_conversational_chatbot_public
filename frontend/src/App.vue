<template>
  <div class="app-root" :dir="isRTL ? 'rtl' : 'ltr'" :lang="currentLanguage" :data-theme="currentTheme">
    <!-- Master Header Navigation -->
    <HeaderNav 
      v-model:currentView="currentView" 
      v-model:currentLanguage="currentLanguage" 
      v-model:currentTheme="currentTheme"
    />

    <!-- Main Content Area based on Selected View -->
    <main class="main-viewport">
      <WidgetView 
        v-if="currentView === 'widget'" 
        :currentLanguage="currentLanguage" 
        :currentTheme="currentTheme"
        @language-changed="currentLanguage = $event"
      />
      <AdminView 
        v-else-if="currentView === 'admin'" 
      />
    </main>

    <!-- Footer with Authoritative Compliance Reference -->
    <footer class="app-footer">
      <p>
        XO — Conversational AI Assistant &bull; Regulatory Scope: UAE / Dubai / DIFC &bull; 
        Retention Reference: <code>XOTO-CORP-RETENTION-POL-2024-V3</code> &bull; 
        All financial outputs are <em>estimates, not offers</em>.
      </p>
    </footer>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import HeaderNav from './components/shared/HeaderNav.vue'
import WidgetView from './views/WidgetView.vue'
import AdminView from './views/AdminView.vue'

const currentView = ref('widget')
const currentLanguage = ref('en')

// Theme management: Light Mode is strictly the default
const savedTheme = typeof window !== 'undefined' ? localStorage.getItem('xo_theme') : null
const currentTheme = ref(savedTheme === 'dark' ? 'dark' : 'light')

// Sync data-theme attribute on document root for global CSS variables
const applyTheme = (theme) => {
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('xo_theme', theme)
  }
}

watch(currentTheme, (newTheme) => {
  applyTheme(newTheme)
})

onMounted(() => {
  applyTheme(currentTheme.value)
})

// Arabic (ar), Urdu (ur), and Persian (fa) use Right-to-Left (RTL) text direction
const isRTL = computed(() => {
  return currentLanguage.value === 'ar' || currentLanguage.value === 'ur' || currentLanguage.value === 'fa'
})
</script>

<style scoped>
.app-root {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--bg-primary);
  color: var(--text-primary);
  transition: background-color var(--transition-smooth), color var(--transition-smooth);
}

.main-viewport {
  flex: 1;
  padding-bottom: 40px;
}

.app-footer {
  text-align: center;
  padding: 16px 20px;
  font-size: 0.75rem;
  color: var(--text-muted);
  border-top: 1px solid var(--border-subtle);
  background: var(--bg-footer, var(--bg-surface));
  transition: background-color var(--transition-normal);
}

.app-footer code {
  color: var(--brand-purple);
  background: rgba(92, 3, 155, 0.08);
  padding: 2px 7px;
  border-radius: var(--radius-sm);
  font-weight: 600;
  border: 1px solid var(--border-purple);
}

[data-theme="dark"] .app-footer code {
  color: var(--text-purple-light);
  background: rgba(255, 255, 255, 0.05);
}

.app-footer em {
  color: var(--text-secondary);
  font-style: normal;
  font-weight: 500;
}
</style>
