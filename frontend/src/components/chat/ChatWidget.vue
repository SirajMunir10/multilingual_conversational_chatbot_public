<template>
  <div class="xo-widget" :class="{ 'is-expanded': isExpanded, 'in-voice': voiceMode }" role="region" aria-label="XO"
       :lang="currentLanguage" :dir="activeLanguage.dir">
    <!-- Header -->
    <header class="xo-header">
      <div class="xo-brand">
        <span class="xo-avatar">
          <img src="/xo-mascot.png" alt="" />
          <span class="xo-online" aria-hidden="true"></span>
        </span>
        <span class="xo-brand-text">
          <strong>XO</strong>
          <small>{{ t('header_tagline') }}</small>
        </span>
      </div>

      <div class="xo-header-actions">
        <!-- In-widget language switch (FR-1: visible manual toggle) -->
        <div class="lang-switch" @keydown.escape="showLangMenu = false">
          <button type="button" class="xo-chip lang-switch-btn" @click="showLangMenu = !showLangMenu" aria-haspopup="listbox"
                  :aria-expanded="showLangMenu" :aria-label="`${t('change_language')}: ${activeLanguage.native}`"
                  :data-tip="showLangMenu ? null : t('change_language')">
            <XoIcon name="globe" :size="16" />
            <span class="chip-label">{{ activeLanguage.native }}</span>
            <span class="chip-code">{{ currentLanguage.toUpperCase() }}</span>
            <XoIcon name="chevronDown" :size="14" :stroke="2.4" class="chip-caret" :class="{ open: showLangMenu }" />
          </button>
          <transition name="pop">
            <ul v-if="showLangMenu" class="lang-menu" role="listbox" :aria-label="t('change_language')">
              <li v-for="lang in languages" :key="lang.code">
                <button type="button" role="option" :aria-selected="lang.code === currentLanguage"
                        :class="{ active: lang.code === currentLanguage }" @click="chooseLanguage(lang.code)">
                  <span class="lang-native" :dir="lang.dir">{{ lang.native }}</span>
                  <span class="lang-name">{{ lang.name }}</span>
                  <XoIcon v-if="lang.code === currentLanguage" name="check" :size="16" class="lang-check" />
                </button>
              </li>
            </ul>
          </transition>
        </div>

        <!-- Persistent human handoff (FR-5) -->
        <button type="button" class="xo-chip advisor-btn" @click="requestHandoff" :aria-label="t('tip_advisor')" :data-tip="t('tip_advisor')">
          <XoIcon name="headset" :size="16" />
          <span class="chip-label">{{ t('advisor') }}</span>
        </button>

        <span class="xo-divider" aria-hidden="true"></span>

        <button type="button" class="xo-icon-btn theme-toggle-btn" @click="toggleTheme"
                :aria-label="currentTheme === 'light' ? t('tip_dark') : t('tip_light')" :data-tip="currentTheme === 'light' ? t('tip_dark') : t('tip_light')">
          <XoIcon :name="currentTheme === 'light' ? 'moon' : 'sun'" />
        </button>
        <button type="button" class="xo-icon-btn tips-toggle-btn" @click="showTips = !showTips" :aria-label="t('tip_tips')" :data-tip="t('tip_tips')">
          <XoIcon name="bulb" />
        </button>
        <button type="button" class="xo-icon-btn clear-chat-btn" @click="clearChat" :aria-label="t('clear_chat')" :data-tip="t('clear_chat')" data-tip-pos="end">
          <XoIcon name="trash" />
        </button>
        <button type="button" class="xo-icon-btn close-widget-btn" @click="$emit('close')" :aria-label="t('tip_close')" :data-tip="t('tip_close')" data-tip-pos="end">
          <XoIcon name="close" />
        </button>
      </div>
    </header>

    <OnboardingTooltips :is-open="showTips" @close="showTips = false" />

    <div class="feed-wrap">
    <div class="feed-backdrop" aria-hidden="true"><UaeSkyline /></div>
    <div class="chat-feed" ref="feedRef" role="log" aria-live="polite" @scroll="handleFeedScroll">
      <div v-if="messages.length <= 1" class="xo-hero">
        <div class="xo-hero-mascot">
          <img src="/xo-mascot.png" alt="XO" />
        </div>
        <h3 dir="auto">{{ t('hero_title') }}</h3>
        <p dir="auto">{{ t('hero_sub') }}</p>
      </div>

      <template v-for="msg in messages" :key="msg.id">
        <div v-if="msg.kind === 'divider'" class="lang-divider" role="separator"><span dir="auto">{{ msg.content }}</span></div>
        <MessageItem v-else-if="!msg.hidden" :message="msg" :language="currentLanguage" @ask="sendQuickPrompt" />
      </template>

      <div class="typing-indicator" v-if="isTyping">
        <img src="/xo-mascot.png" alt="" class="typing-avatar" />
        <div class="typing-pill">
          <span class="typing-dots" aria-hidden="true"><i></i><i></i><i></i></span>
          <span class="typing-text">{{ statusText }}</span>
        </div>
      </div>
    </div>
    </div>

    <transition name="pop">
      <button v-if="isUserScrolledUp" type="button" class="jump-to-latest-btn" @click="scrollToLatest">
        <XoIcon name="arrowDown" :size="14" />
        <span>{{ t('latest') }}</span>
      </button>
    </transition>

    <!-- First-time voice intro -->
    <transition name="voice-intro">
      <div v-if="voiceIntro" class="voice-intro" role="dialog" :aria-label="t('voice_intro')" @click="voiceIntro = false">
        <VoiceOrb :size="introOrbSize" phase="speaking" :beat="introBeat" :dark="true" assemble />
        <p class="voice-intro-text" dir="auto">{{ t('voice_intro') }}</p>
      </div>
    </transition>

    <!-- Voice dock: the conversation stays visible while XO listens, thinks and speaks -->
    <transition name="dock" mode="out-in">
      <div v-if="voiceMode" key="voice" class="voice-dock" :class="'phase-' + voicePhase" role="region" :aria-label="t('voice_listening')">
        <button type="button" class="voice-orb-btn" :class="'phase-' + voicePhase" @click="micAction" :aria-label="micLabel" :data-tip="micLabel" data-tip-pos="top-start">
          <VoiceOrb :size="68" :phase="voicePhase" :level="voice.level.value" :beat="orbBeat" :dark="currentTheme === 'dark'" />
          <!-- "Your turn": a short double heartbeat each time the mic goes live -->
          <span v-if="voicePhase === 'listening'" :key="listenBeat" class="orb-heartbeat" aria-hidden="true"></span>
          <span v-if="voicePhase === 'hold' || voicePhase === 'idle'" class="orb-glyph" aria-hidden="true">
            <XoIcon name="mic" :size="20" />
          </span>
          <span v-if="voicePhase === 'speaking' || voicePhase === 'thinking'" class="orb-badge" aria-hidden="true">
            <XoIcon name="pause" :size="10" :stroke="3" />
          </span>
        </button>
        <div class="voice-dock-text" aria-live="polite">
          <span class="voice-dock-status">{{ voiceStatusText }}</span>
          <p v-if="voicePhase === 'listening' && voice.liveText.value.trim()" class="voice-dock-caption" dir="auto">{{ voice.liveText.value }}</p>
          <p v-if="voiceError" class="voice-error-text" role="alert">{{ voiceError }}</p>
        </div>
        <div class="voice-dock-actions">
          <transition name="pop">
            <button v-if="voicePhase === 'listening' && voice.liveText.value.trim()" type="button" class="xo-round-btn confirm" @click="voice.commit()" :aria-label="t('send')" :data-tip="t('send')" data-tip-pos="top">
              <XoIcon name="check" :size="20" />
            </button>
          </transition>
          <button type="button" class="xo-round-btn cancel" @click="exitVoiceMode" :aria-label="t('tip_end_voice')" :data-tip="t('tip_end_voice')" data-tip-pos="top-end">
            <XoIcon name="close" :size="20" />
          </button>
        </div>
      </div>

      <div v-else key="text" class="chat-footer">
        <form @submit.prevent="sendMessage()" class="input-form">
          <label for="chat-text-input" class="visually-hidden">{{ t('placeholder') }}</label>
          <input id="chat-text-input" ref="inputRef" v-model="inputQuery" type="text" dir="auto" enterkeyhint="send"
                 :placeholder="t('placeholder')" class="chat-input-field" :disabled="isTyping" autocomplete="off" maxlength="2000" />
          <button type="button" class="mic-btn" @click="enterVoiceMode" :aria-label="t('tip_voice')" :data-tip="t('tip_voice')" data-tip-pos="top">
            <XoIcon name="mic" :size="20" />
          </button>
          <button type="submit" class="send-btn" :disabled="!inputQuery.trim() || isTyping" :aria-label="t('send')" :data-tip="t('send')" data-tip-pos="top-end">
            <XoIcon name="send" :size="18" :stroke="2.4" />
          </button>
        </form>
      </div>
    </transition>

    <div class="input-disclaimer">
      <span dir="auto">{{ t('footer_disclaimer') }}</span>
    </div>

    <audio ref="audioPlayerRef" class="visually-hidden" playsinline></audio>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick, toRefs, provide } from 'vue'
