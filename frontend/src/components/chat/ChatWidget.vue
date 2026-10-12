<template>
  <div class="chat-widget-wrapper glass-panel" :class="{ 'is-expanded': isExpanded }" role="region" aria-label="XO Conversational Assistant">
    <!-- Chat Header with XO Mascot Avatar -->
    <div class="chat-header">
      <div class="chat-header-brand">
        <div class="mascot-avatar-container">
          <img src="/xo-mascot.png" alt="XO Mascot" class="mascot-avatar-img" />
          <span class="live-status-dot"></span>
        </div>
        <div class="header-brand-info">
          <div class="header-brand-title">
            <h3 class="header-title">XO</h3>
            <span class="badge-online">ONLINE</span>
          </div>
          <span class="header-status" :title="activeLanguageLabel + ' • Luxury Property & Mortgage Specialist'">
            {{ activeLanguageLabel }} &bull; Real Estate &amp; Mortgages
          </span>
        </div>
      </div>

      <div class="header-actions">
        <!-- Context Pills -->
        <div class="header-pills-group">
          <!-- Persistent Human Handoff (FR-5) -->
          <button 
            class="handoff-btn" 
            @click="requestHandoff" 
            title="Connect with Human Specialist"
            aria-label="Connect with Human Specialist"
            data-tooltip="Human Advisor"
            data-tooltip-pos="bottom"
          >
            <span class="pill-icon">🎧</span>
            <span class="pill-label">Advisor</span>
          </button>

          <!-- User Auth Context Toggle (FR-21/FR-22) -->
          <button 
            class="auth-toggle-btn" 
            @click="toggleAuthUser" 
            :title="currentUserId ? 'Authenticated: Siraj Munir (VIP Client). Click to switch to Guest mode.' : 'Guest Mode (Unauthenticated). Click to switch to VIP Client.'"
            :aria-label="currentUserId ? 'Signed in as Siraj Munir' : 'Guest Mode'"
            :data-tooltip="currentUserId ? '👑 VIP: Siraj (Sign Out)' : '👤 Guest (Sign In)'"
            data-tooltip-pos="bottom"
          >
            <span class="pill-icon">{{ currentUserId ? '👑' : '👤' }}</span>
            <span class="pill-label">{{ currentUserId ? 'Siraj' : 'Guest' }}</span>
          </button>
        </div>

        <!-- Utility Action Controls Cluster -->
        <div class="header-tools-group">
          <!-- Theme Toggle (Light / Dark) -->
          <button 
            class="icon-btn theme-toggle-btn"
            @click="toggleTheme" 
            :title="currentTheme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'"
            :aria-label="currentTheme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'"
            data-tooltip="Theme"
            data-tooltip-pos="bottom"
          >
            <span>{{ currentTheme === 'light' ? '🌙' : '☀️' }}</span>
          </button>

          <!-- Feature Tips Toggle -->
          <button 
            class="icon-btn tips-toggle-btn" 
            @click="showTips = !showTips" 
            title="Toggle Feature Tips (💡)"
            aria-label="Toggle Feature Tips"
            data-tooltip="Tips"
            data-tooltip-pos="bottom"
          >
            <span>💡</span>
          </button>

          <!-- Clear Chat Button with explicit Clear Chat hover tooltip -->
          <button 
            class="icon-btn clear-chat-btn" 
            @click="clearChat" 
            title="Clear Chat"
            aria-label="Clear Chat"
          >
            <span class="btn-icon">🗑️</span>
            <span class="clear-tooltip-bubble">Clear Chat</span>
          </button>

          <!-- Resize / Preview Size Toggle (Arrow button) -->
          <button 
            class="icon-btn resize-toggle-btn" 
            @click="$emit('toggle-expand')" 
            :title="isExpanded ? 'Restore compact view (⤡)' : 'Expand to larger view (⤢)'"
            :aria-label="isExpanded ? 'Restore compact view' : 'Expand preview'"
            :data-tooltip="isExpanded ? 'Compact' : 'Expand'"
            data-tooltip-pos="bottom"
          >
            <span class="resize-icon">{{ isExpanded ? '⤡' : '⤢' }}</span>
          </button>

          <!-- Close Chatbot Button (✕) -->
          <button 
            class="icon-btn close-widget-btn" 
            @click="$emit('close')" 
            title="Close Chatbot (✕)"
            aria-label="Close Chatbot"
            data-tooltip="Close"
            data-tooltip-pos="bottom"
          >
            <span>✕</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Onboarding Feature Tips (Prompt Section 6) -->
    <OnboardingTooltips 
      :is-open="showTips" 
      @close="showTips = false" 
    />

    <!-- Dedicated Voice Mode Screen: Replicates Perplexity AI Voice UI & Animation -->
    <div 
      v-if="isVoiceActive" 
      class="pplx-voice-screen" 
      :class="{ 'is-speaking': Boolean(liveSpokenText.trim()) }"
    >
      <div class="pplx-voice-stage">
        <!-- 3D Particle Sphere Model (Perplexity Orb) -->
        <div class="pplx-orb-container">
          <VoiceVisualizer 
            :is-active="isVoiceActive" 
            :audio-level="currentAudioLevel"
            :is-compact="Boolean(liveSpokenText.trim())"
          />
        </div>

        <!-- Live Speech Transcription / Prompt Text -->
        <div class="pplx-text-zone">
          <p v-if="liveSpokenText.trim()" class="pplx-transcript-text">
            “{{ liveSpokenText }}”
          </p>
          <p v-else class="pplx-prompt-text">
            Say something...
          </p>
          <div v-if="silenceTimerActive && liveSpokenText.trim()" class="pplx-silence-pulse">
            <span class="pplx-silence-dot"></span>
            <span>Sending in 2s...</span>
          </div>
        </div>

        <!-- Circular Action Buttons: Cross ✕ on Left, Tick ✓ on Right -->
        <div class="pplx-actions-row">
          <!-- Cross / Cancel Button -->
          <button 
            type="button" 
            class="pplx-action-btn pplx-btn-cancel" 
            @click="cancelVoiceInput"
            title="Cancel voice input (✕)"
            aria-label="Cancel Voice Input"
          >
            ✕
          </button>

          <!-- Tick / Confirm Button -->
          <button 
            type="button" 
            class="pplx-action-btn pplx-btn-confirm" 
            :disabled="!liveSpokenText.trim() && !inputQuery.trim() && audioChunks.length === 0"
            @click="confirmVoiceInput"
            title="Send speech to chat (✓)"
            aria-label="Confirm Voice Input"
          >
            ✓
          </button>
        </div>
      </div>
    </div>

    <!-- Standard Chat Interface: Displayed when Voice Mode is NOT active -->
    <template v-else>
      <!-- Message Feed -->
      <div class="chat-feed" ref="feedRef" role="log" aria-live="polite" @scroll="handleFeedScroll">
        <!-- HERO CENTERPIECE: Shown upon opening / at start of conversation -->
        <div v-if="messages.length <= 1" class="hero-centerpiece glass-card">
          <div class="hero-badge">
            <span class="pulse-dot"></span>
            <span>XO AI v4.2</span>
          </div>

          <div class="hero-mascot-visual">
            <img src="/xo-mascot.png" alt="XO Assistant Mascot" class="hero-mascot-img" />
          </div>

          <h3 class="hero-greeting-title">
            How can I assist your UAE investment journey today?
          </h3>
          <p class="hero-greeting-sub">
            Speak or message naturally in English, Arabic, Hindi, or Urdu.
          </p>
        </div>

        <!-- Messages Stream -->
        <MessageItem 
          v-for="msg in messages" 
          :key="msg.id" 
          :message="msg"
          @select-property-mortgage="handlePropertyMortgageCheck"
          @jump-to-properties="handleJumpToProperties"
          @shortlist-property="handleShortlistProperty"
        />

        <!-- Streaming / Typing Indicator -->
        <div class="typing-indicator" v-if="isTyping">
          <div class="mascot-typing-avatar">
            <img src="/xo-mascot.png" alt="XO" class="typing-mascot-img" />
          </div>
          <div class="typing-dots-wrapper">
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
            <span class="typing-text">XO AI is analyzing market data...</span>
          </div>
        </div>
      </div>

      <!-- Floating Jump to Latest Button (Auto-scroll assistance) -->
      <transition name="jump-fade">
        <button 
          v-if="isUserScrolledUp" 
          type="button" 
          class="jump-to-latest-btn" 
          @click="scrollToLatest"
          title="Jump to latest message"
          aria-label="Jump to latest message"
        >
          <span class="jump-arrow">↓</span>
          <span class="jump-text">Latest</span>
        </button>
      </transition>

      <!-- Compact Voice Playback Bar (when XO is speaking back audio) -->
      <div v-if="isPlayingVoice" class="voice-playback-bar" @click="stopVoicePlayback" title="Click to stop voice playback">
        <span class="playback-dot"></span>
        <span class="playback-text">XO is speaking • Click to interrupt</span>
        <button type="button" class="btn-stop-playback" @click.stop="stopVoicePlayback" aria-label="Stop audio">⏹</button>
      </div>

      <!-- Advisor Standby Notification Bar -->
      <div class="advisor-standby-bar">
        <div class="standby-status">
          <span class="standby-icon">🎧</span>
          <span class="standby-text">
            Advisor on Standby: <strong>4 licensed specialists</strong> available
          </span>
        </div>
        <button 
          type="button" 
          class="btn-standby-connect" 
          @click="requestHandoff"
          title="Connect with a licensed human specialist"
          data-tooltip="Connect with 1 of 4 advisors"
          data-tooltip-pos="left"
        >
          Connect
        </button>
      </div>

      <!-- Chat Input Controls (Floating Pill Dock) -->
      <div class="chat-footer">
        <form @submit.prevent="sendMessage" class="input-form">
          <label for="chat-text-input" class="visually-hidden">Type your message</label>
          <input 
            id="chat-text-input"
            ref="inputRef"
            v-model="inputQuery" 
            type="text" 
            :placeholder="inputPlaceholder" 
            class="chat-input-field"
            :disabled="isTyping"
            autocomplete="off"
          />

          <!-- Microphone Button -->
          <button 
            type="button" 
            class="mic-btn" 
            :class="{ 'speaking': isPlayingVoice }"
            @click="toggleVoiceRecording"
            :title="isPlayingVoice ? 'Interrupt XO & Speak' : 'Tap to Speak (Voice STT in EN, AR, HI, UR)'"
            aria-label="Microphone Voice Input"
            :data-tooltip="isPlayingVoice ? 'Click to Interrupt & Speak' : 'Voice Input: Tap to Speak'"
            data-tooltip-pos="left"
          >
            <svg class="mic-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
              <line x1="12" y1="19" x2="12" y2="22"></line>
            </svg>
          </button>

          <!-- Send Button: Purple circle with upward arrow -->
          <button 
            type="submit" 
            class="send-btn" 
            :disabled="!inputQuery.trim() || isTyping"
            title="Send message (Enter)"
            aria-label="Send Message"
            data-tooltip="Send message (Enter)"
            data-tooltip-pos="left"
          >
            <span class="send-arrow">↑</span>
          </button>
        </form>
      </div>

      <!-- Legal Disclaimer Under Input -->
      <div class="input-disclaimer">
        <span>XO AI provides informational estimates based on official UAE Central Bank &amp; DLD guidelines. Real-time rates subject to bank approval.</span>
      </div>
    </template>

    <!-- Audio Element for synthesized TTS playback -->
    <audio ref="audioPlayerRef" @ended="stopVoicePlayback" class="visually-hidden"></audio>

    <!-- Anonymous Shortlist Lead Capture Modal (FR-10) -->
    <div v-if="showLeadCaptureModal" class="lead-modal-overlay" @click.self="showLeadCaptureModal = false">
      <div class="lead-modal-card glass-card">
        <div class="lead-modal-header">
          <div class="lead-modal-title">
            <img src="/xo-mascot.png" alt="XO Mascot" class="modal-mascot-icon" />
            <div>
              <h4>Save to Shortlist &amp; Request Brochure</h4>
              <span class="modal-sub">Direct access to XO Luxury Advisory</span>
            </div>
          </div>
          <button class="lead-modal-close" @click="showLeadCaptureModal = false" aria-label="Close modal">✕</button>
        </div>

        <p class="lead-modal-subtitle" v-if="selectedShortlistProp">
          You shortlisted <strong>{{ selectedShortlistProp.title }}</strong> (AED {{ formatNumber(selectedShortlistProp.price) }}). Enter your contact details to save your portfolio and receive official floor plans, payment schedules, and DLD verification directly from an XO Luxury Specialist.
        </p>

        <form @submit.prevent="submitLeadCapture" class="lead-form">
          <div class="form-group">
            <label for="lead-name">Full Name</label>
            <input 
              id="lead-name" 
              v-model="leadForm.name" 
              type="text" 
              placeholder="e.g. Alex Henderson" 
              required 
              class="lead-input"
            />
          </div>

          <div class="form-group">
            <label for="lead-email">Email Address</label>
            <input 
              id="lead-email" 
              v-model="leadForm.email" 
              type="email" 
              placeholder="e.g. alex@example.com" 
              required 
              class="lead-input"
            />
          </div>

          <div class="form-group">
            <label for="lead-phone">Phone / WhatsApp</label>
            <input 
              id="lead-phone" 
              v-model="leadForm.phone" 
              type="tel" 
              placeholder="e.g. +971 50 123 4567" 
              required 
              class="lead-input"
            />
          </div>

          <div class="lead-modal-actions">
            <button type="button" class="btn-cancel" @click="showLeadCaptureModal = false">
              Maybe Later
            </button>
            <button type="submit" class="btn-submit" :disabled="isSubmittingLead">
              {{ isSubmittingLead ? 'Saving...' : 'Save & Send Brochure' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted, nextTick, toRefs } from 'vue'
import MessageItem from './MessageItem.vue'
import OnboardingTooltips from './OnboardingTooltips.vue'
import VoiceVisualizer from './VoiceVisualizer.vue'

const props = defineProps({
  currentLanguage: {
    type: String,
    default: 'en'
  },
  currentTheme: {
    type: String,
    default: 'light'
  },
  isExpanded: {
    type: Boolean,
    default: false
  }
})

const { isExpanded } = toRefs(props)

const emit = defineEmits(['close', 'language-changed', 'update:currentTheme', 'toggle-expand'])

const SESSION_STORAGE_KEY_ID = 'xo_session_id'
const SESSION_STORAGE_KEY_MESSAGES = 'xo_chat_messages'

// Initialize or restore session ID across widget close/reopen and page loads
const getInitialSessionId = () => {
  if (typeof window !== 'undefined' && window.sessionStorage) {
    const saved = window.sessionStorage.getItem(SESSION_STORAGE_KEY_ID)
    if (saved) return saved
    const newId = `sess_${Math.random().toString(36).substring(2, 10)}`
    window.sessionStorage.setItem(SESSION_STORAGE_KEY_ID, newId)
    return newId
  }
  return `sess_${Math.random().toString(36).substring(2, 10)}`
}

const messages = ref([])
const inputQuery = ref('')
const isTyping = ref(false)
const isRecording = ref(false)
const isPlayingVoice = ref(false)
const showTips = ref(false)
const sessionId = ref(getInitialSessionId())

// Phase 6: Authenticated User Context (FR-21, FR-22, FR-23)
// Default to Siraj Munir VIP client; can toggle to null (Guest) to test unauthenticated rejection flow
const currentUserId = ref('user_siraj_vip')
const toggleAuthUser = () => {
  currentUserId.value = currentUserId.value ? null : 'user_siraj_vip'
}

// Voice UX Refinement State
const hasVoiceSessionGreeted = ref(false)
const isVoiceActive = ref(false)
const isVoiceInFlight = ref(false)
const recordedAudioBlob = ref(null)
const liveSpokenText = ref('')
const currentAudioLevel = ref(0)
const hasMeaningfulSpeech = ref(false)
const silenceTimerActive = ref(false)
let silenceTimer = null
let audioContext = null
let analyserNode = null
let audioAnalysisInterval = null
let speechRecognition = null
let voiceAbortController = null

const voiceStatusLabel = computed(() => {
  if (silenceTimerActive.value) {
    return 'Silence detected • Auto-sending in 2s...'
  }
  if (isRecording.value) {
    return liveSpokenText.value 
      ? 'Listening • ' + (liveSpokenText.value.length > 28 ? liveSpokenText.value.slice(-28) : liveSpokenText.value)
      : 'Listening (Speak in EN, AR, HI, UR)...'
  }
  if (isPlayingVoice.value) {
    return 'Speaking (XO Audio Stream) • Click mic to interrupt'
  }
  return 'Voice Mode Active'
})

const feedRef = ref(null)
const inputRef = ref(null)
const audioPlayerRef = ref(null)

const toggleTheme = () => {
  const nextTheme = props.currentTheme === 'light' ? 'dark' : 'light'
  emit('update:currentTheme', nextTheme)
}

const activeLanguageLabel = computed(() => {
  const map = { en: 'English', ar: 'العربية', hi: 'हिन्दी', ur: 'اردو' }
  return map[props.currentLanguage] || 'English'
})

const inputPlaceholder = computed(() => {
  const map = {
    ar: 'اسأل عن عقار في دبي، أو احسب قسط التمويل...',
    hi: 'दुबई में प्रॉपर्टी खोजें या मॉर्गेज EMI की गणना करें...',
    ur: 'دبئی میں پراپرٹی سرچ کریں یا مارگیج قسط معلوم کریں...',
    en: 'Ask about properties, mortgage eligibility, or market analysis...'
  }
  return map[props.currentLanguage] || map.en
})

// Automated Welcome Message upon Opening (FR-1 / Prompt Section 6)
const initializeWelcomeMessage = () => {
  const welcomeTexts = {
    ar: 'أهلاً بك في XO! أنا مساعدك الذكي للعقارات والتمويل العقاري في الإمارات. كيف يمكنني مساعدتك اليوم؟',
    hi: 'नमस्ते! मैं XO हूँ, यूएई में प्रॉपर्टी और होम लोन के लिए आपका एआई सहायक। आज मैं आपकी क्या सहायता कर सकता हूँ?',
    ur: 'خوش آمدید! میں XO ہوں، متحدہ عرب امارات میں پراپرٹی اور مارگیج کے لیے آپ کا AI اسسٹنٹ۔ میں آپ کی کیا مدد کر سکتا ہوں؟',
    en: 'Welcome to XO! I am your AI assistant for premier properties, mortgage affordability, and instant guidance across the UAE. How can I help you today?'
  }

  messages.value.push({
    id: 'welcome-msg',
    role: 'assistant',
    content: welcomeTexts[props.currentLanguage] || welcomeTexts.en,
    timestamp: new Date().toISOString(),
    language: props.currentLanguage
  })
}

// Restore previous messages from sessionStorage or initialize fresh welcome message
const initializeChatSession = () => {
  if (typeof window !== 'undefined' && window.sessionStorage) {
    const saved = window.sessionStorage.getItem(SESSION_STORAGE_KEY_MESSAGES)
    if (saved) {
      try {
        const parsed = JSON.parse(saved)
        if (Array.isArray(parsed) && parsed.length > 0) {
          // Filter out corrupted/empty placeholder assistant messages and clear any stuck streaming flags
          const cleaned = parsed
            .filter(msg => msg.role === 'user' || (msg.role === 'assistant' && (msg.content?.trim() || msg.metadata?.property_results?.length || msg.metadata?.mortgage_result)))
            .map(msg => ({
              ...msg,
              isStreaming: false
            }))
          if (cleaned.length > 0) {
            messages.value = cleaned
            return
          }
        }
      } catch (e) {
        console.warn('Could not parse saved chat messages:', e)
      }
    }
  }
  initializeWelcomeMessage()
}

// Watch and persist messages to sessionStorage so state is never lost on widget close
watch(messages, (newMsgs) => {
  if (typeof window !== 'undefined' && window.sessionStorage) {
    try {
      window.sessionStorage.setItem(SESSION_STORAGE_KEY_MESSAGES, JSON.stringify(newMsgs))
    } catch (e) {
      console.warn('Could not persist messages to sessionStorage:', e)
    }
  }
}, { deep: true })

// Reset voice greeting status when user switches language so XO greets in the new language
watch(() => props.currentLanguage, () => {
  hasVoiceSessionGreeted.value = false
  if (isVoiceActive.value || isRecording.value) {
    cancelVoiceInput()
  }
})

// Auto-trigger silence countdown whenever spoken text updates
watch(liveSpokenText, (newText) => {
  if (isVoiceActive.value && !isVoiceInFlight.value && newText.trim()) {
    restartSilenceTimer()
  }
})

const clearChat = () => {
  messages.value = []
  
  if (typeof window !== 'undefined' && window.sessionStorage) {
    window.sessionStorage.removeItem(SESSION_STORAGE_KEY_MESSAGES)
    
    // Generate a fresh session ID for the backend
    const newId = `sess_${Math.random().toString(36).substring(2, 10)}`
    window.sessionStorage.setItem(SESSION_STORAGE_KEY_ID, newId)
    sessionId.value = newId
  }

  // Stop active processes
  if (isPlayingVoice.value) stopVoicePlayback()
  if (isVoiceActive.value || isRecording.value) {
    if (typeof cancelVoiceInput === 'function') cancelVoiceInput()
  }
  if (chatAbortController) {
    chatAbortController.abort()
    chatAbortController = null
  }
  isTyping.value = false

  // Re-initialize the welcome message
  initializeWelcomeMessage()
}

// Scroll and Progressive Auto-Scroll State
const isUserScrolledUp = ref(false)
let chatAbortController = null

const handleFeedScroll = () => {
  if (!feedRef.value) return
  const el = feedRef.value
  // User is considered at bottom if within 60px of the bottom edge
  const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  isUserScrolledUp.value = distanceFromBottom > 60
}

const scrollToLatest = () => {
  isUserScrolledUp.value = false
  if (feedRef.value) {
    feedRef.value.scrollTo({
      top: feedRef.value.scrollHeight,
      behavior: 'smooth'
    })
  }
}

const scrollToBottom = async () => {
  await nextTick()
  if (feedRef.value) {
    feedRef.value.scrollTop = feedRef.value.scrollHeight
  }
}

const conditionallyScrollToBottom = async (force = false) => {
  await nextTick()
  if (!feedRef.value) return
  if (force || !isUserScrolledUp.value) {
    feedRef.value.scrollTop = feedRef.value.scrollHeight
  }
}

const sendQuickPrompt = (text) => {
  inputQuery.value = text
  sendMessage()
}

const sendMessage = async () => {
  if (isPlayingVoice.value) {
    stopVoicePlayback()
  }
  const query = inputQuery.value.trim()
  if (!query) return

  // Abort any in-flight streaming request cleanly
  if (chatAbortController) {
    chatAbortController.abort()
    chatAbortController = null
  }

  // Add User Message
  messages.value.push({
    id: `usr_${Date.now()}`,
    role: 'user',
    content: query,
    timestamp: new Date().toISOString(),
    language: props.currentLanguage
  })
  inputQuery.value = ''
  isTyping.value = true
  isUserScrolledUp.value = false
  await conditionallyScrollToBottom(true)

  // Do NOT add an empty assistant message yet!
  // While XO AI is analyzing, the user sees ONLY the typing indicator:
  // "XO AI is analyzing market data..."
  let assistantMsg = null

  chatAbortController = new AbortController()

  const processChunkPayload = (payload) => {
    // When the first packet arrives, dismiss the typing indicator and instantiate the reactive assistant message
    if (!assistantMsg) {
      isTyping.value = false
      assistantMsg = reactive({
        id: `ast_${Date.now()}`,
        role: 'assistant',
        content: '',
        isStreaming: true,
        timestamp: new Date().toISOString(),
        language: props.currentLanguage,
        metadata: {}
      })
      messages.value.push(assistantMsg)
    }

    if (payload.error) {
      assistantMsg.content = `Notice: ${payload.error}`
      assistantMsg.isStreaming = false
      return
    }

    if (payload.token) {
      assistantMsg.content += payload.token
      conditionallyScrollToBottom(false)
    }

    if (payload.is_final) {
      assistantMsg.isStreaming = false
      if (payload.text && !assistantMsg.content) {
        assistantMsg.content = payload.text
      }
      if (payload.language && payload.language !== props.currentLanguage) {
        emit('language-changed', payload.language)
      }
      assistantMsg.metadata = {
        property_results: payload.property_results || [],
        mortgage_result: payload.mortgage_result || null,
        saved_properties: payload.saved_properties || [],
        application_status: payload.application_status || null,
        handoff_data: payload.handoff_data || null
      }
      conditionallyScrollToBottom(false)
    }
  }

  try {
    const headers = {
      'Content-Type': 'application/json',
      'X-Session-ID': sessionId.value
    }
    if (currentUserId.value) {
      headers['X-User-ID'] = currentUserId.value
    }

    const res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers,
      signal: chatAbortController.signal,
      body: JSON.stringify({
        message: query,
        session_id: sessionId.value,
        language: props.currentLanguage
      })
    })

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}))
      throw new Error(errData.detail || `Server error (${res.status})`)
    }

    if (!res.body) {
      throw new Error('Streaming response body unavailable')
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let sseBuffer = ''

    while (true) {
      const { value, done } = await reader.read()
      if (done) {
        if (sseBuffer.trim()) {
          const remainingLines = sseBuffer.split('\n\n')
          for (const line of remainingLines) {
            const trimmed = line.trim()
            if (trimmed.startsWith('data: ')) {
              try {
                processChunkPayload(JSON.parse(trimmed.slice(6)))
              } catch (e) {}
            }
          }
        }
        break
      }

      sseBuffer += decoder.decode(value, { stream: true })
      const lines = sseBuffer.split('\n\n')
      sseBuffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data: ')) continue

        try {
          const payload = JSON.parse(trimmed.slice(6))
          processChunkPayload(payload)
        } catch (jsonErr) {
          console.warn('Failed to parse SSE JSON chunk:', jsonErr, trimmed)
        }
      }
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      console.log('Chat stream turn cancelled by user or next request.')
    } else {
      console.error('Streaming turn error:', err)
      isTyping.value = false
      if (!assistantMsg) {
        assistantMsg = reactive({
          id: `ast_${Date.now()}`,
          role: 'assistant',
          content: `Notice: ${err.message || 'Unable to connect to assistant.'}`,
          isStreaming: false,
          timestamp: new Date().toISOString(),
          language: props.currentLanguage,
          metadata: {}
        })
        messages.value.push(assistantMsg)
      } else {
        if (!assistantMsg.content) {
          assistantMsg.content = `Notice: ${err.message || 'Unable to connect to assistant.'}`
        }
        assistantMsg.isStreaming = false
      }
    }
  } finally {
    isTyping.value = false
    if (assistantMsg) {
      assistantMsg.isStreaming = false
    }
    chatAbortController = null
    conditionallyScrollToBottom(false)
  }
}

