"""Role-based access control for the admin module (PRD FR-30).

The four PRD roles and what each may do. Every admin endpoint declares the permission it needs and the
server enforces it; the admin UI only uses this list to decide what to show."""
from typing import Dict, FrozenSet, List

from app.core.security import Role

# Read
ANALYTICS_VIEW = "analytics.view"            # FR-31 dashboard, usage and cost
CONVERSATIONS_VIEW = "conversations.view"    # FR-26 transcripts
# Content and training
CONVERSATIONS_REVIEW = "conversations.review"  # FR-26 tag, flag, turn a corrected answer into a KB entry
KB_EDIT = "kb.edit"                          # FR-24 knowledge base
TRANSLATIONS_EDIT = "translations.edit"      # FR-33 multilingual content
PROMPTS_EDIT = "prompts.edit"                # FR-25 prompt, persona, journeys, guardrails, tone
ESCALATION_EDIT = "escalation.edit"          # FR-29 handoff triggers and routing
EXPERIMENTS_EDIT = "experiments.edit"        # FR-32 A/B tests
# Administration
RULES_EDIT = "rules.edit"                    # FR-27 rates, rules, thresholds, fees (financial; admins only)
BUDGET_EDIT = "budget.edit"                  # PRD §7 monthly AI budget and alert
INTEGRATIONS_MANAGE = "integrations.manage"  # FR-28
LEADS_VIEW = "leads.view"                    # advisor leads contain personal data
USERS_MANAGE = "users.manage"                # FR-30 accounts and roles
ACTIVITY_VIEW = "activity.view"              # who changed what
CONFIG_RELOAD = "config.reload"

ALL_PERMISSIONS: FrozenSet[str] = frozenset({
    ANALYTICS_VIEW, CONVERSATIONS_VIEW, CONVERSATIONS_REVIEW, KB_EDIT, TRANSLATIONS_EDIT, PROMPTS_EDIT, ESCALATION_EDIT,
    EXPERIMENTS_EDIT, RULES_EDIT, BUDGET_EDIT, INTEGRATIONS_MANAGE, LEADS_VIEW, USERS_MANAGE, ACTIVITY_VIEW, CONFIG_RELOAD,
})

_ANALYST = frozenset({ANALYTICS_VIEW, CONVERSATIONS_VIEW})
_EDITOR = _ANALYST | {KB_EDIT, TRANSLATIONS_EDIT}
_TRAINER = _EDITOR | {CONVERSATIONS_REVIEW, PROMPTS_EDIT, ESCALATION_EDIT, EXPERIMENTS_EDIT}

ROLE_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    Role.READ_ONLY_ANALYST: _ANALYST,
    Role.CONTENT_EDITOR: frozenset(_EDITOR),
    Role.BOT_TRAINER: frozenset(_TRAINER),
    Role.ADMIN: ALL_PERMISSIONS,
}

ROLE_LABELS: Dict[str, str] = {
    Role.ADMIN: "Admin",
    Role.BOT_TRAINER: "Bot trainer",
    Role.CONTENT_EDITOR: "Content editor",
    Role.READ_ONLY_ANALYST: "Read-only analyst",
}

ROLES: List[str] = list(ROLE_LABELS)


def permissions_for(role: str) -> FrozenSet[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())
