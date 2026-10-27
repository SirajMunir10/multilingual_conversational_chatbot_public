// Admin insights end to end (PRD FR-26, FR-31, §7), against a real backend with the real model:
// a visitor chats and rates a reply "not helpful" in the widget → it appears in analytics, the conversation list and the
// review queue → a trainer-level admin reviews it and saves a corrected answer as a knowledge draft → an analyst
// sees personal data masked and no review controls → the monthly budget alert.
// Needs the same setup as admin.spec.js (ADMIN_E2E_EMAIL, ADMIN_E2E_PASSWORD, BASE_URL on the same origin).
const { test, expect } = require('@playwright/test')

const ADMIN = { email: process.env.ADMIN_E2E_EMAIL, password: process.env.ADMIN_E2E_PASSWORD }
const run = Date.now().toString(36)
const QUESTION = `Can a non-resident get a mortgage in Dubai? My number is +971 50 765 4321 (test ${run})`

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

test('a visitor rates a reply as not helpful in the widget', async ({ page }) => {
  test.setTimeout(120_000)
  await page.goto('/')
  await page.locator('#chat-text-input').fill(QUESTION)
  await page.locator('#chat-text-input').press('Enter')
  const reply = page.locator('.message-wrapper.assistant').last()
  await expect(reply.getByRole('button', { name: 'Not helpful' })).toBeVisible({ timeout: 90_000 })
  const saved = page.waitForResponse((r) => r.url().includes('/api/chat/feedback') && r.status() === 200)
  await reply.getByRole('button', { name: 'Not helpful' }).click()
  await saved
})

test('the conversation shows in analytics, the list and the review queue; it can be reviewed', async ({ page }) => {
  await signIn(page, ADMIN)
  await page.goto('/admin#/analytics')
  await expect(page.locator('.xa-stat').filter({ hasText: 'Conversations' }).locator('.xa-stat-value')).not.toHaveText('0')
  await expect(page.locator('.xa-stat').filter({ hasText: 'Satisfaction' })).toContainText(/[1-9]\d* not helpful/)

  await page.goto('/admin#/conversations')
  await page.getByLabel('Search messages').fill(run)
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await expect(page.getByRole('heading', { name: '1 conversation' })).toBeVisible()
  const row = page.getByRole('row').filter({ hasText: run })
  await expect(row.locator('.xa-badge-bad')).toHaveText('1')
  await expect(row).toContainText('+971 50 765 4321') // admins may see personal data

  await page.getByRole('tab', { name: 'Review queue' }).click()
  const item = page.locator('.xa-queue li').filter({ hasText: run })
  await expect(item).toContainText('Visitor: not helpful')
  await item.getByRole('button', { name: 'Open conversation' }).click()

  const turn = page.locator('.xa-turn-assistant').first()
  await expect(turn).toContainText('Visitor: not helpful')
  await turn.getByRole('radio', { name: 'Bad' }).click()
  await turn.getByLabel('Flag for review').check()
  await turn.getByLabel('Note on this reply').fill(`Should mention the 50% loan-to-value rule (${run})`)
  await turn.getByRole('button', { name: 'Save review' }).click()
  await expect(turn.getByText('Saved')).toBeVisible()

  await turn.getByRole('button', { name: 'Save as knowledge draft' }).click()
  const dialog = page.getByRole('dialog', { name: 'Save as knowledge draft' })
  await expect(dialog.getByLabel('Question')).toHaveValue(QUESTION)
  await dialog.getByLabel('Title').fill(`Non-resident mortgages ${run}`)
  await dialog.getByLabel('Correct answer').fill('Yes. Non-residents can usually borrow up to 50% of the property value; some banks go up to 65%.')
  await dialog.getByRole('button', { name: 'Save draft' }).click()
  await expect(page.getByText(`Saved “Non-resident mortgages ${run}” as a knowledge draft`)).toBeVisible()

  await page.getByRole('button', { name: 'All conversations' }).click()
  await page.getByRole('tab', { name: 'Knowledge drafts' }).click()
  await expect(page.locator('.xa-queue li').filter({ hasText: `Non-resident mortgages ${run}` })).toContainText('Draft')
  await page.getByRole('tab', { name: 'Review queue' }).click()
  await expect(page.locator('.xa-queue li').filter({ hasText: run })).toContainText('Marked bad')

  const activity = await (await page.request.get('/api/admin/activity?limit=50', { headers: { 'X-Requested-With': 'xo-admin' } })).json()
  expect(activity.map((e) => e.action)).toEqual(expect.arrayContaining(['reply_reviewed', 'kb_draft_created']))
})

test('an analyst sees personal data masked and cannot review', async ({ page, browser }) => {
  await signIn(page, ADMIN)
  await page.goto('/admin#/users')
  await page.getByRole('button', { name: 'Add person' }).click()
  const dialog = page.getByRole('dialog', { name: 'Add a person' })
  await dialog.getByLabel('Full name').fill(`Analyst ${run}`)
  await dialog.getByLabel('Work email').fill(`analyst-${run}@xoto.ae`)
  await dialog.getByLabel('Role').selectOption({ label: 'Read-only analyst' })
  const password = await dialog.getByLabel('Temporary password').inputValue()
  await dialog.getByRole('button', { name: 'Add person' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'can now sign in' })).toBeVisible()

  const analyst = await browser.newPage()
  await signIn(analyst, { email: `analyst-${run}@xoto.ae`, password })
  await analyst.goto('/admin#/conversations')
  await expect(analyst.getByRole('tab', { name: 'Knowledge drafts' })).toHaveCount(0)
  await analyst.getByLabel('Search messages').fill(run)
  await analyst.getByRole('button', { name: 'Search', exact: true }).click()
  const row = analyst.getByRole('row').filter({ hasText: run })
  await expect(row).toContainText('•••321')
  await expect(row).not.toContainText('765 4321')
  await row.getByRole('link').click()
  await expect(analyst.getByText('Phone numbers and emails are hidden for your role.')).toBeVisible()
  await expect(analyst.getByRole('button', { name: 'Save review' })).toHaveCount(0)
  await expect(analyst.locator('.xa-turn-assistant').first()).toContainText('Marked bad') // sees the review, read-only
  await analyst.goto('/admin#/analytics')
  await expect(analyst.getByRole('button', { name: /budget/i })).toHaveCount(0)
  await analyst.close()
})

test('the monthly budget alert', async ({ page }) => {
  await signIn(page, ADMIN)
  await page.goto('/admin#/analytics')
  await page.getByRole('button', { name: /Set a budget|Change budget/ }).click()
  const dialog = page.getByRole('dialog', { name: 'Monthly AI budget' })
  await dialog.getByLabel('Budget per month (USD)').fill('0.000001')
  await dialog.getByLabel('Alert when spending reaches (%)').fill('50')
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByRole('status').filter({ hasText: /AI spend this month is .* budget/ })).toBeVisible()
  await expect(page.getByText('Over the alert level')).toBeVisible()

  // Switch it off again so the shared test backend is left as it was.
  await page.getByRole('button', { name: 'Change budget' }).click()
  await dialog.getByLabel('Budget per month (USD)').fill('')
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByRole('button', { name: 'Set a budget' })).toBeVisible()
})
