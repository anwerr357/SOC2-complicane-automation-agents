# Dev Team Agent

**Module:** `agents/dev_team_agent.py`
**Class:** `DevTeamAgent(BaseAgent)`

---

## Purpose

PR-level compliance gatekeeper. Shallow-clones every pull request branch and runs two scanner chains: Trufflehog for secret detection across the full commit history, and Semgrep for code-level compliance patterns using custom rules.

---

## Redis streams consumed

| Stream | Trigger |
|--------|---------|
| `github.prs` | A pull request is opened or synchronised on GitHub |

**Controls owned:** `CC6.1`, `CC7.2`, `CC8.1`, `CC6.3`

---

## How it works

1. Receives event: `{"repo_full_name": "org/repo", "pr_number": 42, "head_sha": "abc123"}`
2. Shallow-clones the PR branch into a temp directory using a token-auth git askpass helper (token never written to disk)
3. **Trufflehog:** Scans full git history of the cloned branch for live secrets — API keys, tokens, certificates
4. **Semgrep:** Runs custom rules from `semgrep_rules/` against the working tree
5. For each finding from either scanner, calls `run_remediation_loop()`
6. Temp directory is always cleaned up, even on error

---

## Scanner chain

```
github.prs event
    │
    ▼
shallow_clone(repo, sha, token) → /tmp/clone-xxxx/
    │
    ├── TrufflehogRunner.scan(clone_dir)
    │       └── findings: list[TrufflehogFinding]
    │
    └── SemgrepRunner.scan(clone_dir)
            └── findings: list[SemgrepFinding]
    │
    ▼
for finding in all_findings:
    run_remediation_loop(finding, repo_full_name, github_token)
    │
    ├── PASS → PR opens: compliance-fix/<control_id>/<check_id>
    └── FAIL → Slack escalation
```

---

## Example end-to-end

**Violation:** A new `/api/users` POST endpoint writes to the database but never calls `audit_log()`.

```
PR opened → github.prs stream
  └── DevTeamAgent.handle_event()
        ├── Trufflehog → no secrets found
        └── Semgrep → custom rule fires: missing audit_log() call
              control_id: CC7.2 (Audit logging)
              └── run_remediation_loop()
                    ├── NOTIFY   → evidence row inserted
                    ├── LEARN    → Qdrant returns CC7.2 control text
                    ├── RECOMMEND → Claude: "This endpoint writes user data..."
                    ├── MUTATE   → PR opened: compliance-fix/CC7.2/semgrep-audit-log
                    └── VALIDATE → Semgrep re-runs → PASS → status=remediated
```

---

## Custom Semgrep rules

Rules live in `semgrep_rules/` as YAML files. Three rules ship out of the box:

| File | What it catches | Control |
|------|----------------|---------|
| `audit_log.yaml` | Functions that write to DB without calling `audit_log()` | CC7.2 |
| `hardcoded_secret.yaml` | String literals that look like API keys or passwords | CC6.1 |
| `dangerous_eval.yaml` | Use of `eval()` or `exec()` with dynamic input | CC8.1 |

**Add a new rule:**

Create a new `.yaml` file in `semgrep_rules/` following the Semgrep rule schema:

```yaml
rules:
  - id: require-rate-limit-on-auth-endpoints
    patterns:
      - pattern: |
          @app.route("/login", ...)
          def $FUNC(...):
              ...
    message: "Auth endpoint missing rate limiting — CC6.2 violation"
    languages: [python]
    severity: WARNING
    metadata:
      control_id: CC6.2
      control_name: "Authentication and MFA"
```

No other files need to change. `SemgrepRunner` discovers all `.yaml` files in the rules directory automatically.