// Composed Voice-to-Voice (V2V) Interaction
const mediaRecorder = ref(null)
const audioChunks = ref([])

const stopVoicePlayback = () => {
  if (audioPlayerRef.value) {
    try {
      audioPlayerRef.value.pause()
      audioPlayerRef.value.currentTime = 0
      audioPlayerRef.value.removeAttribute('src')
      audioPlayerRef.value.load()
    } catch (e) {
      console.warn('Error pausing audio playback:', e)
    }
  }
  isPlayingVoice.value = false
}

// 1. Voice Session Greeting (Requirement 1)
const playVoiceGreeting = async () => {
  const welcomeTexts = {
    ar: 'أهلاً بك في XO! أنا مساعدك الذكي للعقارات والتمويل العقاري في الإمارات. كيف يمكنني مساعدتك اليوم؟',
    hi: 'नमस्ते! मैं XO हूँ, यूएई में प्रॉपर्टी और होम लोन के लिए आपका एआई सहायक। आज मैं आपकी क्या सहायता कर सकता हूँ?',
    ur: 'خوش آمدید! میں XO ہوں، متحدہ عرب امارات میں پراپرٹی اور مارگیج کے لیے آپ کا AI اسسٹنٹ۔ میں آپ کی کیا مدد کر سکتا ہوں؟',
    en: 'Welcome to XO! I am your AI assistant for premier properties, mortgage affordability, and instant guidance across the UAE. How can I help you today?'
  }
  const text = welcomeTexts[props.currentLanguage] || welcomeTexts.en

  // Ensure greeting text is present in the feed if empty
  if (messages.value.length === 0) {
    messages.value.push({
      id: 'welcome-msg',
      role: 'assistant',
      content: text,
      timestamp: new Date().toISOString(),
      language: props.currentLanguage
    })
  }

  try {
    const res = await fetch('/api/voice/synthesize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, language: props.currentLanguage })
    })

    if (res.ok && audioPlayerRef.value) {
      const blob = await res.blob()
      const audioUrl = URL.createObjectURL(blob)
      stopVoicePlayback()
      isPlayingVoice.value = true
      audioPlayerRef.value.src = audioUrl

      audioPlayerRef.value.onended = () => {
        stopVoicePlayback()
        startVoiceRecording()
      }

      await audioPlayerRef.value.play().catch((err) => {
        console.warn('Greeting playback auto-play error:', err)
        isPlayingVoice.value = false
        startVoiceRecording()
      })
      return
    }
  } catch (err) {
    console.warn('Voice greeting error:', err)
  }

  // Fallback if audio playback fails: smoothly proceed to recording
  startVoiceRecording()
}

