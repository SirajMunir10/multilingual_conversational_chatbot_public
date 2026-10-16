<template>
  <div class="mortgage-card" :class="['verdict-' + (data.verdict || 'none'), { 'dbr-exceeded': dbr && dbr.within_cap === false }]">
    <div class="card-header">
      <div class="header-left">
        <span class="calc-icon"><XoIcon name="calculator" :size="18" /></span>
        <h4 class="calc-title">{{ isCheck ? (data.calculation_type === 'affordability' ? tr('afford_title') : tr('elig_title')) : tr('emi_title') }}</h4>
      </div>
      <span v-if="isCheck && data.verdict && data.verdict !== 'can_borrow'" class="verdict-badge">{{ tr('verdict_' + data.verdict) }}</span>
      <span v-else class="badge-estimates-not-offers">{{ tr('estimates_not_offers') }}</span>
    </div>

    <!-- Eligibility / affordability (approved build logic: gates, ceilings, verdict) -->
    <template v-if="isCheck">
      <div class="metric-spotlight">
        <template v-if="data.verdict === 'not_eligible'">
          <span class="spotlight-label">{{ tr('checks') }}</span>
          <div class="spotlight-value fail">{{ tr('gate_' + data.failed_gate) }} — {{ tr('gate_fail') }}</div>
        </template>
        <template v-else>
          <span class="spotlight-label">{{ data.verdict === 'can_borrow' ? tr('verdict_can_borrow') : tr('eligible_loan') }}</span>
          <div class="spotlight-value">AED {{ aed(data.eligible_loan_aed) }}</div>
          <p v-if="data.shortfall_aed > 0" class="shortfall">{{ tr('short_by') }} AED {{ aed(data.shortfall_aed) }} · {{ tr('tightest_limit') }}: {{ tr('limit_' + data.tightest_limit) }}</p>
          <div class="spotlight-submetrics">
            <div class="submetric-pill">
              <span class="submetric-label">{{ tr('monthly_payment') }}</span>
              <span class="submetric-val">AED {{ aed(data.instalment_aed) }}</span>
            </div>
            <div class="submetric-pill">
              <span class="submetric-label">{{ tr('stress_payment', { rate: data.stress_rate_pct }) }}</span>
              <span class="submetric-val">AED {{ aed(data.stress_instalment_aed) }}</span>
            </div>
            <div class="submetric-pill" v-if="data.max_property_price_aed">
              <span class="submetric-label">{{ data.verdict === 'can_borrow' ? tr('max_price') : tr('property_price') }}</span>
              <span class="submetric-val text-cyan">AED {{ aed(data.max_property_price_aed) }}</span>
            </div>
            <div class="submetric-pill">
              <span class="submetric-label">{{ tr('rate_tenure') }}</span>
              <span class="submetric-val">{{ data.interest_rate_pct }}% · {{ data.term_years }} {{ tr('years') }}</span>
            </div>
          </div>
        </template>
      </div>
      <p v-if="data.inputs?.residency === 'Non-resident'" class="card-note">{{ tr('note_non_resident') }}</p>
    </template>

    <!-- Monthly payment (EMI) -->
    <div v-else class="metric-spotlight">
      <span class="spotlight-label">{{ tr('monthly_payment') }}</span>
      <div class="spotlight-value">AED {{ aed(data.instalment_aed) }}</div>
      <div class="spotlight-submetrics">
        <div class="submetric-pill">
          <span class="submetric-label">{{ tr('loan_amount') }}</span>
          <span class="submetric-val text-cyan">AED {{ aed(data.loan_amount_aed) }}</span>
        </div>
        <div class="submetric-pill" v-if="data.down_payment_aed">
          <span class="submetric-label">{{ tr('down_payment') }}</span>
          <span class="submetric-val">AED {{ aed(data.down_payment_aed) }}</span>
        </div>
        <div class="submetric-pill">
          <span class="submetric-label">{{ tr('total_interest') }}</span>
          <span class="submetric-val">AED {{ aed(data.total_interest_aed) }}</span>
        </div>
        <div class="submetric-pill">
          <span class="submetric-label">{{ tr('rate_tenure') }}</span>
          <span class="submetric-val">{{ data.interest_rate_pct }}% · {{ data.tenure_years }} {{ tr('years') }}</span>
        </div>
      </div>
    </div>

    <button type="button" class="btn-toggle-mortgage-card" @click="isExpanded = !isExpanded" :aria-expanded="isExpanded">
      <span>{{ isExpanded ? tr('hide') : tr('details') }}</span>
      <XoIcon name="chevronDown" :size="15" class="toggle-arrow" :class="{ rotated: isExpanded }" />
    </button>

    <div class="mortgage-expanded-drawer" v-show="isExpanded">
      <template v-if="isCheck">
        <div class="breakdown-body" v-if="data.gates?.length">
          <div class="cost-row cost-heading"><span class="cost-label">{{ tr('checks') }}</span></div>
          <div class="cost-row" v-for="g in data.gates" :key="g.gate">
            <span class="cost-label">{{ tr('gate_' + g.gate) }}</span>
            <span class="gate-chip" :class="g.result">{{ tr('gate_' + g.result) }}</span>
          </div>
        </div>
        <div class="breakdown-body" v-if="data.ceilings_aed">
          <div class="cost-row cost-heading"><span class="cost-label">{{ tr('limits_title') }}</span></div>
          <div class="cost-row" v-for="(value, key) in data.ceilings_aed" :key="key" :class="{ tightest: key === data.tightest_limit }">
            <span class="cost-label">{{ tr('limit_' + key) }}<template v-if="key === 'ltv' && data.ltv_applied_pct"> ({{ data.ltv_applied_pct }}%)</template></span>
            <span class="cost-value">AED {{ aed(value) }}</span>
          </div>
        </div>
      </template>

      <div class="dbr-gauge-box" v-if="dbrPct !== null">
        <div class="dbr-title-row">
          <span class="dbr-title">{{ tr('debt_after') }}</span>
          <span class="dbr-badge" :class="dbr.within_cap === false ? 'badge-danger' : 'badge-success'">{{ dbrPct }}% / {{ dbr.max_ratio_pct }}%</span>
        </div>
        <div class="dbr-progress-track">
          <div class="dbr-progress-bar" :style="{ width: `${Math.min(dbrPct, 100)}%` }"></div>
        </div>
      </div>

      <div class="breakdown-section" v-if="cash">
        <div class="breakdown-body">
          <div class="cost-row cost-heading"><span class="cost-label">{{ tr('cash_upfront') }}</span></div>
          <div class="cost-row" v-for="item in cash.items" :key="item.item">
            <span class="cost-label">{{ tr('cash_' + item.item) }}</span>
            <span class="cost-value" v-if="item.amount_aed !== undefined">AED {{ aed(item.amount_aed) }}</span>
            <span class="cost-value" v-else>AED {{ aed(item.min_aed) }}–{{ aed(item.max_aed) }}</span>
          </div>
          <div class="cost-divider"></div>
          <div class="cost-row total-row">
            <span class="cost-label font-bold">{{ tr('total') }}</span>
            <span class="cost-value font-bold">AED {{ aed(cash.total_min_aed) }}–{{ aed(cash.total_max_aed) }}</span>
          </div>
        </div>
      </div>

      <div class="breakdown-section" v-if="costs">
        <div class="breakdown-body">
          <div class="cost-row cost-heading"><span class="cost-label font-bold">{{ tr('purchase_costs') }} ({{ costs.emirate }})</span></div>
          <div class="cost-row" v-for="item in costs.items" :key="item.item">
            <span class="cost-label">{{ item.item }}</span>
            <span class="cost-value">AED {{ aed(item.amount_aed) }}</span>
          </div>
        </div>
      </div>

      <div class="amortization-section" v-if="data.amortization_schedule?.length">
        <table class="amort-table">
          <thead>
            <tr><th>#</th><th>Principal</th><th>Interest</th><th>Balance</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in data.amortization_schedule" :key="row.year">
              <td class="font-bold">{{ row.year }}</td>
              <td class="text-emerald">{{ aed(row.principal_paid_aed) }}</td>
              <td class="text-ruby">{{ aed(row.interest_paid_aed) }}</td>
              <td class="text-cyan">{{ aed(row.remaining_balance_aed) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="distribution-section" v-if="data.principal_share_pct">
        <div class="distribution-bar-track">
          <div class="dist-bar principal-bar" :style="{ width: `${data.principal_share_pct}%` }"></div>
          <div class="dist-bar interest-bar" :style="{ width: `${data.interest_share_pct}%` }"></div>
        </div>
      </div>

      <p class="assumptions-line" v-if="data.assumptions?.length">{{ tr('assumptions') }}: {{ data.assumptions.join(' · ') }}</p>
    </div>

    <div class="mandatory-disclaimer-box" role="note">
      <XoIcon name="info" :size="15" class="disclaimer-icon" />
      <p class="disclaimer-text">{{ tr('estimate_only') }}</p>
    </div>

    <div class="card-actions" v-if="data.verdict === 'can_borrow' && data.max_property_price_aed > 0">
      <button type="button" class="btn-jump-properties"
              @click="$emit('ask', tr('show_matching_prompt', { budget: aed(data.max_property_price_aed) }))">
        <span>{{ tr('show_matching') }}</span>
        <XoIcon name="arrowDown" :size="15" class="action-arrow" />
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { t, formatAed } from '../../i18n'
import XoIcon from '../shared/XoIcon.vue'

const props = defineProps({
  data: { type: Object, required: true },
  language: { type: String, default: 'en' }
})
defineEmits(['ask'])

const isExpanded = ref(false)
const tr = (key, vars) => t(props.language, key, vars)
const aed = (v) => formatAed(v, props.language)

// Eligibility and affordability share one result shape (verdict, eligible loan, gates, ceilings).
const isCheck = computed(() => ['affordability', 'eligibility'].includes(props.data.calculation_type) && 'verdict' in props.data)
const dbr = computed(() => props.data.debt_burden || null)
const dbrPct = computed(() => {
  const d = dbr.value
  if (!d) return null
  const v = d.after_loan_pct ?? d.projected_ratio_pct
  return v === null || v === undefined ? null : v
})
const cash = computed(() => props.data.cash_upfront || null)
const costs = computed(() => props.data.purchase_costs || null)
</script>

<style scoped>
/* Colours come from the widget tokens (--w-*) defined on .xo-widget in ChatWidget.vue */
.mortgage-card {
  display: flex; flex-direction: column; gap: 12px; width: 100%; margin-top: 8px; padding: 14px;
  background: var(--w-bg, #fff); color: var(--w-ink, #0f172a);
  border: 1px solid var(--w-line, rgba(15, 23, 42, 0.08)); border-radius: 18px;
  box-shadow: 0 10px 24px -16px rgba(38, 10, 74, 0.35);
  font-variant-numeric: tabular-nums;
}
.mortgage-card.dbr-exceeded { border-color: rgba(244, 63, 94, 0.5); }

.card-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.header-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
.calc-icon {
  display: grid; place-items: center; width: 34px; height: 34px; border-radius: 10px; flex: none;
  background: linear-gradient(135deg, #5c039b, #7c2cf0); color: #fff;
}
.calc-title { margin: 0; font-family: var(--font-heading); font-size: 0.95rem; font-weight: 700; }
.badge-estimates-not-offers {
  padding: 3px 9px; border-radius: 999px; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.03em; text-transform: uppercase;
  color: var(--w-brand, #5c039b); background: var(--w-chip, rgba(92, 3, 155, 0.06));
}

.metric-spotlight {
  padding: 14px; border-radius: 14px;
  background: linear-gradient(135deg, rgba(124, 44, 240, 0.07), rgba(3, 164, 244, 0.07));
}
.spotlight-label { font-size: 0.72rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--w-ink-2, #64748b); }
.spotlight-value { margin-top: 2px; font-family: var(--font-heading); font-size: 1.7rem; font-weight: 800; line-height: 1.15; color: #15803d; }
[data-theme="dark"] .spotlight-value { color: #86ef3c; }
.spotlight-submetrics {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px;
  margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--w-line, rgba(15, 23, 42, 0.08));
}
.submetric-pill { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.submetric-label { font-size: 0.7rem; color: var(--w-ink-2, #64748b); }
.submetric-val { font-size: 0.86rem; font-weight: 700; color: var(--w-ink, #0f172a); overflow-wrap: anywhere; }
.submetric-val.text-cyan { color: #0284c7; }
[data-theme="dark"] .submetric-val.text-cyan { color: #38bdf8; }

.btn-toggle-mortgage-card {
  display: flex; align-items: center; justify-content: center; gap: 6px; width: 100%; padding: 8px 12px;
  border: 1px solid var(--w-line, rgba(15, 23, 42, 0.08)); border-radius: 12px; cursor: pointer;
  background: transparent; color: var(--w-brand, #5c039b); font-size: 0.78rem; font-weight: 600;
  transition: background 150ms ease;
}
.btn-toggle-mortgage-card:hover { background: var(--w-chip, rgba(92, 3, 155, 0.06)); }
.toggle-arrow { transition: transform 200ms ease; }
.toggle-arrow.rotated { transform: rotate(180deg); }

.mortgage-expanded-drawer { display: flex; flex-direction: column; gap: 12px; }
.dbr-gauge-box { display: flex; flex-direction: column; gap: 6px; }
.dbr-title-row { display: flex; align-items: center; justify-content: space-between; }
.dbr-title { font-size: 0.76rem; font-weight: 700; color: var(--w-ink-2, #64748b); }
.dbr-badge { padding: 2px 8px; border-radius: 999px; font-size: 0.72rem; font-weight: 700; }
.badge-success { background: rgba(34, 197, 94, 0.14); color: #15803d; }
.badge-danger { background: rgba(244, 63, 94, 0.14); color: #be123c; }
.dbr-progress-track { height: 6px; border-radius: 999px; background: var(--w-line, rgba(15, 23, 42, 0.08)); overflow: hidden; }
.dbr-progress-bar { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #22c55e, #03a4f4); }
.dbr-exceeded .dbr-progress-bar { background: linear-gradient(90deg, #f59e0b, #f43f5e); }

.breakdown-body { display: flex; flex-direction: column; gap: 6px; font-size: 0.8rem; }
.cost-row { display: flex; justify-content: space-between; gap: 12px; }
.cost-label { color: var(--w-ink-2, #64748b); }
.cost-value { font-weight: 600; text-align: end; white-space: nowrap; }
.cost-heading .cost-label, .font-bold { font-weight: 700; color: var(--w-ink, #0f172a); }
.cost-divider { height: 1px; background: var(--w-line, rgba(15, 23, 42, 0.08)); margin: 2px 0; }
.total-row .cost-value { color: #15803d; }
[data-theme="dark"] .total-row .cost-value { color: #86ef3c; }

.amortization-section { max-height: 220px; overflow: auto; border: 1px solid var(--w-line, rgba(15, 23, 42, 0.08)); border-radius: 12px; }
.amort-table { width: 100%; border-collapse: collapse; font-size: 0.74rem; }
.amort-table th {
  position: sticky; top: 0; padding: 6px 8px; text-align: end; font-weight: 600;
  background: var(--w-feed, #f7f6fb); color: var(--w-ink-2, #64748b);
}
.amort-table th:first-child, .amort-table td:first-child { text-align: start; }
.amort-table td { padding: 5px 8px; text-align: end; border-top: 1px solid var(--w-line, rgba(15, 23, 42, 0.08)); }
.text-emerald { color: #15803d; }
.text-ruby { color: #be123c; }
.text-cyan { color: #0284c7; }
[data-theme="dark"] .text-emerald { color: #86ef3c; }
[data-theme="dark"] .text-ruby { color: #fb7185; }
[data-theme="dark"] .text-cyan { color: #38bdf8; }

.distribution-bar-track { display: flex; height: 8px; border-radius: 999px; overflow: hidden; background: var(--w-line, rgba(15, 23, 42, 0.08)); }
.principal-bar { background: #22c55e; }
.interest-bar { background: #f43f5e; }
.assumptions-line { margin: 0; font-size: 0.72rem; color: var(--w-ink-2, #64748b); }

.verdict-badge { padding: 4px 10px; border-radius: 999px; font-size: 0.72rem; font-weight: 700; background: rgba(34, 197, 94, 0.14); color: #15803d; }
.verdict-eligible_lower .verdict-badge { background: rgba(245, 158, 11, 0.16); color: #b45309; }
.verdict-not_eligible .verdict-badge { background: rgba(244, 63, 94, 0.14); color: #be123c; }
.verdict-can_borrow .verdict-badge { background: rgba(3, 164, 244, 0.12); color: #0284c7; }
[data-theme="dark"] .verdict-badge { color: #86ef3c; }
[data-theme="dark"] .verdict-eligible_lower .verdict-badge { color: #fbbf24; }
[data-theme="dark"] .verdict-not_eligible .verdict-badge { color: #fb7185; }
[data-theme="dark"] .verdict-can_borrow .verdict-badge { color: #38bdf8; }
.spotlight-value.fail { font-size: 1.05rem; color: #be123c; }
.shortfall { margin: 4px 0 0; font-size: 0.78rem; color: #b45309; }
.card-note { margin: 0; font-size: 0.76rem; color: var(--w-ink-2, #64748b); }
.gate-chip { padding: 1px 8px; border-radius: 999px; font-size: 0.7rem; font-weight: 700; }
.gate-chip.pass { background: rgba(34, 197, 94, 0.14); color: #15803d; }
.gate-chip.review { background: rgba(245, 158, 11, 0.16); color: #b45309; }
.gate-chip.fail { background: rgba(244, 63, 94, 0.14); color: #be123c; }
.cost-row.tightest .cost-label, .cost-row.tightest .cost-value { color: var(--w-brand, #5c039b); font-weight: 700; }
.mandatory-disclaimer-box { display: flex; align-items: center; gap: 8px; color: var(--w-ink-2, #64748b); }
.disclaimer-icon { flex: none; }
.disclaimer-text { margin: 0; font-size: 0.74rem; }

.card-actions { display: flex; }
.btn-jump-properties {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px; width: 100%; padding: 10px 14px;
  border: 0; border-radius: 12px; cursor: pointer;
  background: linear-gradient(135deg, #5c039b, #7c2cf0); color: #fff; font-size: 0.82rem; font-weight: 600;
}
.btn-jump-properties:active { transform: scale(0.98); }
.action-arrow { transform: rotate(-90deg); }
[dir="rtl"] .action-arrow { transform: rotate(90deg); }

@container (max-width: 340px) {
  .spotlight-submetrics { grid-template-columns: minmax(0, 1fr); }
}
</style>
