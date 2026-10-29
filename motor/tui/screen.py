"""Cross-platform raw alternate-screen (`?1049h`) terminal driver (`termios` / `msvcrt`)."""

from __future__ import annotations

import atexit
import codecs
from collections.abc import Sequence
import os
import select
import signal
import sys
import time

from ..core.i18n import Style, get_term_size, pad_right, truncate_ansi

try:
    import termios  # type: ignore[import-not-found]
    _HAS_TERMIOS = True
except ImportError:
    termios = None  # type: ignore[assignment]
    _HAS_TERMIOS = False

try:
    import msvcrt  # type: ignore[import-not-found]
    _HAS_MSVCRT = True
except ImportError:
    msvcrt = None  # type: ignore[assignment]
    _HAS_MSVCRT = False


class TuiScreen:
    """Cross-platform alternate-screen ANSI windowing driver with zero-flicker frame buffer."""

    def __init__(self, use_color: bool = True) -> None:
        self.use_color = use_color
        self.st = Style(use_color)
        self._active = False
        self._fd: int | None = None
        self._old_termios = None
        self._old_sigwinch = None
        self._resized = False
        self._last_size = (120, 34)
        self._utf8_dec = codecs.getincrementaldecoder("utf-8")("replace")
        self._pending_bytes = bytearray()

    def __enter__(self) -> TuiScreen:
        self.enter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.leave()

    def enter(self) -> None:
        if self._active:
            return
        if _HAS_TERMIOS and sys.stdin.isatty():
            fd = sys.stdin.fileno()
            self._fd = fd
            self._old_termios = termios.tcgetattr(fd)
            new_attr = termios.tcgetattr(fd)
            new_attr[0] &= ~(termios.IXON | termios.ICRNL)
            new_attr[3] &= ~(termios.ICANON | termios.ECHO)
            new_attr[6][termios.VMIN] = 1
            new_attr[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSADRAIN, new_attr)

        if hasattr(signal, "SIGWINCH"):
            try:
                self._old_sigwinch = signal.getsignal(signal.SIGWINCH)
                signal.signal(signal.SIGWINCH, self._on_sigwinch)
            except (OSError, ValueError):
                self._old_sigwinch = None

        self._active = True
        atexit.register(self.leave)
        self._last_size = get_term_size()
        sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[?2004h\x1b[2J\x1b[H")
        sys.stdout.flush()

    def leave(self) -> None:
        if not self._active:
            return
        self._active = False
        try:
            sys.stdout.write("\x1b[0m\x1b[?2004l\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()
        except OSError:
            pass
        if self._fd is not None and self._old_termios is not None and _HAS_TERMIOS:
            try:
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_termios)
            except OSError:
                pass
            self._fd = None
            self._old_termios = None
        if hasattr(signal, "SIGWINCH") and self._old_sigwinch is not None:
            try:
                signal.signal(signal.SIGWINCH, self._old_sigwinch)
            except (OSError, ValueError):
                pass
            self._old_sigwinch = None

    def _on_sigwinch(self, _signum: int, _frame) -> None:
        self._resized = True

    def size(self) -> tuple[int, int]:
        sz = get_term_size()
        self._last_size = sz
        return sz

    def draw_rows(self, rows_buf: Sequence[str], top_bar_sgr: str = "", bot_bar_sgr: str = "") -> None:
        """Flush a full screen frame in one write without bottom-right scroll wrap."""
        cols, rows = self.size()
        out: list[str] = ["\x1b[?25l"]
        total_r = min(rows, len(rows_buf))
        for r in range(total_r):
            ln = rows_buf[r]
            if r == 0 and top_bar_sgr and self.use_color:
                vis = truncate_ansi(ln, cols - 1, "")
                out.append(f"\x1b[1;1H{top_bar_sgr}{pad_right(vis, cols - 1)}\x1b[K\x1b[0m")
            elif r == rows - 1 and bot_bar_sgr and self.use_color:
                vis = truncate_ansi(ln, cols - 1, "")
                out.append(f"\x1b[{r + 1};1H{bot_bar_sgr}{pad_right(vis, cols - 1)}\x1b[K\x1b[0m")
            elif r == rows - 1:
                vis = truncate_ansi(ln, max(1, cols - 1), "")
                out.append(f"\x1b[{r + 1};1H{vis}\x1b[0m\x1b[K")
            else:
                vis = truncate_ansi(ln, cols, "")
                out.append(f"\x1b[{r + 1};1H{vis}\x1b[0m\x1b[K")
        for r in range(total_r, rows):
            out.append(f"\x1b[{r + 1};1H\x1b[0m\x1b[K")
        sys.stdout.write("".join(out))
        sys.stdout.flush()

    def _read_raw_byte(self, timeout: float | None) -> int | None:
        if self._pending_bytes:
            return self._pending_bytes.pop(0)
        if _HAS_TERMIOS and self._fd is not None:
            try:
                rlist, _, _ = select.select([self._fd], [], [], timeout)
            except InterruptedError:
                return None
            if not rlist:
                return None
            try:
                chunk = os.read(self._fd, 1024)
            except InterruptedError:
                return None
            if not chunk:
                raise EOFError
            self._pending_bytes.extend(chunk)
            return self._pending_bytes.pop(0)
        if _HAS_MSVCRT:
            deadline = None if timeout is None else (time.monotonic() + timeout)
            while True:
                if msvcrt.kbhit():  # type: ignore[union-attr]
                    ch_b = msvcrt.getch()  # type: ignore[union-attr]
                    if ch_b in (b"\x00", b"\xe0"):
                        ch2 = msvcrt.getch()  # type: ignore[union-attr]
                        win_map = {
                            b"H": b"\x1b[A",
                            b"P": b"\x1b[B",
                            b"M": b"\x1b[C",
                            b"K": b"\x1b[D",
                            b"G": b"\x1b[H",
                            b"O": b"\x1b[F",
                            b"I": b"\x1b[5~",
                            b"Q": b"\x1b[6~",
                            b"S": b"\x1b[3~",
                            b"<": b"\x1bOQ",
                        }
                        seq = win_map.get(ch2, b"")
                        if seq:
                            self._pending_bytes.extend(seq)
                            return self._pending_bytes.pop(0)
                        continue
                    self._pending_bytes.extend(ch_b)
                    return self._pending_bytes.pop(0)
                if deadline is not None and time.monotonic() >= deadline:
                    return None
                time.sleep(0.01)
        data = sys.stdin.buffer.read(1)
        if not data:
            raise EOFError
        return data[0]

    def read_event(self, timeout: float = 0.15) -> tuple[str, str]:
        """Read next keyboard, bracketed-paste, or resize event -> `(kind, value)`."""
        while True:
            if self._resized or get_term_size() != self._last_size:
                self._resized = False
                self._last_size = get_term_size()
                return ("RESIZE", "")

            b = self._read_raw_byte(timeout)
            if b is None:
                continue

            if b == 0x03:
                raise KeyboardInterrupt
            if b == 0x04:
                raise EOFError
            if b in (0x0D, 0x0A):
                if b == 0x0D and self._pending_bytes and self._pending_bytes[0] == 0x0A:
                    self._pending_bytes.pop(0)
                return ("KEY", "ENTER")
            if b == 0x09:
                return ("KEY", "TAB")
            if b in (0x7F, 0x08):
                return ("KEY", "BACKSPACE")
            if b == 0x15:
                return ("KEY", "CTRL_U")
            if b == 0x07:
                return ("KEY", "CTRL_G")
            if b == 0x1B:
                return self._parse_escape()

            if b < 0x20:
                continue

            s = self._utf8_dec.decode(bytes([b]), final=False)
            while not s:
                nb = self._read_raw_byte(0.05)
                if nb is None:
                    s = self._utf8_dec.decode(b"", final=True)
                    self._utf8_dec.reset()
                    break
                s = self._utf8_dec.decode(bytes([nb]), final=False)
            if s:
                return ("CHAR", s)

    def _parse_escape(self) -> tuple[str, str]:
        b1 = self._read_raw_byte(0.035)
        if b1 is None or b1 == 0x1B:
            return ("KEY", "ESC")

        if b1 == ord("["):
            seq_chars: list[str] = []
            while len(seq_chars) < 16:
                bn = self._read_raw_byte(0.035)
                if bn is None:
                    break
                ch = chr(bn)
                seq_chars.append(ch)
                if "A" <= ch <= "Z" or "a" <= ch <= "z" or ch == "~":
                    break
            seq = "".join(seq_chars)
            if seq == "200~":
                return ("PASTE", self._read_bracketed_paste())
            csi_map = {
                "A": "UP",
                "B": "DOWN",
                "C": "RIGHT",
                "D": "LEFT",
                "H": "HOME",
                "F": "END",
                "Z": "SHIFT_TAB",
                "1~": "HOME",
                "4~": "END",
                "7~": "HOME",
                "8~": "END",
                "5~": "PGUP",
                "6~": "PGDN",
                "3~": "DELETE",
                "11~": "F1",
                "12~": "F2",
            }
            if seq in csi_map:
                return ("KEY", csi_map[seq])
            if seq.endswith("A"):
                return ("KEY", "UP")
            if seq.endswith("B"):
                return ("KEY", "DOWN")
            if seq.endswith("C"):
                return ("KEY", "RIGHT")
            if seq.endswith("D"):
                return ("KEY", "LEFT")
            return ("KEY", "UNKNOWN")

        if b1 == ord("O"):
            b2 = self._read_raw_byte(0.035)
            if b2 is not None:
                ss3_map = {
                    "A": "UP",
                    "B": "DOWN",
                    "C": "RIGHT",
                    "D": "LEFT",
                    "H": "HOME",
                    "F": "END",
                    "P": "F1",
                    "Q": "F2",
                }
                ch2 = chr(b2)
                if ch2 in ss3_map:
                    return ("KEY", ss3_map[ch2])
            return ("KEY", "UNKNOWN")

        return ("KEY", "ESC")

    def _read_bracketed_paste(self) -> str:
        buf = bytearray()
        end_sig = b"\x1b[201~"
        while len(buf) < 65536:
            bn = self._read_raw_byte(0.10)
            if bn is None:
                break
            buf.append(bn)
            if buf.endswith(end_sig):
                del buf[-len(end_sig) :]
                break
        return buf.decode("utf-8", errors="replace")
