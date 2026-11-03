// Language switching (menu, server-driven, header select), right-to-left, theme, tips and tooltips.
const { test, expect } = require('@playwright/test')
const { openApp, send } = require('./support/mock')
const ui = require('../../frontend/src/xo/i18n/ui.json')

test.describe('language', () => {
  test('menu lists every language; Arabic switches the widget to right-to-left and is sent once', async ({ page }) => {
    const log = await openApp(page)
    await page.locator('.lang-switch-btn').click()
    await expect(page.locator('.lang-menu li')).toHaveCount(ui.languages.length)
    await page.locator('.lang-menu li button', { hasText: 'العربية' }).click()
    await expect(page.locator('.lang-menu')).toHaveCount(0)
    await expect(page.locator('.xo-widget')).toHaveAttribute('dir', 'rtl')
    await expect(page.locator('#chat-text-input')).toHaveAttribute('placeholder', 'اسأل عن العقارات أو التمويل أو الرسوم…')
    await send(page, 'hello')
    expect(log.chat.at(-1)).toMatchObject({ selected_language: 'ar', ui_language: 'ar' })
    await send(page, 'hello again')
    expect(log.chat.at(-1).selected_language).toBeUndefined()
  })

  test('the language search finds a language by its native or English name, without accents; Enter picks it', async ({ page }) => {
    await openApp(page)
    await page.locator('.lang-switch-btn').click()
    const search = page.locator('.lang-search input')
    await search.fill('turkce')
    await expect(page.locator('.lang-menu li')).toHaveCount(1)
    await expect(page.locator('.lang-menu li')).toContainText('Türkçe')
    await search.fill('Gujarati')
    await expect(page.locator('.lang-menu li')).toContainText('ગુજરાતી')
    await search.fill('zzz')
    await expect(page.locator('.lang-empty')).toHaveText('No language matches')
    await search.fill('русс')
    await search.press('Enter')
    await expect(page.locator('.lang-menu')).toHaveCount(0)
    await expect(page.locator('#chat-text-input')).toHaveAttribute('placeholder', ui.strings.ru.placeholder)
  })

  test('every language has every phrase, with the same placeholders as English', () => {
    const placeholders = (s) => (s.match(/\{[a-z_]+\}/g) || []).sort().join()
    for (const { code } of ui.languages) {
      for (const [key, english] of Object.entries(ui.strings.en)) {
        expect(ui.strings[code]?.[key], `${code}.${key}`).toBeTruthy()
        expect(placeholders(ui.strings[code][key]), `${code}.${key}`).toBe(placeholders(english))
      }
    }
  })

  test('switching mid-conversation keeps history and adds a divider', async ({ page }) => {
    await openApp(page)
    await send(page, 'hello')
    await page.locator('.lang-switch-btn').click()
    await page.locator('.lang-menu li button', { hasText: 'हिन्दी' }).click()
    await expect(page.locator('.lang-divider')).toHaveText('भाषा बदलकर हिन्दी की गई')
    await expect(page.locator('.message-wrapper.user')).toHaveCount(1)
  })

  test('a language change from the assistant updates the widget', async ({ page }) => {
    await openApp(page)
    await send(page, 'arabic please')
    await expect(page.locator('.xo-widget')).toHaveAttribute('dir', 'rtl')
    await expect(page.locator('.lang-switch-btn')).toHaveAttribute('aria-label', /العربية/)
  })

  test('the page header language select drives the widget', async ({ page, isMobile }) => {
    test.skip(isMobile, 'desktop shell behaviour')
    await openApp(page)
    await page.locator('#lang-select').selectOption('fr')
    await expect(page.locator('.xo-widget')).toHaveAttribute('lang', 'fr')
    await expect(page.locator('.xo-brand-text small')).toHaveText('Assistant immobilier et prêts')
  })
})

test.describe('theme, tips and tooltips', () => {
  test('dark mode toggles from the widget and persists after reload', async ({ page }) => {
    await openApp(page)
    await page.locator('.theme-toggle-btn').click()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await page.reload()
    await page.locator('.xo-widget').waitFor()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await page.locator('.theme-toggle-btn').click()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  })

  test('header theme pill switches theme', async ({ page, isMobile }) => {
    test.skip(isMobile, 'desktop shell behaviour')
    await openApp(page)
    await page.locator('.theme-btn').nth(1).click()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await expect(page.locator('.theme-btn').nth(1)).toHaveClass(/active/)
  })

  test('the header has no tips button', async ({ page }) => {
    await openApp(page)
    await expect(page.locator('.tips-toggle-btn')).toHaveCount(0)
    await expect(page.locator('.onboarding-tips-container')).toHaveCount(0)
  })

  test('hovering a header button shows its tooltip', async ({ page, isMobile }) => {
    test.skip(isMobile, 'tooltips are for pointer devices')
    await openApp(page)
    await page.locator('.advisor-btn').hover()
    await expect.poll(() => page.locator('.advisor-btn').evaluate((el) => getComputedStyle(el, '::after').content)).toContain('Talk to a human advisor')
  })
})
