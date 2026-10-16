import { apiUrl } from '../services/api'
import { CJK } from './useWordHighlight'

// Sentence boundaries for the supported languages (Latin, Arabic/Urdu, Devanagari, CJK).
const SENTENCE_END = /[.!?؟।。！？۔](?=\s|$)|\n/g
// The first piece is kept short so XO starts talking quickly; later pieces are larger
// (fewer TTS requests, more natural prosody).
const FIRST_MIN = 24
const CHUNK_MIN = 160
const CHUNK_MAX = 320
// Progressive playback (starts while the MP3 is still downloading) where Media Source Extensions
// support MP3: Chrome, Android, Edge, desktop Safari. Elsewhere (e.g. iPhone, Firefox) each piece
// is downloaded first, then played.
const STREAMING = typeof window !== 'undefined' && !!window.MediaSource && MediaSource.isTypeSupported('audio/mpeg')

function base64ToBytes(b64) {
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out
}

/** Reads the NDJSON stream from /api/voice/speak-timed, calling onChunk({ audio, chars, start }). */
async function readTimed(res, onChunk, isCurrent) {
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (!isCurrent()) { reader.cancel().catch(() => {}); return false }
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) if (line.trim()) await onChunk(JSON.parse(line))
  }
  if (buffer.trim()) await onChunk(JSON.parse(buffer))
  return true
}

/** Groups character timings into words: [{ text, start }]. */
function wordTimeline() {
  const words = []
  let current = null
  return {
    words,
    add(chars, starts) {
      for (let i = 0; i < chars.length; i++) {
        if (/\s/.test(chars[i])) { current = null; continue }
        if (CJK.test(chars[i])) { words.push({ text: chars[i], start: starts[i] }); current = null; continue }
        if (!current) { current = { text: '', start: starts[i] }; words.push(current) }
        current.text += chars[i]
      }
    }
  }
}

/**
 * Speaks a streamed reply while it is still being written (eleven_v4_turbo via /api/voice/speak-timed).
 * Reports each word as it is spoken (onWord), so the chat can mark it.
 * stop() silences everything immediately; audio that arrives afterwards is discarded.
 */
