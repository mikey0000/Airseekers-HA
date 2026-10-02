# Contributing

1. Read `CONSTITUTION.md` here and pyairseekers' `CONSTITUTION.md`.
2. Need a new endpoint or topic? Add it to pyairseekers first (its
   `docs/architecture.md` §4), release, then bump the requirement here.
3. New entity: an entity description in the platform module, a translation
   key in `strings.json` (copied to `translations/en.json`), the right base
   class (`AirseekersTronEntity` for local reads, `AirseekersCloudEntity` for
   cloud writes).
4. New non-obvious choice: a numbered entry in `docs/decisions.md`.
5. `pre-commit run --all-files` is green.
6. Commits: imperative subject line, one change per commit, no attribution
   trailers.

## Pull request checklist

- [ ] Reads come from the local coordinator, writes from the cloud coordinator.
- [ ] Commands go through `async_command`; failures surface as errors.
- [ ] No secret can reach a log, attribute, or exception.
- [ ] Tests assert behaviour with hand-written fakes.
- [ ] `docs/` updated where the change alters behaviour or rules.
