# Interactive vs scripted mode

Every AutoRXTE subcommand can run interactively (it prompts you for
missing arguments) or non-interactively (you pass everything as flags
and it runs unattended). Mix and match: pass some flags, get prompted
for the rest.

## Interactive (default when something's missing)

```bash
autorxte download
# Source name or coordinates: GRS 1915+105
# Catalog [xtemaster]:
# Search radius (arcmin) [5.0]:
# Output directory [.]: ./data
# ...
```

Defaults are shown in `[brackets]`; press Enter to accept.

From Python:

```python
from autorxte.core import search_and_download

search_and_download()   # prompts for everything
```

## Scripted (`--no-interactive`)

```bash
autorxte download --source "Cyg X-1" --top-n 5 --directory ./data --no-interactive
```

Without `--no-interactive`, the CLI defaults to interactive mode
*only* when something's missing. With `--source` set, it stays
non-interactive even without the flag, and falls back to defaults for
the rest.

From Python:

```python
search_and_download(
    source="Cyg X-1",
    top_n=5,
    output_dir=Path("./data"),
    interactive=False,
)
```

## Mixing

Provide the args you want to pin, leave the rest to be prompted:

```bash
autorxte filter --directory ./data --filter '(ELV > 10) && (OFFSET < 0.02)'
# Parallel workers [8]:
# Skip obsids whose Analysis/good.gti already exists? [y]:
```

This is the most common mode in practice: you script the project-level
choices (directory, source, model) and let the runtime defaults handle
the rest.

## How it works under the hood

Each function follows the same pattern:

```python
def some_step(arg1=None, arg2=None, interactive=True):
    if interactive:
        arg1 = get_input("Prompt 1", default1, arg1)
        arg2 = get_input("Prompt 2", default2, arg2)
    else:
        arg1 = arg1 or default1
        arg2 = arg2 or default2
    ...
```

`get_input` returns its `arg_value` immediately when one is supplied;
otherwise it prompts. The CLI translates flags into `arg_value`s, so
"flag set" means "skip prompt". Boolean flags like `--no-rewrite` are
wired so that *not passing* the flag leaves the parameter as `None`
(prompt fires); *passing* the flag forces `False` (prompt skipped, value
forced).

If a prompt you expect doesn't fire in interactive mode, the most likely
cause is that the function or CLI is passing a concrete value where it
should pass `None`.

## Tab completion

Path prompts have bash-style tab completion via `readline`. Type a
partial path and press Tab.
