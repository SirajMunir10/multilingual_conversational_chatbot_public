'use client'
import { useState } from 'react'
import { adminApi, errorMessage } from '../lib/api'
import { HistoryDrawer, PublishBar, PublishDialog, VersionLine, useConfigItem } from '../components/config'
import Icon from '../components/Icon'
import { Badge, Button, Card, EmptyState, Field, Notice, PageHeader, Tabs, UnitInput } from '../components/ui'

const get = (obj, path) => path.split('.').reduce((o, k) => (o == null ? o : o[k]), obj)
const set = (obj, path, value) => {
  const keys = path.split('.')
  const last = keys.pop()
  keys.reduce((o, k) => o[k], obj)[last] = value
}

// Lending rules (approved build logic). `scale` shows stored fractions as percentages.
const RULE_GROUPS = [
  { title: 'Interest and term', sub: 'The benchmark rate is used when a visitor has no rate from a bank.', fields: [
    ['interest.benchmark_rate_pct', 'Benchmark rate', '%'], ['interest.min_rate_pct', 'Lowest accepted rate', '%'],
    ['interest.max_rate_pct', 'Highest accepted rate', '%'], ['tenure.default_years', 'Default term', 'years'],
    ['tenure.min_years', 'Shortest term', 'years'], ['tenure.max_years', 'Longest term', 'years']] },
  { title: 'Who can apply', sub: 'The applicant and term checks of the approved build logic.', fields: [
    ['bank_settings.min_age', 'Minimum age', 'years'], ['bank_settings.min_monthly_income_aed', 'Minimum monthly income', 'AED', 1, true],
    ['bank_settings.max_age_at_last_repayment.salaried', 'Age at last payment, salaried', 'years'],
    ['bank_settings.max_age_at_last_repayment.self_employed', 'Age at last payment, self-employed', 'years']] },
  { title: 'Affordability limits', sub: 'Central Bank limits and the stress test used for the debt-burden ceiling.', fields: [
    ['central_bank.debt_burden_max_ratio', 'Maximum debt burden', '%', 100], ['bank_settings.stress_test_addon_pct', 'Stress-test add-on', 'pts'],
    ['bank_settings.credit_card_debt_pct_of_limit', 'Card limit counted as debt', '%', 100],
    ['central_bank.income_multiple.uae_national', 'Income multiple, UAE national', '×'], ['central_bank.income_multiple.expat', 'Income multiple, expat', '×'],
    ['central_bank.max_term_years', 'Central Bank maximum term', 'years'], ['central_bank.rent_vacancy_months', 'Rent vacancy allowance', 'months']] },
  { title: 'Property and costs', sub: 'The value threshold splits the loan-to-value rows below.', fields: [
    ['property_value_threshold_aed', 'Property value threshold', 'AED', 1, true], ['bank_settings.non_resident_ltv', 'Non-resident loan-to-value', '%', 100],
    ['upfront_costs.arrangement_fee_max_pct_of_loan', 'Bank arrangement fee, at most', '%', 100]] },
  { title: 'Sense checks on what visitors type', sub: 'Incomes outside this range are treated as missing, so XO asks again.', fields: [
    ['input_limits.min_monthly_income_aed', 'Lowest income accepted', 'AED', 1, true], ['input_limits.max_monthly_income_aed', 'Highest income accepted', 'AED', 1, true]] },
]

const FEE_GENERAL = [
  ['vat_rate', 'VAT', '%', 100], ['agent_commission_pct', 'Agent commission', '%', 100],
  ['mortgage.registration_fee_pct_of_loan', 'Mortgage registration, share of loan', '%', 100],
  ['mortgage.valuation_fee_aed.min', 'Valuation fee, from', 'AED', 1, true], ['mortgage.valuation_fee_aed.max', 'Valuation fee, up to', 'AED', 1, true],
  ['resale_only.developer_noc_aed.min', 'Developer NOC, from', 'AED', 1, true], ['resale_only.developer_noc_aed.max', 'Developer NOC, up to', 'AED', 1, true],
  ['early_settlement_fee_pct.min', 'Early settlement fee, from', '%', 100], ['early_settlement_fee_pct.max', 'Early settlement fee, up to', '%', 100],
]