// 2. Start Voice Recording & Live Speech Recognition (Requirement 2)
const resetSilenceTimer = () => {
  if (silenceTimer) {
    clearTimeout(silenceTimer)
    silenceTimer = null
  }
  silenceTimerActive.value = false
}

const restartSilenceTimer = () => {
  if (silenceTimer) {
    clearTimeout(silenceTimer)
    silenceTimer = null
  }
  if (!isVoiceActive.value || isVoiceInFlight.value) {
    silenceTimerActive.value = false
    return
  }
  const text = liveSpokenText.value.trim() || inputQuery.value.trim()
  if (!text) {
    silenceTimerActive.value = false
    return
  }

  silenceTimerActive.value = true
  silenceTimer = setTimeout(async () => {
    silenceTimerActive.value = false
    silenceTimer = null
    // Auto-confirm & submit after 2 seconds of continuous silence
    if (isVoiceActive.value && !isVoiceInFlight.value) {
      const finalText = liveSpokenText.value.trim() || inputQuery.value.trim()
      if (finalText) {
        await confirmVoiceInput()
      }
    }
  }, 2000)
}

const startVoiceRecording = async () => {
  if (isPlayingVoice.value) {
    stopVoicePlayback()
  }

  audioChunks.value = []
  recordedAudioBlob.value = null
  liveSpokenText.value = ''
  inputQuery.value = ''
  hasMeaningfulSpeech.value = false
  resetSilenceTimer()
  isVoiceActive.value = true
  isRecording.value = true

  // Initialize SpeechRecognition for live progressive text display on screen
  const SpeechRecognition = typeof window !== 'undefined' ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null
  if (SpeechRecognition) {
    try {
      if (speechRecognition) {
        speechRecognition.onresult = null
        speechRecognition.onerror = null
        speechRecognition.onend = null
        speechRecognition.onspeechend = null
        speechRecognition.stop()
      }
      speechRecognition = new SpeechRecognition()
      speechRecognition.continuous = true
      speechRecognition.interimResults = true
      const langMap = { en: 'en-US', ar: 'ar-AE', hi: 'hi-IN', ur: 'ur-PK' }
      speechRecognition.lang = langMap[props.currentLanguage] || 'en-US'

      speechRecognition.onresult = (event) => {
        let interim = ''
        let final = ''
        for (let i = 0; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            final += event.results[i][0].transcript
          } else {
            interim += event.results[i][0].transcript
          }
        }
        const transcript = (final + ' ' + interim).trim()
        if (transcript) {
          liveSpokenText.value = transcript
          inputQuery.value = transcript
          hasMeaningfulSpeech.value = true
          // Debounce 2 seconds of silence after words are captured
          restartSilenceTimer()
        }
      }

      speechRecognition.onspeechend = () => {
        // Native browser VAD detected speech ceased
        if (liveSpokenText.value.trim()) {
          restartSilenceTimer()
        }
      }

      speechRecognition.onend = () => {
        if (isVoiceActive.value && !isVoiceInFlight.value) {
          if (liveSpokenText.value.trim()) {
            restartSilenceTimer()
          } else if (isRecording.value) {
            try { speechRecognition.start() } catch (e) {}
          }
        }
      }

      speechRecognition.onerror = (e) => {
        console.warn('SpeechRecognition notice:', e)
      }
      speechRecognition.start()
    } catch (err) {
      console.warn('SpeechRecognition init error:', err)
    }
  }

  // Initialize MediaRecorder for audio recording & Web Audio API for 3D visualizer
  if (typeof navigator !== 'undefined' && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4'
      const recorder = new MediaRecorder(stream, { mimeType })
      mediaRecorder.value = recorder

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          audioChunks.value.push(e.data)
        }
      }

      recorder.onstop = () => {
        if (audioChunks.value.length > 0) {
          recordedAudioBlob.value = new Blob(audioChunks.value, { type: mimeType })
        }
        if (stream) {
          stream.getTracks().forEach(t => t.stop())
        }
      }

      recorder.start()

      // Connect Web Audio API Analyser exclusively for real-time 3D orb organic pulsation
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext
        if (AudioCtx) {
          if (audioContext) {
            try { audioContext.close() } catch (e) {}
          }
          audioContext = new AudioCtx()
          analyserNode = audioContext.createAnalyser()
          analyserNode.fftSize = 256
          const source = audioContext.createMediaStreamSource(stream)
          source.connect(analyserNode)

          const bufferLength = analyserNode.frequencyBinCount
          const dataArray = new Uint8Array(bufferLength)

          if (audioAnalysisInterval) clearInterval(audioAnalysisInterval)
          audioAnalysisInterval = setInterval(() => {
            if (!isRecording.value || !analyserNode) return
            analyserNode.getByteFrequencyData(dataArray)
            let sum = 0
            for (let i = 0; i < bufferLength; i++) {
              sum += dataArray[i]
            }
            const avg = sum / bufferLength
            const normalized = Math.min(avg / 65.0, 1.0)
            currentAudioLevel.value = normalized
          }, 80)
        }
      } catch (audioErr) {
        console.warn('Web Audio Analyser init notice:', audioErr)
      }
    } catch (err) {
      console.warn('Microphone permission or hardware unavailable:', err)
    }
  }
}

