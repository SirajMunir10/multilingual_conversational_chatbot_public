// Marks the word XO is currently saying inside a rendered reply.
// Spoken words come from the TTS timings; they are matched in order against the words on screen,
// so markdown, numbering and punctuation differences between speech and display do not matter.

const LOOKAHEAD = 8
const CLASS_WORD = 'xo-w'
const CLASS_NOW = 'xo-w-now'

// Chinese has no spaces between words: each character is marked on its own.
export const CJK = /[\u3400-\u9fff\uf900-\ufaff]/
const CJK_SPLIT = /([\u3400-\u9fff\uf900-\ufaff])/

const normalise = (s) => (s || '').toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu, '')

function wrapWords(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.nodeValue.trim() && !n.parentElement.closest(`.${CLASS_WORD}`) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT)
  })
  const nodes = []
  while (walker.nextNode()) nodes.push(walker.currentNode)
  for (const node of nodes) {
    const frag = document.createDocumentFragment()
    for (const part of node.nodeValue.split(/(\s+)/).flatMap(p => (CJK.test(p) ? p.split(CJK_SPLIT) : [p]))) {
      if (!part) continue
      if (/^\s+$/.test(part)) frag.appendChild(document.createTextNode(part))
      else {
        const span = document.createElement('span')
        span.className = CLASS_WORD
        span.textContent = part
        frag.appendChild(span)
      }
    }
    node.parentNode.replaceChild(frag, node)
  }
  return [...root.querySelectorAll(`.${CLASS_WORD}`)].map(el => ({ el, key: normalise(el.textContent) })).filter(w => w.key)
}

export function createWordHighlight() {
  let words = []
  let cursor = 0
  let current = null

  function clear() {
    if (current) current.classList.remove(CLASS_NOW)
    current = null
  }

  /** Prepares a reply element (call once its final text is on screen). */
  function attach(root) {
    clear()
    words = root ? wrapWords(root) : []
    cursor = 0
  }

  /** Marks the next on-screen word matching the spoken word; null clears the mark. */
  function mark(spoken) {
    if (spoken === null) return clear()
    const key = normalise(spoken)
    if (!key || !words.length) return
    const end = Math.min(words.length, cursor + LOOKAHEAD)
    let hit = -1
    for (let i = cursor; i < end && hit < 0; i++) if (words[i].key === key) hit = i
    // Partial forms (e.g. spoken "AED2.1M" vs shown "AED 2.1M") fall back to a prefix match.
    for (let i = cursor; i < end && hit < 0 && key.length > 2; i++) {
      if (words[i].key.startsWith(key) || key.startsWith(words[i].key)) hit = i
    }
    if (hit < 0) return
    clear()
    cursor = hit + 1
    if (!words[hit].el.isConnected) return
    current = words[hit].el
    current.classList.add(CLASS_NOW)
  }

  function detach() {
    clear()
    words = []
    cursor = 0
  }

  return { attach, mark, detach }
}
