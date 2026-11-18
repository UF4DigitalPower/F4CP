"""Decode the firmware's read-only USBFS diagnostic pages over secure BLE."""
import struct


def format_usb_diagnostics(pages):
    if len(pages) not in (3, 6, 9) or any(
            len(raw) != 20 or raw[:4] != b"U4\x01" + bytes([page])
            for page, raw in enumerate(pages)):
        raise ValueError("USB 诊断数据无效，请确认设备运行 0.1.2 或更新的兼容固件")
    registers, counters, request = pages[:3]
    state, ctrl, port, ien, flags, status, mis, tx, rx, tx_len, rx_len, pending = registers[4:16]
    cfgr = struct.unpack_from("<I", registers, 16)[0]
    resets, setups, ins, outs = struct.unpack_from("<4I", counters, 4)
    stalls, irqs = struct.unpack_from("<2I", request, 12)
    setup = request[4:12].hex(" ").upper()
    lines = [
        f"USB诊断：初始化={bool(state & 1)} 配置={bool(state & 2)} 挂起={bool(state & 4)} "
        f"IRQ使能={bool(state & 8)} IRQ待处理={bool(state & 16)} USB时钟使能={bool(state & 32)}",
        f"USB计数：IRQ={irqs} RESET={resets} SETUP={setups} IN={ins} OUT={outs} STALL={stalls}",
        f"USB寄存器：CTRL={ctrl:02X} PORT={port:02X} IEN={ien:02X} MIS={mis:02X} "
        f"INT_FG={pending:02X} 最近IRQ={flags:02X}/{status:02X} RX_LEN={rx_len} "
        f"EP0 TX={tx:02X}/{tx_len} RX={rx:02X} RCC_CFGR0={cfgr:08X}",
        f"USB最近SETUP：{setup}" + ("（尚未收到）" if not setups else ""),
    ]
    if not state & 1 or not state & 8 or not state & 32:
        lines.append("定位提示：USB 初始化、时钟或中断使能不完整，请保存以上诊断数据。")
    elif not irqs:
        lines.append("定位提示：尚无 USB 中断；保持 BLE 连接，拔插 USB 数据线后再次读取，比较计数。")
    elif not setups:
        lines.append("定位提示：尚未收到有效 SETUP，需对照 BLE 启动前快照检查应用 USB 初始化与时钟。")
    elif not state & 2:
        lines.append("定位提示：已收到 SETUP，但尚未配置；请保存最近请求及 IN/OUT/STALL 计数。")
    else:
        lines.append("定位提示：设备已接受 SET_CONFIGURATION；请继续核对 Windows 的 HID/WinUSB 接口。")
    if len(pages) >= 6:
        frozen, counts, previous = pages[3:6]
        before = frozen[4]
        if not before & 0x80:
            lines.append("BLE启动前快照：尚未捕获，无法进行启动对照。")
        else:
            br, bs, bi, bo = struct.unpack_from("<4I", counts, 4)
            bst, birq = struct.unpack_from("<2I", previous, 12)
            lines.extend([
                f"BLE启动前（USB独立运行约3秒）：配置={bool(before & 2)} 挂起={bool(before & 4)} "
                f"IRQ={birq} RESET={br} SETUP={bs} IN={bi} OUT={bo} STALL={bst}",
                f"BLE启动前寄存器：CTRL={frozen[5]:02X} PORT={frozen[6]:02X} IEN={frozen[7]:02X} "
                f"MIS={frozen[10]:02X} RCC_CFGR0={struct.unpack_from('<I', frozen, 16)[0]:08X}",
                "BLE启动前最近SETUP：" + previous[4:12].hex(" ").upper(),
            ])
            if before & 2:
                lines.append("启动对照：BLE 启动前已配置；请对照当前状态判断后续是否失去配置。")
            elif bs:
                lines.append("启动对照：BLE 启动前已收到 SETUP，但窗口内未完成配置。")
            elif br:
                lines.append("启动对照：BLE 启动前已有复位但无有效 SETUP，问题在该窗口内已出现。")
            else:
                lines.append("启动对照：窗口内未观察到复位或 SETUP；该快照不足以判断 BLE 的影响。")
    if len(pages) == 9:
        transfer, dma, first = pages[6:9]
        total, unexpected, malformed, modes = struct.unpack_from("<4I", transfer, 4)
        expected, ep0, ep1, ep2 = struct.unpack_from("<4I", dma, 4)
        lines.extend([
            f"USB接收分类：TRANSFER标志次数={total} 非预期端点={unexpected} EP0 SETUP长度异常={malformed} "
            f"端点模式={modes:08X}",
            f"USB DMA：EP0期望={expected:08X} 读回={ep0:08X} 一致={expected == ep0} "
            f"EP1={ep1:08X} EP2={ep2:08X}",
        ])
        if total:
            fg, st, length = struct.unpack_from("<BBH", first, 4)
            phase = "窗口结束后" if first[16] else "USB独立窗口内"
            lines.append(f"USB首个TRANSFER（{phase}）：IRQ={fg:02X}/{st:02X} "
                         f"EP={st & 15} TOKEN={(st >> 4) & 3} RX_LEN={length}")
            if not fg & 1 and st & 0x3F == 0x30 and length == 8:
                lines.append("首个EP0 SETUP数据：" + first[8:16].hex(" ").upper())
        else:
            lines.append("USB首个TRANSFER：尚未记录。")
    lines.append("当前页为连续读取的即时快照；计数从本次应用 USB 初始化开始累计，"
                 "BLE启动前快照冻结后不随 USB 复位改变。")
    return "\n".join(lines)
