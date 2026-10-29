# Schutz-Kaput Community Research & Right-to-Repair License

**Copyright (c) 2026 PerkTheFox**  
- Website: https://vwhacking.antonperk.com  
- Drive2: https://www.drive2.ru/users/perkthefox/  
- Telegram: https://t.me/perkthefox  

> **TL;DR:** Free for honest owners, researchers, and tinkerers — **strictly forbidden** for commercial resellers, stolen parts, or blaming the author if you turn your ECU into an expensive paperweight.  
> *(Ниже приведены равнозначные версии на английском и русском языках / Both English and Russian sections below apply equally.)*

---

## 🇬🇧 English Version

### 1. Grant of Non-Commercial Research & Personal Repair License
Permission is hereby granted, free of charge, to any natural person obtaining a copy of this software and associated documentation files (the **"Software"**), to inspect, study, execute, modify, and redistribute the Software **strictly for non-commercial purposes** — specifically independent academic/security research, interoperability analysis, diagnosis, repair, and personal retrofitting of lawfully owned hardware — subject to all of the following conditions:

1. **Attribution:** All copies, forks, or substantial portions of the Software must retain the above copyright notice, author links (`PerkTheFox` / `vwhacking.antonperk.com`), and this entire `LICENSE.md` file unmodified.
2. **Strictly Not For Sale (Zero Commercialization):** You may **NOT** sell, rent, lease, sublicense, paywall, bundle into paid "activator" / group-buy ("skladchina") packages, or charge any fee for the Software itself, nor may you commercially sell pre-patched firmware images, containers, or commercial unlocking services generated with the Software.

### 2. Clean-Room Tool & Zero Proprietary Firmware Notice
This repository contains **zero bytes (`0 B`)** of proprietary OEM firmware, ROM dumps, dealer diagnostic software, or leaked vendor source code. All source code herein is independent original work implementing general-purpose container framing and byte-pattern transformations on files locally supplied and lawfully possessed by the user.

### 3. Statutory Right-to-Repair & Interoperability Safe Harbors
This Software is developed and published strictly within the scope of established statutory exemptions for interoperability, security research, and independent repair of lawfully acquired motorized land vehicles, including without limitation:
- **European Union:** Directive 2009/24/EC on the legal protection of computer programs (Articles 5 and 6 — lawful acquirer's right to observe, study, test, and adapt embedded software for interoperability and error correction);
- **United States:** 17 U.S.C. § 1201(f) (Reverse Engineering for Interoperability) and Library of Congress Exemption **37 C.F.R. § 201.40(b)** (computer programs embedded in motorized land vehicles accessed for diagnosis, repair, or lawful modification of a vehicle function);
- **Applicable National Laws:** Equivalent statutory exceptions for lawful owners of hardware containing embedded computer programs (including **Article 1280 of the Civil Code of the Russian Federation**).

### 4. Lawful Ownership Mandate (Strict Anti-Theft Clause)
You may use the Software **solely** on electronic control units (ECUs) and vehicles to which you hold clear, verifiable, lawful title (or explicit authorization from the verifiable lawful owner for unpaid personal assistance). Any use of the Software in connection with stolen vehicles, stolen/untraceable parts, fraud, odometer tampering, or concealment of unlawful origin is **strictly prohibited** and immediately terminates your license *ab initio*.

### 5. Automotive Safety, ADAS Calibration & Homologation Notice
Modifying software inside automotive ECUs — especially Advanced Driver Assistance Systems (**ADAS**, such as `0x00A5` front cameras) — may:
- void manufacturer or dealer warranties;
- invalidate public-road vehicle homologation / type approval (`ECE`, `StVZO`, `DOT`/`FMVSS`, `ОТТС`, etc.);
- alter or degrade optical recognition and driver-assistance behavior unless followed by proper dataset matching, vehicle coding, and professional static/dynamic optical calibration (`VAS 6430` or equivalent).

Unless explicitly permitted and inspected under your local road-traffic regulations, modified ECUs are intended **exclusively for bench research, emulation, and closed-course / off-public-highway testing**. Driver-assistance functions are **never** autonomous driving; the human driver remains 100% alert, in control, and legally responsible for safe vehicle operation at all times.

### 6. Non-Affiliation & Nominative Trademark Notice
This is an independent community research project. It is **not** affiliated with, endorsed by, sponsored by, or approved by Volkswagen AG, Audi AG, Škoda Auto, SEAT/CUPRA, Valeo, Renesas Electronics, Mobileye, or any of their affiliates. All product names, protocol acronyms (`ODIS`, `SWaP`, `FeC`, `GEKO`, `FAZIT`), and hardware part numbers (`2Q0 980 653`, etc.) are trademarks or identifiers of their respective owners and are used strictly in a descriptive, nominative fair-use manner to identify technical compatibility.

### 7. Disclaimer of Warranty, Assumption of Risk & Limitation of Liability
THE SOFTWARE IS PROVIDED **"AS IS"**, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, SAFETY, ACCURACY, AND NON-INFRINGEMENT.

THE SOFTWARE DOES NOT COMMUNICATE WITH ANY VEHICLE OR CONTROL FLASHING HARDWARE. BY EXECUTING THE SOFTWARE, YOU ACKNOWLEDGE THAT FLASHING MODIFIED DATA CAN PERMANENTLY "BRICK" ELECTRONIC CONTROL UNITS BEYOND OBD RECOVERY (REQUIRING HARDWARE BENCH PROGRAMMING OR REPLACEMENT). IN NO EVENT SHALL THE AUTHOR (`PerkTheFox`) OR CONTRIBUTORS BE LIABLE FOR ANY CLAIM, DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING BRICKED ECUS, VEHICLE DAMAGE, CALIBRATION OR TOWING COSTS, PERSONAL INJURY, TRAFFIC INCIDENTS, REGULATORY FINES, OR LOSS OF WARRANTY), HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE. YOU AGREE TO INDEMNIFY AND HOLD HARMLESS THE AUTHOR FROM ANY CLAIMS ARISING OUT OF YOUR UNLAWFUL, UNSAFE, OR COMMERCIAL MISUSE OF THE SOFTWARE.

