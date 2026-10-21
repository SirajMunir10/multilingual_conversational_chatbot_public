// The widget fits every screen: phones (portrait/landscape), foldables, tablets, laptops, monitors and TVs.
const { test, expect, devices } = require('@playwright/test')
const { installMocks } = require('./support/mock')

const SIZES = [
  ['iPhone SE', { viewport: { width: 320, height: 568 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 }],
  ['Pixel 7', devices['Pixel 7']],
  ['Galaxy S9+', devices['Galaxy S9+']],
  ['iPhone 14', { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 3 }],
  ['Phone landscape', { viewport: { width: 844, height: 390 }, isMobile: true, hasTouch: true, deviceScaleFactor: 3 }],
  ['Galaxy Fold', { viewport: { width: 280, height: 653 }, isMobile: true, hasTouch: true, deviceScaleFactor: 3 }],
  ['iPad portrait', { viewport: { width: 768, height: 1024 }, isMobile: true, hasTouch: true }],
  ['iPad landscape', { viewport: { width: 1024, height: 768 }, isMobile: true, hasTouch: true }],
  ['Laptop 1280', { viewport: { width: 1280, height: 720 } }],
  ['Laptop 1440', { viewport: { width: 1440, height: 900 } }],
  ['Desktop 1920', { viewport: { width: 1920, height: 1080 } }],
  ['QHD 2560', { viewport: { width: 2560, height: 1440 } }],
  ['TV 4K', { viewport: { width: 3840, height: 2160 } }]
]

test.describe('responsive', () => {
  for (const [name, options] of SIZES) {
    test(name, async ({ browser, baseURL }, info) => {
      test.skip(info.project.name !== 'desktop', 'runs once, in its own contexts')
      const context = await browser.newContext({ ...options, baseURL })
      const page = await context.newPage()
      await installMocks(page)
      await page.goto('/')
      await page.locator('.xo-widget').waitFor()
      const r = await page.evaluate(() => {
        const w = document.querySelector('.xo-widget').getBoundingClientRect()
        const input = document.querySelector('#chat-text-input').getBoundingClientRect()
        const buttons = [...document.querySelectorAll('.xo-header button')].filter((b) => b.offsetParent).map((b) => b.getBoundingClientRect())
        return {
          inside: w.left >= -1 && w.top >= -1 && w.right <= innerWidth + 1 && w.bottom <= innerHeight + 1,
          inputVisible: input.top >= 0 && input.bottom <= innerHeight + 1,
          headerFits: buttons.every((b) => b.left >= w.left - 1 && b.right <= w.right + 1),
          hscroll: document.documentElement.scrollWidth > innerWidth + 1
        }
      })
      expect(r).toEqual({ inside: true, inputVisible: true, headerFits: true, hscroll: false })
      await context.close()
    })
  }
})