import MessageItem from './MessageItem.vue'
import OnboardingTooltips from './OnboardingTooltips.vue'
import VoiceOrb from './VoiceOrb.vue'
import UaeSkyline from './UaeSkyline.vue'
import XoIcon from '../shared/XoIcon.vue'
import { languages, languageInfo, t as translate } from '../../i18n'
import { apiUrl, fetchClientConfig } from '../../services/api'
import { useVoice } from '../../composables/useVoice'
import { useSpeech } from '../../composables/useSpeech'
import { useWordHighlight } from '../../composables/useWordHighlight'

const props = defineProps({
  currentLanguage: { type: String, default: 'en' },
  currentTheme: { type: String, default: 'light' },
  isExpanded: { type: Boolean, default: false }
})
const { isExpanded } = toRefs(props)
const emit = defineEmits(['close', 'language-changed', 'update:currentTheme', 'toggle-expand'])

const STORE_SESSION = 'xo_session_id'
const STORE_MESSAGES = 'xo_chat_messages'

const t = (key, vars) => translate(props.currentLanguage, key, vars)
const activeLanguage = computed(() => languageInfo(props.currentLanguage))

const messages = ref([])
const inputQuery = ref('')
const isTyping = ref(false)
const statusKey = ref('thinking')
const showTips = ref(false)
const showLangMenu = ref(false)
const feedRef = ref(null)
const inputRef = ref(null)
const audioPlayerRef = ref(null)
const isUserScrolledUp = ref(false)
const sessionId = ref(safeStorage('get', STORE_SESSION) || null)
const clientConfig = ref({ voice: { sample_rate: 24000, silence_submit_ms: 2000, max_session_sec: 120 } })

// Language bookkeeping: a manual choice is sent once as `selected_language`;
// a switch made by the assistant is only reflected in the UI.
let pendingSelectedLanguage = null
let serverLanguage = props.currentLanguage

const statusText = computed(() => t(statusKey.value))
const STATUS_BY_TOOL = {
  search_properties: 'status_search', find_similar: 'status_search', compare_listings: 'status_search', get_listing_details: 'status_search',
  calc_affordability: 'status_calc', calc_emi: 'status_calc', check_eligibility: 'status_calc', calc_purchase_costs: 'status_calc',
  estimate_offers: 'status_calc', get_mortgage_products: 'status_calc', get_lending_rules: 'status_calc',
  retrieve_kb: 'status_kb', request_human_handoff: 'status_handoff'
}

