// Admin module (PRD §5.6, FR-30) against a real backend: sign-in, roles decide what people see, user management,
// sessions end on role change, own password, activity trail, keyboard use and the phone drawer.
// Needs a backend with a first admin, served on the same origin as the frontend:
//   ADMIN_E2E_EMAIL=… ADMIN_E2E_PASSWORD=… BASE_URL=http://… npx playwright test admin
const { test, expect } = require('@playwright/test')

const ADMIN = { email: process.env.ADMIN_E2E_EMAIL, password: process.env.ADMIN_E2E_PASSWORD }
const run = Date.now().toString(36)

test.skip(!ADMIN.email || !ADMIN.password, 'set ADMIN_E2E_EMAIL and ADMIN_E2E_PASSWORD to run the admin tests')

async function signIn(page, { email, password }) {
  await page.goto('/admin')
  await page.getByLabel('Work email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: /^Good (morning|afternoon|evening),/, level: 1 })).toBeVisible()
}

async function addPerson(page, { name, email, role }) {
  await page.goto('/admin#/users')
  await page.getByRole('button', { name: 'Add person' }).click()
  const dialog = page.getByRole('dialog', { name: 'Add a person' })
  await dialog.getByLabel('Full name').fill(name)
  await dialog.getByLabel('Work email').fill(email)
  await dialog.getByLabel('Role').selectOption({ label: role })
  const password = await dialog.getByLabel('Temporary password').inputValue()
  await dialog.getByRole('button', { name: 'Add person' }).click()
  await expect(page.getByRole('status').filter({ hasText: `${name} can now sign in` })).toBeVisible()
  return { email, password }
}

test.describe('admin', () => {
  test.beforeEach(({}, info) => test.skip(info.project.name !== 'desktop', 'desktop flows; the phone drawer has its own test'))

  test('sign-in: wrong password is refused, then the overview loads', async ({ page }) => {
    await page.goto('/admin')
    await expect(page).toHaveTitle('XO Admin')
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
    await expect(page.getByText('Your session ended')).toHaveCount(0) // a first visit is not an ended session
    await page.getByLabel('Work email').fill(ADMIN.email)
    await page.getByLabel('Password', { exact: true }).fill('definitely not it')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('alert').filter({ hasText: 'do not match' })).toContainText('do not match an active account')
    await expect(page.getByLabel('Password', { exact: true })).toHaveValue('')

    await signIn(page, ADMIN)
    await expect(page.getByText('Signed in as Admin.')).toBeVisible()
    await expect(page.locator('.xa-facts')).toContainText(/PostgreSQL|Memory only/)
    const nav = page.getByRole('complementary', { name: 'Admin sections' })
    for (const ready of ['Analytics', 'Conversations', 'Knowledge base', 'Bot tuning', 'Escalation rules', 'Calculator rules', 'Users & roles']) {
      await expect(nav.getByRole('link', { name: new RegExp(ready) })).not.toContainText(/7[CD]/)
    }
    await expect(nav.getByRole('link', { name: /Integrations/ })).toContainText('7D')
  })

  test('roles decide what a person sees, and a role change signs them out', async ({ page, browser }) => {
    await signIn(page, ADMIN)
    const editor = await addPerson(page, { name: `Editor ${run}`, email: `editor-${run}@xoto.ae`, role: 'Content editor' })

    const other = await browser.newPage()
    await signIn(other, editor)
    await expect(other.getByText('Signed in as Content editor.')).toBeVisible()
    const nav = other.getByRole('complementary', { name: 'Admin sections' })
    await expect(nav.getByRole('link', { name: /Knowledge base/ })).toBeVisible()
    await expect(nav.getByRole('link', { name: /Users & roles/ })).toHaveCount(0)
    await expect(nav.getByRole('link', { name: /Calculator rules/ })).toHaveCount(0) // rules are for admins only
    await expect(nav.getByRole('link', { name: /Bot tuning/ })).toHaveCount(0) // tuning is for bot trainers and admins
    await expect(nav.getByRole('link', { name: /Activity log/ })).toHaveCount(0)
    await other.goto('/admin#/users')
    await expect(other.getByRole('heading', { name: /^Good (morning|afternoon|evening),/, level: 1 })).toBeVisible()

    // The admin changes the role; the editor's next request finds the session ended.
    await page.getByLabel(`Role for Editor ${run}`).selectOption({ label: 'Read-only analyst' })
    await expect(page.getByRole('status').filter({ hasText: 'is now Read-only analyst' })).toBeVisible()
    await other.goto('/admin#/account')
    await other.getByRole('link', { name: /Overview/ }).click() // the overview asks the server for status
    await expect(other.getByText('Your session ended. Please sign in again.')).toBeVisible()
    await signIn(other, editor)
    await expect(other.getByText('Signed in as Read-only analyst.')).toBeVisible()

    // Deactivation: the person cannot sign in any more.
    await page.getByRole('row', { name: new RegExp(`Editor ${run}`) }).getByRole('button', { name: 'Deactivate' }).click()
    await expect(page.getByRole('status').filter({ hasText: 'deactivated and signed out' })).toBeVisible()
    await other.goto('/admin')
    await expect(other.getByRole('button', { name: 'Sign in' })).toBeVisible()
    await other.getByLabel('Work email').fill(editor.email)
    await other.getByLabel('Password', { exact: true }).fill(editor.password)
    await other.getByRole('button', { name: 'Sign in' }).click()
    await expect(other.getByRole('alert').filter({ hasText: 'do not match' })).toContainText('do not match an active account')
    await other.close()

    // Every change is in the activity log with the person who made it.
    await page.goto('/admin#/activity')
    const rows = page.getByRole('row')
    await expect(rows.filter({ hasText: `user:editor-${run}@xoto.ae` }).filter({ hasText: 'Added a person' })).toHaveCount(1)
    await expect(rows.filter({ hasText: `user:editor-${run}@xoto.ae` }).filter({ hasText: 'role: content_editor → read_only_analyst' })).toHaveCount(1)
    await expect(rows.filter({ hasText: `user:editor-${run}@xoto.ae` }).filter({ hasText: 'active: true → false' })).toHaveCount(1)
  })

  test('the admin cannot remove their own access', async ({ page }) => {
    await signIn(page, ADMIN)
    await page.goto('/admin#/users')
    const me = page.getByRole('row').filter({ has: page.getByText('You', { exact: true }) })
    await expect(me.getByRole('combobox')).toBeDisabled()
    await expect(me.getByRole('button', { name: 'Deactivate' })).toHaveCount(0)
  })

  test('change own password, sign out, sign in with the new one', async ({ page }) => {
    await signIn(page, ADMIN)
    const person = await addPerson(page, { name: `Trainer ${run}`, email: `trainer-${run}@xoto.ae`, role: 'Bot trainer' })
    await page.getByRole('button', { name: 'Sign out' }).click()
    await expect(page.getByText('You have signed out.')).toBeVisible()

    await signIn(page, person)
    await page.getByRole('link', { name: /^My account/ }).click()
    await page.getByLabel('Current password').fill(person.password)
    await page.getByLabel('New password', { exact: true }).fill('a sentence I will remember')
    await page.getByLabel('Repeat new password').fill('a sentence I will not')
    await expect(page.getByText('The two passwords do not match.')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Change password' })).toBeDisabled()
    await page.getByLabel('Repeat new password').fill('a sentence I will remember')
    await page.getByRole('button', { name: 'Change password' }).click()
    await expect(page.getByText('Password changed.')).toBeVisible()

    await page.getByRole('button', { name: 'Sign out' }).click()
    await signIn(page, { email: person.email, password: 'a sentence I will remember' })
  })

  test('dialogs work from the keyboard', async ({ page }) => {
    await signIn(page, ADMIN)
    await page.goto('/admin#/users')
    const opener = page.getByRole('button', { name: 'Add person' })
    await opener.focus()
    await page.keyboard.press('Enter')
    const dialog = page.getByRole('dialog', { name: 'Add a person' })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByLabel('Full name')).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(opener).toBeFocused()
  })
})

test('phone: the sidebar opens as a drawer and closes after choosing a section', async ({ page }, info) => {
  test.skip(info.project.name !== 'android', 'phone layout')
  await signIn(page, ADMIN)
  const nav = page.getByRole('complementary', { name: 'Admin sections' })
  await expect(nav).not.toBeInViewport()
  await page.getByRole('button', { name: 'Open menu' }).click()
  await expect(nav).toBeInViewport()
  await nav.getByRole('link', { name: /Activity log/ }).click()
  await expect(page.getByRole('heading', { name: 'Activity log', level: 1 })).toBeVisible()
  await expect(nav).not.toBeInViewport()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(overflow).toBeLessThanOrEqual(0)
})
