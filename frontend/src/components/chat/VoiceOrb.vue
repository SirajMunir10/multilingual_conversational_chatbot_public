<template>
  <canvas ref="canvasRef" class="voice-orb" :style="{ width: size + 'px', height: size + 'px' }" aria-hidden="true"></canvas>
</template>

<script setup>
// XO voice orb: a 3D particle sphere in the brand palette (purple → cyan → lime).
// listening: ripples with the user's voice level · thinking: swirls · speaking: pulses on each spoken word
// hold/idle: slow breathing. Canvas 2D, no dependencies; pauses when hidden; static under reduced motion.
import { ref, watch, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  phase: { type: String, default: 'idle' },
  level: { type: Number, default: 0 },   // 0..1 microphone level
  beat: { type: Number, default: 0 },    // increments on every spoken word
  size: { type: Number, default: 64 },
  dark: { type: Boolean, default: false },
  assemble: { type: Boolean, default: false } // particles fly in and form the sphere (first-time intro)
})

const canvasRef = ref(null)
const STOPS = [[124, 44, 240], [3, 164, 244], [100, 239, 10]] // XO purple (lifted for contrast), cyan, lime
const ENERGY = { listening: 0.16, thinking: 0.32, speaking: 0.28, hold: 0.08, idle: 0.08 }
const SPIN = { listening: 0.5, thinking: 1.5, speaking: 0.7, hold: 0.3, idle: 0.3 }

let particles = []
let raf = 0
let last = 0
let born = 0
let angle = 0
let energy = 0.1
let pulse = 0
let ctx = null
let dpr = 1
const reducedMotion = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

function mix(t) {
  const seg = t < 0.5 ? 0 : 1
  const k = t < 0.5 ? t * 2 : (t - 0.5) * 2
  const a = STOPS[seg], b = STOPS[seg + 1]
  return [0, 1, 2].map(i => Math.round(a[i] + (b[i] - a[i]) * k))
}

function build() {
  const n = Math.max(320, Math.min(1600, Math.round(props.size * props.size * 0.14)))
  const golden = Math.PI * (3 - Math.sqrt(5))
  particles = []
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2
    const r = Math.sqrt(Math.max(0, 1 - y * y))
    const x = Math.cos(golden * i) * r
    const z = Math.sin(golden * i) * r
    const tone = Math.min(1, Math.max(0, 0.5 - 0.42 * y + 0.18 * x + (Math.random() - 0.5) * 0.18))
    const [cr, cg, cb] = mix(tone)
    // Intro start positions: scattered on a wider shell that still fits inside the canvas.
    const spread = 1.25 + Math.random() * 0.35
    const twist = (Math.random() - 0.5) * 1.2
    particles.push({
      x, y, z, seed: Math.random() * Math.PI * 2, jitter: 0.94 + Math.random() * 0.1,
      color: `${cr},${cg},${cb}`,
      sx: (x * Math.cos(twist) - z * Math.sin(twist)) * spread, sy: y * spread, sz: (x * Math.sin(twist) + z * Math.cos(twist)) * spread
    })
  }
}

function resize() {
  const canvas = canvasRef.value
  if (!canvas) return
  dpr = Math.min(window.devicePixelRatio || 1, 2)
  canvas.width = Math.round(props.size * dpr)
  canvas.height = Math.round(props.size * dpr)
  ctx = canvas.getContext('2d')
}

function draw(now) {
  if (!ctx) return
  const dt = Math.min(0.05, (now - (last || now)) / 1000)
  last = now
  const phase = props.phase
  const target = (ENERGY[phase] ?? 0.1) + (phase === 'listening' ? props.level * 0.9 : 0) + pulse
  energy += (target - energy) * Math.min(1, dt * 8)
  pulse *= Math.exp(-dt * 5)
  angle += (SPIN[phase] ?? 0.3) * dt
  const t = now / 1000
  const breathe = phase === 'hold' || phase === 'idle' ? Math.sin(t * 2.4) * 0.025 : 0

  const W = ctx.canvas.width
  const c = W / 2
  const R = W * 0.29 * (1 + breathe + energy * 0.1)
  const focal = R * 3.2
  const assembleK = props.assemble ? Math.min(1, (now - born) / 1500) : 1
  const ease = 1 - Math.pow(1 - assembleK, 3)

  ctx.clearRect(0, 0, W, W)
  const halo = ctx.createRadialGradient(c, c, R * 0.2, c, c, R * 1.65)
  const glow = phase === 'speaking' ? '3,164,244' : phase === 'listening' ? '124,44,240' : '92,3,155'
  halo.addColorStop(0, `rgba(${glow},${props.dark ? 0.35 + energy * 0.4 : 0.18 + energy * 0.3})`)
  halo.addColorStop(1, `rgba(${glow},0)`)
  ctx.fillStyle = halo
  ctx.fillRect(0, 0, W, W)

  ctx.globalCompositeOperation = props.dark ? 'lighter' : 'source-over'
  const cosA = Math.cos(angle), sinA = Math.sin(angle)
  const tilt = 0.38, cosT = Math.cos(tilt), sinT = Math.sin(tilt)
  const dot = Math.max(0.9, W / 120)
  const fade = 0.25 + 0.75 * ease
  for (const p of particles) {
    const wave = Math.sin(p.x * 3 + t * 2.1 + p.seed) * Math.cos(p.y * 3 - t * 1.7) + 0.5 * Math.sin(p.z * 5 + t * 3)
    const k = p.jitter * (1 + energy * 0.22 * wave)
    let x = p.x * k, y = p.y * k, z = p.z * k
    if (ease < 1) {
      x = p.sx + (x - p.sx) * ease
      y = p.sy + (y - p.sy) * ease
      z = p.sz + (z - p.sz) * ease
    }
    const x1 = x * cosA + z * sinA
    const z1 = -x * sinA + z * cosA
    const y2 = y * cosT - z1 * sinT
    const z2 = y * sinT + z1 * cosT
    const scale = focal / (focal - z2 * R)
    const px = c + x1 * R * scale
    const py = c + y2 * R * scale
    const depth = (z2 + 1) / 2
    const alpha = ((props.dark ? 0.25 : 0.35) + depth * 0.65) * fade
    ctx.fillStyle = `rgba(${p.color},${alpha.toFixed(3)})`
    const r = dot * (0.55 + depth * 0.75) * scale
    ctx.beginPath()
    ctx.arc(px, py, r, 0, Math.PI * 2)
    ctx.fill()
  }
  ctx.globalCompositeOperation = 'source-over'
}

function loop(now) {
  draw(now)
  raf = requestAnimationFrame(loop)
}

function start() {
  cancelAnimationFrame(raf)
  if (reducedMotion) {
    draw(performance.now())
    return
  }
  last = 0
  raf = requestAnimationFrame(loop)
}

function onVisibility() {
  if (document.hidden) cancelAnimationFrame(raf)
  else start()
}

watch(() => props.beat, () => { pulse = Math.min(0.55, pulse + 0.32) })
watch(() => props.size, () => { resize(); build(); start() })
watch(() => [props.phase, props.dark], () => { if (reducedMotion) draw(performance.now()) })

onMounted(() => {
  born = performance.now()
  resize()
  build()
  start()
  document.addEventListener('visibilitychange', onVisibility)
})

onUnmounted(() => {
  cancelAnimationFrame(raf)
  document.removeEventListener('visibilitychange', onVisibility)
})
</script>

<style scoped>
.voice-orb { display: block; pointer-events: none; }
</style>