function safeStorage(op, key, value) {
  try {
    if (op === 'get') return window.sessionStorage.getItem(key)
    if (op === 'set') return window.sessionStorage.setItem(key, value)
    if (op === 'remove') return window.sessionStorage.removeItem(key)
  } catch (e) {
    return null
  }
}

const newId = (prefix) => `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`

function welcomeMessage() {
  return { id: 'welcome', role: 'assistant', content: t('welcome'), timestamp: new Date().toISOString(), metadata: {} }
}

function restoreMessages() {
  const saved = safeStorage('get', STORE_MESSAGES)
  if (saved) {
    try {
      const parsed = JSON.parse(saved)
      if (Array.isArray(parsed) && parsed.length) {
        messages.value = parsed.map(m => ({ ...m, isStreaming: false, hidden: false }))
        return
      }
    } catch (e) {}
  }
  messages.value = [welcomeMessage()]
}

watch(messages, (val) => {
  safeStorage('set', STORE_MESSAGES, JSON.stringify(val.filter(m => !m.isStreaming)))
}, { deep: true })

// ---- Language switching (history is always preserved) ----
function addLanguageDivider(code) {
  if (messages.value.length <= 1 && messages.value[0]?.id === 'welcome') {
    messages.value = [welcomeMessage()]
    return
  }
  messages.value.push({ id: newId('div'), kind: 'divider', content: translate(code, 'language_changed', { lang: languageInfo(code).native }) })
}

function chooseLanguage(code) {
  showLangMenu.value = false
  if (code !== props.currentLanguage) emit('language-changed', code)
}

watch(() => props.currentLanguage, (code, old) => {
  if (code === old) return
  if (code !== serverLanguage) pendingSelectedLanguage = code
  serverLanguage = code
  addLanguageDivider(code)
})

// ---- Scrolling ----
function handleFeedScroll() {
  const el = feedRef.value
  if (el) isUserScrolledUp.value = el.scrollHeight - el.scrollTop - el.clientHeight > 60
}
async function scrollToBottom(force = false) {
  await nextTick()
  if (feedRef.value && (force || !isUserScrolledUp.value)) feedRef.value.scrollTop = feedRef.value.scrollHeight
}
function scrollToLatest() {
  isUserScrolledUp.value = false
  scrollToBottom(true)
}

// ---- Conversation ----
let abortController = null

// hooks: onToken(text), onLanguage(code), onMessage(reply), hold (voice: keep the reply hidden until reveal()).
async function streamTurn(text, channel = 'text', hooks = {}) {
  if (abortController) abortController.abort()
  abortController = new AbortController()
  isTyping.value = true
  statusKey.value = 'thinking'
  const reply = { id: newId('ast'), role: 'assistant', content: '', isStreaming: true, hidden: !!hooks.hold, timestamp: new Date().toISOString(), metadata: {} }
  let added = false
  let live = null
  const ensureAdded = () => {
    if (!added) {
      messages.value.push(reply)
      added = true
      live = messages.value[messages.value.length - 1]
      if (!reply.hidden) isTyping.value = false
      hooks.onMessage && hooks.onMessage(live)
    }
    return live
  }

  const body = {
    message: text,
    session_id: sessionId.value,
    ui_language: props.currentLanguage,
    channel
  }
  if (pendingSelectedLanguage) {
    body.selected_language = pendingSelectedLanguage
    pendingSelectedLanguage = null
  }

  let finalEvent = null
  try {
    const res = await fetch(apiUrl('/api/chat/stream'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: abortController.signal
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
          sessionId.value = ev.session_id
          safeStorage('set', STORE_SESSION, ev.session_id)
          hooks.onLanguage && hooks.onLanguage(ev.language)
        } else if (ev.type === 'language') {
          hooks.onLanguage && hooks.onLanguage(ev.language)
        } else if (ev.type === 'status') {
          statusKey.value = STATUS_BY_TOOL[ev.tool] || 'thinking'
        } else if (ev.type === 'token') {
          const msg = ensureAdded()
          msg.content += ev.text
          hooks.onToken && hooks.onToken(ev.text)
          scrollToBottom()
        } else if (ev.type === 'final') {
          finalEvent = ev
        } else if (ev.type === 'error') {
          const msg = ensureAdded()
          msg.content = ev.message
          msg.isError = true
        }
      }
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      if (added) { live.isStreaming = false; live.hidden = false }
      return null
    }
    const msg = ensureAdded()
    msg.content = t('error_generic')
    msg.isError = true
  } finally {
    if (!added || !live.hidden) isTyping.value = false
    abortController = null
  }

  const msg = ensureAdded()
  msg.isStreaming = false
  if (msg.isError) msg.hidden = false
  if (finalEvent) {
    msg.content = finalEvent.text || msg.content
    msg.metadata = {
      property_results: finalEvent.property_results || [],
      results_are_alternatives: finalEvent.results_are_alternatives || null,
      mortgage_result: finalEvent.mortgage_result || null,
      handoff_data: finalEvent.handoff_data || null,
      handoff_draft: finalEvent.handoff_draft || null
    }
    if (finalEvent.handoff_draft) {
      // A newer callback card replaces any earlier card that was never confirmed.
      messages.value.forEach(m => {
        const d = m !== msg && m.metadata?.handoff_draft
        if (d && d.status === 'review') d.status = 'expired'
      })
    }
    if (finalEvent.language && finalEvent.language !== props.currentLanguage) {
      serverLanguage = finalEvent.language
      emit('language-changed', finalEvent.language)
    }
  }
  scrollToBottom()
  return finalEvent
}

