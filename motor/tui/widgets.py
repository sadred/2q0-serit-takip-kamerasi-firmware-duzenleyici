"""Sleek `ncurses`-style windowing widgets, menus, checkboxes, file picker, and warning modals."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..core.i18n import (
    AUTHOR_CREDIT,
    AUTHOR_DRIVE2_URL,
    AUTHOR_SITE_SHORT,
    AUTHOR_SITE_URL,
    AUTHOR_TG_URL,
    Style,
    TOOLKIT_NAME,
    TOOLKIT_SHORT_NAME,
    TOOLKIT_VERSION,
    copy_to_clipboard,
    get_final_responsibility_warning_lines,
    get_lang,
    pad_right,
    set_lang,
    strip_ansi,
    tr,
    truncate_ansi,
    vlen,
    wrap_ansi,
)
from .screen import TuiScreen


@dataclass
class MenuItem:
    item_id: str
    hotkey: str
    label: str
    badge: str = ""
    details: tuple[str, ...] = ()


@dataclass
class CheckboxItem:
    item_id: str
    label: str
    checked: bool = False
    locked: bool = False
    details: tuple[str, ...] = ()


class TuiWindowMixin:
    """Shared `ncurses`-style windowing widgets for `KsPatcherTuiApp`."""

    scr: TuiScreen
    st: Style
    active_target_badge: str = ""

    def toggle_lang(self) -> None:
        set_lang("en" if get_lang() == "ru" else "ru")

    def _top_bar_text(self, cols: int) -> str:
        lang_tag = f"[{get_lang().upper()}]"
        nf_sale = tr("НЕ ДЛЯ ПРОДАЖИ", "NOT FOR SALE")
        tgt_part = f"  ▸  {self.active_target_badge}" if self.active_target_badge else ""
        left_full = f" ◆ {TOOLKIT_NAME.upper()} v{TOOLKIT_VERSION}{tgt_part}"
        right_full = f"{AUTHOR_CREDIT}  •  {AUTHOR_SITE_SHORT}  •  {nf_sale}  {lang_tag} "
        if vlen(left_full) + vlen(right_full) + 2 <= cols - 1:
            gap = (cols - 1) - vlen(left_full) - vlen(right_full)
            return left_full + (" " * gap) + right_full
        right_mid = f"{AUTHOR_CREDIT}  •  {lang_tag} "
        left_mid = f" ◆ {TOOLKIT_SHORT_NAME.upper()}{tgt_part}"
        if vlen(left_mid) + vlen(right_mid) + 2 <= cols - 1:
            gap = (cols - 1) - vlen(left_mid) - vlen(right_mid)
            return left_mid + (" " * gap) + right_mid
        compact = f" ◆ {TOOLKIT_SHORT_NAME.upper()} • {AUTHOR_CREDIT} {lang_tag}"
        return truncate_ansi(compact, max(10, cols - 1))

    def compose_window_frame(
        self,
        title: str,
        keybar: str,
        body_rows: Sequence[str],
        *,
        info_lines: Sequence[str] = (),
        footer_lines: Sequence[str] = (),
        border_color: str = "cyan",
        preferred_w: int = 100,
        fill_height: bool = False,
        right_badge: str = "",
        scroll_info: tuple[int, int, int] | None = None,
    ) -> None:
        """Render top bar + centered rounded window with soft shadow + scrollbar + bottom hotkey bar."""
        cols, rows = self.scr.size()
        st = self.st
        bcol = getattr(st, border_color, st.cyan)

        avail_h = max(6, rows - 2)
        win_w = max(38, min(cols - 4 if cols >= 48 else cols, preferred_w))
        inner_w = max(18, win_w - 6)

        wrapped_info: list[str] = []
        for ln in info_lines:
            wrapped_info.extend(wrap_ansi(ln, inner_w))

        wrapped_footer: list[str] = []
        for ln in footer_lines:
            wrapped_footer.extend(wrap_ansi(ln, inner_w))

        fixed_overhead = 2
        if wrapped_info:
            fixed_overhead += len(wrapped_info) + 1
        if wrapped_footer:
            fixed_overhead += len(wrapped_footer) + 1

        if fixed_overhead + 3 > avail_h and wrapped_info:
            keep_info = max(1, avail_h - (2 + (len(wrapped_footer) + 1 if wrapped_footer else 0) + 4))
            wrapped_info = wrapped_info[:keep_info]
            fixed_overhead = 2 + len(wrapped_info) + 1 + (len(wrapped_footer) + 1 if wrapped_footer else 0)
        if fixed_overhead + 2 > avail_h and wrapped_footer:
            keep_foot = max(1, avail_h - (2 + (len(wrapped_info) + 1 if wrapped_info else 0) + 3))
            wrapped_footer = wrapped_footer[:keep_foot]
            fixed_overhead = 2 + (len(wrapped_info) + 1 if wrapped_info else 0) + len(wrapped_footer) + 1

        max_body_h = max(1, avail_h - fixed_overhead)
        body_h = max_body_h if fill_height else min(max_body_h, max(1, len(body_rows)))
        win_h = min(avail_h, fixed_overhead + body_h)
        body_h = max(1, win_h - fixed_overhead)

        badge_part = f" {right_badge} " if right_badge else ""
        max_title_w = max(8, win_w - 8 - vlen(badge_part))
        t_clean = f" {truncate_ansi(title, max_title_w)} " if title else ""
        dashes_total = max(2, win_w - 2 - vlen(t_clean) - vlen(badge_part))
        left_d = min(3, dashes_total)
        right_d = min(3, max(0, dashes_total - left_d)) if badge_part else max(0, dashes_total - left_d)
        mid_d = max(0, dashes_total - left_d - right_d)
        if badge_part:
            top_border = (
                bcol("╭" + "─" * left_d)
                + st.bold(st.white(t_clean))
                + bcol("─" * mid_d)
                + st.dim(badge_part)
                + bcol("─" * right_d + "╮")
            )
        else:
            top_border = (
                bcol("╭" + "─" * left_d)
                + (st.bold(st.white(t_clean)) if t_clean else "")
                + bcol("─" * (dashes_total - left_d) + "╮")
            )
        divider = bcol("├" + "─" * (win_w - 2) + "┤")
        bot_border = bcol("╰" + "─" * (win_w - 2) + "╯")

        sb_chars: list[str] | None = None
        if scroll_info is not None:
            sc_top, sc_vis, sc_total = scroll_info
            if sc_total > sc_vis and body_h >= 3:
                sb_chars = ["░"] * body_h
                sb_chars[0] = "▲" if sc_top > 0 else "│"
                sb_chars[-1] = "▼" if (sc_top + sc_vis) < sc_total else "│"
                track = max(1, body_h - 2)
                thumb_h = max(1, round(track * sc_vis / sc_total))
                max_off = max(1, sc_total - sc_vis)
                thumb_pos = round((track - thumb_h) * min(sc_top, max_off) / max_off)
                for k in range(thumb_h):
                    if 1 + thumb_pos + k < body_h - 1:
                        sb_chars[1 + thumb_pos + k] = "█"

        win_lines: list[str] = [top_border]
        for iln in wrapped_info:
            win_lines.append(bcol("│  ") + pad_right(truncate_ansi(iln, inner_w), inner_w) + bcol("  │"))
        if wrapped_info:
            win_lines.append(divider)

        for idx_b in range(body_h):
            raw_b = body_rows[idx_b] if idx_b < len(body_rows) else ""
            clipped = pad_right(truncate_ansi(raw_b, inner_w), inner_w)
            r_glyph = sb_chars[idx_b] if sb_chars is not None else "│"
            r_edge = bcol("  " + r_glyph) if r_glyph == "│" else ("  " + st.cyan(r_glyph))
            win_lines.append(bcol("│  ") + clipped + r_edge)

        if wrapped_footer:
            win_lines.append(divider)
            for fln in wrapped_footer:
                win_lines.append(bcol("│  ") + pad_right(truncate_ansi(fln, inner_w), inner_w) + bcol("  │"))

        win_lines.append(bot_border)

        draw_shadow = cols >= win_w + 4 and avail_h >= len(win_lines) + 2
        pad_x = max(0, (cols - win_w - (2 if draw_shadow else 0)) // 2)
        pad_y = max(0, (avail_h - len(win_lines) - (1 if draw_shadow else 0)) // 2)
        left_margin = " " * pad_x
        sh_char = st.dim("░")

        screen_rows: list[str] = [
            self._top_bar_text(cols)
            if self.scr.use_color
            else self.st.inv(pad_right(self._top_bar_text(cols), cols - 1))
        ]
        for r_canvas in range(avail_h):
            w_idx = r_canvas - pad_y
            if 0 <= w_idx < len(win_lines):
                if draw_shadow and w_idx > 0:
                    screen_rows.append(left_margin + win_lines[w_idx] + sh_char + sh_char)
                else:
                    screen_rows.append(left_margin + win_lines[w_idx])
            elif draw_shadow and w_idx == len(win_lines):
                screen_rows.append(left_margin + "  " + (sh_char * win_w))
            else:
                screen_rows.append("")

        kb_text = "  " + keybar.strip()
        screen_rows.append(
            kb_text if self.scr.use_color else self.st.inv(pad_right(truncate_ansi(kb_text, cols - 1), cols - 1))
        )

        self.scr.draw_rows(
            screen_rows,
            top_bar_sgr="\x1b[1;37;44m",
            bot_bar_sgr="\x1b[1;30;46m",
        )

    def select_language_modal(self) -> str:
        cur = 0 if get_lang() == "ru" else 1
        opts = ("ru", "en")
        while True:
            cols, _ = self.scr.size()
            win_w = min(78, max(44, cols - 4))
            inner_w = win_w - 6
            labels = [
                "1   Русский язык     (по умолчанию)",
                "2   English          (switch UI to English)",
            ]
            body: list[str] = [""]
            for i, lbl in enumerate(labels):
                if i == cur:
                    body.append(self.st.sel(pad_right(f"  ▸  {lbl}", inner_w)))
                else:
                    body.append(pad_right(f"     {self.st.cyan(lbl[:1])}{lbl[1:]}", inner_w))
            body.append("")

            self.compose_window_frame(
                title="Выбор языка  /  Select Language",
                keybar="↑↓ Выбор   •   Enter Открыть   •   1 RU   2 EN   •   Q Выход",
                info_lines=[
                    f"{self.st.cyan(self.st.bold(AUTHOR_CREDIT))}   •   {self.st.dim(AUTHOR_SITE_SHORT)}",
                ],
                body_rows=body,
                footer_lines=[
                    self.st.yellow("БЕСПЛАТНЫЙ ИНСТРУМЕНТ  •  СТРОГО НЕ ДЛЯ ПРОДАЖИ  /  NOT FOR SALE"),
                ],
                border_color="cyan",
                preferred_w=win_w,
            )

            kind, val = self.scr.read_event()
            if kind == "KEY":
                if val in ("UP", "LEFT"):
                    cur = (cur - 1) % 2
                elif val in ("DOWN", "RIGHT", "TAB"):
                    cur = (cur + 1) % 2
                elif val == "ENTER":
                    return set_lang(opts[cur])
                elif val == "ESC":
                    raise EOFError
            elif kind == "CHAR":
                low = val.lower()
                if low in ("1", "r", "р"):
                    return set_lang("ru")
                if low in ("2", "e"):
                    return set_lang("en")
                if low in ("q", "0"):
                    raise EOFError

    def startup_disclaimer_modal(self) -> bool:
        btn = 0
        scroll = 0
        while True:
            cols, rows = self.scr.size()
            win_w = min(96, max(46, cols - 4))
            inner_w = max(20, win_w - 6)

            if get_lang() == "en":
                title = f"{TOOLKIT_SHORT_NAME} v{TOOLKIT_VERSION} — Disclaimer & Terms of Use"
                raw_lines = [
                    f"{self.st.cyan(self.st.bold(AUTHOR_CREDIT))}   •   {AUTHOR_SITE_URL}",
                    f"{self.st.dim(f'Drive2: {AUTHOR_DRIVE2_URL}   •   Telegram: {AUTHOR_TG_URL}')}",
                    "",
                    f"{self.st.red(self.st.bold('FREE COMMUNITY TOOL — STRICTLY NOT FOR SALE!'))}",
                    "Selling this utility, bundling it into commercial packages, or charging for it is prohibited.",
                    "",
                    f"{self.st.yellow(self.st.bold('USE AT YOUR OWN RISK:'))}",
                    "Provided 'AS IS'. Always save a full original backup of your ECU before any modification.",
                ]
                accept_lbl = " ✓ Accept & Continue "
                decline_lbl = " ✗ Exit "
                kb = "←→ Switch   •   Enter Confirm   •   L Language   •   Esc Exit"
            else:
                title = f"{TOOLKIT_SHORT_NAME} v{TOOLKIT_VERSION} — Условия использования"
                raw_lines = [
                    f"{self.st.cyan(self.st.bold(AUTHOR_CREDIT))}   •   {AUTHOR_SITE_URL}",
                    f"{self.st.dim(f'Drive2: {AUTHOR_DRIVE2_URL}   •   Telegram: {AUTHOR_TG_URL}')}",
                    "",
                    f"{self.st.red(self.st.bold('БЕСПЛАТНО — СТРОГО НЕ ДЛЯ ПРОДАЖИ!'))}",
                    "Продавать утилиту, встраивать её в платные сборки или брать за неё деньги запрещено.",
                    "",
                    f"{self.st.yellow(self.st.bold('ОТКАЗ ОТ ОТВЕТСТВЕННОСТИ:'))}",
                    "Программа предоставляется «КАК ЕСТЬ». Перед любыми действиями сохраняйте родной бэкап блока.",
                ]
                accept_lbl = " ✓ Принимаю — Продолжить "
                decline_lbl = " ✗ Выход "
                kb = "←→ Выбор кнопки   •   Enter Подтвердить   •   L RU/EN   •   Esc Выход"

            wrapped: list[str] = [""]
            for rln in raw_lines:
                wrapped.extend(wrap_ansi(rln, inner_w))
            wrapped.append("")

            vis_h = max(3, min(len(wrapped), (rows - 2) - 5))
            max_sc = max(0, len(wrapped) - vis_h)
            scroll = max(0, min(scroll, max_sc))
            vis_rows = wrapped[scroll : scroll + vis_h]

            b0 = self.st.sel_green(f" {accept_lbl} ") if btn == 0 else self.st.green(f"[{accept_lbl}]")
            b1 = self.st.sel_warn(f" {decline_lbl} ") if btn == 1 else self.st.dim(f"[{decline_lbl}]")
            btn_line = f"{b0}     {b1}"
            pad_b = max(0, (inner_w - vlen(btn_line)) // 2)

            self.compose_window_frame(
                title=title,
                keybar=kb,
                body_rows=vis_rows,
                footer_lines=[(" " * pad_b) + btn_line],
                border_color="yellow",
                preferred_w=win_w,
                scroll_info=(scroll, vis_h, len(wrapped)),
            )

            kind, val = self.scr.read_event()
            if kind == "KEY":
                if val in ("LEFT", "RIGHT", "TAB", "SHIFT_TAB"):
                    btn = 1 - btn
                elif val == "UP":
                    scroll = max(0, scroll - 1)
                elif val == "DOWN":
                    scroll = min(max_sc, scroll + 1)
                elif val == "ENTER":
                    return btn == 0
                elif val == "ESC":
                    return False
            elif kind == "CHAR":
                low = val.lower()
                if low in ("l", "я"):
                    self.toggle_lang()
                elif low in ("y", "д", "+"):
                    return True
                elif low in ("n", "н", "0", "q", "в"):
                    return False

    def final_generation_warning_modal(
        self,
        summary_lines_fn: Callable[[], list[str]],
    ) -> bool:
        """Mandatory pre-generation warning modal. Defaults cursor to Cancel so user consciously confirms."""
        btn = 1  # Start on [Cancel] so user reads the warning before switching to [Generate]
        scroll = 0
        while True:
            cols, rows = self.scr.size()
            win_w = min(98, max(46, cols - 4))
            inner_w = max(20, win_w - 6)

            card_w = inner_w
            card_inner = max(14, card_w - 4)
            warn_wrapped: list[str] = []
            for wln in get_final_responsibility_warning_lines(self.st):
                warn_wrapped.extend(wrap_ansi(wln, card_inner))

            box_lines: list[str] = [
                self.st.red("┏" + "━" * (card_w - 2) + "┓"),
            ]
            for wln in warn_wrapped:
                box_lines.append(
                    self.st.red("┃ ") + pad_right(truncate_ansi(wln, card_inner), card_inner) + self.st.red(" ┃")
                )
            box_lines.append(self.st.red("┗" + "━" * (card_w - 2) + "┛"))

            all_rows: list[str] = []
            for sln in summary_lines_fn():
                all_rows.extend(wrap_ansi(sln, inner_w))
            if all_rows:
                all_rows.append("")
            all_rows.extend(box_lines)

            vis_h = max(4, min(len(all_rows), (rows - 2) - 6))
            max_sc = max(0, len(all_rows) - vis_h)
            scroll = max(0, min(scroll, max_sc))

            yes_lbl = tr(" ✓ Понимаю риск — Сгенерировать ", " ✓ I Accept Responsibility — Generate ")
            no_lbl = tr(" ✗ Отмена ", " ✗ Cancel ")
            b0 = self.st.sel_danger(f" {yes_lbl} ") if btn == 0 else self.st.yellow(f"[{yes_lbl}]")
            b1 = self.st.sel(f" {no_lbl} ") if btn == 1 else self.st.dim(f"[{no_lbl}]")
            btn_line = f"{b0}     {b1}"
            pad_b = max(0, (inner_w - vlen(btn_line)) // 2)

            hint_line = self.st.dim(
                tr(
                    "Выберите «Понимаю риск — Сгенерировать» (стрелка ← затем Enter, либо клавиша Y)",
                    "Select 'I Accept Responsibility — Generate' (press ← then Enter, or press Y)",
                )
            )
            pad_h = max(0, (inner_w - vlen(hint_line)) // 2)

            self.compose_window_frame(
                title=tr("⚠ Подтверждение перед генерацией файлов", "⚠ Final Confirmation Before File Generation"),
                keybar=tr(
                    "←→ Выбор кнопки   •   Enter Подтвердить   •   Y Создать   •   Esc Отмена",
                    "←→ Switch Button   •   Enter Confirm   •   Y Generate   •   Esc Cancel",
                ),
                body_rows=all_rows[scroll : scroll + vis_h],
                footer_lines=[
                    (" " * pad_b) + btn_line,
                    (" " * pad_h) + hint_line,
                ],
                border_color="red",
                preferred_w=win_w,
                scroll_info=(scroll, vis_h, len(all_rows)),
            )

            kind, val = self.scr.read_event()
            if kind == "KEY":
                if val in ("LEFT", "RIGHT", "TAB", "SHIFT_TAB"):
                    btn = 1 - btn
                elif val == "UP":
                    scroll = max(0, scroll - 1)
                elif val == "DOWN":
                    scroll = min(max_sc, scroll + 1)
                elif val == "ENTER":
                    return btn == 0
                elif val == "ESC":
                    return False
            elif kind == "CHAR":
                low = val.lower()
                if low in ("y", "д"):
                    return True
                if low in ("n", "н", "0", "q", "в"):
                    return False
                if low in ("l", "я"):
                    self.toggle_lang()

    def menu_window(
        self,
        title_fn: Callable[[], str],
        info_fn: Callable[[], list[str]],
        items_fn: Callable[[], list[MenuItem]],
        keybar_fn: Callable[[], str],
        *,
        default_idx: int = 0,
        allow_esc: bool = True,
        border_color: str = "cyan",
        preferred_w: int = 100,
        right_badge_fn: Callable[[], str] | None = None,
    ) -> str | None:
        cur = max(0, default_idx)
        scroll = 0
        while True:
            items = items_fn()
            if not items:
                return None
            cur = max(0, min(cur, len(items) - 1))

            cols, rows = self.scr.size()
            win_w = min(preferred_w, max(44, cols - 4))
            inner_w = max(20, win_w - 6)

            info_lns = info_fn()
            cur_item = items[cur]
            foot_lns = list(cur_item.details) if cur_item.details else []

            w_info_cnt = sum(len(wrap_ansi(x, inner_w)) for x in info_lns) + (1 if info_lns else 0)
            w_foot_cnt = sum(len(wrap_ansi(x, inner_w)) for x in foot_lns) + (1 if foot_lns else 0)
            avail_list = max(3, (rows - 2) - 4 - w_info_cnt - w_foot_cnt)
            vis_h = max(3, min(len(items), avail_list))

            if cur < scroll:
                scroll = cur
            elif cur >= scroll + vis_h:
                scroll = cur - vis_h + 1
            scroll = max(0, min(scroll, max(0, len(items) - vis_h)))

            rendered_rows: list[str] = [""]
            for idx in range(scroll, min(len(items), scroll + vis_h)):
                it = items[idx]
                hk_disp = f"{it.hotkey.upper():<2}  " if it.hotkey else "    "
                if idx == cur:
                    plain_lbl = strip_ansi(it.label)
                    plain_bdg = strip_ansi(it.badge)
                    left_part = f"  ▸  {hk_disp}{plain_lbl}"
                    if plain_bdg and vlen(left_part) + vlen(plain_bdg) + 4 <= inner_w:
                        gap = inner_w - vlen(left_part) - vlen(plain_bdg) - 2
                        row_txt = left_part + (" " * gap) + plain_bdg + "  "
                    else:
                        row_txt = pad_right(truncate_ansi(left_part, inner_w), inner_w)
                    rendered_rows.append(self.st.sel(row_txt))
                else:
                    hk_col = self.st.cyan(self.st.bold(hk_disp)) if it.hotkey else hk_disp
                    left_part = f"     {hk_col}{it.label}"
                    if it.badge and vlen(left_part) + vlen(it.badge) + 4 <= inner_w:
                        gap = inner_w - vlen(left_part) - vlen(it.badge) - 2
                        row_txt = left_part + (" " * gap) + it.badge + "  "
                    else:
                        row_txt = truncate_ansi(left_part, inner_w)
                    rendered_rows.append(row_txt)
            rendered_rows.append("")

            self.compose_window_frame(
                title=title_fn(),
                keybar=keybar_fn(),
                info_lines=info_lns,
                body_rows=rendered_rows,
                footer_lines=foot_lns,
                border_color=border_color,
                preferred_w=win_w,
                right_badge=right_badge_fn() if right_badge_fn else f"{cur + 1}/{len(items)}",
                scroll_info=(scroll, vis_h, len(items)) if len(items) > vis_h else None,
            )

            kind, val = self.scr.read_event()
            if kind == "KEY":
                if val == "UP":
                    cur = (cur - 1) % len(items)
                elif val == "DOWN":
                    cur = (cur + 1) % len(items)
                elif val == "HOME":
                    cur = 0
                elif val == "END":
                    cur = len(items) - 1
                elif val == "PGUP":
                    cur = max(0, cur - vis_h)
                elif val == "PGDN":
                    cur = min(len(items) - 1, cur + vis_h)
                elif val == "ENTER":
                    return items[cur].item_id
                elif val == "ESC" and allow_esc:
                    return None
            elif kind == "CHAR":
                low = val.lower()
                if low in ("l", "я"):
                    self.toggle_lang()
                    continue
                if allow_esc and low in ("q", "в") and not any(it.hotkey.lower() == low for it in items):
                    return None
                for idx_h, it in enumerate(items):
                    if it.hotkey and it.hotkey.lower() == low:
                        cur = idx_h
                        return it.item_id

    def checkbox_modal(
        self,
        title_fn: Callable[[], str],
        info_fn: Callable[[], list[str]],
        items_fn: Callable[[dict[str, bool]], list[CheckboxItem]],
        initial_state: dict[str, bool],
        *,
        confirm_label_fn: Callable[[], str] | None = None,
        border_color: str = "cyan",
        preferred_w: int = 100,
        right_badge: str = "",
    ) -> dict[str, bool] | None:
        """Interactive `ncurses`-style checkbox form (`Space` toggles, `Enter` on button continues)."""
        state = dict(initial_state)
        items_init = items_fn(state)
        # Default cursor right onto the [Continue] button so standard settings work in 1 Enter!
        cur = len(items_init)

        while True:
            items = items_fn(state)
            total_rows = len(items) + 1
            cur = max(0, min(cur, total_rows - 1))

            cols, _ = self.scr.size()
            win_w = min(preferred_w, max(46, cols - 4))
            inner_w = max(20, win_w - 6)

            body: list[str] = [""]
            for idx, it in enumerate(items):
                val_on = state.get(it.item_id, it.checked)
                mark = "✓" if val_on else " "
                lock_tag = f"  ({tr('всегда вкл.', 'always on')})" if it.locked else ""
                if idx == cur:
                    row_txt = pad_right(
                        truncate_ansi(f"  ▸  [{mark}]  {strip_ansi(it.label)}{lock_tag}", inner_w),
                        inner_w,
                    )
                    body.append(self.st.sel(row_txt))
                else:
                    box_col = self.st.green(f"[{mark}]") if val_on else self.st.dim("[ ]")
                    lbl_s = f"     {box_col}  {it.label}" + (self.st.dim(lock_tag) if lock_tag else "")
                    body.append(truncate_ansi(lbl_s, inner_w))

            body.append("")
            btn_txt = confirm_label_fn() if confirm_label_fn else tr(" ▶ Далее — Продолжить ", " ▶ Next — Continue ")
            btn_rendered = self.st.sel_green(f" {btn_txt} ") if cur == len(items) else self.st.green(f"[{btn_txt}]")
            pad_b = max(0, (inner_w - vlen(btn_rendered)) // 2)
            body.append((" " * pad_b) + btn_rendered)
            body.append("")

            foot_lns: list[str] = []
            if cur < len(items) and items[cur].details:
                foot_lns.extend(items[cur].details)
            else:
                foot_lns.append(
                    self.st.dim(
                        tr(
                            "Оптимальные настройки уже выбраны. Нажмите Enter для продолжения или ↑↓ + Пробел для изменения.",
                            "Recommended options are pre-selected. Press Enter to continue or ↑↓ + Space to customize.",
                        )
                    )
                )

            self.compose_window_frame(
                title=title_fn(),
                keybar=tr(
                    "↑↓ Выбор   •   Пробел Переключить   •   Enter Продолжить   •   Esc Назад",
                    "↑↓ Move   •   Space Toggle   •   Enter Continue   •   Esc Back",
                ),
                info_lines=info_fn(),
                body_rows=body,
                footer_lines=foot_lns,
                border_color=border_color,
                preferred_w=win_w,
                right_badge=right_badge,
            )

            kind, val = self.scr.read_event()
            if kind == "KEY":
                if val == "UP":
                    cur = (cur - 1) % total_rows
                elif val in ("DOWN", "TAB"):
                    cur = (cur + 1) % total_rows
                elif val == "SHIFT_TAB":
                    cur = (cur - 1) % total_rows
                elif val == "ENTER":
                    if cur == len(items):
                        return state
                    it = items[cur]
                    if not it.locked:
                        state[it.item_id] = not state.get(it.item_id, it.checked)
                elif val == "ESC":
                    return None
            elif kind == "CHAR":
                if val == " ":
                    if cur < len(items) and not items[cur].locked:
                        it = items[cur]
                        state[it.item_id] = not state.get(it.item_id, it.checked)
                    elif cur == len(items):
                        return state
                else:
                    low = val.lower()
                    if low in ("s", "ы"):
                        return state
                    if low in ("l", "я"):
                        self.toggle_lang()
                    elif low in ("q", "0"):
                        return None

    def confirm_modal(
        self,
        title_fn: Callable[[], str],
        body_fn: Callable[[], list[str]],
        *,
        default: bool = True,
        yes_fn: Callable[[], str] | None = None,
        no_fn: Callable[[], str] | None = None,
        border_color: str = "yellow",
        preferred_w: int = 92,
    ) -> bool | None:
        btn = 0 if default else 1
        scroll = 0
        while True:
            cols, rows = self.scr.size()
            win_w = min(preferred_w, max(42, cols - 4))
            inner_w = max(18, win_w - 6)

            wrapped: list[str] = [""]
            for ln in body_fn():
                wrapped.extend(wrap_ansi(ln, inner_w))
            wrapped.append("")

            vis_h = max(2, min(len(wrapped), (rows - 2) - 5))
            max_sc = max(0, len(wrapped) - vis_h)
            scroll = max(0, min(scroll, max_sc))

            y_txt = yes_fn() if yes_fn else tr(" ✓ Да ", " ✓ Yes ")
            n_txt = no_fn() if no_fn else tr(" ✗ Нет ", " ✗ No ")
            b0 = self.st.sel_green(f" {y_txt} ") if btn == 0 else self.st.green(f"[{y_txt}]")
            b1 = self.st.sel_warn(f" {n_txt} ") if btn == 1 else self.st.dim(f"[{n_txt}]")
            btn_line = f"{b0}     {b1}"
            pad_b = max(0, (inner_w - vlen(btn_line)) // 2)

            self.compose_window_frame(
                title=title_fn(),
                keybar=tr(
                    "←→ Выбор   •   Enter Подтвердить   •   Esc Отмена",
                    "←→ Switch   •   Enter Confirm   •   Esc Cancel",
                ),
                body_rows=wrapped[scroll : scroll + vis_h],
                footer_lines=[(" " * pad_b) + btn_line],
                border_color=border_color,
                preferred_w=win_w,
                scroll_info=(scroll, vis_h, len(wrapped)),
            )

            kind, val = self.scr.read_event()
            if kind == "KEY":
                if val in ("LEFT", "RIGHT", "TAB", "SHIFT_TAB"):
                    btn = 1 - btn
                elif val == "UP":
                    scroll = max(0, scroll - 1)
                elif val == "DOWN":
                    scroll = min(max_sc, scroll + 1)
                elif val == "ENTER":
                    return btn == 0
                elif val == "ESC":
                    return None
            elif kind == "CHAR":
                low = val.lower()
                if low in ("y", "д", "+"):
                    return True
                if low in ("n", "н", "-"):
                    return False
                if low in ("l", "я"):
                    self.toggle_lang()

    def alert_modal(
        self,
        title_fn: Callable[[], str],
        body_fn: Callable[[int], list[str]],
        *,
        detailed_body_fn: Callable[[int], list[str]] | None = None,
        border_color: str = "green",
        copy_text: str | None = None,
        preferred_w: int = 100,
    ) -> None:
        scroll = 0
        copied_note = ""
        show_details = False
        while True:
            cols, rows = self.scr.size()
            win_w = min(preferred_w, max(44, cols - 4))
            inner_w = max(18, win_w - 6)

            active_fn = detailed_body_fn if (show_details and detailed_body_fn is not None) else body_fn
            raw_body = active_fn(inner_w)
            wrapped: list[str] = [""]
            for ln in raw_body:
                wrapped.extend(wrap_ansi(ln, inner_w))
            wrapped.append("")

            vis_h = max(3, min(len(wrapped), (rows - 2) - 5))
            max_sc = max(0, len(wrapped) - vis_h)
            scroll = max(0, min(scroll, max_sc))

            plain_report = copy_text if copy_text is not None else "\n".join(strip_ansi(x) for x in raw_body)
            ok_btn = self.st.sel(f" {tr('✓ Готово (Enter)', '✓ Close (Enter)')} ")
            parts = [ok_btn]
            if detailed_body_fn is not None:
                det_lbl = (
                    tr("D — Скрыть тех. детали", "D — Hide Tech Details")
                    if show_details
                    else tr("D — Тех. подробности", "D — Tech Details")
                )
                parts.append(self.st.dim(f"[{det_lbl}]"))
            parts.append(self.st.cyan(f"[{tr('C — Копировать', 'C — Copy')}]"))
            btn_line = "   ".join(parts)
            if copied_note:
                btn_line += f"   {self.st.green(copied_note)}"
            pad_b = max(0, (inner_w - vlen(btn_line)) // 2)

            pct = 100 if max_sc == 0 else round(100 * scroll / max_sc)
            rbadge = f"{pct}%" if len(wrapped) > vis_h else ""

            self.compose_window_frame(
                title=title_fn(),
                keybar=tr(
                    "↑↓ Прокрутка   •   Enter Закрыть"
                    + ("   •   D Тех. детали" if detailed_body_fn else "")
                    + "   •   C Копировать",
                    "↑↓ Scroll   •   Enter Close"
                    + ("   •   D Tech Details" if detailed_body_fn else "")
                    + "   •   C Copy",
                ),
                body_rows=wrapped[scroll : scroll + vis_h],
                footer_lines=[(" " * pad_b) + btn_line],
                border_color=border_color,
                preferred_w=win_w,
                right_badge=rbadge,
                scroll_info=(scroll, vis_h, len(wrapped)),
            )

            kind, val = self.scr.read_event()
            if kind == "KEY":
                if val == "UP":
                    scroll = max(0, scroll - 1)
                elif val == "DOWN":
                    scroll = min(max_sc, scroll + 1)
                elif val == "PGUP":
                    scroll = max(0, scroll - max(1, vis_h - 1))
                elif val == "PGDN":
                    scroll = min(max_sc, scroll + max(1, vis_h - 1))
                elif val == "HOME":
                    scroll = 0
                elif val == "END":
                    scroll = max_sc
                elif val in ("ENTER", "ESC"):
                    return
            elif kind == "CHAR":
                low = val.lower()
                if low in ("d", "в") and detailed_body_fn is not None:
                    show_details = not show_details
                    scroll = 0
                elif low in ("c", "с") and plain_report:
                    ok = copy_to_clipboard(plain_report)
                    copied_note = (
                        tr("✓ Скопировано!", "✓ Copied!")
                        if ok
                        else tr("Буфер недоступен", "Clipboard unavailable")
                    )
                elif low in ("l", "я"):
                    self.toggle_lang()
                    copied_note = ""
                elif low in ("q", "0"):
                    return

    def input_modal(
        self,
        title_fn: Callable[[], str],
        info_fn: Callable[[], list[str]],
        *,
        default_val: str = "",
        initial_text: str = "",
        validator: Callable[[str], tuple[bool, str]] | None = None,
        border_color: str = "cyan",
        preferred_w: int = 96,
        right_badge: str = "",
    ) -> str | None:
        buf = list(initial_text)
        cur = len(buf)
        err_msg = ""

        while True:
            cols, _ = self.scr.size()
            win_w = min(preferred_w, max(44, cols - 4))
            inner_w = max(20, win_w - 6)
            field_w = max(12, inner_w - 4)

            text_str = "".join(buf)
            view_start = 0
            if cur >= field_w - 1:
                view_start = cur - (field_w - 2)
            vis_slice = text_str[view_start : view_start + field_w]
            rel_cur = cur - view_start

            before_c = vis_slice[:rel_cur]
            at_c = vis_slice[rel_cur] if rel_cur < len(vis_slice) else " "
            after_c = vis_slice[rel_cur + 1 :] if rel_cur < len(vis_slice) else ""
            pad_rem = max(0, field_w - len(before_c) - 1 - len(after_c))
            rendered_input = before_c + self.st.sel(at_c) + after_c + (" " * pad_rem)

            box_top = self.st.cyan("╭─" + "─" * field_w + "─╮")
            box_mid = self.st.cyan("│ ") + rendered_input + self.st.cyan(" │")
            box_bot = self.st.cyan("╰─" + "─" * field_w + "─╯")

            body: list[str] = ["", box_top, box_mid, box_bot, ""]
            if default_val and not text_str:
                body.append(
                    self.st.dim(
                        tr(
                            f"Нажмите Enter для пути по умолчанию: {default_val}",
                            f"Press Enter for default path: {default_val}",
                        )
                    )
                )

            foot: list[str] = []
            if err_msg:
                foot.append(self.st.red(f"[!] {err_msg}"))
            else:
                foot.append(
                    self.st.dim(
                        tr(
                            "Нажмите Enter, чтобы оставить предложенный путь, или укажите свой.",
                            "Press Enter to keep the suggested path, or edit it above.",
                        )
                    )
                )

            self.compose_window_frame(
                title=title_fn(),
                keybar=tr(
                    "Enter Подтвердить   •   Ctrl+U Очистить   •   Esc Назад",
                    "Enter Confirm   •   Ctrl+U Clear   •   Esc Back",
                ),
                info_lines=info_fn(),
                body_rows=body,
                footer_lines=foot,
                border_color="red" if err_msg else border_color,
                preferred_w=win_w,
                right_badge=right_badge,
            )

            kind, val = self.scr.read_event()
            if kind == "KEY":
                if val == "LEFT":
                    cur = max(0, cur - 1)
                elif val == "RIGHT":
                    cur = min(len(buf), cur + 1)
                elif val == "HOME":
                    cur = 0
                elif val == "END":
                    cur = len(buf)
                elif val == "BACKSPACE":
                    if cur > 0:
                        buf.pop(cur - 1)
                        cur -= 1
                        err_msg = ""
                elif val == "DELETE":
                    if cur < len(buf):
                        buf.pop(cur)
                        err_msg = ""
                elif val == "CTRL_U":
                    buf.clear()
                    cur = 0
                    err_msg = ""
                elif val == "ESC":
                    return None
                elif val == "ENTER":
                    candidate = "".join(buf).strip().strip("'\"")
                    if not candidate and default_val:
                        candidate = default_val
                    if validator is not None:
                        ok, msg = validator(candidate)
                        if not ok:
                            err_msg = msg
                            continue
                    return candidate
            elif kind == "PASTE":
                clean_p = val.replace("\r", " ").replace("\n", " ").strip().strip("'\"")
                if clean_p:
                    buf[cur:cur] = list(clean_p)
                    cur += len(clean_p)
                    err_msg = ""
            elif kind == "CHAR":
                buf[cur:cur] = list(val)
                cur += len(val)
                err_msg = ""

    def directory_browser_modal(
        self,
        title_fn: Callable[[], str],
        start_dir: Path,
        *,
        expected_sizes: tuple[int, ...] = (),
        allowed_exts: tuple[str, ...] = (),
        select_directory: bool = False,
    ) -> Path | None:
        cur_dir = start_dir.resolve() if start_dir.exists() else Path.cwd().resolve()
        if cur_dir.is_file():
            cur_dir = cur_dir.parent
        cur = 0
        scroll = 0
        err_msg = ""

        while True:
            entries: list[tuple[str, Path, bool, int]] = []
            if select_directory:
                entries.append(
                    (
                        tr("✓ [Выбрать эту папку]", "✓ [Select This Folder]"),
                        cur_dir,
                        False,
                        -1,
                    )
                )
            parent = cur_dir.parent
            if parent != cur_dir:
                entries.append(("↩  ..  " + tr("(на уровень выше)", "(parent folder)"), parent, True, 0))
            try:
                raw_children = list(cur_dir.iterdir())
            except OSError as exc:
                raw_children = []
                err_msg = str(exc)

            dirs = sorted(
                (p for p in raw_children if p.is_dir() and not p.name.startswith(".")),
                key=lambda x: x.name.lower(),
            )
            for d in dirs:
                entries.append((f"📁 {d.name}/", d, True, 0))

            if not select_directory:
                files = sorted(
                    (p for p in raw_children if p.is_file() and not p.name.startswith(".")),
                    key=lambda x: x.name.lower(),
                )
                for f in files:
                    try:
                        sz = f.stat().st_size
                    except OSError:
                        sz = 0
                    entries.append((f"📄 {f.name}", f, False, sz))

            if not entries:
                entries.append(("<пусто / empty>", cur_dir, True, 0))
            cur = max(0, min(cur, len(entries) - 1))

            cols, rows = self.scr.size()
            win_w = min(100, max(46, cols - 4))
            inner_w = max(20, win_w - 6)
            vis_h = max(4, min(len(entries), (rows - 2) - 7))
            if cur < scroll:
                scroll = cur
            elif cur >= scroll + vis_h:
                scroll = cur - vis_h + 1
            scroll = max(0, min(scroll, max(0, len(entries) - vis_h)))

            body: list[str] = []
            for idx in range(scroll, min(len(entries), scroll + vis_h)):
                lbl, p_obj, is_dir, sz = entries[idx]
                sz_str = ""
                if not is_dir and sz >= 0:
                    sz_str = f"{sz / (1024 * 1024):.1f} MB" if sz >= 1024 * 1024 else f"{sz // 1024} KB"
                    if expected_sizes and sz in expected_sizes:
                        sz_str += " ★"
                elif allowed_exts and not is_dir and p_obj.suffix.lower() in allowed_exts and sz >= 0:
                    sz_str = f"{sz / (1024 * 1024):.1f} MB" if sz >= 1024 * 1024 else f"{sz // 1024} KB"

                if idx == cur:
                    left_s = f"  ▸  {strip_ansi(lbl)}"
                    if sz_str and vlen(left_s) + len(sz_str) + 4 <= inner_w:
                        gap = inner_w - vlen(left_s) - len(sz_str) - 2
                        row_s = left_s + (" " * gap) + sz_str + "  "
                    else:
                        row_s = pad_right(truncate_ansi(left_s, inner_w), inner_w)
                    body.append(self.st.sel(row_s))
                else:
                    col_lbl = (
                        self.st.cyan(lbl)
                        if is_dir
                        else (self.st.green(lbl) if sz == -1 else lbl)
                    )
                    left_s = f"     {col_lbl}"
                    if sz_str and vlen(left_s) + len(sz_str) + 4 <= inner_w:
                        gap = inner_w - vlen(left_s) - len(sz_str) - 2
                        s_col = self.st.green(sz_str) if "★" in sz_str else self.st.dim(sz_str)
                        row_s = left_s + (" " * gap) + s_col + "  "
                    else:
                        row_s = truncate_ansi(left_s, inner_w)
                    body.append(row_s)

            foot: list[str] = []
            if err_msg:
                foot.append(self.st.red(f"[!] {err_msg}"))
            else:
                _, sel_p, _, _ = entries[cur]
                foot.append(self.st.dim(str(sel_p)))

            self.compose_window_frame(
                title=title_fn(),
                keybar=tr(
                    "↑↓ Навигация   •   Enter Открыть   •   Backspace Вверх   •   Esc Назад",
                    "↑↓ Move   •   Enter Open   •   Backspace Up   •   Esc Back",
                ),
                info_lines=[f"{self.st.dim(tr('Папка:', 'Folder:'))}  {self.st.cyan(str(cur_dir))}"],
                body_rows=body,
                footer_lines=foot,
                border_color="cyan",
                preferred_w=win_w,
                right_badge=f"{cur + 1}/{len(entries)}",
                scroll_info=(scroll, vis_h, len(entries)),
            )

            kind, val = self.scr.read_event()
            if kind == "KEY":
                if val == "UP":
                    cur = (cur - 1) % len(entries)
                    err_msg = ""
                elif val == "DOWN":
                    cur = (cur + 1) % len(entries)
                    err_msg = ""
                elif val == "PGUP":
                    cur = max(0, cur - vis_h)
                elif val == "PGDN":
                    cur = min(len(entries) - 1, cur + vis_h)
                elif val == "BACKSPACE":
                    if cur_dir.parent != cur_dir:
                        cur_dir = cur_dir.parent
                        cur = 0
                        scroll = 0
                        err_msg = ""
                elif val == "ENTER":
                    _, target_p, is_dir, _ = entries[cur]
                    if is_dir:
                        cur_dir = target_p
                        cur = 0
                        scroll = 0
                        err_msg = ""
                    else:
                        return target_p
                elif val == "ESC":
                    return None
            elif kind == "CHAR":
                low = val.lower()
                if low in ("l", "я"):
                    self.toggle_lang()
                elif low in ("q", "0"):
                    return None

    def file_picker_modal(
        self,
        title_fn: Callable[[], str],
        hint_fn: Callable[[], str],
        candidates_fn: Callable[[], list[Path]],
        *,
        start_dir: Path,
        expected_sizes: tuple[int, ...] = (),
        allowed_exts: tuple[str, ...] = (),
        right_badge: str = "",
    ) -> Path | None:
        """Select from auto-discovered ECU files, browse folders, or paste path."""
        while True:
            cands = candidates_fn()

            def _build_items() -> list[MenuItem]:
                out: list[MenuItem] = []
                for idx, cp in enumerate(cands, 1):
                    try:
                        sz = cp.stat().st_size
                        sz_s = f"{sz / (1024 * 1024):.1f} MB" if sz >= 1024 * 1024 else f"{max(1, sz // 1024)} KB"
                    except OSError:
                        sz_s = "?"
                    hk = str(idx) if idx <= 9 else ""
                    out.append(
                        MenuItem(
                            item_id=f"cand:{idx - 1}",
                            hotkey=hk,
                            label=f"📄 {cp.name}",
                            badge=self.st.green(sz_s),
                            details=(f"{self.st.dim(str(cp.parent))}",),
                        )
                    )
                out.append(
                    MenuItem(
                        item_id="browse",
                        hotkey="B",
                        label=tr("📁 Выбрать файл через обзор папок...", "📁 Browse folders for a file..."),
                        badge="",
                        details=(
                            tr(
                                "Открыть проводник папок для выбора файла в любом месте диска.",
                                "Open folder browser to pick a file from any directory.",
                            ),
                        ),
                    )
                )
                out.append(
                    MenuItem(
                        item_id="manual",
                        hotkey="M",
                        label=tr("⌨  Вставить путь или перетащить файл в окно...", "⌨  Paste file path or drag & drop..."),
                        badge="",
                        details=(
                            tr(
                                "Можно перетащить файл мышкой прямо в терминал или вставить путь (Cmd+V).",
                                "Drag & drop a file into the terminal window or paste its path.",
                            ),
                        ),
                    )
                )
                return out

            choice = self.menu_window(
                title_fn=title_fn,
                info_fn=lambda: [hint_fn()],
                items_fn=_build_items,
                keybar_fn=lambda: tr(
                    "↑↓ Выбор   •   Enter Открыть   •   B Обзор папок   •   M Путь   •   Esc Назад",
                    "↑↓ Select   •   Enter Open   •   B Browse   •   M Path   •   Esc Back",
                ),
                right_badge_fn=(lambda: right_badge) if right_badge else None,
            )
            if choice is None:
                return None
            if choice.startswith("cand:"):
                idx = int(choice.split(":", 1)[1])
                return cands[idx]
            if choice == "browse":
                picked = self.directory_browser_modal(
                    title_fn=title_fn,
                    start_dir=start_dir,
                    expected_sizes=expected_sizes,
                    allowed_exts=allowed_exts,
                )
                if picked is not None:
                    return picked
            elif choice == "manual":
                raw_p = self.input_modal(
                    title_fn=title_fn,
                    info_fn=lambda: [hint_fn()],
                    validator=lambda s: (
                        (True, "")
                        if s and Path(s).expanduser().is_file()
                        else (False, tr(f"Файл не найден: {s}", f"File not found: {s}"))
                    ),
                )
                if raw_p is not None:
                    return Path(raw_p).expanduser().resolve()
