from __future__ import annotations

import os
import asyncio
from collections import deque
from pathlib import Path
from typing import Deque, Tuple

from nicegui import ui

from backend.logger_setup import logger, LOG_TIME_FORMAT

LOG_FILE = Path(__file__).resolve().parents[1] / "main.log"


def _read_tail(path: Path, max_lines: int) -> Tuple[str, int]:
    """
    Read the last `max_lines` lines and return (text, end_position).
    """
    if not path.exists():
        return "", 0

    dq: Deque[str] = deque(maxlen=max_lines)
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            dq.append(line)
        pos = f.tell()
    return "".join(dq), pos


def _read_from(path: Path, pos: int) -> Tuple[str, int]:
    """
    Read from file starting at `pos` and return (new_text, new_pos).
    """
    if not path.exists():
        return "", 0

    with path.open("r", encoding="utf-8", errors="replace") as f:
        try:
            f.seek(pos)
        except Exception:
            f.seek(0)
        data = f.read()
        new_pos = f.tell()
    return data, new_pos


async def _follow_log(text_setter, lines_getter, interval_getter, tail_mode_getter) -> None:
    """
    Continuously stream the log file into a textarea, honoring UI controls.

    Parameters
    ----------
    text_setter : Callable[[str], None]
        Function to update the textarea value.
    lines_getter : Callable[[], int]
        Returns the max number of lines to keep.
    interval_getter : Callable[[], float]
        Returns the refresh interval in seconds.
    tail_mode_getter : Callable[[], bool]
        Returns True to start at EOF (tail), False to preload last N lines.
    """
    try:
        # wait until file exists (do not crash UI if file still not created)
        while not LOG_FILE.exists():
            await asyncio.sleep(0.5)

        if tail_mode_getter():
            buffer: Deque[str] = deque(maxlen=lines_getter())
            text, pos = "", os.path.getsize(LOG_FILE)
        else:
            text, pos = _read_tail(LOG_FILE, lines_getter())
            buffer = deque(text.splitlines(True), maxlen=lines_getter())

        text_setter("".join(buffer))

        while True:
            # detect truncation/rotation
            try:
                size = os.path.getsize(LOG_FILE)
            except FileNotFoundError:
                size = 0

            if pos > size:
                pos = 0

            chunk, pos = _read_from(LOG_FILE, pos)
            if chunk:
                for line in chunk.splitlines(True):
                    buffer.append(line)
                # if user changed "lines to keep", update maxlen on the fly
                if buffer.maxlen != lines_getter():
                    buffer = deque(buffer, maxlen=lines_getter())
                text_setter("".join(buffer))

            await asyncio.sleep(max(0.1, interval_getter()))
    except Exception as exc:
        logger.error(f"{LOG_TIME_FORMAT()} Live log stream stopped: {exc}", exc_info=True)


def create_ui() -> None:
    """
    Render a real-time NiceGUI viewer for main.log that starts automatically.
    """
    ui.label("Backend Log — Live Tail").classes("text-h5 text-bold mt-4 mb-2")

    controls = ui.row().classes("items-center gap-6")
    with controls:
        lines_input = ui.number(
            label="Lines to keep",
            value=300, min=50, max=5000, step=50
        )
        refresh_input = ui.number(
            label="Refresh (ms)",
            value=500, min=100, max=5000, step=100
        )
        mode_toggle = ui.toggle(
            ["Preload last N", "Tail (new only)"],
            value="Preload last N"
        )

    ta = ui.textarea(label="Live Log").classes("w-full h-96 mt-3")
    ta._props["readonly"] = True  # NiceGUI prop to make it read-only

    def set_text(s: str) -> None:
        ta.value = s

    def get_lines() -> int:
        try:
            return int(lines_input.value) if lines_input.value else 300
        except Exception:
            return 300

    def get_interval() -> float:
        try:
            return float(refresh_input.value) / 1000.0
        except Exception:
            return 0.5

    def is_tail_mode() -> bool:
        return mode_toggle.value == "Tail (new only)"

    # auto-start one background task after page is ready
    ui.timer(
        0.2,
        lambda: asyncio.create_task(_follow_log(set_text, get_lines, get_interval, is_tail_mode)),
        once=True,
    )
