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
      <div class="message-bubble" v-if="message.content || message.isStreaming">
        <div class="message-content">
          <span v-html="formattedContent"></span>
          <span v-if="message.isStreaming" class="streaming-cursor" aria-hidden="true"></span>
        </div>
      </div>

      <!-- Property Recommendations Display (FR-8) -->
      <div class="property-results-container" v-if="message.metadata?.property_results?.length">
        <div class="property-results-header">
          <span class="results-badge">Featured Listings (Live Inventory)</span>
          <span class="results-hint">Tap card or arrow to expand details</span>
        </div>
        <div class="property-card-list">
          <div 
            v-for="prop in message.metadata.property_results" 
            :key="prop.id" 
            class="prop-card"
            :class="{ 'is-expanded': isCardExpanded(prop.id) }"
          >
            <!-- 1. COMPACT / COLLAPSED PREVIEW BAR (Always visible, lightweight) -->
            <div class="prop-compact-bar" @click="toggleCardExpand(prop.id)">
              <div class="prop-thumb-wrap">
                <img :src="prop.image_url" :alt="prop.title" class="prop-thumb-img" loading="lazy" />
                <span class="prop-thumb-status" :class="prop.status">{{ prop.status === 'off-plan' ? 'Off-Plan' : 'Ready' }}</span>
              </div>

              <div class="prop-compact-info">
                <h5 class="prop-compact-title" :title="prop.title">{{ prop.title }}</h5>
                <div class="prop-compact-sub">
                  <span class="prop-compact-loc">📍 {{ prop.community }}</span>
                  <span class="prop-compact-beds">{{ prop.beds }} BHK</span>
                </div>
                <div class="prop-compact-price">
                  AED {{ formatNumber(prop.price) }}
                </div>
              </div>

              <div class="prop-compact-controls" @click.stop>
                <button 
                  type="button"
                  class="prop-shortlist-btn compact-heart" 
                  :class="{ 'is-saved': prop.is_shortlisted }"
                  @click="$emit('shortlist-property', prop)"
                  :title="prop.is_shortlisted ? 'Remove from shortlist' : 'Save to shortlist'"
                  aria-label="Save to shortlist"
                >
                  {{ prop.is_shortlisted ? '❤️' : '🤍' }}
                </button>
                <button 
                  type="button" 
                  class="prop-expand-btn"
                  @click="toggleCardExpand(prop.id)"
                  :aria-expanded="isCardExpanded(prop.id)"
                  :title="isCardExpanded(prop.id) ? 'Collapse card' : 'Expand full details'"
                >
                  <span class="expand-arrow" :class="{ 'rotated': isCardExpanded(prop.id) }">▼</span>
                </button>
              </div>
            </div>

            <!-- 2. EXPANDED CONTENT DRAWER (Revealed smoothly on click) -->
            <div class="prop-expanded-drawer" v-show="isCardExpanded(prop.id)">
              <div class="prop-image-wrap">
                <img :src="prop.image_url" :alt="prop.title" class="prop-image" loading="lazy" />
                <div class="prop-badges-top">
                  <span class="badge-status" :class="prop.status">{{ prop.status }}</span>
                  <span class="badge-dev" v-if="prop.developer">{{ prop.developer }}</span>
                </div>
                <span class="prop-price">AED {{ formatNumber(prop.price) }}</span>
              </div>
              <div class="prop-info">
                <p class="prop-location">📍 {{ prop.community }}, {{ prop.city }}</p>
                
                <div class="prop-specs">
                  <span>🛏️ {{ prop.beds }} Beds</span>
                  <span v-if="prop.baths && prop.baths > 0">🚿 {{ prop.baths }} Baths</span>
                  <span v-if="prop.sq_ft && prop.sq_ft > 0">📐 {{ prop.sq_ft }} sq.ft</span>
                  <span v-else>📐 Area on request</span>
                </div>

                <!-- Amenities Tags -->
                <div class="prop-amenities-row" v-if="prop.amenities?.length">
                  <span v-for="(amenity, i) in prop.amenities.slice(0, 4)" :key="i" class="amenity-chip">
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

                <button 
                  type="button" 
                  class="btn-collapse-drawer" 
                  @click="toggleCardExpand(prop.id)"
                >
                  ▲ Collapse Preview
                </button>
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

      <!-- Saved Properties Display (FR-21) -->
      <div class="account-card-container" v-if="message.metadata?.saved_properties?.length">
        <div class="account-card-header">
          <span class="account-badge">⭐ Saved Residences (User Account)</span>
          <span class="account-badge-sub">{{ message.metadata.saved_properties.length }} Shortlisted</span>
        </div>
        <div class="account-saved-list">
          <div v-for="prop in message.metadata.saved_properties" :key="prop.id" class="account-prop-item">
            <img :src="prop.image_url" :alt="prop.title" class="account-prop-thumb" loading="lazy" />
            <div class="account-prop-details">
              <h6 class="account-prop-title">{{ prop.title }}</h6>
              <span class="account-prop-sub">📍 {{ prop.community }} • {{ prop.beds }} BHK</span>
              <span class="account-prop-price">AED {{ formatNumber(prop.price) }}</span>
            </div>
            <button 
              type="button"
              class="account-prop-action-btn"
              @click="$emit('select-property-mortgage', prop)"
              title="Calculate Mortgage for this property"
            >
              🧮 Check EMI
            </button>
          </div>
        </div>
      </div>

      <!-- Application Status Display (FR-21) -->
      <div class="account-card-container" v-if="message.metadata?.application_status?.applications?.length">
        <div class="account-card-header">
          <span class="account-badge">📁 Application & Viewing Status (Vault & GRID)</span>
          <span class="account-badge-sub">{{ message.metadata.application_status.applications.length }} Records</span>
        </div>
        <div class="account-apps-list">
          <div v-for="app in message.metadata.application_status.applications" :key="app.application_id || app.lead_id" class="account-app-item">
            <div class="app-item-top">
              <span class="app-badge-crm" :class="app.crm?.toLowerCase()">{{ app.crm }}</span>
              <span class="app-title-text">{{ app.type || 'Application' }}</span>
              <span class="app-status-pill" :class="app.status">{{ app.status_label || app.status }}</span>
            </div>
            <div class="app-item-body">
              <div class="app-field" v-if="app.requested_loan_aed">
                <span class="label">Loan Requested:</span>
                <span class="val">AED {{ formatNumber(app.requested_loan_aed) }} ({{ app.lender_partner || 'Lender Partner' }})</span>
              </div>
              <div class="app-field" v-if="app.property_title">
                <span class="label">Property:</span>
                <span class="val">{{ app.property_title }}</span>
              </div>
              <div class="app-field" v-if="app.assigned_officer || app.assigned_agent">
                <span class="label">Assigned Specialist:</span>
                <span class="val">👤 {{ app.assigned_officer || app.assigned_agent }}</span>
              </div>
              <div class="app-field" v-if="app.scheduled_date">
                <span class="label">Scheduled Time:</span>
                <span class="val">📅 {{ app.scheduled_date }}</span>
              </div>
            </div>
            <div class="app-item-footer">
              <span class="app-ref-id">Ref: {{ app.application_id || app.lead_id }}</span>
              <span class="app-updated">{{ app.last_update || 'In Progress' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Human Handoff Status Card (FR-5, FR-20) -->
      <div class="handoff-card-container" v-if="message.metadata?.handoff_data">
        <div class="handoff-card-header">
          <div class="handoff-header-left">
            <span class="handoff-pulse-dot"></span>
            <span class="handoff-badge-title">Specialist Callback Scheduled</span>
          </div>
          <span class="handoff-ticket-id">Ticket #{{ message.metadata.handoff_data.ticket_id }}</span>
        </div>
        <div class="handoff-card-body">
          <div class="advisor-profile-row">
            <div class="advisor-avatar-box">
              <span class="advisor-icon">🏛️</span>
            </div>
            <div class="advisor-info-box">
              <h6 class="advisor-name">{{ message.metadata.handoff_data.assigned_advisor?.department || message.metadata.handoff_data.assigned_advisor?.name || 'UAE Advisory Department' }}</h6>
              <p class="advisor-title">{{ message.metadata.handoff_data.assigned_advisor?.title || 'Licensed Advisory Team' }}</p>
            </div>
          </div>
          <div class="handoff-client-summary-box" v-if="message.metadata.handoff_data.applicant_name || message.metadata.handoff_data.applicant_phone">
            <div class="client-detail-row" v-if="message.metadata.handoff_data.applicant_name">
              <span class="client-detail-lbl">Client:</span>
              <span class="client-detail-val">{{ message.metadata.handoff_data.applicant_name }}</span>
            </div>
            <div class="client-detail-row" v-if="message.metadata.handoff_data.applicant_phone">
              <span class="client-detail-lbl">Callback Contact:</span>
              <span class="client-detail-val">{{ message.metadata.handoff_data.applicant_phone }}</span>
            </div>
            <div class="client-detail-row" v-if="message.metadata.handoff_data.preferred_language">
              <span class="client-detail-lbl">Preferred Language:</span>
              <span class="client-detail-val">{{ message.metadata.handoff_data.preferred_language }}</span>
            </div>
          </div>
          <div class="handoff-metrics-badge">
            <span class="metrics-icon">📋</span>
            <span>Callback request registered. A licensed advisor will reach out to your provided phone number directly.</span>
          </div>
        </div>
      </div>

      <span class="message-timestamp">{{ message.timestamp ? formatTime(message.timestamp) : '' }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import MortgageCard from './MortgageCard.vue'

const props = defineProps({
  message: {
    type: Object,
    required: true
  }
})

defineEmits(['select-property-mortgage', 'jump-to-properties', 'shortlist-property'])

// Track expanded card state per property ID (default collapsed)
const expandedCards = ref({})

const isCardExpanded = (propId) => {
  return !!expandedCards.value[propId]
}

const toggleCardExpand = (propId) => {
  expandedCards.value[propId] = !expandedCards.value[propId]
}

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
  object-fit: contain;
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

.streaming-cursor {
  display: inline-block;
  width: 3px;
  height: 14px;
  background-color: var(--brand-purple, #5c039b);
  margin-left: 4px;
  vertical-align: -1px;
  border-radius: 1px;
  animation: cursorBlink 0.8s infinite;
}

[data-theme="dark"] .streaming-cursor {
  background-color: var(--brand-cyan, #03a4f4);
}

@keyframes cursorBlink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.15; }
}

/* Property Results Inside Chat */
.property-results-container {
  margin-top: 10px;
}

.property-results-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
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

.results-hint {
  font-size: 0.68rem;
  color: var(--text-muted);
}

.property-card-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.prop-card {
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  background: var(--bg-surface);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

[data-theme="dark"] .prop-card {
  border-color: var(--border-purple);
}

.prop-card:hover {
  border-color: var(--brand-purple);
  box-shadow: var(--shadow-md);
}

.prop-card.is-expanded {
  border-color: var(--brand-purple-light);
  box-shadow: 0 4px 16px rgba(92, 3, 155, 0.12);
}

/* 1. COMPACT COLLAPSED BAR STYLES */
.prop-compact-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  cursor: pointer;
  background: var(--bg-surface);
  transition: background var(--transition-fast);
}

.prop-compact-bar:hover {
  background: rgba(92, 3, 155, 0.04);
}

[data-theme="dark"] .prop-compact-bar:hover {
  background: rgba(92, 3, 155, 0.12);
}

.prop-thumb-wrap {
  position: relative;
  width: 62px;
  height: 62px;
  flex-shrink: 0;
  border-radius: var(--radius-sm);
  overflow: hidden;
  border: 1px solid var(--border-subtle);
}

.prop-thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.prop-thumb-status {
  position: absolute;
  bottom: 2px;
  left: 2px;
  font-size: 0.55rem;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 3px;
  background: rgba(15, 23, 42, 0.85);
  color: #fff;
  letter-spacing: 0.2px;
}

.prop-thumb-status.off-plan {
  color: var(--brand-cyan);
}

.prop-compact-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.prop-compact-title {
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.prop-compact-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.70rem;
  color: var(--text-muted);
}

.prop-compact-loc {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.prop-compact-beds {
  background: var(--bg-surface-elevated);
  padding: 1px 5px;
  border-radius: 3px;
  font-weight: 600;
  font-size: 0.65rem;
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
}

.prop-compact-price {
  font-size: 0.78rem;
  font-weight: 800;
  color: var(--brand-purple);
}

[data-theme="dark"] .prop-compact-price {
  color: var(--brand-lime-vivid);
}

.prop-compact-controls {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.compact-heart {
  position: static !important;
  width: 28px !important;
  height: 28px !important;
  font-size: 0.75rem !important;
  background: var(--bg-surface-elevated) !important;
  border: 1px solid var(--border-subtle) !important;
}

.prop-expand-btn {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(92, 3, 155, 0.08);
  border: 1px solid var(--border-purple);
  color: var(--brand-purple);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.prop-expand-btn:hover {
  background: var(--brand-purple);
  color: #fff;
  transform: scale(1.08);
}

.expand-arrow {
  font-size: 0.68rem;
  transition: transform 0.25s ease;
  display: inline-block;
}

.expand-arrow.rotated {
  transform: rotate(180deg);
}

/* 2. EXPANDED DRAWER STYLES */
.prop-expanded-drawer {
  border-top: 1px solid var(--border-subtle);
  animation: slideDownFade 0.25s ease-out;
}

@keyframes slideDownFade {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.btn-collapse-drawer {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  margin-top: 10px;
  padding: 6px;
  font-size: 0.70rem;
  font-weight: 600;
  color: var(--text-muted);
  background: transparent;
  border: 1px dashed var(--border-subtle);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-collapse-drawer:hover {
  color: var(--brand-purple);
  border-color: var(--border-purple);
  background: rgba(92, 3, 155, 0.04);
}

.prop-image-wrap {
  position: relative;
  height: 130px;
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

/* =========================================================================
   PHASE 6: ACCOUNT AWARENESS & HUMAN HANDOFF LUXURY STYLES
   ========================================================================= */

.account-card-container,
.handoff-card-container {
  margin-top: 10px;
  background: var(--bg-card);
  border: 1px solid var(--border-glass);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  box-shadow: var(--shadow-sm);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  animation: fadeIn 200ms ease;
}

.account-card-header,
.handoff-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-glass);
}

.account-badge,
.handoff-badge-title {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 6px;
}

.account-badge-sub,
.handoff-ticket-id {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--brand-purple);
  background: rgba(142, 68, 173, 0.1);
  padding: 2px 8px;
  border-radius: 12px;
  border: 1px solid rgba(142, 68, 173, 0.2);
}

/* Saved Properties List */
.account-saved-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.account-prop-item {
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border-glass);
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
}

.account-prop-item:hover {
  border-color: var(--brand-purple-light);
  transform: translateY(-1px);
}

.account-prop-thumb {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-sm);
  object-fit: cover;
  flex-shrink: 0;
}

.account-prop-details {
  flex: 1;
  min-width: 0;
}

.account-prop-title {
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 2px 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.account-prop-sub {
  font-size: 0.72rem;
  color: var(--text-secondary);
  display: block;
}

.account-prop-price {
  font-size: 0.76rem;
  font-weight: 700;
  color: var(--brand-purple);
}

.account-prop-action-btn {
  font-size: 0.72rem;
  font-weight: 600;
  background: linear-gradient(135deg, var(--brand-purple-light), var(--brand-purple));
  color: #FFFFFF;
  border: none;
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  white-space: nowrap;
  transition: all var(--transition-fast);
}

.account-prop-action-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(142, 68, 173, 0.3);
}

/* Application Status List */
.account-apps-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.account-app-item {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border-glass);
  border-radius: var(--radius-sm);
  padding: 10px;
}

.app-item-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.app-badge-crm {
  font-size: 0.68rem;
  font-weight: 800;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
}

.app-badge-crm.vault {
  background: rgba(243, 156, 18, 0.15);
  color: #f39c12;
  border: 1px solid rgba(243, 156, 18, 0.3);
}

.app-badge-crm.grid {
  background: rgba(52, 152, 219, 0.15);
  color: #3498db;
  border: 1px solid rgba(52, 152, 219, 0.3);
}

.app-title-text {
  font-size: 0.78rem;
  font-weight: 700;
  color: var(--text-primary);
  flex: 1;
}

.app-status-pill {
  font-size: 0.68rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 12px;
  background: rgba(46, 204, 113, 0.15);
  color: #2ecc71;
  border: 1px solid rgba(46, 204, 113, 0.3);
}

.app-status-pill.under_review {
  background: rgba(241, 196, 15, 0.15);
  color: #f1c40f;
  border-color: rgba(241, 196, 15, 0.3);
}

.app-item-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}

.app-field {
  font-size: 0.72rem;
  display: flex;
  gap: 6px;
}

.app-field .label {
  color: var(--text-secondary);
  font-weight: 500;
}

.app-field .val {
  color: var(--text-primary);
  font-weight: 600;
}

.app-item-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.68rem;
  color: var(--text-secondary);
  border-top: 1px dashed var(--border-glass);
  padding-top: 6px;
}

/* Human Handoff Card */
.handoff-header-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.handoff-pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #2ecc71;
  box-shadow: 0 0 8px #2ecc71;
  animation: pulse 1.5s infinite;
}

