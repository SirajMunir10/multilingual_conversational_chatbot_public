// Editing XO from the admin module (PRD FR-24, FR-25, FR-27, FR-29), against a real backend:
// calculator rules with the impact check, publish and restore; escalation rules; bot tuning's locked sections;
// knowledge base entries with history, removal and restore; who may open which editor.
// Needs the same setup as admin.spec.js (ADMIN_E2E_EMAIL, ADMIN_E2E_PASSWORD, BASE_URL on the same origin).
// Every test puts the live configuration back as it was, so a shared test backend is left unchanged.
const { test, expect } = require('@playwright/test')

const ADMIN = { email: process.env.ADMIN_E2E_EMAIL, password: process.env.ADMIN_E2E_PASSWORD }
const run = Date.now().toString(36)
const API = { headers: { 'X-Requested-With': 'xo-admin' } }

test.skip(!ADMIN.email || !ADMIN.password, 'set ADMIN_E2E_EMAIL and ADMIN_E2E_PASSWORD to run the admin tests')
test.describe.configure({ mode: 'serial' })
test.beforeEach(({}, info) => test.skip(info.project.name !== 'desktop', 'desktop flows'))

async function signIn(page, { email, password }) {
  await page.goto('/admin')
  await page.getByLabel('Work email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: /^Good (morning|afternoon|evening),/, level: 1 })).toBeVisible()
}

async function publish(page, note) {
  await page.getByRole('region', { name: 'Unpublished changes' }).getByRole('button', { name: 'Review & publish' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('What changed and why').fill(note)
  await dialog.getByRole('button', { name: 'Publish' }).click()
  await expect(page.getByRole('status').filter({ hasText: /Published version \d+/ })).toBeVisible()
}

async function restoreBuiltIn(page) {
  await page.getByRole('button', { name: 'History' }).click()
  const drawer = page.getByRole('dialog', { name: 'Version history' })
  await drawer.getByRole('listitem').filter({ hasText: 'v0' }).getByRole('button', { name: 'Restore' }).click()
  await page.getByRole('dialog', { name: 'Restore version 0?' }).getByRole('button', { name: 'Restore' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Version 0 restored' })).toBeVisible()
}

test('calculator rules: impact check, publish, live in the calculator, restore', async ({ page }) => {
  await signIn(page, ADMIN)
  await page.goto('/admin#/rules')
  const rate = page.getByLabel('Benchmark rate')
  const original = await rate.inputValue()
  await rate.fill('4.2')
  await page.getByRole('button', { name: 'Check impact' }).click()
  await expect(page.getByText(/\d+ of \d+ cases change/)).toBeVisible()
  await publish(page, `Benchmark review ${run}`)

  const emi = await (await page.request.post('/api/mortgage/emi', { data: { property_price: 1500000 } })).json()
  expect(JSON.stringify(emi)).toContain('4.2')

  await restoreBuiltIn(page)
  await expect(page.getByLabel('Benchmark rate')).toHaveValue(original)
  const activity = await (await page.request.get('/api/admin/activity?limit=20', API)).json()
  expect(activity.map((e) => e.action)).toEqual(expect.arrayContaining(['config_published', 'config_rolled_back']))
})

test('escalation rules: a keyword rule goes live, the visitor-request rule stays on', async ({ page }) => {
  await signIn(page, ADMIN)
  await page.goto('/admin#/escalation')
  await expect(page.getByRole('switch', { name: /The visitor asks for a person/ })).toBeDisabled()
  const card = page.locator('.xa-rulecard', { has: page.getByRole('heading', { name: 'Sensitive words' }) })
  await card.locator('.xa-switch i').click()
  const words = page.getByLabel('Words and phrases')
  await words.fill(`complaint${run}`)
  await words.press('Enter')
  await publish(page, `Complaints go to support ${run}`)
  const live = await (await page.request.get('/api/admin/config/escalation', API)).json()
  expect(live.published.data.rules.find((r) => r.type === 'keywords').keywords).toContain(`complaint${run}`)
  await restoreBuiltIn(page)
})

test('bot tuning: required sections are locked, a banned topic can be drafted and discarded', async ({ page }) => {
  await signIn(page, ADMIN)
  await page.goto('/admin#/tuning')
  await expect(page.getByText('Truthfulness (critical)')).toBeVisible()
  await expect(page.locator('.xa-lock').first()).toContainText('Locked by the PRD')
  await page.getByRole('tab', { name: 'Banned topics' }).click()
  await page.getByRole('button', { name: 'Add a topic' }).click()
  await page.getByLabel('Topic').fill(`Crypto ${run}`)
  await expect(page.getByRole('region', { name: 'Unpublished changes' })).toContainText('Draft saved', { timeout: 10000 })
  await page.getByRole('region', { name: 'Unpublished changes' }).getByRole('button', { name: 'Discard' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Draft discarded.' })).toBeVisible()
})

test('knowledge base: write an entry, remove it, restore it', async ({ page }) => {
  test.setTimeout(90_000)
  await signIn(page, ADMIN)
  await page.goto('/admin#/knowledge')
  await expect(page.getByRole('radio', { name: /Live/ })).toBeVisible()
  await page.getByRole('button', { name: 'New entry' }).click()
  await page.getByLabel('Title').fill(`What is Oqood? ${run}`)
  await page.getByLabel('Short answer').fill('Oqood is the Dubai Land Department register for off-plan property sales.')
  await page.getByRole('region', { name: 'Unpublished changes' }).getByRole('button', { name: 'Publish' }).click()
  const history = page.locator('.xa-history')
  await expect(history.getByText('New entry')).toBeVisible({ timeout: 30_000 })

  await page.getByRole('button', { name: 'Remove from XO' }).click()
  await page.getByRole('dialog', { name: 'Remove this entry from XO?' }).getByRole('button', { name: 'Remove' }).click()
  await expect(page.getByText('XO does not use this entry.')).toBeVisible()
  await history.getByRole('listitem').filter({ hasText: 'Published' }).getByRole('button', { name: 'Restore' }).click()
  await page.getByRole('dialog', { name: 'Restore version 1?' }).getByRole('button', { name: 'Restore' }).click()
  await expect(history.getByText('Restored', { exact: true })).toBeVisible()
  await expect(page.getByText('Live: XO answers from it')).toBeVisible()

  // Tidy up: remove it again so the shared backend keeps only real content.
  await page.getByRole('button', { name: 'Remove from XO' }).click()
  await page.getByRole('dialog', { name: 'Remove this entry from XO?' }).getByRole('button', { name: 'Remove' }).click()
  await expect(page.getByText('XO does not use this entry.')).toBeVisible()
})

test('a content editor edits knowledge but cannot open rules or tuning', async ({ page, browser }) => {
  await signIn(page, ADMIN)
  await page.goto('/admin#/users')
  await page.getByRole('button', { name: 'Add person' }).click()
  const dialog = page.getByRole('dialog', { name: 'Add a person' })
  await dialog.getByLabel('Full name').fill(`Writer ${run}`)
  await dialog.getByLabel('Work email').fill(`writer-${run}@xoto.ae`)
  await dialog.getByLabel('Role').selectOption({ label: 'Content editor' })
  const password = await dialog.getByLabel('Temporary password').inputValue()
  await dialog.getByRole('button', { name: 'Add person' }).click()

  const editor = await browser.newPage()
  await signIn(editor, { email: `writer-${run}@xoto.ae`, password })
  await editor.goto('/admin#/knowledge')
  await expect(editor.getByRole('heading', { name: 'Knowledge base', level: 1 })).toBeVisible()
  for (const page_ of ['rules', 'tuning', 'escalation']) {
    await editor.goto(`/admin#/${page_}`)
    await expect(editor.getByRole('heading', { name: /^Good (morning|afternoon|evening),/, level: 1 })).toBeVisible()
  }
  expect((await editor.request.put('/api/admin/config/mortgage_rules/draft', { ...API, data: { data: {}, base_version: 0 } })).status()).toBe(403)
  await editor.close()
})
