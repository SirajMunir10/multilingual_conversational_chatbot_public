'use client'
// XO chat widget: text chat (streamed), rich result cards, language switching, advisor review card and voice mode.
// Port of ChatWidget.vue. Behaviour is unchanged; Vue's in-place reactivity is replaced by React state plus
// synchronous mirrors (refs) that the streaming and voice flows read between renders.
import { useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from 'react'
import MessageItem from './MessageItem'
import OnboardingTooltips from './OnboardingTooltips'
import VoiceOrb from './VoiceOrb'
import UaeSkyline from './UaeSkyline'
import XoIcon from './XoIcon'
import LanguageMenu from './LanguageMenu'
import { SubmitHandoffContext } from './HandoffCard'
import { Transition, SwitchTransition } from './Transition'
import { languages, languageInfo, t as translate } from '../i18n'
import { apiUrl, fetchClientConfig, warmBackend } from '../lib/api'
import { useVoice } from '../hooks/useVoice'
import { createSpeech } from '../lib/speech'
import { createWordHighlight } from '../lib/wordHighlight'

const STORE_SESSION = 'xo_session_id'
const STORE_MESSAGES = 'xo_chat_messages'
const VOICE_TURNS_KEY = 'xo_voice_turns' // voice turns completed on this device; the mic hint shows for the first two
const STATUS_BY_TOOL = {
  search_properties: 'status_search', find_similar: 'status_search', compare_listings: 'status_search', get_listing_details: 'status_search',
  calc_affordability: 'status_calc', calc_emi: 'status_calc', check_eligibility: 'status_calc', calc_purchase_costs: 'status_calc',
  estimate_offers: 'status_calc', get_mortgage_products: 'status_calc', get_lending_rules: 'status_calc',
  retrieve_kb: 'status_kb', request_human_handoff: 'status_handoff'
}

const VOICE_FILLER = { status_search: 'voice_filler_search', status_calc: 'voice_filler_calc', status_kb: 'voice_filler_check' }

const cx = (...names) => names.filter(Boolean).join(' ')

function safeStorage(op, key, value) {
  try {
    if (op === 'get') return window.sessionStorage.getItem(key)
    if (op === 'set') return window.sessionStorage.setItem(key, value)
    if (op === 'remove') return window.sessionStorage.removeItem(key)
  } catch (e) {
    return null
  }
  return null
}

const newId = (prefix) => `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`

export default function ChatWidget({
  currentLanguage = 'en', currentTheme = 'light', isExpanded = false, visible = true,
  onClose, onLanguageChanged, onThemeChange
}) {
  const props = useRef({})
  props.current = { currentLanguage, currentTheme, onLanguageChanged, onThemeChange }
  const t = (key, vars) => translate(currentLanguage, key, vars)
  const tNow = (key, vars) => translate(props.current.currentLanguage, key, vars)
  const activeLanguage = languageInfo(currentLanguage)

  const welcomeMessage = () => ({ id: 'welcome', role: 'assistant', content: tNow('welcome'), timestamp: new Date().toISOString(), metadata: {} })

  // ---- Messages: React state + a synchronous mirror for the async flows ----
  const [messages, setMessagesState] = useState(() => {
    const saved = safeStorage('get', STORE_MESSAGES)
    if (saved) {
      try {
        const parsed = JSON.parse(saved)
        if (Array.isArray(parsed) && parsed.length) return parsed.map(m => ({ ...m, isStreaming: false, hidden: false }))
      } catch (e) {}
    }
    return [{ id: 'welcome', role: 'assistant', content: translate(currentLanguage, 'welcome'), timestamp: new Date().toISOString(), metadata: {} }]
  })
  const messagesRef = useRef(messages)
  const commitMessages = useCallback((next) => {
    messagesRef.current = typeof next === 'function' ? next(messagesRef.current) : next
    setMessagesState(messagesRef.current)
  }, [])
  const addMessage = (msg) => commitMessages((list) => [...list, msg])
  const updateMessage = useCallback((id, patch) => commitMessages((list) => list.map((m) => (m.id === id ? { ...m, ...(typeof patch === 'function' ? patch(m) : patch) } : m))), [commitMessages])
  const getMessage = (id) => messagesRef.current.find((m) => m.id === id)

  const [inputQuery, setInputQuery] = useState('')
  const [isTyping, setIsTypingState] = useState(false)
  const isTypingRef = useRef(false)
  const setIsTyping = (v) => { isTypingRef.current = v; setIsTypingState(v) }
  const [statusKey, setStatusKey] = useState('thinking')
  const [showTips, setShowTips] = useState(false)
  const [showLangMenu, setShowLangMenu] = useState(false)
  const feedRef = useRef(null)
  const audioPlayerRef = useRef(null)
  const [isUserScrolledUp, setIsUserScrolledUpState] = useState(false)
  const scrolledUpRef = useRef(false)
  const setIsUserScrolledUp = (v) => { scrolledUpRef.current = v; setIsUserScrolledUpState(v) }
  const sessionId = useRef(safeStorage('get', STORE_SESSION) || null)
  const clientConfig = useRef({ voice: { sample_rate: 24000, silence_submit_ms: 1000, max_session_sec: 120 } })

  // Language bookkeeping: a manual choice is sent once as `selected_language`;
  // a switch made by the assistant is only reflected in the UI.
  const pendingSelectedLanguage = useRef(null)
  const serverLanguage = useRef(currentLanguage)

  const statusText = t(statusKey)

  // ---- Vue nextTick equivalent: resolves after the next render has been committed to the page ----
  const [, forceRender] = useReducer((n) => n + 1, 0)
  const tickWaiters = useRef([])
  const scrollPending = useRef(null)
  const nextTick = () => new Promise((resolve) => { tickWaiters.current.push(resolve); forceRender() })
  useLayoutEffect(() => {
    if (scrollPending.current) {
      const { force, anchor } = scrollPending.current
      scrollPending.current = null
      const el = feedRef.current
      if (el && (force || !scrolledUpRef.current)) {
        let target = el.scrollHeight
        // A reply is shown from its first line: the view follows it only until that line reaches the top.
        const msg = anchor && el.querySelector(`[data-msg-id="${anchor}"]`)
        if (msg) target = Math.min(target, msg.getBoundingClientRect().top - el.getBoundingClientRect().top + el.scrollTop - 12)
        el.scrollTop = target
      }
    }
    if (tickWaiters.current.length) {
      const waiters = tickWaiters.current.splice(0)
      waiters.forEach((resolve) => resolve())
    }
  })

  // Persist the conversation (sessionStorage), without messages still streaming.
  useEffect(() => {
    safeStorage('set', STORE_MESSAGES, JSON.stringify(messages.filter(m => !m.isStreaming)))
  }, [messages])

  // ---- Language switching (history is always preserved) ----
  const lastLanguage = useRef(currentLanguage)
  useEffect(() => {
    const old = lastLanguage.current
    lastLanguage.current = currentLanguage
    if (currentLanguage === old) return
    if (currentLanguage !== serverLanguage.current) pendingSelectedLanguage.current = currentLanguage
    serverLanguage.current = currentLanguage
    const list = messagesRef.current
    if (list.length <= 1 && list[0]?.id === 'welcome') {
      commitMessages([welcomeMessage()])
      return
    }
    addMessage({ id: newId('div'), kind: 'divider', content: translate(currentLanguage, 'language_changed', { lang: languageInfo(currentLanguage).native }) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentLanguage])

  function chooseLanguage(code) {
    setShowLangMenu(false)
    if (code !== props.current.currentLanguage) props.current.onLanguageChanged?.(code)
  }

  // ---- Scrolling ----
  function handleFeedScroll() {
    const el = feedRef.current
    if (el) setIsUserScrolledUp(el.scrollHeight - el.scrollTop - el.clientHeight > 60)
  }
  function scrollToBottom(force = false, anchor = null) {
    const prev = scrollPending.current
    // An explicit "go to the bottom" replaces an earlier reply anchor in the same frame; a gentle request keeps it.
    scrollPending.current = { force: force || !!prev?.force, anchor: anchor || (force ? null : prev?.anchor || null) }
    forceRender()
  }
  // Brings the start of a reply into view (forced when it first appears, gentle while it streams).
  function scrollToReply(id, force = false) {
    scrollToBottom(force, id)
  }
  function scrollToLatest() {
    setIsUserScrolledUp(false)
    scrollToBottom(true)
  }

  // ---- Conversation ----
  const abortController = useRef(null)

  // hooks: onToken(text), onLanguage(code), onMessage(replyId), hold (voice: keep the reply hidden until reveal()).
  async function streamTurn(text, channel = 'text', hooks = {}) {
    if (abortController.current) abortController.current.abort()
    const controller = new AbortController()
    abortController.current = controller
    setIsTyping(true)
    setStatusKey('thinking')
    const reply = { id: newId('ast'), role: 'assistant', content: '', isStreaming: true, hidden: !!hooks.hold, timestamp: new Date().toISOString(), metadata: {} }
    let added = false
    const ensureAdded = () => {
      if (!added) {
        addMessage(reply)
        added = true
        if (!reply.hidden) {
          setIsTyping(false)
          scrollToReply(reply.id, true) // the visitor is taken to the first words of the answer
        }
        hooks.onMessage && hooks.onMessage(reply.id)
      }
      return reply.id
    }

    const body = {
      message: text,
      session_id: sessionId.current,
      ui_language: props.current.currentLanguage,
      channel
    }
    if (pendingSelectedLanguage.current) {
      body.selected_language = pendingSelectedLanguage.current
      pendingSelectedLanguage.current = null
    }

    let finalEvent = null
    try {
      const res = await fetch(apiUrl('/api/chat/stream'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal
      })
      if (!res.ok || !res.body) throw new Error(String(res.status))
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const events = buffer.split('\n\n')
        buffer = events.pop() || ''
        for (const raw of events) {
          if (!raw.startsWith('data: ')) continue
          const ev = JSON.parse(raw.slice(6))
          if (ev.type === 'session') {
            sessionId.current = ev.session_id
            safeStorage('set', STORE_SESSION, ev.session_id)
            hooks.onLanguage && hooks.onLanguage(ev.language)
          } else if (ev.type === 'language') {
            hooks.onLanguage && hooks.onLanguage(ev.language)
          } else if (ev.type === 'status') {
            setStatusKey(STATUS_BY_TOOL[ev.tool] || 'thinking')
            hooks.onStatus && hooks.onStatus(ev.tool)
          } else if (ev.type === 'token') {
            const id = ensureAdded()
            updateMessage(id, (m) => ({ content: m.content + ev.text }))
            hooks.onToken && hooks.onToken(ev.text)
            scrollToReply(id)
          } else if (ev.type === 'final') {
            finalEvent = ev
          } else if (ev.type === 'error') {
            const id = ensureAdded()
            updateMessage(id, { content: ev.message, isError: true })
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        if (added) updateMessage(reply.id, { isStreaming: false, hidden: false })
        return null
      }
      const id = ensureAdded()
      updateMessage(id, { content: tNow('error_generic'), isError: true })
    } finally {
      if (!added || !getMessage(reply.id)?.hidden) setIsTyping(false)
      if (abortController.current === controller) abortController.current = null
    }

    const id = ensureAdded()
    updateMessage(id, (m) => ({ isStreaming: false, hidden: m.isError ? false : m.hidden }))
    if (finalEvent) {
      updateMessage(id, (m) => ({
        content: finalEvent.text || m.content,
        metadata: {
          property_results: finalEvent.property_results || [],
          results_are_alternatives: finalEvent.results_are_alternatives || null,
          mortgage_result: finalEvent.mortgage_result || null,
          handoff_data: finalEvent.handoff_data || null,
          handoff_draft: finalEvent.handoff_draft || null,
          turn_id: finalEvent.turn_id || null
        }
      }))
      if (finalEvent.handoff_draft) {
        // A newer callback card replaces any earlier card that was never confirmed.
        commitMessages((list) => list.map((m) => {
          const d = m.id !== id && m.metadata?.handoff_draft
          return d && d.status === 'review' ? { ...m, metadata: { ...m.metadata, handoff_draft: { ...d, status: 'expired' } } } : m
        }))
      }
      if (finalEvent.language && finalEvent.language !== props.current.currentLanguage) {
        serverLanguage.current = finalEvent.language
        props.current.onLanguageChanged?.(finalEvent.language)
      }
    }
    if (!getMessage(id)?.hidden) scrollToReply(id)
    return finalEvent
  }

  async function sendMessage(textOverride) {
    const text = (textOverride ?? inputQuery).trim()
    if (!text || isTypingRef.current) return
    stopAudio()
    addMessage({ id: newId('usr'), role: 'user', content: text, timestamp: new Date().toISOString() })
    setInputQuery('')
    setIsUserScrolledUp(false)
    scrollToBottom(true)
    await streamTurn(text, 'text')
  }

  // Advisor callback review card → saves the confirmed (or edited) details to the lead store.
  const submitHandoff = useCallback(async (details) => {
    try {
      const res = await fetch(apiUrl('/api/handoff/confirm'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId.current, ...details })
      })
      if (res.status === 404) return { lead_saved: false, error: 'draft_expired' }
      if (!res.ok) return { lead_saved: false, error: 'save_failed' }
      return await res.json()
    } catch (e) {
      return { lead_saved: false, error: 'save_failed' }
    }
  }, [])

  const handoffUpdate = useCallback((messageId, patch) => {
    updateMessage(messageId, (m) => ({ metadata: { ...m.metadata, handoff_draft: { ...m.metadata.handoff_draft, ...patch } } }))
  }, [updateMessage])

  // Thumbs up/down on an XO reply (PRD FR-26). Shown at once; put back if the server could not save it.
  const rateReply = useCallback(async (messageId, rating) => {
    const message = messagesRef.current.find((m) => m.id === messageId)
    const turnId = message?.metadata?.turn_id
    if (!turnId) return
    const previous = message.metadata.rating || null
    const next = previous === rating ? null : rating
    updateMessage(messageId, (m) => ({ metadata: { ...m.metadata, rating: next } }))
    try {
      const res = await fetch(apiUrl('/api/chat/feedback'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId.current, turn_id: turnId, rating: next })
      })
      if (!res.ok) throw new Error(String(res.status))
    } catch (e) {
      updateMessage(messageId, (m) => ({ metadata: { ...m.metadata, rating: previous } }))
    }
  }, [updateMessage])

  const sendRef = useRef(sendMessage)
  sendRef.current = sendMessage
  const sendQuickPrompt = useCallback((text) => { sendRef.current(text) }, [])

  function requestHandoff() {
    sendMessage(t('advisor_request'))
  }

  function clearChat() {
    if (abortController.current) abortController.current.abort()
    exitVoiceMode()
    safeStorage('remove', STORE_MESSAGES)
    safeStorage('remove', STORE_SESSION)
    sessionId.current = null
    pendingSelectedLanguage.current = props.current.currentLanguage !== 'en' ? props.current.currentLanguage : null
    commitMessages([welcomeMessage()])
    setIsTyping(false)
  }

  function toggleTheme() {
    props.current.onThemeChange?.(props.current.currentTheme === 'light' ? 'dark' : 'light')
  }

  // ---- Voice (gpt-live-transcribe in, eleven_v4_turbo out) ----
  // Phases: listening → thinking → speaking → hold. In hold the mic waits for a tap (no auto-listen);
  // tapping while XO thinks or speaks interrupts it and starts listening straight away.
  const { liveText, silenceCountdown, voice } = useVoice()
  const speechRef = useRef(null)
  if (!speechRef.current) speechRef.current = createSpeech(() => audioPlayerRef.current)
  const speech = speechRef.current
  const highlighterRef = useRef(null)
  if (!highlighterRef.current) highlighterRef.current = createWordHighlight()
  const highlighter = highlighterRef.current

  const [voiceMode, setVoiceModeState] = useState(false)
  const voiceModeRef = useRef(false)
  const setVoiceMode = (v) => { voiceModeRef.current = v; setVoiceModeState(v) }
  const [voicePhase, setVoicePhaseState] = useState('idle') // listening | thinking | speaking | hold | idle
  const voicePhaseRef = useRef('idle')
  const setVoicePhase = (v) => { voicePhaseRef.current = v; setVoicePhaseState(v) }
  const [voiceError, setVoiceError] = useState('')
  const [voiceEntering, setVoiceEntering] = useState(0) // a short (<1 s) entry ripple each time voice mode opens
  const [orbBeat, setOrbBeat] = useState(0)
  const [listenBeat, setListenBeat] = useState(0)
  const [voiceTurnsDone, setVoiceTurnsDone] = useState(2) // read from storage after mount; 2+ hides the mic hint
  const voiceTurn = useRef(0)
  const pendingReveal = useRef(null)
  const captionRef = useRef(null)

  // Mic hint for people new to voice: a hand pointing at the mic, until they have completed two voice turns.
  function readVoiceTurns() {
    try { return Number(window.localStorage.getItem(VOICE_TURNS_KEY)) || 0 } catch (e) { return 2 }
  }
  function countVoiceTurn() {
    const next = readVoiceTurns() + 1
    try { window.localStorage.setItem(VOICE_TURNS_KEY, String(next)) } catch (e) {}
    setVoiceTurnsDone(next)
  }

  const voiceStatusText = useMemo(() => {
    if (voicePhase === 'thinking') return statusText
    if (voicePhase === 'speaking') return t('voice_speaking')
    if (voicePhase === 'hold') return t('voice_hold')
    if (voicePhase === 'listening') {
      if (silenceCountdown && liveText.trim()) return t('voice_sending')
      return liveText.trim() ? t('voice_listening') : t('voice_say_something')
    }
    return t('tap_to_talk')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voicePhase, statusText, silenceCountdown, liveText, currentLanguage])

  const micLabel = voicePhase === 'listening' ? t('send') : t('tap_to_talk')

  function stopAudio() {
    speech.stop()
  }

  function primeAudio() {
    // Unlocks playback on mobile browsers while we are inside the user's tap.
    const el = audioPlayerRef.current
    if (!el) return
    el.muted = true
    el.play().catch(() => {}).finally(() => { el.pause(); el.muted = false })
  }

  function revealReply(replyId) {
    if (replyId && getMessage(replyId)?.hidden) updateMessage(replyId, { hidden: false })
    setIsTyping(false)
    scrollToReply(replyId, true)
  }

  async function listenTurn() {
    const turn = ++voiceTurn.current
    speech.stop()
    highlighter.detach()
    if (pendingReveal.current) pendingReveal.current()
    setVoiceError('')
    setVoicePhase('listening')
    setListenBeat((n) => n + 1)
    let transcript = ''
    try {
      transcript = await voice.listen({
        language: props.current.currentLanguage,
        sessionId: sessionId.current,
        sampleRate: clientConfig.current.voice.sample_rate,
        silenceMs: clientConfig.current.voice.silence_submit_ms,
        maxSec: clientConfig.current.voice.max_session_sec
      })
    } catch (err) {
      if (turn !== voiceTurn.current || !voiceModeRef.current) return
      setVoiceError(tNow('voice_unavailable'))
      setVoicePhase('hold')
      return
    }
    if (turn !== voiceTurn.current || !voiceModeRef.current) return
    if (!transcript) {
      setVoicePhase('hold')
      return
    }

    addMessage({ id: newId('usr'), role: 'user', content: transcript, viaVoice: true, timestamp: new Date().toISOString() })
    setIsUserScrolledUp(false)
    scrollToBottom(true)
    setVoicePhase('thinking')

    // The reply text is shown when XO starts speaking, or at most 0.9 s after its first words arrive, so the answer
    // is never kept waiting on the voice. The spoken word is marked once the full text is on screen.
    let replyId = null
    let audioStarted = false
    let textDone = false
    let revealTimer = null
    let earlyTimer = null
    let marking = false
    const show = () => {
      clearTimeout(earlyTimer)
      if (replyId && getMessage(replyId)?.hidden) revealReply(replyId)
    }
    const reveal = async () => {
      clearTimeout(revealTimer)
      show()
      if (!replyId || marking || !textDone) return
      marking = true
      await nextTick()
      if (turn === voiceTurn.current) highlighter.attach(document.querySelector(`[data-msg-id="${replyId}"] .md`))
    }
    const maybeReveal = () => { if (audioStarted) (textDone ? reveal() : show()) }
    pendingReveal.current = () => { pendingReveal.current = null; reveal() }

    // While a search, calculation or knowledge check runs, XO says a short "let me check" so the visitor hears him at once.
    let turnLanguage = props.current.currentLanguage
    let heardWords = false
    let saidFiller = false
    const spoken = speech.start({
      language: props.current.currentLanguage,
      sessionId: () => sessionId.current,
      onStart: () => {
        if (turn !== voiceTurn.current || !voiceModeRef.current) return
        audioStarted = true
        setVoicePhase('speaking')
        maybeReveal()
      },
      onWord: (word) => {
        if (turn !== voiceTurn.current) return
        highlighter.mark(word)
        if (word) setOrbBeat((n) => n + 1)
      },
      onError: () => { if (turn === voiceTurn.current) setVoiceError(tNow('voice_unavailable')) }
    })
    const final = await streamTurn(transcript, 'voice', {
      hold: true,
      onMessage: (id) => { replyId = id },
      onToken: (text) => {
        if (turn !== voiceTurn.current) return
        heardWords = true
        if (!earlyTimer && !audioStarted) earlyTimer = setTimeout(show, 900)
        speech.push(text)
      },
      onStatus: (tool) => {
        const key = VOICE_FILLER[STATUS_BY_TOOL[tool]]
        if (turn !== voiceTurn.current || saidFiller || heardWords || !key) return
        saidFiller = true
        speech.push(translate(turnLanguage, key) + ' ')
      },
      onLanguage: (lang) => {
        if (turn !== voiceTurn.current) return
        turnLanguage = lang || turnLanguage
        speech.setLanguage(lang)
      }
    })
    textDone = true
    if (final && transcript) countVoiceTurn()
    if (turn !== voiceTurn.current || !voiceModeRef.current) return reveal()
    speech.end(final && final.text)
    maybeReveal()
    // Never keep the answer hidden for long if the voice is slow or unavailable.
    revealTimer = setTimeout(reveal, 2500)
    await spoken
    clearTimeout(earlyTimer)
    reveal()
    highlighter.detach()
    pendingReveal.current = null
    if (turn === voiceTurn.current && voiceModeRef.current) setVoicePhase('hold')
  }

  function micAction() {
    if (voicePhaseRef.current === 'listening') {
      voice.commit()
      return
    }
    // Interrupt XO (or resume from hold) and listen. Runs inside the tap, so audio stays unlocked.
    voice.prepare()
    listenTurn()
  }

  async function enterVoiceMode() {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      addMessage({ id: newId('ast'), role: 'assistant', content: t('voice_unavailable'), isError: true, timestamp: new Date().toISOString() })
      return
    }
    // Must run synchronously inside the tap: unlocks audio input and playback on Android and iOS.
    voice.prepare()
    primeAudio()
    if (abortController.current) abortController.current.abort()
    setVoiceError('')
    setVoiceMode(true)
    setVoicePhase('thinking')
    setVoiceEntering((n) => n + 1)
    setVoiceTurnsDone(readVoiceTurns())
    warmBackend()
    const turn = ++voiceTurn.current
    try {
      await voice.open()
    } catch (err) {
      setVoiceError(err.message === 'mic_denied' ? tNow('voice_mic_denied') : tNow('voice_unavailable'))
      setVoicePhase('hold')
      return
    }
    if (turn === voiceTurn.current && voiceModeRef.current) listenTurn()
  }

  function exitVoiceMode() {
    voiceTurn.current += 1
    if (pendingReveal.current) pendingReveal.current()
    highlighter.detach()
    setVoiceMode(false)
    setVoicePhase('idle')
    speech.stop()
    voice.close()
    scrollToBottom(true)
  }

  const exitRef = useRef(exitVoiceMode)
  exitRef.current = exitVoiceMode
  useEffect(() => {
    let active = true
    scrollToBottom(true)
    warmBackend() // the first answer does not wait for new provider connections (or a sleeping server)
    fetchClientConfig().then((cfg) => { if (active && cfg?.voice) clientConfig.current = cfg })
    return () => {
      active = false
      if (abortController.current) abortController.current.abort()
      exitRef.current()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // The live caption always shows the latest words of a long question.
  useLayoutEffect(() => {
    const el = captionRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [liveText])

  // ---- View ----
  const showHero = messages.length <= 1
  const coach = voiceMode && voiceTurnsDone < 2 && !voiceError &&
    (voicePhase === 'hold' || (voicePhase === 'listening' && !liveText.trim()))

  const voiceDock = (
    <div className={cx('voice-dock', 'phase-' + voicePhase)} role="region" aria-label={t('voice_listening')}>
      {/* Mic hint for first-time voice users: a hand points at the mic with one short line */}
      <Transition name="coach" show={coach}>
        <div className={cx('voice-coach', voicePhase === 'hold' && 'is-tap')} aria-hidden="true">
          <span className="voice-coach-bubble" dir="auto">{voicePhase === 'hold' ? t('voice_coach_tap') : t('voice_coach_listening')}</span>
          <span className="voice-coach-hand">
            {/* Pointing hand (Lucide "pointer", ISC licence), turned to point down at the mic */}
            <svg viewBox="0 0 24 24" width="30" height="30" aria-hidden="true">
              <g transform="rotate(180 12 12)" fill="none" strokeLinecap="round" strokeLinejoin="round">
                {['halo', 'line'].map((layer) => (
                  <g key={layer} stroke={layer === 'halo' ? 'var(--w-bg)' : 'currentColor'} strokeWidth={layer === 'halo' ? 4.5 : 1.9}>
                    <path d="M22 14a8 8 0 0 1-8 8" />
                    <path d="M18 11v-1a2 2 0 0 0-2-2a2 2 0 0 0-2 2" />
                    <path d="M14 10V9a2 2 0 0 0-2-2a2 2 0 0 0-2 2v1" />
                    <path d="M10 9.5V4a2 2 0 0 0-2-2a2 2 0 0 0-2 2v10" />
                    <path d="M18 11a2 2 0 1 1 4 0v3a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15" />
                  </g>
                ))}
              </g>
            </svg>
          </span>
        </div>
      </Transition>
      <button type="button" className={cx('voice-orb-btn', 'phase-' + voicePhase, coach && voicePhase === 'hold' && 'is-coached')} onClick={micAction} aria-label={micLabel} data-tip={micLabel} data-tip-pos="top-start">
        <VoiceOrb size={68} phase={voicePhase} levelSource={voice.state} beat={orbBeat} dark={currentTheme === 'dark'} />
        {/* "Your turn": a short double heartbeat each time the mic goes live */}
        {voicePhase === 'listening' && <span key={listenBeat} className="orb-heartbeat" aria-hidden="true" />}
        {(voicePhase === 'hold' || voicePhase === 'idle') && (
          <span className="orb-glyph" aria-hidden="true">
            <XoIcon name="mic" size={20} />
          </span>
        )}
        {(voicePhase === 'speaking' || voicePhase === 'thinking') && (
          <span className="orb-badge" aria-hidden="true">
            <XoIcon name="pause" size={10} stroke={3} />
          </span>
        )}
      </button>
      <div className="voice-dock-text" aria-live="polite">
        <span className="voice-dock-status">{voiceStatusText}</span>
        {voicePhase === 'listening' && liveText.trim() && <p ref={captionRef} className="voice-dock-caption" dir="auto">{liveText}</p>}
        {voiceError && <p className="voice-error-text" role="alert">{voiceError}</p>}
      </div>
      <div className="voice-dock-actions">
        <Transition name="pop" show={voicePhase === 'listening' && !!liveText.trim()}>
          <button type="button" className="xo-round-btn confirm" onClick={() => voice.commit()} aria-label={t('send')} data-tip={t('send')} data-tip-pos="top">
            <XoIcon name="check" size={20} />
          </button>
        </Transition>
        <button type="button" className="xo-round-btn cancel" onClick={exitVoiceMode} aria-label={t('tip_end_voice')} data-tip={t('tip_end_voice')} data-tip-pos="top-end">
          <XoIcon name="close" size={20} />
        </button>
      </div>
    </div>
  )

  const footer = (
    <div className="chat-footer">
      <form onSubmit={(e) => { e.preventDefault(); sendMessage() }} className="input-form">
        <label htmlFor="chat-text-input" className="visually-hidden">{t('placeholder')}</label>
        <input id="chat-text-input" value={inputQuery} onChange={(e) => setInputQuery(e.target.value)} type="text" dir="auto" enterKeyHint="send"
               placeholder={t('placeholder')} className="chat-input-field" disabled={isTyping} autoComplete="off" maxLength={2000} />
        <button type="button" className="mic-btn" onClick={enterVoiceMode} aria-label={t('tip_voice')} data-tip={t('tip_voice')} data-tip-pos="top">
          <XoIcon name="mic" size={20} />
        </button>
        <button type="submit" className="send-btn" disabled={!inputQuery.trim() || isTyping} aria-label={t('send')} data-tip={t('send')} data-tip-pos="top-end">
          <XoIcon name="send" size={18} stroke={2.4} />
        </button>
      </form>
    </div>
  )

  return (
    <SubmitHandoffContext.Provider value={submitHandoff}>
      <div className={cx('xo-widget', isExpanded && 'is-expanded', voiceMode && 'in-voice')} role="region" aria-label="XO"
           lang={currentLanguage} dir={activeLanguage.dir} style={visible ? undefined : { display: 'none' }}>
        {/* Header */}
        <header className="xo-header">
          <div className="xo-brand">
            <span className="xo-avatar">
              <img src="/xo-mascot.png" alt="" />
              <span className="xo-online" aria-hidden="true" />
            </span>
            <span className="xo-brand-text">
              <strong>XO</strong>
              <small>{t('header_tagline')}</small>
            </span>
          </div>

          <div className="xo-header-actions">
            {/* In-widget language switch (FR-1: visible manual toggle) */}
            <div className="lang-switch" onKeyDown={(e) => { if (e.key === 'Escape') setShowLangMenu(false) }}>
              <button type="button" className="xo-chip lang-switch-btn" onClick={() => setShowLangMenu(!showLangMenu)} aria-haspopup="listbox"
                      aria-expanded={showLangMenu} aria-label={`${t('change_language')}: ${activeLanguage.native}`}
                      data-tip={showLangMenu ? undefined : t('change_language')}>
                <XoIcon name="globe" size={16} />
                <span className="chip-label">{activeLanguage.native}</span>
                <span className="chip-code">{currentLanguage.toUpperCase()}</span>
                <XoIcon name="chevronDown" size={14} stroke={2.4} className={cx('chip-caret', showLangMenu && 'open')} />
              </button>
              <Transition name="pop" show={showLangMenu}>
                <LanguageMenu current={currentLanguage} onChoose={chooseLanguage} t={t} />
              </Transition>
            </div>

            {/* Persistent human handoff (FR-5) */}
            <button type="button" className="xo-chip advisor-btn" onClick={requestHandoff} aria-label={t('tip_advisor')} data-tip={t('tip_advisor')}>
              <XoIcon name="headset" size={16} />
              <span className="chip-label">{t('advisor')}</span>
            </button>

            <span className="xo-divider" aria-hidden="true" />

            <button type="button" className="xo-icon-btn theme-toggle-btn" onClick={toggleTheme}
                    aria-label={currentTheme === 'light' ? t('tip_dark') : t('tip_light')} data-tip={currentTheme === 'light' ? t('tip_dark') : t('tip_light')}>
              <XoIcon name={currentTheme === 'light' ? 'moon' : 'sun'} />
            </button>
            <button type="button" className="xo-icon-btn tips-toggle-btn" onClick={() => setShowTips(!showTips)} aria-label={t('tip_tips')} data-tip={t('tip_tips')}>
              <XoIcon name="bulb" />
            </button>
            <button type="button" className="xo-icon-btn clear-chat-btn" onClick={clearChat} aria-label={t('clear_chat')} data-tip={t('clear_chat')} data-tip-pos="end">
              <XoIcon name="trash" />
            </button>
            <button type="button" className="xo-icon-btn close-widget-btn" onClick={() => onClose?.()} aria-label={t('tip_close')} data-tip={t('tip_close')} data-tip-pos="end">
              <XoIcon name="close" />
            </button>
          </div>
        </header>

        <OnboardingTooltips isOpen={showTips} onClose={() => setShowTips(false)} />

        <div className="feed-wrap">
          <div className="feed-backdrop" aria-hidden="true"><UaeSkyline /></div>
          <div className="chat-feed" ref={feedRef} role="log" aria-live="polite" onScroll={handleFeedScroll}>
            {showHero && (
              <div className="xo-hero">
                <div className="xo-hero-mascot">
                  <img src="/xo-mascot.png" alt="XO" />
                </div>
                <h3 dir="auto">{t('hero_title')}</h3>
                <p dir="auto">{t('hero_sub')}</p>
              </div>
            )}

            {messages.map((msg) => (msg.kind === 'divider'
              ? <div key={msg.id} className="lang-divider" role="separator"><span dir="auto">{msg.content}</span></div>
              : !msg.hidden && <MessageItem key={msg.id} message={msg} language={currentLanguage} onAsk={sendQuickPrompt} onHandoffUpdate={handoffUpdate} onRate={rateReply} />
            ))}

            {isTyping && (
              <div className="typing-indicator">
                <img src="/xo-mascot.png" alt="" className="typing-avatar" />
                <div className="typing-pill">
                  <span className="typing-dots" aria-hidden="true"><i /><i /><i /></span>
                  <span className="typing-text">{statusText}</span>
                </div>
              </div>
            )}
          </div>
        </div>

        <Transition name="pop" show={isUserScrolledUp}>
          <button type="button" className="jump-to-latest-btn" onClick={scrollToLatest}>
            <XoIcon name="arrowDown" size={14} />
            <span>{t('latest')}</span>
          </button>
        </Transition>

        {/* Entering voice mode: one quick ripple in the widget's own colours (under 1 s) */}
        {voiceMode && voiceEntering > 0 && <span key={voiceEntering} className="voice-enter-ripple" aria-hidden="true" />}

        {/* Voice dock: the conversation stays visible while XO listens, thinks and speaks */}
        <SwitchTransition name="dock" activeKey={voiceMode ? 'voice' : 'text'} render={(key) => (key === 'voice' ? voiceDock : footer)} />

        <div className="input-disclaimer">
          <span dir="auto">{t('footer_disclaimer')}</span>
        </div>

        <audio ref={audioPlayerRef} className="visually-hidden" playsInline />
      </div>
    </SubmitHandoffContext.Provider>
  )
}