const PRODUCT_COLUMNS = [
  ['bank_name', 'Bank', 'text'], ['rate_type', 'Product', 'text'], ['interest_rate', 'Rate', '%'], ['max_ltv_national', 'LTV national', '%'],
  ['max_ltv_expat', 'LTV expat', '%'], ['min_salary_aed', 'Min salary', 'AED'], ['max_tenure_years', 'Max term', 'yrs'],
  ['processing_fee_pct', 'Processing', '%'], ['valuation_fee_aed', 'Valuation', 'AED'], ['early_settlement_fee_pct', 'Early settle', '%'],
]

const CONDITION_LABELS = {
  off_plan: 'Off-plan', uae_national: 'UAE national', uae_resident: 'Expat', non_resident: 'Non-resident', first: 'First home', second: 'Second home',
  at_or_below: 'Up to threshold', above: 'Above threshold', below: 'Below threshold', at_or_above: 'Threshold or more'
}

function NumberField({ item, path, label, unit, scale = 1, prefix }) {
  const value = get(item.working, path)
  const live = get(item.published.data, path)
  return (
    <Field label={label} changed={value !== live} hint={value !== live ? `Live: ${prefix ? `AED ${Number(live).toLocaleString()}` : `${+(live * scale).toFixed(4)} ${unit}`}` : undefined}>
      {(a) => <UnitInput {...a} value={value} scale={scale} unit={prefix ? undefined : unit} prefix={prefix ? 'AED' : undefined}
        onChange={(v) => item.update((d) => set(d, path, v))} />}
    </Field>
  )
}

function changedFields(item, groups) {
  return groups.flatMap(([path, label, unit, scale = 1]) => {
    const before = get(item.published.data, path)
    const after = get(item.working, path)
    return before !== after ? [{ label, before: `${+(before * scale).toFixed(4)} ${unit}`, after: after == null ? '—' : `${+(after * scale).toFixed(4)} ${unit}` }] : []
  })
}

export default function Rules() {
  const rules = useConfigItem('mortgage_rules')
  const fees = useConfigItem('fees')
  const products = useConfigItem('bank_products')
  const [tab, setTab] = useState('rules')
  const [history, setHistory] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [impact, setImpact] = useState(null)
  const [checking, setChecking] = useState(false)

  const item = { rules, fees, products }[tab]
  const ready = rules.working && fees.working && products.working
  const loadError = rules.error || fees.error || products.error

  const checkImpact = async () => {
    setChecking(true)
    try {
      setImpact(await adminApi('/config/rules/impact', { method: 'POST', body: {
        mortgage_rules: rules.working, fees: fees.working, bank_products: products.working } }))
    } catch (e) {
      setImpact({ error: e.status === 422 ? 'Fix the problems listed in the publish check first.' : errorMessage(e) })
    } finally {
      setChecking(false)
    }
  }

  const review = async () => {
    setReviewing(true)
    await checkImpact()
  }

  return (
    <div className="xa-stack-sm">
      <PageHeader title="Calculator rules" subtitle="The rates, limits and fees behind every figure XO gives. Changes are checked against the 15 approved cases before they go live."
        actions={item?.published && <VersionLine item={item} onHistory={() => setHistory(true)} />} />
      {loadError && <Notice tone="error">{loadError}</Notice>}
      <Tabs label="Rule tables" value={tab} onChange={(t) => { setTab(t); setImpact(null) }} tabs={[
        { id: 'rules', label: 'Lending rules', changed: rules.changed }, { id: 'fees', label: 'Fees', changed: fees.changed },
        { id: 'products', label: 'Bank products', changed: products.changed }]} />

      {ready && (
        <div className="xa-editor">
          <div className="xa-stack">
            {tab === 'rules' && <LendingRules item={rules} />}
            {tab === 'fees' && <Fees item={fees} />}
            {tab === 'products' && <Products item={products} />}
          </div>
          <aside className="xa-editor-side">
            <Card title="Impact check" subtitle="The 15 approved cases and two examples, with the live rules and with your changes.">
              {!impact && <Button variant="ghost" icon="target" busy={checking} onClick={checkImpact} className="xa-btn-block">Check impact</Button>}
              {impact?.error && <Notice tone="error">{impact.error}</Notice>}
              {impact?.scenarios && <ImpactSummary impact={impact} onRecheck={checkImpact} busy={checking} />}
            </Card>
            <Card>
              <p className="xa-small xa-muted"><Icon name="info" size={14} /> Edits are saved as a draft as you type. Visitors keep getting the live
                version until you publish. The loan-to-value conditions and the engine come from the approved build logic and are not editable here.</p>
            </Card>
          </aside>
        </div>
      )}

      {item?.working && <PublishBar item={item} onReview={review} />}
      {reviewing && (
        <PublishDialog item={item} title={`Publish ${{ rules: 'lending rules', fees: 'fees', products: 'bank products' }[tab]}`} onClose={() => setReviewing(false)}>
          {tab === 'rules' && <ChangeList changes={changedFields(rules, RULE_GROUPS.flatMap((g) => g.fields))} />}
          {tab === 'fees' && <ChangeList changes={changedFields(fees, FEE_GENERAL)} extra="Emirate fees are compared in the impact table." />}
          {impact?.scenarios ? <ImpactTable impact={impact} /> : <p className="xa-muted">{checking ? 'Checking the approved cases…' : impact?.error}</p>}
        </PublishDialog>
      )}
      {history && item && <HistoryDrawer item={item} onClose={() => setHistory(false)} />}
    </div>
  )
}

