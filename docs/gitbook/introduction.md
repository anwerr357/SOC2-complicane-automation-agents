# Introduction

ComplyAgent is an event-driven system of three autonomous AI agents that watch your Kubernetes cluster, Terraform infrastructure, and GitHub pull requests 24/7. When a SOC 2 control violation is detected, the system explains it in plain English and automatically opens a remediation pull request — without any human intervention.

---

## The problem it solves

Most engineering teams treat SOC 2 compliance as a quarterly event. An auditor arrives, requests evidence, and violations that have been sitting undetected for weeks are discovered under pressure. Manual evidence collection is slow. Engineers spend hours translating raw scanner output (`CKV_AWS_19 FAILED`) into something actionable.

ComplyAgent makes compliance **continuous and automated**:

- Violations are detected the moment they occur — not weeks later
- Every finding is logged automatically to an immutable audit trail
- Engineers receive specific, LLM-generated remediation PRs instead of raw scanner JSON

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         Event Sources                            │
│   GitHub webhooks   ·   Terraform plans   ·   Kubernetes watch   │
└───────────────┬──────────────────┬────────────────┬─────────────┘
                │                  │                │
                ▼                  ▼                ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Redis Streams (event bus)                   │
│      github.prs     ·     tf.plans     ·     k8s.events          │
└──────┬──────────────────────┬──────────────────┬────────────────┘
       │                      │                  │
       ▼                      ▼                  ▼
  Dev Team Agent        Policy Agent      Cluster Operator
  (Trufflehog +         (Checkov)         (k8s watch API)
   Semgrep)
       │                      │                  │
       └──────────────┬───────┘──────────────────┘
                      ▼
         ┌────────────────────────┐
         │   Compliance Brain     │
         │  Claude API + Qdrant   │
         │  (RAG on SOC 2 TSC)    │
         └────────────┬───────────┘
                      ▼
            ┌─────────────────────┐
            │  Remediation Loop   │
            │  5 automated steps  │
            └─────────┬───────────┘
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
   GitHub Pull Request      Postgres evidence
   (compliance-fix/*)        store (audit trail)
```

---

## SOC 2 control coverage

| Control | Description | Agent | Scanner |
|---------|-------------|-------|---------|
| CC6.1 | Logical and physical access controls | Policy, Dev Team | Checkov, Trufflehog |
| CC6.2 | Authentication and MFA | Policy | Checkov |
| CC6.3 | Access removal | Dev Team | Semgrep |
| CC6.6 | Least privilege | Policy | Checkov |
| CC6.7 | Encryption at rest | Policy | Checkov |
| CC6.8 | Unauthorized software | Cluster Operator | k8s watch |
| CC7.1 | System monitoring | Cluster Operator | k8s watch |
| CC7.2 | Audit logging | Cluster Operator, Dev Team | Semgrep, k8s watch |
| CC8.1 | Change management | Dev Team | Semgrep |
| CC9.1 | Risk assessment | Policy | Checkov |
| A1.1 | Availability | Cluster Operator | k8s watch, Checkov |

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 (async throughout) |
| Agent orchestration | LangGraph |
| LLM | Claude (`claude-sonnet-4-6`) |
| Vector DB | Qdrant |
| Event bus | Redis Streams |
| IaC scanner | Checkov |
| Secret scanner | Trufflehog |
| SAST | Semgrep |
| K8s client | kubernetes-asyncio |
| GitHub API | PyGithub |
| Web framework | FastAPI |
| Database | Postgres 16 |
| Dashboard | React + Tailwind |

---

Next: [Installation →](installation.md)
