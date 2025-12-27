import { test, expect } from '@playwright/test'
import { env } from './helpers/env.js'
import {
    createDbClient,
    getFirstTeam,
    ensureJournalistUser,
    getJournalistAssignments,
    clearJournalistAssignments
} from './helpers/db.js'
import { loginWithCode, setAdminKey } from './helpers/auth.js'

let dbClient
let team
let journalistUser

test.describe.serial('Journalist coverage assignment workflows', () => {
    test.beforeAll(async () => {
        if (!env.adminKey) {
            throw new Error('ADMIN_API_KEY is required for coverage assignment E2E tests')
        }

        dbClient = createDbClient()
        await dbClient.connect()
        team = await getFirstTeam(dbClient)

        // Create or get test journalist user
        journalistUser = await ensureJournalistUser(dbClient, env.journalistEmail, {
            displayName: 'E2E Coverage Test Journalist'
        })

        // Clear any existing assignments for clean test state
        await clearJournalistAssignments(dbClient, journalistUser.id)
    })

    test.afterAll(async () => {
        if (dbClient) {
            // Clean up test assignments
            if (journalistUser?.id) {
                await clearJournalistAssignments(dbClient, journalistUser.id)
            }
            await dbClient.end()
        }
    })

    test('admin can see Edit Coverage button on journalist card', async ({ page }) => {
        await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
        await setAdminKey(page, env.adminKey)

        await page.goto('/admin/users')
        await expect(page.getByRole('heading', { name: 'Users' })).toBeVisible()

        // Search for the journalist
        const searchInput = page.getByPlaceholder('Search users...')
        await searchInput.fill(env.journalistEmail)

        // Find the journalist card and verify Edit Coverage button is visible
        const journalistCard = page.locator('[class*="Card"]').filter({ hasText: env.journalistEmail })
        await expect(journalistCard).toBeVisible()

        const editCoverageButton = journalistCard.getByRole('button', { name: /Edit Coverage/i })
        await expect(editCoverageButton).toBeVisible()
    })

    test('admin can open coverage dialog and see two tabs', async ({ page }) => {
        await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
        await setAdminKey(page, env.adminKey)

        await page.goto('/admin/users')

        // Search for the journalist
        const searchInput = page.getByPlaceholder('Search users...')
        await searchInput.fill(env.journalistEmail)

        // Click Edit Coverage button
        const journalistCard = page.locator('[class*="Card"]').filter({ hasText: env.journalistEmail })
        await journalistCard.getByRole('button', { name: /Edit Coverage/i }).click()

        // Verify dialog opened with correct title
        await expect(page.getByRole('dialog')).toBeVisible()
        await expect(page.getByRole('heading', { name: /Edit Coverage:/i })).toBeVisible()

        // Verify both tabs are present
        const parentClubsTab = page.getByRole('tab', { name: /Parent Clubs/i })
        const loanTeamsTab = page.getByRole('tab', { name: /Loan Teams/i })

        await expect(parentClubsTab).toBeVisible()
        await expect(loanTeamsTab).toBeVisible()

        // Verify Parent Clubs tab is active by default (has info box)
        await expect(page.getByText(/Outgoing Loans Coverage/i)).toBeVisible()
        await expect(page.getByText(/all players loaned out from/i)).toBeVisible()
    })

    test('admin can switch to Loan Teams tab', async ({ page }) => {
        await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
        await setAdminKey(page, env.adminKey)

        await page.goto('/admin/users')

        // Search and open dialog
        const searchInput = page.getByPlaceholder('Search users...')
        await searchInput.fill(env.journalistEmail)

        const journalistCard = page.locator('[class*="Card"]').filter({ hasText: env.journalistEmail })
        await journalistCard.getByRole('button', { name: /Edit Coverage/i }).click()

        // Click Loan Teams tab
        const loanTeamsTab = page.getByRole('tab', { name: /Loan Teams/i })
        await loanTeamsTab.click()

        // Verify Loan Teams content is visible
        await expect(page.getByText(/Incoming Loans Coverage/i)).toBeVisible()
        await expect(page.getByText(/all players currently on loan at/i)).toBeVisible()
        await expect(page.getByPlaceholder(/Enter team name/i)).toBeVisible()
    })

    test('admin can add a custom loan team', async ({ page }) => {
        await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
        await setAdminKey(page, env.adminKey)

        await page.goto('/admin/users')

        // Search and open dialog
        const searchInput = page.getByPlaceholder('Search users...')
        await searchInput.fill(env.journalistEmail)

        const journalistCard = page.locator('[class*="Card"]').filter({ hasText: env.journalistEmail })
        await journalistCard.getByRole('button', { name: /Edit Coverage/i }).click()

        // Switch to Loan Teams tab
        await page.getByRole('tab', { name: /Loan Teams/i }).click()

        // Add a custom loan team
        const customTeamName = `E2E Custom Team ${Date.now()}`
        const loanTeamInput = page.getByPlaceholder(/Enter team name/i)
        await loanTeamInput.fill(customTeamName)

        // Click the add button (Plus icon)
        await page.getByRole('button', { name: '' }).filter({ has: page.locator('svg') }).first().click()

        // Verify the team badge appears with (custom) label
        await expect(page.getByText(customTeamName)).toBeVisible()
        await expect(page.getByText('(custom)')).toBeVisible()
    })

    test('admin can save coverage assignments', async ({ page }) => {
        // Clear assignments first
        await clearJournalistAssignments(dbClient, journalistUser.id)

        await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
        await setAdminKey(page, env.adminKey)

        await page.goto('/admin/users')

        // Search and open dialog
        const searchInput = page.getByPlaceholder('Search users...')
        await searchInput.fill(env.journalistEmail)

        const journalistCard = page.locator('[class*="Card"]').filter({ hasText: env.journalistEmail })
        await journalistCard.getByRole('button', { name: /Edit Coverage/i }).click()

        // Wait for dialog to load assignments
        await expect(page.getByRole('dialog')).toBeVisible()
        await page.waitForTimeout(1000) // Wait for assignments to load

        // Switch to Loan Teams tab and add a custom team
        await page.getByRole('tab', { name: /Loan Teams/i }).click()

        const customTeamName = `E2E Save Test ${Date.now()}`
        await page.getByPlaceholder(/Enter team name/i).fill(customTeamName)
        await page.locator('button').filter({ has: page.locator('svg.lucide-plus') }).click()

        // Save
        await page.getByRole('button', { name: /Save Coverage/i }).click()

        // Dialog should close
        await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 5000 })

        // Verify in database
        const assignments = await getJournalistAssignments(dbClient, journalistUser.id)
        expect(assignments.loanTeams.some(lt => lt.loan_team_name === customTeamName)).toBe(true)
    })

    test('assignments persist after dialog reopened', async ({ page }) => {
        // Set up known assignments
        await clearJournalistAssignments(dbClient, journalistUser.id)

        // Add a known loan team assignment directly to DB
        const testTeamName = `Persist Test Team ${Date.now()}`
        await dbClient.query(
            `INSERT INTO journalist_loan_team_assignments (user_id, loan_team_name, assigned_at)
       VALUES ($1, $2, NOW())`,
            [journalistUser.id, testTeamName]
        )

        await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
        await setAdminKey(page, env.adminKey)

        await page.goto('/admin/users')

        // Search and open dialog
        const searchInput = page.getByPlaceholder('Search users...')
        await searchInput.fill(env.journalistEmail)

        const journalistCard = page.locator('[class*="Card"]').filter({ hasText: env.journalistEmail })
        await journalistCard.getByRole('button', { name: /Edit Coverage/i }).click()

        // Wait for dialog and switch to Loan Teams tab
        await expect(page.getByRole('dialog')).toBeVisible()
        await page.getByRole('tab', { name: /Loan Teams/i }).click()

        // Verify the pre-existing assignment is shown
        await expect(page.getByText(testTeamName)).toBeVisible()
    })
})