const stopVoiceRecording = () => {
  isRecording.value = false
  if (audioAnalysisInterval) {
    clearInterval(audioAnalysisInterval)
    audioAnalysisInterval = null
  }
  currentAudioLevel.value = 0
  if (speechRecognition) {
    try {
      speechRecognition.stop()
    } catch (e) {
      // ignore
    }
  }
  if (mediaRecorder.value && mediaRecorder.value.state === 'recording') {
    try {
      mediaRecorder.value.requestData()
    } catch (e) {
      // ignore
    }
  }
  // isVoiceActive remains true so Confirm (✓) and Cancel (✕) buttons stay accessible
}

const toggleVoiceRecording = async () => {
  // If XO is currently speaking, clicking mic interrupts audio and starts recording
  if (isPlayingVoice.value) {
    stopVoicePlayback()
    await startVoiceRecording()
    return
  }

  // If voice session has not greeted yet, greet user through voice (Requirement 1)
  if (!hasVoiceSessionGreeted.value) {
    hasVoiceSessionGreeted.value = true
    await playVoiceGreeting()
    return
  }

  if (isRecording.value) {
    stopVoiceRecording()
  } else {
    await startVoiceRecording()
  }
}

// 3. Cancel / X Action (Requirement 3)
const cancelVoiceInput = () => {
  resetSilenceTimer()
  hasMeaningfulSpeech.value = false
  if (audioAnalysisInterval) {
    clearInterval(audioAnalysisInterval)
    audioAnalysisInterval = null
  }
  if (audioContext) {
    try { audioContext.close() } catch (e) {}
    audioContext = null
    analyserNode = null
  }
  currentAudioLevel.value = 0

  if (voiceAbortController) {
    try {
      voiceAbortController.abort()
    } catch (e) {}
    voiceAbortController = null
  }

  if (speechRecognition) {
    try {
      speechRecognition.onresult = null
      speechRecognition.onerror = null
      speechRecognition.stop()
    } catch (e) {
      // ignore
    }
    speechRecognition = null
  }

  if (mediaRecorder.value && mediaRecorder.value.state !== 'inactive') {
    mediaRecorder.value.onstop = null // Discard without pipeline execution
    try {
      mediaRecorder.value.stop()
      if (mediaRecorder.value.stream) {
        mediaRecorder.value.stream.getTracks().forEach(t => t.stop())
      }
    } catch (e) {
      // ignore
    }
  }

  audioChunks.value = []
  recordedAudioBlob.value = null
  liveSpokenText.value = ''
  inputQuery.value = ''
  isRecording.value = false
  isVoiceActive.value = false
  isVoiceInFlight.value = false
  // Chatbot remains open, session context completely preserved
}