async function sendMessage(textOverride) {
  const text = (textOverride ?? inputQuery.value).trim()
  if (!text || isTyping.value) return
  stopAudio()
  messages.value.push({ id: newId('usr'), role: 'user', content: text, timestamp: new Date().toISOString() })
  inputQuery.value = ''
  isUserScrolledUp.value = false
  scrollToBottom(true)
  await streamTurn(text, 'text')
}

// Advisor callback review card → saves the confirmed (or edited) details to the lead store.
async function submitHandoff(details) {
  try {
    const res = await fetch(apiUrl('/api/handoff/confirm'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId.value, ...details })
    })
    if (res.status === 404) return { lead_saved: false, error: 'draft_expired' }
    if (!res.ok) return { lead_saved: false, error: 'save_failed' }
    return await res.json()
  } catch (e) {
    return { lead_saved: false, error: 'save_failed' }
  }
}
provide('submitHandoff', submitHandoff)

function sendQuickPrompt(text) {
  sendMessage(text)
}

function requestHandoff() {
  sendMessage(t('advisor_request'))
}

function clearChat() {
  if (abortController) abortController.abort()
  exitVoiceMode()
  safeStorage('remove', STORE_MESSAGES)
  safeStorage('remove', STORE_SESSION)
  sessionId.value = null
  pendingSelectedLanguage = props.currentLanguage !== 'en' ? props.currentLanguage : null
  messages.value = [welcomeMessage()]
  isTyping.value = false
}

function toggleTheme() {
  emit('update:currentTheme', props.currentTheme === 'light' ? 'dark' : 'light')
}

// ---- Voice (gpt-live-transcribe in, eleven_v4_turbo out) ----
// Phases: listening → thinking → speaking → hold. In hold the mic waits for a tap (no auto-listen);
// tapping while XO thinks or speaks interrupts it and starts listening straight away.
const VOICE_INTRO_KEY = 'xo_voice_intro_seen'
const voice = useVoice()
const speech = useSpeech(() => audioPlayerRef.value)
const voiceMode = ref(false)
const voicePhase = ref('idle') // listening | thinking | speaking | hold | idle
const voiceError = ref('')
const voiceIntro = ref(false)
const highlighter = useWordHighlight()
const orbBeat = ref(0)
const introBeat = ref(0)
const listenBeat = ref(0)
const introOrbSize = ref(180)
let voiceTurn = 0
let pendingReveal = null

const voiceStatusText = computed(() => {
  if (voicePhase.value === 'thinking') return statusText.value
  if (voicePhase.value === 'speaking') return t('voice_speaking')
  if (voicePhase.value === 'hold') return t('voice_hold')
  if (voicePhase.value === 'listening') {
    if (voice.silenceCountdown.value && voice.liveText.value.trim()) return t('voice_sending')
    return voice.liveText.value.trim() ? t('voice_listening') : t('voice_say_something')
  }
  return t('tap_to_talk')
})

const micLabel = computed(() => (voicePhase.value === 'listening' ? t('send') : t('tap_to_talk')))

function stopAudio() {
  speech.stop()
}

function primeAudio() {
  // Unlocks playback on mobile browsers while we are inside the user's tap.
  const el = audioPlayerRef.value
  if (!el) return
  el.muted = true
  el.play().catch(() => {}).finally(() => { el.pause(); el.muted = false })
}

function revealReply(reply) {
  if (reply && reply.hidden) reply.hidden = false
  isTyping.value = false
  scrollToBottom(true)
}

async function listenTurn() {
  const turn = ++voiceTurn
  speech.stop()
  highlighter.detach()
  if (pendingReveal) pendingReveal()
  voiceError.value = ''
  voicePhase.value = 'listening'
  listenBeat.value += 1
  let transcript = ''
  try {
    transcript = await voice.listen({
      language: props.currentLanguage,
      sessionId: sessionId.value,
      sampleRate: clientConfig.value.voice.sample_rate,
      silenceMs: clientConfig.value.voice.silence_submit_ms,
      maxSec: clientConfig.value.voice.max_session_sec
    })
  } catch (err) {
    if (turn !== voiceTurn || !voiceMode.value) return
    voiceError.value = t('voice_unavailable')
    voicePhase.value = 'hold'
    return
  }
  if (turn !== voiceTurn || !voiceMode.value) return
  if (!transcript) {
    voicePhase.value = 'hold'
    return
  }

  messages.value.push({ id: newId('usr'), role: 'user', content: transcript, viaVoice: true, timestamp: new Date().toISOString() })
  isUserScrolledUp.value = false
  scrollToBottom(true)
  voicePhase.value = 'thinking'

  // The reply text stays hidden until XO starts speaking, so text and voice arrive together.
  let reply = null
  let audioStarted = false
  let textDone = false
  let revealTimer = null
  const reveal = async () => {
    clearTimeout(revealTimer)
    if (!reply || !reply.hidden) return
    revealReply(reply)
    await nextTick()
    if (turn === voiceTurn) highlighter.attach(document.querySelector(`[data-msg-id="${reply.id}"] .md`))
  }
  const maybeReveal = () => { if (audioStarted && textDone) reveal() }
  pendingReveal = () => { pendingReveal = null; reveal() }

  const spoken = speech.start({
    language: props.currentLanguage,
    sessionId: sessionId.value,
    onStart: () => {
      if (turn !== voiceTurn || !voiceMode.value) return
      audioStarted = true
      voicePhase.value = 'speaking'
      maybeReveal()
    },
    onWord: (word) => {
      if (turn !== voiceTurn) return
      highlighter.mark(word)
      if (word) orbBeat.value += 1
    },
    onError: () => { if (turn === voiceTurn) voiceError.value = t('voice_unavailable') }
  })
  const final = await streamTurn(transcript, 'voice', {
    hold: true,
    onMessage: (msg) => { reply = msg },
    onToken: (text) => { if (turn === voiceTurn) speech.push(text) },
    onLanguage: (lang) => { if (turn === voiceTurn) speech.setLanguage(lang) }
  })
  textDone = true
  if (turn !== voiceTurn || !voiceMode.value) return reveal()
  speech.end(final && final.text)
  maybeReveal()
  // Never keep the answer hidden for long if the voice is slow or unavailable.
  revealTimer = setTimeout(reveal, 2500)
  await spoken
  reveal()
  highlighter.detach()
  pendingReveal = null
  if (turn === voiceTurn && voiceMode.value) voicePhase.value = 'hold'
}

