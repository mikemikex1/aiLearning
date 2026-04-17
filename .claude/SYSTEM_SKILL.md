# System Skill Rules

## Git Workflow (Mandatory)

For every completed action/change:

1. Stage changes
2. Commit
3. Push to remote
4. Update `README.md`
5. Update handover document(s), at least `A_BROWSER_RAG_VALIDATION_HANDOVER.md`

## Commit Message Rule (Mandatory)

Use this format:

`<type>: <Action>`

Recommended `type` values:

- `debug`: bug fix
- `add`: new feature
- `edit`: modify existing behavior
- `docs`: documentation only
- `chore`: maintenance/refactor/non-feature task
- `test`: test changes
- `perf`: performance optimization
- `refactor`: structural cleanup without behavior change

Examples:

- `debug: fix search follow-up context expansion`
- `add: in-chat suggestion buttons on search page`
- `edit: adjust i18n labels for zh and en`

## Documentation Sync Rule (Mandatory)

Every code/config/behavior change must include documentation updates in the same commit:

- `README.md`: update user-facing behavior, architecture, or setup notes
- Handover document(s): update verification status, operational SOP, and changelog
