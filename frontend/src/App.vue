<template>
  <div class="app-root" :data-theme="currentTheme">
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
        @update:currentTheme="currentTheme = $event"
      />
      <AdminView 
        v-else-if="currentView === 'admin'" 
      />
    </main>

    <!-- Footer with Authoritative Compliance Reference -->
    <footer class="app-footer">
      <p>XO — UAE real estate &amp; mortgage assistant &bull; All financial outputs are <em>estimates, not offers</em>.</p>
    </footer>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import HeaderNav from './components/shared/HeaderNav.vue'
import WidgetView from './views/WidgetView.vue'
import AdminView from './views/AdminView.vue'

const currentView = ref('widget')
const currentLanguage = ref('en')

// Theme management: Light Mode is strictly the default.
// Storage can throw (private browsing, blocked cookies), so every access is guarded.
const readTheme = () => {
  try { return window.localStorage.getItem('xo_theme') } catch (e) { return null }
}
const savedTheme = typeof window !== 'undefined' ? readTheme() : null
const currentTheme = ref(savedTheme === 'dark' ? 'dark' : 'light')

// Sync data-theme attribute on document root for global CSS variables
const applyTheme = (theme) => {
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', theme)
    try { window.localStorage.setItem('xo_theme', theme) } catch (e) {}
  }
}

watch(currentTheme, (newTheme) => {
  applyTheme(newTheme)
})

onMounted(() => {
  applyTheme(currentTheme.value)
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

/* Large TVs: scale the page so it reads well from a distance */
@media (min-width: 2200px) { .app-header, .app-footer { zoom: 1.4; } }
@media (min-width: 3200px) { .app-header, .app-footer { zoom: 2; } }

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
