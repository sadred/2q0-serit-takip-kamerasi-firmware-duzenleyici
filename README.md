# Denizli Garaj 2Q Şerit Takip Kamerası Yazılım Düzenleyici

Valeo **MFK3** ön ADAS kamerası (`2Q0 980 653` / `653B` / `653C` / `653D` / `653J`, diag **`0x00A5`**)
için ham firmware dosyalarını **CP pasif + FeC açık + virgin key DTC bastırılmış**, ODIS-E ile
yazılabilir paketlere çeviren masaüstü aracı.

- Girdi: `FL_*.frf` / `.odx-f` / `.odx` / `.pdx` (ham firmware) veya programmer dump `.bin`
- Seçenek: **CP pasif** · **FeC (9 kod)** · **Virgin key DTC bastırma** · (ops.) XCP/CAN0
- Çıktı: sürüm başına `PART1/` + `PART2/` + `RAPOR.txt`, toplu `OZET.txt`
- Her dosya bağımsız doğrulanır; yapılamayan varsa satır **HATA** olur ve gerekçesi yazılır

## Kullanılan kaynak / atıf

Bu programın yama mantığı **PerkTheFox**'un **Schutz-Kaput** projesine dayanır ve çalışırken
onu harici olarak çağırır (kodu bu repoda yer almaz):

> **Schutz-Kaput** — VAG ECU CP & SWaP Patcher · https://github.com/perkthefox/mqb-kshutz-kaput
> Yazar: **PerkTheFox** · https://vwhacking.antonperk.com · Drive2: perkthefox · Telegram: @perkthefox

Bu arayüz o projenin `ks_patcher.py` dosyasını, senin diskindeki bir kopyadan çağırır
(`--build-odx`, `--suppress-key-dtcs`, `--no-fecs` bayrakları). Doğrulama, toplu işleme,
Türkçe arayüz ve raporlama bu projeye aittir.

## Kurulum

**Hazır exe:** `dist/DenizliGaraj-2Q-Kamera-Duzenleyici.exe` (tek dosya, Python gerekmez).

**Kaynaktan:**

```bash
python denizli_garaj_2q.py      # Python 3.9+, tkinter, harici paket yok
DenizliGaraj-2Q.bat             # çift tıkla
```

### Yama motorunu tanıtma

`ks_patcher.py` şu konumlardan birinde olmalı (ilk bulunan kullanılır):

1. exe'nin / script'in yanındaki `ks_patcher.py` veya `mqb-kshutz-kaput/`, `motor/` klasörü
2. `Documents/tools/mqb-kshutz-kaput`
3. `Downloads/mqb-kshutz-kaput`, `Desktop/mqb-kshutz-kaput`

Yoksa:

```bash
git clone https://github.com/perkthefox/mqb-kshutz-kaput
```

## Kullanım

1. **Dosya ekle… / Klasör ekle…** ile ham firmware'leri listeye at. Satır başındaki **☑** ile
   dosya tek tek devre dışı bırakılabilir.
2. **Ne uygulanacak?** → `CP pasif`, `FeC (9 kod)`, `Virgin key DTC bastır` işaretle.
3. **Çıktı klasörü** → varsayılan `Desktop\2Q_KAMERA_YAMALI` (DTC seçilirse `…_KDT`).
4. **▶ Derle** — dosyalar sırayla okunur, yamalanır, doğrulanır.

### Doğrulama kriterleri

| Kontrol | Ne bakılıyor |
|---|---|
| Durum bayrakları | Üretilen `PART1` yeniden okunur: `ks_state` / `fec_state` / `key_dtc_state` / `xcp_state` |
| Cold-boot başlığı | `DB_01` ilk 8 bayt `00 00 00 AA 00 82 04 00` |
| CRC tutarlılığı | `BF_01` adındaki CRC32 = hesaplanan CRC32 |
| Harici dosyalar | Konteynerin `<DATAFILE>` referansları klasörde mevcut |
| Bütünlük | `PART1` + `PART2` ikisi de üretildi |

İstenen bir grubun imzası o firmware'de yoksa (ör. SW 1202'de `Xcp_BootControl`) o seçenek
**o dosya için** uyarıyla atlanır; dosya yine `TAMAM` olur ve notta `imza yok: xcp` yazar.

## Flash (ODIS-E 17/18 + VAS 6154A)

1. `PART1\` içindeki `.odx-f` → flash. Sonunda **imza hatası beklenir**, kontağı/adaptörü KESME.
2. Hemen `PART2\` içindekini flash et → `71 01 02 02 01`, %100 yeşil.
3. `BF_*.bin` dosyalarını `.odx-f`'den ayırma.

Bu paketler gömülü yamadır: **ODIS-S online CP kaldırma ve SWaP anahtar transferi gerekmez.**
Sonrasında optik kalibrasyon (`VAS 6430`) ve araç tarafı kodlama (gateway `0x19`, `A5` dataset,
`44`/`03`/`17`) şart.

## Exe derleme

```bash
python -m venv .build-venv
.build-venv/Scripts/python -m pip install pyinstaller
.build-venv/Scripts/python -m PyInstaller --noconfirm --onefile --windowed ^
  --icon assets/logo.ico --add-data "assets;assets" ^
  --name DenizliGaraj-2Q-Kamera-Duzenleyici denizli_garaj_2q.py
```

## Firmware hakkında

Bu repoda **hiçbir OEM firmware bulunmaz**. VAG/Valeo firmware dosyaları telif hakkıyla
korunur; bu yüzden repoya eklenmez (`.gitignore` ile hariç tutulur). Kendi dosyalarını
`org/` klasörüne koyup arayüzden seçersin.

## Lisans

[LICENSE.md](LICENSE.md) — non-commercial / Right-to-Repair. Ticari satış ve ücretli hizmet yasak.
Atıf zorunlu: **PerkTheFox / Schutz-Kaput** + **Denizli Garaj**.

## Uyarılar

- Sürüm kameranın mevcut yazılımıyla **birebir** eşleşmeli; yanlış sürüm = tuğla.
- Tuğla olan kamera OBD'den kurtarılamaz (bench programmer gerekir). Önce tam yedek al.
- Yasal çerçeve: kendi malın olan donanımda onarım/retrofit; üçüncü şahıs araçlarında ve
  ticari kullanımda sorumluluk kullanıcıdadır. ADAS firmware değişikliği aracın
  homologasyonunu etkileyebilir.
