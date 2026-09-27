# Safe merge-conflict resolution

Resolve semantic intent, not just conflict markers. Preserve unrelated user
changes and require explicit authorization before irreversible actions.

Never discard changes with hard reset, forced checkout, or destructive cleanup
unless explicitly requested and approved. Never assume an uncommitted worktree
is disposable. Do not push, commit, abort an operation, or change the target
branch unless requested. Establish what ours and theirs mean in the current
operation before using those terms.

Inspect the current branch and commit, dirty and staged changes, active merge or
rebase state, conflict list and types, intended source and destination, and
whether unrelated work could be overwritten.

For each conflict reconstruct the base, our change, their change, surrounding
code and tests, and required combined behavior. Classify the resolution as keep
ours, keep theirs, combine independent changes, reconcile overlapping behavior,
regenerate with the owning tool, or defer because intent is ambiguous.

Apply the smallest semantic resolution. Preserve compatible behavior from both
sides, avoid unrelated cleanup, and keep generated files owned by their
generator.

Validate that no unmerged entries or conflict markers remain, patch integrity
is sound, focused checks cover combined behavior, and the final diff did not
drop unrelated work. Report resolved files, behavior preserved from each side,
validation, ambiguity, current Git operation state, and any remaining commit or
continuation step.
