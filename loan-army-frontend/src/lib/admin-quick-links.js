export function getAdminQuickLinks() {
  return [
    { label: 'API Key', href: '#admin-api' },
    { label: 'Runs', href: '#admin-runs' },
    { label: 'Seed Top-5', href: '#admin-seed' },
    { label: 'Loans Manager', href: '#admin-loans' },
    { label: 'Newsletters', href: '#admin-newsletters' },
    { label: 'Sandbox checks', href: '/admin/sandbox', spa: true },
  ]
}
