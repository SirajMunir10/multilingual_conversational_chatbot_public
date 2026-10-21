// Screenshot comparison. The reference images are taken from the Vue version; the Next.js version must match them.
const { test, expect } = require('@playwright/test')
const { openApp: open, send } = require('./support/mock')

// WebKit applies the app's custom ::-webkit-scrollbar style to the page scrollbar only if the scrollbar is
// created after the CSS has loaded, so the same CSS can render with or without a 6px gutter depending on load
// timing. Real iPhones never draw these scrollbars. Zeroing them before the first layout keeps the comparison
// about the app itself (layout, scroll positions and wrapping are then identical for both builds).
const NO_SCROLLBARS = '::-webkit-scrollbar { width: 0 !important; height: 0 !important; }'
async function openApp(page, options) {
  // Applied before the page's first layout (WebKit keeps the gutter it measured at first layout).
  await page.addInitScript((css) => {
    const sheet = new CSSStyleSheet()
    sheet.replaceSync(css)
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet]
  }, NO_SCROLLBARS)
  return open(page, options)
}

async function settle(page) {
  await page.evaluate(async () => {
    await document.fonts.ready
    await Promise.all([...document.images].map((img) => (img.complete ? null : new Promise((r) => { img.onload = img.onerror = r }))))
  })
  await page.waitForTimeout(400)
}

async function shot(page, name) {
  await settle(page)
  await expect(page).toHaveScreenshot(`${name}.png`, { mask: [page.locator('canvas')] })
}

test.describe('visual parity', () => {
  test('home', async ({ page }) => { await openApp(page); await shot(page, 'home') })

  test('property results', async ({ page }) => {
    await openApp(page)
    await send(page, 'show me properties in marina')
    await shot(page, 'properties')
    await page.locator('.prop-card').nth(1).locator('.prop-compact-bar').click()
    await page.locator('.prop-card').nth(1).locator('.prop-expanded-drawer').scrollIntoViewIfNeeded()
    await shot(page, 'property-expanded')
  })

  test('eligibility card expanded', async ({ page }) => {
    await openApp(page)
    const reply = await send(page, 'am I eligible for 2.5M')
    await reply.locator('.btn-toggle-mortgage-card').click()
    await reply.locator('.mortgage-card').evaluate((el) => el.scrollIntoView({ block: 'start' }))
    await shot(page, 'eligibility')
  })

  test('advisor card in edit mode', async ({ page }) => {
    await openApp(page)
    const reply = await send(page, 'I want an advisor')
    await reply.locator('.hc-btn.ghost').click()
    // Wait until the name field has focus (the card focuses it after rendering the form), then scroll.
    await expect(reply.locator('.hc-form input[type="text"]')).toBeFocused()
    await page.waitForTimeout(300)
    await reply.locator('.handoff-card').evaluate((el) => el.scrollIntoView({ block: 'end' }))
    await shot(page, 'advisor-edit')
  })

  test('arabic right-to-left', async ({ page }) => {
    await openApp(page)
    await send(page, 'arabic please')
    await shot(page, 'arabic')
  })

  test('dark mode', async ({ page }) => {
    await openApp(page)
    await page.locator('.theme-toggle-btn').click()
    await send(page, 'show me properties in marina')
    await shot(page, 'dark')
  })

  test('language menu', async ({ page }) => {
    await openApp(page)
    await page.locator('.lang-switch-btn').click()
    await shot(page, 'language-menu')
  })

  test('tips panel', async ({ page, isMobile }) => {
    await openApp(page)
    test.skip(isMobile && !(await page.locator('.tips-toggle-btn').isVisible()), 'tips button hidden on narrow phones')
    await page.locator('.tips-toggle-btn').click()
    await shot(page, 'tips')
  })

  test('voice dock in hold', async ({ page }) => {
    test.setTimeout(90_000)
    await openApp(page)
    await page.evaluate(() => localStorage.setItem('xo_voice_intro_seen', '1'))
    await page.locator('.mic-btn').click()
    await expect(page.locator('.voice-dock.phase-hold')).toBeVisible({ timeout: 45_000 })
    await shot(page, 'voice-hold')
  })

  test('admin preview', async ({ page, isMobile }) => {
    test.skip(isMobile, 'desktop shell')
    await openApp(page)
    await page.locator('.app-header .nav-tab').nth(1).click()
    await shot(page, 'admin')
  })

  test('widget closed shows the launcher', async ({ page, isMobile }) => {
    test.skip(isMobile, 'desktop shell')
    await openApp(page)
    await page.locator('.close-widget-btn').click()
    await shot(page, 'launcher')
  })
})
