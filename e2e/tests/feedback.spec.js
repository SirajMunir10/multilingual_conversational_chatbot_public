// Thumbs up/down on XO replies (PRD FR-26): shown only on finished replies that have an id, one tap rates,
// tapping again removes it, the rating survives a reload, a failed save is undone, labels follow the language.
const { test, expect } = require('@playwright/test')
const { openApp, send } = require('./support/mock')

test('rate a reply, change it, remove it', async ({ page }) => {
  const log = await openApp(page)
  await expect(page.locator('.message-wrapper.assistant').first().locator('.rating-btn')).toHaveCount(0) // greeting
  const reply = await send(page, 'please rate this answer')
  const up = reply.getByRole('button', { name: 'Helpful', exact: true })
  const down = reply.getByRole('button', { name: 'Not helpful' })
  await expect(up).toHaveAttribute('aria-pressed', 'false')

  await up.click()
  await expect(up).toHaveAttribute('aria-pressed', 'true')
  await expect(reply.getByRole('status')).toHaveText('Thanks for the feedback')
  await expect.poll(() => log.feedback.at(-1)).toMatchObject({ session_id: 'sess_test', rating: 'up' })
  expect(log.feedback.at(-1).turn_id).toMatch(/^[0-9a-f]{16}$/)

  await down.click()
  await expect(down).toHaveAttribute('aria-pressed', 'true')
  await expect(up).toHaveAttribute('aria-pressed', 'false')
  await expect.poll(() => log.feedback.at(-1).rating).toBe('down')

  await down.click()
  await expect(down).toHaveAttribute('aria-pressed', 'false')
  await expect(reply.getByRole('status')).toHaveText('')
  await expect.poll(() => log.feedback.at(-1).rating).toBe(null)

  // Replies without an id (older saved chats, errors) never show thumbs.
  const plain = await send(page, 'hello there')
  await expect(plain.locator('.rating-btn')).toHaveCount(0)
})

test('the rating is kept after a reload', async ({ page }) => {
  await openApp(page)
  const reply = await send(page, 'rate me please')
  await reply.getByRole('button', { name: 'Not helpful' }).click()
  await page.reload()
  await page.locator('.xo-widget').waitFor()
  const again = page.locator('.message-wrapper.assistant').last()
  await expect(again.getByRole('button', { name: 'Not helpful' })).toHaveAttribute('aria-pressed', 'true')
})

test('a rating the server could not save is undone', async ({ page }) => {
  const log = await openApp(page)
  const reply = await send(page, 'rate-fail this one')
  const up = reply.getByRole('button', { name: 'Helpful', exact: true })
  await up.click()
  await expect.poll(() => log.feedback.length).toBe(1)
  await expect(up).toHaveAttribute('aria-pressed', 'false')
})

test('labels follow the conversation language and keyboard works', async ({ page }) => {
  await openApp(page)
  const reply = await send(page, 'arabic, rate please')
  const up = reply.getByRole('button', { name: 'مفيد', exact: true })
  await expect(up).toBeVisible()
  await expect(reply.getByRole('button', { name: 'غير مفيد' })).toBeVisible()
  await up.focus()
  await page.keyboard.press('Enter')
  await expect(up).toHaveAttribute('aria-pressed', 'true')
  await expect(reply.getByRole('status')).toHaveText('شكرًا على ملاحظتك')
})
