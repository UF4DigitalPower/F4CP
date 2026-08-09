/**
  ******************************************************************************
  * @file    uf4com_cmd.h
  * @author  UF4
  * @date    26-6-13 下午1:41
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
#ifndef UF4COM_CMD_H
#define UF4COM_CMD_H

#include "uf4com.h"

void UF4_Dispatch(uf4_frame_t *frame);
void UF4_StreamTask(void);
void UF4_NotifyWriteApplied(void);

#endif // UF4COM_CMD_H
