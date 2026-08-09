/**
  ******************************************************************************
  * @file    uf4com_id_table.c
  * @author  UF4
  * @date    26-6-13 下午1:42
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
#include "uf4com_usrt.h"
#include "uf4com.h"

void UF4_UART_RxByte(uint8_t byte)
{
  (void)UF4_InputByte(byte);
}
