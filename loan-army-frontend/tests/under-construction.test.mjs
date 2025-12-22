import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

test('app shows an under construction page with Go On Loan branding', async () => {
  const appSource = await fs.readFile(new URL('../src/App.jsx', import.meta.url), 'utf8')

  assert.match(
    appSource,
    /SITE_UNDER_CONSTRUCTION\s*=\s*true/,
    'SITE_UNDER_CONSTRUCTION should be enabled to route all traffic to the maintenance page'
  )
  assert.match(
    appSource,
    /function UnderConstructionPage\(/,
    'UnderConstructionPage component should exist'
  )
  assert.match(
    appSource,
    /We'\\?re Making Improvements/,
    'UnderConstructionPage should include the exact heading copy'
  )
  assert.match(
    appSource,
    /<img[^>]*src=\{BRAND_LOGO_SRC\}[^>]*alt="Go On Loan logo"/,
    'UnderConstructionPage should display the Go On Loan logo'
  )
})
