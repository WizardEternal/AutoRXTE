"""Interactive input utilities with fallback to function arguments."""

import glob
from pathlib import Path
from typing import Optional, List, Any


# Enable bash-style tab completion if available
try:
    import readline
    readline.parse_and_bind("tab: complete")
    
    def path_completer(text, state):
        matches = glob.glob(text + "*")
        return matches[state] if state < len(matches) else None
    
    readline.set_completer(path_completer)
except ImportError:
    pass


def get_input(
    prompt: str,
    default: Optional[Any] = None,
    arg_value: Optional[Any] = None,
    converter=str,
    validator=None
) -> Any:
    """
    Get input from argument or interactively.
    
    Args:
        prompt: Prompt to display if interactive
        default: Default value if user enters nothing
        arg_value: Value passed as function argument (takes precedence)
        converter: Function to convert string input to desired type
        validator: Function to validate input (raises ValueError if invalid)
        
    Returns:
        The input value (from arg, user input, or default)
    """
    # If argument provided, use it
    if arg_value is not None:
        return arg_value
    
    # Otherwise, prompt interactively
    default_str = f" [{default}]" if default is not None else ""
    user_input = input(f"{prompt}{default_str}: ").strip()
    
    if not user_input and default is not None:
        return default
    
    if not user_input:
        return None
    
    # Convert and validate
    try:
        value = converter(user_input)
        if validator:
            validator(value)
        return value
    except (ValueError, TypeError) as e:
        print(f"Invalid input: {e}")
        return get_input(prompt, default, None, converter, validator)


def get_yes_no(prompt: str, default: bool = False, arg_value: Optional[bool] = None) -> bool:
    """Get yes/no input from argument or interactively."""
    if arg_value is not None:
        return arg_value
    
    default_str = " [y/n]" if default is None else f" [{'y' if default else 'n'}]"
    response = input(f"{prompt}{default_str}: ").strip().lower()
    
    if not response and default is not None:
        return default
    
    return response.startswith('y')


def get_path(prompt: str, default: Optional[Path] = None, arg_value: Optional[Path] = None) -> Path:
    """Get path input from argument or interactively."""
    if arg_value is not None:
        return Path(arg_value)
    
    default_str = f" [{default}]" if default is not None else ""
    user_input = input(f"{prompt}{default_str}: ").strip()
    
    if not user_input and default is not None:
        return Path(default)
    
    return Path(user_input) if user_input else None


def get_int(
    prompt: str,
    default: Optional[int] = None,
    arg_value: Optional[int] = None,
    min_val: Optional[int] = None,
    max_val: Optional[int] = None
) -> int:
    """Get integer input from argument or interactively."""
    if arg_value is not None:
        return arg_value
    
    def validator(val):
        if min_val is not None and val < min_val:
            raise ValueError(f"Must be >= {min_val}")
        if max_val is not None and val > max_val:
            raise ValueError(f"Must be <= {max_val}")
    
    return get_input(prompt, default, None, int, validator)


def get_float(
    prompt: str,
    default: Optional[float] = None,
    arg_value: Optional[float] = None,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None
) -> float:
    """Get float input from argument or interactively."""
    if arg_value is not None:
        return arg_value
    
    def validator(val):
        if min_val is not None and val < min_val:
            raise ValueError(f"Must be >= {min_val}")
        if max_val is not None and val > max_val:
            raise ValueError(f"Must be <= {max_val}")
    
    return get_input(prompt, default, None, float, validator)


def get_choice(
    prompt: str,
    choices: List[str],
    default: Optional[str] = None,
    arg_value: Optional[str] = None
) -> str:
    """Get choice from list of options."""
    if arg_value is not None:
        if arg_value not in choices:
            raise ValueError(f"Invalid choice: {arg_value}. Must be one of {choices}")
        return arg_value
    
    choices_str = "/".join(choices)
    default_str = f" [{default}]" if default else ""
    
    while True:
        user_input = input(f"{prompt} ({choices_str}){default_str}: ").strip().lower()
        
        if not user_input and default:
            return default
        
        if user_input in choices:
            return user_input
        
        print(f"Invalid choice. Must be one of: {', '.join(choices)}")
