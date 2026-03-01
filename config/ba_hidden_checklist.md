# Internal BA Quality Checklist

> This file is NOT shown to end users. It is loaded by the backend and used as
> internal guidance to ensure all BA outputs meet project standards.

## Mandatory Sections in Every Requirements Document

- [ ] **Overview / Purpose** — 1–2 sentences describing the feature and its business value.
- [ ] **Functional Requirements** — At minimum 3 distinct, testable functional requirements.
- [ ] **Non-Functional Requirements** — Must include at least one of: performance, security, accessibility.
- [ ] **Out of Scope** — Explicitly state what is NOT covered.
- [ ] **Assumptions** — At least one assumption documented.
- [ ] **Clarifying Questions** — Any unresolved decisions must be listed.

## Story Quality Standards

- Every story must have a clear **"who/what/why"** (user story format or equivalent).
- Acceptance criteria must be **testable** — avoid subjective language ("user-friendly", "fast", "intuitive").
- Stories should be **independently deliverable** — no hidden dependencies between stories without explicit documentation.
- Each story should take no more than **1 sprint** to complete. If larger, split it.
- Every Epic must have a description that explains **business value**.

## Acceptance Criteria Requirements

- Must cover the **happy path** (success scenario).
- Must cover at least one **error/failure path**.
- Must cover relevant **edge cases** (empty states, max/min values, concurrent operations).
- Language must be precise enough for a QA engineer to write a test case without clarification.
- Language must be precise enough for an automated Playwright script to be generated.

## Consistency Checklist

- Terminology must be consistent across all stories in the set (e.g., do not use "user" and "customer" interchangeably).
- Statuses/states referenced in ACs must match those in the system (e.g., "Pending", "Active", "Cancelled").
- API field names referenced in requirements should match the actual API contract where known.

## Security & Compliance (flag if missing)

- If the feature handles PII or sensitive data: data retention and access control must be documented.
- If the feature includes file upload: accepted formats, max file size, and virus scanning must be mentioned.
- If the feature involves authentication/authorisation changes: flag for security review.

## Output Reminders

- Never produce vague acceptance criteria. Always be specific.
- Never produce stories without at least 2 acceptance criteria.
- Always include labels to help with Jira filtering (e.g., "frontend", "backend", "api", "data", "ux", "security").
