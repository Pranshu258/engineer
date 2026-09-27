# Systematic debugging

Find the root cause before proposing a fix. Use this skill for diagnosis and
implement only after the failure mechanism is supported by evidence.

## Guardrails

- Do not expose secrets, credentials, customer data, or private tokens.
- Prefer read-only observation first. Ask before destructive or materially
  expensive actions.
- Do not change multiple variables in one experiment.
- Do not present a passing proxy as proof that the reported failure is fixed.
- Treat unavailable external dependencies separately from code defects.

## Workflow

1. Define expected behavior, observed behavior and exact error, the smallest
   reproduction, environment and revision, and whether the failure is
   deterministic, intermittent, or historical.
2. Establish the change boundary by inspecting relevant code, configuration,
   dependencies, and producer-consumer contracts. Correlation is only a lead.
3. Trace evidence from input through parsing, transformation, storage or
   transport, consumer, and observed failure. At each boundary identify inputs,
   outputs, and the invariant that should hold.
4. Form one falsifiable hypothesis. Record supporting and contradicting
   evidence, the smallest experiment that could disprove it, and expected
   results for true and false outcomes.
5. Prove why the failure occurs under the observed conditions, why a comparison
   case works, why the correction addresses the mechanism, and how recurrence
   would be detected. If three attempted corrections fail, reassess rather than
   stacking patches.
6. Bound the repair with the confirmed root cause, affected surface, regression
   test or reproduction, smallest correction, required validation, and
   remaining uncertainty.

Lead with: failure, root cause, evidence, disproved alternatives, repair
boundary, required validation, and remaining uncertainty.
