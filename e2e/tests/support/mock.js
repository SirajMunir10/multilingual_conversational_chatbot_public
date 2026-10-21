// Simulated XO backend for the frontend tests.
// Every /api call the widget makes is answered here, so the same tests give the same results on any
// frontend build (Vue today, Next.js after the migration). Response shapes come from the real backend
// (see ../../fixtures, captured from FastAPI).
const fs = require('fs')
const path = require('path')

const FIXTURES = path.join(__dirname, '..', '..', 'fixtures')
const load = (name) => JSON.parse(fs.readFileSync(path.join(FIXTURES, name), 'utf-8'))
const CONFIG = load('config.json')
const PROPERTIES = load('properties.json')
const MORTGAGE = load('mortgage.json')
const TTS = load('tts.json')

const FIXED_TIME = new Date('2026-10-19T10:00:00+04:00')

const REPLIES = {
  default: 'Hi! I can help with UAE property, mortgages, renting or XOTO services.',
  properties: 'I found **3 homes** in Dubai Marina:\n\n1. An off-plan project from AED 703,000\n2. A ready 1-bedroom from AED 1,350,000\n3. A ready 2-bedroom from AED 3,200,000',
  eligibility: 'You are eligible for up to **AED 2,000,000**. The loan-to-value limit is the tightest, so you are short by AED 250,000.',
  affordability: 'You could borrow up to **AED 2,293,827** at the 3.8% benchmark over 25 years.',
  emi: 'On a AED 1.5M apartment the estimated payment is **AED 6,202** a month.',
  advisor: 'Please check the details on the card and tap Confirm, or Edit to change them.',
  arabic: 'مرحباً! يمكنني مساعدتك في العقارات والتمويل العقاري في الإمارات.',
  xss: 'Safe **markdown** check <img src=x onerror="window.__xss=1"> <script>window.__xss=2</script>',
  long: Array.from({ length: 14 }, (_, i) => `${i + 1}. Point number ${i + 1} about buying property in the UAE.`).join('\n'),
  voice: 'I found three homes in Dubai Marina for you.'
}

function scenario(message) {
  const m = (message || '').toLowerCase()
  if (m.includes('xss')) return 'xss'
  if (m.includes('long')) return 'long'
  if (m.includes('advisor')) return 'advisor'
  if (m.includes('arabic')) return 'arabic'
  if (m.includes('eligib')) return 'eligibility'
  if (m.includes('afford') || m.includes('borrow')) return 'affordability'
  if (m.includes('payment')) return 'emi'
  if (m.includes('show me homes')) return 'voice'
  if (m.includes('propert') || m.includes('marina')) return 'properties'
  return 'default'
}

function sse(events) {
  return events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('')
}

function tokens(text) {
  const words = text.split(/(\s+)/)
  const size = Math.max(1, Math.ceil(words.length / 4))
  const out = []
  for (let i = 0; i < words.length; i += size) out.push({ type: 'token', text: words.slice(i, i + size).join('') })
  return out
}

/**
 * Installs the simulated backend and a scripted (silent) microphone on a page.
 * Returns a log of what the widget sent, for assertions.
 */
