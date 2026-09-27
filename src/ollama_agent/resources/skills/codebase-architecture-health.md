# Codebase architecture health

Produce a read-only model of how a repository or subsystem works. Separate
verified implementation facts from inferred intent and possible concerns.

Choose the smallest useful scope: repository, package or service, one execution
path, or one cross-cutting concern. For monorepos, do not inventory every
package unless requested.

Prefer evidence in this order: executed code and tests; build and runtime
configuration; dependency manifests; repository instructions; documentation;
naming or structural inference. Mark claims as observed, inferred, or unknown.

Identify entry points, packages and processes, public interfaces, data and
control flows, persistence and external dependencies, build and test paths,
trust boundaries, and documented ownership boundaries. Describe important
flows as trigger to entry point to orchestration to domain behavior to output.

Treat metrics and structure as investigation leads, not findings. For each
evidence-backed concern include exact files or symbols, affected behavior,
concrete failure or maintenance scenario, confidence, and the smallest
reasonable improvement direction. Do not automatically turn observations into
implementation work.

Default to an in-chat report. Do not copy secrets, private URLs, credentials,
customer identifiers, or large proprietary excerpts. Provide scope and
confidence, component map, important flows, strengths, risks, and unknowns.
