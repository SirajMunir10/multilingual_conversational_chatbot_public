'use client'
import { useEffect, useRef, useState } from 'react'
import Icon from './Icon'

// Single-measure charts for the admin. One series each, so one hue, no legend (the title names the measure), values in
// text ink, hover and keyboard tooltips, and a table view for screen readers and exact values.

/** A stat tile: identity chip, value, change against the previous period, and a small trend line. */
export function StatCard({ label, value, icon, tone = 'c1', delta, deltaGood = 'up', hint, series }) {
  return (
    <div className={`xa-stat ${tone}`}>
      <div className="xa-stat-top">
        <span className="xa-stat-chip"><Icon name={icon} size={19} /></span>
        <div>
          <div className="xa-stat-value">{value}{delta && <Delta {...delta} good={deltaGood} />}</div>
          <div className="xa-stat-label">{label}</div>
        </div>
      </div>
      {hint && <div className="xa-stat-hint">{hint}</div>}
      {series && series.length > 1 && <Sparkline values={series} label={`${label} trend`} />}
    </div>
  )
}

function Delta({ value, unit = '%', good }) {
  if (value === null || value === undefined || !Number.isFinite(value)) return null
  const dir = Math.abs(value) < 0.05 ? 'flat' : value > 0 ? 'up' : 'down'
  const better = dir === 'flat' ? 'flat' : (dir === good ? 'up' : 'down')
  const text = `${value > 0 ? '+' : ''}${Math.abs(value) >= 10 ? Math.round(value) : value.toFixed(1)}${unit}`
  return (
    <span className={`xa-delta is-${better}`} title="Change against the previous period of the same length">
      {dir !== 'flat' && <Icon name={dir === 'up' ? 'trendUp' : 'trendDown'} size={11} strokeWidth={2.4} />}{text}
    </span>
  )
}

export function Sparkline({ values, label }) {
  const w = 240
  const h = 44
  const max = Math.max(...values, 1)
  const min = Math.min(...values, 0)
  const span = max - min || 1
  const pts = values.map((v, i) => [(i / (values.length - 1)) * w, h - 4 - ((v - min) / span) * (h - 10)])
  const line = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  return (
    <span className="xa-stat-spark">
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label={label}>
        <path className="xa-spark-area" d={`${line} L${w},${h} L0,${h} Z`} />
        <path className="xa-spark-line" d={line} vectorEffect="non-scaling-stroke" />
      </svg>
    </span>
  )
}

/** Vertical bars over time (e.g. conversations per day). `data`: [{ label, value, title }]. */
export function ColumnChart({ data, valueLabel, height = 220 }) {
  const [active, setActive] = useState(null)
  // Drawn at the container's real width so axis text keeps its size (no scaling of the whole picture).
  const box = useRef(null)
  const [width, setWidth] = useState(640)
  useEffect(() => {
    const el = box.current
    if (!el || typeof ResizeObserver === 'undefined') return undefined
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.round(entry.contentRect.width))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const max = Math.max(1, ...data.map((d) => d.value))
  const n = data.length || 1
  const pad = { top: 12, bottom: 24, left: 32, right: 4 }
  const plotW = width - pad.left - pad.right
  const plotH = height - pad.top - pad.bottom
  const slot = plotW / n
  const barW = Math.max(2, Math.min(26, slot - 2)) // 2px gap between adjacent bars
  const ticks = [0, Math.ceil(max / 2), max].filter((v, i, a) => a.indexOf(v) === i)
  const labelEvery = Math.ceil(n / Math.max(2, Math.floor(plotW / 70)))

  return (
    <figure className="xa-chart">
      <div className="xa-chart-plot" ref={box}>
        <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label={`${valueLabel} by day`}>
          {ticks.map((t) => {
            const y = pad.top + plotH - (t / max) * plotH
            return (
              <g key={t}>
                <line x1={pad.left} x2={width - pad.right} y1={y} y2={y} className="xa-chart-grid" />
                <text x={pad.left - 8} y={y + 4} textAnchor="end" className="xa-chart-axis">{t}</text>
              </g>
            )
          })}
          {data.map((d, i) => {
            const h = d.value ? Math.max(2, (d.value / max) * plotH) : 0
            const x = pad.left + i * slot + (slot - barW) / 2
            const y = pad.top + plotH - h
            return (
              <g key={d.label + i}>
                <rect x={pad.left + i * slot} y={pad.top} width={slot} height={plotH} fill="transparent" tabIndex={0}
                  aria-label={d.title} onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)}
                  onFocus={() => setActive(i)} onBlur={() => setActive(null)} />
                {h > 0 && <path d={roundedTop(x, y, barW, h, Math.min(4, barW / 2))} className={`xa-chart-bar${active === i ? ' is-active' : ''}`} />}
                {i % labelEvery === 0 && <text x={x + barW / 2} y={height - 6} textAnchor="middle" className="xa-chart-axis">{d.label}</text>}
              </g>
            )
          })}
        </svg>
        {active !== null && (
          <div className="xa-chart-tip" style={{ left: `${((pad.left + (active + 0.5) * slot) / width) * 100}%` }}>{data[active].title}</div>
        )}
      </div>
      <TableView rows={data.map((d) => [d.label, d.value])} headers={['Day', valueLabel]} />
    </figure>
  )
}

/** Horizontal bars with the label and value as text (topics, endings, languages). `data`: [{ label, value }]. */
export function BarList({ data, valueLabel, total, empty = 'No data yet' }) {
  if (!data.length) return <p className="xa-muted xa-small">{empty}</p>
  const max = Math.max(1, ...data.map((d) => d.value))
  return (
    <ul className="xa-barlist">
      {data.map((d) => {
        const share = total ? Math.round((100 * d.value) / total) : null
        return (
          <li key={d.label} title={`${d.label}: ${d.value} ${valueLabel}${share !== null ? ` (${share}%)` : ''}`}>
            <div className="xa-barlist-text">
              <span>{d.label}</span>
              <span className="xa-barlist-value">{d.value}{share !== null && <small> · {share}%</small>}</span>
            </div>
            <div className="xa-barlist-track" aria-hidden="true">
              <span className="xa-barlist-fill" style={{ width: `${Math.max(2, (100 * d.value) / max)}%` }} />
            </div>
          </li>
        )
      })}
    </ul>
  )
}

function TableView({ headers, rows }) {
  return (
    <details className="xa-chart-table">
      <summary>Show as table</summary>
      <table className="xa-table">
        <thead><tr>{headers.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
      </table>
    </details>
  )
}

function roundedTop(x, y, w, h, r) {
  const rr = Math.min(r, h)
  return `M${x},${y + h} V${y + rr} Q${x},${y} ${x + rr},${y} H${x + w - rr} Q${x + w},${y} ${x + w},${y + rr} V${y + h} Z`
}
