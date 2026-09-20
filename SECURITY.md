# Security

This alpha supports trusted local operation only. Do not put credentials, provider
payloads or state files in issues. Report vulnerabilities privately using GitHub's
security advisory reporting for this repository when enabled.

No provider key is needed by CI. Live deployments supply TYPESAFE_API_KEY through
their own secret manager. Publishing credentials are restricted to the release job.
