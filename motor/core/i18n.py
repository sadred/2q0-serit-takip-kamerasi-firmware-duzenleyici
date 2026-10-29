"""Bilingual RU/EN localization, authorship credits, ANSI SGR styling, and terminal width/wrapping helpers."""

from __future__ import annotations

from collections.abc import Sequence
import os
import re
import shutil
import subprocess
import sys
import unicodedata


AUTHOR_CREDIT = "Made by PerkTheFox"
AUTHOR_SITE_URL = "https://vwhacking.antonperk.com"
AUTHOR_SITE_SHORT = "vwhacking.antonperk.com"
AUTHOR_DRIVE2_URL = "https://www.drive2.ru/users/perkthefox/"
AUTHOR_TG_URL = "https://t.me/perkthefox"
TOOLKIT_SHORT_NAME = "Schutz-Kaput"
TOOLKIT_NAME = "Schutz-Kaput • CP & SWaP"
TOOLKIT_VERSION = "2.0"

_LANG: str = "ru"

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_SGR_TOKEN_RE = re.compile(r"\x1b\[([0-9;]*)m|([^\x1b]+)|\x1b\[[0-9;?]*[A-Za-z]|\x1b.")


def normalize_lang_code(raw: str | None) -> str | None:
    if raw is None:
        return None
    val = raw.strip().lower()
    if val in ("ru", "rus", "russian", "р", "ру", "рус", "русский", "1"):
        return "ru"
    if val in ("en", "eng", "english", "англ", "2"):
        return "en"
    return None


def set_lang(lang: str) -> str:
    global _LANG
    norm = normalize_lang_code(lang)
    if norm not in ("ru", "en"):
        raise ValueError(f"Unsupported language / Неподдерживаемый язык: {lang!r} (use 'ru' or 'en')")
    _LANG = norm
    return _LANG


def get_lang() -> str:
    return _LANG


def tr(ru: str, en: str) -> str:
    """Return Russian or English string depending on active language."""
    return en if _LANG == "en" else ru


def detect_early_cli_lang(argv: Sequence[str]) -> str | None:
    """Inspect argv / environment before building argparse so even --help is localized."""
    for i, arg in enumerate(argv):
        if arg in ("-l", "--lang") and i + 1 < len(argv):
            norm = normalize_lang_code(argv[i + 1])
            if norm:
                return norm
        elif arg.startswith("--lang="):
            norm = normalize_lang_code(arg.split("=", 1)[1])
            if norm:
                return norm
    return normalize_lang_code(os.environ.get("KS_PATCHER_LANG") or os.environ.get("CONTI_CP_LANG"))


