import { ref } from 'vue'
import { wsUrl } from '../services/api'

// AudioWorklet that forwards raw microphone frames to the main thread.
const WORKLET_SOURCE = `
class Capture extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0]
    if (ch) this.port.postMessage(ch.slice(0))
    return true
  }
}
registerProcessor('xo-capture', Capture)
`

function downsample(float32, fromRate, toRate) {
  if (fromRate === toRate) return float32
  const ratio = fromRate / toRate
  const out = new Float32Array(Math.floor(float32.length / ratio))
  for (let i = 0; i < out.length; i++) {
    const pos = i * ratio
    const i0 = Math.floor(pos)
    const i1 = Math.min(i0 + 1, float32.length - 1)
    out[i] = float32[i0] + (float32[i1] - float32[i0]) * (pos - i0)
  }
  return out
}

function toPcm16(float32) {
  const buf = new Int16Array(float32.length)
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]))
    buf[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return buf.buffer
}

/**
 * Live speech-to-text with gpt-live-transcribe through the backend relay.
 *
 * Mobile-safe lifecycle:
 *  - prepare() must be called synchronously inside the user's tap: it creates and resumes the
 *    AudioContext (Android/iOS keep contexts created outside a gesture suspended).
 *  - open() asks for the microphone once and keeps it for the whole voice session.
 *  - listen() runs one turn and resolves with the final transcript after silence (or commit()).
 *  - close() releases the microphone and audio engine.
 */
