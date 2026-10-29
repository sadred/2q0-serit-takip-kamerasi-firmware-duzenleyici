#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MFK3 Crack Builder — ham firmware → CP/FeC/DTC yamalı ODIS-E paketi

Ne yapar:
  • Girdi: ham firmware dosyaları (FL_*.frf / .odx-f / .odx / .pdx, ya da programmer dump .bin)
  • Seçenek: CP pasif · FeC (9 kod) · Virgin key DTC bastırma · (ops.) XCP/CAN0
  • Çıktı: her sürüm için ODIS-E 17/18 ile yazılabilir PART1 + PART2 klasörü + RAPOR.txt

Yama motoru: Schutz-Kaput (ks_patcher.py, PerkTheFox) — otomatik bulunur.
Bu program firmware içermez; yalnızca kullanıcının kendi dosyalarını işler.
Lisans: non-commercial / Right-to-Repair. Risk kullanıcıda.

Gereksinim: Python 3.9+ (tkinter dahil, harici paket yok).
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import zlib
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "Denizli Garaj 2Q Şerit Takip Kamerası Yazılım Düzenleyici"
APP_SHORT = "Denizli Garaj 2Q Kamera Düzenleyici"
APP_VERSION = "2.0"
APP_SUBTITLE = ("Valeo MFK3 · 2Q0 980 653B/C/D/J · diag 0x00A5 · "
                "ham firmware → CP/FeC/DTC yamalı ODIS-E paketi")
SOURCE_PROJECT = "Schutz-Kaput / PerkTheFox — https://github.com/perkthefox/mqb-kshutz-kaput"
TARGET_ID = "mfk3"
HERE = Path(__file__).resolve().parent
FROZEN = bool(getattr(sys, "frozen", False))
# paket içi kaynaklar (PyInstaller _MEIPASS), ayarlar ise exe'nin yanında
ASSET_DIR = Path(getattr(sys, "_MEIPASS", HERE)) / "assets"
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else HERE
CONFIG_PATH = APP_DIR / "duzenleyici_ayarlar.json"
DB01_HEADER = bytes.fromhex("000000AA00820400")
INPUT_SUFFIXES = (".frf", ".odx-f", ".odx", ".pdx", ".bin")
DEFAULT_OUT = Path.home() / "Desktop" / "2Q_KAMERA_YAMALI"
DEFAULT_OUT_KDT = Path.home() / "Desktop" / "2Q_KAMERA_YAMALI_KDT"


# ==========================================================================
# Yardımcılar
# ==========================================================================
def resolve_tool() -> Path | None:
    """ks_patcher.py'yi bilinen yerlerde ara (önce exe'nin yanı)."""
    cands = [
        APP_DIR,
        APP_DIR / "mqb-kshutz-kaput",
        APP_DIR / "motor",
        Path.home() / "Documents/tools/mqb-kshutz-kaput",
        Path.home() / "Documents/mqb-kshutz-kaput",
        Path.home() / "Desktop/mqb-kshutz-kaput",
        Path.home() / "Downloads/mqb-kshutz-kaput",
        HERE.parent / "mqb-kshutz-kaput",
    ]
    for c in cands:
        p = c / "ks_patcher.py"
        if p.is_file():
            return p
    for p in Path.home().glob("**/mqb-kshutz-kaput/ks_patcher.py"):
        return p
    return None


def label_from_name(name: str) -> tuple[str, str]:
    """Dosya adından (sürüm, parça) çıkar: FL_2Q0980653D_1421_MEAPP_V001_S.frf → ('1421', '2Q0980653D')."""
    m = re.search(r"(2Q0\d+[A-Z]?)_(\d{4})_MEAPP", name, re.I)
    if m:
        return m.group(2), m.group(1).upper()
    m = re.search(r"_(\d{4})_", name)
    return (m.group(1) if m else "?"), "?"


