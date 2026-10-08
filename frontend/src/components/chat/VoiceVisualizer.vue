<template>
  <div class="pplx-particle-container" v-show="isActive">
    <canvas 
      ref="canvasRef" 
      width="360" 
      height="360" 
      class="pplx-particle-canvas"
      aria-hidden="true"
    ></canvas>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'

const props = defineProps({
  isActive: {
    type: Boolean,
    default: false
  },
  isCompact: {
    type: Boolean,
    default: false
  },
  audioLevel: {
    type: Number,
    default: 0
  }
})

const canvasRef = ref(null)
let animationFrameId = null

// Perplexity 3D Particle Sphere Model
const NUM_PARTICLES = 1250
const particles = []

// Initialize Fibonacci Point-Cloud Sphere
const initParticles = () => {
  particles.length = 0
  const phi = Math.PI * (3.0 - Math.sqrt(5.0)) // Golden angle in radians

  for (let i = 0; i < NUM_PARTICLES; i++) {
    const y = 1 - (i / (NUM_PARTICLES - 1)) * 2 // From 1 to -1
    const radiusAtY = Math.sqrt(Math.max(0, 1 - y * y))
    const theta = phi * i

    const x = Math.cos(theta) * radiusAtY
    const z = Math.sin(theta) * radiusAtY

    // Volumetric particulate jitter for that iconic fuzzy Perplexity orb look
    const jitter = 0.94 + Math.random() * 0.12

    // XO Official Brand Palette (rich saturation for crisp visibility on both light & dark modes):
    // 1. Electric Cyan:  rgb(3, 164, 244)
    // 2. Vibrant Purple: rgb(147, 51, 234)
    // 3. Crisp Emerald / Lime: rgb(22, 163, 74)
    const rand = Math.random()
    let r, g, b, isLime = false
    if (rand < 0.44) {
      // Electric Cyan
      r = 3; g = 164; b = 244;
    } else if (rand < 0.82) {
      // Vibrant Brand Purple
      r = 147; g = 51; b = 234;
    } else {
      // Crisp Lime/Emerald Green
      r = 22; g = 163; b = 74;
      isLime = true;
    }

    particles.push({
      origX: x * jitter,
      origY: y * jitter,
      origZ: z * jitter,
      phase: Math.random() * Math.PI * 2,
      driftSpeed: 0.8 + Math.random() * 0.6,
      r, g, b, isLime
    })
  }
}

// 3D Orbital Rotation & Smooth Scaling
let rotX = 0.15
let rotY = 0.35
let rotZ = 0.05
let time = 0
let currentRadius = 78

