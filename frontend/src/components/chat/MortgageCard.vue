<template>
  <div class="mortgage-card glass-card" :class="{ 'dbr-exceeded': isDbrExceeded }">
    <!-- Card Header with Mandatory Badge (Rule 10) -->
    <div class="card-header">
      <div class="header-left">
        <span class="calc-icon">{{ isAffordability ? '📊' : '🧮' }}</span>
        <h4 class="calc-title">
          {{ isAffordability ? 'Mortgage Affordability Estimate' : 'Mortgage Payment & EMI Estimate' }}
        </h4>
      </div>
      <!-- Rule 10 Mandatory Label: "estimates, not offers" -->
      <span class="badge-estimates-not-offers">estimates, not offers</span>
    </div>

    <!-- Primary Metric Spotlight -->
    <div class="metric-spotlight">
      <div class="spotlight-content">
        <span class="spotlight-label">
          {{ isAffordability ? 'Max Estimated Monthly Payment' : 'Estimated Monthly Installment (EMI)' }}
        </span>
        <div class="spotlight-value text-lime">
          AED {{ formatNumber(monthlyInstallment) }}
          <span class="per-month">/ month</span>
        </div>
      </div>
      <div class="spotlight-submetrics">
        <div class="submetric-pill">
          <span class="submetric-label">Max Borrowing Capacity</span>
          <span class="submetric-val text-cyan">AED {{ formatNumber(loanCapacity) }}</span>
        </div>
        <div class="submetric-pill" v-if="propertyPrice">
          <span class="submetric-label">Affordable Property Price</span>
          <span class="submetric-val text-emerald">AED {{ formatNumber(propertyPrice) }}</span>
        </div>
        <div class="submetric-pill">
          <span class="submetric-label">Rate & Tenure</span>
          <span class="submetric-val">{{ interestRate }}% · {{ tenureYears }} Yrs</span>
        </div>
      </div>
    </div>

    <!-- Visual DBR Gauge (UAE Central Bank 50% Regulatory Cap) -->
    <div class="dbr-gauge-box" v-if="dbrStatus">
      <div class="dbr-gauge-header">
        <div class="dbr-title-row">
          <span class="dbr-title">Debt Burden Ratio (DBR)</span>
          <span class="dbr-badge" :class="dbrBadgeClass">
            {{ isDbrExceeded ? 'Exceeds 50% Cap' : 'Within Central Bank Limit' }}
          </span>
        </div>
        <span class="dbr-reg-note">UAE Central Bank Max: 50%</span>
      </div>

      <!-- DBR Progress Track -->
      <div class="dbr-progress-track">
        <div 
          class="dbr-progress-bar"
          :style="{ 
            width: `${Math.min(projectedDbrPct, 100)}%`,
            backgroundColor: dbrBarColor
          }"
        ></div>
        <!-- 50% Cap Marker Line -->
        <div class="dbr-cap-marker" title="UAE Central Bank 50% Cap">
          <span class="marker-flag">50% Max Cap</span>
        </div>
      </div>

      <div class="dbr-readouts">
        <span class="dbr-current" v-if="currentDbrPct > 0">
          Existing Commitments: <strong>{{ currentDbrPct }}%</strong>
        </span>
        <span class="dbr-projected">
          Projected Total DBR: <strong>{{ projectedDbrPct }}%</strong>
        </span>
      </div>
    </div>

    <!-- Purchase Costs Breakdown (Expandable Drawer) -->
    <div class="breakdown-section" v-if="upfrontCosts">
      <button 
        type="button" 
        class="toggle-section-btn" 
        @click="showCosts = !showCosts"
        :aria-expanded="showCosts"
      >
        <span>💼 Upfront Purchase Costs & Fees Breakdown</span>
        <span class="toggle-icon">{{ showCosts ? '▲' : '▼' }}</span>
      </button>

      <div class="breakdown-body" v-if="showCosts">
        <div class="cost-row">
          <span class="cost-label">Down Payment (Equity)</span>
          <span class="cost-value font-mono">AED {{ formatNumber(upfrontCosts.down_payment_aed) }}</span>
        </div>
        <div class="cost-row">
          <span class="cost-label">DLD Transfer Fee (4% + admin)</span>
          <span class="cost-value font-mono">AED {{ formatNumber(upfrontCosts.dld_transfer_fee_aed) }}</span>
        </div>
        <div class="cost-row">
          <span class="cost-label">Agency Broker Fee (2% + VAT)</span>
          <span class="cost-value font-mono">AED {{ formatNumber(upfrontCosts.agency_broker_fee_aed) }}</span>
        </div>
        <div class="cost-row">
          <span class="cost-label">Mortgage Registration (0.25% + admin)</span>
          <span class="cost-value font-mono">AED {{ formatNumber(upfrontCosts.mortgage_registration_fee_aed) }}</span>
        </div>
        <div class="cost-row">
          <span class="cost-label">Bank Processing & Valuation</span>
          <span class="cost-value font-mono">
            AED {{ formatNumber(upfrontCosts.bank_processing_fee_aed + upfrontCosts.property_valuation_fee_aed) }}
          </span>
        </div>
        <div class="cost-divider"></div>
        <div class="cost-row total-row">
          <span class="cost-label font-bold">Total Upfront Cash Required</span>
          <span class="cost-value text-lime font-bold font-mono">
            AED {{ formatNumber(upfrontCosts.total_cash_required_at_purchase_aed) }}
          </span>
        </div>
      </div>
    </div>

    <!-- Amortization Schedule (Collapsible) -->
    <div class="amortization-section" v-if="amortizationSample && amortizationSample.length">
      <button 
        type="button" 
        class="toggle-section-btn" 
        @click="showAmortization = !showAmortization"
        :aria-expanded="showAmortization"
      >
        <span>📅 Amortization Schedule (Sample Years 1–5)</span>
        <span class="toggle-icon">{{ showAmortization ? '▲' : '▼' }}</span>
      </button>

      <div class="amortization-body" v-if="showAmortization">
        <table class="amort-table">
          <thead>
            <tr>
              <th>Year</th>
              <th>Principal Paid</th>
              <th>Interest Paid</th>
              <th>Remaining Balance</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in amortizationSample" :key="row.year">
              <td class="font-bold">{{ row.year }}</td>
              <td class="text-emerald font-mono">AED {{ formatNumber(row.principal_paid) }}</td>
              <td class="text-ruby font-mono">AED {{ formatNumber(row.interest_paid) }}</td>
              <td class="text-cyan font-mono">AED {{ formatNumber(row.remaining_balance) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Principal vs Interest Breakdown Bar (for EMI calculations) -->
    <div class="distribution-section" v-if="breakdownPct">
      <div class="distribution-header">
        <span>Principal vs Interest Distribution</span>
        <span>{{ breakdownPct.principal_pct }}% Principal / {{ breakdownPct.interest_pct }}% Interest</span>
      </div>
      <div class="distribution-bar-track">
        <div 
          class="dist-bar principal-bar" 
          :style="{ width: `${breakdownPct.principal_pct}%` }"
          title="Principal portion"
        ></div>
        <div 
          class="dist-bar interest-bar" 
          :style="{ width: `${breakdownPct.interest_pct}%` }"
          title="Interest portion"
        ></div>
      </div>
    </div>

    <!-- Rule 10 Mandatory Disclaimer Block: "estimate only, subject to lender approval" -->
    <div class="mandatory-disclaimer-box" role="note">
      <span class="disclaimer-icon">⚠️</span>
      <p class="disclaimer-text">
        <strong>Disclaimer:</strong> estimate only, subject to lender approval. All calculation outputs are indicative estimates and not formal loan offers. Actual terms, rates, and qualification depend on comprehensive credit assessment by UAE Central Bank licensed partner institutions.
      </p>
    </div>

    <!-- FR-15 Direct Jump to Matching Properties Action Button -->
    <div class="card-actions" v-if="propertyPrice || loanCapacity">
      <button 
        type="button" 
        class="btn-jump-properties"
        @click="handleJumpToProperties"
        id="btn-mortgage-jump-properties"
      >
        <span>🏢 View Matching Properties in Budget (~AED {{ formatNumber(recommendedBudget) }})</span>
        <span class="action-arrow">↗</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  data: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['jump-to-properties'])

const showCosts = ref(false)
const showAmortization = ref(false)

const isAffordability = computed(() => {
  return props.data.calculation_type === 'affordability' || !!props.data.affordability_summary
})

const summary = computed(() => {
  return props.data.affordability_summary || null
})

const monthlyInstallment = computed(() => {
  if (summary.value) {
    return summary.value.max_allowable_monthly_emi_aed || summary.value.max_dbr_allowable_installment_aed || 0
  }
  return props.data.periodic_installment_aed || 0
})

const loanCapacity = computed(() => {
  if (summary.value) {
    return summary.value.max_borrowing_capacity_aed || 0
  }
  return props.data.loan_amount_aed || 0
})

const propertyPrice = computed(() => {
  if (summary.value) {
    return summary.value.max_property_price_aed || 0
  }
  return props.data.loan_amount_aed ? Math.round(props.data.loan_amount_aed * 1.25) : 0
})

const interestRate = computed(() => {
  if (summary.value) {
    return summary.value.assumed_interest_rate_pct || 4.49
  }
  return props.data.interest_rate_pct || 4.49
})

const tenureYears = computed(() => {
  if (summary.value) {
    return summary.value.tenure_years || 25
  }
  return props.data.tenure_years || 25
})

const dbrStatus = computed(() => {
  return props.data.dbr_status || null
})

const currentDbrPct = computed(() => {
  return dbrStatus.value?.current_dbr_pct || 0
})

const projectedDbrPct = computed(() => {
  return dbrStatus.value?.projected_dbr_pct || 0
})

const isDbrExceeded = computed(() => {
  return dbrStatus.value?.dbr_cap_exceeded || projectedDbrPct.value > 50.0
})

const dbrBadgeClass = computed(() => {
  if (isDbrExceeded.value) return 'badge-danger'
  if (projectedDbrPct.value > 40) return 'badge-warning'
  return 'badge-success'
})

const dbrBarColor = computed(() => {
  if (isDbrExceeded.value) return 'var(--ruby-primary, #f43f5e)'
  if (projectedDbrPct.value > 40) return 'var(--gold-primary, #d4af37)'
  return 'var(--emerald-primary, #10b981)'
})

const upfrontCosts = computed(() => {
  return props.data.upfront_costs_breakdown || null
})

const amortizationSample = computed(() => {
  return props.data.amortization_sample || []
})

const breakdownPct = computed(() => {
  return props.data.breakdown_pct || null
})

const recommendedBudget = computed(() => {
  if (props.data.jump_to_properties?.recommended_budget_max) {
    return props.data.jump_to_properties.recommended_budget_max
  }
  return propertyPrice.value || loanCapacity.value
})

const handleJumpToProperties = () => {
  emit('jump-to-properties', recommendedBudget.value)
}

const formatNumber = (num) => {
  if (!num && num !== 0) return '0'
  return Math.round(Number(num)).toLocaleString()
}
</script>

<style scoped>
.mortgage-card {
  width: 100%;
  border-radius: var(--radius-md);
  padding: 16px;
  margin-top: 12px;
  background: var(--bg-surface);
  border: 1px solid var(--border-purple);
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  gap: 14px;
  color: var(--text-primary);
  transition: all var(--transition-normal);
}

.mortgage-card.dbr-exceeded {
  border-color: rgba(244, 63, 94, 0.6);
  box-shadow: 0 4px 16px rgba(244, 63, 94, 0.15);
}

/* Header */
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.calc-icon {
  font-size: 1.25rem;
}

.calc-title {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--text-primary);
  font-family: var(--font-heading);
}

