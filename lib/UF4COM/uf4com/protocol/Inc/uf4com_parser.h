/**
  ******************************************************************************
  * @file    uf4com_parser.h
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
#ifndef UF4COM_PARSER_H
#define UF4COM_PARSER_H

#include "uf4com.h"

void UF4_ParserInit(uf4_parser_t *parser);
uint8_t UF4_ParserInput(uf4_parser_t *parser, uint8_t byte, uf4_frame_t *out_frame);

#endif // UF4COM_PARSER_H
