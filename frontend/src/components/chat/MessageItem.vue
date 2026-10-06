<template>
  <div class="message-wrapper" :class="[message.role]">
    <!-- 3D Mascot Avatar for Assistant / Initial for User -->
    <div class="message-avatar" :class="message.role">
      <img 
        v-if="message.role === 'assistant'" 
        src="/xo-mascot.png" 
        alt="XO Assistant Mascot" 
        class="assistant-mascot-img" 
      />
      <span v-else class="user-avatar-text">👤</span>
    </div>

    <div class="message-bubble-container">
      <div class="message-bubble">
        <div class="message-content" v-html="formattedContent"></div>
      </div>

      <!-- Property Recommendations Display (FR-8) -->
      <div class="property-results-container" v-if="message.metadata?.property_results?.length">
        <div class="property-results-header">
          <span class="results-badge">Featured Listings (Live Inventory)</span>
        </div>
        <div class="property-card-list">
          <div 
            v-for="prop in message.metadata.property_results" 
            :key="prop.id" 
            class="prop-card"
          >
            <div class="prop-image-wrap">
              <img :src="prop.image_url" :alt="prop.title" class="prop-image" />
              <div class="prop-badges-top">
                <span class="badge-status" :class="prop.status">{{ prop.status }}</span>
                <span class="badge-dev" v-if="prop.developer">{{ prop.developer }}</span>
              </div>
              <button 
                class="prop-shortlist-btn" 
                :class="{ 'is-saved': prop.is_shortlisted }"
                @click="$emit('shortlist-property', prop)"
                :title="prop.is_shortlisted ? 'Remove from shortlist' : 'Save to shortlist'"
                aria-label="Save to shortlist"
              >
                {{ prop.is_shortlisted ? '❤️' : '🤍' }}
              </button>
              <span class="prop-price">AED {{ formatNumber(prop.price) }}</span>
            </div>
            <div class="prop-info">
              <h5 class="prop-title">{{ prop.title }}</h5>
              <p class="prop-location">📍 {{ prop.community }}, {{ prop.city }}</p>
              
              <div class="prop-specs">
                <span>🛏️ {{ prop.beds }} Beds</span>
                <span>🚿 {{ prop.baths }} Baths</span>
                <span>📐 {{ prop.sq_ft }} sq.ft</span>
              </div>

              <!-- Amenities Tags -->
              <div class="prop-amenities-row" v-if="prop.amenities?.length">
                <span v-for="(amenity, i) in prop.amenities.slice(0, 3)" :key="i" class="amenity-chip">
                  {{ amenity }}
                </span>
              </div>

              <!-- Mortgage Cross-Sell Banner (FR-11) -->
              <div class="prop-mortgage-banner" v-if="prop.mortgage_cross_sell">
                <span class="cross-sell-icon">💳</span>
                <div class="cross-sell-text">
                  <strong>Est. EMI: AED {{ formatNumber(prop.mortgage_cross_sell.monthly_emi_aed) }}/mo</strong>
                  <span class="cross-sell-sub">({{ prop.mortgage_cross_sell.required_down_payment_pct }}% down &bull; {{ prop.mortgage_cross_sell.representative_rate_pct }}% profit rate)</span>
                </div>
              </div>

              <div class="prop-actions">
                <button 
                  class="btn-card-action mortgage-btn"
                  @click="$emit('select-property-mortgage', prop)"
                >
                  🧮 Calculate Mortgage
                </button>
                <a :href="prop.listing_url" target="_blank" class="prop-link">View Details ↗</a>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Mortgage Calculation Card Display (Rule 5, Rule 10, FR-14, FR-15) -->
      <MortgageCard 
        v-if="message.metadata?.mortgage_result" 
        :data="message.metadata.mortgage_result" 
        @jump-to-properties="$emit('jump-to-properties', $event)" 
      />

      <span class="message-timestamp">{{ message.timestamp ? formatTime(message.timestamp) : '' }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import MortgageCard from './MortgageCard.vue'

const props = defineProps({
  message: {
    type: Object,
    required: true
  }
})

defineEmits(['select-property-mortgage', 'jump-to-properties', 'shortlist-property'])

const formattedContent = computed(() => {
  if (!props.message.content) return ''
  // Basic markdown formatting for bold and line breaks
  return props.message.content
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\n/g, '<br/>')
})

const formatNumber = (num) => {
  if (!num) return '0'
  return Number(num).toLocaleString()
}

const formatTime = (isoString) => {
  try {
    const d = new Date(isoString)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}
</script>

<style scoped>
.message-wrapper {
  display: flex;
  gap: 10px;
  margin-bottom: 14px;
  animation: fadeInUp 250ms ease forwards;
}

.message-wrapper.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.82rem;
  font-weight: 700;
  flex-shrink: 0;
  overflow: hidden;
}

.message-wrapper.assistant .message-avatar {
  background: radial-gradient(circle, rgba(92, 3, 155, 0.15), rgba(3, 164, 244, 0.10));
  border: 1.5px solid var(--brand-purple-light);
  box-shadow: var(--shadow-sm);
  padding: 1px;
}

.assistant-mascot-img {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  object-fit: cover;
}

.message-wrapper.user .message-avatar {
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-prominent);
  color: var(--text-primary);
}

.user-avatar-text {
  font-size: 0.85rem;
}

.message-bubble-container {
  max-width: 82%;
  display: flex;
  flex-direction: column;
}

