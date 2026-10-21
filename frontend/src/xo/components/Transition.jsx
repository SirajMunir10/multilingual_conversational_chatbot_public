'use client'
// Minimal equivalents of Vue's <transition>, so the existing CSS classes keep working unchanged:
//   enter: `${name}-enter-from ${name}-enter-active` → next frame → `${name}-enter-active ${name}-enter-to` → done
//   leave: `${name}-leave-from ${name}-leave-active` → next frame → `${name}-leave-active ${name}-leave-to` → removed
// Like Vue, the end is detected from the element's computed transition/animation duration.
import { cloneElement, useLayoutEffect, useRef, useState } from 'react'

const nextFrame = (fn) => requestAnimationFrame(() => requestAnimationFrame(fn))
const cx = (...names) => names.filter(Boolean).join(' ')

function toMs(list) {
  return Math.max(0, ...list.split(',').map((v) => (v.trim().endsWith('ms') ? parseFloat(v) : parseFloat(v) * 1000) || 0))
}

function whenDone(el, done) {
  if (!el) return done()
  const cs = getComputedStyle(el)
  const total = Math.max(toMs(cs.transitionDuration) + toMs(cs.transitionDelay), toMs(cs.animationDuration) + toMs(cs.animationDelay))
  if (!total) return done()
  let finished = false
  const finish = (e) => {
    if ((e && e.target !== el) || finished) return
    finished = true
    el.removeEventListener('transitionend', finish)
    el.removeEventListener('animationend', finish)
    clearTimeout(timer)
    done()
  }
  el.addEventListener('transitionend', finish)
  el.addEventListener('animationend', finish)
  const timer = setTimeout(finish, total + 50)
}

/** Shows or hides one element (Vue `<transition>` around a `v-if`). */
export function Transition({ name, show, children }) {
  const [rendered, setRendered] = useState(show)
  const [classes, setClasses] = useState('')
  const ref = useRef(null)
  const last = useRef(children)
  const mounted = useRef(false)
  if (show && children) last.current = children

  useLayoutEffect(() => {
    if (!mounted.current) {
      mounted.current = true
      return undefined
    }
    let cancelled = false
    if (show) {
      setRendered(true)
      setClasses(cx(`${name}-enter-from`, `${name}-enter-active`))
      nextFrame(() => {
        if (cancelled) return
        setClasses(cx(`${name}-enter-active`, `${name}-enter-to`))
        whenDone(ref.current, () => { if (!cancelled) setClasses('') })
      })
    } else {
      setClasses(cx(`${name}-leave-from`, `${name}-leave-active`))
      nextFrame(() => {
        if (cancelled) return
        setClasses(cx(`${name}-leave-active`, `${name}-leave-to`))
        whenDone(ref.current, () => {
          if (cancelled) return
          setRendered(false)
          setClasses('')
        })
      })
    }
    return () => { cancelled = true }
  }, [show, name])

  if (!rendered) return null
  const child = show ? children : last.current
  if (!child) return null
  return cloneElement(child, { ref, className: cx(child.props.className, classes) })
}

/** Swaps between keyed elements, old one leaving before the new one enters (Vue `mode="out-in"`). */
export function SwitchTransition({ name, activeKey, render }) {
  const [shown, setShown] = useState(activeKey)
  const [classes, setClasses] = useState('')
  const ref = useRef(null)

  useLayoutEffect(() => {
    if (activeKey === shown) {
      setClasses('')
      return undefined
    }
    let cancelled = false
    setClasses(cx(`${name}-leave-from`, `${name}-leave-active`))
    nextFrame(() => {
      if (cancelled) return
      setClasses(cx(`${name}-leave-active`, `${name}-leave-to`))
      whenDone(ref.current, () => {
        if (cancelled) return
        setShown(activeKey)
        setClasses(cx(`${name}-enter-from`, `${name}-enter-active`))
        nextFrame(() => {
          if (cancelled) return
          setClasses(cx(`${name}-enter-active`, `${name}-enter-to`))
          whenDone(ref.current, () => { if (!cancelled) setClasses('') })
        })
      })
    })
    return () => { cancelled = true }
    // `shown` changes inside this effect's own flow; re-running on it would restart the swap.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeKey, name])

  const element = render(shown)
  if (!element) return null
  return cloneElement(element, { key: shown, ref, className: cx(element.props.className, classes) })
}