const renderFrame = () => {
  if (!props.isActive) return

  const canvas = canvasRef.value
  if (!canvas) {
    animationFrameId = requestAnimationFrame(renderFrame)
    return
  }
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    animationFrameId = requestAnimationFrame(renderFrame)
    return
  }

  const width = canvas.width
  const height = canvas.height
  const cx = width / 2
  const cy = height / 2

  ctx.clearRect(0, 0, width, height)

  // Increment rotation angles smoothly
  time += 0.016
  rotX += 0.005
  rotY += 0.008
  rotZ += 0.003

  // Dynamic radius interpolation (big initial state vs compact speaking state)
  const targetBase = props.isCompact ? 46 : 76
  currentRadius += (targetBase - currentRadius) * 0.14

  // Audio responsive organic deformation
  const effectiveAudio = Math.min(Math.max(props.audioLevel, 0), 1)
  const breathing = Math.sin(time * 1.6) * 2.5
  const audioPulse = effectiveAudio * 20
  const baseRadius = currentRadius + breathing + audioPulse

  // Subtle central ambient glow reflecting XO purple & cyan brand tones
  const glowGrad = ctx.createRadialGradient(cx, cy, 4, cx, cy, Math.max(10, baseRadius * 0.95))
  glowGrad.addColorStop(0, 'rgba(147, 51, 234, 0.09)')
  glowGrad.addColorStop(0.5, 'rgba(3, 164, 244, 0.04)')
  glowGrad.addColorStop(1, 'rgba(3, 164, 244, 0.0)')
  ctx.fillStyle = glowGrad
  ctx.fillRect(0, 0, width, height)

  // Pre-calculate trigonometric rotations
  const cosX = Math.cos(rotX)
  const sinX = Math.sin(rotX)
  const cosY = Math.cos(rotY)
  const sinY = Math.sin(rotY)
  const cosZ = Math.cos(rotZ)
  const sinZ = Math.sin(rotZ)

  const cameraZ = 3.0

  // Rotate, project, and render particle points
  for (let i = 0; i < particles.length; i++) {
    const p = particles[i]

    // Surface wave ripple when speaking / audio active
    const wave = effectiveAudio > 0.02
      ? Math.sin(time * 6 + p.phase) * (effectiveAudio * 0.12)
      : Math.sin(time * 1.5 + p.phase) * 0.02

    const vRadius = 1.0 + wave
    const vx = p.origX * vRadius
    const vy = p.origY * vRadius
    const vz = p.origZ * vRadius

    // 3D Matrix Rotation (X, Y, Z)
    const y1 = vy * cosX - vz * sinX
    const z1 = vy * sinX + vz * cosX

    const x2 = vx * cosY + z1 * sinY
    const z2 = -vx * sinY + z1 * cosY

    const x3 = x2 * cosZ - y1 * sinZ
    const y3 = x2 * sinZ + y1 * cosZ
    const z3 = z2

    // Perspective Projection
    const scale = cameraZ / (cameraZ + z3)
    const px = cx + x3 * baseRadius * scale
    const py = cy + y3 * baseRadius * scale

    // High-clarity Depth-based stippled shading
    let alpha = 0.35
    let dotRadius = 1.2

    if (z3 > 0) {
      // Front hemisphere (crisp & defined)
      alpha = Math.max(0.65, Math.min(0.98, 0.72 + (z3 * 0.24) + (effectiveAudio * 0.15)))
      dotRadius = Math.max(1.4, (2.1 * scale) + (effectiveAudio * 0.6))
    } else {
      // Back hemisphere (soft & ethereal depth)
      alpha = Math.max(0.22, Math.min(0.48, 0.32 + (z3 * 0.15)))
      dotRadius = Math.max(0.85, 1.2 * scale)
    }

    // Audio-reactive boost: as user speaks, emerald & cyan energize
    let pr = p.r
    let pg = p.g
    let pb = p.b
    if (effectiveAudio > 0.05 && z3 > 0) {
      if (p.isLime) {
        dotRadius += effectiveAudio * 0.8
        alpha = Math.min(1.0, alpha + 0.2)
      } else {
        alpha = Math.min(1.0, alpha + effectiveAudio * 0.15)
      }
    }

    ctx.beginPath()
    ctx.arc(px, py, dotRadius, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(${pr}, ${pg}, ${pb}, ${alpha.toFixed(3)})`
    ctx.fill()
  }

  if (props.isActive) {
    animationFrameId = requestAnimationFrame(renderFrame)
  }
}

const startAnimation = () => {
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId)
    animationFrameId = null
  }
  if (particles.length === 0) {
    initParticles()
  }
  animationFrameId = requestAnimationFrame(renderFrame)
}

const stopAnimation = () => {
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId)
    animationFrameId = null
  }
}

watch(() => props.isActive, (active) => {
  if (active) {
    nextTick(() => {
      startAnimation()
    })
  } else {
    stopAnimation()
  }
}, { immediate: true })

onMounted(() => {
  initParticles()
  if (props.isActive) {
    nextTick(() => {
      startAnimation()
    })
  }
})

onUnmounted(() => {
  stopAnimation()
})
</script>

<style scoped>
.pplx-particle-container {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}

.pplx-particle-canvas {
  width: 100%;
  height: 100%;
  aspect-ratio: 1 / 1;
  display: block;
}
</style>