function LendingRules({ item }) {
  const rows = item.working.ltv_table
  return (
    <>
      {RULE_GROUPS.map((g) => (
        <Card key={g.title} title={g.title} subtitle={g.sub}>
          <div className="xa-fields">
            {g.fields.map(([path, label, unit, scale, aed]) => <NumberField key={path} item={item} path={path} label={label} unit={unit} scale={scale} prefix={aed} />)}
          </div>
        </Card>
      ))}
      <Card title="Loan-to-value table" subtitle="The first matching row applies. Conditions come from the approved build logic; the percentage and description can change." flush>
        <div className="xa-table-wrap">
          <table className="xa-table">
            <thead><tr><th scope="col">#</th><th scope="col">Applies to</th><th scope="col">Description</th><th scope="col" className="xa-num">Loan-to-value</th></tr></thead>
            <tbody>
              {rows.map((row, i) => {
                const live = item.published.data.ltv_table[i]
                const conditions = ['property_status', 'residency', 'home', 'value'].filter((k) => row[k]).map((k) => CONDITION_LABELS[row[k]] || row[k])
                return (
                  <tr key={row.order}>
                    <td className="xa-muted">{row.order}</td>
                    <td>{conditions.length ? conditions.map((c) => <span key={c} className="xa-tag" style={{ marginInlineEnd: 4 }}>{c}</span>) : <span className="xa-muted">Anyone</span>}</td>
                    <td><label className="xa-sr" htmlFor={`ltv-case-${i}`}>Description of row {row.order}</label>
                      <input id={`ltv-case-${i}`} value={row.case} onChange={(e) => item.update((d) => { d.ltv_table[i].case = e.target.value })} /></td>
                    <td className="xa-num" style={{ width: 150 }}>
                      {'ltv' in row
                        ? <div className={row.ltv !== live.ltv ? 'xa-field is-changed' : 'xa-field'}>
                            <label className="xa-sr" htmlFor={`ltv-${i}`}>Loan-to-value for row {row.order}</label>
                            <UnitInput id={`ltv-${i}`} value={row.ltv} scale={100} unit="%" onChange={(v) => item.update((d) => { d.ltv_table[i].ltv = v })} />
                          </div>
                        : <span className="xa-small xa-muted">Non-resident setting</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  )
}

function Fees({ item }) {
  const emirates = item.working.emirates
  const live = item.published.data.emirates
  const cell = (code, path, scale = 1, unit = 'AED') => {
    const value = get(emirates[code], path)
    return (
      <div className={value !== get(live[code], path) ? 'xa-field is-changed' : 'xa-field'}>
        <label className="xa-sr" htmlFor={`fee-${code}-${path}`}>{`${emirates[code].label} ${path.replace(/_/g, ' ')}`}</label>
        <UnitInput id={`fee-${code}-${path}`} value={value} scale={scale} unit={unit} onChange={(v) => item.update((d) => set(d.emirates[code], path, v))} />
      </div>
    )
  }
  return (
    <>
      <Card title="General fees" subtitle="Applied on top of each emirate's registration fees.">
        <div className="xa-fields">
          {FEE_GENERAL.map(([path, label, unit, scale, aed]) => <NumberField key={path} item={item} path={path} label={label} unit={unit} scale={scale} prefix={aed} />)}
        </div>
      </Card>
      <Card title="Fees by emirate" subtitle="Used for buying-cost estimates." flush
        actions={(
          <div className="xa-row xa-small">
            <label htmlFor="default-emirate">Default emirate</label>
            <select id="default-emirate" value={item.working.default_emirate} onChange={(e) => item.update((d) => { d.default_emirate = e.target.value })}>
              {Object.entries(emirates).map(([code, e]) => <option key={code} value={code}>{e.label}</option>)}
            </select>
          </div>
        )}>
        <div className="xa-table-wrap">
          <table className="xa-table">
            <thead><tr><th scope="col">Emirate</th><th scope="col">Registration</th><th scope="col">Admin fee</th><th scope="col">Title deed</th><th scope="col">Trustee fee</th></tr></thead>
            <tbody>
              {Object.entries(emirates).map(([code, e]) => (
                <tr key={code}>
                  <td><strong>{e.label}</strong><div className="xa-small xa-muted">{e.registration_label}</div></td>
                  <td style={{ minWidth: 120 }}>{cell(code, 'registration_fee_pct', 100, '%')}</td>
                  <td style={{ minWidth: 130 }}>{cell(code, 'admin_fee_aed')}</td>
                  <td style={{ minWidth: 130 }}>{cell(code, 'title_deed_fee_aed')}</td>
                  <td style={{ minWidth: 300 }}>
                    {e.trustee_fee
                      ? <div className="xa-row" style={{ flexWrap: 'nowrap' }}>{cell(code, 'trustee_fee.at_or_below_aed')}{cell(code, 'trustee_fee.above_aed')}</div>
                      : <span className="xa-small xa-muted">None</span>}
                    {e.trustee_fee && <div className="xa-small xa-muted">Up to / above AED {Number(e.trustee_fee.threshold_aed).toLocaleString()}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  )
}

function Products({ item }) {
  const list = item.working.products
  const add = () => item.update((d) => {
    d.products.push({ product_id: `prod_${Date.now().toString(36)}`, bank_name: '', rate_type: '', interest_rate: 4, max_ltv_national: 80,
      max_ltv_expat: 75, min_salary_aed: 15000, max_tenure_years: 25, processing_fee_pct: 1, valuation_fee_aed: 2500, early_settlement_fee_pct: 1,
      finance_type: 'conventional' })
  })
  return (
    <Card title="Bank products" subtitle="Indicative rates XO quotes when a visitor asks about specific banks." flush
      actions={<Button variant="ghost" size="sm" icon="plus" onClick={add}>Add product</Button>}>
      {item.working.note && <div style={{ padding: '0 20px 14px' }}><Notice tone="warning">{item.working.note}</Notice></div>}
      {list.length === 0 ? <EmptyState icon="calculator" title="No products">Add the products XO may quote.</EmptyState> : (
        <div className="xa-table-wrap">
          <table className="xa-table">
            <thead><tr>{PRODUCT_COLUMNS.map(([, label]) => <th key={label} scope="col">{label}</th>)}<th scope="col">Type</th><th scope="col"><span className="xa-sr">Remove</span></th></tr></thead>
            <tbody>
              {list.map((p, i) => (
                <tr key={p.product_id}>
                  {PRODUCT_COLUMNS.map(([key, label, unit]) => (
                    <td key={key} style={{ minWidth: unit === 'text' ? 150 : 104 }}>
                      <label className="xa-sr" htmlFor={`p-${i}-${key}`}>{`${label} for ${p.bank_name || 'new product'}`}</label>
                      {unit === 'text'
                        ? <input id={`p-${i}-${key}`} value={p[key]} onChange={(e) => item.update((d) => { d.products[i][key] = e.target.value })} />
                        : <UnitInput id={`p-${i}-${key}`} value={p[key]} unit={unit} onChange={(v) => item.update((d) => { d.products[i][key] = v })} />}
                    </td>
                  ))}
                  <td>
                    <label className="xa-sr" htmlFor={`p-${i}-type`}>Finance type</label>
                    <select id={`p-${i}-type`} value={p.finance_type} onChange={(e) => item.update((d) => { d.products[i].finance_type = e.target.value })}>
                      <option value="conventional">Conventional</option><option value="islamic">Islamic</option>
                    </select>
                  </td>
                  <td><button type="button" className="xa-icon-btn" aria-label={`Remove ${p.bank_name || 'product'}`}
                    onClick={() => item.update((d) => { d.products.splice(i, 1) })}><Icon name="trash" size={16} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

function ChangeList({ changes, extra }) {
  if (!changes.length && !extra) return null
  return (
    <div>
      <p className="xa-field-label">Changed values</p>
      {changes.length === 0 ? <p className="xa-muted xa-small">{extra}</p> : (
        <ul className="xa-check-list" style={{ marginBlockStart: 8 }}>
          {changes.map((c) => <li key={c.label}><Icon name="arrowRight" size={14} /><span><strong>{c.label}</strong>: {c.before} → {c.after}</span></li>)}
        </ul>
      )}
    </div>
  )
}

function ImpactSummary({ impact, onRecheck, busy }) {
  const changed = impact.scenarios.filter((s) => s.changed.length)
  return (
    <div className="xa-stack-sm">
      {changed.length === 0
        ? <Badge tone="ok" icon="check">No figure changes</Badge>
        : <Badge tone="warning" icon="alert">{changed.length} of {impact.scenarios.length} cases change</Badge>}
      {changed.slice(0, 6).map((s) => (
        <div key={s.id} className="xa-small">
          <strong>{s.label}</strong>
          {s.changed.slice(0, 2).map((k) => <div key={k} className="xa-muted">{k}: {fmt(s.before[k])} → <b>{fmt(s.after[k])}</b></div>)}
        </div>
      ))}
      {changed.length > 6 && <span className="xa-small xa-muted">and {changed.length - 6} more; all are listed when you publish.</span>}
      <Button variant="quiet" size="sm" icon="refresh" busy={busy} onClick={onRecheck}>Check again</Button>
    </div>
  )
}

const fmt = (v) => (typeof v === 'number' ? v.toLocaleString() : v ?? '—')

function ImpactTable({ impact }) {
  const changed = impact.scenarios.filter((s) => s.changed.length)
  return (
    <div>
      <p className="xa-field-label">Effect on the approved cases</p>
      {changed.length === 0 ? <p className="xa-muted xa-small" style={{ marginBlockStart: 6 }}>None of the 15 approved cases or the two examples change.</p> : (
        <div className="xa-table-wrap" style={{ marginBlockStart: 8, border: '1px solid var(--xa-line)', borderRadius: 10 }}>
          <table className="xa-table">
            <thead><tr><th scope="col">Case</th><th scope="col">What changes</th></tr></thead>
            <tbody>
              {changed.map((s) => (
                <tr key={s.id} className="xa-impact-row">
                  <td style={{ width: '40%' }}>{s.label}</td>
                  <td><div className="xa-impact-figs">{s.changed.map((k) => (
                    <div key={k} className="is-changed"><span>{k}</span><span>{fmt(s.before[k])} → <b>{fmt(s.after[k])}</b></span></div>
                  ))}</div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
