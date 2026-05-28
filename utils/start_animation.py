import random
import shutil
import sys
import time
import concurrent.futures

FRAME_DELAY        = 0.08
SCATTER_STEPS      = 8
FUSION_STEPS       = 6
GLITCH_REPEATS     = 4
BOOT_LINE_DELAY    = 0.045
FINAL_HOLD         = 0.6
MIN_WIDTH          = 60
CHECK_TIMEOUT      = 9

CYAN    = "\033[96m"
TCYAN   = "\033[36m"
YELLOW  = "\033[93m"
GOLD    = "\033[33m"
WHITE   = "\033[97m"
GREY    = "\033[37m"
DIM     = "\033[2m"
BOLD    = "\033[1m"
ITALIC  = "\033[3m"
RED     = "\033[91m"
GREEN   = "\033[92m"
MAGENTA = "\033[95m"
RESET   = "\033[0m"

HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
CLEAR_LINE  = "\033[2K"
CURSOR_UP   = "\033[1A"

LOGO_LINES = [
    r" _   _ _____ _     ___ _   _ __  __ ",
    r"| | | | ____| |   |_ _| | | |  \/  |",
    r"| |_| |  _| | |    | || | | | |\/| |",
    r"|  _  | |___| |___ | || |_| | |  | |",
    r"|_| |_|_____|_____|___|\___/|_|  |_|",
]

_GLITCH = list("▓▒░█▄▀■□◆◇⬛⬜╬╪╫╦╩╠═║╔╗╚╝")

def _visible_len(text: str) -> int:
    length, in_escape = 0, False
    for ch in text:
        if ch == "\033":
            in_escape = True; continue
        if in_escape:
            if ch == "m": in_escape = False
            continue
        length += 1
    return length


