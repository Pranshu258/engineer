# Technical evidence map

Turn a technical question into an auditable decision supported by traceable
local evidence. Do not confuse repetition or confident prose with proof.

Frame one falsifiable decision question, then record constraints, non-goals,
affected environments and users, acceptance criteria, and facts that would
reverse the recommendation.

Prefer current source code, tests, specifications, release artifacts available
in the checkout, repository documentation, and reproducible local results.
This runtime has no built-in web or remote GitHub access; explicitly mark
external evidence as unavailable rather than inventing it.

For each decision-relevant claim record the evidence, whether it supports,
contradicts, qualifies, or leaves the claim unproven, its applicability, and
whether it is observed, reported, inferred, or unverified. Preserve credible
counterevidence.

Check that evidence matches the relevant software versions, deployment model,
platform, workload, trust boundary, and operational requirements.

Provide the recommendation, strongest supporting evidence, strongest
counterargument, important unknowns, accepted tradeoffs, reversal conditions,
and the smallest experiment needed when evidence is insufficient. Do not force
a recommendation when a bounded experiment is the responsible next step.
