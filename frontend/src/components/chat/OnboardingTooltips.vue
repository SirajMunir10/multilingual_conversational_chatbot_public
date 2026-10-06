<template>
  <div class="onboarding-tips-container glass-card" v-if="isOpen">
    <div class="tips-header">
      <div class="tips-title">
        <span class="sparkle-icon">💡</span>
        <h4>XO Feature Tips & Guide</h4>
      </div>
      <button 
        class="tips-close-btn" 
        @click="$emit('close')" 
        aria-label="Close feature tips"
        title="Dismiss tips"
        data-tooltip="Dismiss tips"
        data-tooltip-pos="left"
      >✕</button>
    </div>

    <div class="tips-grid">
      <div class="tip-item">
        <span class="tip-icon">🎙️</span>
        <div>
          <strong>Voice Interaction:</strong>
          <p>Tap the microphone to speak naturally in English, Arabic, Hindi, or Urdu.</p>
        </div>
      </div>

      <div class="tip-item">
        <span class="tip-icon">🌐</span>
        <div>
          <strong>Auto Language Detect:</strong>
          <p>Type in any supported language; XO automatically matches your locale and text direction.</p>
        </div>
      </div>

      <div class="tip-item">
        <span class="tip-icon">🏙️</span>
        <div>
          <strong>Live Property Search:</strong>
          <p>Try: <em>"Show 2 bedroom apartments in Downtown under 3 million"</em>.</p>
        </div>
      </div>

      <div class="tip-item">
        <span class="tip-icon">🧮</span>
        <div>
          <strong>Deterministic Mortgages:</strong>
          <p>Try: <em>"What would my EMI be with 40k income?"</em> for UAE Central Bank aligned calculations.</p>
        </div>
      </div>

      <div class="tip-item">
        <span class="tip-icon">🤝</span>
        <div>
          <strong>Human Agent Handoff:</strong>
          <p>Tap 'Connect Human Agent' anytime to route your full transcript to our specialist team.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  isOpen: {
    type: Boolean,
    default: true
  }
})

defineEmits(['close'])
</script>

<style scoped>
.onboarding-tips-container {
  padding: 14px;
  margin: 10px 0;
  border: 1px solid var(--border-purple);
  background: var(--bg-surface);
  box-shadow: var(--shadow-sm);
  border-radius: var(--radius-md);
}

.tips-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.tips-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tips-title h4 {
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--text-primary);
}

.tips-close-btn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 0.9rem;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
}

.tips-close-btn:hover {
  color: var(--text-primary);
  background: var(--bg-surface-hover);
}

.tips-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tip-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 0.8rem;
}

.tip-icon {
  font-size: 1.1rem;
  line-height: 1;
}

.tip-item strong {
  color: var(--text-primary);
  display: block;
  margin-bottom: 2px;
}

.tip-item p {
  color: var(--text-secondary);
  line-height: 1.4;
}

.tip-item em {
  color: var(--brand-purple);
  font-style: normal;
  font-weight: 600;
}

[data-theme="dark"] .tip-item em {
  color: var(--brand-cyan);
}
</style>