---

## 🇷🇺 Русская версия

### 1. Некоммерческая исследовательская лицензия и право личного ремонта
Настоящим любому физическому лицу, получившему копию данного программного обеспечения и сопутствующей документации (далее — **«ПО»**), безвозмездно предоставляется право изучать, запускать, модифицировать и распространять ПО **исключительно в некоммерческих целях** — для независимых технических исследований, анализа совместимости (интероперабельности), диагностики, ремонта и личного дооснащения законно принадлежащего пользователю оборудования — при строгом соблюдении следующих условий:

1. **Сохранение авторства:** Во всех копиях, форках и производных материалах должны в неизменном виде сохраняться уведомление об авторских правах (`PerkTheFox` / `vwhacking.antonperk.com`), ссылки на автора и полный текст настоящего файла `LICENSE.md`.
2. **Строгий запрет на коммерцию (`STRICTLY NOT FOR SALE`):** Категорически **ЗАПРЕЩАЕТСЯ** продавать ПО, сдавать его в аренду, закрывать платной подпиской, включать в платные сборники/«складчины»/коммерческие пакеты, а также продавать за деньги сгенерированные с помощью этого ПО бинарные дампы, прошивочные контейнеры или коммерческие услуги «удалённой активации».

### 2. Отсутствие чужого проприетарного кода
В данном репозитории содержится **ровно ноль байт (`0 Б`)** заводских прошивок, дампов ПЗУ, дилерского ПО, закрытых ключей подписи или проприетарного исходного кода автопроизводителей и их поставщиков. Весь код написан автором с нуля на стандартном Python и представляет собой универсальный локальный инструмент преобразования байтовых последовательностей и контейнерной разметки для файлов, которыми пользователь уже владеет на законных основаниях.

### 3. Право на ремонт (Right to Repair) и законодательные основания
Разработка и публикация ПО опираются на общепризнанные нормы права на исследование, обеспечение совместимости и самостоятельный ремонт законно приобретённых технических средств:
- **Ст. 1280 Гражданского кодекса РФ** (право лица, правомерно владеющего экземпляром программы / устройством со встроенным ПО, на адаптацию, исправление явных ограничений работоспособности и достижение совместимости с другими техническими средствами пользователя без согласия правообладателя);
- **Директива ЕС 2009/24/EC (ст. 5 и 6)** — право законного владельца изучать, тестировать и адаптировать встроенное ПО для интероперабельности;
- **17 U.S.C. § 1201(f) и исключение 37 C.F.R. § 201.40(b) (DMCA Land Motor Vehicle Repair & Modification Exemption)** — прямое разрешение владельцам наземных транспортных средств модифицировать встроенное ПО ЭБУ в целях диагностики, ремонта и законной модификации функций автомобиля.

### 4. Законность происхождения железа (Анти-криминальная оговорка)
Использование ПО разрешено **исключительно** с электронными блоками управления и автомобилями, на которые у вас есть законное право собственности. Любая попытка использования ПО в отношении краденых автомобилей, деталей криминального или неизвестного происхождения, для мошенничества или сокрытия следов хищения **категорически запрещена** и автоматически аннулирует действие настоящей лицензии с момента нарушения (*ab initio*).