// 4. Confirm / ✓ Action (Requirement 3)
const confirmVoiceInput = async () => {
  if (isVoiceInFlight.value) return
  resetSilenceTimer()
  if (audioAnalysisInterval) {
    clearInterval(audioAnalysisInterval)
    audioAnalysisInterval = null
  }
  if (audioContext) {
    try { audioContext.close() } catch (e) {}
    audioContext = null
    analyserNode = null
  }
  currentAudioLevel.value = 0

  const capturedText = liveSpokenText.value.trim() || inputQuery.value.trim()
  if (!capturedText && audioChunks.value.length === 0 && !recordedAudioBlob.value) {
    // Empty voice interaction, cancel instead of submitting blank message
    cancelVoiceInput()
    return
  }

  if (speechRecognition) {
    try {
      speechRecognition.onresult = null
      speechRecognition.onerror = null
      speechRecognition.stop()
    } catch (e) {
      // ignore
    }
    speechRecognition = null
  }

  const mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4'

  if (mediaRecorder.value && mediaRecorder.value.state !== 'inactive') {
    const recorder = mediaRecorder.value
    recorder.onstop = async () => {
      const audioBlob = audioChunks.value.length > 0
        ? new Blob(audioChunks.value, { type: mimeType })
        : null
      if (recorder.stream) {
        recorder.stream.getTracks().forEach(t => t.stop())
      }
      await executeVoicePipeline(audioBlob, capturedText)
    }
    try {
      recorder.stop()
    } catch (e) {
      console.warn('MediaRecorder stop error:', e)
      const audioBlob = audioChunks.value.length > 0 ? new Blob(audioChunks.value, { type: mimeType }) : null
      await executeVoicePipeline(audioBlob, capturedText)
    }
  } else {
    const audioBlob = recordedAudioBlob.value || (audioChunks.value.length > 0 ? new Blob(audioChunks.value, { type: mimeType }) : null)
    await executeVoicePipeline(audioBlob, capturedText)
  }
}

const executeVoicePipeline = async (recordedBlob = null, textOverride = null) => {
  if (isVoiceInFlight.value) return
  isVoiceInFlight.value = true
  isTyping.value = true
  isVoiceActive.value = false
  isRecording.value = false

  const textToSend = textOverride || liveSpokenText.value || inputQuery.value || ''

  const controller = new AbortController()
  voiceAbortController = controller
  const timeoutId = setTimeout(() => controller.abort(), 60000) // 60s timeout for multi-turn voice pipeline

  try {
    const formData = new FormData()
    if (recordedBlob && recordedBlob.size > 200) {
      const ext = recordedBlob.type.includes('webm') ? 'webm' : 'wav'
      formData.append('audio', recordedBlob, `voice_recording.${ext}`)
    } else {
      const fakeWav = new Uint8Array([
        0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00, 0x57, 0x41, 0x56, 0x66,
        0x6d, 0x74, 0x20, 0x10, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00,
        0x44, 0xac, 0x00, 0x00, 0x88, 0x58, 0x01, 0x00, 0x02, 0x00, 0x10, 0x00,
        0x64, 0x61, 0x74, 0x61, 0x00, 0x00, 0x00, 0x00
      ])
      const audioBlob = new Blob([fakeWav], { type: 'audio/wav' })
      formData.append('audio', audioBlob, 'mic_recording.wav')
    }
    formData.append('session_id', sessionId.value)
    formData.append('language_hint', props.currentLanguage)
    if (currentUserId.value) {
      formData.append('user_id', currentUserId.value)
    }
    if (textToSend.trim()) {
      formData.append('transcribed_text', textToSend.trim())
    }

    const res = await fetch('/api/voice/interact', {
      method: 'POST',
      body: formData,
      signal: controller.signal
    })

    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}))
      throw new Error(errJson.detail || `Server error (${res.status})`)
    }

    const data = await res.json()

    messages.value.push({
      id: `usr_v_${Date.now()}`,
      role: 'user',
      content: `🎙️ ${data.transcribed_user_text}`,
      timestamp: new Date().toISOString()
    })

    messages.value.push({
      id: `ast_v_${Date.now()}`,
      role: 'assistant',
      content: data.reply_text,
      timestamp: new Date().toISOString(),
      metadata: {
        property_results: data.property_results,
        mortgage_result: data.mortgage_result,
        saved_properties: data.saved_properties,
        application_status: data.application_status,
        handoff_data: data.handoff_data
      }
    })

    if (data.audio_base64 && audioPlayerRef.value) {
      stopVoicePlayback()
      isPlayingVoice.value = true
      audioPlayerRef.value.src = data.audio_base64
      audioPlayerRef.value.play().catch(() => {
        isPlayingVoice.value = false
      })
    }
  } catch (err) {
    let errMsg = err.message
    if (err.name === 'AbortError') {
      errMsg = props.currentLanguage === 'ar' 
        ? 'انتهت مهلة معالجة الصوت، يرجى المحاولة مرة أخرى.' 
        : 'Voice request timed out. Please try again.'
    } else if (err.message && err.message.includes('Failed to fetch')) {
      errMsg = props.currentLanguage === 'ar'
        ? 'تعذر الاتصال بالخادم. يرجى التحقق من تشغيل الخادم والاتصال بالشبكة.'
        : 'Could not connect to backend server. Please verify server is running.'
    }
    messages.value.push({
      id: `err_v_${Date.now()}`,
      role: 'assistant',
      content: `Voice error: ${errMsg}`,
      timestamp: new Date().toISOString()
    })
  } finally {
    clearTimeout(timeoutId)
    voiceAbortController = null
    isVoiceInFlight.value = false
    isTyping.value = false
    liveSpokenText.value = ''
    inputQuery.value = ''
    scrollToBottom()
  }
}

onUnmounted(() => {
  stopVoicePlayback()
  if (speechRecognition) {
    try {
      speechRecognition.stop()
    } catch (e) {
      // ignore
    }
  }
})

const handlePropertyMortgageCheck = (prop) => {
  inputQuery.value = `What mortgage would I qualify for on ${prop.title} priced at ${prop.price.toLocaleString()} AED?`
  sendMessage()
}

const handleJumpToProperties = (budget) => {
  inputQuery.value = `Show me matching properties around ${Number(budget).toLocaleString()} AED`
  sendMessage()
}

const requestHandoff = () => {
  inputQuery.value = 'I would like to speak with a human agent.'
  sendMessage()
}

