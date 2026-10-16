<template>
  <div class="message-wrapper" :class="[message.role, { 'is-error': message.isError }]" :data-msg-id="message.id">
    <img v-if="message.role === 'assistant'" src="/xo-mascot.png" alt="XO" class="message-avatar" />

    <div class="message-bubble-container" :class="{ 'has-rich': message.metadata?.property_results?.length || message.metadata?.mortgage_result || handoff }">
      <div class="message-bubble" v-if="message.content || message.isStreaming">
        <div class="message-content" dir="auto">
          <div v-if="message.role === 'assistant'" class="md" v-html="rendered"></div>
          <span v-else class="plain-text">{{ message.content }}</span>
          <span v-if="message.isStreaming" class="streaming-cursor" aria-hidden="true"></span>
        </div>
      </div>

      <!-- Property recommendations (FR-8) -->
      <div class="property-results-container" v-if="message.metadata?.property_results?.length">
        <div class="property-results-header" v-if="message.metadata.results_are_alternatives">
          <span class="results-badge">{{ tr('alternatives') }}</span>
        </div>
        <div class="property-card-list">
          <article v-for="prop in message.metadata.property_results" :key="prop.id" class="prop-card" :class="{ 'is-expanded': expanded[prop.id] }">
            <div class="prop-compact-bar" @click="toggle(prop.id)">
              <div class="prop-thumb-wrap">
                <img v-if="prop.image_url" :src="prop.image_url" :alt="prop.title" class="prop-thumb-img" loading="lazy" />
                <span class="prop-ref-badge">#{{ prop.ref }}</span>
              </div>
              <div class="prop-compact-info">
                <h5 class="prop-compact-title" :title="prop.title">{{ prop.title }}</h5>
                <div class="prop-compact-sub">
                  <span class="prop-compact-loc"><XoIcon name="pin" :size="13" />{{ prop.community }}</span>
                  <span class="prop-compact-beds" v-if="bedsLabel(prop)">{{ bedsLabel(prop) }}</span>
                </div>
                <div class="prop-compact-price">{{ priceLabel(prop) }}</div>
                <div class="prop-source-row">
                  <span class="source-badge" :class="prop.source">{{ prop.source === 'live_offplan' ? tr('live_offplan') : tr('sample_listing') }}</span>
                  <span class="status-chip">{{ prop.status === 'off-plan' ? tr('off_plan') : tr('ready') }}</span>
                </div>
              </div>
              <div class="prop-compact-controls" @click.stop>
                <button type="button" class="prop-icon-btn" @click="$emit('ask', tr('save_prompt', { ref: prop.ref }))" :aria-label="tr('save_prompt', { ref: prop.ref })" :title="tr('save_prompt', { ref: prop.ref })">
                  <XoIcon name="heart" :size="16" />
                </button>
                <button type="button" class="prop-icon-btn" @click="toggle(prop.id)" :aria-expanded="!!expanded[prop.id]" :aria-label="expanded[prop.id] ? tr('hide') : tr('details')">
                  <XoIcon name="chevronDown" :size="16" class="expand-arrow" :class="{ rotated: expanded[prop.id] }" />
                </button>
              </div>
            </div>

            <div class="prop-expanded-drawer" v-show="expanded[prop.id]">
              <div class="prop-image-wrap" v-if="prop.image_url">
                <img :src="prop.image_url" :alt="prop.title" class="prop-image" loading="lazy" />
                <span class="badge-dev" v-if="prop.developer">{{ prop.developer }}</span>
              </div>
              <div class="prop-info">
                <p class="prop-location"><XoIcon name="pin" :size="14" />{{ prop.community }}<span v-if="prop.city">, {{ prop.city }}</span></p>
                <div class="prop-specs">
                  <span v-if="bedsLabel(prop)"><XoIcon name="bed" :size="14" />{{ bedsLabel(prop) }}</span>
                  <span v-if="prop.baths"><XoIcon name="bath" :size="14" />{{ prop.baths }}</span>
                  <span v-if="prop.size_sqft"><XoIcon name="area" :size="14" />{{ prop.size_sqft.toLocaleString() }} sq ft</span>
                  <span v-if="prop.completion">{{ tr('completion') }}: {{ prop.completion }}</span>
                </div>
                <div class="prop-amenities-row" v-if="prop.amenities?.length">
                  <span v-for="(a, i) in prop.amenities.slice(0, 4)" :key="i" class="amenity-chip">{{ a }}</span>
                </div>
                <div class="prop-mortgage-banner" v-if="prop.mortgage_estimate">
                  <strong>{{ tr('est_monthly') }}: AED {{ aed(prop.mortgage_estimate.monthly_payment_aed) }}</strong>
                  <span>{{ tr('down_payment') }} AED {{ aed(prop.mortgage_estimate.down_payment_aed) }} · {{ prop.mortgage_estimate.interest_rate_pct }}% · {{ prop.mortgage_estimate.tenure_years }} {{ tr('years') }}</span>
                  <span class="muted">{{ tr('estimate_only') }}</span>
                </div>
                <div class="prop-actions">
                  <button type="button" class="btn-card-action" @click="$emit('ask', tr('mortgage_this_prompt', { ref: prop.ref }))">
                    <XoIcon name="calculator" :size="15" />{{ tr('mortgage_this') }}
                  </button>
                  <a v-if="prop.listing_url" :href="prop.listing_url" target="_blank" rel="noopener noreferrer" class="prop-link">
                    {{ tr('view_details') }}<XoIcon name="external" :size="14" />
                  </a>
                </div>
              </div>
            </div>
          </article>
        </div>
      </div>

      <!-- Calculator result (FR-14, FR-15) -->
      <MortgageCard v-if="message.metadata?.mortgage_result" :data="message.metadata.mortgage_result" :language="language"
                    @ask="$emit('ask', $event)" />

      <!-- Advisor callback review card (FR-5): confirm or edit, then saved -->
      <HandoffCard v-if="handoff" :draft="handoff" :language="language" />

      <span class="message-timestamp">
        <XoIcon v-if="message.viaVoice" name="mic" :size="11" />
        {{ message.timestamp ? formatTime(message.timestamp) : '' }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive } from 'vue'
