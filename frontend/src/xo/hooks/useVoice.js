'use client'
// React binding for the live speech-to-text core (lib/voice.js).
// Renders only when the caption, listening flag or silence countdown change; the microphone level
// is read directly by the voice orb from `voice.state` on each animation frame.
import { useRef, useState } from 'react'
import { createVoice } from '../lib/voice'

export function useVoice() {
  const [view, setView] = useState({ liveText: '', listening: false, silenceCountdown: false })
  const core = useRef(null)
  if (!core.current) core.current = createVoice(setView)
  return { ...view, voice: core.current }
}
