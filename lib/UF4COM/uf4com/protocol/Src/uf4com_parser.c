/**
  ******************************************************************************
  * @file    uf4com_parser.c
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
#include "uf4com_parser.h"
#include "uf4com_crc.h"

void UF4_ParserInit(uf4_parser_t *parser)
{
  if(parser == NULL)
  {
    return;
  }

  parser->state = WAIT_SOF1;
  parser->data_index = 0u;
  parser->crc_rx = 0u;
  parser->frame.seq = 0u;
  parser->frame.flags = 0u;
  parser->frame.cmd = 0u;
  parser->frame.len = 0u;
}

uint8_t UF4_ParserInput(uf4_parser_t *parser, uint8_t byte, uf4_frame_t *out_frame)
{
  if(parser == NULL || out_frame == NULL)
  {
    return 0u;
  }

  switch(parser->state)
  {
    case WAIT_SOF1:
      parser->state = (byte == UF4_SOF1) ? WAIT_SOF2 : WAIT_SOF1;
      break;

    case WAIT_SOF2:
      parser->state = (byte == UF4_SOF2) ? WAIT_SEQ : WAIT_SOF1;
      break;

    case WAIT_SEQ:
      parser->frame.seq = byte;
      parser->state = WAIT_FLAGS;
      break;

    case WAIT_FLAGS:
      parser->frame.flags = byte;
      parser->state = WAIT_CMD;
      break;

    case WAIT_CMD:
      parser->frame.cmd = byte;
      parser->state = WAIT_LEN;
      break;

    case WAIT_LEN:
      parser->frame.len = byte;
      parser->data_index = 0u;
      parser->state = (byte == 0u) ? WAIT_CRC_L : WAIT_DATA;
      break;

    case WAIT_DATA:
      parser->frame.data[parser->data_index++] = byte;
      if(parser->data_index >= parser->frame.len)
      {
        parser->state = WAIT_CRC_L;
      }
      break;

    case WAIT_CRC_L:
      parser->crc_rx = byte;
      parser->state = WAIT_CRC_H;
      break;

    case WAIT_CRC_H:
    {
      parser->crc_rx |= (uint16_t)byte << 8;

      uint8_t crc_data[4u + UF4_MAX_DATA_LEN];
      crc_data[0] = parser->frame.seq;
      crc_data[1] = parser->frame.flags;
      crc_data[2] = parser->frame.cmd;
      crc_data[3] = parser->frame.len;

      for(uint8_t i = 0; i < parser->frame.len; i++)
      {
        crc_data[4u + i] = parser->frame.data[i];
      }

      const uint16_t crc_calc = UF4_CRC16(crc_data, (uint16_t)(4u + parser->frame.len));
      const uint8_t valid = (crc_calc == parser->crc_rx);

      if(valid != 0u)
      {
        *out_frame = parser->frame;
      }

      UF4_ParserInit(parser);
      return valid;
    }

    default:
      UF4_ParserInit(parser);
      break;
  }

  return 0u;
}
