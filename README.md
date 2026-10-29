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

**Hazır exe (önerilen):** `dist/2Q0-SeritTakip-Kamera-Firmware-Duzenleyici.exe`
— **tek dosya**, Python gerekmez, **yama motoru exe'nin içinde gömülü** (dış `.py` gerekmez).
Kod imzalı (self-signed): sertifika `assets/denizli-garaj-kod-imza.cer`.

**Kaynaktan:**

```bash
python denizli_garaj_2q.py      # Python 3.9+, tkinter, harici paket yok
DenizliGaraj-2Q.bat             # çift tıkla
```

### Komut satırı (toplu derleme)

```bash
2Q0-SeritTakip-Kamera-Firmware-Duzenleyici.exe --out C:\cikti --kdtc org\FL_*.frf
# seçenekler: --no-fec · --kdtc · --xcp · --bin
```

### Yama motoru (geliştirici modu)

exe gömülü motorla gelir. Kaynaktan (`python denizli_garaj_2q.py`) çalıştırırken motor şu
sırayla aranır: `motor/` (paket içi) → `ks_patcher.py` yanındaki klasör → `Documents/tools/mqb-kshutz-kaput`.
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
  --icon assets/logo.ico --add-data "assets;assets" --add-data "motor;motor" ^
  --hidden-import xml.etree.ElementTree --hidden-import xml --hidden-import select ^
  --hidden-import signal --hidden-import unicodedata --hidden-import base64 ^
  --hidden-import tarfile --hidden-import datetime ^
  --name 2Q0-SeritTakip-Kamera-Firmware-Duzenleyici denizli_garaj_2q.py
```

`motor/` klasörü Schutz-Kaput'un yamasız kopyasıdır (kendi `LICENSE.md`/`README.md` dosyalarıyla
birlikte gelir) — exe'nin içine gömülür, böylece dış `.py` dosyası gerekmez.

## Kod imzası

exe, **Denizli Garaj** adına üretilmiş **self-signed** kod imzalama sertifikasıyla imzalanmıştır
(SHA-256, zaman damgalı). Bu makinede sertifika `Trusted Root` + `Trusted Publisher` depolarına
kurulduğu için Windows açılışta uyarı vermez.

Başka bir bilgisayarda uyarı çıkmaması için `assets/denizli-garaj-kod-imza.cer` dosyasını
**Güvenilen Kök Sertifika Yetkilileri** ve **Güvenilen Yayımcılar** depolarına ekleyin
(çift tık → Sertifika Yükle → «Sertifikayı şu depoya yerleştir»). Alternatif: CA'dan
(OV/EV) alınmış gerçek bir kod imzalama sertifikası kullanmak — SmartScreen itibarı için tek yol budur.

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
