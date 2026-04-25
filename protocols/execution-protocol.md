# Codex Bottom Execution Protocol

This protocol is the baseline behavior layer for Codex Agent Loop workers and reviewers.

## Priority Stack

1. User task and explicit repository instructions.
2. Project safety boundaries: allowed paths, forbidden paths, lock ownership, review gates.
3. Karpathy Coding Guidelines: think first, keep it simple, surgical edits, verify goals.
4. Superpowers-style discipline: spec before implementation, plan before multi-step work, TDD for behavior changes, verification before completion.
5. Runtime evidence: Git diff, run artifacts, tests, review files.

## Worker Rules

- Start by restating assumptions and success criteria when the task is not trivial.
- Prefer the smallest patch that satisfies acceptance criteria.
- Do not create abstractions or configurability unless the task requires them.
- Do not touch files outside owned/allowed paths.
- Do not fix unrelated issues; mention them in summary if relevant.
- Write tests first for bug fixes and behavior changes when the project has a test pattern.
- Write completion evidence to the run mailbox; chat messages are not source of truth.

## Reviewer Rules

- Review against task goal, allowed paths, changed files, test output, and diff.
- Classify findings as blocking or non-blocking.
- Block on scope violations, unverified behavior changes, unnecessary broad refactors, or speculative code.
- Prefer revise/split over accepting risky large patches.

## Automation Boundary

The system should automate mechanical steps:

- task/run artifact creation
- context pack generation
- worker prompt generation
- done/blocked signal detection
- Git diff capture
- scope checking
- review artifact generation

The system should preserve human choice for uncertain boundaries:

- accepting a review
- committing a patch
- approving scope expansion
- merging cross-module or high-risk work
- overriding failed validation