.message-wrapper.user .message-bubble-container {
  align-items: flex-end;
}

.message-bubble {
  padding: 10px 16px;
  font-size: 0.88rem;
  line-height: 1.55;
  border-radius: var(--radius-md);
  transition: all var(--transition-normal);
}

.message-wrapper.assistant .message-bubble {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}

[data-theme="dark"] .message-wrapper.assistant .message-bubble {
  background: var(--bg-surface-elevated);
  border-color: var(--border-purple);
}

.message-wrapper.user .message-bubble {
  background: linear-gradient(135deg, var(--brand-purple-light), var(--brand-purple));
  color: #FFFFFF;
  border: 1px solid rgba(255, 255, 255, 0.20);
  box-shadow: var(--shadow-sm);
}

.message-timestamp {
  font-size: 0.68rem;
  color: var(--text-muted);
  margin-top: 4px;
}

/* Property Results Inside Chat */
.property-results-container {
  margin-top: 10px;
}

.property-results-header {
  margin-bottom: 8px;
}

.results-badge {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--brand-cyan);
  background: rgba(3, 164, 244, 0.10);
  padding: 3px 9px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-cyan);
}

.property-card-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.prop-card {
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  background: var(--bg-surface);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-normal);
}

[data-theme="dark"] .prop-card {
  border-color: var(--border-purple);
}

.prop-card:hover {
  border-color: var(--brand-purple);
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.prop-image-wrap {
  position: relative;
  height: 140px;
  overflow: hidden;
}

.prop-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform var(--transition-normal);
}

.prop-card:hover .prop-image {
  transform: scale(1.03);
}

.prop-badges-top {
  position: absolute;
  top: 8px;
  left: 8px;
  display: flex;
  gap: 6px;
  z-index: 2;
}

[dir="rtl"] .prop-badges-top {
  left: auto;
  right: 8px;
}

.badge-status {
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  padding: 2px 7px;
  border-radius: var(--radius-sm);
  background: rgba(22, 163, 74, 0.15);
  color: var(--brand-lime);
  border: 1px solid var(--border-lime);
  letter-spacing: 0.5px;
}

.badge-status.off-plan {
  background: rgba(3, 164, 244, 0.15);
  color: var(--brand-cyan);
  border-color: var(--border-cyan);
}

.badge-dev {
  font-size: 0.65rem;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: var(--radius-sm);
  background: rgba(15, 23, 42, 0.85);
  color: #FFFFFF;
  border: 1px solid var(--border-subtle);
}

.prop-shortlist-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  background: rgba(15, 23, 42, 0.75);
  backdrop-filter: blur(6px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 50%;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 0.85rem;
  transition: all 0.2s ease;
  z-index: 2;
}

[dir="rtl"] .prop-shortlist-btn {
  right: auto;
  left: 8px;
}

.prop-shortlist-btn:hover {
  transform: scale(1.12);
  background: rgba(92, 3, 155, 0.8);
}

.prop-shortlist-btn.is-saved {
  background: rgba(92, 3, 155, 0.9);
}

.prop-price {
  position: absolute;
  bottom: 8px;
  right: 8px;
  background: rgba(15, 23, 42, 0.90);
  backdrop-filter: blur(8px);
  color: var(--brand-lime-vivid);
  font-weight: 800;
  font-size: 0.84rem;
  padding: 3px 9px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(100, 239, 10, 0.4);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5);
}

[dir="rtl"] .prop-price {
  right: auto;
  left: 8px;
}

.prop-amenities-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}

.amenity-chip {
  font-size: 0.65rem;
  color: var(--text-muted);
  background: var(--bg-surface-elevated);
  padding: 2px 7px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-subtle);
}

.prop-mortgage-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: rgba(92, 3, 155, 0.06);
  border: 1px dashed var(--border-purple);
  border-radius: var(--radius-sm);
  margin-bottom: 10px;
}

[data-theme="dark"] .prop-mortgage-banner {
  background: rgba(92, 3, 155, 0.15);
  border-color: var(--brand-purple-soft);
}

.cross-sell-icon {
  font-size: 1rem;
}

.cross-sell-text {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}

.cross-sell-text strong {
  font-size: 0.74rem;
  color: var(--brand-purple);
  font-weight: 700;
}

[data-theme="dark"] .cross-sell-text strong {
  color: var(--brand-lime-vivid);
}

.cross-sell-sub {
  font-size: 0.65rem;
  color: var(--text-muted);
}

.prop-info {
  padding: 12px 14px;
}

.prop-title {
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.prop-location {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.prop-specs {
  display: flex;
  gap: 10px;
  font-size: 0.74rem;
  color: var(--text-secondary);
  margin-bottom: 10px;
}

.prop-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.btn-card-action {
  font-size: 0.75rem;
  font-weight: 600;
  background: linear-gradient(135deg, var(--brand-purple-light), var(--brand-purple));
  color: #FFFFFF;
  border: 1px solid rgba(255, 255, 255, 0.15);
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-fast);
}

.btn-card-action:hover {
  background: linear-gradient(135deg, var(--brand-purple-vibrant), var(--brand-purple-light));
  transform: translateY(-1px);
}

.prop-link {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--brand-cyan);
  text-decoration: none;
  transition: color var(--transition-fast);
}

.prop-link:hover {
  color: var(--brand-purple);
  text-decoration: underline;
}
</style>
