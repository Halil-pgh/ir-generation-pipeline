# Semantics

Behaviour the schemas leave open is decided here, once, and every part of
the pipeline (front-end, checks, backends) follows it. When the spec and
this file disagree, this file wins until the spec is fixed.

## Issues

- A problem in a picture is an **issue**, never an exception. Its code
  (`E-SUBTITLE`) is defined once, in `ISSUE_CODES`, by the module that
  reports it. Reporting an unregistered code is a bug in that stage.
- The first letter of a code is its severity: `E-` error, `W-` warning.
  There are no other severities.
- Every code has an **origin**: `ir`, `capability`, `internal`,
  `environment` or `infeasible`. The origin belongs to the code, not to
  one issue, so an issue of a given code always goes to the same place.
- `path` is a JSON path into the IR written as `objects[3].size`;
  `objects` lists the ids involved, or a part of one such as `v.label`.

## Stopping a run

- A stage either writes every artifact it promised, or reports at least
  one error that says why it could not. In the second case the run stops
  after that stage, with status `STOPPED`.
- A stage that reports errors but still writes its outputs (a lint check)
  does not stop the run: the picture is still drawn, problems included.

## READY

A picture is `READY` when every stage ran and no issue is open: no
errors (an error can never be accepted), and every warning fixed or
accepted with an `allow` entry.
Otherwise it is `NOT_READY` (every stage ran) or `STOPPED` (one could not
go on). Allowed issues stay in the report, marked with their reason.

## `allow`

An entry `{"code", "objects", "reason"}` accepts issues on purpose.

- It matches an issue when the codes are equal and **every** object it
  names covers at least one object of the issue.
- An id covers itself and its parts: `v` covers `v` and `v.label`, but
  not `vx`. A group id covers everything inside it (from step 6 on, when
  groups exist).
- An entry with no objects matches only issues that name no objects,
  such as one about the picture as a whole. It is never a blanket pass
  for a whole code.
- Only codes defined as `allowable` can be accepted, and only warnings
  of origin `ir` can be allowable. An entry that names any other code is
  an `E-ALLOW` error and accepts nothing.
- The reason needs at least four words, so stock answers such as "ok"
  or "this is intended" do not pass. Each issue is accepted by the first
  entry that matches it.
