# Security Policy

## Supported versions

Security fixes are made on the `main` branch. There are no separate release branches, so please make sure you are testing the latest `main` before reporting.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Report it privately through GitHub: open the **Security** tab of this repository and choose **Report a vulnerability**. (If you do not see that button, private reporting is not enabled yet; open an issue that says only "I would like to report a security problem privately" and no details, and the maintainer will arrange a private channel.)

Please include:

- what the problem is and where it is (file, endpoint or page)
- steps to reproduce it, or a short proof of concept
- what an attacker could do with it
- the version or commit you tested

## What to expect

- You will get an acknowledgement within a few days.
- The problem will be confirmed, fixed on `main` and covered by a test where possible.
- You will be told when the fix is released, and you are welcome to be credited if you want to be.

## Scope

In scope: the API, the web application, authentication and authorization, the AI triage and assist features (including prompt injection), and the Docker and deployment configuration in this repository.

Out of scope: problems that need an already compromised server or database, demo mode (`DEMO_MODE`) behaving as documented (it is intentionally passwordless and refused in production), and findings in third-party services you run alongside it.

## Security measures in the project

The automated checks that run on every change (CodeQL, Bandit, pip-audit, npm audit, Gitleaks, Trivy and Dependabot) are described in the [Security & Quality](README.md#security--quality) section of the README.