/* Mandatory Label (Rule 10) */
.badge-estimates-not-offers {
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 3px 10px;
  border-radius: var(--radius-full);
  background: rgba(92, 3, 155, 0.08);
  color: var(--brand-purple);
  border: 1px solid var(--border-purple);
}

[data-theme="dark"] .badge-estimates-not-offers {
  background: rgba(92, 3, 155, 0.25);
  color: var(--brand-cyan);
}

/* Spotlight */
.metric-spotlight {
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.spotlight-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.spotlight-label {
  font-size: 0.74rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 600;
}

.spotlight-value {
  font-size: 1.55rem;
  font-weight: 800;
  font-family: var(--font-heading);
  letter-spacing: -0.02em;
  display: flex;
  align-items: baseline;
  gap: 6px;
  color: var(--brand-purple);
}

[data-theme="dark"] .spotlight-value {
  color: var(--brand-lime-vivid);
}

.per-month {
  font-size: 0.82rem;
  font-weight: 500;
  color: var(--text-muted);
}

.spotlight-submetrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle);
}

.submetric-pill {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.submetric-label {
  font-size: 0.70rem;
  color: var(--text-muted);
}

.submetric-val {
  font-size: 0.86rem;
  font-weight: 600;
  font-family: monospace;
}

/* DBR Gauge */
.dbr-gauge-box {
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dbr-gauge-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.76rem;
}

.dbr-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dbr-title {
  font-weight: 600;
  color: var(--text-secondary);
}

.dbr-reg-note {
  font-size: 0.70rem;
  color: var(--text-muted);
}

.dbr-badge {
  font-size: 0.65rem;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: var(--radius-full);
}

.badge-success {
  background: rgba(22, 163, 74, 0.12);
  color: var(--brand-lime);
  border: 1px solid var(--border-lime);
}

.badge-warning {
  background: rgba(234, 179, 8, 0.12);
  color: #B45309;
  border: 1px solid rgba(234, 179, 8, 0.35);
}

.badge-danger {
  background: rgba(244, 63, 94, 0.12);
  color: #E11D48;
  border: 1px solid rgba(244, 63, 94, 0.35);
}

.dbr-progress-track {
  position: relative;
  width: 100%;
  height: 8px;
  background: var(--border-prominent);
  border-radius: var(--radius-full);
  overflow: visible;
}

.dbr-progress-bar {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width var(--transition-smooth);
}

.dbr-cap-marker {
  position: absolute;
  left: 50%;
  top: -4px;
  bottom: -4px;
  width: 2px;
  background: #E11D48;
  box-shadow: 0 0 6px rgba(225, 29, 72, 0.4);
}

.marker-flag {
  position: absolute;
  top: -18px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.62rem;
  font-weight: 700;
  color: #E11D48;
  white-space: nowrap;
}

.dbr-readouts {
  display: flex;
  justify-content: space-between;
  font-size: 0.72rem;
  color: var(--text-muted);
  margin-top: 4px;
}

/* Expandable breakdown sections */
.breakdown-section, .amortization-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.toggle-section-btn {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  color: var(--text-secondary);
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.toggle-section-btn:hover {
  background: var(--bg-surface-hover);
  color: var(--text-primary);
}

.toggle-icon {
  font-size: 0.65rem;
  color: var(--brand-purple);
}

[data-theme="dark"] .toggle-icon {
  color: var(--brand-cyan);
}

.breakdown-body {
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 0.76rem;
}

.cost-row {
  display: flex;
  justify-content: space-between;
  color: var(--text-secondary);
}

.cost-divider {
  height: 1px;
  background: var(--border-subtle);
  margin: 4px 0;
}

.total-row {
  font-size: 0.85rem;
}

/* Amortization Table */
.amort-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.72rem;
  text-align: left;
}

.amort-table th, .amort-table td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.amort-table th {
  color: var(--text-muted);
  font-weight: 600;
  text-transform: uppercase;
  font-size: 0.66rem;
}

/* Distribution Bar */
.distribution-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 0.72rem;
  color: var(--text-muted);
}