class Style:
    """ANSI SGR terminal styling matching `conti_cp_tool.py`."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def _c(self, code: str, text: str) -> str:
        return f"\x1b[{code}m{text}\x1b[0m" if self.enabled else text

    def bold(self, t: str) -> str:
        return self._c("1", t)

    def dim(self, t: str) -> str:
        return self._c("2", t)

    def cyan(self, t: str) -> str:
        return self._c("1;36", t)

    def green(self, t: str) -> str:
        return self._c("1;32", t)

    def yellow(self, t: str) -> str:
        return self._c("1;33", t)

    def red(self, t: str) -> str:
        return self._c("1;31", t)

    def blue(self, t: str) -> str:
        return self._c("1;34", t)

    def magenta(self, t: str) -> str:
        return self._c("1;35", t)

    def white(self, t: str) -> str:
        return self._c("1;37", t)

    def inv(self, t: str) -> str:
        return self._c("7", t)

    def sel(self, t: str) -> str:
        return f"\x1b[1;30;46m{t}\x1b[0m" if self.enabled else t

    def sel_green(self, t: str) -> str:
        return f"\x1b[1;30;42m{t}\x1b[0m" if self.enabled else t

    def sel_warn(self, t: str) -> str:
        return f"\x1b[1;30;43m{t}\x1b[0m" if self.enabled else t

    def sel_danger(self, t: str) -> str:
        return f"\x1b[1;37;41m{t}\x1b[0m" if self.enabled else t


def get_term_size(fallback: tuple[int, int] = (120, 34)) -> tuple[int, int]:
    """Return current (columns, lines) of the attached terminal."""
    for stream in (sys.__stdout__, sys.stdout, sys.__stderr__, sys.stderr):
        if stream is not None:
            try:
                if stream.isatty():
                    sz = os.get_terminal_size(stream.fileno())
                    if sz.columns > 0 and sz.lines > 0:
                        return sz.columns, sz.lines
            except OSError:
                pass
    sz = shutil.get_terminal_size(fallback=fallback)
    return max(40, sz.columns), max(14, sz.lines)


def char_width(ch: str) -> int:
    """Display cell width of a single Unicode character in monospace terminals."""
    cp = ord(ch)
    if cp < 32 or (0x7F <= cp < 0xA0):
        return 0
    if unicodedata.combining(ch):
        return 0
    cat = unicodedata.category(ch)
    if cat in ("Mn", "Me", "Cf"):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def vlen(text: str) -> int:
    """Visible display column width ignoring ANSI escape sequences."""
    plain = ANSI_RE.sub("", text)
    if plain.isascii():
        return len(plain)
    return sum(char_width(ch) for ch in plain)


def pad_right(text: str, width: int) -> str:
    extra = width - vlen(text)
    return text + (" " * extra if extra > 0 else "")


def _parse_ansi_cells(text: str) -> list[tuple[str, str, int]]:
    cells: list[tuple[str, str, int]] = []
    cur_sgr = ""
    for m in _SGR_TOKEN_RE.finditer(text):
        sgr_code, chunk = m.group(1), m.group(2)
        if sgr_code is not None:
            if sgr_code in ("", "0"):
                cur_sgr = ""
            else:
                parts = [p for p in sgr_code.split(";") if p]
                if "0" in parts:
                    idx0 = len(parts) - 1 - parts[::-1].index("0")
                    rem = parts[idx0 + 1 :]
                    cur_sgr = ";".join(rem)
                else:
                    cur_sgr = f"{cur_sgr};{sgr_code}" if cur_sgr else sgr_code
        elif chunk is not None:
            for ch in chunk:
                if ch == "\t":
                    for _ in range(4):
                        cells.append((" ", cur_sgr, 1))
                else:
                    cells.append((ch, cur_sgr, char_width(ch)))
    return cells


def _cells_to_ansi(cells: Sequence[tuple[str, str, int]]) -> str:
    if not cells:
        return ""
    out: list[str] = []
    active = ""
    for ch, sgr, _ in cells:
        if sgr != active:
            if active:
                out.append("\x1b[0m")
            if sgr:
                out.append(f"\x1b[{sgr}m")
            active = sgr
        out.append(ch)
    if active:
        out.append("\x1b[0m")
    return "".join(out)


def truncate_ansi(text: str, max_width: int, ellipsis: str = "…") -> str:
    """Truncate ANSI-styled text to max_width display columns without leaking SGR codes."""
    if max_width <= 0:
        return ""
    if vlen(text) <= max_width:
        return text
    ell_w = vlen(ellipsis)
    if max_width <= ell_w:
        return ellipsis[:max_width]
    cells = _parse_ansi_cells(text)
    limit = max_width - ell_w
    taken: list[tuple[str, str, int]] = []
    used = 0
    for cell in cells:
        if used + cell[2] > limit:
            break
        taken.append(cell)
        used += cell[2]
    return _cells_to_ansi(taken) + ellipsis


def wrap_ansi(text: str, width: int, cont_indent: str | None = None) -> list[str]:
    """Word- and token-wrap ANSI-styled text to `width` columns while preserving SGR colors."""
    width = max(4, width)
    paragraphs = text.split("\n")
    result: list[str] = []

    for para in paragraphs:
        if not para:
            result.append("")
            continue
        if vlen(para) <= width:
            result.append(para)
            continue

        cells = _parse_ansi_cells(para)
        if not cells:
            result.append("")
            continue

        if cont_indent is not None:
            indent_str = cont_indent
        else:
            plain = "".join(c[0] for c in cells)
            m = re.match(r"^(\s*(?:[•▪▸◆\-—]\s+|\d+[.)]\s+)?)", plain)
            cand = " " * (len(m.group(1)) if m else 0)
            if len(cand) > max(2, width // 3):
                cand = "  "
            indent_str = cand

        indent_cells: list[tuple[str, str, int]] = [(ch, "", 1) for ch in indent_str]
        indent_w = len(indent_cells)

        pos = 0
        line_idx = 0
        n_cells = len(cells)
        while pos < n_cells:
            prefix = [] if line_idx == 0 else indent_cells
            avail = max(2, width - (0 if line_idx == 0 else indent_w))

            used = 0
            end = pos
            last_space: int | None = None
            last_punct: int | None = None
            while end < n_cells:
                cw = cells[end][2]
                if used + cw > avail and end > pos:
                    break
                ch = cells[end][0]
                if ch == " ":
                    last_space = end
                elif ch in ("/", "\\", ",", ";") and end > pos:
                    last_punct = end
                used += cw
                end += 1
                if used >= avail and end < n_cells and cells[end][2] > 0:
                    break

            if end >= n_cells:
                seg = cells[pos:n_cells]
                result.append(_cells_to_ansi(prefix + seg))
                break

            if end < n_cells and cells[end][0] == " ":
                seg = cells[pos:end]
                pos = end + 1
                while pos < n_cells and cells[pos][0] == " ":
                    pos += 1
            elif last_space is not None and last_space > pos:
                seg = cells[pos:last_space]
                while seg and seg[-1][0] == " ":
                    seg.pop()
                pos = last_space + 1
                while pos < n_cells and cells[pos][0] == " ":
                    pos += 1
            elif last_punct is not None and last_punct >= pos:
                seg = cells[pos : last_punct + 1]
                pos = last_punct + 1
            else:
                seg = cells[pos:end]
                pos = end

            result.append(_cells_to_ansi(prefix + seg))
            line_idx += 1

    return result or [""]


def copy_to_clipboard(text: str) -> bool:
    """Best-effort copy to OS clipboard (macOS pbcopy / Windows clip / Linux wl-copy, xclip)."""
    if not text:
        return False
    cmds: list[list[str]] = []
    if sys.platform == "darwin":
        cmds.append(["pbcopy"])
    elif sys.platform.startswith("win"):
        cmds.append(["clip"])
    else:
        cmds.extend([
            ["wl-copy"],
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ])
    data = text.encode("utf-8")
    for cmd in cmds:
        try:
            proc = subprocess.run(
                cmd,
                input=data,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
                check=False,
            )
            if proc.returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


def render_cli_disclaimer_box(st: Style, width: int = 96) -> str:
    inner = width - 4
    lines = [
        st.bold(st.cyan(f"{TOOLKIT_NAME} v{TOOLKIT_VERSION}  •  {AUTHOR_CREDIT}")),
        st.dim(f"{AUTHOR_SITE_URL}  •  Drive2: perkthefox  •  TG: {AUTHOR_TG_URL}"),
        st.bold(
            st.yellow(
                tr(
                    "БЕСПЛАТНО • СТРОГО НЕ ДЛЯ ПРОДАЖИ!  |  Всегда сохраняйте родной бэкап блока!",
                    "FREE COMMUNITY TOOL • STRICTLY NOT FOR SALE!  |  Always keep an original ECU backup!",
                )
            )
        ),
    ]
    top = "╭" + ("─" * (width - 2)) + "╮"
    bot = "╰" + ("─" * (width - 2)) + "╯"
    body = [f"│ {pad_right(truncate_ansi(line, inner), inner)} │" for line in lines]
    return "\n".join([top, *body, bot])


def get_final_responsibility_warning_lines(st: Style) -> list[str]:
    """Return clear pre-generation responsibility & bricking warning lines (RU / EN)."""
    if get_lang() == "en":
        return [
            st.bold(st.red("⚠  READ CAREFULLY BEFORE GENERATING FILES:")),
            "",
            "• Everything that happens to the control unit afterwards is 100% YOUR responsibility.",
            "• This script only prepares files — it has NO connection to the ECU and does NOT control flashing.",
            "• Everything is done strictly AT YOUR OWN RISK.",
            st.bold(
                st.yellow(
                    "• Bricked units CANNOT be recovered over OBD — recovery is impossible without a bench programmer!"
                )
            ),
        ]
    return [
        st.bold(st.red("⚠  ВНИМАТЕЛЬНО ПРОЧИТАЙТЕ ПЕРЕД ГЕНЕРАЦИЕЙ:")),
        "",
        "• Всё, что произойдёт с блоком далее — это полностью ваша зона ответственности.",
        "• Скрипт к блоку отношения не имеет и процессом прошивки не руководит (он только готовит файлы).",
        "• Всё делается исключительно на ваш страх и риск.",
        st.bold(
            st.yellow(
                "• Окирпиченные юниты восстановлению без программатора НЕ подлежат!"
            )
        ),
    ]


def render_cli_final_warning_box(st: Style, width: int = 96) -> str:
    inner = width - 4
    wrapped: list[str] = []
    for ln in get_final_responsibility_warning_lines(st):
        wrapped.extend(wrap_ansi(ln, inner))
    top = st.red("┏" + ("━" * (width - 2)) + "┓")
    bot = st.red("┗" + ("━" * (width - 2)) + "┛")
    body = [st.red("┃ ") + pad_right(truncate_ansi(line, inner), inner) + st.red(" ┃") for line in wrapped]
    return "\n".join([top, *body, bot])
