"""Minimal interactive prompt helpers — arrow-key select, confirmations, styled output."""

from __future__ import annotations

import sys

# ANSI codes
DIM = "\033[2m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
CLEAR_LINE = "\033[2K"
UP = "\033[A"


def _raw_mode():
    """Context manager for raw terminal input (no echo, char-by-char)."""
    import contextlib
    import termios
    import tty

    @contextlib.contextmanager
    def _raw():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            yield
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    return _raw()


def _read_key() -> str:
    """Read a single keypress. Returns 'up', 'down', 'enter', or the character."""
    ch = sys.stdin.read(1)
    if ch == "\r" or ch == "\n":
        return "enter"
    if ch == "\x03":
        raise KeyboardInterrupt
    if ch == "\x1b":
        seq = sys.stdin.read(2)
        if seq == "[A":
            return "up"
        if seq == "[B":
            return "down"
    return ch


def select(label: str, choices: list[str]) -> str:
    """Arrow-key select menu. Returns the chosen string."""
    idx = 0
    n = len(choices)

    # Print label before entering raw mode
    sys.stdout.write(f"\n{BOLD}{label}{RESET}\n")
    sys.stdout.flush()

    # Print initial menu in normal mode, then switch to raw for input
    for i, choice in enumerate(choices):
        if i == idx:
            sys.stdout.write(f"  {CYAN}❯ {choice}{RESET}\n")  # noqa: RUF001
        else:
            sys.stdout.write(f"    {DIM}{choice}{RESET}\n")
    sys.stdout.flush()

    with _raw_mode():
        sys.stdout.write(HIDE_CURSOR)
        try:
            while True:
                key = _read_key()
                if key == "up":
                    idx = (idx - 1) % n
                elif key == "down":
                    idx = (idx + 1) % n
                elif key == "enter":
                    break
                else:
                    continue

                # Move cursor up n lines
                for _ in range(n):
                    sys.stdout.write(UP)

                # Redraw each line (use \r to go to column 0, clear line)
                for i, choice in enumerate(choices):
                    sys.stdout.write(f"\r{CLEAR_LINE}")
                    if i == idx:
                        sys.stdout.write(f"  {CYAN}❯ {choice}{RESET}")  # noqa: RUF001
                    else:
                        sys.stdout.write(f"    {DIM}{choice}{RESET}")
                    if i < n - 1:
                        sys.stdout.write("\r\n")
                sys.stdout.write("\r\n")
                sys.stdout.flush()
        finally:
            sys.stdout.write(SHOW_CURSOR)
            sys.stdout.flush()

    # Clear the menu and show selection
    for _ in range(n):
        sys.stdout.write(f"{UP}{CLEAR_LINE}")
    sys.stdout.write(f"  {GREEN}✓{RESET} {choices[idx]}\n\n")
    sys.stdout.flush()

    return choices[idx]


def confirm(label: str, default: bool = True) -> bool:
    """Y/n confirmation prompt."""
    hint = "Y/n" if default else "y/N"
    sys.stdout.write(f"  {BOLD}{label}{RESET} {DIM}({hint}){RESET} ")
    sys.stdout.flush()
    answer = input().strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def step_ok(msg: str):
    sys.stdout.write(f"  {GREEN}✓{RESET} {msg}\n")
    sys.stdout.flush()


def step_fail(msg: str):
    sys.stdout.write(f"  {RED}✗{RESET} {msg}\n")
    sys.stdout.flush()


def step_hint(msg: str):
    sys.stdout.write(f"    {DIM}{msg}{RESET}\n")
    sys.stdout.flush()


def header(msg: str):
    sys.stdout.write(f"\n  {BOLD}{msg}{RESET}\n\n")
    sys.stdout.flush()


def done(msg: str):
    sys.stdout.write(f"\n  {GREEN}{BOLD}{msg}{RESET}\n\n")
    sys.stdout.flush()