.distribution-header {
  display: flex;
  justify-content: space-between;
}

.distribution-bar-track {
  width: 100%;
  height: 8px;
  display: flex;
  border-radius: var(--radius-full);
  overflow: hidden;
  background: var(--border-prominent);
}

.dist-bar.principal-bar {
  background: var(--brand-lime);
}

.dist-bar.interest-bar {
  background: #E11D48;
}

/* Mandatory Disclaimer Banner (Rule 10) */
.mandatory-disclaimer-box {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  background: rgba(92, 3, 155, 0.05);
  border: 1px solid var(--border-purple);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
}

[data-theme="dark"] .mandatory-disclaimer-box {
  background: rgba(92, 3, 155, 0.12);
}

.disclaimer-icon {
  font-size: 0.95rem;
  flex-shrink: 0;
  margin-top: 1px;
}

.disclaimer-text {
  margin: 0;
  font-size: 0.72rem;
  line-height: 1.4;
  color: var(--text-muted);
}

.disclaimer-text strong {
  color: var(--brand-purple);
}

[data-theme="dark"] .disclaimer-text strong {
  color: var(--brand-cyan);
}

/* Action Button (FR-15) */
.card-actions {
  display: flex;
  margin-top: 4px;
}

.btn-jump-properties {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: linear-gradient(135deg, var(--brand-purple-light), var(--brand-purple));
  color: #FFFFFF;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: var(--radius-sm);
  padding: 10px 16px;
  font-size: 0.84rem;
  font-weight: 700;
  font-family: var(--font-heading);
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-fast);
}

.btn-jump-properties:hover {
  background: linear-gradient(135deg, var(--brand-purple-vibrant), var(--brand-purple-light));
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.action-arrow {
  font-size: 1rem;
  transition: transform var(--transition-fast);
}

.btn-jump-properties:hover .action-arrow {
  transform: translateX(2px) translateY(-2px);
}

/* Text color utilities */
.text-lime { color: var(--brand-lime); }
.text-gold { color: var(--brand-purple); }
[data-theme="dark"] .text-gold { color: var(--brand-lime-vivid); }
.text-cyan { color: var(--brand-cyan); }
.text-emerald { color: var(--brand-lime); }
.text-ruby { color: #E11D48; }
.font-mono { font-family: monospace; }
.font-bold { font-weight: 700; }
</style>
