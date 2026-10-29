#!/usr/bin/env python3
"""Schutz-Kaput — Modular VAG ECU CP (`KS_PASSIVE`) & `FeC`/`SWaP` Patcher (`ncurses`-style TUI + CLI).

Made by PerkTheFox
  • Website  : https://vwhacking.antonperk.com (vwhacking.antonperk.com)
  • Drive2   : https://www.drive2.ru/users/perkthefox/
  • Telegram : https://t.me/perkthefox

FREE COMMUNITY RESEARCH TOOL — STRICTLY NOT FOR SALE! (БЕСПЛАТНО • НЕ ДЛЯ ПРОДАЖИ!)
DISCLAIMER ("AS IS"): Always keep a full original hardware Flash + EEPROM/NvM backup first!
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import dataclasses
import json
import os
from pathlib import Path
import sys

# Bootstrap synthetic package root so `python3 ks_patcher.py` works regardless of repository folder name
# (including hyphenated Git clones like `schutz-kaput/` or `Schutz-Kaput-main/`).
_PKG_DIR = Path(__file__).resolve().parent
if not __package__:
    import importlib.util

    _SYNTH_PKG = "_schutz_kaput_pkg"
    if _SYNTH_PKG not in sys.modules:
        _spec = importlib.util.spec_from_file_location(
            _SYNTH_PKG,
            _PKG_DIR / "__init__.py",
            submodule_search_locations=[str(_PKG_DIR)],
        )
        if _spec is None or _spec.loader is None:
            raise RuntimeError(f"Failed to initialize package root at {_PKG_DIR}")
        _pkg_mod = importlib.util.module_from_spec(_spec)
        sys.modules[_SYNTH_PKG] = _pkg_mod
        _spec.loader.exec_module(_pkg_mod)
    __package__ = _SYNTH_PKG

from .core.i18n import (  # noqa: E402
    Style,
    detect_early_cli_lang,
    get_lang,
    pad_right,
    render_cli_disclaimer_box,
    render_cli_final_warning_box,
    set_lang,
    tr,
    vlen,
)
from .core.target_base import PatchOptions  # noqa: E402
from .targets import get_target, list_targets  # noqa: E402
from .tui import KsPatcherTuiApp, TuiScreen  # noqa: E402


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ks_patcher.py",
        description=tr(
            "Schutz-Kaput — модульный патчер CP (KSchutz) и кодов FeC/SWaP для блоков VAG (интерактивный TUI + CLI)",
            "Schutz-Kaput — Modular VAG ECU CP (KSchutz) & FeC/SWaP Patcher (interactive TUI + CLI)",
        ),
    )
    parser.add_argument(
        "-l",
        "--lang",
        help=tr("Язык интерфейса: ru или en", "Interface language: ru or en"),
    )
    parser.add_argument(
        "-t",
        "--target",
        help=tr(
            "Целевой модуль ЭБУ (например: mfk3 / 0x00A5). В TUI без флага открывается меню выбора блока.",
            "Target ECU module (e.g. mfk3 / 0x00A5). Omit in TUI mode to open the ECU Target Selector.",
        ),
    )
    parser.add_argument(
        "--list-targets",
        action="store_true",
        help=tr("Вывести список всех поддерживаемых блоков ЭБУ и выйти", "List all registered ECU targets and exit"),
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help=tr("Отключить цветной вывод ANSI", "Disable ANSI color output"),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help=tr("Показать технические подробности (адреса, CRC, SHA-256)", "Show technical details (addresses, CRC, SHA-256)"),
    )

    sub = parser.add_subparsers(dest="cmd")

    # tui / wizard
    sub.add_parser(
        "tui",
        aliases=["wizard"],
        help=tr(
            "Запустить полноэкранное интерактивное меню (по умолчанию при запуске без аргументов)",
            "Launch full-screen interactive TUI menu (default when invoked with no subcommand)",
        ),
    )

    # inspect
    p_insp = sub.add_parser(
        "inspect",
        help=tr(
            "Проверить дамп / блок данных / контейнер (.bin, .odx-f, .odx, .pdx, .frf)",
            "Inspect dump / datablock / container (.bin, .odx-f, .odx, .pdx, .frf)",
        ),
    )
    p_insp.add_argument("input", type=Path, help=tr("Путь к входному файлу", "Path to input file"))
    p_insp.add_argument("--frf-key", type=Path, help=tr("Свой frf.key (по умолчанию встроен)", "Custom frf.key (built-in by default)"))
    p_insp.add_argument("--ignore-input-crc", action="store_true", help=tr("Игнорировать несовпадение входного FW-CHECKSUM", "Ignore input FW-CHECKSUM mismatch"))
    p_insp.add_argument("--json", action="store_true", help=tr("Вывести результат в формате JSON", "Emit structured JSON output"))
    p_insp.add_argument(
        "-v",
        "--verbose",
        dest="sub_verbose",
        action="store_true",
        help=tr("Показать технические подробности (адреса, CRC, SHA-256)", "Show technical details (addresses, CRC, SHA-256)"),
    )

    # patch
    p_patch = sub.add_parser(
        "patch",
        help=tr(
            "Подготовить прошивку с отключением KS + активацией всех функций FeC/SWaP (или откатить в сток)",
            "Prepare firmware with KS disabled + all FeC/SWaP features unlocked (or restore stock)",
        ),
    )
    p_patch.add_argument("input", type=Path, help=tr("Входной дамп / DB_01 / контейнер (.odx-f, .frf)", "Input dump / DB_01 / container (.odx-f, .frf)"))
    p_patch.add_argument("-o", "--output", type=Path, help=tr("Путь для сохранения выходного .bin", "Output .bin path"))
    p_patch.add_argument("--in-place", action="store_true", help=tr("Перезаписать входной бинарный дамп на месте", "Modify input binary dump in-place"))
    p_patch.add_argument(
        "--no-fecs",
        action="store_true",
        help=tr(
            "Не открывать платные функции FeC/SWaP (по умолчанию активируются все функции блока)",
            "Leave FeC/SWaP untouched (by default all features of the ECU are activated)",
        ),
    )
    p_patch.add_argument(
        "--suppress-key-dtcs",
        action="store_true",
        help=tr(
            "Подавить ошибки непривязанных ключей на новой Virgin-камере",
            "Suppress unadapted key DTCs on brand-new Virgin cameras",
        ),
    )
    p_patch.add_argument(
        "--enable-xcp-can0",
        action="store_true",
        help=tr(
            "[Инженерная опция] Активировать XCP на шине CAN0 (пины 3/4 T12a, 500 кбит/с; обычным людям это не нужно)",
            "[Engineering Option] Enable XCP on CAN0 bus (T12a pins 3/4, 500 kbit/s; not needed for ordinary users)",
        ),
    )
    p_patch.add_argument(
        "--restore-stock",
        action="store_true",
        help=tr(
            "Побитово вернуть все пропатченные участки в 100%% заводской сток",
            "Losslessly revert all patched sites back to 100%% factory stock",
        ),
    )
    p_patch.add_argument(
        "--build-odx",
        type=Path,
        metavar="DIR",
        help=tr("Собрать готовые пакеты PART1 (+ PART2) для прошивки в ODIS-E (без сжатия 00)", "Build PART1 (+ PART2) ODX packages for ODIS-E in DIR (uncompressed 00)"),
    )
    p_patch.add_argument(
        "--template-odx",
        type=Path,
        help=tr("Заводской .odx-f/.odx/.frf шаблон (если вход — сырой дамп/DB_01)", "Factory .odx-f/.odx/.frf template (when input is raw dump/DB_01)"),
    )
    p_patch.add_argument(
        "--odx-layout",
        choices=("extern", "intern", "both"),
        default="extern",
        help=tr("Формат ODX: extern (.odx-f + BF_*.bin + index.xml), intern (.odx) или both", "ODX layout: extern (.odx-f + BF_*.bin + index.xml), intern (.odx), or both"),
    )
    p_patch.add_argument("--no-part2", action="store_true", help=tr("Не собирать пакет PART2", "Skip generating PART2 package"))
    p_patch.add_argument("--frf-key", type=Path, help=tr("Свой frf.key (по умолчанию встроен)", "Custom frf.key (built-in by default)"))
    p_patch.add_argument("--ignore-input-crc", action="store_true", help=tr("Игнорировать входной FW-CHECKSUM", "Ignore input FW-CHECKSUM mismatch"))
    p_patch.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help=tr("Подтвердить понимание рисков без интерактивного запроса [y/N]", "Confirm responsibility warning without interactive [y/N] prompt"),
    )
    p_patch.add_argument(
        "-v",
        "--verbose",
        dest="sub_verbose",
        action="store_true",
        help=tr("Показать технические подробности (адреса, CRC, SHA-256)", "Show technical details (addresses, CRC, SHA-256)"),
    )

    # unpack
    p_unp = sub.add_parser(
        "unpack",
        help=tr(
            "Распаковать контейнер прошивки (.odx-f, .odx, .pdx, .frf, ODIS 1.xml)",
            "Unpack flash container (.odx-f, .odx, .pdx, .frf, ODIS 1.xml)",
        ),
    )
    p_unp.add_argument("input", type=Path, help=tr("Путь к контейнеру", "Path to container"))
    p_unp.add_argument("-o", "--output-dir", type=Path, required=True, help=tr("Целевая папка распаковки", "Output folder"))
    p_unp.add_argument("--skip-db03", "--skip-large", dest="skip_large", action="store_true", help=tr("Пропустить 64 МиБ блок EyeQ4 DB_03", "Skip 64 MiB EyeQ4 DB_03 block"))
    p_unp.add_argument("--frf-key", type=Path, help=tr("Свой frf.key (по умолчанию встроен)", "Custom frf.key (built-in by default)"))
    p_unp.add_argument("--ignore-input-crc", action="store_true", help=tr("Игнорировать входной FW-CHECKSUM", "Ignore input FW-CHECKSUM"))

    # selftest
    sub.add_parser(
        "selftest",
        help=tr("Запустить встроенные самотесты сигнатур, кодеков и откатов", "Run built-in self-tests across ECU modules"),
    )

    return parser


def _print_target_table(st: Style) -> None:
    print(render_cli_disclaimer_box(st))
    print()
    print(st.bold(tr("Поддерживаемые модули ЭБУ:", "Supported ECU Target Modules:")))
    headers = (
        tr("Таргет", "Target"),
        tr("Адрес", "Addr"),
        tr("Модуль ЭБУ", "ECU Module"),
        tr("Платформа / MCU", "Platform / MCU"),
        tr("Дока", "Docs"),
    )
    rows: list[tuple[str, str, str, str, str]] = []
    doc_suffix = "README.en.md" if get_lang() == "en" else "README.md"
    for tgt in list_targets():
        rows.append((
            st.cyan(tgt.target_id),
            st.bold(tgt.ecu_address),
            tgt.title(),
            st.dim(tgt.arch_name),
            st.green(f"targets/{tgt.target_id}/{doc_suffix}"),
        ))
    widths = [
        max(vlen(headers[col]), *(vlen(r[col]) for r in rows))
        for col in range(len(headers))
    ]
    top = "┌─" + "─┬─".join("─" * w for w in widths) + "─┐"
    sep = "├─" + "─┼─".join("─" * w for w in widths) + "─┤"
    bot = "└─" + "─┴─".join("─" * w for w in widths) + "─┘"
    print(top)
    print("│ " + " │ ".join(st.bold(pad_right(headers[i], widths[i])) for i in range(len(headers))) + " │")
    print(sep)
    for r in rows:
        print("│ " + " │ ".join(pad_right(r[i], widths[i]) for i in range(len(headers))) + " │")
    print(bot)


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    early_lang = detect_early_cli_lang(raw_argv)
    if early_lang:
        set_lang(early_lang)

    parser = _build_arg_parser()
    args = parser.parse_args(raw_argv)
    if args.lang:
        set_lang(args.lang)

    use_color = (not args.no_color) and (os.environ.get("NO_COLOR") is None) and sys.stdout.isatty()
    st = Style(use_color)

    if args.list_targets:
        _print_target_table(st)
        return 0

    # Launch full-screen interactive `ncurses`-style TUI when no subcommand or `tui`/`wizard`
    if args.cmd in (None, "tui", "wizard"):
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            _print_target_table(st)
            print()
            parser.print_help()
            return 0
        init_tgt = get_target(args.target) if args.target else None
        with TuiScreen(use_color=not args.no_color and os.environ.get("NO_COLOR") is None) as scr:
            app = KsPatcherTuiApp(
                scr,
                skip_lang_prompt=bool(early_lang or args.lang),
                initial_target=init_tgt,
            )
            return app.run()

    if args.cmd == "selftest":
        print(render_cli_disclaimer_box(st))
        targets = [get_target(args.target)] if args.target else list_targets()
        for tgt in targets:
            print(f"\n{st.bold(st.cyan(f'══ Self-Test: {tgt.ecu_address} • {tgt.title()} ({tgt.arch_name}) ══'))}")
            for ln in tgt.selftest():
                print("  " + st.green(ln))
        print(f"\n{st.bold(st.green(tr('Все самотесты успешно пройдены!', 'All self-tests passed!')))}")
        return 0

    target = get_target(args.target or "mfk3")
    is_verbose = bool(args.verbose or getattr(args, "sub_verbose", False))

    if args.cmd == "inspect":
        insp = target.inspect_file(
            args.input,
            frf_key_path=args.frf_key,
            ignore_input_crc=args.ignore_input_crc,
        )
        if args.json:
            payload = dataclasses.asdict(insp)
            payload["source_path"] = str(insp.source_path)
            for s in payload["sites"]:
                s["spec"]["edits"] = [
                    {
                        "rel_offset": e["rel_offset"],
                        "stock_bytes": e["stock_bytes"].hex(),
                        "patched_bytes": e["patched_bytes"].hex(),
                    }
                    for e in s["spec"]["edits"]
                ]
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        print(render_cli_disclaimer_box(st))
        print()
        for ln in target.render_inspection_lines(insp, st, verbose=is_verbose):
            print(ln)
        return 0

    if args.cmd == "patch":
        print(render_cli_disclaimer_box(st))
        print()
        print(render_cli_final_warning_box(st))
        print()
        if sys.stdin.isatty() and not args.yes:
            prompt_s = st.bold(
                tr(
                    "Вы принимаете ответственность и риски? Сгенерировать файлы? [y/N]: ",
                    "Do you accept all risks and responsibility? Generate files? [y/N]: ",
                )
            )
            try:
                ans = input(prompt_s).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return 1
            if ans not in ("y", "yes", "д", "да"):
                print(st.yellow(tr("Операция отменена пользователем.", "Operation cancelled by user.")))
                return 0
            print()

        opts = PatchOptions(
            restore_stock=args.restore_stock,
            activate_all_fecs=not args.no_fecs,
            suppress_key_dtcs=args.suppress_key_dtcs,
            enable_xcp_can0=args.enable_xcp_can0,
            output_bin=args.output,
            in_place=args.in_place,
            build_odx_dir=args.build_odx,
            template_odx=args.template_odx,
            odx_method="00",
            odx_layout=args.odx_layout,
            include_part2=not args.no_part2,
            frf_key_path=args.frf_key,
            ignore_input_crc=args.ignore_input_crc,
        )
        res = target.patch_file(args.input, opts)
        for ln in target.render_patch_result_lines(res, st, verbose=is_verbose):
            print(ln)
        return 0

    if args.cmd == "unpack":
        print(render_cli_disclaimer_box(st))
        print()
        rows = target.unpack_container(
            args.input,
            args.output_dir,
            skip_large_blocks=args.skip_large,
            frf_key_path=args.frf_key,
            ignore_input_crc=args.ignore_input_crc,
        )
        print(st.bold(st.green(tr("══ Контейнер успешно распакован! ══", "══ Container Unpacked Successfully! ══"))))
        for name, method, raw_sz, dec_sz, crc, fp in rows:
            print(
                f"  • {st.bold(name):<22}  method=0x{method:02X}  "
                f"{raw_sz:>10,} B -> {dec_sz:>10,} B  CRC32=0x{crc:08X}  -> {fp}"
            )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError, RuntimeError) as err:
        sys.stderr.write(f"\n[!] Error: {err}\n")
        raise SystemExit(2) from None
