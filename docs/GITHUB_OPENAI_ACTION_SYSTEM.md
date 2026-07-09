# GitHub + OpenAI Action System Architecture

This document defines the target architecture for a Codex-style Titan Nova workflow where a user can ask for repo work, the backend can use OpenAI for planning/code assistance, and GitHub actions are executed through auditable backend APIs.

## High-level flow

```text
User → Frontend (React/Next)
         ↓
   Backend API (Node.js / Python)
         ↓
   ┌─────┴─────┐
   ↓           ↓
GitHub API  OpenAI API
   ↓           ↓
   └─────┬─────┘
         ↓
   Database (PostgreSQL / MongoDB)
   - Users
   - Repos
   - Chats
   - Actions (Gists, Issues, PRs)
```

## Main components

### 1. Frontend

Recommended stack: React or Next.js.

Responsibilities:
- Login/session UI.
- Repo selector.
- Chat/task input.
- Review generated plans before execution.
- Show PRs, issues, gists, commits, and action logs.
- Require explicit confirmation for dangerous actions such as merge, delete, force update, or secret/environment changes.

Frontend must never store or expose GitHub tokens or OpenAI API keys.

### 2. Backend API

Recommended stack: Node.js/Express/NestJS or Python/FastAPI/Flask.

Responsibilities:
- Authenticate users.
- Store encrypted GitHub credentials or GitHub App installation IDs.
- Store OpenAI API key only on the server side.
- Route user tasks into safe action plans.
- Call OpenAI API for planning, summaries, patch suggestions, and code review.
- Call GitHub API for branch creation, file updates, issues, gists, PRs, and merges.
- Persist all chats and actions to the database.
- Enforce allowlists, confirmations, and audit logs.

### 3. GitHub API integration

Supported actions:
- Search repositories and files.
- Fetch files and diffs.
- Create/update branches.
- Create/update files.
- Create issues and comments.
- Create pull requests.
- Read PR status and mergeability.
- Merge only when safe and explicitly approved.

Rules:
- Do not write directly to `main` for normal feature work.
- Create a focused branch first.
- Upgrade existing patch/module files instead of creating duplicate patch files for the same feature.
- Create a PR for review.
- Merge only when the PR is mergeable and approved.

### 4. OpenAI API integration

OpenAI is used for:
- Understanding user requests.
- Planning safe repository changes.
- Generating or editing code.
- Explaining diffs.
- Summarizing PRs and actions.
- Classifying actions by risk level.

OpenAI should not receive raw secrets, private tokens, or unnecessary user credentials.

### 5. Database

PostgreSQL is recommended for strong consistency and auditability. MongoDB is acceptable for flexible chat/action documents.

Core tables/collections:

#### users
- `id`
- `email`
- `display_name`
- `created_at`
- `last_login_at`
- `role`

#### repos
- `id`
- `user_id`
- `provider`
- `owner`
- `name`
- `default_branch`
- `installation_id` or encrypted token reference
- `created_at`

#### chats
- `id`
- `user_id`
- `repo_id`
- `title`
- `created_at`
- `updated_at`

#### messages
- `id`
- `chat_id`
- `role`
- `content`
- `created_at`

#### actions
- `id`
- `chat_id`
- `repo_id`
- `action_type`
- `status`
- `risk_level`
- `branch`
- `pr_number`
- `github_url`
- `input_json`
- `result_json`
- `created_at`
- `completed_at`

#### audit_logs
- `id`
- `user_id`
- `repo_id`
- `action_id`
- `event`
- `metadata_json`
- `created_at`

## Recommended action workflow

```text
1. User asks for repo work.
2. Backend creates a chat/action record.
3. OpenAI produces a plan.
4. Backend checks policy and existing repo files.
5. Backend creates a branch from latest main.
6. Backend updates only the existing relevant module/patch file when applicable.
7. Backend creates a PR.
8. User reviews PR.
9. Backend merges only after explicit approval and mergeability check.
10. Backend stores final action result and deploy instructions.
```

## Titan Nova patch ownership rules

- Result tab, checkbox, settlement, auto mark: update `result_toggle_sticky.py`.
- VIPs tab, profile create/delete/approval: update `titan_profile_delete_guard_patch.py` or the existing VIP module.
- Deposit OCR and UPI screenshot verification: update `deposit_ocr_guard.py`.
- Finance deposit/payment/wallet bridge: update `deposit_finance_force.py`.
- Realtime sync and refresh revert: update `titan_realtime_global.py`.
- WhatsApp OCR/gateway bridge: update existing `gateway_deposit_ocr_patch.js` or launcher registration in `Gateway.js`.
- `flask_app.py` should only register/load modules. Avoid duplicating business logic there.
- `Gateway.js` should only register/load gateway bridges. Avoid duplicate bridge files for the same feature.

## Security rules

- GitHub token never goes to the frontend.
- OpenAI API key never goes to the frontend.
- Store secrets encrypted or use GitHub App installations.
- Log every write action.
- Require confirmation for merge, delete, overwrite, or force-update actions.
- Do not send secrets to OpenAI.
- Validate repository owner/name and branch names.
- Avoid destructive actions on `main`.

## Merge policy

Safe to merge:
- PR is mergeable.
- PR does not delete active runtime files.
- PR has focused changes.
- PR passes syntax/smoke checks where available.
- User explicitly requests merge.

Do not merge automatically:
- PR is not mergeable.
- PR deletes `flask_app.py`, `Gateway.js`, or legacy runtime backups without a confirmed migration.
- PR changes credentials/secrets.
- PR mixes unrelated changes.
- PR conflicts with current Titan Nova patch ownership rules.

## Deployment reminder

After merge, Termux deployments should use:

```bash
cd ~/titan-app

titan stop 2>/dev/null || true
pkill -f flask_app.py 2>/dev/null || true
pkill -f Gateway.js 2>/dev/null || true

git fetch origin main
git reset --hard origin/main

python -m py_compile flask_app.py result_toggle_sticky.py titan_profile_delete_guard_patch.py deposit_ocr_guard.py deposit_finance_force.py titan_realtime_global.py
node --check Gateway.js

titan start
```
