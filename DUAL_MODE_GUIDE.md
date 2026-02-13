# Dual-Mode Feature Guide

AutoRXTE supports BOTH interactive and scriptable modes. You choose!

## Interactive Mode (Default)

Perfect for exploration and one-off analyses:

```python
from autorxte.core.download import search_and_download

# Just call with no arguments - it will prompt you
search_and_download()
```

Or from command line:
```bash
python -m autorxte.core.01_download
# Will prompt: "Source name or coordinates: "
# Will prompt: "Search radius (arcmin) [5.0]: "
# etc.
```

## Scripted Mode

Perfect for automation and batch processing:

```python
# Pass all arguments, set interactive=False
search_and_download(
    source="Cyg X-1",
    catalog="xtemaster",
    radius=5.0,
    top_n=5,
    output_dir="./data",
    interactive=False  # No prompts!
)
```

Or from command line:
```bash
python -m autorxte.core.01_download \
    --source "Cyg X-1" \
    --top-n 5 \
    --no-interactive
```

## Mixed Mode

You can also provide some arguments and let it prompt for the rest:

```python
# Provide source, prompt for everything else
search_and_download(source="Cyg X-1")
# Will prompt for: radius, filters, what to download, etc.
```

## How It Works

Every function follows this pattern:

```python
def some_function(
    param1: Optional[Type] = None,
    param2: Optional[Type] = None,
    interactive: bool = True
):
    if interactive:
        # Prompt for any None parameters
        param1 = get_input("Prompt", default, param1)
        param2 = get_input("Prompt", default, param2)
    else:
        # Use defaults for None parameters
        param1 = param1 or default_value
        param2 = param2 or default_value
    
    # Rest of function uses param1, param2
```

## Command Line Flags

All modules support:
- `--no-interactive` - Disable all prompts
- Arguments for each parameter
- If arg provided: use it
- If arg missing + interactive: prompt
- If arg missing + no-interactive: use default

## Best Practices

**Use Interactive Mode When:**
- Exploring new data
- One-off analysis
- Learning the workflow
- Testing parameters

**Use Scripted Mode When:**
- Batch processing
- Automation scripts
- Reproducible pipelines
- CI/CD integration

## Tab Completion

In interactive mode, file paths have bash-style tab completion!
Just start typing and press Tab.
