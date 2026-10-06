<template>
  <div class="chat-widget-wrapper glass-panel" :class="{ 'is-expanded': isExpanded }" role="region" aria-label="XO Conversational Assistant">
    <!-- Chat Header with XO Mascot Avatar -->
    <div class="chat-header">
      <div class="chat-header-brand">
        <div class="mascot-avatar-container">
          <img src="/xo-mascot.png" alt="XO Mascot" class="mascot-avatar-img" />
          <span class="live-status-dot"></span>
        </div>
        <div>
          <div class="header-brand-title">
            <h3 class="header-title">XO Realty AI</h3>
            <span class="badge-online">ONLINE &amp; READY</span>
          </div>
          <span class="header-status">
            {{ activeLanguageLabel }} &bull; Luxury Property &amp; Mortgage Specialist
          </span>
        </div>
      </div>

      <div class="header-actions">
        <!-- Theme Toggle (Light / Dark) -->
        <button 
          class="icon-btn theme-toggle-btn"
          @click="toggleTheme" 
          :title="currentTheme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'"
          :aria-label="currentTheme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'"
          :data-tooltip="currentTheme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'"
          data-tooltip-pos="bottom"
        >
          <span>{{ currentTheme === 'light' ? '🌙' : '☀️' }}</span>
        </button>

        <!-- Feature Tips Toggle -->
        <button 
          class="icon-btn" 
          @click="showTips = !showTips" 
          title="Toggle Feature Tips (💡)"
          aria-label="Toggle Feature Tips"
          data-tooltip="Feature Tips & Guide"
          data-tooltip-pos="bottom"
        >
          💡
        </button>

        <!-- Resize / Preview Size Toggle (Arrow button) -->
        <button 
          class="icon-btn resize-toggle-btn" 
          @click="$emit('toggle-expand')" 
          :title="isExpanded ? 'Restore compact preview (⤡)' : 'Expand to larger preview (⤢)'"
          :aria-label="isExpanded ? 'Restore compact preview' : 'Expand preview'"
          :data-tooltip="isExpanded ? 'Restore compact view' : 'Expand to larger view'"
          data-tooltip-pos="bottom"
        >
          <span class="resize-icon">{{ isExpanded ? '⤡' : '⤢' }}</span>
        </button>

        <!-- Persistent Human Handoff (FR-5) -->
        <button 
          class="handoff-btn" 
          @click="requestHandoff" 
          title="Connect with Human Specialist"
          aria-label="Connect with Human Specialist"
          data-tooltip="Connect with Human Specialist"
          data-tooltip-pos="bottom"
        >
          <span>🎧 Advisor</span>
        </button>

        <!-- Close Chatbot Button (✕) -->
        <button 
          class="icon-btn close-widget-btn" 
          @click="$emit('close')" 
          title="Close Chatbot & return to page (✕)"
          aria-label="Close Chatbot"
          data-tooltip="Close Chatbot"
          data-tooltip-pos="left"
        >
          ✕
        </button>
      </div>
    </div>

    <!-- Onboarding Feature Tips (Prompt Section 6) -->
    <OnboardingTooltips 
      :is-open="showTips" 
      @close="showTips = false" 
    />

    <!-- Message Feed -->
    <div class="chat-feed" ref="feedRef" role="log" aria-live="polite">
      
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
          How can I assist your Dubai investment journey today?
        </h3>
        <p class="hero-greeting-sub">
          Choose a quick action below or speak naturally in English, Arabic, Hindi, or Urdu.
        </p>

        <!-- 4 Quick Suggestion Prompt Cards -->
        <div class="quick-prompts-grid">
          <button 
            type="button" 
            class="prompt-card"
            @click="sendQuickPrompt('Find a 3-bed penthouse in Downtown or Palm under 5M AED')"
            title="Search luxury penthouses in Downtown & Palm (<5M AED)"
            data-tooltip="Search penthouses in Downtown & Palm"
            data-tooltip-pos="bottom"
          >
            <span class="prompt-icon">🏢</span>
            <div class="prompt-text-group">
              <strong>Luxury Penthouses</strong>
              <span>3-bed in Downtown or Palm &lt; 5M AED</span>
            </div>
            <span class="prompt-arrow">→</span>
          </button>

          <button 
            type="button" 
            class="prompt-card"
            @click="sendQuickPrompt('Check what I can afford with AED 350k down and AED 30k salary')"
            title="Calculate maximum mortgage borrowing capacity"
            data-tooltip="Calculate mortgage affordability"
            data-tooltip-pos="bottom"
          >
            <span class="prompt-icon">🧮</span>
            <div class="prompt-text-group">
              <strong>Mortgage Affordability</strong>
              <span>AED 350k down &amp; AED 30k salary</span>
            </div>
            <span class="prompt-arrow">→</span>
          </button>

          <button 
            type="button" 
            class="prompt-card"
            @click="sendQuickPrompt('Compare rental yields and high-ROI investment assets in Business Bay')"
            title="Analyze rental yields and ROI across Dubai districts"
            data-tooltip="Analyze rental yields & ROI"
            data-tooltip-pos="bottom"
          >
            <span class="prompt-icon">📈</span>
            <div class="prompt-text-group">
              <strong>High-ROI Assets</strong>
              <span>Rental yields in Business Bay &amp; Marina</span>
            </div>
            <span class="prompt-arrow">→</span>
          </button>

          <button 
            type="button" 
            class="prompt-card"
            @click="sendQuickPrompt('I would like to speak with a licensed luxury property & mortgage advisor.')"
            title="Request human broker & mortgage advisor handoff"
            data-tooltip="Request licensed advisor handoff"
            data-tooltip-pos="bottom"
          >
            <span class="prompt-icon">🤝</span>
            <div class="prompt-text-group">
              <strong>Speak with Advisor</strong>
              <span>Licensed broker &amp; mortgage specialist</span>
            </div>
            <span class="prompt-arrow">→</span>
          </button>
        </div>
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

      <!-- Voice Visualizer during Recording or Playing -->
      <VoiceVisualizer 
        :is-active="isRecording" 
        label="Listening (Speak in English, Arabic, Hindi, or Urdu)..." 
      />
      <VoiceVisualizer 
        :is-active="isPlayingVoice" 
        label="Speaking (XO Audio Stream) • Click mic to interrupt" 
        @click="stopVoicePlayback"
        style="cursor: pointer;"
        title="Click to interrupt voice playback"
      />
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
          :disabled="isTyping || isRecording"
          autocomplete="off"
        />

        <!-- Microphone Button (Composed V2V Voice Interaction) -->
        <button 
          type="button" 
          class="mic-btn" 
          :class="{ 'recording': isRecording, 'speaking': isPlayingVoice }"
          @click="toggleVoiceRecording"
          :title="isRecording ? 'Stop Recording' : (isPlayingVoice ? 'Interrupt XO & Speak' : 'Hold/Tap to Speak (Voice STT in EN, AR, HI, UR)')"
          aria-label="Microphone Voice Input"
          :data-tooltip="isRecording ? 'Click to Stop Recording' : (isPlayingVoice ? 'Click to Interrupt & Speak' : 'Voice Input: Tap to Speak')"
          data-tooltip-pos="left"
        >
          <svg v-if="!isRecording" class="mic-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path>
            <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
            <line x1="12" y1="19" x2="12" y2="22"></line>
          </svg>
          <span v-else class="rec-stop-box">■</span>
        </button>

        <!-- Send Button: Purple circle with upward arrow -->
        <button 
          type="submit" 
          class="send-btn" 
          :disabled="!inputQuery.trim() || isTyping || isRecording"
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
import { ref, computed, onMounted, onUnmounted, nextTick, toRefs } from 'vue'
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

