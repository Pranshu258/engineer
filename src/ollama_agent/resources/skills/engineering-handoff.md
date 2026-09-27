# Engineering handoff

Preserve the information required to continue safely. A handoff is not a
chronological transcript and must not turn uncertain claims into facts.

Preserve exact paths, symbols, commit identifiers, commands, and error text
where precision matters. Distinguish executed evidence from reported or
inferred information. Preserve the original goal, acceptance criteria, and
explicit exclusions. Record rejected alternatives only when they prevent
repeated work. Do not include secrets, tokens, customer data, or unnecessary
private information.

Include:

1. Goal, acceptance criteria, non-goals, and safety constraints.
2. Current state: complete, active, blocked, and not started work; relevant Git
   state and identifiers.
3. Repository evidence grouped as modified, created, deleted or renamed, and
   materially read files.
4. Important decisions with reason, evidence, rejected alternative, and
   reversal condition.
5. Commands whose results matter, clearly distinguishing executed from pending
   validation.
6. Failures, established root causes, disproved hypotheses, unverified
   assumptions, and operational or data-loss risks.
7. Smallest next actions in dependency order, identifying steps that require
   user input or approval.

End with three to five continuation probes that a receiving engineer should be
able to answer from the handoff. Default to presenting it in chat; write a file
only when requested.