function micAction() {
  if (voicePhase.value === 'listening') {
    voice.commit()
    return
  }
  // Interrupt XO (or resume from hold) and listen. Runs inside the tap, so audio stays unlocked.
  voice.prepare()
  listenTurn()
}

// First-time voice intro: remembered across visits (localStorage), shown again only if storage is unavailable.
function introSeen(mark) {
  try {
    if (mark) window.localStorage.setItem(VOICE_INTRO_KEY, '1')
    return window.localStorage.getItem(VOICE_INTRO_KEY) === '1'
  } catch (e) {
    return false
  }
}

function showVoiceIntro() {
  if (introSeen()) return Promise.resolve()
  introSeen(true)
  introOrbSize.value = Math.round(Math.min(200, (feedRef.value?.clientWidth || 320) * 0.5))
  voiceIntro.value = true
  const beats = setInterval(() => { introBeat.value += 1 }, 280)
  return new Promise((resolve) => {
    const timer = setTimeout(() => { voiceIntro.value = false }, 3000)
    const stopWatching = watch(voiceIntro, (shown) => {
      if (shown) return
      clearTimeout(timer)
      clearInterval(beats)
      stopWatching()
      resolve()
    })
  })
}

async function enterVoiceMode() {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    messages.value.push({ id: newId('ast'), role: 'assistant', content: t('voice_unavailable'), isError: true, timestamp: new Date().toISOString() })
    return
  }
  // Must run synchronously inside the tap: unlocks audio input and playback on Android and iOS.
  voice.prepare()
  primeAudio()
  if (abortController) abortController.abort()
  voiceError.value = ''
  voiceMode.value = true
  voicePhase.value = 'thinking'
  const turn = ++voiceTurn
  const intro = showVoiceIntro()
  try {
    await voice.open()
  } catch (err) {
    voiceIntro.value = false
    voiceError.value = err.message === 'mic_denied' ? t('voice_mic_denied') : t('voice_unavailable')
    voicePhase.value = 'hold'
    return
  }
  await intro
  if (turn === voiceTurn && voiceMode.value) listenTurn()
}

function exitVoiceMode() {
  voiceTurn += 1
  if (pendingReveal) pendingReveal()
  highlighter.detach()
  voiceMode.value = false
  voiceIntro.value = false
  voicePhase.value = 'idle'
  speech.stop()
  voice.close()
  scrollToBottom(true)
}

onMounted(async () => {
  restoreMessages()
  scrollToBottom(true)
  const cfg = await fetchClientConfig()
  if (cfg?.voice) clientConfig.value = cfg
})

onUnmounted(() => {
  if (abortController) abortController.abort()
  exitVoiceMode()
})
</script>

