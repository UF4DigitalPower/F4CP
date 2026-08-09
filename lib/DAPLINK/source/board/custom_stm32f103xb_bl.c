/**
 * @file    custom_stm32f103xb_bl.c
 * @brief   board ID and meta-data for a custom STM32F103XB DAPLink bootloader build
 *
 * DAPLink Interface Firmware
 * Copyright (c) 2009-2019, ARM Limited, All Rights Reserved
 * SPDX-License-Identifier: Apache-2.0
 */

#include <stdbool.h>

#include "target_config.h"
#include "target_board.h"
#include "target_family.h"

static const sector_info_t sectors_info[] = {
    {0x08000000 + KB(48), 0x400},
};

target_cfg_t target_device = {
    .version                    = kTargetConfigVersion,
    .sectors_info               = sectors_info,
    .sector_info_length         = (sizeof(sectors_info)) / (sizeof(sector_info_t)),
    .flash_regions[0].start     = 0x08000000 + KB(48),
    .flash_regions[0].end       = 0x08000000 + KB(128),
    .flash_regions[0].flags     = kRegionIsDefault,
    .ram_regions[0].start       = 0x20000000,
    .ram_regions[0].end         = 0x20005000,
    /* .flash_algo not needed for bootloader */
};

const target_family_descriptor_t *g_target_family = NULL;

const board_info_t g_board_info = {
    .info_version = kBoardInfoVersion,
    .board_id = "0000",
    .daplink_url_name = "UF4BL320HTM",
    .daplink_drive_name = "UF4BLPOWER",
    .daplink_target_url = "https://daplink.io",
    .target_cfg = &target_device,
};

bool reset_button_pressed(void)
{
    // This custom UF4 design uses the sampled reset input as the target nRESET line.
    // During target power collapse/ramp that line can be held low, which makes the
    // generic STM32F103 bootloader falsely stay in maintenance mode on every cold boot.
    // For this board only enter bootloader when the interface image is invalid or the
    // running interface explicitly requested hold-in-bootloader before reset.
    return false;
}

