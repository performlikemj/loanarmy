/**
 * Build query params for fetching team loans for the writer editor.
 * Ensures we pull the current season and include supplemental/manual rows.
 * @param {Date} now
 * @returns {{active_only: string, dedupe: string, include_supplemental: string}}
 */
export function buildLoanFetchParams() {
  return {
    active_only: 'true',
    dedupe: 'true',
    include_supplemental: 'true',
  }
}
