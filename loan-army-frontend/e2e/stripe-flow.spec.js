import { test, expect } from '@playwright/test'
import { env } from './helpers/env.js'
import { createDbClient, waitForEmailToken, getFirstTeam, createLoginToken, waitForStripeAccount, markStripeOnboardingComplete } from './helpers/db.js'
import { inviteJournalist, assignJournalistTeams, verifyLoginCode } from './helpers/api.js'
import { loginWithCode } from './helpers/auth.js'
import { completeStripeOnboarding, completeStripeCheckout } from './helpers/stripe.js'

let dbClient
let team
let journalistId
let adminToken

test.describe.serial('Stripe journalist + subscriber flow', () => {
  test.beforeAll(async () => {
    if (!env.adminKey) {
      throw new Error('ADMIN_API_KEY is required for Stripe E2E tests')
    }

    dbClient = createDbClient()
    await dbClient.connect()

    team = await getFirstTeam(dbClient)

    const adminCode = await createLoginToken(dbClient, env.adminEmail)
    const adminAuth = await verifyLoginCode(env.adminEmail, adminCode)
    adminToken = adminAuth?.token
    if (!adminToken) {
      throw new Error('Failed to resolve admin bearer token for Stripe setup')
    }

    const invite = await inviteJournalist(env.journalistEmail, { adminKey: env.adminKey, token: adminToken })
    journalistId = invite?.user?.id
    if (!journalistId) {
      throw new Error('Failed to create journalist user for Stripe tests')
    }

    await assignJournalistTeams(journalistId, [team.team_id], { adminKey: env.adminKey, token: adminToken })
  })

  test.afterAll(async () => {
    if (dbClient) {
      await dbClient.end()
    }
  })

  test('journalist completes onboarding and sets price', async ({ page }) => {
    await loginWithCode(page, env.journalistEmail, dbClient, { displayName: 'E2E Journalist' })

    await page.goto('/journalist/stripe-setup')

    if (await page.getByRole('button', { name: /Create Stripe Account/i }).isVisible().catch(() => false)) {
      await page.getByRole('button', { name: /Create Stripe Account/i }).click()
      await completeStripeOnboarding(page, { email: env.journalistEmail })
    }

    await waitForStripeAccount(dbClient, journalistId)
    await markStripeOnboardingComplete(dbClient, journalistId)

    await page.goto('/journalist/pricing')
    await page.getByLabel('Monthly Subscription Price (USD)').fill('9.99')
    await page.getByRole('button', { name: /Set Price|Update Price/i }).click()

    await expect(page.getByText(/Subscription price .*successfully/i)).toBeVisible()
  })

  test('subscriber completes Stripe checkout', async ({ page }) => {
    await loginWithCode(page, env.userEmail, dbClient, { displayName: 'E2E Subscriber' })

    await page.goto(`/journalists/${journalistId}`)

    const subscribeButton = page.getByRole('button', { name: /Subscribe Now/i })
    await expect(subscribeButton).toBeVisible()
    await subscribeButton.click()

    await completeStripeCheckout(page, { email: env.userEmail })

    await expect(page).toHaveURL(/settings/)
    await expect(page.getByText(/Premium Subscriptions/i)).toBeVisible()
  })
})
