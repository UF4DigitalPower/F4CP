"""Windows PIN pairing for the board's DISPLAY_ONLY / MITM configuration."""
import asyncio

from bleak.backends.winrt.client import BleakClientWinRT
from winrt.windows.devices.enumeration import (
    DeviceInformation, DevicePairingKinds, DevicePairingProtectionLevel,
    DevicePairingResultStatus,
)

PASSKEY = "005213"


async def pair_with_passkey(pairing):
    if pairing.is_paired:
        return
    if not pairing.can_pair:
        raise RuntimeError("Windows 暂时不能配对此设备，请重新扫描后重试")

    def requested(sender, args):
        if args.pairing_kind == DevicePairingKinds.PROVIDE_PIN:
            args.accept_with_pin(PASSKEY)

    custom = pairing.custom
    token = custom.add_pairing_requested(requested)
    try:
        async with asyncio.timeout(60):
            # Do not fall back to unauthenticated Just Works pairing: all UF4
            # business characteristics require an authenticated encrypted link.
            result = await custom.pair_with_protection_level_async(
                DevicePairingKinds.PROVIDE_PIN,
                DevicePairingProtectionLevel.ENCRYPTION_AND_AUTHENTICATION,
            )
    except TimeoutError as exc:
        raise RuntimeError("Windows 口令配对超时，请重新扫描或点击“重新配对”") from exc
    finally:
        custom.remove_pairing_requested(token)

    if result.status not in (DevicePairingResultStatus.PAIRED, DevicePairingResultStatus.ALREADY_PAIRED):
        raise RuntimeError(f"Windows 口令配对失败：{result.status.name}，请点击“重新配对”后重试")


class Uf4WinRTClient(BleakClientWinRT):
    async def pair(self, **kwargs):
        # Bleak's default WinRT backend accepts CONFIRM_ONLY. The board instead
        # uses a fixed displayed passkey, so support the Windows PROVIDE_PIN event.
        if self._requester is None:
            raise RuntimeError("Windows 蓝牙设备尚未就绪")
        information = await DeviceInformation.create_from_id_async(self._requester.device_information.id)
        await pair_with_passkey(information.pairing)