export function useSpeech(getAudioElement) {
  let generation = 0
  let active = false
  let buffer = ''
  let ended = false
  let pumping = false
  let sentAny = false
  let heardAny = false
  let queue = []
  let currentUrl = null
  let resolveDone = null
  let options = {}
  let raf = 0

  function release() {
    cancelAnimationFrame(raf)
    if (currentUrl) {
      URL.revokeObjectURL(currentUrl)
      currentUrl = null
    }
  }

  function finish() {
    const done = resolveDone
    resolveDone = null
    active = false
    if (options.onWord) options.onWord(null)
    done && done(heardAny)
  }

  function request(text, gen) {
    return fetch(apiUrl('/api/voice/speak-timed'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, language: options.language, session_id: options.sessionId })
    }).then(res => (res.ok && res.body && gen === generation ? res : null)).catch(() => null)
  }

  function enqueue(text) {
    const clean = text.trim()
    if (!/[\p{L}\p{N}]/u.test(clean)) return
    sentAny = true
    queue.push({ gen: generation, response: request(clean, generation) })
    pump()
  }

  // Follows playback and reports the word being spoken.
  function track(el, timeline, gen) {
    let last = -1
    const tick = () => {
      if (gen !== generation) return
      const t = el.currentTime + 0.04
      let idx = last
      while (idx + 1 < timeline.words.length && timeline.words[idx + 1].start <= t) idx++
      if (idx !== last && idx >= 0) {
        last = idx
        if (options.onWord) options.onWord(timeline.words[idx].text)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
  }

  function started(gen) {
    if (gen !== generation) return
    if (!heardAny && options.onStart) options.onStart()
    heardAny = true
  }

  // Plays one piece; resolves when it ends, is stopped or fails.
  function play(res, gen) {
    return new Promise((resolve) => {
      const el = getAudioElement()
      if (!el || gen !== generation) return resolve()
      release()
      const timeline = wordTimeline()
      const settle = () => { cancelAnimationFrame(raf); resolve() }
      el.onended = settle
      el.onpause = settle
      el.onerror = settle
      const isCurrent = () => gen === generation

      if (STREAMING) {
        const ms = new MediaSource()
        currentUrl = URL.createObjectURL(ms)
        el.src = currentUrl
        ms.addEventListener('sourceopen', async () => {
          let playing = false
          try {
            const sb = ms.addSourceBuffer('audio/mpeg')
            const ok = await readTimed(res, async (chunk) => {
              timeline.add(chunk.chars || [], chunk.start || [])
              if (!chunk.audio) return
              sb.appendBuffer(base64ToBytes(chunk.audio))
              await new Promise(r => sb.addEventListener('updateend', r, { once: true }))
              if (!playing && isCurrent()) {
                playing = true
                el.play().then(() => { started(gen); track(el, timeline, gen) }).catch(settle)
              }
            }, isCurrent)
            if (ok && ms.readyState === 'open') ms.endOfStream()
            if (!playing) settle()
          } catch (e) {
            try { if (ms.readyState === 'open') ms.endOfStream() } catch (err) {}
            if (!playing) settle()
          }
        }, { once: true })
        return
      }

      const parts = []
      readTimed(res, async (chunk) => {
        timeline.add(chunk.chars || [], chunk.start || [])
        if (chunk.audio) parts.push(base64ToBytes(chunk.audio))
      }, isCurrent).then((ok) => {
        if (!ok || !parts.length || !isCurrent()) return settle()
        currentUrl = URL.createObjectURL(new Blob(parts, { type: 'audio/mpeg' }))
        el.src = currentUrl
        el.play().then(() => { started(gen); track(el, timeline, gen) }).catch(settle)
      }).catch(settle)
    })
  }

  async function pump() {
    if (pumping) return
    pumping = true
    const gen = generation
    while (queue.length && gen === generation) {
      const item = queue.shift()
      const res = await item.response
      if (item.gen !== generation) continue
      if (res) await play(res, item.gen)
      else if (options.onError) options.onError()
    }
    if (gen !== generation) return
    pumping = false
    if (ended && active && !queue.length) finish()
  }

  // Index just after the first sentence end at or beyond `min` characters (-1 when none yet).
  function boundary(min) {
    SENTENCE_END.lastIndex = 0
    let m
    while ((m = SENTENCE_END.exec(buffer))) {
      const end = m.index + m[0].length
      if (end >= min) return end
    }
    return -1
  }

  function cut(force) {
    while (buffer) {
      let idx = boundary(sentAny ? CHUNK_MIN : 1)
      if (idx < 0 && !sentAny && buffer.length > FIRST_MIN * 2) {
        // A long opening sentence: start on its first clause instead of waiting for the full stop.
        const comma = buffer.slice(FIRST_MIN).search(/[,،、;:](\s)/)
        if (comma >= 0) idx = FIRST_MIN + comma + 1
      }
      if (idx < 0 && buffer.length > CHUNK_MAX) {
        const space = buffer.lastIndexOf(' ', CHUNK_MAX)
        idx = space > 40 ? space : CHUNK_MAX
      }
      if (idx < 0) break
      enqueue(buffer.slice(0, idx))
      buffer = buffer.slice(idx)
    }
    if (force && buffer.trim()) enqueue(buffer)
    if (force) buffer = ''
  }

  /** Starts speaking a new reply. Resolves (with whether any audio played) when done or stopped. */
  function start(opts) {
    stop()
    options = opts || {}
    active = true
    ended = false
    sentAny = false
    heardAny = false
    return new Promise((resolve) => { resolveDone = resolve })
  }

  function setLanguage(language) {
    if (language) options.language = language
  }

  function push(text) {
    if (!active || !text) return
    buffer += text
    cut(false)
  }

  /** The reply is complete; speaks what is left. `fallbackText` is used when no tokens streamed. */
  function end(fallbackText) {
    if (!active) return
    if (!sentAny && !buffer.trim() && fallbackText) buffer = fallbackText
    cut(true)
    ended = true
    if (!pumping && !queue.length) finish()
  }

  function stop() {
    generation += 1
    queue = []
    buffer = ''
    pumping = false
    const el = getAudioElement()
    if (el) {
      try { el.pause() } catch (e) {}
    }
    release()
    if (resolveDone) finish()
    active = false
  }

  return { start, setLanguage, push, end, stop }
}