async function installMocks(page, { transcript = 'Show me homes in Dubai Marina' } = {}) {
  const log = { chat: [], speak: [], confirm: [], sttSockets: 0, sttCommits: 0 }
  let advisorCount = 0

  await page.clock.setFixedTime(FIXED_TIME)
  await page.addInitScript(() => {
    // Scripted microphone: a silent stream, so speech is detected only from transcript activity.
    MediaDevices.prototype.getUserMedia = async function () {
      const ctx = new AudioContext()
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      gain.gain.value = 0
      const dest = ctx.createMediaStreamDestination()
      osc.connect(gain).connect(dest)
      osc.start()
      return dest.stream
    }
    window.__plays = []
    const play = HTMLMediaElement.prototype.play
    HTMLMediaElement.prototype.play = function () {
      if (!this.muted) window.__plays.push(performance.now())
      return play.call(this)
    }
  })

  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname

    if (p.endsWith('/api/config')) return route.fulfill({ json: CONFIG })
    if (p.endsWith('/api/health')) return route.fulfill({ json: { status: 'ok' } })

    if (p.endsWith('/api/chat/stream')) {
      const body = req.postDataJSON()
      log.chat.push(body)
      const kind = scenario(body.message)
      const lang = kind === 'arabic' ? 'ar' : (body.selected_language || body.ui_language || 'en')
      const extra = {}
      const status = []
      if (kind === 'properties' || kind === 'voice') { status.push({ type: 'status', tool: 'search_properties' }); extra.property_results = PROPERTIES }
      if (kind === 'eligibility') { status.push({ type: 'status', tool: 'check_eligibility' }); extra.mortgage_result = MORTGAGE.eligibility }
      if (kind === 'affordability') { status.push({ type: 'status', tool: 'calc_affordability' }); extra.mortgage_result = MORTGAGE.affordability }
      if (kind === 'emi') { status.push({ type: 'status', tool: 'calc_emi' }); extra.mortgage_result = MORTGAGE.emi }
      if (kind === 'advisor') {
        advisorCount += 1
        extra.handoff_draft = { draft_id: `draft-${advisorCount}`, name: 'Rahul Sharma', phone: '+971 50 123 4567', preferred_language: 'en', team: 'mortgage', status: 'review' }
      }
      const text = REPLIES[kind]
      const events = [{ type: 'session', session_id: 'sess_test', language: lang }, ...status, ...tokens(text),
        { type: 'final', session_id: 'sess_test', language: lang, text, tools: status.map((s) => s.tool), ...extra }]
      return route.fulfill({ status: 200, headers: { 'Content-Type': 'text/event-stream' }, body: sse(events) })
    }

    if (p.endsWith('/api/handoff/confirm')) {
      const body = req.postDataJSON()
      log.confirm.push(body)
      if ((body.phone || '').replace(/\D/g, '').startsWith('0884')) return route.fulfill({ json: { lead_saved: false, error: 'invalid_phone', field: 'phone' } })
      if (body.draft_id !== `draft-${advisorCount}`) return route.fulfill({ json: { lead_saved: false, error: 'draft_expired' } })
      return route.fulfill({ json: { lead_saved: true, ticket_id: 'XO-261019-ABC123', team: body.team, name: body.full_name.trim(),
        phone: body.phone, preferred_language: body.preferred_language, status: 'saved' } })
    }

    if (p.endsWith('/api/voice/speak-timed')) {
      const body = req.postDataJSON()
      log.speak.push(body.text)
      // Real audio from the backend; character timings spread over its duration for whatever text was asked.
      const chars = [...body.text]
      const step = (TTS.duration_sec * 0.95) / Math.max(chars.length, 1)
      const first = { audio: TTS.audio_chunks[0], chars, start: chars.map((_, i) => +(i * step).toFixed(3)), end: chars.map((_, i) => +((i + 1) * step).toFixed(3)) }
      const rest = TTS.audio_chunks.slice(1).map((audio) => ({ audio, chars: [], start: [], end: [] }))
      return route.fulfill({ status: 200, headers: { 'Content-Type': 'application/x-ndjson' }, body: [first, ...rest].map((l) => JSON.stringify(l)).join('\n') + '\n' })
    }

    if (p.endsWith('/api/voice/speak')) {
      return route.fulfill({ status: 200, headers: { 'Content-Type': 'audio/mpeg' }, body: Buffer.from(TTS.audio_chunks.join(''), 'base64') })
    }

    return route.fulfill({ status: 404, json: { detail: 'not mocked' } })
  })

  // Live transcription: "ready", then transcript deltas while audio frames arrive, "final" on commit.
  await page.routeWebSocket(/\/api\/voice\/stt/, (ws) => {
    log.sttSockets += 1
    let frames = 0
    let sent = false
    setTimeout(() => ws.send(JSON.stringify({ type: 'ready' })), 100)
    ws.onMessage((message) => {
      if (typeof message === 'string') {
        const msg = JSON.parse(message)
        if (msg.type === 'commit') {
          log.sttCommits += 1
          setTimeout(() => ws.send(JSON.stringify({ type: 'final', text: transcript })), 150)
        }
        return
      }
      frames += 1
      if (!sent && frames >= 3) {
        sent = true
        const words = transcript.split(' ')
        words.forEach((w, i) => setTimeout(() => ws.send(JSON.stringify({ type: 'delta', text: (i ? ' ' : '') + w })), 150 * (i + 1)))
      }
    })
  })
  return log
}

/** Opens the app with mocks installed and waits for fonts so screenshots are stable. */
async function openApp(page, options) {
  const log = await installMocks(page, options)
  await page.goto('/')
  await page.locator('.xo-widget').waitFor()
  // Load the app's web fonts before interacting, so text wrapping (and therefore scroll positions) never depends
  // on whether a font arrived a few milliseconds earlier or later.
  await page.evaluate(() => Promise.all(['400 16px Inter', '500 16px Inter', '600 16px Inter', '700 16px Inter',
    '600 16px Outfit', '700 16px Outfit', '800 16px Outfit', '400 16px Cairo', '600 16px Cairo'].map((f) => document.fonts.load(f))))
  await page.evaluate(() => document.fonts.ready)
  return log
}

/** Sends a message and waits until the reply has finished streaming. */
async function send(page, text) {
  const replies = page.locator('.message-wrapper.assistant')
  const before = await replies.count()
  await page.locator('#chat-text-input').fill(text)
  await page.locator('#chat-text-input').press('Enter')
  await page.waitForFunction((n) => document.querySelectorAll('.message-wrapper.assistant').length > n && !document.querySelector('.streaming-cursor'), before)
  return replies.last()
}

module.exports = { installMocks, openApp, send, REPLIES, PROPERTIES, MORTGAGE }
