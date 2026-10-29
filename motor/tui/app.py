"""Sleek interactive TUI controller with ECU Selector, simple wizards, and pre-generation safety warning."""

from __future__ import annotations

from pathlib import Path
import traceback

from ..core.i18n import tr
from ..core.target_base import EcuTargetPlugin, PatchOptions
from ..targets import list_targets
from ..targets.mfk3.loader import find_sibling_mfk3_template_odx
from .screen import TuiScreen
from .widgets import CheckboxItem, MenuItem, TuiWindowMixin


class KsPatcherTuiApp(TuiWindowMixin):
    """Main full-screen TUI controller for `KSchutz & FeC Patcher`."""

    def __init__(
        self,
        scr: TuiScreen,
        search_roots: list[Path] | None = None,
        *,
        skip_lang_prompt: bool = False,
        initial_target: EcuTargetPlugin | None = None,
    ) -> None:
        self.scr = scr
        self.st = scr.st
        self.skip_lang_prompt = skip_lang_prompt
        self.initial_target = initial_target
        self.active_target_badge = ""
        self.last_dir = Path.cwd().resolve()

        if search_roots is not None:
            self.search_roots = search_roots
        else:
            cwd = Path.cwd().resolve()
            pkg_root = Path(__file__).resolve().parents[1]
            roots = [cwd]
            if pkg_root != cwd:
                roots.append(pkg_root)
            self.search_roots = roots

    def run(self) -> int:
        try:
            if not self.skip_lang_prompt:
                self.select_language_modal()
            if not self.startup_disclaimer_modal():
                return 0

            if self.initial_target is not None:
                res = self.run_target_workspace(self.initial_target)
                if res == "exit":
                    return 0

            return self.select_target_loop()
        except (EOFError, KeyboardInterrupt):
            return 0

    def select_target_loop(self) -> int:
        while True:
            self.active_target_badge = ""
            targets = list_targets()

            def _build_items() -> list[MenuItem]:
                items: list[MenuItem] = []
                for idx, tgt in enumerate(targets, 1):
                    hk = str(idx) if idx <= 9 else ""
                    badge_s = self.st.green(f"{tr('Блок', 'Unit')} {tgt.ecu_address}  •  KS + FeC")
                    items.append(
                        MenuItem(
                            item_id=f"tgt:{tgt.target_id}",
                            hotkey=hk,
                            label=tgt.title(),
                            badge=badge_s,
                            details=tuple(tgt.description_lines(self.st)),
                        )
                    )
                items.extend([
                    MenuItem(
                        item_id="lang",
                        hotkey="L",
                        label=tr("Сменить язык интерфейса (RU / EN)", "Switch Language (RU / EN)"),
                        badge=self.st.dim("RU / EN"),
                        details=(
                            tr("Переключение между русским и английским языками.", "Toggle between Russian and English."),
                        ),
                    ),
                    MenuItem(
                        item_id="exit",
                        hotkey="0",
                        label=tr("Выход", "Exit"),
                        badge="",
                        details=(tr("Закрыть программу.", "Quit application."),),
                    ),
                ])
                return items

            choice = self.menu_window(
                title_fn=lambda: tr("Выбор блока ЭБУ", "Select Control Unit"),
                info_fn=lambda: [
                    tr(
                        "Выберите блок, для которого нужно подготовить прошивку или дамп:",
                        "Choose the ECU unit you want to prepare firmware or dump files for:",
                    ),
                ],
                items_fn=_build_items,
                keybar_fn=lambda: tr(
                    "↑↓ Выбор блока   •   Enter Открыть   •   L Язык   •   0 Выход",
                    "↑↓ Select Unit   •   Enter Open   •   L Language   •   0 Exit",
                ),
            )

            if choice is None or choice == "exit":
                return 0
            if choice == "lang":
                self.toggle_lang()
                continue
            if choice.startswith("tgt:"):
                tid = choice.split(":", 1)[1]
                selected = next((t for t in targets if t.target_id == tid), None)
                if selected is not None:
                    nav = self.run_target_workspace(selected)
                    if nav == "exit":
                        return 0

    def run_target_workspace(self, target: EcuTargetPlugin) -> str:
        """Main action menu for a chosen ECU target. Returns `'back'` or `'exit'`."""
        while True:
            self.active_target_badge = f"{target.ecu_address} • {target.target_id.upper()}"

            def _build_items() -> list[MenuItem]:
                items: list[MenuItem] = []
                if target.supports_odx_build:
                    items.append(
                        MenuItem(
                            item_id="patch_odx",
                            hotkey="1",
                            label=tr(
                                "Собрать прошивку под ODIS-E (PART1 + PART2)",
                                "Build ODIS-E Flash Packages (PART1 + PART2)",
                            ),
                            badge=self.st.green(tr("Без разбора", "Via OBD / CAN")),
                            details=(
                                tr(
                                    "Готовит две папки (PART1 и PART2) из обычного .frf / .odx-f для записи в камеру через ODIS-E.",
                                    "Builds PART1 & PART2 folders from a standard .frf / .odx-f for flashing via ODIS-E.",
                                ),
                            ),
                        )
                    )
                items.extend([
                    MenuItem(
                        item_id="patch_bin",
                        hotkey="2" if target.supports_odx_build else "1",
                        label=tr(
                            "Пропатчить дамп под программатор (.bin)",
                            "Patch Flash Dump for Programmer (.bin)",
                        ),
                        badge=self.st.cyan(tr("На столе", "Bench Dump")),
                        details=(
                            tr(
                                "Отключает защиту компонентов и открывает все функции в вычитанном .bin дампе памяти.",
                                "Disables Component Protection and unlocks all features inside a raw .bin dump.",
                            ),
                        ),
                    ),
                    MenuItem(
                        item_id="inspect",
                        hotkey="3" if target.supports_odx_build else "2",
                        label=tr(
                            "Проверить файл (узнать статус защиты и функций)",
                            "Check File Status (CP & Features)",
                        ),
                        badge=self.st.dim(tr("Проверка", "Read-Only")),
                        details=(
                            tr(
                                "Показывает, включена ли защита компонентов и открыты ли платные функции в выбранном файле.",
                                "Checks whether Component Protection and paid features are active or unlocked in a file.",
                            ),
                        ),
                    ),
                    MenuItem(
                        item_id="restore_stock",
                        hotkey="4" if target.supports_odx_build else "3",
                        label=tr(
                            "Вернуть файл в 100% заводской сток",
                            "Restore File to 100% Factory Stock",
                        ),
                        badge=self.st.yellow(tr("Откат", "Restore")),
                        details=(
                            tr(
                                "Полностью возвращает ранее пропатченный файл к заводскому оригиналу.",
                                "Completely reverts a previously patched file back to factory original.",
                            ),
                        ),
                    ),
                ])
                if target.supports_container_unpack:
                    items.append(
                        MenuItem(
                            item_id="unpack",
                            hotkey="5",
                            label=tr(
                                "Распаковать заводской контейнер (.frf / .odx-f)",
                                "Unpack Firmware Container (.frf / .odx-f)",
                            ),
                            badge=self.st.dim(tr("Утилита", "Utility")),
                            details=(
                                tr(
                                    "Извлекает внутренние блоки прошивки из зашифрованного .frf или .odx-f в обычные .bin файлы.",
                                    "Extracts raw .bin blocks from an encrypted .frf or .odx-f container.",
                                ),
                            ),
                        )
                    )
                items.extend([
                    MenuItem(
                        item_id="back",
                        hotkey="B",
                        label=tr("← Сменить блок ЭБУ", "← Change Control Unit"),
                        badge="",
                        details=(
                            tr("Вернуться к списку блоков ЭБУ.", "Return to the ECU selection screen."),
                        ),
                    ),
                    MenuItem(
                        item_id="exit",
                        hotkey="0",
                        label=tr("Выход", "Exit"),
                        badge="",
                        details=(tr("Закрыть программу.", "Quit application."),),
                    ),
                ])
                return items

            action = self.menu_window(
                title_fn=target.title,
                info_fn=lambda: [
                    self.st.dim(target.subtitle()),
                ],
                items_fn=_build_items,
                keybar_fn=lambda: tr(
                    "↑↓ Выбор действия   •   Enter Открыть   •   B Сменить блок   •   L Язык   •   0 Выход",
                    "↑↓ Select Action   •   Enter Open   •   B Change Unit   •   L Language   •   0 Exit",
                ),
            )

            if action is None or action == "back":
                return "back"
            if action == "exit":
                return "exit"
            if action == "inspect":
                self._flow_inspect(target)
            elif action == "patch_bin":
                self._flow_patch_binary(target)
            elif action == "patch_odx":
                self._flow_patch_odx(target)
            elif action == "restore_stock":
                self._flow_restore_stock(target)
            elif action == "unpack":
                self._flow_unpack(target)

    # ---- Individual Interactive Flows -------------------------------------

    def _pick_target_file(
        self,
        target: EcuTargetPlugin,
        title_ru: str,
        title_en: str,
        *,
        step_badge: str = "",
    ) -> Path | None:
        picked = self.file_picker_modal(
            title_fn=lambda: tr(title_ru, title_en),
            hint_fn=target.input_hint,
            candidates_fn=lambda: target.discover_candidates(self.search_roots),
            start_dir=self.last_dir,
            expected_sizes=target.expected_dump_sizes,
            allowed_exts=target.allowed_extensions,
            right_badge=step_badge,
        )
        if picked is not None:
            self.last_dir = picked.parent
        return picked

    def _show_error(self, exc: Exception) -> None:
        tb_short = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        self.alert_modal(
            title_fn=lambda: tr("Не удалось выполнить операцию", "Operation Failed"),
            body_fn=lambda _w: [
                self.st.red(self.st.bold(tb_short)),
            ],
            border_color="red",
        )

    def _flow_inspect(self, target: EcuTargetPlugin) -> None:
        src = self._pick_target_file(
            target,
            "Выберите файл для проверки",
            "Select File to Check",
        )
        if src is None:
            return
        try:
            insp = target.inspect_file(src)
        except Exception as exc:
            self._show_error(exc)
            return

        border = "green" if insp.ks_state == "patched" else ("yellow" if insp.ks_state == "stock" else "red")
        self.alert_modal(
            title_fn=lambda: tr(f"Информация о файле • {src.name}", f"File Status • {src.name}"),
            body_fn=lambda _w: target.render_inspection_lines(insp, self.st, verbose=False),
            detailed_body_fn=lambda _w: target.render_inspection_lines(insp, self.st, verbose=True),
            border_color=border,
        )

    def _flow_patch_odx(self, target: EcuTargetPlugin) -> None:
        src = self._pick_target_file(
            target,
            "Выберите заводскую прошивку (.frf / .odx-f)",
            "Select Factory Firmware (.frf / .odx-f)",
            step_badge=tr("Шаг 1 из 4", "Step 1 of 4"),
        )
        if src is None:
            return
        try:
            insp = target.inspect_file(src)
        except Exception as exc:
            self._show_error(exc)
            return

        init_flags = {
            "ks_passive": True,
            "activate_all_fecs": True,
            "suppress_key_dtcs": insp.key_dtc_state == "patched",
            "enable_xcp_can0": insp.xcp_state == "patched",
        }

        def _make_checkboxes(_state: dict[str, bool]) -> list[CheckboxItem]:
            rows: list[CheckboxItem] = [
                CheckboxItem(
                    item_id="ks_passive",
                    label=tr(
                        "Отключить защиту компонентов (пассивный режим без ошибок)",
                        "Disable Component Protection (passive mode, no fault codes)",
                    ),
                    checked=True,
                    locked=True,
                ),
                CheckboxItem(
                    item_id="activate_all_fecs",
                    label=tr(
                        "Активировать все платные функции камеры (знаки VZE, полоса, автодальний, pACC)",
                        "Activate all paid camera features (VZE signs, Lane Assist, HBA, pACC)",
                    ),
                    checked=True,
                    details=(
                        tr(
                            "Все 9 функций открываются сразу — покупка или заливка ключей не требуется.",
                            "Unlocks all 9 features immediately — no activation keys required.",
                        ),
                    ),
                ),
                CheckboxItem(
                    item_id="suppress_key_dtcs",
                    label=tr(
                        "Подавить ошибки непривязанных ключей (только для новой «чистой» камеры)",
                        "Suppress unadapted key faults (only for brand-new Virgin cameras)",
                    ),
                    checked=False,
                    details=(
                        tr(
                            "Включайте только для новой с магазина камеры. Для б/у камер с разборки оставьте выключенным.",
                            "Enable only on brand-new Virgin cameras; leave off for used donor cameras.",
                        ),
                    ),
                ),
            ]
            if target.supports_xcp_unlock:
                rows.append(
                    CheckboxItem(
                        item_id="enable_xcp_can0",
                        label=tr(
                            "[Инженерная опция] Активировать XCP на шине CAN0 (обычным людям это НЕ нужно)",
                            "[Engineering Option] Enable XCP on CAN0 bus (NOT needed for ordinary users)",
                        ),
                        checked=False,
                        details=(
                            tr(
                                "Включает протокол XCP на шине CAN0 (пины 3=CAN-H и 4=CAN-L T12a, 500 кбит/с, ID 0x1BFE7E01/00). "
                                "Обычным пользователям для установки в авто НЕ нужно — только для стенда/исследований.",
                                "Enables XCP protocol on CAN0 bus (T12a pins 3=CAN-H & 4=CAN-L, 500 kbit/s, ID 0x1BFE7E01/00). "
                                "Ordinary users do NOT need this for car installation — bench/research only.",
                            ),
                        ),
                    )
                )
            return rows

        chosen = self.checkbox_modal(
            title_fn=lambda: tr("Настройки прошивки под ODIS-E", "ODIS-E Package Settings"),
            info_fn=lambda: [
                f"{self.st.dim(tr('Выбран файл:', 'Selected file:'))}  {self.st.bold(src.name)}   "
                f"{self.st.dim('(' + insp.format_label + ')')}",
            ],
            items_fn=_make_checkboxes,
            initial_state=init_flags,
            right_badge=tr("Шаг 2 из 4", "Step 2 of 4"),
        )
        if chosen is None:
            return

        tmpl_odx: Path | None = None
        if insp.format_kind != "odx_container" and find_sibling_mfk3_template_odx(src) is None:
            tmpl_odx = self._pick_template_odx(target)
            if tmpl_odx is None:
                return

        base_dir = src.parent if _can_write_dir(src.parent) else Path.cwd()
        def_dir = base_dir / "ODIS_MFK3_READY"
        out_dir_s = self.input_modal(
            title_fn=lambda: tr("Куда сохранить готовые папки PART1 и PART2", "Where to Save PART1 & PART2 Folders"),
            info_fn=lambda: [
                tr("Папка будет создана автоматически:", "Output folder will be created automatically:"),
                self.st.cyan(str(def_dir)),
            ],
            default_val=str(def_dir),
            initial_text=str(def_dir),
            right_badge=tr("Шаг 3 из 4", "Step 3 of 4"),
        )
        if out_dir_s is None:
            return
        out_dir = Path(out_dir_s).expanduser().resolve()

        act_fecs = chosen.get("activate_all_fecs", True)
        en_xcp = chosen.get("enable_xcp_can0", False)
        xcp_note_s = (
            " + " + tr("инж. XCP на CAN0", "eng. XCP on CAN0")
            if en_xcp
            else ""
        )
        if not self.final_generation_warning_modal(
            lambda: [
                f"{self.st.dim(tr('Исходный файл :', 'Source file   :'))}  {self.st.bold(src.name)}",
                f"{self.st.dim(tr('Что делаем    :', 'Action        :'))}  "
                + self.st.green(
                    (
                        tr("Отключение KS + активация всех функций", "Disable KS + unlock all features")
                        if act_fecs
                        else tr("Отключение KS", "Disable KS")
                    )
                    + xcp_note_s
                    + " (ODIS-E)"
                ),
                f"{self.st.dim(tr('Папка вывода  :', 'Output folder :'))}  {self.st.cyan(str(out_dir))}",
            ]
        ):
            return

        try:
            res = target.patch_file(
                src,
                PatchOptions(
                    restore_stock=False,
                    activate_all_fecs=act_fecs,
                    suppress_key_dtcs=chosen.get("suppress_key_dtcs", False),
                    enable_xcp_can0=en_xcp,
                    output_bin=None,
                    build_odx_dir=out_dir,
                    template_odx=tmpl_odx,
                    odx_method="00",
                    odx_layout="extern",
                    include_part2=True,
                ),
            )
        except Exception as exc:
            self._show_error(exc)
            return

        self.alert_modal(
            title_fn=lambda: tr("Прошивка под ODIS-E готова!", "ODIS-E Packages Ready!"),
            body_fn=lambda _w: target.render_patch_result_lines(res, self.st, verbose=False),
            detailed_body_fn=lambda _w: target.render_patch_result_lines(res, self.st, verbose=True),
            border_color="green",
        )

    def _flow_patch_binary(self, target: EcuTargetPlugin) -> None:
        src = self._pick_target_file(
            target,
            "Выберите дамп или файл для патча",
            "Select Dump or Firmware File",
            step_badge=tr("Шаг 1 из 4", "Step 1 of 4"),
        )
        if src is None:
            return
        try:
            insp = target.inspect_file(src)
        except Exception as exc:
            self._show_error(exc)
            return

        init_flags: dict[str, bool] = {
            "ks_passive": True,
            "activate_all_fecs": True,
            "suppress_key_dtcs": insp.key_dtc_state == "patched",
            "enable_xcp_can0": insp.xcp_state == "patched",
        }

        def _make_checkboxes(_state: dict[str, bool]) -> list[CheckboxItem]:
            rows: list[CheckboxItem] = [
                CheckboxItem(
                    item_id="ks_passive",
                    label=tr(
                        "Отключить защиту компонентов (пассивный режим без ошибок)",
                        "Disable Component Protection (passive mode, no fault codes)",
                    ),
                    checked=True,
                    locked=True,
                )
            ]
            if target.supports_fec_unlock:
                rows.append(
                    CheckboxItem(
                        item_id="activate_all_fecs",
                        label=tr(
                            "Активировать все платные функции камеры (знаки VZE, полоса, автодальний, pACC)",
                            "Activate all paid camera features (VZE signs, Lane Assist, HBA, pACC)",
                        ),
                        checked=True,
                        details=(
                            tr(
                                "Все 9 функций камеры будут работать сразу после записи дампа.",
                                "All 9 camera features will work immediately after writing the dump.",
                            ),
                        ),
                    )
                )
            if target.supports_key_dtc_suppress:
                rows.append(
                    CheckboxItem(
                        item_id="suppress_key_dtcs",
                        label=tr(
                            "Подавить ошибки непривязанных ключей (только для новой «чистой» камеры)",
                            "Suppress unadapted key faults (only for brand-new Virgin cameras)",
                        ),
                        checked=False,
                        details=(
                            tr(
                                "Для б/у камер с разборки оставьте выключенным.",
                                "Leave unchecked for used donor cameras.",
                            ),
                        ),
                    )
                )
            if target.supports_xcp_unlock:
                rows.append(
                    CheckboxItem(
                        item_id="enable_xcp_can0",
                        label=tr(
                            "[Инженерная опция] Активировать XCP на шине CAN0 (обычным людям это НЕ нужно)",
                            "[Engineering Option] Enable XCP on CAN0 bus (NOT needed for ordinary users)",
                        ),
                        checked=False,
                        details=(
                            tr(
                                "Включает протокол XCP на шине CAN0 (пины 3=CAN-H и 4=CAN-L T12a, 500 кбит/с, ID 0x1BFE7E01/00). "
                                "Обычным пользователям для установки в авто НЕ нужно — только для стенда/исследований.",
                                "Enables XCP protocol on CAN0 bus (T12a pins 3=CAN-H & 4=CAN-L, 500 kbit/s, ID 0x1BFE7E01/00). "
                                "Ordinary users do NOT need this for car installation — bench/research only.",
                            ),
                        ),
                    )
                )
            return rows

        chosen = self.checkbox_modal(
            title_fn=lambda: tr("Настройки патча дампа", "Dump Patch Settings"),
            info_fn=lambda: [
                f"{self.st.dim(tr('Выбран файл:', 'Selected file:'))}  {self.st.bold(src.name)}   "
                f"{self.st.dim('(' + insp.format_label + ')')}",
            ],
            items_fn=_make_checkboxes,
            initial_state=init_flags,
            right_badge=tr("Шаг 2 из 4", "Step 2 of 4"),
        )
        if chosen is None:
            return

        activate_fecs = chosen.get("activate_all_fecs", True)
        suppress_dtc = chosen.get("suppress_key_dtcs", False)
        enable_xcp = chosen.get("enable_xcp_can0", False)

        xcp_part = "_xcp" if enable_xcp else ""
        tag = f"patched{xcp_part}" if activate_fecs else f"ks_only{xcp_part}"
        out_dir_base = src.parent if _can_write_dir(src.parent) else Path.cwd()
        if insp.format_kind == "odx_container":
            default_out = out_dir_base / f"{src.stem}_DB_01_{tag}.bin"
        else:
            default_out = out_dir_base / f"{src.stem}_{tag}{src.suffix or '.bin'}"

        out_str = self.input_modal(
            title_fn=lambda: tr("Куда сохранить готовый .bin файл", "Where to Save Patched .bin File"),
            info_fn=lambda: [
                tr("Исходный файл останется нетронутым — результат запишется рядом:", "Original file stays untouched:"),
                self.st.cyan(str(default_out)),
            ],
            default_val=str(default_out),
            initial_text=str(default_out),
            right_badge=tr("Шаг 3 из 4", "Step 3 of 4"),
        )
        if out_str is None:
            return
        out_bin = Path(out_str).expanduser().resolve()

        xcp_note_b = (
            " + " + tr("инж. XCP на CAN0", "eng. XCP on CAN0")
            if enable_xcp
            else ""
        )
        if not self.final_generation_warning_modal(
            lambda: [
                f"{self.st.dim(tr('Исходный файл :', 'Source file   :'))}  {self.st.bold(src.name)}",
                f"{self.st.dim(tr('Что делаем    :', 'Action        :'))}  "
                + self.st.green(
                    (
                        tr("Отключение KS + активация всех функций", "Disable KS + unlock all features")
                        if activate_fecs
                        else tr("Отключение KS", "Disable KS")
                    )
                    + xcp_note_b
                    + " (.bin)"
                ),
                f"{self.st.dim(tr('Выходной файл :', 'Output file   :'))}  {self.st.cyan(str(out_bin))}",
            ]
        ):
            return

        try:
            res = target.patch_file(
                src,
                PatchOptions(
                    restore_stock=False,
                    activate_all_fecs=activate_fecs,
                    suppress_key_dtcs=suppress_dtc,
                    enable_xcp_can0=enable_xcp,
                    output_bin=out_bin,
                ),
            )
        except Exception as exc:
            self._show_error(exc)
            return

        self.alert_modal(
            title_fn=lambda: tr("Файл успешно подготовлен!", "File Prepared Successfully!"),
            body_fn=lambda _w: target.render_patch_result_lines(res, self.st, verbose=False),
            detailed_body_fn=lambda _w: target.render_patch_result_lines(res, self.st, verbose=True),
            border_color="green",
        )

    def _pick_template_odx(self, target: EcuTargetPlugin) -> Path | None:
        return self.file_picker_modal(
            title_fn=lambda: tr(
                "Укажите заводской файл прошивки (.frf / .odx-f)",
                "Select Factory Firmware Template (.frf / .odx-f)",
            ),
            hint_fn=lambda: tr(
                "Для упаковки сырого дампа под ODIS-E нужен оригинальный .frf или .odx-f от этой камеры",
                "Building ODIS-E packages from a raw dump requires the matching factory .frf or .odx-f",
            ),
            candidates_fn=lambda: [
                p
                for p in target.discover_candidates(self.search_roots)
                if p.suffix.lower() in (".odx-f", ".odx", ".pdx", ".frf")
            ],
            start_dir=self.last_dir,
            allowed_exts=(".odx-f", ".odx", ".pdx", ".frf", ".xml"),
        )

    def _flow_restore_stock(self, target: EcuTargetPlugin) -> None:
        src = self._pick_target_file(
            target,
            "Выберите пропатченный файл для возврата в сток",
            "Select Patched File to Restore",
            step_badge=tr("Шаг 1 из 3", "Step 1 of 3"),
        )
        if src is None:
            return
        base_dir = src.parent if _can_write_dir(src.parent) else Path.cwd()
        def_out = base_dir / f"{src.stem}_stock.bin"
        out_s = self.input_modal(
            title_fn=lambda: tr("Куда сохранить восстановленный сток", "Where to Save Restored Stock File"),
            info_fn=lambda: [
                tr("Файл будет возвращён к 100% заводскому оригиналу:", "File will be reverted to 100% factory stock:"),
                self.st.cyan(str(def_out)),
            ],
            default_val=str(def_out),
            initial_text=str(def_out),
            right_badge=tr("Шаг 2 из 3", "Step 2 of 3"),
        )
        if out_s is None:
            return
        out_bin = Path(out_s).expanduser().resolve()

        if not self.final_generation_warning_modal(
            lambda: [
                f"{self.st.dim(tr('Исходный файл :', 'Source file   :'))}  {self.st.bold(src.name)}",
                f"{self.st.dim(tr('Что делаем    :', 'Action        :'))}  "
                + self.st.yellow(tr("Возврат в заводской сток", "Restore to factory stock")),
                f"{self.st.dim(tr('Выходной файл :', 'Output file   :'))}  {self.st.cyan(str(out_bin))}",
            ]
        ):
            return

        try:
            res = target.patch_file(
                src,
                PatchOptions(
                    restore_stock=True,
                    output_bin=out_bin,
                ),
            )
        except Exception as exc:
            self._show_error(exc)
            return

        self.alert_modal(
            title_fn=lambda: tr("Заводской сток восстановлен!", "Factory Stock Restored!"),
            body_fn=lambda _w: target.render_patch_result_lines(res, self.st, verbose=False),
            detailed_body_fn=lambda _w: target.render_patch_result_lines(res, self.st, verbose=True),
            border_color="green",
        )

    def _flow_unpack(self, target: EcuTargetPlugin) -> None:
        src = self.file_picker_modal(
            title_fn=lambda: tr(
                "Выберите контейнер для распаковки (.frf / .odx-f)",
                "Select Container to Unpack (.frf / .odx-f)",
            ),
            hint_fn=lambda: tr(
                "Выберите зашифрованный .frf или .odx-f для извлечения блоков в .bin",
                "Select an encrypted .frf or .odx-f to extract raw .bin blocks",
            ),
            candidates_fn=lambda: [
                p
                for p in target.discover_candidates(self.search_roots)
                if p.suffix.lower() in (".odx-f", ".odx", ".pdx", ".frf", ".xml")
            ],
            start_dir=self.last_dir,
            allowed_exts=(".odx-f", ".odx", ".pdx", ".frf", ".xml"),
        )
        if src is None:
            return
        self.last_dir = src.parent
        skip_big = self.confirm_modal(
            title_fn=lambda: tr("Пропустить большой 64 МБ блок видеочипа?", "Skip Large 64 MB Video-Chip Block?"),
            body_fn=lambda: [
                tr(
                    "Извлечь только основные блоки программы камеры (мгновенно, без 64 МБ блока DB_03)?",
                    "Extract only main camera program blocks (instant, skips the 64 MB DB_03 block)?",
                ),
            ],
            default=True,
            yes_fn=lambda: tr(" ✓ Да, быстро ", " ✓ Yes, fast "),
            no_fn=lambda: tr(" Извлечь всё (с 64 МБ) ", " Extract all (with 64 MB) "),
        )
        if skip_big is None:
            return

        base_dir = src.parent if _can_write_dir(src.parent) else Path.cwd()
        def_out = base_dir / f"{src.stem}_unpacked"
        out_s = self.input_modal(
            title_fn=lambda: tr("Папка для распакованных файлов", "Output Folder for Unpacked Files"),
            info_fn=lambda: [self.st.cyan(str(def_out))],
            default_val=str(def_out),
            initial_text=str(def_out),
        )
        if out_s is None:
            return
        out_dir = Path(out_s).expanduser().resolve()

        try:
            rows = target.unpack_container(src, out_dir, skip_large_blocks=skip_big)
        except Exception as exc:
            self._show_error(exc)
            return

        lines = [
            self.st.bold(self.st.green(tr("✓ Контейнер успешно распакован!", "✓ Container Unpacked Successfully!"))),
            "",
            f"  {self.st.dim(tr('Папка :', 'Folder:'))}  {self.st.cyan(str(out_dir))}",
            "",
        ]
        for name, _method, _raw_sz, dec_sz, _crc, fp in rows:
            sz_txt = f"{dec_sz / (1024 * 1024):.2f} MB" if dec_sz >= 1024 * 1024 else f"{dec_sz:,} B"
            lines.append(f"    • {self.st.bold(fp.name):<26}  ({sz_txt})")
        self.alert_modal(
            title_fn=lambda: tr("Распаковка завершена", "Unpack Complete"),
            body_fn=lambda _w: lines,
            border_color="green",
        )


def _can_write_dir(d: Path) -> bool:
    try:
        probe = d / ".ks_tui_probe.tmp"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False
