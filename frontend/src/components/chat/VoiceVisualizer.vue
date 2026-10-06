<template>
  <div class="voice-visualizer-container" v-if="isActive">
    <div class="visualizer-header">
      <span class="recording-pulse"></span>
      <span class="status-label">{{ label }}</span>
    </div>
    <div class="wave-bars">
      <span v-for="n in 12" :key="n" class="wave-bar" :style="{ animationDelay: `${(n * 0.1).toFixed(1)}s` }"></span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  isActive: {
    type: Boolean,
    default: false
  },
  label: {
    type: String,
    default: 'Listening...'
  }
})
</script>

<style scoped>
.voice-visualizer-container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  margin: 6px 0;
  border-radius: var(--radius-md);
  background: rgba(56, 189, 248, 0.12);
  border: 1px solid var(--border-cyan);
}

.visualizer-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.recording-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #f43f5e;
  box-shadow: 0 0 10px #f43f5e;
  animation: pulseRecording 1.2s infinite;
}

.status-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-cyan);
}

.wave-bars {
  display: flex;
  align-items: center;
  gap: 3px;
  height: 20px;
}

.wave-bar {
  width: 3px;
  background: var(--cyan-primary);
  border-radius: 2px;
  height: 6px;
  animation: waveMotion 1s ease-in-out infinite;
}

@keyframes waveMotion {
  0%, 100% { height: 6px; opacity: 0.5; }
  50% { height: 20px; opacity: 1; }
}

@keyframes pulseRecording {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.3; transform: scale(0.8); }
}
</style>
