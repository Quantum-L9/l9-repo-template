# Security Policy

## Reporting a Vulnerability

Quantum-L9 takes the security of the L9 CI platform seriously. If you discover a
security vulnerability in this repository, please report it **privately**.

- Do **not** open a public issue for security reports.
- Email: ib@scrapmanagement.com
- Owners: @Quantum-L9/platform

Please include a description of the issue, the affected component, and steps to
reproduce. You can expect an acknowledgement while the platform team
investigates and coordinates a fix.

## Supported Versions

Security fixes target the latest released tag and the `main` branch. Pre-release
tags (`v0.1.x`) receive fixes until the stable `v1` line supersedes them.

## Scope

This policy covers the L9 CI trio: the SDK runtime and CLI, the reusable GitHub
Actions workflows and governance defaults, and the repo template. The wire
contract is TransportPacket; reports concerning legacy contracts are out of
scope.
