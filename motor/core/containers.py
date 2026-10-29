"""VAG ODX / ODX-F / PDX / FRF / ODIS XML container codec, built-in `frf.key`, and `LZSS A0` codec."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import datetime as dt
import io
from pathlib import Path
import re
import tarfile
import xml.etree.ElementTree as ET
import zipfile
import zlib

from .i18n import tr


XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
XSI_TYPE_ATTR = f"{{{XSI_NS}}}type"

BUILTIN_FRF_KEY_SHA256 = "08909854ee0856571035b53bb0b260d13a01fb66a0357f84540a5892376a1ee3"
BUILTIN_FRF_KEY_B85 = (
    'c-jrr1Ck>F006*>W@6j6ZF^&T<Be^8{q7H4Z5H))3|4r#Cy-RH0Wxx)Y!06oClbNC5<OTFdvlDlruN'
    'S?Tw$XJq`Gs;u`V@hGT8~n0zyASBCiqL($X=a$6$^J<zl#=Oz8rhV+p*Ed+c%nm(4m(MR@V-u7A!oX'
    'wU*frV-F1TWVdTn6zxFnZ0st&|qZ0k3THFjaUfCz9IigqH$8xztE_1dye*p=!>JZ6U|QT!)?cpt;sK'
    ';C*k>GpUo{c-XI}oOYI8+dpB6>)nWSzjG4*s#I2txD8PN@W^SVjj3|2%@w+ooN28&Vd2P$En-qBrkJ'
    '<-%X#YknKEe~?Ws>I+<PO3s7WR`}#_Z3!>9L^~6%|tGD!f%^xAG--$KvsgNk=hD6SAG`ciwFPaNp|<'
    '`%HNCsQFrRh$ps(o$j;F%gMe7(xqiDwYs3W(G>o7>W;!;?qRbk-t@2SQuPCUjs(H-iqYpZQijk*)xX'
    'Ph5@<&M&>+c42282(jmlW_eR<Y+`eOfC*qV7f6>)6RGQRr>qDIs~=ff<^Rp1%yXRx98<l5L9`{u)i!'
    'y$SwCm+=hw~#m}0xX&$N~YjiJ4(m3-xh_RMxB=BQ378&_yA_EUAa+&7=Zkz;3o(ICAQ(`V2JwQeOGf'
    'qL(|YVY_M%}u8Pb}i1^>Va*g5#Uy?#`_>1B-HCf^t8YJuJO?1HFob4~Jxfq?IhmSV`*ew8q_ylhn>F'
    'M?$#h6egn8|2kUk4Dycq*SWmEVwNEez3#Q#&dtuPFaDH2U$elV=BZtG8Y#bD>0<q^+iiSfj1mChj*w'
    'pNJbrXPT?zD$(?-wx|%pHH+i!v71La_I}dYPDAiHJ5=kw=P!UPK%s`r$(Yv{+AT$HfG`)e1F3SHfa6'
    '9F?qPu}e8_u434uux*RlX#w-hQ0=)=fQC9>=?>+qJS8p0F{?!z)F-OvHPahljc`#E%=`MwTdVPj(v{'
    'AcHDKm>6DmCLS3&s3mWUrkLZ)>L-<cXkMoB?;Xdge1U^h&0))2y|h|<ATGg-0u)oR@pOPSpt&ct!pB'
    'KEz=KDV+muEq;4h|U(xkcTacPsJ-#Y_uFNy3m^@nAG(;h*HyE0!;g2jrBYXj7FKd+5!UtEaVH5ct@W'
    'xqAG!4*%gLLjKFy)VH>~7tOGcGY|^27X#AK=a+18y;9WuenSZhc)pcGgSq-3s3s0V9o-yy2bu+-!rz'
    'mt%d8;VC&EU{ksYOQ~CwTGuTM`Jc+z6e<1)GUu*JN85~#LP&L3H2EOPyuHcJe(%T@&9}+J3f=T$r(s'
    'I>^QIj^>&4upS}R&nC*OUUPkn4Kp}xo8h%J1lmAl^MT$E_RpmGuxQKHxqDXj-a*>{mG_k8&pr~2IWV'
    '#7lf32W;bL)_Zy*<xKF@`{|)4KKQ<Jg#hfb3`oQbk|0Nq(Wx6#SDm}3sO|w+>k+>J@jpSR7v-kd@*|'
    '%n512Ij%A-j$#Auf$e^X3Z4L1wJ3c*@f-&HI_EiT?+sXSxhFUualfKM6#WhR~JLq<tAH=}DY#D;sI9'
    'aDFrxNR~!j#+;JE!W`N)An{&DT#{f#%~La|i62oz(mtMP(B+vC><sr)dP?sJ;K{_weaNNw`+!len|O'
    '<2_IQ1G=sVWD9!ye~jf#ZT|HumZf9Zx?dB@&cE}jXa#6M;_@xuOU)p-*>74x-WIEAwiF+ez$h59#zX'
    'Hg)JrduB3lM3nKnZIr%?WIHEZPO(QEwe#pTf}ysLj^!LeZ4!O!koJ}!@nqLMVo?tzX%uA$1aL|t2cY'
    '5JiDVu@h4pB_5P;RkRqHJTefET~oF-CQ#}&}|>;&Y?m(B~t(UM{YGU1=dBef?EwgL32ZT1<duP9uFC'
    '$#@QBfj}!e$QCbiE2c=%>UtW`P|7x1Sn%N?Jc)mG^orf&Hv*IKx^}>-d_jJ(=S@2fw!Z+E4*4@9hs#'
    'jQrMX5aCC?1OlDfh#IvWQ|3SWZ>_Sy)S!;<)On=VmEX-GH+xV1TyW>BJwWgF>V7hh&lld+IFYmDpH|'
    '^tKSye%zWI!ctG|IN2_Nj*grkhn5_<xRY)OSowNBkxMcNT~b*eIm3(!Hjp+WSM4gU#|1$0WchHdML0'
    'VVXG>B~0F(+;X|@k9Ot%*bh5nH7D*3)NX(F~X6G*y_#PcS*5(~B=a2Aur_B%W8R;ITu*(tL)Fe09W-'
    'enD64^oN_@r93-_?S0VB>1u>JrXcXgy1(;(Lw11`<qwPiRvf15xbHO<vA@FB{bF;yb$iKUV>O|C}1S'
    'uw2l&F#0`;Z+}GI<lQbQLUhQHOiMUHWRG?}j<!IVV?vqi{dGjAD2rA1R27#0GQ`?>NU}AIwwMTptWC'
    '+N}zv~LyiyBakkj<yFyOO{o-q_l=2;DODC^{}RTxD5G462gV#2^MqS2a1t3Sny6=MSO7rJfb<c|L0r'
    'Pa%H+^o0Db+L8)ucxDhw-VVhE9O7f*<L$uc@B|NMpzgqSmz%7b29fwW%Qf0jMv%_^ShZ6~6G_pl%-Q'
    'qR+IY5usOk@EUgtU_n6m2Ge8zQfhJkqD`(p2reWRo#EDWDcrpQ^M;t3`KGoDxKIWcA0wjvwa;n#Ld;'
    '2SncmA-6g!JC<!QZ-}RU`*1+P}qJQNfuC+xQntpbuQO33xk~n`I}x;hA~y7wrkAcUgHiW%N77Cyv2r'
    'Jp1AQOkn<&|LK>?`q+BlQ@yxdBe9X^*07*meu!#e%+Q-yivI0sNhwgPG<f1nvUm(jD?s>LhF8y-(`3'
    'O;)exYjs>=>d$@7Tk2qJI6=6Xi`HkZUi9s_4fuIVed?IPS=N@$fL3@OA)EOvGyE(zh<%|HjVS(sVlf'
    ';|RM}*Zc26OKPvZ=+S1}7J?IyGdARe$T5alV-}m-JuG!_FqwP}*I;E|M^MvYtEOB<Bo(uKb5(eA4=q'
    ')ly}&1BFvNK2N9<@-eX{ROTaWo*D2$Ym-<_Z2--CL9dw~VYGllqL<1O0;kA`@@qj#dB<PllX#Dqt!S'
    '{nX1G#t9&+BC{=YX@38MX^k8QWs|&oUU33xwivTV&e>iUGe=ENrMBG8Jk*XTG1b!2h=v}La$tsT^Gc'
    'M0tU)^rx$O4*Uw3<(ML%-FSBFz$$e%<z7xx`@1A(SG%utQq4Cu#*9Jae@dD{FW47ZOO!#wJH6e>HOk'
    'fRzY;}5NNuOwdlGMekK3~)FPIL{-S(snOc+!;Kq(69zJY8OW`=XQlB6jJ{MV1$COq9koBsR0LQ@^pn'
    'W}gGOo~3@)1(EzPNw~M#p>(0NR|>tm#}Jvn%`2wK!-ZnzT}n4ths@OuUH(*(=8v&xGOp1T+C37))+g'
    'Biu*sGofiMg5nJl|8keyw)b62Sq!EAlyXzXe=FaXm>P_42zt}~MZ+0O-edqEDebde8AWy+FP%yb;AY'
    '3M)!XJMngmD@$nd!Y+$G7UJ_$}8a`Fe=WJshbJ}mjJOST!Shhy()7~+Q$P0U`J6>D1f~<R03e3khxv'
    '<gxVOQ83@dsH~XhJ^d|j{IqRN&$i|aDA2K~(Ss*ow1ZboCfahuZgUe+6hIa{NZ0Q4=7V-q0RP_6v>I'
    '2Z!VcED+l73XBXDVf_%5b0!May(P2&O(uNN8;(-6xAMzwu>YDag_+^76{kOYQYw0Ny6)6T*7$%tHg0'
    ')zWTM_zwcjQ=sI=rE0Y(RVNRI;lG~QN#3F>Ou8w@xgx1j!iFml4{wU|p9b#Nc@E7rDD~3XD4i^vvot'
    'x<G;$khWuS(|Na-e3TWNhA)oJd`DR#?}Y-qYRsx3{btM{oH{OXBFQkR7DFJu_O`VnTDoKHY|Rd1E>j'
    'jld*Qjp;O)qT*7R7Yw%R>%s21#&hi&r?UjGvHQ)Wp$umG%W|;szqef8rC_KrTQkbI!{*UlvY($<X(v'
    'zdPFTJdy&Ad-TXC<S)TJ8B4Ri(=|;6_@Iv)sA<f91ikInJA$<p^3r80sp3J-GdgaR_;j;_co-N7GR*'
    '!S}RnLOj&&8O*{2*vNl%kD^7)B+6lKt*7z$EDY!c};t&rIoaJmnm~6y0z-0f>UZW^XP#7J}idefdc5'
    'pC!VdBL*%0+5DbV?34`HyKEQKlk7N8;pjvy87g&NY@5aNL%Se*D$*|Sx-6+15<K&IyPn~jY~rVO8g('
    'Nh$XAfg<%F@WLCkoCO?ROlBt+d8=Siu|>d*P7NN(0>qO$%1<WFwrYvKeR7r7vP)Yf5BuQKkIUys5+7'
    'S9}}dutS(c>2pU;SHqpSwKY!%zp;*tnurh#PRUy(ALO1l5%jis{Oepvv)Du{taNW0XKXU)M1y%qcBM'
    'C)i$*+m2nh7=xc^+uyn?(B}IBgZ<vbtX`QUG0oO5^^(lfe=GyxFw!(z8oW%;{%G}v*GMD|>iGqw&pY'
    'Qu+ZTU8$U&(X9rlrqVp3iuhIZ}nh(=M$>c1Zc=SD@!n1;OV5D)pLS;_nKP3I*R87wg1tD|AR95qU=q'
    '<-B1wXN(evw5~xZK5k?I#WQWVPOUny?(>L5jz{6w;Fu3DhU(yYJi*ggR}ulEOREaoI*XoP-`Vjy!Bd'
    'AfpZI;3@C@l2pCbi`;tGKBTg!ku=J2o;eqA?NaqhI<)u?o1(-WgM!;HS(`R;->W2pZbjX#;NQ8`(Wl'
    'tDt?3c4th;8L;F?%tp6>c}`as{>#yS)>CrK@Qiw-fY^9LU*+>3Qr~C{H4U3>2<;K57Mjr%K'
)

_CACHED_BUILTIN_FRF_KEY: bytes | None = None


def get_frf_key(frf_key_path: Path | None = None) -> bytes:
    """Return custom `frf.key` if provided, otherwise the built-in 4095-byte VAG FRF key."""
    global _CACHED_BUILTIN_FRF_KEY
    if frf_key_path is not None:
        return frf_key_path.read_bytes()
    if _CACHED_BUILTIN_FRF_KEY is None:
        _CACHED_BUILTIN_FRF_KEY = zlib.decompress(base64.b85decode(BUILTIN_FRF_KEY_B85))
    return _CACHED_BUILTIN_FRF_KEY


def frf_decrypt(data: bytes, key: bytes | None = None) -> bytes:
    """Decrypt VW `.frf` stream using 4095-byte `frf.key` (built-in by default)."""
    if key is None:
        key = get_frf_key(None)
    out = bytearray(len(data))
    first, second = 0, 1
    klen = len(key)
    for i, byte in enumerate(data):
        k = key[i % klen]
        first = ((first + k) * 3) & 0xFF
        out[i] = byte ^ first ^ 0xFF ^ second ^ k
        second = ((second + 1) * first) & 0xFF
    return bytes(out)


def lzss_a0_decompress(src: bytes, *, strict_hw: bool = False) -> bytes:
    """Decode VAG `0xA0` LZSS stream (1024-byte `0x20`-initialized window, MSB-first flags).

    When `strict_hw=True`, enforces the exact hardware bounds of the MFK3 0220 bootloader
    (`FUN_ram_0001b5d4`: `dist >= length` and `1 <= dist <= 0x3FF`), rejecting overlapping RLE refs
    that would trigger `NRC 0x72` (`generalProgrammingFailure`) during UDS `TransferData (0x36)`.
    """
    win = bytearray(b"\x20" * 1024)
    out = bytearray()
    nxt = 0
    p = 0
    flags = 0
    nbits = 0
    n = len(src)
    while True:
        if nbits == 0:
            if p >= n:
                break
            flags = src[p]
            nbits = 8
            p += 1
        bit = flags & 0x80
        flags = (flags << 1) & 0xFF
        nbits -= 1
        if not bit:
            if p >= n:
                break
            c = src[p]
            p += 1
            out.append(c)
            win[nxt] = c
            nxt = (nxt + 1) & 1023
        else:
            if p + 1 >= n:
                break
            b0 = src[p]
            b1 = src[p + 1]
            p += 2
            length = b0 >> 2
            dist = b1 | ((b0 & 3) << 8)
            if strict_hw and (dist < length or dist > 0x3FF or length < 3):
                raise ValueError(
                    f"Hardware-invalid LZSS A0 back-reference (dist={dist}, length={length}): "
                    f"0220 bootloader requires dist >= length and dist <= 0x3FF"
                )
            off = 1024 - dist
            for i in range(length):
                c = win[(nxt + off + i) & 1023]
                out.append(c)
                win[(nxt + i) & 1023] = c
            nxt = (nxt + length) & 1023
    return bytes(out)


def lzss_a0_compress(data: bytes, max_chain: int = 48) -> bytes:
    """Encode raw bytes into a hardware-safe VAG `0xA0` LZSS stream (`dist >= length`, `dist <= 0x3FF`)."""
    n = len(data)
    if n == 0:
        return b""
    head = [-1] * 65536
    prev = [-1] * n
    out = bytearray()
    flag_pos = 0
    flags = 0
    bit_idx = 0
    mv = memoryview(data)
    pos = 0

    while pos < n:
        if bit_idx == 0:
            flag_pos = len(out)
            out.append(0)
            flags = 0

        best_len = 2
        best_dist = 0
        max_len = min(63, n - pos)

        # Require pos >= 3 and limit cur_max <= pos - cur so dist >= length always holds (0220 FBL rule)
        if max_len >= 3 and pos >= 3:
            h = (data[pos] << 8) ^ (data[pos + 1] << 4) ^ data[pos + 2]
            cur = head[h]
            min_p = max(0, pos - 1023)
            b_end = data[pos + best_len]
            steps = 0
            while cur >= min_p and steps < max_chain:
                steps += 1
                dist = pos - cur
                cur_max = max_len if max_len <= dist else dist
                if (
                    cur_max > best_len
                    and data[cur + best_len] == b_end
                    and mv[cur : cur + best_len] == mv[pos : pos + best_len]
                ):
                    ml = best_len + 1
                    while ml < cur_max and data[cur + ml] == data[pos + ml]:
                        ml += 1
                    best_len = ml
                    best_dist = dist
                    if best_len == max_len:
                        break
                    b_end = data[pos + best_len]
                cur = prev[cur]

        if best_len >= 3:
            flags |= 0x80 >> bit_idx
            out.append((best_len << 2) | ((best_dist >> 8) & 3))
            out.append(best_dist & 0xFF)
            end_ins = min(pos + best_len, n - 2)
            for p_ins in range(pos, end_ins):
                hh = (data[p_ins] << 8) ^ (data[p_ins + 1] << 4) ^ data[p_ins + 2]
                prev[p_ins] = head[hh]
                head[hh] = p_ins
            pos += best_len
        else:
            out.append(data[pos])
            if pos + 2 < n:
                hh = (data[pos] << 8) ^ (data[pos + 1] << 4) ^ data[pos + 2]
                prev[pos] = head[hh]
                head[hh] = pos
            pos += 1

        bit_idx += 1
        if bit_idx == 8:
            out[flag_pos] = flags
            bit_idx = 0

    if bit_idx != 0:
        out[flag_pos] = flags

    encoded = bytes(out)
    if lzss_a0_decompress(encoded, strict_hw=True) != data:
        raise RuntimeError("Internal LZSS A0 hardware-strict round-trip verification failed!")
    return encoded


@dataclass
class OdxBlockEntry:
    short_name: str
    method: int                 # 0x00 or 0xA0
    raw_payload: bytes          # As stored in ODX / BF_*.bin (compressed if A0)
    uncompressed: bytes         # Decoded payload
    uncompressed_size: int
    crc32_expected: int | None
    signature_hex: str | None
    security_method: str | None
    datafile_name: str | None


def _xml_text(el: ET.Element, path: str) -> str | None:
    found = el.find(path)
    return None if found is None or found.text is None else found.text.strip()


def parse_odx_container(
    path: Path,
    *,
    frf_key_path: Path | None = None,
    only_blocks: set[str] | None = None,
    verify_crc: bool = True,
) -> tuple[str, dict[str, OdxBlockEntry], dict[str, str]]:
    """Parse `.odx`, `.odx-f`, `.pdx`, `.frf`, or ODIS `.xml` response into decoded `OdxBlockEntry` records."""
    raw_file = path.read_bytes()
    suffix = path.suffix.lower()
    base_dir = path.parent
    archive_files: dict[str, bytes] = {}

    def _load_zip_bytes(zbytes: bytes) -> str:
        with zipfile.ZipFile(io.BytesIO(zbytes)) as zf:
            for member in zf.namelist():
                if not member.endswith("/"):
                    archive_files[Path(member).name] = zf.read(member)
            odx_names = [n for n in zf.namelist() if n.lower().endswith((".odx", ".odx-f"))]
            if not odx_names:
                raise ValueError(f"No .odx/.odx-f found inside archive: {path}")
            return zf.read(odx_names[0]).decode("utf-8")

    if suffix == ".frf":
        dec = frf_decrypt(raw_file, get_frf_key(frf_key_path))
        xml_text = _load_zip_bytes(dec)
    elif suffix == ".pdx" or raw_file[:4] == b"PK\x03\x04":
        xml_text = _load_zip_bytes(raw_file)
    else:
        xml_text = raw_file.decode("utf-8")
        if "<COMPRESSED_DATA" in xml_text:
            root_resp = ET.fromstring(xml_text)
            b64 = _xml_text(root_resp, ".//COMPRESSED_DATA")
            if not b64:
                raise ValueError(f"Empty COMPRESSED_DATA in {path}")
            with tarfile.open(fileobj=io.BytesIO(base64.b64decode(b64))) as tf:
                frf_member = next(m for m in tf.getmembers() if m.name.lower().endswith(".frf"))
                frf_bytes = tf.extractfile(frf_member).read()  # type: ignore[union-attr]
            dec = frf_decrypt(frf_bytes, get_frf_key(frf_key_path))
            xml_text = _load_zip_bytes(dec)

    root = ET.fromstring(xml_text)
    flash_el = root.find("FLASH")
    meta: dict[str, str] = {}
    if flash_el is not None:
        sn = _xml_text(flash_el, "SHORT-NAME")
        if sn:
            meta["flash_short_name"] = sn
    part_no = _xml_text(root, ".//PARTNUMBER")
    if part_no:
        meta["part_number"] = part_no.strip()
    rev = _xml_text(root, ".//REVISION-LABEL")
    if rev:
        meta["revision"] = rev

    flashdata_map = {fd.get("ID"): fd for fd in root.iter("FLASHDATA")}
    session_crcs: dict[str, int] = {}
    session_sigs: dict[str, tuple[str | None, str | None]] = {}
    for sec in root.iter("SECURITY"):
        val_for = _xml_text(sec, "VALIDITY-FOR")
        if val_for:
            chk = _xml_text(sec, "FW-CHECKSUM")
            sig = _xml_text(sec, "FW-SIGNATURE")
            sm = _xml_text(sec, "SECURITY-METHOD")
            if chk:
                session_crcs[val_for] = int(chk, 16)
            session_sigs[val_for] = (sig, sm)

    blocks: dict[str, OdxBlockEntry] = {}
    for db in root.iter("DATABLOCK"):
        name = _xml_text(db, "SHORT-NAME") or ""
        if only_blocks is not None and name not in only_blocks:
            continue
        fd_ref = db.find("FLASHDATA-REF")
        if fd_ref is None:
            continue
        fd = flashdata_map[fd_ref.get("ID-REF")]
        method_hex = _xml_text(fd, "ENCRYPT-COMPRESS-METHOD") or "00"
        method = int(method_hex, 16)
        datafile_name: str | None = None
        if fd.get(XSI_TYPE_ATTR) == "EXTERN-FLASHDATA":
            datafile_name = _xml_text(fd, "DATAFILE")
            if not datafile_name:
                raise ValueError(f"{path.name}: {name} missing <DATAFILE>")
            if Path(datafile_name).name in archive_files:
                raw_payload = archive_files[Path(datafile_name).name]
            else:
                df_path = base_dir / datafile_name
                if not df_path.is_file():
                    raise FileNotFoundError(
                        tr(
                            f"Не найден внешний файл данных {df_path} для блока {name} (должен лежать рядом с {path.name})",
                            f"Missing external DATAFILE {df_path} for {name} (must sit next to {path.name})",
                        )
                    )
                raw_payload = df_path.read_bytes()
        else:
            hex_body = _xml_text(fd, "DATA") or ""
            raw_payload = bytes.fromhex("".join(hex_body.split()))

        seg = db.find("SEGMENTS/SEGMENT")
        usize = int(_xml_text(seg, "UNCOMPRESSED-SIZE") or len(raw_payload)) if seg is not None else len(raw_payload)
        own_crc_txt = _xml_text(db, ".//FW-CHECKSUM")
        expected_crc = int(own_crc_txt, 16) if own_crc_txt else session_crcs.get(name)
        own_sig = _xml_text(db, ".//FW-SIGNATURE")
        own_sm = _xml_text(db, ".//SECURITY-METHOD")
        if not own_sig and name in session_sigs:
            own_sig, own_sm = session_sigs[name]

        if method == 0x00:
            uncompressed = raw_payload
        elif method == 0xA0:
            uncompressed = lzss_a0_decompress(raw_payload)
        else:
            raise ValueError(f"{path.name}: unsupported ENCRYPT-COMPRESS-METHOD 0x{method:02X} in {name}")

        if len(uncompressed) != usize:
            raise ValueError(
                f"{path.name} ({name}): decompressed size {len(uncompressed)} != UNCOMPRESSED-SIZE {usize}"
            )
        got_crc = zlib.crc32(uncompressed) & 0xFFFFFFFF
        if verify_crc and expected_crc is not None and got_crc != expected_crc:
            raise ValueError(
                f"{path.name} ({name}): CRC-32 0x{got_crc:08X} != FW-CHECKSUM 0x{expected_crc:08X}"
            )

        blocks[name] = OdxBlockEntry(
            short_name=name,
            method=method,
            raw_payload=raw_payload,
            uncompressed=uncompressed,
            uncompressed_size=usize,
            crc32_expected=expected_crc,
            signature_hex=own_sig,
            security_method=own_sm,
            datafile_name=datafile_name,
        )

    return xml_text, blocks, meta


def _extract_xml_element_block(xml_text: str, tag: str, id_substring: str) -> str:
    pattern = re.compile(
        rf"([ \t]*<{tag}\b[^>]*\bID=\"[^\"]*{re.escape(id_substring)}[^\"]*\"[^>]*>.*?</{tag}>[ \t]*\r?\n?)",
        re.DOTALL,
    )
    m = pattern.search(xml_text)
    if not m:
        raise ValueError(f"Template ODX missing <{tag} ID=\"...{id_substring}...\">")
    return m.group(1)


def build_single_odx_xml(
    template_xml: str,
    keep_db_short_names: tuple[str, ...],
    db_to_fd_map: dict[str, str],
    block_overrides: dict[str, dict[str, object]],
    *,
    intern_flashdata: bool,
    container_ident: str | None = None,
    long_name_suffix: str | None = None,
) -> str:
    """Prune `template_xml` to `keep_db_short_names`, rewrite container IDs, and update block metadata."""

    def _filter_refs(m: re.Match[str]) -> str:
        inner = m.group(2)
        kept_lines = []
        for line in inner.splitlines(keepends=True):
            if "<DATABLOCK-REF" in line:
                if any(f'.{name}"' in line for name in keep_db_short_names):
                    kept_lines.append(line)
            elif line.strip():
                kept_lines.append(line)
        return m.group(1) + "".join(kept_lines) + m.group(3)

    out = re.sub(
        r"(<DATABLOCK-REFS>\r?\n?)(.*?)([ \t]*</DATABLOCK-REFS>)",
        _filter_refs,
        template_xml,
        count=1,
        flags=re.DOTALL,
    )

    db_chunks: list[str] = []
    for name in keep_db_short_names:
        chunk = _extract_xml_element_block(out, "DATABLOCK", f".{name}")
        ov = block_overrides.get(name)
        if ov:
            usize = int(ov["uncompressed_size"])  # type: ignore[arg-type]
            csize = ov.get("compressed_size")
            crc_hex = str(ov["crc32_hex"])
            sig_hex = ov.get("signature_hex")
            method_hex_ov = str(ov.get("method_hex", "")).upper()
            sec_method_ov = ov.get("security_method")

            chunk = re.sub(
                r"<UNCOMPRESSED-SIZE>\d+</UNCOMPRESSED-SIZE>",
                f"<UNCOMPRESSED-SIZE>{usize}</UNCOMPRESSED-SIZE>",
                chunk,
                count=1,
            )
            if csize is None:
                chunk = re.sub(r"[ \t]*<COMPRESSED-SIZE>\d+</COMPRESSED-SIZE>\r?\n?", "", chunk, count=1)
            else:
                if "<COMPRESSED-SIZE>" in chunk:
                    chunk = re.sub(
                        r"<COMPRESSED-SIZE>\d+</COMPRESSED-SIZE>",
                        f"<COMPRESSED-SIZE>{int(csize)}</COMPRESSED-SIZE>",  # type: ignore[arg-type]
                        chunk,
                        count=1,
                    )
                else:
                    chunk = re.sub(
                        r"([ \t]*)(<UNCOMPRESSED-SIZE>)",
                        rf"\1<COMPRESSED-SIZE>{int(csize)}</COMPRESSED-SIZE>\n\1\2",  # type: ignore[arg-type]
                        chunk,
                        count=1,
                    )

            if sec_method_ov:
                chunk = re.sub(
                    r"(<SECURITY-METHOD\b[^>]*>)[^<]+(</SECURITY-METHOD>)",
                    rf"\g<1>{sec_method_ov}\g<2>",
                    chunk,
                    count=1,
                )
            elif method_hex_ov == "00":
                # Factory uncompressed blocks (e.g. DB_03) use SIG_SHA1-RSA1024_S without _with_CRC32,
                # so VCP / VW-Flash send 131 bytes instead of 135 bytes (avoiding NRC 0x13 on 0220).
                chunk = re.sub(
                    r"(<SECURITY-METHOD\b[^>]*>[^<]*?)_with_CRC32([^<]*</SECURITY-METHOD>)",
                    r"\g<1>\g<2>",
                    chunk,
                    count=1,
                )

            chunk = re.sub(
                r"(<FW-CHECKSUM\b[^>]*>)[0-9A-Fa-f]+(</FW-CHECKSUM>)",
                rf"\g<1>{crc_hex}\g<2>",
                chunk,
                count=1,
            )
            if sig_hex:
                chunk = re.sub(
                    r"(<FW-SIGNATURE\b[^>]*>)[0-9A-Fa-f]+(</FW-SIGNATURE>)",
                    rf"\g<1>{sig_hex}\g<2>",
                    chunk,
                    count=1,
                )
        db_chunks.append(chunk)

    out = re.sub(
        r"(<DATABLOCKS>\r?\n?)(.*?)([ \t]*</DATABLOCKS>)",
        lambda m: m.group(1) + "".join(db_chunks) + m.group(3),
        out,
        count=1,
        flags=re.DOTALL,
    )

    fd_chunks: list[str] = []
    for name in keep_db_short_names:
        fd_name = db_to_fd_map[name]
        chunk = _extract_xml_element_block(out, "FLASHDATA", f".{fd_name}")
        ov = block_overrides[name]
        method_hex = str(ov["method_hex"])
        payload_bytes: bytes = ov["payload_bytes"]  # type: ignore[assignment]
        datafile_name = str(ov["datafile_name"])

        chunk = re.sub(
            r"(<ENCRYPT-COMPRESS-METHOD\b[^>]*>)[0-9A-Fa-f]+(</ENCRYPT-COMPRESS-METHOD>)",
            rf"\g<1>{method_hex}\g<2>",
            chunk,
            count=1,
        )
        if intern_flashdata:
            chunk = re.sub(r'xsi:type="EXTERN-FLASHDATA"', 'xsi:type="INTERN-FLASHDATA"', chunk, count=1)
            hex_upper = payload_bytes.hex().upper()
            if "<DATAFILE" in chunk:
                chunk = re.sub(
                    r"<DATAFILE\b[^>]*>.*?</DATAFILE>",
                    f"<DATA>{hex_upper}</DATA>",
                    chunk,
                    count=1,
                    flags=re.DOTALL,
                )
            else:
                chunk = re.sub(
                    r"<DATA>.*?</DATA>",
                    f"<DATA>{hex_upper}</DATA>",
                    chunk,
                    count=1,
                    flags=re.DOTALL,
                )
        else:
            chunk = re.sub(r'xsi:type="INTERN-FLASHDATA"', 'xsi:type="EXTERN-FLASHDATA"', chunk, count=1)
            if "<DATAFILE" in chunk:
                chunk = re.sub(
                    r"<DATAFILE\b[^>]*>.*?</DATAFILE>",
                    f'<DATAFILE LATEBOUND-DATAFILE="true">{datafile_name}</DATAFILE>',
                    chunk,
                    count=1,
                    flags=re.DOTALL,
                )
            else:
                chunk = re.sub(
                    r"<DATA>.*?</DATA>",
                    f'<DATAFILE LATEBOUND-DATAFILE="true">{datafile_name}</DATAFILE>',
                    chunk,
                    count=1,
                    flags=re.DOTALL,
                )
        fd_chunks.append(chunk)

    out = re.sub(
        r"(<FLASHDATAS>\r?\n?)(.*?)([ \t]*</FLASHDATAS>)",
        lambda m: m.group(1) + "".join(fd_chunks) + m.group(3),
        out,
        count=1,
        flags=re.DOTALL,
    )

    if container_ident:
        # Rewrite FL_<ident> / EMEM_<ident> / SES_<ident> / EMC_<ident> / SESD_<ident> across all IDs,
        # SHORT-NAMEs, ID-REFs, and SESSION-SNREFs so ODIS-E MCD-3D treats PART1 and PART2 as distinct containers.
        m_fl = re.search(r"<FLASH\b[^>]*>\s*<SHORT-NAME>FL_([^<\s]+)</SHORT-NAME>", out)
        if not m_fl:
            m_fl = re.search(r'<FLASH\b[^>]*\bID="FL_([^"]+)"', out)
        if m_fl:
            old_ident = m_fl.group(1)
            out = re.sub(
                rf"\b(FL|EMEM|SES|EMC|SESD)_{re.escape(old_ident)}\b",
                rf"\g<1>_{container_ident}",
                out,
            )
        if long_name_suffix:
            out = re.sub(
                r"(<LONG-NAME>[^<]*?)_MEAP\s*P\s*_V\d+\s*_S(</LONG-NAME>)",
                rf"\g<1>_{long_name_suffix}\g<2>",
                out,
            )

    return out


def build_catalog_index_xml(
    short_name_stem: str,
    odxf_filename: str,
    bf_filenames: list[str],
    *,
    company_id: str = "Compy_Valeo",
    company_name: str = "Valeo",
    department: str = "Front Camera",
    rev_label: str = "1423_V001",
) -> str:
    today = dt.date.today().isoformat()
    now_iso = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    ablocks = []
    for bf in bf_filenames:
        sn = bf.replace(".", "_")
        ablocks.append(
            f'    <ABLOCK UPD="UNDEFINED">\n'
            f"      <SHORT-NAME>{sn}</SHORT-NAME>\n"
            f"      <CATEGORY>PROGRAMMING-DATA</CATEGORY>\n"
            f"      <FILES>\n"
            f'        <FILE MIME-TYPE="application/octet-stream" CREATION-DATE="{today}">{bf}</FILE>\n'
            f"      </FILES>\n"
            f"    </ABLOCK>"
        )
    odx_sn = f"{short_name_stem}_odx"
    ablocks.append(
        f'    <ABLOCK UPD="UNDEFINED">\n'
        f"      <SHORT-NAME>{odx_sn}</SHORT-NAME>\n"
        f"      <CATEGORY>ODX-DATA</CATEGORY>\n"
        f"      <FILES>\n"
        f'        <FILE MIME-TYPE="text/xml" CREATION-DATE="{today}">{odxf_filename}</FILE>\n'
        f"      </FILES>\n"
        f"    </ABLOCK>"
    )
    joined = "\n".join(ablocks)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<CATALOG xsi:noNamespaceSchemaLocation="odx-cc.xsd" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
        f"  <SHORT-NAME>{short_name_stem}</SHORT-NAME>\n"
        "  <COMPANY-DATAS>\n"
        f'    <COMPANY-DATA ID="{company_id}">\n'
        f"      <SHORT-NAME>{company_id}</SHORT-NAME>\n"
        f"      <LONG-NAME>{company_name}</LONG-NAME>\n"
        "      <TEAM-MEMBERS>\n"
        f'        <TEAM-MEMBER ID="{company_id}.TM_">\n'
        "          <SHORT-NAME>TM_</SHORT-NAME>\n"
        "          <LONG-NAME/>\n"
        "          <DESC>\n"
        f"            <p>Mitarbeiter der Firma {company_name}</p>\n"
        "          </DESC>\n"
        "          <ROLES>\n"
        "            <ROLE>Contact person consultant</ROLE>\n"
        "          </ROLES>\n"
        f"          <DEPARTMENT>{department}</DEPARTMENT>\n"
        "          <ADDRESS>Bietigheim</ADDRESS>\n"
        "          <ZIP/>\n"
        "          <CITY/>\n"
        "          <PHONE/>\n"
        "          <FAX/>\n"
        "          <EMAIL/>\n"
        "        </TEAM-MEMBER>\n"
        "      </TEAM-MEMBERS>\n"
        "      <COMPANY-SPECIFIC-INFO>\n"
        "        <SDGS>\n"
        "          <SDG/>\n"
        "        </SDGS>\n"
        "      </COMPANY-SPECIFIC-INFO>\n"
        "    </COMPANY-DATA>\n"
        "  </COMPANY-DATAS>\n"
        "  <ADMIN-DATA>\n"
        "    <DOC-REVISIONS>\n"
        "      <DOC-REVISION>\n"
        f'        <TEAM-MEMBER-REF ID-REF="{company_id}.TM_"/>\n'
        f"        <REVISION-LABEL>{rev_label}</REVISION-LABEL>\n"
        "        <STATE>NEW</STATE>\n"
        f"        <DATE>{now_iso}</DATE>\n"
        "        <TOOL>AUDI-VW ODX-Generator V2.64</TOOL>\n"
        "      </DOC-REVISION>\n"
        "    </DOC-REVISIONS>\n"
        "  </ADMIN-DATA>\n"
        "  <ABLOCKS>\n"
        f"{joined}\n"
        "  </ABLOCKS>\n"
        "</CATALOG>\n"
    )