// Property Shortlisting & Lead Capture (FR-10)
const showLeadCaptureModal = ref(false)
const selectedShortlistProp = ref(null)
const isSubmittingLead = ref(false)
const leadForm = ref({
  name: '',
  email: '',
  phone: ''
})

const formatNumber = (num) => {
  if (!num) return '0'
  return Number(num).toLocaleString()
}

const handleShortlistProperty = async (prop) => {
  try {
    const res = await fetch(`/api/properties/${prop.id}/shortlist`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-ID': sessionId.value
      },
      body: JSON.stringify({
        user_id: null,
        session_id: sessionId.value
      })
    })

    if (!res.ok) throw new Error('Failed to update shortlist')
    const data = await res.json()

    prop.is_shortlisted = data.is_shortlisted

    if (data.is_shortlisted && data.requires_lead_capture) {
      selectedShortlistProp.value = prop
      showLeadCaptureModal.value = true
    }
  } catch (err) {
    console.error('Shortlist error:', err)
  }
}

const submitLeadCapture = async () => {
  if (!leadForm.value.name || !leadForm.value.email || !leadForm.value.phone) return
  isSubmittingLead.value = true
  try {
    const res = await fetch('/api/properties/shortlist/lead', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-ID': sessionId.value
      },
      body: JSON.stringify({
        property_id: selectedShortlistProp.value?.id,
        full_name: leadForm.value.name,
        email: leadForm.value.email,
        phone: leadForm.value.phone,
        session_id: sessionId.value
      })
    })

    if (!res.ok) throw new Error('Lead capture failed')
    const data = await res.json()

    showLeadCaptureModal.value = false
    const propTitle = selectedShortlistProp.value ? selectedShortlistProp.value.title : 'property'

    messages.value.push({
      id: `lead_${Date.now()}`,
      role: 'assistant',
      content: `✅ Thank you, **${leadForm.value.name}**! **${propTitle}** has been saved to your portfolio. An XO luxury property specialist has been assigned and will send complete floor plans, payment schedules, and DLD verification to **${leadForm.value.email}** shortly.`,
      timestamp: new Date().toISOString()
    })

    leadForm.value = { name: '', email: '', phone: '' }
    selectedShortlistProp.value = null
    scrollToBottom()
  } catch (err) {
    alert(`Could not save lead: ${err.message}`)
  } finally {
    isSubmittingLead.value = false
  }
}

onMounted(() => {
  initializeChatSession()
})

onUnmounted(() => {
  if (chatAbortController) {
    chatAbortController.abort()
    chatAbortController = null
  }
})
</script>

<style scoped>
.chat-widget-wrapper {
  display: flex;
  flex-direction: column;
  height: 580px;
  max-height: calc(100vh - 44px);
  width: 100%;
  background: var(--bg-surface);
  border: 1.5px solid var(--border-purple);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.16), 0 0 20px rgba(92, 3, 155, 0.14);
  transition: height 0.3s cubic-bezier(0.16, 1, 0.3, 1), background-color var(--transition-normal), border-color var(--transition-normal);
}

.chat-widget-wrapper.is-expanded {
  height: 720px;
  max-height: calc(100vh - 44px);
}

/* Header */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 14px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-subtle);
  position: sticky;
  top: 0;
  z-index: 30;
  flex-shrink: 0;
  transition: background-color var(--transition-normal);
}

.chat-header-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1 1 auto;
}

.mascot-avatar-container {
  position: relative;
  width: 38px;
  height: 38px;
  min-width: 38px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(92, 3, 155, 0.15) 0%, rgba(3, 164, 244, 0.10) 70%);
  border: 1.5px solid var(--brand-purple);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  box-shadow: 0 2px 8px rgba(92, 3, 155, 0.15);
  flex-shrink: 0;
}

.mascot-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  border-radius: 50%;
}

.live-status-dot {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--brand-lime-vivid);
  border: 1.5px solid var(--bg-surface);
  box-shadow: 0 0 6px var(--brand-lime-vivid);
  animation: pulseLive 2s infinite;
}

.header-brand-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

.header-brand-title {
  display: flex;
  align-items: center;
  gap: 6px;
  line-height: 1.2;
}

.header-title {
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  line-height: 1.2;
}

.badge-online {
  font-size: 0.58rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  color: #020202;
  background: var(--brand-lime-vivid);
  padding: 1.5px 6px;
  border-radius: 999px;
  box-shadow: 0 0 6px rgba(100, 239, 10, 0.3);
  line-height: 1.2;
}

.header-status {
  display: block;
  font-size: 0.69rem;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
  margin-top: 2px;
  line-height: 1.2;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.header-pills-group {
  display: flex;
  align-items: center;
  gap: 5px;
}

.header-tools-group {
  display: flex;
  align-items: center;
  gap: 3px;
  background: var(--bg-surface);
  padding: 2px 4px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-xs);
}

.icon-btn {
  background: transparent;
  border: 1px solid transparent;
  color: var(--text-secondary);
  cursor: pointer;
  width: 26px;
  height: 26px;
  font-size: 0.85rem;
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  position: relative;
}

.icon-btn:hover {
  color: var(--text-primary);
  background: var(--bg-surface-hover);
  border-color: var(--border-subtle);
  transform: translateY(-1px);
}

/* Dedicated Clear Chat button with prominent hover tooltip */
.clear-chat-btn {
  position: relative;
}

.clear-chat-btn:hover {
  background: rgba(239, 68, 68, 0.12);
  border-color: rgba(239, 68, 68, 0.35);
  color: #DC2626;
}

.clear-tooltip-bubble {
  position: absolute;
  top: calc(100% + 7px);
  right: -8px;
  background: #0F172A;
  color: #FFFFFF;
  font-family: var(--font-body);
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  padding: 4px 8px;
  border-radius: 6px;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  visibility: hidden;
  transform: translateY(-3px);
  transition: opacity 0.15s ease, transform 0.15s ease;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.32);
  border: 1px solid rgba(255, 255, 255, 0.15);
  z-index: 10002;
}

.clear-tooltip-bubble::before {
  content: '';
  position: absolute;
  bottom: 100%;
  right: 14px;
  border: 4px solid transparent;
  border-bottom-color: #0F172A;
}

.clear-chat-btn:hover .clear-tooltip-bubble,
.clear-chat-btn:focus-visible .clear-tooltip-bubble {
  opacity: 1;
  visibility: visible;
  transform: translateY(0);
}

[data-theme="dark"] .clear-tooltip-bubble {
  background: #1E293B;
  border-color: rgba(255, 255, 255, 0.20);
}

[data-theme="dark"] .clear-tooltip-bubble::before {
  border-bottom-color: #1E293B;
}

.resize-toggle-btn {
  font-size: 0.95rem;
  color: var(--brand-purple);
}

.resize-toggle-btn:hover {
  background: rgba(92, 3, 155, 0.15);
  color: var(--brand-purple);
}

[data-theme="dark"] .resize-toggle-btn {
  color: var(--brand-cyan-vivid);
}

[data-theme="dark"] .resize-toggle-btn:hover {
  background: rgba(3, 164, 244, 0.20);
  color: #FFFFFF;
}

.close-widget-btn {
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--text-muted);
}

.close-widget-btn:hover {
  background: rgba(239, 68, 68, 0.14);
  border-color: rgba(239, 68, 68, 0.40);
  color: #DC2626;
}

[data-theme="dark"] .close-widget-btn:hover {
  background: rgba(239, 68, 68, 0.25);
  border-color: rgba(239, 68, 68, 0.55);
  color: #F87171;
}

.handoff-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: rgba(92, 3, 155, 0.08);
  border: 1px solid var(--border-purple);
  color: var(--brand-purple);
  font-size: 0.70rem;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 999px;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

[data-theme="dark"] .handoff-btn {
  background: rgba(92, 3, 155, 0.25);
  color: #FFFFFF;
}

.handoff-btn:hover {
  background: var(--brand-purple);
  color: #FFFFFF;
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.auth-toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: rgba(217, 119, 6, 0.08);
  border: 1px solid rgba(217, 119, 6, 0.30);
  color: #B45309;
  font-size: 0.70rem;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 999px;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

[data-theme="dark"] .auth-toggle-btn {
  background: rgba(245, 158, 11, 0.16);
  border-color: rgba(245, 158, 11, 0.40);
  color: #FBBF24;
}

.auth-toggle-btn:hover {
  background: rgba(217, 119, 6, 0.22);
  border-color: #D97706;
  transform: translateY(-1px);
}

/* Responsive collapse for header pills on narrow widget widths */
@media (max-width: 460px) {
  .chat-header {
    padding: 8px 10px;
    gap: 6px;
  }
  .header-status {
    max-width: 110px;
  }
  .header-pills-group .pill-label {
    display: none;
  }
  .handoff-btn,
  .auth-toggle-btn {
    padding: 3px 6px;
  }
}

/* Chat Feed */
.chat-feed {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--bg-feed);
  transition: background-color var(--transition-normal);
}

