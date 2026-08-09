/**
 * @file    custom_f103rb.c
 * @brief   board information for a custom-branded STM32F103RB debug probe build
 *
 * DAPLink Interface Firmware
 * Copyright (c) 2009-2019, ARM Limited, All Rights Reserved
 * SPDX-License-Identifier: Apache-2.0
 */

#include "target_family.h"
#include "target_board.h"

const board_info_t g_board_info = {
    .info_version = kBoardInfoVersion,
    .board_id = "UF40",
    .family_id = kStub_HWReset_FamilyID,
    .target_cfg = &target_device,
    .daplink_url_name = "UF40320 HTM",
    .daplink_drive_name = "UF4PWR0320 ",
    .daplink_target_url = "https://daplink.io",
    .board_vendor = "UF4OVER",
    .board_name = "UF4DigitalPower",
};
