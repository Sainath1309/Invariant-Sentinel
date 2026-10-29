# Admin console and remediation workflow

The Admin tab adds service-management tools alongside the existing Monitor, Relationships, Evaluation, and Your data pages. The original monitoring interface and its detection logic remain in place.

## Admin console

- Password-protected admin session using an HttpOnly, SameSite cookie.
- Overview counts for clients, configured datasets, drift incidents, and saved recommendations.
- Client records with contact metadata, notes, active/paused status, and incident assignment.
- Persistent incident queue with workflow states: open, in review, resolved, dismissed.
- Per-incident remediation suggestions and a lightweight audit trail.
- Client, incident, recommendation, and audit metadata are stored in `artifacts/admin.sqlite3`.

### Configure credentials

Set these environment variables before starting the server:

PowerShell:

```powershell
$env:SENTINEL_ADMIN_PASSWORD = "use-a-long-unique-password"
$env:SENTINEL_ADMIN_SECRET = "use-a-long-random-secret-value"
python run.py
```

For a local demo only, the fallback password is `admin-change-me`. Do not deploy with fallback credentials or the fallback signing secret. Use HTTPS and a secret manager in a deployed service. The session expires after 12 hours.

## Remediation workflow

Sentinel records non-normal batches that need attention (including quality issues, broken/unclear relationships, insufficient data, and distribution shifts). The admin can generate a deterministic recommendation from the stored incident evidence. Recommendations include:

1. the Sentinel verdict and evidence used;
2. the suggested investigation or remediation method;
3. why the method fits the evidence;
4. concrete action steps and success criteria;
5. limitations and a review status.

The recommendations are decision support, not automatic production changes. Quality issues prioritize correcting the source/pipeline before retraining. A harmless distribution shift prompts performance and segment checks first. A broken relationship prompts lineage/source investigation; retraining is considered only if the underlying process has genuinely changed. Ambiguous or insufficient cases explicitly ask for more evidence.

## Current service boundary

This is an admin and incident-management foundation for the project, not a complete hardened multi-tenant SaaS deployment. Client records and incident assignment are supported, but dataset access is still shared by the current single-process monitoring API. Before giving external clients direct access, add authenticated client identities, per-tenant data isolation and authorization, upload limits, rate limiting, persistent monitoring-run storage, backups, and deployment secrets. Run progress itself remains in memory and is lost when the server restarts; stored incident and admin metadata persists.
