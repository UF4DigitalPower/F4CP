/**
  ******************************************************************************
  * @file    uf4com_crc.h
  * @author  UF4
  * @date    26-6-13 下午1:40
  * @brief
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 UF4.
  * All rights reserved.
  *
  * This software is provided "as is", without warranty of any kind.
  *
  ******************************************************************************
  */
#ifndef UF4COM_CRC_H
#define UF4COM_CRC_H

#include <stdint.h>

#ifndef USE_HARDWARE_CRC
#define USE_HARDWARE_CRC 0
#endif

uint16_t UF4_CRC16(const uint8_t *data, uint16_t len);

#endif // UF4COM_CRC_H
