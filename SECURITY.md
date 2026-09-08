# Security Policy

Omi handles personal conversations, screen context, integrations, and account data. Please report security issues privately so maintainers can investigate and ship fixes before details are public.

## Supported Versions

Security fixes are prioritized for:

- The latest `main` branch
- Current production releases of the Omi mobile, desktop, web, backend, firmware, and wearable software

Older releases may not receive separate fixes unless maintainers decide the risk warrants a backport.

## Reporting a Vulnerability

Please do not open a public GitHub issue, public pull request, or Discord thread for an unpatched vulnerability.

Preferred reporting path:

1. Use GitHub's private vulnerability reporting flow from the repository Security tab, if available: https://github.com/BasedHardware/omi/security/advisories/new
2. If private vulnerability reporting is unavailable, contact the maintainers and ask for a private security channel before sharing exploit details.

Include as much of the following as possible:

- Affected component, endpoint, app, firmware, or commit
- Impact and who can be affected
- Reproduction steps or a minimal proof of concept
- Any relevant logs, request/response examples, screenshots, or traces
- Whether the issue affects production, local development, self-hosted deployments, or all environments
- Suggested fix or mitigation, if you have one

Maintainers aim to acknowledge valid reports within 3 business days and will follow up with triage questions, mitigation status, and disclosure timing when possible.

## Scope

In scope examples:

- Broken authentication or authorization
- Cross-account data access or modification
- Exposure of conversations, memories, transcripts, recordings, screenshots, credentials, API keys, or integration secrets
- Remote code execution, command injection, SSRF, path traversal, or unsafe file handling
- Vulnerabilities in OAuth, Firebase auth handling, webhook delivery, MCP/tool integrations, or app marketplace flows
- Mobile, desktop, backend, firmware, web, and self-hosting security issues

Out of scope examples:

- Social engineering, phishing, or physical attacks
- Vulnerabilities that only affect unsupported versions or modified private forks
- Denial-of-service testing that degrades production service availability
- Spam, rate-limit bypass, or automation abuse without a demonstrated security impact
- Reports that require access to another user's account or data without permission
- Third-party service vulnerabilities that do not affect Omi's implementation

## Safe Harbor

Good-faith security research is welcome when it follows this policy.

Please:

- Use your own accounts, devices, workspaces, and data whenever possible
- Stop testing and report immediately if you encounter another user's data
- Do not persist, copy, disclose, or modify data that is not yours
- Avoid disrupting Omi services, users, integrations, or infrastructure
- Give maintainers reasonable time to investigate and fix before public disclosure

If you are unsure whether a test is safe, ask maintainers privately before continuing.

## Coordinated Disclosure

Public disclosure should wait until maintainers have confirmed a fix, mitigation, or disclosure plan. If a report is accepted, maintainers may credit the reporter in release notes, advisories, or pull requests unless the reporter asks to remain anonymous.
