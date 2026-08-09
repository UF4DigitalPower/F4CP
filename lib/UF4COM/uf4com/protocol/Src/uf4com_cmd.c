/**
  ******************************************************************************
  * @file    uf4com_cmd.c
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
#include "uf4com_cmd.h"
#include "uf4com_id_table.h"

#define UF4_TV_SIZE 3u
#define UF4_MAX_STREAM_IDS 64u

uint8_t g_stream_enable;
uint8_t g_stream_ids[UF4_MAX_STREAM_IDS];
uint8_t g_stream_count;

static void UF4_HandleRead(uf4_frame_t *frame);
static void UF4_HandleWrite(uf4_frame_t *frame);
static void UF4_HandleStreamStart(uf4_frame_t *frame);
static void UF4_HandleStreamStop(uf4_frame_t *frame);
static void UF4_SendError(const uf4_frame_t *frame, uint8_t rsp_cmd, uf4_error_t error);


void UF4_Dispatch(uf4_frame_t *frame)
{
  switch(frame->cmd)
  {
    case UF4_CMD_READ_REQ:
      UF4_HandleRead(frame);
    break;

    case UF4_CMD_WRITE_REQ:
      UF4_HandleWrite(frame);
    break;

    case UF4_CMD_STREAM_START_REQ:
      UF4_HandleStreamStart(frame);
    break;

    case UF4_CMD_STREAM_STOP_REQ:
      UF4_HandleStreamStop(frame);
    break;

    default:
      UF4_SendError(frame, frame->cmd, UF4_ERR_INVALID_CMD);
      break;
  }
}


static void UF4_HandleRead(
    uf4_frame_t *frame)
{
  uint8_t rsp[255];
  uint8_t rsp_len = 0;

  if((frame->len % UF4_TV_SIZE) != 0u)
  {
    UF4_SendError(frame, UF4_CMD_READ_RSP, UF4_ERR_INVALID_LEN);
    return;
  }

  for(uint8_t i = 0u; i < frame->len; i += UF4_TV_SIZE)
  {
    uint8_t id =
        frame->data[i];

    uf4_id_t *item =
        UF4_FindID(id);

    if(item == NULL)
    {
      UF4_SendError(frame, UF4_CMD_READ_RSP, UF4_ERR_INVALID_ID);
      return;
    }

    uint16_t value =
        *(item->ptr);

    rsp[rsp_len++] = id;
    rsp[rsp_len++] = value >> 8;
    rsp[rsp_len++] = value & 0xFF;
  }

  UF4_SendFrame(
      frame->seq,
      UF4_FLAG_ACK_FRAME,
      UF4_CMD_READ_RSP,
      rsp,
      rsp_len);
}


static void UF4_HandleWrite(
    uf4_frame_t *frame)
{
  if((frame->len % UF4_TV_SIZE) != 0u)
  {
    UF4_SendError(frame, UF4_CMD_WRITE_RSP, UF4_ERR_INVALID_LEN);
    return;
  }

  for(uint8_t i = 0u; i < frame->len; i += UF4_TV_SIZE)
  {
    uint8_t id =
        frame->data[i];

    uint16_t value =
        ((uint16_t)frame->data[i+1] << 8)
        | frame->data[i+2];

    uf4_id_t *item =
        UF4_FindID(id);

    if(item == NULL)
    {
      UF4_SendError(frame, UF4_CMD_WRITE_RSP, UF4_ERR_INVALID_ID);
      return;
    }

    if(item->rw == 0)
    {
      UF4_SendError(frame, UF4_CMD_WRITE_RSP, UF4_ERR_WRITE_PROTECT);
      return;
    }

    *(item->ptr) = value;
  }

  UF4_NotifyWriteApplied();

  UF4_SendFrame(
      frame->seq,
      UF4_FLAG_ACK_FRAME,
      UF4_CMD_WRITE_RSP,
      frame->data,
      frame->len);
}



static void UF4_HandleStreamStart(
    uf4_frame_t *frame)
{
    uint8_t req_count = frame->len / UF4_TV_SIZE;

    if((frame->len % UF4_TV_SIZE) != 0u || req_count > UF4_MAX_STREAM_IDS)
    {
        UF4_SendError(frame, UF4_CMD_STREAM_START_RSP, UF4_ERR_INVALID_LEN);
        return;
    }

    g_stream_enable = 1;
    g_stream_count = 0;

    if(frame->len == 0u)
    {
        /* 空 payload = 请求全量流，把 ID 表里所有 ID 都加进来 */
        g_stream_count = (uint8_t)UF4_GetAllIDs(g_stream_ids, UF4_MAX_STREAM_IDS);
    }
    else
    {
        for(uint8_t i = 0u; i < frame->len; i += UF4_TV_SIZE)
        {
            if(UF4_FindID(frame->data[i]) == NULL)
            {
                g_stream_enable = 0u;
                g_stream_count = 0u;
                UF4_SendError(frame, UF4_CMD_STREAM_START_RSP, UF4_ERR_INVALID_ID);
                return;
            }

            g_stream_ids[g_stream_count++] = frame->data[i];
        }
    }

    UF4_SendFrame(
        frame->seq,
        UF4_FLAG_ACK_FRAME,
        UF4_CMD_STREAM_START_RSP,
        NULL,
        0);
}

static void UF4_HandleStreamStop(
    uf4_frame_t *frame)
{
    g_stream_enable = 0;

    g_stream_count = 0;

    UF4_SendFrame(
        frame->seq,
        UF4_FLAG_ACK_FRAME,
        UF4_CMD_STREAM_STOP_RSP,
        NULL,
        0);
}

void UF4_StreamTask(void)
{
    if(g_stream_enable == 0)
        return;

    uint8_t data[255];

    uint8_t len = 0;

    for(uint8_t i = 0u; i < g_stream_count; i++)
    {
        uint8_t id =
            g_stream_ids[i];

        uf4_id_t *item =
            UF4_FindID(id);

        if(item == NULL)
            continue;

        uint16_t value =
            *(item->ptr);

        data[len++] = id;
        data[len++] = value >> 8;
        data[len++] = value & 0xFFu;
    }

    UF4_SendFrame(
        0,
        0,
        UF4_CMD_STREAM_DATA,
        data,
        len);
}

static void UF4_SendError(const uf4_frame_t *frame, uint8_t rsp_cmd, uf4_error_t error)
{
  uint8_t data[3];

  data[0] = 0xFFu;
  data[1] = (uint8_t)((uint16_t)error >> 8);
  data[2] = (uint8_t)((uint16_t)error & 0xFFu);

  UF4_SendFrame(
      frame->seq,
      UF4_FLAG_ACK_FRAME | UF4_FLAG_ERROR,
      rsp_cmd,
      data,
      sizeof(data));
}