### 5. Безопасность движения, калибровка ADAS и дорожная омологация
Внесение изменений в прошивку автомобильных ЭБУ — особенно систем помощи водителю (**ADAS**, включая переднюю камеру ассистентов `0x00A5`) — может:
- повлечь прекращение заводской или дилерской гарантии;
- повлиять на соответствие транспортного средства требованиям одобрения типа ТС (`ОТТС`, `ТР ТС 018/2011`, `ECE`, `StVZO` и др.);
- изменить работу оптических алгоритмов при отсутствии корректной параметрии, кодировки и обязательной стендовой/динамической калибровки камеры (`VAS 6430` и аналоги).

Если иное прямо не допускается законодательством вашей страны после прохождения соответствующих проверок, модифицированные блоки предназначены **исключительно для стендовых исследований, эмуляции и испытаний вне дорог общего пользования (на закрытых площадках)**. Электронные ассистенты не являются автопилотом: всю полноту ответственности за управление автомобилем и соблюдение ПДД ежесекундно несёт водитель.

### 6. Отсутствие аффилированности и товарные знаки
Проект является полностью независимым исследованием энтузиастов и **не связан** с Volkswagen AG, Audi AG, Škoda Auto, SEAT/CUPRA, Valeo, Renesas Electronics, Mobileye или их дочерними компаниями. Все упоминаемые в документации названия брендов, протоколов (`ODIS`, `SWaP`, `FeC`, `GEKO`, `FAZIT`) и каталожные номера деталей (`2Q0 980 653` и др.) принадлежат их законным правообладателям и используются исключительно в справочно-информационных целях (*nominative fair use*) для указания технической совместимости оборудования.

### 7. Полный отказ от гарантий и ограничение ответственности (`«КАК ЕСТЬ»`)
ПРОГРАММНОЕ ОБЕСПЕЧЕНИЕ ПРЕДОСТАВЛЯЕТСЯ ПО ПРИНЦИПУ **«КАК ЕСТЬ» (`AS IS`)**, БЕЗ КАКИХ-ЛИБО ПРЯМЫХ ИЛИ ПОДРАЗУМЕВАЕМЫХ ГАРАНТИЙ РАБОТОСПОСОБНОСТИ, БЕЗОПАСНОСТИ ИЛИ ПРИГОДНОСТИ ДЛЯ КОНКРЕТНЫХ ЦЕЛЕЙ.

СКРИПТ НЕ ПОДКЛЮЧАЕТСЯ К АВТОМОБИЛЮ И НЕ УПРАВЛЯЕТ ПРОЦЕССОМ ПРОШИВКИ. ЗАПУСКАЯ ПРОГРАММУ, ВЫ ПОДТВЕРЖДАЕТЕ, ЧТО ПОНИМАЕТЕ РИСКИ: ЗАПИСЬ МОДИФИЦИРОВАННЫХ ДАННЫХ МОЖЕТ ПРИВЕСТИ К НЕОБРАТИМОМУ ВЫХОДУ ЭБУ ИЗ СТРОЯ («ОКИРПИЧИВАНИЮ»), ПОСЛЕ ЧЕГО ВОССТАНОВЛЕНИЕ ПО OBD НЕВОЗМОЖНО БЕЗ АППАРАТНОГО ПРОГРАММАТОРА НА СТОЛЕ ИЛИ ЗАМЕНЫ БЛОКА. НИ ПРИ КАКИХ ОБСТОЯТЕЛЬСТВАХ АВТОР (`PerkTheFox`) НЕ НЕСЁТ ОТВЕТСТВЕННОСТИ ЗА ЛЮБОЙ ПРЯМОЙ, КОСВЕННЫЙ, СЛУЧАЙНЫЙ ИЛИ ПОБОЧНЫЙ УЩЕРБ (ВКЛЮЧАЯ ВЫШЕДШИЕ ИЗ СТРОЯ ЭБУ, ПОВРЕЖДЕНИЕ АВТОМОБИЛЯ, РАСХОДЫ НА ЭВАКУАЦИЮ/ПРОГРАММАТОРЫ/КАЛИБРОВКУ, ДТП, ШТРАФЫ ИЛИ ПОТЕРЮ ГАРАНТИИ), ВОЗНИКШИЙ В СВЯЗИ С ИСПОЛЬЗОВАНИЕМ ИЛИ НЕВОЗМОЖНОСТЬЮ ИСПОЛЬЗОВАНИЯ ДАННОГО ПО.
