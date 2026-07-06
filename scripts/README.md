# Scripts

Use this folder for deploy helpers, audit scripts, patchers, and maintenance tools.

Current migration rule:

- Existing root scripts remain in place so the current Termux `titan` command does not break.
- New scripts should be added here first.
- After full testing, root scripts can be replaced by small wrappers that call files from this folder.