def _center(text: str, width: int) -> str:
    pad = max(0, (width - _visible_len(text)) // 2)
    return " " * pad + text


def _write_frame(
    lines: list[str],
    width: int,
    *,
    previous_height: int,
    clear_extra: int = 0,
) -> None:
    if previous_height:
        sys.stdout.write(CURSOR_UP * previous_height)
    for line in lines:
        sys.stdout.write(f"{CLEAR_LINE}{_center(line, width)}\n")
    for _ in range(clear_extra):
        sys.stdout.write(f"{CLEAR_LINE}\n")
    sys.stdout.flush()


def _glitch_line(line: str) -> str:
    """Randomly corrupt ~15 % of characters with block glyphs."""
    out = []
    for ch in line:
        if ch != " " and random.random() < 0.15:
            out.append(random.choice(_GLITCH))
        else:
            out.append(ch)
    return "".join(out)



def _scatter_frames() -> list[list[str]]:
    """Two protons drift together across a wide field."""
    width_field = 32
    proton = f"{YELLOW}◉{RESET}"
    trail  = f"{DIM}{GOLD}·{RESET}"

    frames = []
    positions = [
        (0,  width_field - 1),
        (3,  width_field - 4),
        (7,  width_field - 8),
        (11, width_field - 12),
        (14, width_field - 15),
        (15, width_field - 16),
        (16, 16),
        (16, 16),
    ]
    for step, (left, right) in enumerate(positions):
        row = [" "] * (width_field + 1)
        for t in range(left):
            row[t] = "·"
        for t in range(right + 1, width_field + 1):
            row[t] = "·"
        row[left]  = "P"
        row[right] = "P"
        plain = "".join(row)

        coloured = ""
        for i, ch in enumerate(plain):
            if ch == "P":
                coloured += proton
            elif ch == "·":
                coloured += trail
            else:
                coloured += " "

        energy = step / (len(positions) - 1)
        bar_len = 20
        filled = int(energy * bar_len)
        bar = (f"{YELLOW}{'█' * filled}{RESET}"
               f"{DIM}{'░' * (bar_len - filled)}{RESET}")
        label = f"{DIM}binding energy  [{RESET}{bar}{DIM}]{RESET}"

        frames.append([
            f"{DIM}── proton approach ──{RESET}",
            coloured,
            label,
        ])
    return frames



_BURST_FRAMES = [
    (["    +    ", "   +++   ", "  +++++  ", "  +++++  ", "   +++   ", "    +    "],
     YELLOW, "quantum tunnelling…"),
    (["   ***   ", "  *****  ", " ******* ", " ******* ", "  *****  ", "   ***   "],
     GOLD,   "nuclear force engaged"),
    (["  \\|/|\\  ", " --◉◉◉-- ", "  /|\\|/  "],
     WHITE,  "FUSION EVENT"),
    (["   (( ))  ", "  (( ◎ )) ", "   (( ))  "],
     CYAN,   "helium-4 forming"),
]


def _burst_frames() -> list[list[str]]:
    frames = []
    for shell, colour, label in _BURST_FRAMES:
        frame = [f"{colour}{line}{RESET}" for line in shell]
        frame.append(f"{DIM}{label}{RESET}")
        frames.append(frame)
    return frames



def _logo_frames() -> list[list[str]]:
    """Return frames: several glitched passes then a clean final logo."""
    frames = []

    for _ in range(GLITCH_REPEATS):
        glitched = [f"{MAGENTA}{_glitch_line(l)}{RESET}" for l in LOGO_LINES]
        frames.append(glitched)

    for reveal in range(1, len(LOGO_LINES) + 1):
        mixed = []
        for i, line in enumerate(LOGO_LINES):
            if i >= len(LOGO_LINES) - reveal:
                mixed.append(f"{BOLD}{CYAN}{line}{RESET}")
            else:
                mixed.append(f"{DIM}{TCYAN}{_glitch_line(line)}{RESET}")
        frames.append(mixed)

    clean = [f"{BOLD}{CYAN}{l}{RESET}" for l in LOGO_LINES]
    clean.append("")
    clean.append(f"{DIM}{'─' * 38}{RESET}")
    clean.append(
        f"  {TCYAN}◉{RESET} {ITALIC}{DIM}local-first AI assistant  "
        f"{GREY}v0.1{RESET}  {TCYAN}◉{RESET}"
    )
    clean.append(f"{DIM}{'─' * 38}{RESET}")
    frames.append(clean)

    return frames

from utils.system_check import check_internet_connectivity, check_llm_api, check_memory, check_tools, check_rag


def _future_ok(
    future: concurrent.futures.Future,
    name: str,
    *,
    timeout: float = CHECK_TIMEOUT,
) -> bool:
    try:
        return bool(future.result(timeout=timeout))
    except concurrent.futures.TimeoutError:
        print(f"{name} check timed out.")
        return False
    except Exception as exc:
        print(f"{name} check failed: {exc}")
        return False

def _render_boot_lines(width: int, *, previous_height: int, boot_checks: list) -> None:
    """Type out boot check lines one by one, in place."""
    logo_block_height = len(LOGO_LINES) + 4
    lines_so_far: list[str] = []

    for name, colour, status in boot_checks:
        dots = "." * (28 - len(name))
        line = (
            f"  {DIM}{name}{RESET}"
            f"{DIM}{dots}{RESET}"
            f" {colour}{BOLD}{status}{RESET}"
        )
        lines_so_far.append(line)

        if previous_height:
            sys.stdout.write(CURSOR_UP * previous_height)
        for l in lines_so_far:
            sys.stdout.write(f"{CLEAR_LINE}{_center(l, width)}\n")
        for _ in range(len(boot_checks) - len(lines_so_far)):
            sys.stdout.write(f"{CLEAR_LINE}\n")
        sys.stdout.flush()
        previous_height = len(boot_checks)

        time.sleep(BOOT_LINE_DELAY)

    sys.stdout.write(CURSOR_UP * previous_height)
    for l in lines_so_far:
        sys.stdout.write(f"{CLEAR_LINE}{_center(l, width)}\n")
    sys.stdout.write(
        f"{CLEAR_LINE}"
        + _center(f"{BOLD}{GREEN}● all systems nominal{RESET}", width)
        + "\n"
    )
    sys.stdout.flush()
    time.sleep(FINAL_HOLD)



def render_startup_intro(*, animated: bool = True) -> None:
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
    fut_tools = executor.submit(check_tools)
    fut_internet = executor.submit(check_internet_connectivity)
    fut_llm = executor.submit(check_llm_api)
    fut_memory = executor.submit(check_memory)
    fut_rag = executor.submit(check_rag)

    width = shutil.get_terminal_size((80, 24)).columns

    if not sys.stdout.isatty() or not animated or width < MIN_WIDTH:
        sys.stdout.write(f"{CYAN}{BOLD}HELIUM AGENT{RESET}\n")
        sys.stdout.flush()
        return

    sys.stdout.write(HIDE_CURSOR)
    previous_height = 0

    try:
        for frame in _scatter_frames():
            _write_frame(frame, width, previous_height=previous_height)
            previous_height = len(frame)
            time.sleep(FRAME_DELAY * 1.5)

        for frame in _burst_frames():
            _write_frame(frame, width, previous_height=previous_height,
                         clear_extra=max(0, previous_height - len(frame)))
            previous_height = len(frame)
            time.sleep(FRAME_DELAY * 2)

        logo_frames = _logo_frames()
        for i, frame in enumerate(logo_frames):
            delay = FRAME_DELAY if i < GLITCH_REPEATS else FRAME_DELAY * 1.8
            _write_frame(frame, width, previous_height=previous_height,
                         clear_extra=max(0, previous_height - len(frame)))
            previous_height = len(frame)
            time.sleep(delay)

        boot_checks = [
            ("kernel interface", GREEN, "ok"),
            ("tool registry", GREEN, "ok") if _future_ok(fut_tools, "tool registry") else ("tool registry", RED, "fail"),
            ("memory subsystem", GREEN, "ok") if _future_ok(fut_memory, "memory subsystem") else ("memory subsystem", RED, "fail"),
            ("inference engine", GREEN, "ok") if _future_ok(fut_llm, "inference engine") else ("inference engine", RED, "fail"),
            ("session context", GREEN, "ready"),
            ("search access", GREEN, "ready") if _future_ok(fut_internet, "search access") else ("search access", RED, "offline"),
            ("retrieval augmented generation", GREEN, "ok") if _future_ok(fut_rag, "retrieval augmented generation") else ("retrieval augmented generation", RED, "fail"),
        ]

        for _ in range(len(boot_checks) + 1):
            sys.stdout.write(f"{CLEAR_LINE}\n")
        sys.stdout.flush()
        _render_boot_lines(width, previous_height=len(boot_checks) + 1, boot_checks=boot_checks)

    finally:
        executor.shutdown(wait=False)
        sys.stdout.write(SHOW_CURSOR)
        sys.stdout.flush()


def main() -> None:
    render_startup_intro()
    sys.stdout.write(f"\n{BOLD}{CYAN}helium{RESET}{DIM}>{RESET} ")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
