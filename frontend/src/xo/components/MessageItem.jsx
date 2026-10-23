'use client'
import { memo, useMemo, useState } from 'react'
import MortgageCard from './MortgageCard'
import HandoffCard from './HandoffCard'
import XoIcon from './XoIcon'
import { renderMarkdown } from '../lib/markdown'
import { t, formatAed } from '../i18n'

const cx = (...names) => names.filter(Boolean).join(' ')

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch (e) {
    return ''
  }
}

/**
 * One chat message with its rich results (property cards, mortgage card, advisor review card).
 * Memoised: during streaming only the message being written re-renders. The markdown HTML is set only
 * when its text changes, so the spoken-word marks added by the voice mode stay in place.
 */
function MessageItem({ message, language = 'en', onAsk, onHandoffUpdate, onRate }) {
  const [expanded, setExpanded] = useState({})
  const toggle = (id) => setExpanded((e) => ({ ...e, [id]: !e[id] }))
  const tr = (key, vars) => t(language, key, vars)
  const aed = (v) => formatAed(v, language)
  const meta = message.metadata || {}

  const rendered = useMemo(() => renderMarkdown(message.content), [message.content])
  // Review card for a callback request; older saved chats only carry handoff_data.
  const handoff = meta.handoff_draft || (meta.handoff_data?.lead_saved ? { ...meta.handoff_data, status: 'saved' } : null)

  const bedsText = (n) => (Number(n) === 0 ? tr('studio') : tr('beds', { n: Number(n) }))
  const bedsLabel = (p) => {
    if (p.beds_min === null || p.beds_min === undefined) return ''
    if (p.beds_max === null || p.beds_max === undefined || p.beds_max === p.beds_min) return bedsText(p.beds_min)
    return `${bedsText(p.beds_min)} – ${bedsText(p.beds_max)}`
  }
  const priceLabel = (p) => {
    if (!p.price_from) return tr('price_on_request')
    const ranged = p.price_to && p.price_to !== p.price_from
    return `${ranged ? tr('from') + ' ' : ''}AED ${aed(p.price_from)}`
  }

  const rateable = message.role === 'assistant' && meta.turn_id && !message.isStreaming && !message.isError
  const rating = meta.rating || null
  const timestamp = (
    <span className="message-timestamp">
      {message.viaVoice && <XoIcon name="mic" size={11} />}
      {message.timestamp ? formatTime(message.timestamp) : ''}
    </span>
  )

  const properties = meta.property_results || []
  const hasRich = properties.length || meta.mortgage_result || handoff

  return (
    <div className={cx('message-wrapper', message.role, message.isError && 'is-error')} data-msg-id={message.id}>
      {message.role === 'assistant' && <img src="/xo-mascot.png" alt="XO" className="message-avatar" />}

      <div className={cx('message-bubble-container', hasRich && 'has-rich')}>
        {(message.content || message.isStreaming) && (
          <div className="message-bubble">
            <div className="message-content" dir="auto">
              {message.role === 'assistant'
                ? <div className="md" dangerouslySetInnerHTML={{ __html: rendered }} />
                : <span className="plain-text">{message.content}</span>}
              {message.isStreaming && <span className="streaming-cursor" aria-hidden="true" />}
            </div>
          </div>
        )}

        {/* Property recommendations (FR-8) */}
        {properties.length > 0 && (
          <div className="property-results-container">
            {meta.results_are_alternatives && (
              <div className="property-results-header">
                <span className="results-badge">{tr('alternatives')}</span>
              </div>
            )}
            <div className="property-card-list">
              {properties.map((prop) => (
                <article key={prop.id} className={cx('prop-card', expanded[prop.id] && 'is-expanded')}>
                  <div className="prop-compact-bar" onClick={() => toggle(prop.id)}>
                    <div className="prop-thumb-wrap">
                      {prop.image_url && <img src={prop.image_url} alt={prop.title} className="prop-thumb-img" loading="lazy" />}
                      <span className="prop-ref-badge">#{prop.ref}</span>
                    </div>
                    <div className="prop-compact-info">
                      <h5 className="prop-compact-title" title={prop.title}>{prop.title}</h5>
                      <div className="prop-compact-sub">
                        <span className="prop-compact-loc"><XoIcon name="pin" size={13} />{prop.community}</span>
                        {bedsLabel(prop) && <span className="prop-compact-beds">{bedsLabel(prop)}</span>}
                      </div>
                      <div className="prop-compact-price">{priceLabel(prop)}</div>
                      <div className="prop-source-row">
                        <span className={cx('source-badge', prop.source)}>{prop.source === 'live_offplan' ? tr('live_offplan') : tr('sample_listing')}</span>
                        <span className="status-chip">{prop.status === 'off-plan' ? tr('off_plan') : tr('ready')}</span>
                      </div>
                    </div>
                    <div className="prop-compact-controls" onClick={(e) => e.stopPropagation()}>
                      <button type="button" className="prop-icon-btn" onClick={() => onAsk?.(tr('save_prompt', { ref: prop.ref }))}
                              aria-label={tr('save_prompt', { ref: prop.ref })} title={tr('save_prompt', { ref: prop.ref })}>
                        <XoIcon name="heart" size={16} />
                      </button>
                      <button type="button" className="prop-icon-btn" onClick={() => toggle(prop.id)} aria-expanded={!!expanded[prop.id]}
                              aria-label={expanded[prop.id] ? tr('hide') : tr('details')}>
                        <XoIcon name="chevronDown" size={16} className={cx('expand-arrow', expanded[prop.id] && 'rotated')} />
                      </button>
                    </div>
                  </div>

                  <div className="prop-expanded-drawer" style={expanded[prop.id] ? undefined : { display: 'none' }}>
                    {prop.image_url && (
                      <div className="prop-image-wrap">
                        <img src={prop.image_url} alt={prop.title} className="prop-image" loading="lazy" />
                        {prop.developer && <span className="badge-dev">{prop.developer}</span>}
                      </div>
                    )}
                    <div className="prop-info">
                      <p className="prop-location"><XoIcon name="pin" size={14} />{prop.community}{prop.city && <span>, {prop.city}</span>}</p>
                      <div className="prop-specs">
                        {bedsLabel(prop) && <span><XoIcon name="bed" size={14} />{bedsLabel(prop)}</span>}
                        {prop.baths ? <span><XoIcon name="bath" size={14} />{prop.baths}</span> : null}
                        {prop.size_sqft ? <span><XoIcon name="area" size={14} />{prop.size_sqft.toLocaleString()} sq ft</span> : null}
                        {prop.completion && <span>{tr('completion')}: {prop.completion}</span>}
                      </div>
                      {prop.amenities?.length > 0 && (
                        <div className="prop-amenities-row">
                          {prop.amenities.slice(0, 4).map((a, i) => <span key={i} className="amenity-chip">{a}</span>)}
                        </div>
                      )}
                      {prop.mortgage_estimate && (
                        <div className="prop-mortgage-banner">
                          <strong>{tr('est_monthly')}: AED {aed(prop.mortgage_estimate.monthly_payment_aed)}</strong>
                          <span>{tr('down_payment')} AED {aed(prop.mortgage_estimate.down_payment_aed)} · {prop.mortgage_estimate.interest_rate_pct}% · {prop.mortgage_estimate.tenure_years} {tr('years')}</span>
                          <span className="muted">{tr('estimate_only')}</span>
                        </div>
                      )}
                      <div className="prop-actions">
                        <button type="button" className="btn-card-action" onClick={() => onAsk?.(tr('mortgage_this_prompt', { ref: prop.ref }))}>
                          <XoIcon name="calculator" size={15} />{tr('mortgage_this')}
                        </button>
                        {prop.listing_url && (
                          <a href={prop.listing_url} target="_blank" rel="noopener noreferrer" className="prop-link">
                            {tr('view_details')}<XoIcon name="external" size={14} />
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </div>
        )}

        {/* Calculator result (FR-14, FR-15) */}
        {meta.mortgage_result && <MortgageCard data={meta.mortgage_result} language={language} onAsk={onAsk} />}

        {/* Advisor callback review card (FR-5): confirm or edit, then saved */}
        {handoff && (
          <HandoffCard draft={handoff} language={language}
                       onUpdate={meta.handoff_draft ? (patch) => onHandoffUpdate?.(message.id, patch) : undefined} />
        )}

        {rateable ? (
          <div className="message-footer">
            {timestamp}
            {/* Thumbs up/down on a finished XO reply (FR-26) */}
            <span className="message-rating" role="group" aria-label={`${tr('rate_helpful')} / ${tr('rate_not_helpful')}`}>
              {[['up', 'thumbUp', 'rate_helpful'], ['down', 'thumbDown', 'rate_not_helpful']].map(([value, icon, label]) => (
                <button key={value} type="button" className={cx('rating-btn', rating === value && 'is-active')}
                        aria-pressed={rating === value} aria-label={tr(label)} title={tr(label)}
                        onClick={() => onRate?.(message.id, value)}>
                  <XoIcon name={icon} size={13} />
                </button>
              ))}
              <span className="rating-thanks" role="status">{rating ? tr('rated_thanks') : ''}</span>
            </span>
          </div>
        ) : timestamp}
      </div>
    </div>
  )
}

export default memo(MessageItem)