export function useVoice() {
  const liveText = ref('')
  const level = ref(0)
  const listening = ref(false)
  const silenceCountdown = ref(false)

  let ctx = null
  let stream = null
  let source = null
  let node = null
  let frameHandler = null

  let ws = null
  let resolveFn = null
  let rejectFn = null
  let committed = false
  let finalTimer = null
  let lastDelta = 0

  function prepare() {
    if (!ctx) {
      const Ctx = window.AudioContext || window.webkitAudioContext
      ctx = new Ctx()
    }
    if (ctx.state === 'suspended') ctx.resume().catch(() => {})
  }

  async function open() {
    prepare()
    if (stream) return
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } })
    } catch (e) {
      throw new Error(e && (e.name === 'NotAllowedError' || e.name === 'SecurityError') ? 'mic_denied' : 'mic_unavailable')
    }
    source = ctx.createMediaStreamSource(stream)
    let workletReady = false
    if (ctx.audioWorklet && window.AudioWorkletNode) {
      try {
        const url = URL.createObjectURL(new Blob([WORKLET_SOURCE], { type: 'application/javascript' }))
        await ctx.audioWorklet.addModule(url)
        node = new AudioWorkletNode(ctx, 'xo-capture')
        node.port.onmessage = (e) => frameHandler && frameHandler(e.data)
        workletReady = true
      } catch (e) {
        workletReady = false
      }
    }
    if (!workletReady) {
      // Fallback for browsers without AudioWorklet (older Android WebViews / Samsung Internet).
      node = ctx.createScriptProcessor(4096, 1, 1)
      node.onaudioprocess = (e) => frameHandler && frameHandler(new Float32Array(e.inputBuffer.getChannelData(0)))
    }
    // Route through a silent gain to the output so every browser keeps pulling microphone frames.
    const mute = ctx.createGain()
    mute.gain.value = 0
    node.connect(mute)
    mute.connect(ctx.destination)
    source.connect(node)
    if (ctx.state === 'suspended') await ctx.resume().catch(() => {})
  }

  function endTurn() {
    listening.value = false
    silenceCountdown.value = false
    level.value = 0
    frameHandler = null
    clearTimeout(finalTimer)
    try { ws && ws.readyState <= 1 && ws.close() } catch (e) {}
    ws = null
  }

  function finish(text) {
    const done = resolveFn
    resolveFn = rejectFn = null
    endTurn()
    done && done((text || '').trim())
  }

  function fail(code) {
    const done = rejectFn
    resolveFn = rejectFn = null
    endTurn()
    done && done(new Error(code))
  }

  function commit() {
    if (committed || !ws) return
    committed = true
    silenceCountdown.value = false
    listening.value = false
    frameHandler = null
    try { ws.send(JSON.stringify({ type: 'commit' })) } catch (e) {}
    finalTimer = setTimeout(() => finish(liveText.value), 6000)
  }

  function cancel() {
    const done = resolveFn
    resolveFn = rejectFn = null
    endTurn()
    done && done('')
  }

  function close() {
    cancel()
    try { node && node.disconnect() } catch (e) {}
    try { source && source.disconnect() } catch (e) {}
    try { stream && stream.getTracks().forEach(t => t.stop()) } catch (e) {}
    try { ctx && ctx.close() } catch (e) {}
    node = source = stream = ctx = null
  }

  function listen({ language, sessionId, sampleRate = 24000, silenceMs = 2000, maxSec = 120, noSpeechMs = 15000 }) {
    liveText.value = ''
    committed = false
    lastDelta = 0
    return new Promise((resolve, reject) => {
      resolveFn = resolve
      rejectFn = reject
      if (!ctx || !stream) return fail('mic_unavailable')
      if (ctx.state === 'suspended') ctx.resume().catch(() => {})

      try {
        const params = new URLSearchParams({ language: language || '' })
        if (sessionId) params.set('session_id', sessionId)
        ws = new WebSocket(wsUrl(`/api/voice/stt?${params.toString()}`))
        ws.binaryType = 'arraybuffer'
      } catch (e) {
        return fail('voice_unavailable')
      }

      const pending = []
      let ready = false
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data)
        if (msg.type === 'ready') {
          ready = true
          pending.splice(0).forEach(b => ws.send(b))
        } else if (msg.type === 'delta') {
          liveText.value += msg.text
          lastDelta = performance.now()
        } else if (msg.type === 'final') {
          finish(msg.text || liveText.value)
        } else if (msg.type === 'error') {
          fail(msg.code === 'session_too_long' ? 'too_long' : 'voice_unavailable')
        }
      }
      ws.onerror = () => fail('voice_unavailable')
      ws.onclose = () => { if (resolveFn) (committed ? finish(liveText.value) : fail('voice_unavailable')) }

      const started = performance.now()
      let noiseFloor = 0.01
      let calibrated = false
      let lastVoice = 0
      let batch = []
      let batchLen = 0
      const batchTarget = Math.round(sampleRate / 10) // ~100 ms per frame sent

      listening.value = true
      frameHandler = (frame) => {
        if (committed) return
        let sum = 0
        for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i]
        const rms = Math.sqrt(sum / frame.length)
        const now = performance.now()
        if (!calibrated) {
          noiseFloor = Math.max(noiseFloor * 0.9 + rms * 0.1, 0.002)
          if (now - started > 400) calibrated = true
        }
        level.value = Math.min(rms / 0.06, 1)
        if (calibrated && rms > Math.max(noiseFloor * 2.5, 0.008)) lastVoice = now

        const pcm = downsample(frame, ctx.sampleRate, sampleRate)
        batch.push(pcm)
        batchLen += pcm.length
        if (batchLen >= batchTarget) {
          const merged = new Float32Array(batchLen)
          let off = 0
          batch.forEach(b => { merged.set(b, off); off += b.length })
          batch = []
          batchLen = 0
          const bytes = toPcm16(merged)
          if (ready && ws && ws.readyState === 1) ws.send(bytes)
          else pending.push(bytes)
        }

        // Speech is detected from transcript activity (works on quiet phone mics) and from loudness.
        const heardSpeech = lastDelta > 0
        if (heardSpeech) {
          const activity = Math.max(lastDelta, lastVoice)
          silenceCountdown.value = now - activity > silenceMs * 0.4
          if (now - activity > silenceMs || now - lastDelta > silenceMs + 2500) commit()
        } else if (now - started > noSpeechMs) {
          finish('')
        }
        if ((now - started) / 1000 > maxSec) commit()
      }
    })
  }

  return { liveText, level, listening, silenceCountdown, prepare, open, listen, commit, cancel, close }
}
