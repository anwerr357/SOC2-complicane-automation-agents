    # `scanners/checkov_runner.py`

    Async subprocess wrapper around the [Checkov](https://www.checkov.io/) IaC
    scanner.  Converts raw Checkov JSON output into normalised `CheckovFinding`
    objects that carry a SOC 2 Trust Service Criterion alongside every violation.

    ---

    ## Responsibilities

    1. **Run Checkov** — spawns `checkov --file <path> --output json --quiet --compact`
    as an async subprocess; captures stdout (JSON) and stderr (logs).
    2. **Parse two output shapes** — Checkov emits a dict when scanning one file type,
    and a list when multiple framework types are detected in the same file.
    3. **Normalise findings** — every `failed_check` becomes a `CheckovFinding`
    dataclass with a consistent set of fields, regardless of Checkov version.
    4. **Map to SOC 2** — a curated `SOC2_CONTROL_MAP` dict translates each check
    ID to a `(control_id, control_name)` pair.  Unknown IDs map to `CC0.0`.
    5. **Attach evidence attribution** — an optional `git_sha` is copied onto every
    finding so the audit trail links violations to a specific commit.

    ---

    ## Public API

    ### `SOC2_CONTROL_MAP`

    ```python
    SOC2_CONTROL_MAP: dict[str, tuple[str, str]]
    ```

    Module-level dict mapping Checkov check IDs to `(control_id, control_name)`.

    ```python
    "CKV2_AWS_61"  →  ("CC6.7", "Encryption at rest")
    "CKV_AWS_289"  →  ("CC6.6", "Least privilege and logical access restriction")
    "CKV_AWS_36"   →  ("CC7.2", "Audit logging and monitoring")
    ```

    **Extend this** when you add new infrastructure coverage.  Unknown IDs fall
    through to `("CC0.0", "Unknown control — review manually")` — the pipeline
    never crashes on unmapped rules.

    Currently covers **50+ check IDs** across these controls:

    | Control | Description |
    |---------|-------------|
    | CC6.1 | Logical and physical access controls |
    | CC6.2 | Authentication and multi-factor authentication |
    | CC6.3 | Access removal and user lifecycle management |
    | CC6.6 | Least privilege and logical access restriction |
    | CC6.7 | Encryption at rest |
    | CC6.8 | Unauthorized or malicious software protection |
    | CC7.1 | System monitoring and alerting |
    | CC7.2 | Audit logging and monitoring |
    | CC8.1 | Change management and authorised changes |
    | CC9.1 | Risk assessment and mitigation |
    | A1.1  | Availability and redundancy |

    ---

    ### `SEVERITY_MAP`

    ```python
    SEVERITY_MAP: dict[str, str]
    ```

    Translates Checkov's severity labels to the four values the evidence store
    accepts: `HIGH | MEDIUM | LOW | INFO`.

    | Checkov label | Normalised |
    |---------------|-----------|
    | `critical`    | `HIGH`    |
    | `high`        | `HIGH`    |
    | `medium`      | `MEDIUM`  |
    | `low`         | `LOW`     |
    | `info`        | `INFO`    |
    | `unknown`     | `INFO`    |

    ---

    ### `class CheckovFinding`

    ```python
    @dataclass
    class CheckovFinding:
        check_id:     str          # e.g. "CKV2_AWS_61"
        check_type:   str          # "terraform" | "kubernetes" | "cloudformation"
        resource_name: str         # e.g. "aws_s3_bucket.app_data"
        file_path:    str          # absolute path to scanned file
        severity:     str          # HIGH | MEDIUM | LOW | INFO
        control_id:   str          # e.g. "CC6.7"
        control_name: str          # e.g. "Encryption at rest"
        git_sha:      str | None   # HEAD SHA for audit attribution (optional)
        raw_finding:  dict         # verbatim Checkov JSON — stored in JSONB
    ```

    #### `CheckovFinding.to_evidence_dict() → dict`

    Returns a dict shaped exactly for `store.evidence.log_event()`.

    ```python
    {
        "agent_name":            "policy",
        "scanner_used":          "checkov",
        "check_id":              self.check_id,
        "control_id":            self.control_id,
        "control_name":          self.control_name,
        "resource_name":         self.resource_name,
        "file_path":             self.file_path,
        "git_sha":               self.git_sha,
        "severity":              self.severity,
        "violation_description": "",          # filled by LLM in Week 3
        "raw_finding":           self.raw_finding,
    }
    ```

    This method is the **integration contract** between the scanner and the store.
    New scanners must implement an equivalent method with the same key set.

    ---

    ### `class CheckovRunner`

    ```python
    class CheckovRunner:
        def __init__(self, checkov_binary: str = "checkov") -> None
    ```

    | Parameter | Type | Default | Description |
    |-----------|------|---------|-------------|
    | `checkov_binary` | `str` | `"checkov"` | Name or full path of the Checkov executable.  Override for non-default `PATH` environments or pinned versions. |

    #### `CheckovRunner.scan(file_path, *, git_sha=None, timeout=120) → list[CheckovFinding]`

    ```python
    async def scan(
        self,
        file_path: str | Path,
        *,
        git_sha: str | None = None,
        timeout: int = 120,
    ) -> list[CheckovFinding]
    ```

    Runs Checkov against a single `.tf` or `.yaml` / `.yml` file.

    | Parameter | Type | Default | Description |
    |-----------|------|---------|-------------|
    | `file_path` | `str \| Path` | required | Path to the IaC file.  Resolved to absolute before subprocess invocation. |
    | `git_sha` | `str \| None` | `None` | Optional HEAD commit SHA.  Attached to every `CheckovFinding` for audit trail. |
    | `timeout` | `int` | `120` | Subprocess hard timeout in seconds.  Kills the process and raises `asyncio.TimeoutError` on breach. |

    **Returns** `list[CheckovFinding]` — only **failed** checks.  Passed checks are
    silently discarded; they are not violations.

    **Raises:**

    | Exception | When |
    |-----------|------|
    | `RuntimeError` | `checkov` binary not found on `PATH` |
    | `asyncio.TimeoutError` | Scan exceeds `timeout` seconds |
    | `RuntimeError` | Checkov exits with code ≥ 2 (internal error) |

    **Exit code contract:**
    - `0` → all checks passed (returns `[]`)
    - `1` → some checks failed (returns findings, normal case)
    - `≥ 2` → Checkov internal error (raises `RuntimeError`)

    ---

    ### `run_checkov()` — convenience function

    ```python
    async def run_checkov(
        file_path: str | Path,
        *,
        git_sha: str | None = None,
        timeout: int = 120,
    ) -> list[CheckovFinding]
    ```

    Module-level shorthand that creates a `CheckovRunner()` and calls `.scan()`.
    Use this for one-off scans where you don't need to share a runner instance.

    ---

    ## Usage examples

    ### Basic scan

    ```python
    from scanners.checkov_runner import run_checkov

    findings = await run_checkov("infra/main.tf", git_sha="abc123def456")

    for f in findings:
        print(f"{f.check_id}  {f.control_id}  {f.resource_name}  [{f.severity}]")
    # CKV2_AWS_61  CC6.7  aws_s3_bucket.app_data  [MEDIUM]
    # CKV_AWS_289  CC6.6  aws_iam_role_policy.app_policy  [HIGH]
    ```

    ### Scan + persist to evidence store

    ```python
    from scanners.checkov_runner import run_checkov
    from store.evidence import get_session, log_event

    findings = await run_checkov("infra/main.tf", git_sha="abc123")

    async with get_session() as session:
        for finding in findings:
            await log_event(session, finding.to_evidence_dict())
    ```

    ### Custom binary path (e.g. virtual environment)

    ```python
    from scanners.checkov_runner import CheckovRunner

    runner = CheckovRunner(checkov_binary="/home/user/.venv/bin/checkov")
    findings = await runner.scan("infra/main.tf")
    ```

    ### Kubernetes YAML

    ```python
    findings = await run_checkov("k8s/deployment.yaml")
    # Returns CC6.6, A1.1, CC6.8 violations if present
    ```

    ---

    ## Internal flow

    ```
    scan(file_path)
        │
        ├── _find_binary()              shutil.which("checkov") in executor
        │
        ├── asyncio.create_subprocess_exec(
        │       "checkov --file <path> --output json --quiet --compact"
        │   )
        │
        ├── asyncio.wait_for(proc.communicate(), timeout)
        │
        ├── check returncode (0 or 1 = ok, ≥2 = error)
        │
        ├── json.loads(stdout)
        │
        └── _parse_results(raw)
                │
                ├── if list  → iterate _parse_block() for each check-type
                └── if dict  → single _parse_block()
                                    │
                                    └── for check in failed_checks:
                                            _normalise_check()
                                                │
                                                ├── SOC2_CONTROL_MAP.get(check_id)
                                                ├── SEVERITY_MAP.get(severity)
                                                └── CheckovFinding(...)
    ```

    ---

    ## Design decisions

    **Why subprocess instead of the Checkov Python SDK?**
    Checkov's internal Python API is not part of its public contract and has
    broken across minor versions multiple times.  The CLI `--output json` is the
    stable, documented surface.  Subprocess isolation also means a Checkov crash
    cannot kill the agent process.

    **Why `--compact`?**
    The `--compact` flag strips source-code line snippets from the JSON output.
    These snippets are large, add no value to the evidence store (we already have
    the file path and git SHA to retrieve the source), and slow down JSON parsing
    on large files.

    **Why resolve to absolute path?**
    `asyncio.create_subprocess_exec` inherits the working directory of the parent
    process, which varies depending on how the agent or API is launched.  Resolving
    to absolute before calling ensures Checkov always finds the file regardless of
    `cwd`.

    **Why is `violation_description` left empty?**
    The LLM-generated plain-English description is added in Week 3 by the
    compliance brain.  The scanner layer stays decoupled from the LLM — it only
    extracts facts.

    ---

    ## Adding a new check → control mapping

    Open [scanners/checkov_runner.py](../scanners/checkov_runner.py) and add one
    line to `SOC2_CONTROL_MAP`:

    ```python
    "CKV_AWS_XYZ": ("CC7.2", "Audit logging and monitoring"),
    ```

    No other files need to change.  The new mapping takes effect on the next scan.
