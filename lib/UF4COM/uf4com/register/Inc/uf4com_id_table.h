/**
  ******************************************************************************
  * @file    uf4com_usrt.h
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
#ifndef UF4COM_ID_TABLE_H
#define UF4COM_ID_TABLE_H

#include <stddef.h>
#include <stdint.h>

typedef struct
{
  uint8_t id;
  uint16_t *ptr;
  uint8_t rw;
} uf4_id_t;

void UF4_IDTableBind(uf4_id_t *table, size_t count);
uf4_id_t *UF4_FindID(uint8_t id);
size_t UF4_IDTableCount(void);
size_t UF4_GetAllIDs(uint8_t *out_ids, size_t max_count);

#endif // UF4COM_ID_TABLE_H
