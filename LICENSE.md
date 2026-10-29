# Lisans — Denizli Garaj 2Q Şerit Takip Kamerası Yazılım Düzenleyici

Copyright (c) 2026 **Denizli Garaj**

## 1. Verilen izin

Bu yazılımı ve belgelerini elde eden her gerçek kişiye, **ticari olmayan** amaçlarla
(bağımsız araştırma, teşhis, onarım, kişisel retrofit, eğitim) kullanma, inceleme,
değiştirme ve yeniden dağıtma izni ücretsiz olarak verilir. Aşağıdaki koşullar geçerlidir:

1. **Atıf:** Tüm kopyalar, çatallar (fork) ve türev çalışmalar bu lisans dosyasını ve
   aşağıdaki atıfları korumak zorundadır:
   - **Schutz-Kaput** — https://github.com/perkthefox/mqb-kshutz-kaput (yazar: PerkTheFox)
   - **Denizli Garaj 2Q Şerit Takip Kamerası Yazılım Düzenleyici**
2. **Ticari satış yasağı:** Bu yazılımı veya onunla üretilen dosyaları satmak, kiralamak,
   ücretli paket/paywall içine almak, "aktivasyon hizmeti" olarak ücretlendirmek yasaktır.
3. **Sorumluluk:** Yazılım "olduğu gibi" (AS IS) sunulur. Araç/ECU üzerindeki tüm sonuçlar
   kullanıcıya aittir. Yazar hiçbir doğrudan/dolaylı zarardan (tuğla olmuş ECU, araç hasarı,
   kalibrasyon/çekici masrafı, yaralanma, trafik olayı, yasal yaptırım, garanti kaybı) sorumlu
   değildir.

## 2. Bu yazılım ne içermez

- **Hiçbir OEM firmware, ROM dump veya üçüncü taraf kaynak kodu içermez.** Yalnızca özgün
  arayüz/orkestrasyon kodu vardır; yamalama işini kullanıcının diskindeki
  `ks_patcher.py` (Schutz-Kaput) yapar.
- Firmware dosyaları telif hakkıyla korunur ve bu depoya dahil edilmez.

## 3. Yasal çerçeve

Yazılım; kullanıcının **kendi mülkiyetindeki** donanımda onarım, teşhis ve retrofit amacıyla
geliştirilmiştir. Tasarım koruması ve fikri mülkiyet mevzuatı ülkeden ülkeye değişir
(AB: 2009/24/EC md. 5–6; ABD: 17 U.S.C. § 1201(f) ve 37 C.F.R. § 201.40(b) onarım muafiyeti).
Kullanıcı, bulunduğu ülkenin mevzuatına uymakla yükümlüdür. Çalıntı araç/parça, sayaç
müdahalesi veya hukuka aykırı menşe gizleme amacıyla kullanım kesinlikle yasaktır ve lisansı
derhal geçersiz kılar.

## 4. Güvenlik ve homologasyon

ADAS firmware değişikliği üretici garantisini geçersiz kılabilir, aracın tip onayını
(`ECE`, `StVZO`, `DOT` vb.) etkileyebilir ve optik kalibrasyon (`VAS 6430` veya eşdeğeri)
yapılmadığı sürece sürücü desteği davranışını bozabilir. Yol trafiğine açık alanda kullanım
için yerel mevzuatı kontrol et. Bu araçlar **otonom sürüş değildir**; sorumluluk sürücüdedir.

## 5. Bağımsızlık

Bu proje Volkswagen AG, Audi AG, Škoda, SEAT/CUPRA, Valeo, Renesas veya Mobileye ile
bağlantılı değildir, onlar tarafından onaylanmamıştır. Tüm marka ve parça numaraları yalnızca
teknik uyumluluğu tanımlamak için kullanılmıştır.
