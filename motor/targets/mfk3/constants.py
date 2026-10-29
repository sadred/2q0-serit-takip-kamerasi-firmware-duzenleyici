"""Hardware layout, SWaP/FeC table, and factory ODX constants for Valeo MFK3 (`2Q0 980 653`, `0x00A5`)."""

from __future__ import annotations

import struct


# RH850/P1H-C (R7F701372A) memory & flash layout constants for Valeo MFK3 (2Q0 980 653)
DB01_BASE_VA = 0x00048000
DB01_END_VA_EXCL = 0x00200000
DB01_MAX_REGION_SIZE = DB01_END_VA_EXCL - DB01_BASE_VA      # 0x001B8000 (1,802,240 B)
DB01_SW1423_SIZE = 0x001B7F18                               # 1,802,008 B
DB01_MIN_VALID_APP_SIZE = 0x00100000                        # >= 1 MiB for MEAPP (rejects 222 KB 0220_FBL!)
FBL_UPDATER_DB01_SIZE = 227840                              # 0x37A00 (FL_2Q0980653J_0220_FBL_V001_S)

DB01_HEADER_MAGIC = 0xAA000000                              # 00 00 00 AA LE @ 0x00048000
DB01_HEADER_REJECT_MAGIC = 0xA5000000                       # Rejected by 0220 cold boot
DB01_HEADER_ENTRY = 0x00048200                              # 00 82 04 00 LE @ 0x00048004
DB01_EXPECTED_HEADER_8B = struct.pack("<II", DB01_HEADER_MAGIC, DB01_HEADER_ENTRY)

BANK0_DUMP_SIZE = 0x00200000                                # 2 MiB (0x00000000..0x001FFFFF)
DUAL_BANK_DUMP_SIZE = 0x00400000                            # 4 MiB (Bank 0 2 MiB + Bank 1 2 MiB)
LINEAR_10M_DUMP_SIZE = 0x00A00000                           # 10 MiB (0x00000000..0x009FFFFF)
LINEAR_9D8_DUMP_SIZE = 0x009D8000                           # 0x00000000..0x009D7FFF

BANK0_DB04_OFF = 0x00002000
BANK0_FBL_VER_OFF = 0x00037F00
BANK0_DB7100_OFF = 0x00038000
BANK0_DB01_OFF = 0x00048000

MFK3_EXPECTED_DUMP_SIZES: tuple[int, ...] = (
    DB01_SW1423_SIZE,
    DB01_MAX_REGION_SIZE,
    BANK0_DUMP_SIZE,
    DUAL_BANK_DUMP_SIZE,
    LINEAR_9D8_DUMP_SIZE,
    LINEAR_10M_DUMP_SIZE,
)

# All 9 SWaP / FeC codes defined in MFK3 NvM 0x53 (`0xFEE89131`, ROM `0x00147641`)
MFK3_SWAP_FECS: tuple[tuple[str, str, str], ...] = (
    (
        "100E1000",
        "Основные ассистенты водителя (удержание в полосе, автодальний, pACC)",
        "Core Driver Assistants (Lane Assist, High Beam Assist, pACC)",
    ),
    (
        "100E1100",
        "Расширенное ведение по полосе (Lane Guidance)",
        "Extended Lane Guidance",
    ),
    (
        "100E1200",
        "Дополнительный канал ассистентов водителя #1",
        "Additional ADAS Feature Channel #1",
    ),
    (
        "100E1300",
        "Дополнительный канал ассистентов водителя #2",
        "Additional ADAS Feature Channel #2",
    ),
    (
        "100E1400",
        "Дополнительный канал ассистентов водителя #3",
        "Additional ADAS Feature Channel #3",
    ),
    (
        "100E1500",
        "Дополнительный канал ассистентов водителя #4",
        "Additional ADAS Feature Channel #4",
    ),
    (
        "100E0F00",
        "Распознавание дорожных знаков (VZE)",
        "Traffic Sign Recognition (VZE)",
    ),
    (
        "100E1600",
        "Резервный слот функций #1",
        "Reserved Feature Slot #1",
    ),
    (
        "100E1700",
        "Резервный слот функций #2",
        "Reserved Feature Slot #2",
    ),
)

KNOWN_DB01_CRCS: dict[int, str] = {
    0x0E6C1A8A: "2Q0980653J SW 1423 MEAPP V001 (Stock)",
    0xF7D80D6E: "2Q0980653J SW 0220 FBL Updater V001 (BOOTLOADER — DO NOT PATCH AS MEAPP!)",
}

MFK3_DB_TO_FD_MAP: dict[str, str] = {
    "DB_30ERASEPROGRROUTI": "FD_30ERASEPROGRROUTI",
    "DB_01FLASHDATA": "FD_01FLASHDATA",
    "DB_02FLASHDATA": "FD_02FLASHDATA",
    "DB_03FLASHDATA": "FD_03FLASHDATA",
    "DB_04FLASHDATA": "FD_04FLASHDATA",
}

STOCK_DB30_CRC32 = 0x686DECEF
STOCK_DB30_SIGNATURE_HEX = (
    "de757c968620fcd1b75f4f9a59847f4eea743fb4e4185ccfa8938cc7fcd14efa"
    "4aaa4998721883173265a4084230aeaa15347dc2876b4dff8acd58191dfe0b35"
    "d4c98ab7a3b76da3c2a9eaa5523aeca03a9a8ab7408e929177ab7ee3516bfabd"
    "22259eb11554a926ee5686332782e43c47240eb1c766a6fc3507229b611b786a"
)
STOCK_DB01_1423_SIGNATURE_HEX = (
    "d412d27a8a8e64d385c92658efa6be6a8294a3bcb8bc550df8d79a4ea9bf159a"
    "0fedd46685e9dada8a62c398dfe979e0ea50d7cc8ead4170a1da74646deb3280"
    "411025808bf1b314a4a0ddecb547a94f86ce7e27b5dc318670a3c16d72e869e7"
    "ab10490e0e465f74cced9e66927dae6f13761d579f0ca429c41a3c7224b97e70"
)
STOCK_DB04_1423_SIGNATURE_HEX = (
    "d0699d45cd5b4a07a298ac66ee7c684042f4998974f8434d0a30041eeb418c8b"
    "79bd294796ea9432795ca2d8e77d2aac219d0b9ff5ec9912b57d61262e3ea0f6"
    "f914adcf5f8b12d224f29dc9abe61cdf754639f6f422d7b7111c809d895b2c46"
    "af9f4a712838c3b07ae331abfc5e36dce5ce6687150f480e0ba153bd53f6b382"
)
