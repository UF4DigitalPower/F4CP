/**
  ******************************************************************************
  * @file    uf4com.h
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
#ifndef UF4COM_H
#define UF4COM_H

#include <stddef.h>
#include <stdint.h>

#define UF4_SOF1                  0xAA
#define UF4_SOF2                  0x55
#define UF4_MAX_DATA_LEN          255u
#define UF4_MAX_FRAME_LEN         (2u + 1u + 1u + 1u + 1u + UF4_MAX_DATA_LEN + 2u)

#define UF4_CMD_READ_REQ          0x01
#define UF4_CMD_READ_RSP          0x81

#define UF4_CMD_WRITE_REQ         0x02
#define UF4_CMD_WRITE_RSP         0x82

#define UF4_CMD_STREAM_START_REQ  0x10
#define UF4_CMD_STREAM_START_RSP  0x90

#define UF4_CMD_STREAM_STOP_REQ   0x11
#define UF4_CMD_STREAM_STOP_RSP   0x91

#define UF4_CMD_STREAM_DATA       0x15

// FLAGS
#define UF4_FLAG_ACK_REQ    0x01
#define UF4_FLAG_ACK_FRAME  0x02
#define UF4_FLAG_ERROR      0x04

// DATA ID
#define UF4_ID_INPUT_VOLTAGE                    0x0A
#define UF4_ID_INPUT_CURRENT                    0x0B
#define UF4_ID_OUTPUT_VOLTAGE                   0x0C
#define UF4_ID_OUTPUT_CURRENT                   0x0D
#define UF4_ID_CORE_TEMPERATURE                 0x0E
#define UF4_ID_TEMP1_TEMPERATURE                0x0F
#define UF4_ID_TEMP2_TEMPERATURE                0x10
#define UF4_ID_SET_VOLTAGE_LIMIT                0x11
#define UF4_ID_SET_CURRENT_LIMIT                0x12
#define UF4_ID_CC_CV_MODE                       0x14
#define UF4_ID_POWER_STATE                      0x15
#define UF4_ID_FAULT_STATE                      0x16
#define UF4_ID_STATE_MACHINE_FLAG_BITS          0x17
#define UF4_ID_STATE_MACHINE_STATE              0x18
#define UF4_ID_INPUT_VOLTAGE_RAW                0x19
#define UF4_ID_INPUT_CURRENT_RAW                0x1A
#define UF4_ID_OUTPUT_VOLTAGE_RAW               0x1B
#define UF4_ID_OUTPUT_CURRENT_RAW               0x1C
#define UF4_ID_OTP_VALUE                        0x1D
#define UF4_ID_OTP_SET_VALUE                    0x1E
#define UF4_ID_OVP_VALUE                        0x1F
#define UF4_ID_OVP_SET_VALUE                    0x20
#define UF4_ID_OCP_VALUE                        0x21
#define UF4_ID_OCP_SET_VALUE                    0x22
#define UF4_ID_DUTY_CMD                         0x23
#define UF4_ID_PWM_A_COMPARE                    0x24
#define UF4_ID_PWM_D_COMPARE                    0x25
#define UF4_ID_FAN_SPEED                        0x26
#define UF4_ID_FAN_SET_VALUE                    0x27
#define UF4_ID_LOOP_CURRENT_FEEDBACK            0x29
#define UF4_ID_LOOP_CURRENT_REFERENCE           0x2A
#define UF4_ID_VOLTAGE_LOOP_CURRENT_REFERENCE   0x2B

typedef enum
{
  UF4_OK = 0x0000,
  UF4_ERR_INVALID_ID = 0x0001,
  UF4_ERR_INVALID_CMD = 0x0002,
  UF4_ERR_CRC = 0x0003,
  UF4_ERR_INVALID_LEN = 0x0004,
  UF4_ERR_WRITE_PROTECT = 0x0005,
  UF4_ERR_OUT_OF_RANGE = 0x0006,
  UF4_ERR_DEVICE_BUSY = 0x0007,
  UF4_ERR_INTERNAL = 0x0008
} uf4_error_t;

typedef struct
{
  uint8_t seq;
  uint8_t flags;
  uint8_t cmd;
  uint8_t len;
  uint8_t data[UF4_MAX_DATA_LEN];
} uf4_frame_t;

typedef struct
{
  uint8_t id;
  uint16_t value;

} tv_t;

typedef enum
{
  WAIT_SOF1,
  WAIT_SOF2,

  WAIT_SEQ,
  WAIT_FLAGS,
  WAIT_CMD,
  WAIT_LEN,

  WAIT_DATA,

  WAIT_CRC_L,
  WAIT_CRC_H

} uf4_state_t;

typedef struct
{
  uf4_state_t state;

  uf4_frame_t frame;

  uint16_t data_index;

  uint16_t crc_rx;

} uf4_parser_t;

typedef void (*uf4_tx_fn_t)(const uint8_t *data, uint16_t len, void *user);
typedef void (*uf4_write_apply_fn_t)(void *user);

void UF4_Init(uf4_tx_fn_t tx, void *user);
void UF4_SetWriteApplyCallback(uf4_write_apply_fn_t cb, void *user);
void UF4_Process(void);
uint16_t UF4_BuildFrame(uint8_t seq,
                        uint8_t flags,
                        uint8_t cmd,
                        const uint8_t *data,
                        uint8_t len,
                        uint8_t *out,
                        uint16_t out_size);
uint8_t UF4_SendFrame(uint8_t seq,
                      uint8_t flags,
                      uint8_t cmd,
                      const uint8_t *data,
                      uint8_t len);
uint8_t UF4_InputByte(uint8_t byte);
uint8_t UF4_InputBuffer(const uint8_t *data, uint16_t len);

#endif // UF4COM_H