import MortgageCard from './MortgageCard.vue'
import HandoffCard from './HandoffCard.vue'
import XoIcon from '../shared/XoIcon.vue'
import { renderMarkdown } from '../../utils/markdown'
import { t, formatAed } from '../../i18n'

const props = defineProps({
  message: { type: Object, required: true },
  language: { type: String, default: 'en' }
})
defineEmits(['ask'])

const expanded = reactive({})
const toggle = (id) => { expanded[id] = !expanded[id] }
const tr = (key, vars) => t(props.language, key, vars)
const aed = (v) => formatAed(v, props.language)

const rendered = computed(() => renderMarkdown(props.message.content))
// Review card for a callback request; older saved chats only carry handoff_data.
const handoff = computed(() => {
  const m = props.message.metadata || {}
  if (m.handoff_draft) return m.handoff_draft
  return m.handoff_data?.lead_saved ? { ...m.handoff_data, status: 'saved' } : null
})

function bedsText(n) {
  return Number(n) === 0 ? tr('studio') : tr('beds', { n: Number(n) })
}

function bedsLabel(p) {
  if (p.beds_min === null || p.beds_min === undefined) return ''
  if (p.beds_max === null || p.beds_max === undefined || p.beds_max === p.beds_min) return bedsText(p.beds_min)
  return `${bedsText(p.beds_min)} – ${bedsText(p.beds_max)}`
}

function priceLabel(p) {
  if (!p.price_from) return tr('price_on_request')
  const ranged = p.price_to && p.price_to !== p.price_from
  return `${ranged ? tr('from') + ' ' : ''}AED ${aed(p.price_from)}`
}

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch (e) {
    return ''
  }
}
</script>

<style scoped>
/* Colours come from the widget tokens (--w-*) defined on .xo-widget in ChatWidget.vue */
.message-wrapper { display: flex; align-items: flex-start; gap: 8px; animation: msgIn 240ms ease both; }
.message-wrapper.user { justify-content: flex-end; }
@keyframes msgIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

.message-avatar {
  flex: none; width: 28px; height: 28px; margin-top: 2px; border-radius: 50%; object-fit: cover;
  background: #f4efff; box-shadow: 0 0 0 1.5px rgba(124, 44, 240, 0.35);
}

.message-bubble-container { display: flex; flex-direction: column; min-width: 0; max-width: 84%; }
.message-wrapper.user .message-bubble-container { align-items: flex-end; max-width: 82%; }
.message-bubble-container.has-rich { flex: 1 1 auto; max-width: calc(100% - 36px); }

