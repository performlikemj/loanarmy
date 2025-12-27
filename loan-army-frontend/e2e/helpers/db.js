import pg from 'pg'
import crypto from 'crypto'

const { Client } = pg

function getDbConfig() {
  const hasLocal = process.env.DB_HOST && process.env.DB_USER && process.env.DB_NAME
  if (hasLocal) {
    return {
      host: process.env.DB_HOST,
      port: Number(process.env.DB_PORT || 5432),
      user: process.env.DB_USER,
      password: process.env.DB_PASSWORD,
      database: process.env.DB_NAME,
      ssl: process.env.DB_SSLMODE && process.env.DB_SSLMODE !== 'disable' ? { rejectUnauthorized: false } : false,
    }
  }

  if (process.env.SUPA_DB_HOST && process.env.SUPA_DB_USER && process.env.SUPA_DB_NAME) {
    return {
      host: process.env.SUPA_DB_HOST,
      port: Number(process.env.SUPA_DB_PORT || 5432),
      user: process.env.SUPA_DB_USER,
      password: process.env.SUPA_DB_PASSWORD,
      database: process.env.SUPA_DB_NAME,
      ssl: { rejectUnauthorized: false },
    }
  }

  throw new Error('Database configuration missing. Set DB_* or SUPA_DB_* env vars.')
}

export function createDbClient() {
  return new Client(getDbConfig())
}

export async function waitForEmailToken(client, email, purpose, { timeoutMs = 15000, intervalMs = 500 } = {}) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    const result = await client.query(
      `SELECT token
         FROM email_tokens
        WHERE email = $1
          AND purpose = $2
          AND used_at IS NULL
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY id DESC
        LIMIT 1`,
      [email, purpose]
    )
    if (result.rows.length) {
      return result.rows[0].token
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
  throw new Error(`Timed out waiting for ${purpose} token for ${email}`)
}

function generateLoginCode() {
  return crypto.randomBytes(8).toString('base64url').slice(0, 11)
}

export async function createLoginToken(client, email, { ttlMinutes = 5 } = {}) {
  const token = generateLoginCode()
  const result = await client.query(
    `INSERT INTO email_tokens
      (token, email, purpose, expires_at, metadata_json, created_at)
     VALUES (
      $1,
      $2,
      'login',
      NOW() + ($3::text || ' minutes')::interval,
      $4,
      NOW()
     )
     RETURNING token`,
    [token, email, ttlMinutes, JSON.stringify({ kind: 'otp', source: 'e2e' })]
  )
  return result.rows[0].token
}

export async function waitForStripeAccount(client, journalistUserId, { timeoutMs = 15000, intervalMs = 500 } = {}) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    const result = await client.query(
      `SELECT stripe_account_id FROM stripe_connected_accounts WHERE journalist_user_id = $1 ORDER BY id DESC LIMIT 1`,
      [journalistUserId]
    )
    if (result.rows.length) {
      return result.rows[0].stripe_account_id
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
  throw new Error(`Timed out waiting for Stripe account for journalist ${journalistUserId}`)
}

export async function markStripeOnboardingComplete(client, journalistUserId) {
  const result = await client.query(
    `UPDATE stripe_connected_accounts
        SET onboarding_complete = true,
            details_submitted = true,
            charges_enabled = true,
            payouts_enabled = true,
            updated_at = NOW()
      WHERE journalist_user_id = $1
      RETURNING stripe_account_id`,
    [journalistUserId]
  )
  return result.rows[0]
}

export async function getFirstTeam(client) {
  const result = await client.query(
    `SELECT id, name, team_id FROM teams ORDER BY id ASC LIMIT 1`
  )
  if (!result.rows.length) {
    throw new Error('No teams found in database')
  }
  return result.rows[0]
}

export async function insertEmptyNewsletter(client, teamId, { slugPrefix = 'e2e-empty' } = {}) {
  const slug = `${slugPrefix}-${Date.now()}`
  const title = `E2E Empty Newsletter ${new Date().toISOString()}`
  const content = ''
  const result = await client.query(
    `INSERT INTO newsletters
      (team_id, newsletter_type, title, content, structured_content, public_slug, generated_date, created_at, updated_at)
     VALUES ($1, 'weekly', $2, $3, NULL, $4, NOW(), NOW(), NOW())
     RETURNING id`,
    [teamId, title, content, slug]
  )
  return { id: result.rows[0].id, title, slug }
}

// --- Journalist/Coverage helpers ---

export async function ensureJournalistUser(client, email, { displayName = 'E2E Journalist' } = {}) {
  // Check if user exists
  let result = await client.query(
    `SELECT id, email, display_name, is_journalist FROM user_accounts WHERE email = $1`,
    [email]
  )

  if (result.rows.length) {
    const user = result.rows[0]
    // Ensure user is a journalist
    if (!user.is_journalist) {
      await client.query(
        `UPDATE user_accounts SET is_journalist = true, updated_at = NOW() WHERE id = $1`,
        [user.id]
      )
    }
    return { ...user, is_journalist: true }
  }

  // Create new journalist user
  result = await client.query(
    `INSERT INTO user_accounts (email, display_name, display_name_lower, is_journalist, created_at, updated_at)
     VALUES ($1, $2, $3, true, NOW(), NOW())
     RETURNING id, email, display_name, is_journalist`,
    [email, displayName, displayName.toLowerCase()]
  )
  return result.rows[0]
}

export async function getJournalistAssignments(client, userId) {
  const [parentResult, loanResult] = await Promise.all([
    client.query(
      `SELECT jta.id, jta.team_id, t.name as team_name
       FROM journalist_team_assignments jta
       JOIN teams t ON t.id = jta.team_id
       WHERE jta.user_id = $1`,
      [userId]
    ),
    client.query(
      `SELECT id, loan_team_id, loan_team_name
       FROM journalist_loan_team_assignments
       WHERE user_id = $1`,
      [userId]
    )
  ])

  return {
    parentClubs: parentResult.rows,
    loanTeams: loanResult.rows
  }
}

export async function clearJournalistAssignments(client, userId) {
  await Promise.all([
    client.query(`DELETE FROM journalist_team_assignments WHERE user_id = $1`, [userId]),
    client.query(`DELETE FROM journalist_loan_team_assignments WHERE user_id = $1`, [userId])
  ])
}

export async function addParentClubAssignment(client, userId, teamId) {
  const result = await client.query(
    `INSERT INTO journalist_team_assignments (user_id, team_id, assigned_at)
     VALUES ($1, $2, NOW())
     ON CONFLICT (user_id, team_id) DO NOTHING
     RETURNING id`,
    [userId, teamId]
  )
  return result.rows[0]
}

export async function addLoanTeamAssignment(client, userId, teamName, teamId = null) {
  const result = await client.query(
    `INSERT INTO journalist_loan_team_assignments (user_id, loan_team_id, loan_team_name, assigned_at)
     VALUES ($1, $2, $3, NOW())
     ON CONFLICT (user_id, loan_team_name) DO NOTHING
     RETURNING id`,
    [userId, teamId, teamName]
  )
  return result.rows[0]
}

