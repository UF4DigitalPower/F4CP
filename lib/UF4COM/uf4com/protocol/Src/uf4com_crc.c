/**
  ******************************************************************************
  * @file    uf4com_crc.c
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
#include "uf4com_crc.h"
#include "stdint.h"

#if USE_HARDWARE_CRC

#include "crc.h"
extern CRC_HandleTypeDef hcrc;

uint16_t UF4_CRC16(uint8_t *buf,uint32_t len)
{
    CRC->CR |= CRC_CR_RESET;
    while(len--)
    {*(volatile uint8_t*)&CRC->DR = *buf++;}
    return (uint16_t)CRC->DR;
}
uint16_t UF4_CRC16(const uint8_t *buf, uint16_t len)
{
    return UF4_CRC16((uint8_t*)buf,len);
}

#else

uint16_t UF4_CRC16(const uint8_t *data,uint16_t len)
{
    uint16_t crc = 0xFFFF;
    while(len--)
    {
        crc ^= ((uint16_t)(*data++)) << 8;
        for(uint8_t i = 0; i < 8; i++){
            if(crc & 0x8000)
            {
                crc = (crc << 1) ^ 0x1021;
            }
            else
            {
                crc <<= 1;
            }
        }
    }

    return crc;
}
#endif
