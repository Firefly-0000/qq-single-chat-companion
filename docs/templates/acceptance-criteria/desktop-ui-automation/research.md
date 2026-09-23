---
forge:
  status: unreviewed
  forged: 2026-09-23
  reviewed: null
content_type: acceptance-criteria
variant: desktop-ui-automation
---

# Research: acceptance-criteria / desktop-ui-automation

## Sources

1. Atlassian, "What is acceptance criteria? Examples and best practices"
   - https://www.atlassian.com/work-management/project-management/acceptance-criteria
   - Supports: clear and concise criteria, outcome-focused behavior, testability,
     measurability, independence, collaboration, review and refinement.
2. Cucumber, "Gherkin Reference"
   - https://cucumber.io/docs/gherkin/reference/
   - Supports: Feature, Rule, Example, Background, Given, When, Then, and
     Scenario Outline as the executable scenario vocabulary.
3. Internal authoring method for feature specifications
   - Supports: edge cases must name handling, state transitions, I/O contracts,
     numeric NFR targets, and metric-threshold acceptance for probabilistic
     behavior.

## Section Mapping

| Template Section | Research Basis | Status |
|---|---|---|
| Document control | Project governance need | Project-specific |
| Acceptance goal and scope | Atlassian: tie criteria to intended outcome | Supported |
| Preconditions | Gherkin: Background establishes shared preconditions | Supported |
| Functional acceptance | Atlassian: testable conditions; Gherkin: examples/scenarios | Supported |
| State and interaction acceptance | Internal method: state-transition table | Single-source; verify in use |
| Exception and recovery acceptance | Internal method: failure handling named per edge case | Single-source; verify in use |
| Non-functional acceptance | Atlassian: measurability; internal method: numeric NFRs | Supported |
| Test data and evidence | Gherkin: examples and scenario evidence | Supported |
| Pass gate | Atlassian: acceptance means completion against agreed conditions | Supported |
| Open questions | Internal method: surface assumptions and blockers | Single-source; verify in use |
| Approval | Project governance need | Project-specific |

## Notes

- The template is intentionally outcome-focused and avoids prescribing implementation.
- Probabilistic behavior must use metric thresholds on a named dataset rather than
  "the response is good".
- User-facing screens must include numeric accessibility, keyboard, and state checks.