def build_patch_cmd(tool: Path, src: Path, *, cp: bool, fec: bool, kdtc: bool, xcp: bool,
                    odx: bool, out_dir: Path, python_exe: str | None = None) -> list[str]:
    cmd = [python_exe or sys.executable, str(tool), "-l", "en", "-t", TARGET_ID, "patch", str(src)]
    if not fec:
        cmd.append("--no-fecs")
    if kdtc:
        cmd.append("--suppress-key-dtcs")
    if xcp:
        cmd.append("--enable-xcp-can0")
    if odx:
        cmd += ["--build-odx", str(out_dir)]
    else:
        cmd += ["-o", str(out_dir / f"{src.stem}_KS.bin")]
    cmd.append("-y")
    return cmd


def parse_json(text: str) -> dict | None:
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e <= s:
        return None
    try:
        return json.loads(text[s:e + 1])
    except json.JSONDecodeError:
        return None


def run_tool(tool: Path, args: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.run([sys.executable, str(tool)] + args, cwd=str(tool.parent),
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=env, timeout=timeout, creationflags=flags)


# ==========================================================================
# Arayüz
# ==========================================================================
class Builder(ttk.Frame):
    def __init__(self, master: tk.Tk, tool: Path | None):
        super().__init__(master, padding=10)
        self.master = master
        self.tool = tool
        self.pack(fill="both", expand=True)

        self.cfg = self._load_cfg()
        self.items: dict[str, dict] = {}       # iid -> {path, label, part, ticked, status, note}
        self.q: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel = threading.Event()
        self.running = False
        self.t0 = 0.0

        self._vars()
        self._ui()
        self._apply_cfg()

    # ---------- config ----------
    def _load_cfg(self) -> dict:
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_cfg(self) -> None:
        try:
            CONFIG_PATH.write_text(json.dumps({
                "cp": self.v_cp.get(), "fec": self.v_fec.get(), "kdtc": self.v_kdtc.get(),
                "xcp": self.v_xcp.get(), "odx": self.v_odx.get(),
                "out": self.v_out.get(), "geometry": self.master.geometry(),
            }, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def _vars(self) -> None:
        self.v_cp = tk.BooleanVar(value=True)
        self.v_fec = tk.BooleanVar(value=True)
        self.v_kdtc = tk.BooleanVar(value=False)
        self.v_xcp = tk.BooleanVar(value=False)
        self.v_odx = tk.BooleanVar(value=True)
        self.v_out = tk.StringVar(value=str(DEFAULT_OUT))
        self.v_status = tk.StringVar(value="Hazır.")
        self.v_summary = tk.StringVar(value="")
        self.v_prog = tk.DoubleVar(value=0.0)

    # ---------- görünüm ----------
    def _ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        head = ttk.Frame(self)
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(1, weight=1)
        self._logo = None
        logo_png = ASSET_DIR / "logo.png"
        if logo_png.is_file():
            try:
                self._logo = tk.PhotoImage(file=str(logo_png))
                ttk.Label(head, image=self._logo).grid(row=0, column=0, rowspan=3, sticky="w", padx=(0, 10))
            except tk.TclError:
                self._logo = None
        ttk.Label(head, text=APP_TITLE, font=("Segoe UI", 13, "bold"), foreground="#3f5c3f").grid(
            row=0, column=1, sticky="w")
        ttk.Label(head, text=APP_SUBTITLE, foreground="#6b6b6b").grid(row=1, column=1, sticky="w")
        tool_txt = (f"motor: {self.tool.name} · kaynak: Schutz-Kaput (PerkTheFox)"
                    if self.tool else "motor: BULUNAMADI — ks_patcher.py gerekli")
        ttk.Label(head, text=tool_txt, foreground="#1f8f3d" if self.tool else "#b3261e").grid(
            row=2, column=1, sticky="w", pady=(2, 0))
        ttk.Button(head, text="Hakkında / Kaynak", command=self._about).grid(
            row=0, column=2, rowspan=3, sticky="e")

        # --- girdi ---
        src = ttk.LabelFrame(self, text=" 1 · Girdi (ham firmware) ", padding=8)
        src.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        src.columnconfigure(3, weight=1)
        ttk.Button(src, text="Dosya ekle…", command=self._add_files).grid(row=0, column=0)
        ttk.Button(src, text="Klasör ekle…", command=self._add_folder).grid(row=0, column=1, padx=6)
        ttk.Button(src, text="Listeyi temizle", command=self._clear).grid(row=0, column=2)
        ttk.Checkbutton(src, text="Tümünü seç", command=self._toggle_all).grid(row=0, column=3, sticky="w", padx=(16, 0))
        self.lbl_count = ttk.Label(src, text="0 dosya", foreground="#6b6b6b")
        self.lbl_count.grid(row=0, column=4, sticky="e")

        # --- liste + seçenekler ---
        mid = ttk.Frame(self)
        mid.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        mid.columnconfigure(0, weight=1)
        mid.rowconfigure(0, weight=1)

        cols = ("tick", "file", "ver", "part", "size", "status", "note")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", height=9, selectmode="browse")
        widths = {"tick": 34, "file": 250, "ver": 54, "part": 96, "size": 82, "status": 108, "note": 330}
        titles = {"tick": "✓", "file": "Dosya", "ver": "Sürüm", "part": "Parça",
                  "size": "Boyut", "status": "Durum", "note": "Not / doğrulama"}
        for c in cols:
            self.tree.heading(c, text=titles[c])
            self.tree.column(c, width=widths[c], anchor="w" if c in ("file", "note") else "center",
                             stretch=c in ("file", "note"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.tag_configure("ok", foreground="#1f8f3d")
        self.tree.tag_configure("err", foreground="#b3261e")
        self.tree.tag_configure("run", foreground="#1f5f8f")
        self.tree.tag_configure("off", foreground="#8b949e")

        opt = ttk.LabelFrame(self, text=" 2 · Ne uygulanacak? ", padding=8)
        opt.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        opt.columnconfigure(3, weight=1)
        ttk.Checkbutton(opt, text="CP pasif (bileşen koruması)", variable=self.v_cp).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(opt, text="FeC (9 kodun tamamı)", variable=self.v_fec).grid(row=0, column=1, sticky="w", padx=(18, 0))
        ttk.Checkbutton(opt, text="Virgin key DTC bastır (D10000/D20000/D30000)",
                        variable=self.v_kdtc, command=self._sync_out).grid(row=0, column=2, sticky="w", padx=(18, 0))
        ttk.Checkbutton(opt, text="XCP/CAN0 (mühendislik)", variable=self.v_xcp).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(opt, text="Çıktı: ODIS-E paketi (PART1+PART2)", variable=self.v_odx).grid(
            row=1, column=1, columnspan=2, sticky="w", padx=(18, 0), pady=(6, 0))

        outf = ttk.Frame(opt)
        outf.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        outf.columnconfigure(1, weight=1)
        ttk.Label(outf, text="Çıktı klasörü").grid(row=0, column=0, sticky="w")
        ttk.Entry(outf, textvariable=self.v_out).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(outf, text="Seç", width=6, command=self._pick_out).grid(row=0, column=2)
        ttk.Button(outf, text="Aç", width=6, command=self._open_out).grid(row=0, column=3, padx=(4, 0))

        # --- aksiyon ---
        act = ttk.Frame(self)
        act.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        act.columnconfigure(3, weight=1)
        self.btn_start = ttk.Button(act, text="▶ Derle", command=self._start)
        self.btn_start.grid(row=0, column=0)
        self.btn_stop = ttk.Button(act, text="Durdur", command=self._stop, state="disabled")
        self.btn_stop.grid(row=0, column=1, padx=6)
        ttk.Button(act, text="Raporu aç", command=self._open_report).grid(row=0, column=2)
        ttk.Label(act, textvariable=self.v_summary, foreground="#1f5f8f").grid(row=0, column=3, sticky="w", padx=(12, 0))
        ttk.Progressbar(act, variable=self.v_prog, maximum=100, length=180).grid(row=0, column=4, sticky="e")

        logf = ttk.LabelFrame(self, text=" Günlük ", padding=4)
        logf.grid(row=5, column=0, sticky="nsew", pady=(6, 0))
        self.rowconfigure(5, weight=1)
        logf.columnconfigure(0, weight=1)
        logf.rowconfigure(0, weight=1)
        self.log = tk.Text(logf, height=9, wrap="none", font=("Consolas", 9),
                           background="#101418", foreground="#d6dde6", insertbackground="#d6dde6")
        self.log.grid(row=0, column=0, sticky="nsew")
        sb2 = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        sb2.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=sb2.set, state="disabled")
        for tag, color in (("err", "#ff6b6b"), ("warn", "#ffc857"), ("ok", "#7ee787"),
                           ("cmd", "#79c0ff"), ("dim", "#8b949e"), ("head", "#c9a0ff")):
            self.log.tag_configure(tag, foreground=color)

        ttk.Label(self, textvariable=self.v_status, foreground="#6b6b6b").grid(
            row=6, column=0, sticky="w", pady=(4, 0))

    def _apply_cfg(self) -> None:
        c = self.cfg
        self.v_cp.set(bool(c.get("cp", True)))
        self.v_fec.set(bool(c.get("fec", True)))
        self.v_kdtc.set(bool(c.get("kdtc", False)))
        self.v_xcp.set(bool(c.get("xcp", False)))
        self.v_odx.set(bool(c.get("odx", True)))
        self.v_out.set(c.get("out") or str(DEFAULT_OUT_KDT if self.v_kdtc.get() else DEFAULT_OUT))
        geo = c.get("geometry")
        if geo:
            try:
                self.master.geometry(geo)
            except tk.TclError:
                pass
        if not self.tool:
            self._log("✘ ks_patcher.py bulunamadı — derleme yapılamaz.", "err")

    # ---------- günlük ----------
    def _log(self, text: str, tag: str | None = None) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", tag or ())
        self.log.see("end")
        self.log.configure(state="disabled")

    # ---------- hakkında ----------
    def _about(self) -> None:
        messagebox.showinfo(
            "Hakkında / Kaynak",
            f"{APP_TITLE}\n"
            f"sürüm {APP_VERSION} — Denizli Garaj\n\n"
            "Ne yapar: ham VAG firmware dosyalarını (FRF/ODX/dump) alır, seçtiğin yamaları\n"
            "(CP pasif · FeC · virgin key DTC bastırma) uygular ve ODIS-E ile yazılabilir\n"
            "PART1 + PART2 paketlerini üretir. Her dosya ayrıca doğrulanır.\n\n"
            f"Kullanılan kaynak / yama motoru:\n{SOURCE_PROJECT}\n"
            "Bu program o projenin kodunu içermez; ks_patcher.py'yi harici olarak çağırır.\n\n"
            "Bu program hiçbir firmware veya OEM kodu içermez. Tüm firmware dosyaları\n"
            "kullanıcının kendi diskindedir.\n\n"
            "Lisans: non-commercial / Right-to-Repair — satış ve ücretli hizmet yasak.\n"
            "Uyarı: hatalı sürüm/blok = tuğla; OBD'den kurtarma yok. Önce tam yedek al,\n"
            "sonrasında optik kalibrasyon (VAS 6430) ve araç tarafı kodlama şart.",
        )

    # ---------- liste yönetimi ----------
    def _add_paths(self, paths: list[Path]) -> None:
        added = 0
        for p in paths:
            key = str(p.resolve())
            if key in self.items or not p.is_file():
                continue
            if p.suffix.lower() not in INPUT_SUFFIXES:
                continue
            label, part = label_from_name(p.name)
            iid = self.tree.insert("", "end", values=("☑", p.name, label, part,
                                                      f"{p.stat().st_size:,} B", "bekliyor", ""))
            self.items[iid] = {"path": p, "label": label, "part": part, "ticked": True,
                               "status": "bekliyor", "note": ""}
            added += 1
        self._refresh_count()
        if added:
            self._log(f"{added} dosya eklendi.", "dim")

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Ham firmware seç",
            filetypes=[("VAG firmware", "*.frf *.odx-f *.odx *.pdx"), ("Dump", "*.bin"), ("Tümü", "*.*")])
        if paths:
            self._add_paths([Path(p) for p in paths])

    def _add_folder(self) -> None:
        d = filedialog.askdirectory(title="Firmware klasörü seç", initialdir=str(Path.home() / "Desktop"))
        if not d:
            return
        root = Path(d)
        files = [p for p in sorted(root.iterdir()) if p.is_file() and p.suffix.lower() in INPUT_SUFFIXES]
        if not files:
            messagebox.showinfo(APP_TITLE, "Bu klasörde .frf/.odx-f/.pdx/.bin dosyası yok.")
            return
        self._add_paths(files)

    def _clear(self) -> None:
        if self.running:
            return
        for iid in list(self.items):
            self.tree.delete(iid)
        self.items.clear()
        self._refresh_count()
        self.v_summary.set("")

    def _toggle_all(self) -> None:
        if self.running:
            return
        want = any(not it["ticked"] for it in self.items.values())
        for iid, it in self.items.items():
            it["ticked"] = want
            if it["status"] in ("bekliyor", "kapalı"):
                it["status"] = "bekliyor" if want else "kapalı"
            self._paint(iid)
        self._refresh_count()

    def _on_click(self, event) -> None:
        if self.running:
            return
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":
            return
        iid = self.tree.identify_row(event.y)
        if iid not in self.items:
            return
        it = self.items[iid]
        it["ticked"] = not it["ticked"]
        if it["status"] in ("bekliyor", "kapalı"):
            it["status"] = "bekliyor" if it["ticked"] else "kapalı"
        self._paint(iid)
        self._refresh_count()

    def _paint(self, iid: str) -> None:
        it = self.items[iid]
        p: Path = it["path"]
        tags = ()
        if not it["ticked"]:
            tags = ("off",)
        elif it["status"] == "TAMAM":
            tags = ("ok",)
        elif it["status"] in ("HATA", "ATLANDI"):
            tags = ("err",)
        elif it["status"] == "çalışıyor…":
            tags = ("run",)
        self.tree.item(iid, values=("☑" if it["ticked"] else "☐", p.name, it["label"], it["part"],
                                    f"{p.stat().st_size:,} B", it["status"], it["note"]), tags=tags)

    def _refresh_count(self) -> None:
        total = len(self.items)
        ticked = sum(1 for it in self.items.values() if it["ticked"])
        self.lbl_count.configure(text=f"{ticked}/{total} dosya seçili")

    def _sync_out(self) -> None:
        cur = Path(self.v_out.get())
        if cur in (DEFAULT_OUT, DEFAULT_OUT_KDT):
            self.v_out.set(str(DEFAULT_OUT_KDT if self.v_kdtc.get() else DEFAULT_OUT))

    def _pick_out(self) -> None:
        d = filedialog.askdirectory(title="Çıktı klasörü")
        if d:
            self.v_out.set(d)

    def _open_out(self) -> None:
        d = Path(self.v_out.get())
        if d.is_dir():
            try:
                os.startfile(str(d)) if os.name == "nt" else subprocess.Popen(["xdg-open", str(d)])
            except OSError as exc:
                messagebox.showerror(APP_TITLE, f"Açılamadı: {exc}")
        else:
            messagebox.showinfo(APP_TITLE, "Çıktı klasörü henüz yok.")

    def _open_report(self) -> None:
        d = Path(self.v_out.get()) / "OZET.txt"
        if d.is_file():
            try:
                os.startfile(str(d)) if os.name == "nt" else subprocess.Popen(["xdg-open", str(d)])
            except OSError as exc:
                messagebox.showerror(APP_TITLE, f"Açılamadı: {exc}")
        else:
            messagebox.showinfo(APP_TITLE, "Henüz rapor yok — önce derle.")

    # ---------- derleme ----------
    def _start(self) -> None:
        if self.running:
            return
        if not self.tool:
            messagebox.showerror(APP_TITLE, "ks_patcher.py bulunamadı (Schutz-Kaput).")
            return
        targets = [iid for iid, it in self.items.items() if it["ticked"]]
        if not targets:
            messagebox.showerror(APP_TITLE, "Derlenecek dosya seçili değil.")
            return
        if not (self.v_cp.get() or self.v_fec.get() or self.v_kdtc.get() or self.v_xcp.get()):
            messagebox.showerror(APP_TITLE, "En az bir yama seç.")
            return
        out = Path(self.v_out.get())
        try:
            out.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Çıktı klasörü: {exc}")
            return

        self.running = True
        self.cancel.clear()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.v_prog.set(0)
        self.t0 = time.time()
        self.v_status.set(f"Derleniyor… ({len(targets)} dosya)")
        self._log("", "dim")
        self._log(f"══ derleme başladı · {len(targets)} dosya → {out} ══", "head")
        self._log(f"seçenekler: CP={int(self.v_cp.get())} FeC={int(self.v_fec.get())} "
                  f"KDT={int(self.v_kdtc.get())} XCP={int(self.v_xcp.get())} "
                  f"ODX paket={int(self.v_odx.get())}", "dim")
        opts = dict(cp=self.v_cp.get(), fec=self.v_fec.get(), kdtc=self.v_kdtc.get(),
                    xcp=self.v_xcp.get(), odx=self.v_odx.get(), out=out)
        self.worker = threading.Thread(target=self._work, args=(targets, opts), daemon=True)
        self.worker.start()
        self.after(150, self._drain)

    def _stop(self) -> None:
        if self.running:
            self.cancel.set()
            self._log("durdurma isteği — mevcut dosya bitince duracak", "warn")
            self.v_status.set("Durduruluyor…")

    def _work(self, targets: list[str], opts: dict) -> None:
        """Arka plan: sırayla her dosyayı işle."""
        results = []
        for n, iid in enumerate(targets, 1):
            if self.cancel.is_set():
                self.q.put(("row", iid, {"status": "ATLANDI", "note": "durduruldu"}))
                continue
            it = self.items[iid]
            src: Path = it["path"]
            label, part = it["label"], it["part"]
            tag = f"{label}_{part}" if label != "?" else src.stem
            dest = Path(opts["out"]) / tag
            self.q.put(("row", iid, {"status": "çalışıyor…", "note": "okunuyor"}))
            self.q.put(("log", f"[{n}/{len(targets)}] {src.name}", "head"))

            try:
                if dest.exists():
                    shutil.rmtree(dest)
                # 1) ön kontrol (stok durum + format)
                r = run_tool(self.tool, ["-l", "en", "-t", TARGET_ID, "inspect", str(src), "--json"])
                info = parse_json(r.stdout)
                if info is None:
                    msg = (r.stdout + r.stderr).strip().splitlines()
                    reason = msg[-1][:160] if msg else "okunamadı"
                    self.q.put(("row", iid, {"status": "HATA", "note": reason}))
                    self.q.put(("log", f"  ✘ okunamadı: {reason}", "err"))
                    results.append((tag, "HATA", reason))
                    self.q.put(("prog", 100 * n / len(targets)))
                    continue
                stock_crc = f"0x{info['crc32_trimmed']:08X}"
                self.q.put(("log", f"  okundu: SW {label} · stok CP={info['ks_state']} "
                                   f"FeC={info['fec_state']} · DB_01 CRC {stock_crc}", "dim"))

                # bu firmware'de imzası olmayan gruplar varsa o seçeneği bu dosya için atla
                fo = dict(opts)
                for opt_key, state_key, name in (("kdtc", "key_dtc_state", "Key DTC"),
                                                 ("xcp", "xcp_state", "XCP")):
                    if fo[opt_key] and info.get(state_key) not in ("stock", "patched"):
                        fo[opt_key] = False
                        self.q.put(("log", f"  ⚠ {name}: bu sürümde yama imzası yok → atlandı", "warn"))

                # 2) yamala
                self.q.put(("row", iid, {"status": "çalışıyor…", "note": "yamalanıyor"}))
                cmd = build_patch_cmd(self.tool, src, cp=fo["cp"], fec=fo["fec"],
                                      kdtc=fo["kdtc"], xcp=fo["xcp"], odx=fo["odx"],
                                      out_dir=dest)
                self.q.put(("log", "  $ " + " ".join(cmd[1:]), "cmd"))
                r = run_tool(self.tool, cmd[2:])
                if r.returncode != 0:
                    tail = (r.stdout + r.stderr).strip().splitlines()
                    reason = " | ".join(tail[-3:])[:200]
                    self.q.put(("row", iid, {"status": "HATA", "note": reason}))
                    self.q.put(("log", f"  ✘ yama başarısız: {reason}", "err"))
                    results.append((tag, "HATA", reason))
                    self.q.put(("prog", 100 * n / len(targets)))
                    continue

                # 3) doğrula
                self.q.put(("row", iid, {"status": "çalışıyor…", "note": "doğrulanıyor"}))
                ok, note, det = self._verify(dest, fo, src.name)
                if ok:
                    self.q.put(("row", iid, {"status": "TAMAM", "note": note}))
                    self.q.put(("log", f"  ✔ {note}", "ok"))
                    results.append((tag, "TAMAM", note))
                else:
                    self.q.put(("row", iid, {"status": "HATA", "note": note}))
                    self.q.put(("log", f"  ✘ {note}", "err"))
                    results.append((tag, "HATA", note))
            except Exception as exc:  # noqa: BLE001
                self.q.put(("row", iid, {"status": "HATA", "note": str(exc)[:160]}))
                self.q.put(("log", f"  ✘ {exc}", "err"))
                results.append((tag, "HATA", str(exc)[:160]))
            self.q.put(("prog", 100 * n / len(targets)))

        self.q.put(("done", results))

    def _verify(self, dest: Path, opts: dict, src_name: str = "") -> tuple[bool, str, dict]:
        if not opts["odx"]:
            bins = list(dest.glob("*.bin"))
            return (bool(bins), f"{len(bins)} .bin üretildi" if bins else "çıktı yok", {})
        p1 = sorted((dest / "PART1").glob("*.odx*")) if (dest / "PART1").is_dir() else []
        p2 = sorted((dest / "PART2").glob("*.odx*")) if (dest / "PART2").is_dir() else []
        if not p1 or not p2:
            return False, f"çıktı eksik (PART1={len(p1)}, PART2={len(p2)})", {}
        notes = []
        # konteynerden durum oku
        r = run_tool(self.tool, ["-l", "en", "-t", TARGET_ID, "inspect", str(p1[0]), "--json"])
        info = parse_json(r.stdout)
        if info is None:
            return False, "yamalı konteyner okunamadı", {}
        states = {"ks_state": info["ks_state"], "fec_state": info["fec_state"],
                  "key_dtc_state": info["key_dtc_state"], "xcp_state": info["xcp_state"]}
        # İstenen gruplar "patched" olmalı. İstenmeyen gruplarda "stock" VEYA "unknown"
        # (imza o firmware'de yok, ör. SW 1202'de Xcp_BootControl yok) kabul edilir.
        for key, requested in (("ks_state", True), ("fec_state", opts["fec"]),
                               ("key_dtc_state", opts["kdtc"]), ("xcp_state", opts["xcp"])):
            got = states[key]
            if requested:
                if got != "patched":
                    return False, f"{key}: yamalanamadı (bulunan: {got})", states
            elif got not in ("stock", "unknown"):
                return False, f"{key}: beklenmedik durum '{got}'", states
        notes.append("CP=patched")
        if opts["fec"]:
            notes.append("FeC=9/9")
        if opts["kdtc"]:
            notes.append("KDT=bastırıldı")
        if stages_missing := [k for k, v in states.items() if v == "unknown"]:
            notes.append("imza yok: " + ", ".join(s.replace("_state", "") for s in stages_missing))
        # BF_01 header + CRC adı
        bf = sorted((dest / "PART1").glob("BF_*_01_*.bin"))
        if bf:
            data = bf[0].read_bytes()
            if data[:8] != DB01_HEADER:
                return False, "cold-boot başlığı bozuk", states
            m = re.search(r"_01_0000_([0-9A-Fa-f]{8})\.bin$", bf[0].name)
            crc = zlib.crc32(data) & 0xFFFFFFFF
            if m and int(m.group(1), 16) != crc:
                return False, "BF_01 CRC adı uyuşmuyor", states
            notes.append(f"BF_01 CRC 0x{crc:08X}")
        # harici referanslar
        xml = p1[0].read_text(encoding="utf-8", errors="replace")
        for ref in {x.strip() for x in re.findall(r"<DATAFILE[^>]*>([^<]+)</DATAFILE>", xml) if x.strip()}:
            if not (dest / "PART1" / ref).is_file():
                return False, f"eksik harici dosya {ref}", states
        # RAPOR.txt
        (dest / "RAPOR.txt").write_text(
            f"{dest.name} — yamalı ODIS-E paketi\n"
            f"kaynak dosya: {src_name or '—'}\n"
            f"uygulanan   : {' + '.join(notes)}\n"
            f"durumlar    : " + ", ".join(f"{k}={v}" for k, v in states.items()) + "\n\n"
            "FLASH (ODIS-E 17/18 + VAS 6154A):\n"
            "  1) PART1 içindeki .odx-f → sonda imza hatası BEKLENİR, kontağı KAPATMA\n"
            "  2) hemen PART2 içindekini flash et → %100 yeşil\n\n"
            "BF_*.bin dosyalarını .odx-f'den ayırma. Sonrasında optik kalibrasyon (VAS 6430).\n",
            encoding="utf-8")
        return True, " · ".join(notes), states

    # ---------- kuyruk ----------
    def _drain(self) -> None:
        try:
            while True:
                kind, a, b = (None, None, None)
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "row":
                    iid, upd = msg[1], msg[2]
                    it = self.items.get(iid)
                    if it:
                        it.update(upd)
                        self._paint(iid)
                elif kind == "log":
                    self._log(msg[1], msg[2] if len(msg) > 2 else None)
                elif kind == "prog":
                    self.v_prog.set(msg[1])
                elif kind == "done":
                    self._finish(msg[1])
        except queue.Empty:
            pass
        if self.running:
            self.after(150, self._drain)

    def _finish(self, results: list[tuple[str, str, str]]) -> None:
        self.running = False
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.v_prog.set(100)
        ok = [r for r in results if r[1] == "TAMAM"]
        bad = [r for r in results if r[1] != "TAMAM"]
        secs = time.time() - self.t0
        self._log("", "dim")
        self._log(f"{'✔' if not bad else '⚠'} bitti: {len(ok)}/{len(results)} TAMAM · {secs:.0f}s",
                  "ok" if not bad else "warn")
        for tag, st, note in bad:
            self._log(f"  ✘ {tag}: {note}", "err")
        self.v_summary.set(f"{len(ok)}/{len(results)} TAMAM · {secs:.0f}s")
        self.v_status.set(f"Bitti · {len(ok)}/{len(results)} başarılı → {self.v_out.get()}")

        # OZET.txt
        out = Path(self.v_out.get())
        lines = [f"{APP_TITLE} v{APP_VERSION} · {time.strftime('%Y-%m-%d %H:%M')}",
                 f"seçenekler: CP={int(self.v_cp.get())} FeC={int(self.v_fec.get())} "
                 f"KDT={int(self.v_kdtc.get())} XCP={int(self.v_xcp.get())} ODX={int(self.v_odx.get())}",
                 "", f"{'PAKET':<22}{'DURUM':<10}NOT", "-" * 92]
        for tag, st, note in results:
            lines.append(f"{tag:<22}{st:<10}{note}")
        lines += ["", f"başarılı: {len(ok)}/{len(results)} · süre {secs:.0f}s"]
        try:
            (out / "OZET.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass
        self._save_cfg()

    def on_close(self) -> None:
        if self.running and not messagebox.askyesno(APP_TITLE, "Derleme sürüyor. Kapatılsın mı?"):
            return
        self.cancel.set()
        self._save_cfg()
        self.master.destroy()


def main() -> int:
    root = tk.Tk()
    root.title(f"{APP_SHORT}  v{APP_VERSION}")
    # pencere / görev çubuğu simgesi
    try:
        png = ASSET_DIR / "logo.png"
        if png.is_file():
            icon = tk.PhotoImage(file=str(png))
            root.iconphoto(True, icon)
            root._icon_ref = icon  # GC'ye kapılmasın
    except tk.TclError:
        pass
    if os.name == "nt":
        try:
            ico = ASSET_DIR / "logo.ico"
            if ico.is_file():
                root.iconbitmap(default=str(ico))
        except tk.TclError:
            pass
    style = ttk.Style()
    if os.name == "nt":
        for theme in ("vista", "xpnative", "winnative"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
    tool = resolve_tool()
    app = Builder(root, tool)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.minsize(960, 640)
    if "geometry" not in app.cfg:
        w, h = 1120, 760
        x = max(0, (root.winfo_screenwidth() - w) // 2)
        y = max(0, (root.winfo_screenheight() - h) // 2)
        root.geometry(f"{w}x{h}+{x}+{y}")
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