<style scoped>
/* ===== XO widget — design tokens (light / dark) ===== */
.xo-widget {
  --w-bg: #ffffff;
  --w-feed: #f7f6fb;
  --w-line: rgba(15, 23, 42, 0.08);
  --w-ink: #0f172a;
  --w-ink-2: #64748b;
  --w-brand: #5c039b;
  --w-brand-2: #7c2cf0;
  --w-accent: #03a4f4;
  --w-lime: #64ef0a;
  --w-grad: linear-gradient(135deg, #5c039b 0%, #7c2cf0 60%, #03a4f4 140%);
  --w-chip: rgba(92, 3, 155, 0.06);
  --w-chip-hover: rgba(92, 3, 155, 0.12);
  --w-ring: rgba(124, 44, 240, 0.14);
  --w-shadow: 0 28px 70px -18px rgba(38, 10, 74, 0.32), 0 10px 24px -12px rgba(38, 10, 74, 0.22);

  position: relative;
  display: flex;
  flex-direction: column;
  width: 100%;
  height: var(--xo-widget-h, 620px);
  background: var(--w-bg);
  color: var(--w-ink);
  border: 1px solid var(--w-line);
  border-radius: 24px;
  box-shadow: var(--w-shadow);
  overflow: hidden;
  container-type: inline-size;
  font-family: var(--font-body);
  -webkit-tap-highlight-color: transparent;
}
[data-theme="dark"] .xo-widget {
  --w-bg: #110e1f;
  --w-feed: #0b0916;
  --w-line: rgba(255, 255, 255, 0.08);
  --w-ink: #f1f0f7;
  --w-ink-2: #9a97ad;
  --w-brand: #c59bff;
  --w-chip: rgba(168, 85, 247, 0.12);
  --w-chip-hover: rgba(168, 85, 247, 0.22);
  --w-ring: rgba(168, 85, 247, 0.22);
  --w-shadow: 0 28px 70px -18px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(168, 85, 247, 0.12);
}
.xo-widget button { font-family: inherit; -webkit-tap-highlight-color: transparent; }
.xo-widget :focus-visible { outline: 2px solid var(--w-accent); outline-offset: 2px; }

/* ===== Header ===== */
.xo-header {
  position: relative; z-index: 6;
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 12px 10px 12px 14px;
  background: var(--w-bg);
  border-bottom: 1px solid var(--w-line);
}
.xo-brand { display: flex; align-items: center; gap: 10px; min-width: 0; }
.xo-avatar { position: relative; flex: none; width: 38px; height: 38px; padding: 2px; border-radius: 50%; background: var(--w-grad); }
.xo-avatar img { display: block; width: 100%; height: 100%; border-radius: 50%; object-fit: cover; background: #f4efff; }
.xo-online { position: absolute; right: 0; bottom: 0; width: 10px; height: 10px; border-radius: 50%; background: var(--w-lime); box-shadow: 0 0 0 2px var(--w-bg); }
.xo-brand-text { display: flex; flex-direction: column; min-width: 0; line-height: 1.2; }
.xo-brand-text strong { font-family: var(--font-heading); font-size: 1.05rem; font-weight: 700; letter-spacing: 0.01em; }
.xo-brand-text small { font-size: 0.72rem; color: var(--w-ink-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.xo-header-actions { display: flex; align-items: center; gap: 2px; flex: none; }
.xo-chip {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  height: 32px; padding: 0 11px; margin-inline-end: 4px;
  border: 0; border-radius: 999px; cursor: pointer;
  background: var(--w-chip); color: var(--w-brand);
  font-size: 0.78rem; font-weight: 600; white-space: nowrap;
  transition: background 150ms ease, transform 150ms ease;
}
.xo-chip:hover { background: var(--w-chip-hover); }
.xo-chip:active { transform: scale(0.96); }
.xo-divider { width: 1px; height: 20px; margin: 0 4px; background: var(--w-line); }
.xo-icon-btn {
  display: grid; place-items: center; width: 32px; height: 32px;
  border: 0; border-radius: 10px; background: transparent; color: var(--w-ink-2); cursor: pointer;
  transition: background 150ms ease, color 150ms ease;
}
.xo-icon-btn:hover { background: var(--w-chip); color: var(--w-ink); }
.close-widget-btn:hover { background: rgba(220, 38, 38, 0.1); color: #dc2626; }

/* Language menu */
.lang-switch { position: relative; }
.lang-menu {
  position: absolute; top: calc(100% + 8px); inset-inline-end: -4px; z-index: 40;
  width: 236px; max-height: min(340px, 60vh); overflow-y: auto; margin: 0; padding: 6px; list-style: none;
  background: var(--w-bg); border: 1px solid var(--w-line); border-radius: 16px;
  box-shadow: 0 18px 40px -12px rgba(15, 23, 42, 0.3);
}
.lang-menu button {
  display: flex; align-items: center; gap: 10px; width: 100%; padding: 9px 10px;
  border: 0; border-radius: 10px; background: transparent; color: var(--w-ink); cursor: pointer; text-align: start;
}
.lang-menu button:hover { background: var(--w-chip); }
.lang-menu button.active { background: var(--w-chip-hover); color: var(--w-brand); font-weight: 600; }
.lang-native { font-size: 0.92rem; }
.lang-name { font-size: 0.74rem; color: var(--w-ink-2); }
.lang-check { margin-inline-start: auto; }
.chip-code { display: none; }
.chip-caret { opacity: 0.7; transition: transform 180ms ease; }
.chip-caret.open { transform: rotate(180deg); }

/* Hover / keyboard tooltips (pointer devices; touch users get aria-labels and visible labels) */
[data-tip] { position: relative; }
@media (hover: hover) {
  [data-tip]:hover::after, [data-tip]:focus-visible::after {
    content: attr(data-tip); position: absolute; z-index: 60; top: calc(100% + 8px); left: 50%; transform: translateX(-50%);
    padding: 6px 10px; border-radius: 8px; white-space: nowrap; pointer-events: none;
    background: #1d1430; color: #fff; font-size: 0.72rem; font-weight: 500; line-height: 1.2; letter-spacing: 0;
    box-shadow: 0 8px 20px -6px rgba(15, 23, 42, 0.45);
    animation: tipIn 140ms ease 300ms both;
  }
  [data-tip-pos="end"]:hover::after, [data-tip-pos="end"]:focus-visible::after { left: auto; inset-inline-end: 0; transform: none; }
  [data-tip-pos^="top"]:hover::after, [data-tip-pos^="top"]:focus-visible::after { top: auto; bottom: calc(100% + 8px); }
  [data-tip-pos="top-end"]:hover::after, [data-tip-pos="top-end"]:focus-visible::after { left: auto; inset-inline-end: 0; transform: none; }
  [data-tip-pos="top-start"]:hover::after, [data-tip-pos="top-start"]:focus-visible::after { left: 0; transform: none; }
  [dir="rtl"] [data-tip-pos="top-start"]:hover::after { left: auto; right: 0; }
  [data-theme="dark"] [data-tip]:hover::after { background: #f1f0f7; color: #110e1f; }
}
@keyframes tipIn { from { opacity: 0; translate: 0 3px; } to { opacity: 1; translate: 0 0; } }

/* The header adapts to the widget's own width on any device */
@container (max-width: 560px) {
  .advisor-btn .chip-label { display: none; }
  .advisor-btn { width: 32px; padding: 0; margin-inline-end: 2px; }
  .lang-switch-btn { gap: 5px; padding: 0 9px 0 10px; }
}
@container (max-width: 440px) {
  .lang-switch-btn .chip-label { display: none; }
  .lang-switch-btn { gap: 4px; padding: 0 8px 0 9px; }
  .lang-switch-btn .chip-code { display: inline; font-size: 0.74rem; letter-spacing: 0.02em; }
}
@container (max-width: 420px) {
  .tips-toggle-btn { display: none; }
}
@container (max-width: 340px) {
  .theme-toggle-btn, .xo-divider, .xo-brand-text small { display: none; }
}

/* ===== Conversation ===== */
.feed-wrap {
  position: relative; flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column;
  background:
    radial-gradient(120% 50% at 0% 0%, rgba(124, 44, 240, 0.06), transparent 60%),
    radial-gradient(100% 45% at 100% 0%, rgba(3, 164, 244, 0.05), transparent 60%),
    var(--w-feed);
}
/* UAE skyline behind the conversation: fixed while messages scroll, very faint so text stays crisp */
.feed-backdrop {
  position: absolute; left: 0; right: 0; bottom: 0; height: min(46%, 300px); pointer-events: none;
  opacity: 0.075;
  -webkit-mask-image: linear-gradient(to top, #000 55%, transparent);
  mask-image: linear-gradient(to top, #000 55%, transparent);
}
[data-theme="dark"] .feed-backdrop { opacity: 0.16; }
.chat-feed {
  position: relative; z-index: 1;
  flex: 1 1 auto; min-height: 0; overflow-y: auto; overscroll-behavior: contain;
  display: flex; flex-direction: column; gap: 14px;
  padding: 18px 14px 22px;
  scrollbar-width: thin; scrollbar-color: var(--w-line) transparent;
}
.chat-feed::-webkit-scrollbar { width: 6px; }
.chat-feed::-webkit-scrollbar-thumb { background: var(--w-line); border-radius: 6px; }

.xo-hero { display: flex; flex-direction: column; align-items: center; text-align: center; padding: 14px 12px 4px; }
.xo-hero-mascot {
  width: 96px; height: 96px; margin-bottom: 14px; border-radius: 50%; display: grid; place-items: center;
  background: radial-gradient(circle at 50% 40%, rgba(3, 164, 244, 0.18), rgba(124, 44, 240, 0.12) 60%, transparent 72%);
}
.xo-hero-mascot img { width: 84px; height: 84px; object-fit: contain; animation: floatMascot 4s ease-in-out infinite; }
.xo-hero h3 { margin: 0 0 6px; font-family: var(--font-heading); font-size: 1.22rem; font-weight: 700; line-height: 1.3; color: var(--w-ink); max-width: 320px; }
.xo-hero p { margin: 0; font-size: 0.9rem; color: var(--w-ink-2); }
@keyframes floatMascot { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-5px); } }

.lang-divider { display: flex; align-items: center; gap: 10px; margin: 2px 0; color: var(--w-ink-2); font-size: 0.72rem; }
.lang-divider::before, .lang-divider::after { content: ""; flex: 1; height: 1px; background: var(--w-line); }

.typing-indicator { display: flex; align-items: center; gap: 8px; animation: rise 220ms ease both; }
.typing-avatar { width: 28px; height: 28px; border-radius: 50%; object-fit: cover; background: #f4efff; flex: none; }
.typing-pill {
  display: inline-flex; align-items: center; gap: 8px; padding: 9px 13px;
  background: var(--w-bg); border: 1px solid var(--w-line); border-radius: 16px 16px 16px 6px;
  font-size: 0.8rem; color: var(--w-ink-2);
}
[dir="rtl"] .typing-pill { border-radius: 16px 16px 6px 16px; }
.typing-dots { display: inline-flex; gap: 3px; }
.typing-dots i { width: 6px; height: 6px; border-radius: 50%; background: var(--w-brand-2); opacity: 0.35; animation: typing 1.2s infinite ease-in-out; }
.typing-dots i:nth-child(2) { animation-delay: 0.15s; }
.typing-dots i:nth-child(3) { animation-delay: 0.3s; }
@keyframes typing { 0%, 80%, 100% { opacity: 0.25; transform: translateY(0); } 40% { opacity: 1; transform: translateY(-3px); } }
@keyframes rise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

.jump-to-latest-btn {
  position: absolute; left: 50%; bottom: 118px; z-index: 8; transform: translateX(-50%);
  display: inline-flex; align-items: center; gap: 6px; padding: 7px 13px;
  border: 1px solid var(--w-line); border-radius: 999px; cursor: pointer;
  background: var(--w-bg); color: var(--w-brand); font-size: 0.76rem; font-weight: 600;
  box-shadow: 0 8px 20px -8px rgba(15, 23, 42, 0.3);
}

/* ===== Text input ===== */
.chat-footer { padding: 10px 12px 2px; background: var(--w-bg); border-top: 1px solid var(--w-line); }
.input-form {
  display: flex; align-items: center; gap: 4px; padding: 5px 5px 5px 16px;
  border: 1px solid var(--w-line); border-radius: 999px; background: var(--w-feed);
  transition: border-color 150ms ease, box-shadow 150ms ease, background 150ms ease;
}
[dir="rtl"] .input-form { padding: 5px 16px 5px 5px; }
.input-form:focus-within { border-color: rgba(124, 44, 240, 0.45); box-shadow: 0 0 0 4px var(--w-ring); background: var(--w-bg); }
.chat-input-field {
  flex: 1 1 auto; min-width: 0; padding: 10px 0; border: 0; outline: none; background: transparent;
  color: var(--w-ink); font-size: 0.95rem; font-family: inherit;
}
.chat-input-field::placeholder { color: var(--w-ink-2); opacity: 0.85; }
.chat-input-field:focus-visible { outline: none; }
.mic-btn, .send-btn {
  flex: none; display: grid; place-items: center; width: 40px; height: 40px;
  border: 0; border-radius: 50%; cursor: pointer; transition: transform 150ms ease, background 150ms ease, opacity 150ms ease;
}
.mic-btn { background: transparent; color: var(--w-brand); }
.mic-btn:hover { background: var(--w-chip-hover); }
.send-btn { background: var(--w-grad); color: #fff; box-shadow: 0 6px 14px -6px rgba(92, 3, 155, 0.6); }
.send-btn:hover:not(:disabled) { transform: translateY(-1px); }
.send-btn:disabled { background: var(--w-line); color: var(--w-ink-2); box-shadow: none; cursor: default; }
.mic-btn:active, .send-btn:active:not(:disabled) { transform: scale(0.94); }
.input-disclaimer {
  padding: 6px 16px calc(8px + env(safe-area-inset-bottom, 0px));
  background: var(--w-bg); color: var(--w-ink-2); font-size: 0.68rem; line-height: 1.35; text-align: center;
}

/* ===== Voice dock ===== */
.voice-dock {
  position: relative; display: flex; align-items: center; gap: 10px;
  padding: 8px 12px 2px 8px; background: var(--w-bg); border-top: 1px solid var(--w-line);
}
.voice-dock::before {
  content: ""; position: absolute; left: 0; right: 0; top: -1px; height: 2px; background: var(--w-grad); opacity: 0.55;
}
.voice-orb-btn {
  position: relative; flex: none; display: grid; place-items: center; width: 68px; height: 68px; padding: 0;
  border: 0; border-radius: 50%; background: transparent; cursor: pointer; transition: transform 150ms ease;
}
.voice-orb-btn :deep(canvas) { position: absolute; inset: 0; }
.voice-orb-btn:active { transform: scale(0.95); }
.orb-heartbeat {
  position: absolute; inset: 6px; border-radius: 50%; pointer-events: none;
  border: 2px solid rgba(124, 44, 240, 0.55);
  animation: heartbeat 1.1s ease-out both;
}
@keyframes heartbeat {
  0% { transform: scale(0.85); opacity: 0; }
  12% { transform: scale(1.12); opacity: 0.9; }
  24% { transform: scale(0.98); opacity: 0.5; }
  38% { transform: scale(1.22); opacity: 0.8; }
  100% { transform: scale(1.45); opacity: 0; }
}
.orb-glyph {
  position: relative; z-index: 1; display: grid; place-items: center; width: 34px; height: 34px; border-radius: 50%;
  background: rgba(92, 3, 155, 0.78); color: #fff; box-shadow: 0 4px 12px -2px rgba(92, 3, 155, 0.6);
}
.orb-glyph:empty { display: none; }
.orb-badge {
  position: absolute; right: 6px; bottom: 6px; z-index: 2; display: grid; place-items: center; width: 20px; height: 20px;
  border-radius: 50%; background: #5c039b; color: #fff; box-shadow: 0 0 0 2px var(--w-bg);
}
.voice-dock-text { flex: 1 1 auto; min-width: 0; }
.voice-dock-status { display: block; font-size: 0.86rem; font-weight: 600; color: var(--w-ink); }
.voice-dock.phase-listening .voice-dock-status { color: var(--w-brand); }
.voice-dock-caption {
  margin: 3px 0 0; font-size: 0.92rem; line-height: 1.35; color: var(--w-ink-2);
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.voice-error-text { margin: 4px 0 0; color: #dc2626; font-size: 0.8rem; }
.voice-dock-actions { display: flex; align-items: center; gap: 8px; flex: none; }
.xo-round-btn {
  display: grid; place-items: center; width: 44px; height: 44px; border-radius: 50%; cursor: pointer;
  border: 1px solid var(--w-line); background: var(--w-bg); color: var(--w-ink-2);
  transition: background 150ms ease, color 150ms ease, transform 150ms ease;
}
.xo-round-btn:active { transform: scale(0.94); }
.xo-round-btn.cancel:hover { background: rgba(220, 38, 38, 0.08); color: #dc2626; }
.xo-round-btn.confirm { border: 0; background: var(--w-grad); color: #fff; box-shadow: 0 6px 14px -6px rgba(92, 3, 155, 0.6); }

/* First-time voice intro */
.voice-intro {
  position: absolute; inset: 0; z-index: 30; cursor: pointer;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 18px; padding: 24px;
  background: radial-gradient(circle at 50% 42%, #2a0a52 0%, #140829 55%, #07040f 100%);
  color: #fff; text-align: center;
}
.voice-intro-text { max-width: 290px; margin: 0; font-size: 1rem; line-height: 1.55; color: rgba(255, 255, 255, 0.92); animation: rise 600ms 500ms ease both; }

/* ===== Transitions ===== */
.dock-enter-active, .dock-leave-active { transition: opacity 160ms ease, transform 160ms ease; }
.dock-enter-from, .dock-leave-to { opacity: 0; transform: translateY(10px); }
.voice-intro-enter-active, .voice-intro-leave-active { transition: opacity 350ms ease; }
.voice-intro-enter-from, .voice-intro-leave-to { opacity: 0; }
.pop-enter-active, .pop-leave-active { transition: opacity 140ms ease, transform 140ms ease; }
.pop-enter-from, .pop-leave-to { opacity: 0; transform: translateY(-4px) scale(0.97); }
.jump-to-latest-btn.pop-enter-from, .jump-to-latest-btn.pop-leave-to { transform: translateX(-50%) translateY(6px); }

.visually-hidden { position: absolute !important; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip: rect(0 0 0 0); border: 0; white-space: nowrap; }

/* Comfortable touch targets on phones and tablets */
@media (pointer: coarse) {
  .xo-icon-btn, .xo-chip { min-width: 36px; height: 36px; }
  .chat-input-field { font-size: 16px; } /* prevents iOS zoom on focus */
}
@media (prefers-reduced-motion: reduce) {
  .xo-hero-mascot img, .typing-dots i, .voice-intro-text, .typing-indicator, .orb-heartbeat { animation: none !important; }
}
</style>
