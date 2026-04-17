# System Skill Rules

## Git Workflow (Mandatory)

For every completed action/change:

1. Stage changes
2. Commit
3. Push to remote
4. Update `README.md`
5. Update handover document(s) (at least `A_BROWSER_RAG_VALIDATION_HANDOVER.md`)

Commit message format:

`refator: <做的事情>`

Examples:

- `refator: search page suggestions layout and i18n sync`
- `refator: language-routed embedding for zh and en`

## Documentation Sync Rule (Mandatory)

Every code/config/behavior change must include documentation updates in the same commit:

- `README.md`: update user-facing behavior, architecture, or setup notes.
- Handover document(s): update verification status, operational SOP, and change log.
