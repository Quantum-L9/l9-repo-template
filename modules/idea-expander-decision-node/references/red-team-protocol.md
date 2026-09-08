# QA and Red-Team Protocol

## Mission

Attempt to invalidate the business plan before capital, reputation, or execution capacity is committed.

## Attack Surfaces

- problem may not be painful enough
- customer or budget owner may be wrong
- distribution may be uneconomic
- offer may be difficult to explain or trust
- economics may depend on optimistic assumptions
- autonomous agents may lack tools, authority, reliability, or observability
- L9 reuse may be overstated or create coupling
- data, legal, security, or privacy constraints may block operation
- operating complexity may erase margin
- incumbent or substitute responses may be underestimated
- founder or team dependencies may be hidden
- scaling may reduce quality or increase risk

## Finding Contract

Each finding includes:

- id
- claim challenged
- evidence
- severity: critical, high, medium, low
- confidence
- failure mechanism
- business impact
- required repair or validation
- disposition: resolved, mitigated, accepted, converted_to_condition, unresolved

## Refinement Loop

1. red-team issues findings
2. business-plan agent responds point by point
3. plan is modified with visible change log
4. red-team verifies dispositions
5. unresolved critical findings force HOLD or NO_GO

The refined plan must not delete the original finding history.
