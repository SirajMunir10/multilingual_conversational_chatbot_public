'use client'
import { useState } from 'react'
import { t, formatAed } from '../i18n'
import XoIcon from './XoIcon'

const cx = (...names) => names.filter(Boolean).join(' ')

export default function MortgageCard({ data, language = 'en', onAsk }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const tr = (key, vars) => t(language, key, vars)
  const aed = (v) => formatAed(v, language)

  // Eligibility and affordability share one result shape (verdict, eligible loan, gates, ceilings).
  const isCheck = ['affordability', 'eligibility'].includes(data.calculation_type) && 'verdict' in data
  const dbr = data.debt_burden || null
  const dbrValue = dbr ? (dbr.after_loan_pct ?? dbr.projected_ratio_pct) : null
  const dbrPct = dbrValue === null || dbrValue === undefined ? null : dbrValue
  const cash = data.cash_upfront || null
  const costs = data.purchase_costs || null

  return (
    <div className={cx('mortgage-card', 'verdict-' + (data.verdict || 'none'), dbr && dbr.within_cap === false && 'dbr-exceeded')}>
      <div className="card-header">
        <div className="header-left">
          <span className="calc-icon"><XoIcon name="calculator" size={18} /></span>
          <h4 className="calc-title">{isCheck ? (data.calculation_type === 'affordability' ? tr('afford_title') : tr('elig_title')) : tr('emi_title')}</h4>
        </div>
        {isCheck && data.verdict && data.verdict !== 'can_borrow'
          ? <span className="verdict-badge">{tr('verdict_' + data.verdict)}</span>
          : <span className="badge-estimates-not-offers">{tr('estimates_not_offers')}</span>}
      </div>

      {isCheck ? (
        <>
          {/* Eligibility / affordability (approved build logic: gates, ceilings, verdict) */}
          <div className="metric-spotlight">
            {data.verdict === 'not_eligible' ? (
              <>
                <span className="spotlight-label">{tr('checks')}</span>
                <div className="spotlight-value fail">{tr('gate_' + data.failed_gate)} — {tr('gate_fail')}</div>
              </>
            ) : (
              <>
                <span className="spotlight-label">{data.verdict === 'can_borrow' ? tr('verdict_can_borrow') : tr('eligible_loan')}</span>
                <div className="spotlight-value">AED {aed(data.eligible_loan_aed)}</div>
                {data.shortfall_aed > 0 && (
                  <p className="shortfall">{tr('short_by')} AED {aed(data.shortfall_aed)} · {tr('tightest_limit')}: {tr('limit_' + data.tightest_limit)}</p>
                )}
                <div className="spotlight-submetrics">
                  <div className="submetric-pill">
                    <span className="submetric-label">{tr('monthly_payment')}</span>
                    <span className="submetric-val">AED {aed(data.instalment_aed)}</span>
                  </div>
                  <div className="submetric-pill">
                    <span className="submetric-label">{tr('stress_payment', { rate: data.stress_rate_pct })}</span>
                    <span className="submetric-val">AED {aed(data.stress_instalment_aed)}</span>
                  </div>
                  {data.max_property_price_aed ? (
                    <div className="submetric-pill">
                      <span className="submetric-label">{data.verdict === 'can_borrow' ? tr('max_price') : tr('property_price')}</span>
                      <span className="submetric-val text-cyan">AED {aed(data.max_property_price_aed)}</span>
                    </div>
                  ) : null}
                  <div className="submetric-pill">
                    <span className="submetric-label">{tr('rate_tenure')}</span>
                    <span className="submetric-val">{data.interest_rate_pct}% · {data.term_years} {tr('years')}</span>
                  </div>
                </div>
              </>
            )}
          </div>
          {data.inputs?.residency === 'Non-resident' && <p className="card-note">{tr('note_non_resident')}</p>}
        </>
      ) : (
        /* Monthly payment (EMI) */
        <div className="metric-spotlight">
          <span className="spotlight-label">{tr('monthly_payment')}</span>
          <div className="spotlight-value">AED {aed(data.instalment_aed)}</div>
          <div className="spotlight-submetrics">
            <div className="submetric-pill">
              <span className="submetric-label">{tr('loan_amount')}</span>
              <span className="submetric-val text-cyan">AED {aed(data.loan_amount_aed)}</span>
            </div>
            {data.down_payment_aed ? (
              <div className="submetric-pill">
                <span className="submetric-label">{tr('down_payment')}</span>
                <span className="submetric-val">AED {aed(data.down_payment_aed)}</span>
              </div>
            ) : null}
            <div className="submetric-pill">
              <span className="submetric-label">{tr('total_interest')}</span>
              <span className="submetric-val">AED {aed(data.total_interest_aed)}</span>
            </div>
            <div className="submetric-pill">
              <span className="submetric-label">{tr('rate_tenure')}</span>
              <span className="submetric-val">{data.interest_rate_pct}% · {data.tenure_years} {tr('years')}</span>
            </div>
          </div>
        </div>
      )}

      <button type="button" className="btn-toggle-mortgage-card" onClick={() => setIsExpanded(!isExpanded)} aria-expanded={isExpanded}>
        <span>{isExpanded ? tr('hide') : tr('details')}</span>
        <XoIcon name="chevronDown" size={15} className={cx('toggle-arrow', isExpanded && 'rotated')} />
      </button>

      <div className="mortgage-expanded-drawer" style={isExpanded ? undefined : { display: 'none' }}>
        {isCheck && (
          <>
            {data.gates?.length > 0 && (
              <div className="breakdown-body">
                <div className="cost-row cost-heading"><span className="cost-label">{tr('checks')}</span></div>
                {data.gates.map((g) => (
                  <div className="cost-row" key={g.gate}>
                    <span className="cost-label">{tr('gate_' + g.gate)}</span>
                    <span className={cx('gate-chip', g.result)}>{tr('gate_' + g.result)}</span>
                  </div>
                ))}
              </div>
            )}
            {data.ceilings_aed && (
              <div className="breakdown-body">
                <div className="cost-row cost-heading"><span className="cost-label">{tr('limits_title')}</span></div>
                {Object.entries(data.ceilings_aed).map(([key, value]) => (
                  <div className={cx('cost-row', key === data.tightest_limit && 'tightest')} key={key}>
                    <span className="cost-label">{tr('limit_' + key)}{key === 'ltv' && data.ltv_applied_pct ? <> ({data.ltv_applied_pct}%)</> : null}</span>
                    <span className="cost-value">AED {aed(value)}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {dbrPct !== null && (
          <div className="dbr-gauge-box">
            <div className="dbr-title-row">
              <span className="dbr-title">{tr('debt_after')}</span>
              <span className={cx('dbr-badge', dbr.within_cap === false ? 'badge-danger' : 'badge-success')}>{dbrPct}% / {dbr.max_ratio_pct}%</span>
            </div>
            <div className="dbr-progress-track">
              <div className="dbr-progress-bar" style={{ width: `${Math.min(dbrPct, 100)}%` }} />
            </div>
          </div>
        )}

        {cash && (
          <div className="breakdown-section">
            <div className="breakdown-body">
              <div className="cost-row cost-heading"><span className="cost-label">{tr('cash_upfront')}</span></div>
              {cash.items.map((item) => (
                <div className="cost-row" key={item.item}>
                  <span className="cost-label">{tr('cash_' + item.item)}</span>
                  {item.amount_aed !== undefined
                    ? <span className="cost-value">AED {aed(item.amount_aed)}</span>
                    : <span className="cost-value">AED {aed(item.min_aed)}–{aed(item.max_aed)}</span>}
                </div>
              ))}
              <div className="cost-divider" />
              <div className="cost-row total-row">
                <span className="cost-label font-bold">{tr('total')}</span>
                <span className="cost-value font-bold">AED {aed(cash.total_min_aed)}–{aed(cash.total_max_aed)}</span>
              </div>
            </div>
          </div>
        )}

        {costs && (
          <div className="breakdown-section">
            <div className="breakdown-body">
              <div className="cost-row cost-heading"><span className="cost-label font-bold">{tr('purchase_costs')} ({costs.emirate})</span></div>
              {costs.items.map((item) => (
                <div className="cost-row" key={item.item}>
                  <span className="cost-label">{item.item}</span>
                  <span className="cost-value">AED {aed(item.amount_aed)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {data.amortization_schedule?.length > 0 && (
          <div className="amortization-section">
            <table className="amort-table">
              <thead>
                <tr><th>#</th><th>Principal</th><th>Interest</th><th>Balance</th></tr>
              </thead>
              <tbody>
                {data.amortization_schedule.map((row) => (
                  <tr key={row.year}>
                    <td className="font-bold">{row.year}</td>
                    <td className="text-emerald">{aed(row.principal_paid_aed)}</td>
                    <td className="text-ruby">{aed(row.interest_paid_aed)}</td>
                    <td className="text-cyan">{aed(row.remaining_balance_aed)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {data.principal_share_pct ? (
          <div className="distribution-section">
            <div className="distribution-bar-track">
              <div className="dist-bar principal-bar" style={{ width: `${data.principal_share_pct}%` }} />
              <div className="dist-bar interest-bar" style={{ width: `${data.interest_share_pct}%` }} />
            </div>
          </div>
        ) : null}

        {data.assumptions?.length > 0 && <p className="assumptions-line">{tr('assumptions')}: {data.assumptions.join(' · ')}</p>}
      </div>

      <div className="mandatory-disclaimer-box" role="note">
        <XoIcon name="info" size={15} className="disclaimer-icon" />
        <p className="disclaimer-text">{tr('estimate_only')}</p>
      </div>

      {data.verdict === 'can_borrow' && data.max_property_price_aed > 0 && (
        <div className="card-actions">
          <button type="button" className="btn-jump-properties"
                  onClick={() => onAsk?.(tr('show_matching_prompt', { budget: aed(data.max_property_price_aed) }))}>
            <span>{tr('show_matching')}</span>
            <XoIcon name="arrowDown" size={15} className="action-arrow" />
          </button>
        </div>
      )}
    </div>
  )
}
