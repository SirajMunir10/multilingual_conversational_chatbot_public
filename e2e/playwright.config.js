// XO frontend end-to-end tests.
// The backend is simulated (tests/support/mock.js) so runs are fast, free and repeatable, and the same
// suite can be pointed at any frontend build:  BASE_URL=http://localhost:3001 npx playwright test
const { defineConfig, devices } = require('@playwright/test')

const chromiumArgs = ['--autoplay-policy=no-user-gesture-required']

module.exports = defineConfig({
  testDir: './tests',
  timeout: 60_000,
  expect: {
    timeout: 10_000,
    toHaveScreenshot: { maxDiffPixelRatio: 0.01, animations: 'disabled', caret: 'hide', scale: 'css' }
  },
  fullyParallel: true,
  workers: 3,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'report' }]],
  snapshotPathTemplate: '{testDir}/__screenshots__/{projectName}/{testFileName}/{arg}{ext}',
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    locale: 'en-US',
    timezoneId: 'Asia/Dubai',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure'
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 }, launchOptions: { args: chromiumArgs } } },
    { name: 'android', use: { ...devices['Pixel 7'], launchOptions: { args: chromiumArgs } } },
    { name: 'iphone', use: { ...devices['iPhone 13'] } }
  ]
})
