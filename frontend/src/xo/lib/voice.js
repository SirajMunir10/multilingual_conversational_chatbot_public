import { wsUrl } from './api'

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

// The longest stretch of audio kept between a sent question and the listening that follows it.
const CARRY_MAX_MS = 15000

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
 * Framework-free core; the React hook (hooks/useVoice.js) mirrors its state for rendering.
 *
 * Mobile-safe lifecycle:
 *  - prepare() must be called synchronously inside the user's tap: it creates and resumes the
 *    AudioContext (Android/iOS keep contexts created outside a gesture suspended).
 *  - open() asks for the microphone once and keeps it for the whole voice session.
 *  - listen() runs one turn and resolves with the final transcript after silence (or commit()).
 *    The audio heard after a turn is sent is kept, so listen({ resume: true }) straight afterwards loses no words
 *    (used to hear the visitor add to a question while XO is still thinking).
 *  - close() releases the microphone and audio engine.
 *
 * `onChange(state)` receives { liveText, listening, silenceCountdown } whenever one of them changes.
 * The microphone level changes on every audio frame, so it is kept in `state.level` and read by the
 * voice orb on each animation frame instead of re-rendering the widget.
 */
export function createVoice(onChange = () => {}) {
  const state = { liveText: '', level: 0, listening: false, silenceCountdown: false }
  const set = (patch) => {
    let changed = false
    for (const [k, v] of Object.entries(patch)) {
      if (state[k] !== v) { state[k] = v; changed = true }
    }
    if (changed) onChange({ liveText: state.liveText, listening: state.listening, silenceCountdown: state.silenceCountdown })
  }

  let ctx = null
  let stream = null
  let source = null
  let node = null
  let frameHandler = null

  let ws = null
  let resolveFn = null
  let rejectFn = null
  let committed = false
  let commitQueued = false // "send" arrived before the transcription service was ready
  let ready = false
  let pending = []
  let finalTimer = null
  let lastDelta = 0
  const gate = { floor: 0, speech: 0 } // the latest listening levels
  // Audio heard after commit(), with the listening levels reached so far, for a listen({ resume: true }) that follows.
  let carry = []
  let carryMs = 0
  let calibration = null
  const keep = (frame) => {
    if (carryMs > CARRY_MAX_MS) return
    carry.push({ frame, at: performance.now() })
    carryMs += (frame.length / ctx.sampleRate) * 1000
  }
  const dropCarry = () => { carry = []; carryMs = 0; calibration = null }

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
    set({ listening: false, silenceCountdown: false, level: 0 })
    if (frameHandler !== keep) frameHandler = null
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
    dropCarry()
    endTurn()
    done && done(new Error(code))
  }

  function sendCommit() {
    try { ws.send(JSON.stringify({ type: 'commit' })) } catch (e) {}
  }

  function commit() {
    if (committed || !ws) return
    committed = true
    set({ silenceCountdown: false, listening: false })
    dropCarry()
    calibration = { ...gate }
    frameHandler = keep
    if (ready && ws.readyState === 1) sendCommit()
    else commitQueued = true // sent with the buffered audio as soon as the service is ready
    finalTimer = setTimeout(() => finish(state.liveText), ready ? 6000 : 10000)
  }

  function cancel() {
    const done = resolveFn
    resolveFn = rejectFn = null
    dropCarry()
    frameHandler = null
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

  // End of speech is found from the voice itself (fast), with transcript activity as the fallback for very quiet
  // microphones. Background sound is tracked all the time, so a visitor who talks straight away is still heard.
  // onText(text) receives the transcript so far each time it grows; onSpeech() is called once the visitor has clearly
  // been talking for speechMs, which comes well before their words are transcribed.
  function listen({ language, sessionId, sampleRate = 24000, silenceMs = 1000, maxSec = 120, noSpeechMs = 15000,
                    resume = false, onText, onSpeech, speechMs = 500 }) {
    if (resolveFn) cancel()
    const replay = resume ? carry : []
    const levels = resume ? calibration : null
    dropCarry()
    if (frameHandler === keep) frameHandler = null
    set({ liveText: '' })
    committed = false
    commitQueued = false
    ready = false
    pending = []
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
      // A socket that has just closed can still report events; only this turn's own socket counts.
      const sock = ws

      const started = replay.length ? replay[0].at : performance.now()
      let readyAt = 0
      sock.onmessage = (ev) => {
        if (sock !== ws) return
        const msg = JSON.parse(ev.data)
        if (msg.type === 'ready') {
          ready = true
          readyAt = performance.now()
          pending.splice(0).forEach(b => ws.send(b))
          if (commitQueued) sendCommit()
        } else if (msg.type === 'delta') {
          set({ liveText: state.liveText + msg.text })
          lastDelta = performance.now()
          onText && onText(state.liveText)
        } else if (msg.type === 'final') {
          finish(msg.text || state.liveText)
        } else if (msg.type === 'error') {
          fail(msg.code === 'session_too_long' ? 'too_long' : 'voice_unavailable')
        }
      }
      sock.onerror = () => { if (sock === ws) fail('voice_unavailable') }
      sock.onclose = () => { if (sock === ws && resolveFn) (committed ? finish(state.liveText) : fail('voice_unavailable')) }

      let floor = levels ? levels.floor : 0.004 // background level: follows quiet moments quickly, loud ones slowly
      let speech = levels ? levels.speech : 0   // the visitor's own speaking level, once they have talked a little
      let voicedMs = 0
      let saidSpeech = false
      let lastVoice = 0
      let openUntil = 0       // the gate stays open briefly after speech so word endings are kept
      let lastFrame = started
      let batch = []
      let batchLen = 0
      const batchTarget = Math.round(sampleRate / 10) // ~100 ms per frame sent

      set({ listening: true })
      frameHandler = (frame, at) => {
        if (committed) return
        let sum = 0
        for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i]
        const rms = Math.sqrt(sum / frame.length)
        const now = at || performance.now()
        const dt = Math.min(now - lastFrame, 250)
        lastFrame = now

        const towards = (from, to, tauMs) => from + (to - from) * (1 - Math.exp(-dt / tauMs))
        floor = Math.max(rms < floor ? towards(floor, rms, 300) : towards(floor, rms, 4000), 0.0015)
        // Voices clearly quieter than the visitor's own (a TV, people nearby) do not count as speech.
        const threshold = Math.max(floor * 3, 0.006, voicedMs > 300 || (levels && levels.speech) ? speech * 0.25 : 0)
        const voiced = rms > threshold
        if (voiced) {
          voicedMs += dt
          lastVoice = now
          openUntil = now + 250
          speech = speech ? towards(speech, rms, 1500) : rms
          if (!saidSpeech && voicedMs >= speechMs) {
            saidSpeech = true
            onSpeech && onSpeech()
          }
        }
        gate.floor = floor
        gate.speech = speech
        state.level = Math.min(rms / 0.06, 1)

        let pcm = downsample(frame, ctx.sampleRate, sampleRate)
        // Outside speech the sound is turned down (not muted), so background talk is not transcribed as the visitor.
        // Skipped for very quiet microphones, where only the transcript shows that someone is talking.
        if (now > openUntil && !(lastDelta && !voicedMs)) pcm = pcm.map(v => v * 0.2)
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

        const heard = lastDelta > 0 || voicedMs >= 600
        if (voicedMs >= 250 && lastVoice) {
          const quiet = now - lastVoice
          set({ silenceCountdown: heard && quiet > silenceMs * 0.4 })
          // A short sound with no words yet waits a little longer for the transcript before sending.
          if (quiet > (heard ? silenceMs : silenceMs + 1200)) commit()
        } else if (lastDelta) {
          const quiet = now - lastDelta
          set({ silenceCountdown: quiet > silenceMs * 0.6 })
          if (quiet > silenceMs + 700) commit()
        } else if ((readyAt && now - readyAt > noSpeechMs) || now - started > noSpeechMs + 10000) {
          finish('')
        }
        if ((now - started) / 1000 > maxSec) commit()
      }
      replay.forEach(({ frame, at }) => frameHandler && frameHandler(frame, at))
    })
  }

  return { state, prepare, open, listen, commit, cancel, close }
}