/* Hero Centerpiece: Polished, human-designed greeting */
.hero-centerpiece {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 20px 16px;
  background: var(--bg-surface);
  border: 1px solid var(--border-purple);
  border-radius: var(--radius-lg);
  margin-bottom: 8px;
  box-shadow: var(--shadow-sm);
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 999px;
  background: rgba(92, 3, 155, 0.08);
  border: 1px solid var(--border-purple);
  font-size: 0.70rem;
  font-weight: 700;
  color: var(--brand-cyan);
  margin-bottom: 12px;
}

.pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand-lime-vivid);
  box-shadow: 0 0 6px var(--brand-lime-vivid);
}

.hero-mascot-visual {
  position: relative;
  width: 90px;
  height: 90px;
  margin: 0 auto 10px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(92, 3, 155, 0.15) 0%, rgba(3, 164, 244, 0.08) 70%, transparent 100%);
  display: flex;
  align-items: center;
  justify-content: center;
}

.hero-mascot-img {
  width: 82px;
  height: 82px;
  object-fit: contain;
  animation: floatMascot 4s ease-in-out infinite;
}

.hero-greeting-title {
  font-size: 1.10rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 6px;
  font-family: var(--font-heading);
}

.hero-greeting-sub {
  font-size: 0.78rem;
  color: var(--text-muted);
  margin: 0 0 6px;
  max-width: 320px;
  line-height: 1.45;
}

/* 4 Quick Suggestion Prompt Cards */
.quick-prompts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  width: 100%;
}

.prompt-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  text-align: left;
  cursor: pointer;
  transition: all var(--transition-normal);
}

.prompt-card:hover {
  background: var(--bg-surface-hover);
  border-color: var(--brand-purple);
  box-shadow: var(--shadow-sm);
  transform: translateY(-2px);
}

.prompt-icon {
  font-size: 1.25rem;
  flex-shrink: 0;
}

.prompt-text-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.prompt-text-group strong {
  font-size: 0.78rem;
  color: var(--text-primary);
  font-weight: 600;
}

.prompt-text-group span {
  font-size: 0.68rem;
  color: var(--text-muted);
  line-height: 1.25;
}

.prompt-arrow {
  color: var(--brand-purple);
  font-size: 0.85rem;
  transition: transform var(--transition-fast);
}

.prompt-card:hover .prompt-arrow {
  transform: translateX(3px);
}

/* Typing Indicator with Mascot */
.typing-indicator {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  width: fit-content;
  margin-top: 6px;
  box-shadow: var(--shadow-sm);
}

.mascot-typing-avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  overflow: hidden;
  border: 1px solid var(--brand-purple);
}

.typing-mascot-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.typing-dots-wrapper {
  display: flex;
  align-items: center;
  gap: 4px;
}

.typing-dot {
  width: 6px;
  height: 6px;
  background: var(--brand-purple);
  border-radius: 50%;
  animation: typingBounce 1.2s infinite;
}

.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }

.typing-text {
  font-size: 0.72rem;
  color: var(--text-muted);
  margin-left: 6px;
}

/* Advisor Standby Notification Bar */
.advisor-standby-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: var(--bg-surface-elevated);
  border-top: 1px solid var(--border-subtle);
  border-bottom: 1px solid var(--border-subtle);
  transition: background-color var(--transition-normal);
}

.standby-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.73rem;
  color: var(--text-secondary);
}

.standby-icon {
  font-size: 0.9rem;
}

.standby-status strong {
  color: var(--brand-lime);
}

