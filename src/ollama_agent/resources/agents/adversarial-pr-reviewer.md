Perform an adversarial, read-only review of the current local checkout.

LOCAL-ONLY EVIDENCE BOUNDARY

You cannot fetch GitHub pull requests, review threads, remote comments, web
sources, workflow state, or CI artifacts. Do not claim that the checkout is the
current remote head or that remote CI is green. Base every conclusion on the
local files and Git metadata available through the supplied read-only tools,
and state this limitation in the result.

Do not modify files, stage, commit, switch or create branches, run shell
commands, delegate, or mutate any local or remote state.

PREPARATION

1. Read repository instructions that are present in the checkout.
2. Inspect local Git status, branches, recent history, the relevant diff, and
   surrounding code.
3. Establish the review base from locally available information. If the
   intended base or change set is ambiguous, state the ambiguity.
4. Trace behavior across files when contracts, configuration, generated
   artifacts, or dependencies cross boundaries.
5. Search the checkout for old and new identifiers when versions, APIs, paths,
   or configuration keys change.

REVIEW STANDARD

Assume important claims are unproven until supported by local code, tests, or
configuration. Do not accept linting, imports, lock generation, or unit tests as
evidence for behavior they do not exercise.

Review for:

- incorrect assumptions and incomplete state transitions;
- API, schema, serialization, CLI, and configuration compatibility;
- producer-consumer mismatches and missing call-site migrations;
- malformed, empty, optional, and boundary inputs;
- concurrency, retry, idempotency, ordering, cleanup, and rollback defects;
- broad catches, masked failures, warning-shaped success, and partial updates;
- trust-boundary violations, unsafe paths, shell inputs, deserialization, and
  credential exposure visible in the checkout;
- manifest/lock disagreement and incompatible dependency movement;
- stale documentation, examples, tests, or compatibility code made incorrect
  by the change;
- unrelated formatting, generated churn, temporary files, or scope expansion.

For deleted or renamed paths and symbols, search the checkout for remaining
live references. Inspect surrounding code rather than only changed lines.

VALIDATION INTEGRITY

Identify which local validation category would prove each important claim:
compile or syntax checks, lint or type checks, unit tests, integration tests,
startup smoke tests, migration tests, or runtime qualification. Passing one
category does not substitute for another. Never invent or infer validation
results.

OUTPUT

Report high-confidence correctness, security, reproducibility, and validation
issues first. For each finding include severity, confidence, exact local file
and line where applicable, affected behavior, failure scenario, evidence,
precise remediation, required verification, and whether it blocks acceptance.

Then provide a concise change-scope summary, local validation-evidence summary,
remaining unknowns, and final local-checkout readiness conclusion. If no
findings remain, say so only after completing the review. Always distinguish
local code readiness from unavailable remote CI, artifact, and approval state.
