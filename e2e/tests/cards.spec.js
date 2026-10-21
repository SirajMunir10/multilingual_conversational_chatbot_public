// Rich cards: property results, mortgage results (eligibility / affordability / EMI) and the advisor review card.
const { test, expect } = require('@playwright/test')
const { openApp, send } = require('./support/mock')

test.describe('property cards', () => {
  test('show badges, prices and actions; expand to details', async ({ page }) => {
    const log = await openApp(page)
    const reply = await send(page, 'show me properties in marina')
    await expect(reply.locator('.md strong')).toHaveText('3 homes')
    const cards = reply.locator('.prop-card')
    await expect(cards).toHaveCount(3)
    await expect(cards.nth(0).locator('.source-badge')).toHaveText('Live off-plan')
    await expect(cards.nth(0).locator('.status-chip')).toHaveText('Off-plan')
    await expect(cards.nth(0).locator('.prop-compact-price')).toHaveText('From AED 703,000')
    await expect(cards.nth(1).locator('.source-badge')).toHaveText('Sample listing')
    await expect(cards.nth(1).locator('.status-chip')).toHaveText('Ready')
    await expect(cards.nth(1).locator('.prop-compact-price')).toHaveText('AED 1,350,000')
    await expect(cards.nth(2).locator('.prop-compact-beds')).toHaveText('2 BR')
    await expect(cards.nth(0).locator('.prop-ref-badge')).toHaveText('#1')

    await cards.nth(1).locator('.prop-compact-bar').click()
    const drawer = cards.nth(1).locator('.prop-expanded-drawer')
    await expect(drawer).toBeVisible()
    await expect(drawer.locator('.prop-mortgage-banner')).toBeVisible()
    await drawer.locator('.btn-card-action').click()
    await expect.poll(() => log.chat.at(-1)?.message).toBe('What would the monthly payment be on #2?')

    await page.locator('.prop-card').nth(0).locator('.prop-icon-btn').first().click()
    await expect.poll(() => log.chat.at(-1)?.message).toBe('Save #1 to my shortlist')
  })
})

test.describe('mortgage cards', () => {
  test('eligibility: verdict, shortfall, checks, limits and cash needed upfront', async ({ page }) => {
    await openApp(page)
    const reply = await send(page, 'am I eligible for 2.5M')
    const card = reply.locator('.mortgage-card')
    await expect(card.locator('.calc-title')).toHaveText('Mortgage eligibility')
    await expect(card.locator('.verdict-badge')).toHaveText('Eligible for a lower amount')
    await expect(card.locator('.spotlight-value')).toHaveText('AED 2,000,000')
    await expect(card.locator('.shortfall')).toContainText('AED 250,000')
    await card.locator('.btn-toggle-mortgage-card').click()
    await expect(card.locator('.gate-chip')).toHaveCount(3)
    await expect(card.locator('.gate-chip.pass')).toHaveCount(3)
    await expect(card.locator('.cost-row.tightest')).toContainText('Loan-to-value')
    await expect(card.locator('.breakdown-section')).toContainText('Cash needed upfront')
    await expect(card.locator('.dbr-badge')).toContainText('/ 50%')
  })

  test('affordability: can-borrow card and "show properties" action', async ({ page }) => {
    const log = await openApp(page)
    const reply = await send(page, 'how much can I borrow')
    const card = reply.locator('.mortgage-card')
    await expect(card.locator('.calc-title')).toHaveText('Affordability estimate')
    await expect(card.locator('.verdict-badge')).toHaveCount(0)
    await expect(card.locator('.spotlight-value')).toContainText('AED 2,')
    await card.locator('.btn-jump-properties').click()
    await expect.poll(() => log.chat.at(-1)?.message).toMatch(/^Show me properties up to AED [\d,]+$/)
  })

  test('EMI: monthly payment and amortisation table', async ({ page }) => {
    await openApp(page)
    const reply = await send(page, 'monthly payment on 1.5M')
    const card = reply.locator('.mortgage-card')
    await expect(card.locator('.calc-title')).toHaveText('Monthly payment estimate')
    await expect(card.locator('.spotlight-value')).toHaveText('AED 6,202')
    await card.locator('.btn-toggle-mortgage-card').click()
    await expect(card.locator('.amort-table tbody tr')).toHaveCount(5)
  })
})

test.describe('advisor review card', () => {
  test('review → edit → invalid number → fix → saved, and it survives a reload', async ({ page }) => {
    const log = await openApp(page)
    const reply = await send(page, 'I want an advisor')
    const card = reply.locator('.handoff-card')
    await expect(card.locator('.hc-title strong')).toHaveText('Check your callback details')
    await expect(card.locator('.hc-rows')).toContainText('+971 50 123 4567')
    await expect(card.locator('.hc-btn')).toHaveText(['Edit', 'Confirm'])

    await card.locator('.hc-btn.ghost').click()
    await card.locator('input[type="tel"]').fill('+0884 1234')
    await card.locator('.hc-btn.primary').click()
    await expect(card.locator('.hc-error')).toHaveText('Enter a valid mobile number with country code, e.g. +971 50 123 4567.')

    await card.locator('input[type="tel"]').fill('+971 52 555 0101')
    await card.locator('select').nth(0).selectOption('ar')
    await card.locator('select').nth(1).selectOption('sales')
    await card.locator('.hc-btn.primary').click()
    await expect(card.locator('.hc-title strong')).toHaveText('Callback request saved')
    await expect(card.locator('.hc-title small')).toContainText('XO-261019-ABC123')
    expect(log.confirm.at(-1)).toMatchObject({ session_id: 'sess_test', draft_id: 'draft-1', phone: '+971 52 555 0101', preferred_language: 'ar', team: 'sales' })

    await page.reload()
    await page.locator('.xo-widget').waitFor()
    await expect(page.locator('.handoff-card.is-saved')).toHaveCount(1)
  })

  test('a newer request replaces an unconfirmed card', async ({ page }) => {
    await openApp(page)
    await send(page, 'I want an advisor')
    await send(page, 'advisor again please')
    const cards = page.locator('.handoff-card')
    await expect(cards).toHaveCount(2)
    await expect(cards.nth(0)).toHaveClass(/is-expired/)
    await expect(cards.nth(0).locator('.hc-note')).toHaveText('These details were replaced by a newer request.')
    await expect(cards.nth(0).locator('.hc-btn')).toHaveCount(0)
    await expect(cards.nth(1).locator('.hc-btn')).toHaveCount(2)
  })

  test('the header advisor button sends the advisor request', async ({ page }) => {
    const log = await openApp(page)
    await page.locator('.advisor-btn').click()
    await expect.poll(() => log.chat.at(-1)?.message).toBeTruthy()
    await expect(page.locator('.handoff-card')).toHaveCount(1)
  })
})