.message-bubble { padding: 10px 14px; font-size: 0.92rem; line-height: 1.6; overflow-wrap: anywhere; }
.message-wrapper.assistant .message-bubble {
  align-self: flex-start;
  background: var(--w-bg, #fff); color: var(--w-ink, #0f172a);
  border: 1px solid var(--w-line, rgba(15, 23, 42, 0.08));
  border-radius: 6px 18px 18px 18px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.message-wrapper.user .message-bubble {
  background: linear-gradient(135deg, #6d14b8, #5c039b);
  color: #fff; border-radius: 18px 18px 6px 18px;
  box-shadow: 0 6px 16px -8px rgba(92, 3, 155, 0.7);
}
[dir="rtl"] .message-wrapper.assistant .message-bubble { border-radius: 18px 6px 18px 18px; }
[dir="rtl"] .message-wrapper.user .message-bubble { border-radius: 18px 18px 18px 6px; }
.message-wrapper.is-error .message-bubble { border-color: rgba(220, 38, 38, 0.35); background: rgba(220, 38, 38, 0.05); }
.plain-text { white-space: pre-wrap; }

.message-timestamp {
  display: inline-flex; align-items: center; gap: 4px; margin-top: 4px; padding: 0 4px;
  font-size: 0.68rem; color: var(--w-ink-2, #64748b);
}

.streaming-cursor {
  display: inline-block; width: 3px; height: 14px; margin-inline-start: 3px; vertical-align: -2px;
  border-radius: 2px; background: var(--w-brand-2, #7c2cf0); animation: cursorBlink 0.8s infinite;
}
@keyframes cursorBlink { 0%, 100% { opacity: 1; } 50% { opacity: 0.15; } }

/* Markdown */
.md :deep(p) { margin: 0 0 0.5em; }
.md :deep(p:last-child) { margin-bottom: 0; }
.md :deep(ul), .md :deep(ol) { margin: 0.25em 0 0.5em; padding-inline-start: 1.3em; }
.md :deep(li) { margin: 0.2em 0; }
.md :deep(li::marker) { color: var(--w-brand-2, #7c2cf0); font-weight: 600; }
.md :deep(strong) { font-weight: 650; }
.md :deep(h1), .md :deep(h2), .md :deep(h3), .md :deep(h4) { font-size: 1em; font-weight: 700; margin: 0.5em 0 0.3em; }
.md :deep(table) { border-collapse: collapse; width: 100%; margin: 0.4em 0; font-size: 0.85em; display: block; overflow-x: auto; }
.md :deep(th), .md :deep(td) { border: 1px solid var(--w-line, rgba(100, 116, 139, 0.3)); padding: 5px 8px; text-align: start; white-space: nowrap; }
.md :deep(th) { background: var(--w-chip, rgba(92, 3, 155, 0.06)); }
.md :deep(a) { color: var(--w-accent, #03a4f4); text-decoration: underline; text-underline-offset: 2px; }
.md :deep(code) { font-size: 0.9em; background: var(--w-chip, rgba(100, 116, 139, 0.12)); padding: 0 4px; border-radius: 4px; }

/* Property cards */
.property-results-container { margin-top: 8px; }
.property-results-header { margin-bottom: 8px; }
.results-badge {
  display: inline-block; padding: 3px 10px; border-radius: 999px;
  font-size: 0.7rem; font-weight: 700; letter-spacing: 0.02em; text-transform: uppercase;
  color: #0284c7; background: rgba(3, 164, 244, 0.1);
}
.property-card-list { display: flex; flex-direction: column; gap: 8px; }
.prop-card {
  overflow: hidden; background: var(--w-bg, #fff);
  border: 1px solid var(--w-line, rgba(15, 23, 42, 0.08)); border-radius: 16px;
  transition: box-shadow 180ms ease, border-color 180ms ease;
}
.prop-card:hover, .prop-card.is-expanded { border-color: rgba(124, 44, 240, 0.3); box-shadow: 0 10px 24px -14px rgba(38, 10, 74, 0.35); }
.prop-compact-bar { display: flex; align-items: center; gap: 12px; padding: 10px; cursor: pointer; }
.prop-thumb-wrap {
  position: relative; flex: none; width: 66px; height: 66px; overflow: hidden; border-radius: 12px;
  background: linear-gradient(135deg, rgba(124, 44, 240, 0.12), rgba(3, 164, 244, 0.12));
}
.prop-thumb-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.prop-ref-badge {
  position: absolute; top: 5px; inset-inline-start: 5px; padding: 1px 6px; border-radius: 999px;
  background: rgba(15, 23, 42, 0.72); color: #fff; font-size: 0.66rem; font-weight: 700;
}
.prop-compact-info { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.prop-compact-title {
  margin: 0; font-size: 0.88rem; font-weight: 650; color: var(--w-ink, #0f172a);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.prop-compact-sub { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; min-width: 0; font-size: 0.76rem; color: var(--w-ink-2, #64748b); }
.prop-compact-loc { display: inline-flex; align-items: center; gap: 3px; min-width: 0; }
.prop-compact-beds { padding: 1px 7px; border-radius: 6px; background: var(--w-chip, rgba(92, 3, 155, 0.06)); color: var(--w-ink, #0f172a); font-weight: 600; }
.prop-compact-price { font-family: var(--font-heading); font-size: 0.98rem; font-weight: 700; color: var(--w-brand, #5c039b); font-variant-numeric: tabular-nums; }
.prop-source-row { display: flex; flex-wrap: wrap; gap: 5px; }
.source-badge, .status-chip { padding: 2px 8px; border-radius: 999px; font-size: 0.66rem; font-weight: 600; }
.source-badge.live_offplan { background: rgba(100, 239, 10, 0.16); color: #15803d; }
.source-badge.sample { background: rgba(100, 116, 139, 0.12); color: var(--w-ink-2, #64748b); }
.status-chip { background: rgba(3, 164, 244, 0.1); color: #0284c7; }
[data-theme="dark"] .source-badge.live_offplan { color: #86ef3c; }
[data-theme="dark"] .status-chip { color: #38bdf8; }
.prop-compact-controls { display: flex; flex-direction: column; gap: 6px; flex: none; }
.prop-icon-btn {
  display: grid; place-items: center; width: 32px; height: 32px; border-radius: 50%; cursor: pointer;
  border: 1px solid var(--w-line, rgba(15, 23, 42, 0.08)); background: var(--w-bg, #fff); color: var(--w-ink-2, #64748b);
  transition: color 150ms ease, background 150ms ease;
}
.prop-icon-btn:hover { color: var(--w-brand, #5c039b); background: var(--w-chip, rgba(92, 3, 155, 0.06)); }
.expand-arrow { transition: transform 200ms ease; }
.expand-arrow.rotated { transform: rotate(180deg); }

.prop-expanded-drawer { border-top: 1px solid var(--w-line, rgba(15, 23, 42, 0.08)); animation: msgIn 200ms ease both; }
.prop-image-wrap { position: relative; aspect-ratio: 16 / 9; overflow: hidden; }
.prop-image { width: 100%; height: 100%; object-fit: cover; display: block; }
.badge-dev {
  position: absolute; top: 10px; inset-inline-start: 10px; padding: 3px 9px; border-radius: 999px;
  background: rgba(15, 23, 42, 0.72); color: #fff; font-size: 0.7rem; font-weight: 600;
}
.prop-info { display: flex; flex-direction: column; gap: 10px; padding: 12px; }
.prop-location { display: flex; align-items: center; gap: 4px; margin: 0; font-size: 0.82rem; color: var(--w-ink-2, #64748b); }
.prop-specs { display: flex; flex-wrap: wrap; gap: 6px 12px; font-size: 0.8rem; color: var(--w-ink, #0f172a); }
.prop-specs span { display: inline-flex; align-items: center; gap: 4px; }
.prop-amenities-row { display: flex; flex-wrap: wrap; gap: 5px; }
.amenity-chip { padding: 3px 9px; border-radius: 999px; font-size: 0.7rem; background: var(--w-chip, rgba(92, 3, 155, 0.06)); color: var(--w-ink, #0f172a); }
.prop-mortgage-banner {
  display: flex; flex-direction: column; gap: 2px; padding: 10px 12px; border-radius: 12px;
  background: linear-gradient(135deg, rgba(124, 44, 240, 0.08), rgba(3, 164, 244, 0.08));
  font-size: 0.76rem; color: var(--w-ink-2, #64748b);
}
.prop-mortgage-banner strong { font-size: 0.86rem; color: var(--w-ink, #0f172a); font-variant-numeric: tabular-nums; }
.prop-mortgage-banner .muted { opacity: 0.8; }
.prop-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.btn-card-action {
  display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border: 0; border-radius: 999px; cursor: pointer;
  background: linear-gradient(135deg, #5c039b, #7c2cf0); color: #fff; font-size: 0.78rem; font-weight: 600;
}
.btn-card-action:active { transform: scale(0.97); }
.prop-link { display: inline-flex; align-items: center; gap: 4px; font-size: 0.78rem; font-weight: 600; color: var(--w-accent, #03a4f4); text-decoration: none; }
.prop-link:hover { text-decoration: underline; }

@media (prefers-reduced-motion: reduce) {
  .message-wrapper, .prop-expanded-drawer, .streaming-cursor { animation: none; }
}
</style>
