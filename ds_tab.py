# -*- coding: utf-8 -*-
"""2Q0 kamera VERİ SETİ (dataset) sekmesi — Tkinter arayüzü.

Saf mantık `dataset_2q0.py` içinde; bu dosya yalnız arayüz ve akış.
Program internete bağlanmaz: dosya kullanıcıdan gelir (ODX-F / .xml / 64 KB .bin).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import dataset_2q0 as dsx

BANNER = (
    "⚠ Veri setini değiştirdikten sonra kameraya YAZILIM (firmware) güncellemesi yapma — "
    "ünite kalıcı olarak kilitlenir (tuğla).\n"
    "İleride yazılım güncellemesi gerekiyorsa önce mevcut yazılımına uygun STOK veri seti yükle."
)

EXPECTED = 0x10000


class DatasetTab(ttk.Frame):
    """Veri seti düzenleyici sekmesi."""

    def __init__(self, master, *, out_dir: str = "", log=None):
        super().__init__(master, padding=8)
        self.log = log or (lambda *a, **k: None)
        self.ds: dsx.Dataset | None = None
        self.original: bytes | None = None
        self.path_var = tk.StringVar()
        self.out_var = tk.StringVar(value=out_dir)
        self.info_var = tk.StringVar(value="Veri seti yüklenmedi.")
        self.status_var = tk.StringVar(value="")
        self.entries: dict[str, tk.StringVar] = {}
        self.adv_entries: dict[str, tk.StringVar] = {}
        self._ui()

    # ------------------------------------------------------------------ UI
    def _ui(self) -> None:
        self.columnconfigure(0, weight=1)

        top = ttk.LabelFrame(self, text=" 1 · Veri seti dosyası ", padding=8)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(2, weight=1)
        ttk.Button(top, text="Dosya seç…", command=self._pick).grid(row=0, column=0)
        ttk.Button(top, text="Otomatik tara", command=self._scan).grid(row=0, column=1, padx=6)
        ttk.Entry(top, textvariable=self.path_var).grid(row=0, column=2, sticky="ew")
        ttk.Button(top, text="Yükle", command=self._load_from_entry).grid(row=0, column=3, padx=(6, 0))
        ttk.Label(top, textvariable=self.info_var, foreground="#1f5f8f").grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))

        par = ttk.LabelFrame(self, text=" 2 · Parametreler (değiştirmek istediklerini düzenle) ", padding=8)
        par.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        for col in range(4):
            par.columnconfigure(col, weight=1 if col in (1, 3) else 0)

        for i, f in enumerate(dsx.FIELDS):
            r, c = divmod(i, 2)
            var = tk.StringVar()
            self.entries[f.key] = var
            ttk.Label(par, text=f"{f.label}").grid(row=r, column=c * 2, sticky="w", padx=(0, 6), pady=2)
            cell = ttk.Frame(par)
            cell.grid(row=r, column=c * 2 + 1, sticky="ew", padx=(0, 18), pady=2)
            ent = ttk.Entry(cell, textvariable=var, width=10, justify="right")
            ent.pack(side="left")
            ttk.Label(cell, text=f.unit, foreground="#6b6b6b").pack(side="left", padx=(4, 0))
            lo = "—" if f.minimum is None else f"{f.minimum:g}"
            hi = "—" if f.maximum is None else f"{f.maximum:g}"
            self._tip(ent, f"{f.label}\nAdres: 0x{f.offset:04X} · float32 · izin: {lo} … {hi} {f.unit}")

        adv = ttk.LabelFrame(self, text=" Gelişmiş (float32 — yalnız ne yaptığını biliyorsan) ", padding=6)
        adv.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        for i, f in enumerate(dsx.ADVANCED_FIELDS):
            var = tk.StringVar()
            self.adv_entries[f.key] = var
            ttk.Label(adv, text=f"{f.label}").grid(row=i // 2, column=(i % 2) * 2, sticky="w", padx=(0, 6), pady=2)
            ent = ttk.Entry(adv, textvariable=var, width=12, justify="right")
            ent.grid(row=i // 2, column=(i % 2) * 2 + 1, sticky="w", padx=(0, 18))
            self._tip(ent, f"0x{f.offset:04X} · float32 (ham değer, ölçek yok)")

        act = ttk.Frame(self)
        act.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        act.columnconfigure(5, weight=1)
        ttk.Button(act, text="💾 Kaydet (yeni dosya)", command=self._save).grid(row=0, column=0)
        ttk.Button(act, text="Ham .bin yaz", command=self._save_bin).grid(row=0, column=1, padx=6)
        ttk.Button(act, text="Değişiklikleri geri al", command=self._reload).grid(row=0, column=2)
        ttk.Button(act, text="Çıktı klasörü…", command=self._pick_out).grid(row=0, column=3, padx=6)
        ttk.Button(act, text="Klasörü aç", command=self._open_out).grid(row=0, column=4)
        ttk.Label(act, textvariable=self.status_var, foreground="#1f8f3d").grid(
            row=0, column=5, sticky="w", padx=(12, 0))

        note = tk.Text(self, height=4, wrap="word", relief="flat", background="#fff7e6",
                       foreground="#8a5300", font=("Segoe UI", 9))
        note.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        note.insert("1.0", BANNER + "\n"
                    "Veri seti 64 KB (0x10000) bloktur: DB_7100FLASHDATA. Kaydederken imza (0x030C) "
                    "ve CRC-32 (0xFFF8) yeniden hesaplanır; ODX çıktısı sıkıştırmasız (00) yazılır.")
        note.configure(state="disabled")

    @staticmethod
    def _tip(widget: tk.Widget, text: str) -> None:
        tip = tk.Toplevel(widget)
        tip.wm_overrideredirect(True)
        tip.withdraw()
        lbl = tk.Label(tip, text=text, background="#2b2b2b", foreground="#eaeaea",
                       relief="solid", borderwidth=1, font=("Segoe UI", 9), justify="left", padx=6, pady=4)
        lbl.pack()

        def enter(_e=None):
            tip.deiconify()
            x = widget.winfo_rootx() + 12
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            tip.wm_geometry(f"+{x}+{y}")

        def leave(_e=None):
            tip.withdraw()

        widget.bind("<Enter>", enter, add="+")
        widget.bind("<Leave>", leave, add="+")
        widget._tip = tip  # type: ignore[attr-defined]

    # --------------------------------------------------------------- akış
    def _pick(self) -> None:
        path = filedialog.askopenfilename(
            title="2Q0 veri seti seç",
            filetypes=[("Veri seti / arşiv", "*.odx-f *.odx *.xml *.bin *.zip *.7z *.rar *.tar *.gz"),
                       ("ODX-F / XML", "*.odx-f *.odx *.xml"),
                       ("64 KB veri seti", "*.bin"),
                       ("Arşiv (zip / 7z / rar)", "*.zip *.7z *.rar *.tar *.gz"),
                       ("Tümü", "*.*")])
        if path:
            self.path_var.set(path)
            self._load(Path(path))

    def _load_from_entry(self) -> None:
        p = Path(self.path_var.get().strip())
        if not p.is_file():
            messagebox.showwarning("Veri seti", "Dosya bulunamadı.")
            return
        self._load(p)

    def _scan(self) -> None:
        hits: list[Path] = []
        for root in (Path.home() / "Desktop", Path.home() / "Downloads", Path.home() / "Documents"):
            if not root.is_dir():
                continue
            for pat in ("*dataset*.odx-f", "*Dataset*.odx-f", "*DB_7100*", "*2Q0*.odx-f", "*2Q0*.xml",
                        "*2Q0*.zip", "*2Q0*.7z", "*2Q0*.rar", "*dataset*.zip", "*Dataset*.zip", "*dataset*.7z"):
                hits.extend(sorted(root.glob(pat))[:6])
            for f in sorted(root.glob("*.bin")):
                try:
                    if f.stat().st_size == EXPECTED:
                        hits.append(f)
                except OSError:
                    pass
        seen, uniq = set(), []
        for h in hits:
            if h not in seen:
                seen.add(h)
                uniq.append(h)
        if not uniq:
            messagebox.showinfo(
                "Otomatik tarama",
                "Masaüstü/İndirilenler/Belgeler içinde 2Q0 veri seti bulunamadı.\n"
                "Dosya adı veya 65536 bayt boyut aranıyor.")
            return
        self.path_var.set(str(uniq[0]))
        self._load(uniq[0])
        self.log(f"Veri seti bulundu: {uniq[0]}", "ok")

    def _load(self, path: Path) -> None:
        try:
            ds = dsx.load(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Veri seti açılamadı", str(exc))
            self.log(f"Veri seti hatası: {exc}", "err")
            return
        self.ds = ds
        self.original = ds.raw
        for f in dsx.ALL_FIELDS:
            shown = f.show(dsx.f32(ds.raw, f.offset))
            var = self.entries.get(f.key) or self.adv_entries.get(f.key)
            if var is not None:
                var.set(f"{shown:.{f.digits}f}" if f.digits else f"{shown:g}")
        s = dsx.summary(ds)
        extra = f" · ARŞİV {s['arşiv']} → {s['arşiv_dosya']}" if ds.archive else ""
        self.info_var.set(
            f"{s['tür']} · {s['boyut']:,} bayt · blok {s['blok']} · sıkıştırma {s['sıkıştırma']} · "
            f"CRC {s['crc']} ({s['crc_durum']}) · imza {s['imza']} · etiket {s['proje_etiketi']}{extra}")
        for w in ds.warnings:
            self.log(f"Veri seti uyarısı: {w}", "warn")
        self.status_var.set("")
        self.log(f"Veri seti yüklendi: {path.name} · {s['boyut']:,} bayt · CRC {s['crc_durum']}", "ok")
        if not ds.size_ok:
            messagebox.showwarning(
                "Boyut uyuşmuyor",
                f"Beklenen 65536 bayt, bulunan {len(ds.raw)} bayt.\n"
                "Bu dosya bir 2Q0 kamera veri seti olmayabilir; yine de düzenleyebilirsin ama yazma!")

    def _collect(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for f in dsx.ALL_FIELDS:
            var = self.entries.get(f.key) or self.adv_entries.get(f.key)
            if var is None:
                continue
            txt = var.get().strip().replace(",", ".")
            if not txt:
                continue
            try:
                val = float(txt)
            except ValueError:
                raise ValueError(f"{f.label}: sayı değil — '{txt}'")
            if f.minimum is not None and val < f.minimum:
                raise ValueError(f"{f.label}: {val:g} çok küçük (en az {f.minimum:g} {f.unit})")
            if f.maximum is not None and val > f.maximum:
                raise ValueError(f"{f.label}: {val:g} çok büyük (en fazla {f.maximum:g} {f.unit})")
            out[f.key] = val
        return out

    def _save(self) -> None:
        if self.ds is None:
            messagebox.showwarning("Veri seti", "Önce bir veri seti yükle.")
            return
        try:
            vals = self._collect()
            new_raw, diff = dsx.apply_values(self.ds, vals)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Kaydedilemedi", str(exc))
            return
        if not diff:
            self.status_var.set("Değişiklik yok.")
            return
        if self.ds.archive is not None:
            base = self.ds.archive.stem
            suffix = ".zip"
        else:
            base = self.ds.source.stem if self.ds.source else "dataset"
            suffix = self.ds.source.suffix if self.ds.source else ".bin"
        out_dir = Path(self.out_var.get().strip()
                       or (self.ds.archive.parent if self.ds.archive
                           else (Path(self.ds.source).parent if self.ds.source else Path.cwd())))
        out = out_dir / f"{base}_duzenlenmis{suffix}"
        try:
            saved = dsx.save(self.ds, out, new_raw)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Yazılamadı", str(exc))
            return
        self.status_var.set(f"✔ {len(diff)} bayt değişti → {saved.name}")
        self.log(f"Veri seti yazıldı: {saved} · {len(diff)} bayt fark · CRC "
                 f"0x{dsx.stored_crc(new_raw):08X} (doğrulandı)", "ok")
        messagebox.showinfo(
            "Veri seti kaydedildi",
            f"{saved}\n\n"
            f"Değişen bayt: {len(diff)}\n"
            f"Yeni CRC-32: 0x{dsx.stored_crc(new_raw):08X} (doğru)\n"
            f"Yeni imza: {dsx.stored_signature(new_raw).hex().upper()}\n\n"
            "Bu dosyayı ODIS-E / VCP ile kameraya yazabilirsin.")

    def _save_bin(self) -> None:
        if self.ds is None:
            messagebox.showwarning("Veri seti", "Önce bir veri seti yükle.")
            return
        try:
            vals = self._collect()
            new_raw, diff = dsx.apply_values(self.ds, vals)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Kaydedilemedi", str(exc))
            return
        out_dir = Path(self.out_var.get().strip() or (Path.home() / "Desktop"))
        base = self.ds.source.stem if self.ds.source else "dataset"
        out = out_dir / f"{base}_duzenlenmis.bin"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(new_raw)
        self.status_var.set(f"✔ ham .bin yazıldı ({len(diff)} bayt fark)")
        self.log(f"Ham veri seti yazıldı: {out}", "ok")

    def _reload(self) -> None:
        if self.ds and self.ds.source:
            self._load(self.ds.source)

    def _pick_out(self) -> None:
        d = filedialog.askdirectory(title="Veri seti çıktı klasörü")
        if d:
            self.out_var.set(d)

    def _open_out(self) -> None:
        target = self.out_var.get().strip()
        if not target:
            return
        p = Path(target)
        p.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(str(p))  # noqa: S606
        else:
            subprocess.Popen(["xdg-open", str(p)])  # noqa: S603,S607
