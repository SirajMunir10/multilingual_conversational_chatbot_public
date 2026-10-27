// Voice mode: quick entry (no full-screen intro), the mic hint for new users, listening with live caption, thinking,
// speaking with the spoken word marked, hold, tap-to-interrupt, closing stops all audio, the hint gone after two turns.
// Runs on Chromium (desktop, Android) and WebKit (iPhone).
const { test, expect } = require('@playwright/test')
const { openApp } = require('./support/mock')

const phase = (page) => page.locator('.voice-dock').getAttribute('class').then((c) => (c || '').match(/phase-(\w+)/)?.[1])

test('full voice conversation', async ({ page }) => {
  test.setTimeout(120_000)
  const log = await openApp(page)
  const marks = []
  await page.exposeFunction('__mark', (w) => marks.push(w))
  await page.evaluate(() => new MutationObserver(() => {
    const now = document.querySelector('.xo-w-now')
    if (now) window.__mark(now.textContent)
  }).observe(document.body, { subtree: true, attributes: true, attributeFilter: ['class'] }))

  // First entry: straight to listening (no intro screen); a hand points at the mic for a new user
  await page.locator('.mic-btn').click()
  await expect(page.locator('.voice-dock.phase-listening')).toBeVisible({ timeout: 3_000 })
  await expect(page.locator('.voice-intro')).toHaveCount(0)
  await expect(page.locator('.voice-coach')).toContainText("I'm listening — just speak")
  await expect(page.locator('.voice-dock-caption')).toHaveText('Show me homes in Dubai Marina', { timeout: 15_000 })
  await expect(page.locator('.voice-coach')).toHaveCount(0) // the hint steps aside once the visitor talks

  // The turn is sent after silence; XO thinks, then speaks with the text and the voice together
  await expect(page.locator('.voice-dock.phase-speaking')).toBeVisible({ timeout: 20_000 })
  await expect(page.locator('.voice-dock-status')).toHaveText('XO is speaking — tap the mic to interrupt')
  await expect(page.locator('.message-wrapper.user').last()).toContainText('Show me homes in Dubai Marina')
  await expect(page.locator('.message-wrapper.assistant').last().locator('.md')).toHaveText('I found three homes in Dubai Marina for you.')
  await expect(page.locator('.message-wrapper.assistant').last().locator('.prop-card')).toHaveCount(3)

  // After speaking: hold (no automatic listening), the mark is cleared
  await expect(page.locator('.voice-dock.phase-hold')).toBeVisible({ timeout: 20_000 })
  await expect(page.locator('.voice-dock-status')).toHaveText('Tap the mic to talk again')
  await expect(page.locator('.voice-coach')).toContainText('Tap the mic to speak')
  await expect(page.locator('.voice-orb-btn.is-coached')).toHaveCount(1)
  await expect(page.locator('.xo-w-now')).toHaveCount(0)
  expect(marks.length).toBeGreaterThan(3)
  expect(log.sttCommits).toBe(1)
  expect(log.speak.join(' ')).toContain('Dubai Marina')
  expect(log.chat.at(-1)).toMatchObject({ message: 'Show me homes in Dubai Marina', channel: 'voice' })
  await page.waitForTimeout(2500)
  expect(await phase(page)).toBe('hold')
  expect(log.sttSockets).toBe(1)

  // Tap in hold -> listening; while XO speaks, tap interrupts and listens again
  await page.locator('.voice-orb-btn').click({ force: true })
  await expect(page.locator('.voice-dock.phase-listening')).toBeVisible()
  await expect(page.locator('.voice-dock.phase-speaking')).toBeVisible({ timeout: 25_000 })
  await page.locator('.voice-orb-btn').click({ force: true })
  await expect(page.locator('.voice-dock.phase-listening')).toBeVisible()
  expect(await page.locator('audio').evaluate((a) => a.paused)).toBe(true)

  // Closing voice mode stops everything; no audio afterwards
  await page.locator('.xo-round-btn.cancel').click()
  await expect(page.locator('.voice-dock')).toHaveCount(0)
  await expect(page.locator('#chat-text-input')).toBeVisible()
  const plays = await page.evaluate(() => window.__plays.length)
  await page.waitForTimeout(6000)
  expect(await page.evaluate(() => window.__plays.length)).toBe(plays)

  // Second entry: after two voice turns the hint is no longer needed
  await page.locator('.mic-btn').click()
  await expect(page.locator('.voice-dock.phase-listening')).toBeVisible()
  await page.waitForTimeout(400)
  await expect(page.locator('.voice-coach')).toHaveCount(0)
  await page.locator('.xo-round-btn.cancel').click()
})

test('a long spoken question keeps its newest words in view; entering voice mode takes under a second', async ({ page }) => {
  test.setTimeout(60_000)
  const transcript = 'I am looking for a three bedroom villa in Arabian Ranches or Dubai Hills with a garden and a pool close to a good school and I can spend about four million dirhams'
  await openApp(page, { transcript })
  await page.evaluate(() => localStorage.setItem('xo_voice_turns', '2'))
  await page.locator('.mic-btn').click()
  const ripple = page.locator('.voice-enter-ripple')
  const ms = await ripple.evaluate((el) => parseFloat(getComputedStyle(el).animationDuration) * 1000)
  expect(ms).toBeLessThan(1000)
  await expect(page.locator('.voice-dock.phase-listening')).toBeVisible({ timeout: 3_000 })

  const caption = page.locator('.voice-dock-caption')
  await expect(caption).toContainText('million dirhams', { timeout: 15_000 })
  // The caption is three lines high and scrolled to its end, so the last words are the ones on screen.
  const view = await caption.evaluate((el) => ({ hidden: el.scrollHeight > el.clientHeight + 2, atEnd: el.scrollHeight - el.scrollTop - el.clientHeight < 2 }))
  expect(view).toEqual({ hidden: true, atEnd: true })
  await page.locator('.xo-round-btn.cancel').click()
})
