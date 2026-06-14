# Dev Team Agent

Scans every pull request for secrets and code-level compliance violations.

**Stream:** `github.prs` | **Controls:** CC6.1, CC6.3, CC7.2, CC8.1

***

## Trigger manually

```bash
curl -X POST http://localhost:8000/webhook/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -d '{
    "action": "opened",
    "pull_request": {
      "number": 42,
      "head": {"sha": "abc123", "repo": {"full_name": "org/repo"}}
    }
  }'
```

***

## Scanner chain

1. **Trufflehog** — scans full git history of the PR branch for live secrets
2. **Semgrep** — runs custom rules from `semgrep_rules/` for code patterns

***

## Example violation → remediation

A new endpoint writes to the database without calling `audit_log()`:

1. Semgrep rule `audit_log.yaml` fires → `CC7.2`
2. Claude explains the audit trail gap
3. PR opened: `compliance-fix/CC7.2/semgrep-audit-log`
4. Semgrep re-runs → passes → status `remediated`

***

## Add a custom Semgrep rule

Create a `.yaml` file in `semgrep_rules/`:

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

→ [Full developer reference](/broken/pages/Gplh51ArC2vhFXmyuDIc)