const messages = ref([])
const inputQuery = ref('')
const isTyping = ref(false)
const isRecording = ref(false)
const isPlayingVoice = ref(false)
const showTips = ref(false)
const sessionId = ref(`sess_${Math.random().toString(36).substring(2, 10)}`)

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

const scrollToBottom = async () => {
  await nextTick()
  if (feedRef.value) {
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
  scrollToBottom()

  try {
    const res = await fetch('/api/chat/message', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-ID': sessionId.value
      },
      body: JSON.stringify({
        message: query,
        session_id: sessionId.value,
        language: props.currentLanguage
      })
    })

    if (!res.ok) {
      const errData = await res.json()
      throw new Error(errData.detail || 'Failed to process message')
    }

    const data = await res.json()

    // If server detected a different language, notify parent
    if (data.language && data.language !== props.currentLanguage) {
      emit('language-changed', data.language)
    }

    messages.value.push({
      id: `ast_${Date.now()}`,
      role: 'assistant',
      content: data.text,
      timestamp: new Date().toISOString(),
      language: data.language,
      metadata: {
        property_results: data.property_results,
        mortgage_result: data.mortgage_result
      }
    })
  } catch (err) {
    messages.value.push({
      id: `err_${Date.now()}`,
      role: 'assistant',
      content: `Notice: ${err.message}`,
      timestamp: new Date().toISOString()
    })
  } finally {
    isTyping.value = false
    scrollToBottom()
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

const startVoiceRecording = async () => {
  if (isPlayingVoice.value) {
    stopVoicePlayback()
  }

  audioChunks.value = []
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

      recorder.onstop = async () => {
        const audioBlob = new Blob(audioChunks.value, { type: mimeType })
        stream.getTracks().forEach(t => t.stop())
        await executeVoicePipeline(audioBlob)
      }

      recorder.start()
      isRecording.value = true
    } catch (err) {
      console.warn('Microphone permission or hardware unavailable:', err)
      isRecording.value = true
    }
  } else {
    isRecording.value = true
  }
}