.btn-standby-connect {
  background: rgba(92, 3, 155, 0.10);
  border: 1px solid var(--border-purple);
  color: var(--brand-purple);
  font-size: 0.70rem;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 999px;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-standby-connect:hover {
  background: var(--brand-purple);
  color: #FFFFFF;
}

/* ==========================================================================
   Dedicated Voice Mode Screen: Perplexity AI Replication
   ========================================================================== */
.pplx-voice-screen {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background: var(--bg-surface, #FFFFFF);
  position: relative;
  overflow: hidden;
  animation: fadeIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

[data-theme="dark"] .pplx-voice-screen {
  background: #111113;
}

.pplx-voice-stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  max-width: 420px;
  position: relative;
  padding: 24px 20px;
}

/* 3D Particle Sphere Orb Container */
.pplx-orb-container {
  position: absolute;
  top: 38%;
  left: 50%;
  width: 200px;
  height: 200px;
  transform: translate(-50%, -50%);
  transition: all 0.55s cubic-bezier(0.16, 1, 0.3, 1);
  z-index: 2;
  pointer-events: none;
}

/* When user starts speaking: 3D model goes down between buttons (Perplexity Style) */
.pplx-voice-screen.is-speaking .pplx-orb-container {
  top: calc(100% - 72px);
  transform: translate(-50%, -50%);
  width: 104px;
  height: 104px;
}

/* Text Zone: Prompts & Live Transcription */
.pplx-text-zone {
  position: absolute;
  top: calc(38% + 120px);
  left: 50%;
  transform: translate(-50%, 0);
  width: 88%;
  max-width: 320px;
  text-align: center;
  transition: all 0.55s cubic-bezier(0.16, 1, 0.3, 1);
  z-index: 3;
}

.pplx-prompt-text {
  font-size: 1.15rem;
  font-weight: 600;
  color: var(--brand-cyan, #0284c7);
  margin: 0;
  letter-spacing: 0.2px;
  font-family: var(--font-heading, system-ui);
}

[data-theme="dark"] .pplx-prompt-text {
  color: var(--brand-cyan-vivid, #03a4f4);
}

.pplx-transcript-text {
  font-size: 1.05rem;
  font-weight: 500;
  color: var(--text-primary, #1e293b);
  line-height: 1.45;
  font-style: italic;
  margin: 0;
  word-break: break-word;
  max-height: 100px;
  overflow-y: auto;
}

[data-theme="dark"] .pplx-transcript-text {
  color: #f1f5f9;
}

/* When speaking: Text floats cleanly in the center above the descended orb and buttons */
.pplx-voice-screen.is-speaking .pplx-text-zone {
  top: 40%;
  transform: translate(-50%, -50%);
  max-width: 340px;
}

.pplx-silence-pulse {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  padding: 4px 12px;
  border-radius: 12px;
  background: rgba(3, 164, 244, 0.08);
  border: 1px solid rgba(3, 164, 244, 0.2);
  color: var(--brand-cyan, #0284c7);
  font-size: 0.74rem;
  font-weight: 600;
  letter-spacing: 0.3px;
  animation: fadeIn 0.25s ease;
}

.pplx-silence-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand-cyan, #0284c7);
  animation: pulseRecording 1s infinite;
}

/* Action Controls Row (✕ on Left, ✓ on Right) */
.pplx-actions-row {
  position: absolute;
  bottom: 46px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 36px;
  z-index: 4;
  transition: gap 0.55s cubic-bezier(0.16, 1, 0.3, 1);
}

/* When speaking: Buttons spread apart to nestle the particle orb right in the middle */
.pplx-voice-screen.is-speaking .pplx-actions-row {
  gap: 120px;
}

/* Perplexity Minimalist Soft Circular Buttons */
.pplx-action-btn {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.05);
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
}

.pplx-btn-cancel {
  color: #374151;
  font-size: 1.15rem;
  font-weight: 700;
}

.pplx-btn-cancel:hover {
  background: rgba(0, 0, 0, 0.10);
  transform: scale(1.06);
}

.pplx-btn-confirm {
  color: #16a34a;
  font-size: 1.35rem;
  font-weight: 800;
}

.pplx-btn-confirm:hover:not(:disabled) {
  background: rgba(22, 163, 74, 0.12);
  transform: scale(1.06);
}

.pplx-btn-confirm:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  transform: none;
}

[data-theme="dark"] .pplx-action-btn {
  background: rgba(255, 255, 255, 0.10);
  color: #f4f4f5;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

[data-theme="dark"] .pplx-btn-cancel:hover {
  background: rgba(255, 255, 255, 0.18);
}

[data-theme="dark"] .pplx-btn-confirm {
  color: #4ade80;
}

[data-theme="dark"] .pplx-btn-confirm:hover:not(:disabled) {
  background: rgba(74, 222, 128, 0.20);
}

/* Compact Voice Playback Bar (when XO is speaking back audio) */
.voice-playback-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 14px;
  margin: 0 12px 6px;
  background: rgba(168, 85, 247, 0.12);
  border: 1px solid var(--border-purple, rgba(168, 85, 247, 0.3));
  border-radius: 20px;
  cursor: pointer;
  transition: all var(--transition-fast, 0.15s ease);
}

.voice-playback-bar:hover {
  background: rgba(168, 85, 247, 0.2);
}

.playback-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #22C55E;
  box-shadow: 0 0 8px #22C55E;
  animation: pulseRecording 1.4s infinite;
}

.playback-text {
  font-size: 0.74rem;
  font-weight: 600;
  color: var(--brand-purple, #9333ea);
}

[data-theme="dark"] .playback-text {
  color: #d8b4fe;
}

.btn-stop-playback {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 0.85rem;
  cursor: pointer;
  padding: 2px 4px;
}

.btn-stop-playback:hover {
  color: #EF4444;
}

/* Floating Jump to Latest Button */
.jump-to-latest-btn {
  position: absolute;
  bottom: 84px;
  right: 18px;
  z-index: 25;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: var(--bg-surface-elevated, #ffffff);
  border: 1.5px solid var(--border-purple, #5c039b);
  border-radius: 999px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15), 0 0 10px rgba(92, 3, 155, 0.20);
  color: var(--brand-purple, #5c039b);
  font-size: 0.78rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

[data-theme="dark"] .jump-to-latest-btn {
  background: rgba(26, 26, 36, 0.92);
  border-color: var(--border-cyan, #03a4f4);
  color: var(--brand-cyan, #03a4f4);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4), 0 0 12px rgba(3, 164, 244, 0.25);
}

.jump-to-latest-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(92, 3, 155, 0.35);
  background: var(--brand-purple, #5c039b);
  color: #ffffff;
}

[data-theme="dark"] .jump-to-latest-btn:hover {
  background: var(--brand-cyan, #03a4f4);
  color: #000000;
  box-shadow: 0 6px 20px rgba(3, 164, 244, 0.45);
}

.jump-arrow {
  font-size: 0.95rem;
  font-weight: 800;
  line-height: 1;
  animation: bounceDown 1.5s infinite;
}

.jump-text {
  font-size: 0.75rem;
  letter-spacing: 0.2px;
}

@keyframes bounceDown {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(2px); }
}

/* Transition */
.jump-fade-enter-active,
.jump-fade-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}

.jump-fade-enter-from,
.jump-fade-leave-to {
  opacity: 0;
  transform: translateY(10px);
}

/* Chat Input Footer Dock */
.chat-footer {
  padding: 8px 12px;
  margin: 10px 12px 6px;
  background: var(--bg-surface);
  border: 1px solid var(--border-purple);
  border-radius: 999px;
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-normal);
}

.input-form {
  display: flex;
  align-items: center;
  gap: 8px;
}

.chat-input-field {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 0.88rem;
  padding: 6px 6px;
}

.chat-input-field:focus {
  outline: none;
}

.chat-input-field::placeholder {
  color: var(--text-muted);
  font-size: 0.82rem;
}

.mic-btn {
  background: linear-gradient(135deg, rgba(2, 132, 199, 0.14), rgba(92, 3, 155, 0.10));
  border: 1.5px solid var(--brand-cyan);
  border-radius: 50%;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--transition-fast);
  color: var(--brand-cyan);
  box-shadow: 0 0 10px rgba(2, 132, 199, 0.22);
  flex-shrink: 0;
}

.mic-svg-icon {
  width: 18px;
  height: 18px;
  stroke: currentColor;
  transition: transform var(--transition-fast);
}

.mic-btn:hover {
  background: var(--brand-cyan);
  color: #FFFFFF;
  border-color: var(--brand-cyan);
  transform: scale(1.10);
  box-shadow: 0 0 16px rgba(2, 132, 199, 0.45);
}

.mic-btn:hover .mic-svg-icon {
  transform: scale(1.08);
}

[data-theme="dark"] .mic-btn {
  background: linear-gradient(135deg, rgba(3, 164, 244, 0.20), rgba(92, 3, 155, 0.25));
  border-color: var(--brand-cyan-vivid);
  color: var(--brand-cyan-vivid);
  box-shadow: 0 0 14px rgba(3, 164, 244, 0.35);
}

[data-theme="dark"] .mic-btn:hover {
  background: var(--brand-cyan-vivid);
  color: #020202;
  box-shadow: 0 0 22px rgba(3, 164, 244, 0.65);
}

.mic-btn.recording {
  background: #EF4444;
  border-color: #EF4444;
  box-shadow: 0 0 20px rgba(239, 68, 68, 0.7);
  color: #FFFFFF;
  animation: pulseRecording 1.1s infinite;
}

.mic-btn.speaking {
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.20), rgba(239, 68, 68, 0.20));
  border-color: #F59E0B;
  color: #F59E0B;
  box-shadow: 0 0 16px rgba(245, 158, 11, 0.5);
  animation: pulseSpeaking 1.4s infinite;
}

@keyframes pulseSpeaking {
  0% { transform: scale(1); box-shadow: 0 0 10px rgba(245, 158, 11, 0.4); }
  50% { transform: scale(1.08); box-shadow: 0 0 20px rgba(245, 158, 11, 0.7); }
  100% { transform: scale(1); box-shadow: 0 0 10px rgba(245, 158, 11, 0.4); }
}

.rec-stop-box {
  font-size: 0.95rem;
  line-height: 1;
  color: #FFFFFF;
}

/* Send Button: Solid brand purple circle with upward arrow */
.send-btn {
  background: var(--brand-purple);
  color: #FFFFFF;
  border: none;
  border-radius: 50%;
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-weight: 800;
  transition: all var(--transition-fast);
  box-shadow: var(--shadow-sm);
}

.send-arrow {
  font-size: 1.10rem;
  line-height: 1;
  font-weight: 900;
}

.send-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  box-shadow: none;
}

.send-btn:not(:disabled):hover {
  background: var(--brand-purple-light);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

/* Disclaimer text under input */
.input-disclaimer {
  padding: 0 16px 10px;
  text-align: center;
  font-size: 0.65rem;
  color: var(--text-muted);
  line-height: 1.35;
}

/* Shortlist Lead Capture Modal */
.lead-modal-overlay {
  position: absolute;
  inset: 0;
  background: rgba(15, 23, 42, 0.65);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 16px;
  animation: fadeIn 200ms ease;
}

.lead-modal-card {
  width: 100%;
  max-width: 380px;
  background: var(--bg-surface);
  border: 1px solid var(--border-purple);
  border-radius: var(--radius-lg);
  padding: 20px;
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
  gap: 14px;
  animation: scaleIn 250ms cubic-bezier(0.16, 1, 0.3, 1);
}

.lead-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.lead-modal-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.modal-mascot-icon {
  width: 36px;
  height: 36px;
  object-fit: cover;
  border-radius: 50%;
  border: 1.5px solid var(--brand-purple);
}

.lead-modal-title h4 {
  margin: 0;
  font-size: 0.92rem;
  font-weight: 700;
  color: var(--text-primary);
}

.modal-sub {
  font-size: 0.7rem;
  color: var(--brand-cyan);
}

.lead-modal-close {
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: 1rem;
  cursor: pointer;
  padding: 4px;
  line-height: 1;
  transition: color var(--transition-fast);
}

.lead-modal-close:hover {
  color: var(--text-primary);
}

.lead-modal-subtitle {
  margin: 0;
  font-size: 0.77rem;
  line-height: 1.45;
  color: var(--text-secondary);
}

.lead-modal-subtitle strong {
  color: var(--brand-purple);
}

[data-theme="dark"] .lead-modal-subtitle strong {
  color: var(--brand-lime-vivid);
}

.lead-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-group label {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.lead-input {
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-prominent);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  color: var(--text-primary);
  font-size: 0.82rem;
  transition: all var(--transition-fast);
}

.lead-input:focus {
  outline: none;
  border-color: var(--brand-purple);
  box-shadow: 0 0 0 3px var(--brand-purple-glow);
}

.lead-modal-actions {
  display: flex;
  gap: 10px;
  margin-top: 6px;
}

.btn-cancel {
  flex: 1;
  background: transparent;
  border: 1px solid var(--border-prominent);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  padding: 8px 12px;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-cancel:hover {
  background: var(--bg-surface-hover);
  color: var(--text-primary);
}

.btn-submit {
  flex: 1.5;
  background: var(--brand-purple);
  border: none;
  border-radius: var(--radius-sm);
  color: #FFFFFF;
  padding: 8px 12px;
  font-size: 0.8rem;
  font-weight: 700;
  cursor: pointer;
  transition: all var(--transition-fast);
  box-shadow: var(--shadow-sm);
}

.btn-submit:hover:not(:disabled) {
  background: var(--brand-purple-light);
  transform: translateY(-1px);
}

.btn-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Animations */
@keyframes floatMascot {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-5px); }
}

@keyframes pulseLive {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.85); }
}

@keyframes pulseRecording {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.9); }
}

@keyframes typingBounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-4px); }
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes scaleIn {
  from { opacity: 0; transform: scale(0.96); }
  to { opacity: 1; transform: scale(1); }
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  border: 0;
}

@media (max-width: 480px) {
  .quick-prompts-grid {
    grid-template-columns: 1fr;
  }
}
</style>
