/**
  ******************************************************************************
  * @file    uf4com.c
  * @author  UF4
  * @date    26-6-13 下午1:39
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
#include "uf4com.h"
#include "uf4com_cmd.h"
#include "uf4com_crc.h"
#include "uf4com_parser.h"

static uf4_tx_fn_t s_tx;
static void *s_tx_user;
static uf4_write_apply_fn_t s_write_apply;
static void *s_write_apply_user;
static uf4_parser_t s_parser;

void UF4_Init(uf4_tx_fn_t tx, void *user)
{
  s_tx = tx;
  s_tx_user = user;
  UF4_ParserInit(&s_parser);
}

void UF4_SetWriteApplyCallback(uf4_write_apply_fn_t cb, void *user)
{
  s_write_apply = cb;
  s_write_apply_user = user;
}

void UF4_NotifyWriteApplied(void)
{
  if(s_write_apply != NULL)
  {
    s_write_apply(s_write_apply_user);
  }
}

void UF4_Process(void)
{
  UF4_StreamTask();
}

uint16_t UF4_BuildFrame(uint8_t seq,
                        uint8_t flags,
                        uint8_t cmd,
                        const uint8_t *data,
                        uint8_t len,
                        uint8_t *out,
                        uint16_t out_size)
{
  const uint16_t frame_len = (uint16_t)(2u + 4u + len + 2u);

  if(out == NULL || out_size < frame_len || (data == NULL && len > 0u))
  {
    return 0;
  }

  out[0] = UF4_SOF1;
  out[1] = UF4_SOF2;
  out[2] = seq;
  out[3] = flags;
  out[4] = cmd;
  out[5] = len;

  for(uint8_t i = 0; i < len; i++)
  {
    out[6u + i] = data[i];
  }

  const uint16_t crc = UF4_CRC16(&out[2], (uint16_t)(4u + len));
  out[6u + len] = (uint8_t)(crc & 0xFFu);
  out[7u + len] = (uint8_t)(crc >> 8);

  return frame_len;
}

uint8_t UF4_SendFrame(uint8_t seq,
                      uint8_t flags,
                      uint8_t cmd,
                      const uint8_t *data,
                      uint8_t len)
{
  uint8_t buffer[UF4_MAX_FRAME_LEN];
  const uint16_t frame_len = UF4_BuildFrame(seq, flags, cmd, data, len, buffer, sizeof(buffer));

  if(frame_len == 0u || s_tx == NULL)
  {
    return 0u;
  }

  s_tx(buffer, frame_len, s_tx_user);
  return 1u;
}

uint8_t UF4_InputByte(uint8_t byte)
{
  uf4_frame_t frame;

  if(UF4_ParserInput(&s_parser, byte, &frame) == 0u)
  {
    return 0u;
  }

  UF4_Dispatch(&frame);
  return 1u;
}

uint8_t UF4_InputBuffer(const uint8_t *data, uint16_t len)
{
  uint8_t frames = 0u;

  if(data == NULL)
  {
    return 0u;
  }

  for(uint16_t i = 0; i < len; i++)
  {
    frames += UF4_InputByte(data[i]);
  }

  return frames;
}
