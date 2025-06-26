class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'

    # Standard colors
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'

    # Bright colors
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'


def _print(color_code: str, message: str, *, bold: bool = False, stream=None):
    """Internal helper to print colored output."""
    if stream is None:
        import sys
        stream = sys.stdout
    bold_code = Colors.BOLD if bold else ""
    print(f"{color_code}{bold_code}{message}{Colors.RESET}", file=stream)


def print_section(message: str):
    """Print a section header in bright cyan with bold."""
    _print(Colors.BRIGHT_CYAN, message, bold=True)


def print_subsection(message: str):
    """Print a subsection header in cyan."""
    _print(Colors.CYAN, message)


def print_success(message: str):
    """Print a success message in green."""
    _print(Colors.GREEN, message)


def print_warning(message: str):
    """Print a warning message in yellow (to stderr)."""
    import sys
    _print(Colors.YELLOW, f"Warning: {message}", stream=sys.stderr)


def print_error(message: str):
    """Print an error message in red (to stderr)."""
    import sys
    _print(Colors.RED, f"Error: {message}", stream=sys.stderr)


def print_result(message: str):
    """Print a result message in bright green with bold."""
    _print(Colors.BRIGHT_GREEN, message, bold=True)


def print_build_info(message: str):
    """Print build-related info in blue."""
    _print(Colors.BLUE, message) 