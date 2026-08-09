cmake_minimum_required(VERSION 3.28)

project(UF4COM C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

if(CMAKE_C_COMPILER_ID STREQUAL "GNU")
    add_compile_options(-g0 -Wall -Wextra -Wpedantic)
endif()

file(GLOB_RECURSE SRC_FILES CONFIGURE_DEPENDS
        uf4com/protocol/Src/*.c
        uf4com/register/Src/*.c
        uf4com/transport/uf4com_uart/Src/*.c
)

add_executable(UF4COM ${SRC_FILES} main.c)

target_include_directories(UF4COM PRIVATE
        uf4com/protocol/Inc
        uf4com/register/Inc
        uf4com/transport/uf4com_uart/Inc
)
