// Admin modules (PRD §5.6) and the permission each needs (FR-30). The server enforces permissions; this list
// only decides what a person sees. Modules still being built are shown as "Coming soon" with their sub-phase.
export const NAV_GROUPS = [
  {
    label: null,
    items: [{ id: 'overview', label: 'Overview', icon: 'home', permission: null }]
  },
  {
    label: 'Insights',
    items: [
      { id: 'analytics', label: 'Analytics', icon: 'chart', permission: 'analytics.view', prd: 'FR-31' },
      { id: 'conversations', label: 'Conversations', icon: 'chat', permission: 'conversations.view', prd: 'FR-26' }
    ]
  },
  {
    label: 'Content',
    items: [
      { id: 'knowledge', label: 'Knowledge base', icon: 'book', permission: 'kb.edit', prd: 'FR-24' },
      { id: 'translations', label: 'Translations', icon: 'globe', permission: 'translations.edit', soon: '7D', prd: 'FR-33' }
    ]
  },
  {
    label: 'Bot',
    items: [
      { id: 'tuning', label: 'Bot tuning', icon: 'sliders', permission: 'prompts.edit', prd: 'FR-25' },
      { id: 'escalation', label: 'Escalation rules', icon: 'route', permission: 'escalation.edit', prd: 'FR-29' },
      { id: 'experiments', label: 'A/B tests', icon: 'split', permission: 'experiments.edit', soon: '7D', prd: 'FR-32' }
    ]
  },
  {
    label: 'Settings',
    items: [
      { id: 'rules', label: 'Calculator rules', icon: 'calculator', permission: 'rules.edit', prd: 'FR-27' },
      { id: 'integrations', label: 'Integrations', icon: 'plug', permission: 'integrations.manage', soon: '7D', prd: 'FR-28' },
      { id: 'users', label: 'Users & roles', icon: 'users', permission: 'users.manage', prd: 'FR-30' },
      { id: 'activity', label: 'Activity log', icon: 'list', permission: 'activity.view', prd: '§7' }
    ]
  }
]

export const ACCOUNT_PAGE = { id: 'account', label: 'My account', permission: null }

export function canSee(item, permissions) {
  return !item.permission || permissions.includes(item.permission)
}

export function visibleGroups(permissions) {
  return NAV_GROUPS
    .map((g) => ({ ...g, items: g.items.filter((i) => canSee(i, permissions)) }))
    .filter((g) => g.items.length)
}

export function findPage(id) {
  if (id === ACCOUNT_PAGE.id) return ACCOUNT_PAGE
  for (const g of NAV_GROUPS) for (const i of g.items) if (i.id === id) return i
  return null
}