.advisor-profile-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.advisor-avatar-box {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(142, 68, 173, 0.2), rgba(0, 210, 255, 0.2));
  border: 1px solid var(--border-glass);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.4rem;
  flex-shrink: 0;
}

.advisor-name {
  font-size: 0.88rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.advisor-title {
  font-size: 0.74rem;
  color: var(--brand-purple);
  margin: 2px 0;
  font-weight: 600;
}

.advisor-license {
  font-size: 0.68rem;
  color: var(--text-secondary);
}

.handoff-metrics-badge {
  font-size: 0.72rem;
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.04);
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-glass);
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
}

.handoff-client-summary-box {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border-glass);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  margin-bottom: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.client-detail-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.75rem;
}

.client-detail-lbl {
  color: var(--text-secondary);
  font-weight: 600;
}

.client-detail-val {
  color: var(--text-primary);
  font-weight: 700;
}

@media (max-width: 480px) {
  .message-bubble-container {
    max-width: 95%;
  }

  .message-bubble {
    padding: 8px 12px;
    font-size: 0.85rem;
  }

  .prop-thumb-wrap {
    width: 52px;
    height: 52px;
  }

  .prop-compact-bar {
    gap: 8px;
    padding: 6px 8px;
  }

  .prop-compact-title {
    font-size: 0.78rem;
  }

  .prop-compact-price {
    font-size: 0.74rem;
  }

  .compact-heart,
  .prop-expand-btn {
    width: 26px !important;
    height: 26px !important;
  }

  .handoff-actions-row {
    flex-direction: column;
  }
}
</style>