const stopVoiceRecording = async () => {
  isRecording.value = false
  if (mediaRecorder.value && mediaRecorder.value.state !== 'inactive') {
    mediaRecorder.value.stop()
  } else {
    await executeVoicePipeline(null)
  }
}

const toggleVoiceRecording = async () => {
  // If XO is currently speaking, clicking the voice button immediately interrupts audio
  // and starts recording the new user speech request without restarting the session!
  if (isPlayingVoice.value) {
    stopVoicePlayback()
    await startVoiceRecording()
    return
  }

  if (isRecording.value) {
    await stopVoiceRecording()
  } else {
    await startVoiceRecording()
  }
}

const executeVoicePipeline = async (recordedBlob = null) => {
  isTyping.value = true
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

    const res = await fetch('/api/voice/interact', {
      method: 'POST',
      body: formData
    })

    if (!res.ok) throw new Error('Voice pipeline failed')

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
        mortgage_result: data.mortgage_result
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
    messages.value.push({
      id: `err_v_${Date.now()}`,
      role: 'assistant',
      content: `Voice error: ${err.message}`,
      timestamp: new Date().toISOString()
    })
  } finally {
    isTyping.value = false
    scrollToBottom()
  }
}

onUnmounted(() => {
  stopVoicePlayback()
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
  initializeWelcomeMessage()
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
  gap: 12px;
}

.mascot-avatar-container {
  position: relative;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(92, 3, 155, 0.15) 0%, rgba(3, 164, 244, 0.10) 70%);
  border: 1.5px solid var(--brand-purple);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  box-shadow: var(--shadow-sm);
}

.mascot-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 50%;
}

.live-status-dot {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--brand-lime-vivid);
  border: 2px solid var(--bg-surface);
  box-shadow: 0 0 6px var(--brand-lime-vivid);
  animation: pulseLive 2s infinite;
}

.header-brand-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-title {
  font-size: 0.96rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.badge-online {
  font-size: 0.62rem;
  font-weight: 800;
  letter-spacing: 0.05em;
  color: #020202;
  background: var(--brand-lime-vivid);
  padding: 2px 7px;
  border-radius: 999px;
  box-shadow: 0 0 8px rgba(100, 239, 10, 0.3);
}

.header-status {
  display: block;
  font-size: 0.72rem;
  color: var(--text-muted);
  margin-top: 1px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.icon-btn {
  background: transparent;
  border: 1px solid transparent;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 5px 7px;
  font-size: 0.95rem;
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
  display: flex;
  align-items: center;
  justify-content: center;
}

.icon-btn:hover {
  color: var(--text-primary);
  background: var(--bg-surface-hover);
  border-color: var(--border-subtle);
}

.resize-toggle-btn {
  font-size: 1.05rem;
  color: var(--brand-purple);
  background: rgba(92, 3, 155, 0.08);
  border-color: var(--border-purple);
}

.resize-toggle-btn:hover {
  background: rgba(92, 3, 155, 0.18);
  color: var(--brand-purple);
  transform: scale(1.05);
}

[data-theme="dark"] .resize-toggle-btn {
  color: var(--brand-cyan-vivid);
  background: rgba(3, 164, 244, 0.12);
  border-color: rgba(3, 164, 244, 0.35);
}

[data-theme="dark"] .resize-toggle-btn:hover {
  background: rgba(3, 164, 244, 0.25);
  color: #FFFFFF;
}

.close-widget-btn {
  font-size: 0.95rem;
  font-weight: 800;
  color: var(--text-muted);
  background: rgba(0, 0, 0, 0.04);
  border-color: var(--border-subtle);
}

.close-widget-btn:hover {
  background: rgba(239, 68, 68, 0.14);
  border-color: rgba(239, 68, 68, 0.40);
  color: #DC2626;
  transform: scale(1.05);
}

[data-theme="dark"] .close-widget-btn {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.12);
  color: var(--text-muted);
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
  background: rgba(92, 3, 155, 0.10);
  border: 1px solid var(--border-purple);
  color: var(--brand-purple);
  font-size: 0.74rem;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 999px;
  cursor: pointer;
  transition: all var(--transition-fast);
}

[data-theme="dark"] .handoff-btn {
  background: rgba(92, 3, 155, 0.25);
  color: #FFFFFF;
}

.handoff-btn:hover {
  background: var(--brand-purple);
  color: #FFFFFF;
  box-shadow: var(--shadow-sm);
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
  margin: 0 0 16px;
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
