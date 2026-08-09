#include <stdio.h>
#include <string.h>

#include "uf4com.h"
#include "uf4com_id_table.h"

static uint16_t g_input_voltage = 13088u;
static uint16_t g_input_current = 320u;
static uint16_t g_output_voltage = 4660u;
static uint16_t g_set_voltage = 0u;
static uint16_t g_set_current = 0u;
static uint16_t g_fan_set = 0u;

static uint8_t g_tx_buffer[UF4_MAX_FRAME_LEN];
static uint16_t g_tx_len;

static uf4_id_t g_id_table[] =
{
    {UF4_ID_INPUT_VOLTAGE, &g_input_voltage, 0u},
    {UF4_ID_INPUT_CURRENT, &g_input_current, 0u},
    {UF4_ID_OUTPUT_VOLTAGE, &g_output_voltage, 0u},
    {UF4_ID_SET_VOLTAGE_LIMIT, &g_set_voltage, 1u},
    {UF4_ID_SET_CURRENT_LIMIT, &g_set_current, 1u},
    {UF4_ID_FAN_SET_VALUE, &g_fan_set, 1u},
};

static void CaptureTx(const uint8_t *data, uint16_t len, void *user)
{
    (void)user;

    if(len <= sizeof(g_tx_buffer))
    {
        memcpy(g_tx_buffer, data, len);
        g_tx_len = len;
    }
}

static int Expect(int condition, const char *message)
{
    if(condition)
    {
        return 0;
    }

    printf("FAIL: %s\n", message);
    return 1;
}

int main(void) {
    uint8_t request[UF4_MAX_FRAME_LEN];
    uint8_t read_data[] = {
        UF4_ID_INPUT_VOLTAGE, 0x00, 0x00,
        UF4_ID_INPUT_CURRENT, 0x00, 0x00,
        UF4_ID_OUTPUT_VOLTAGE, 0x00, 0x00,
    };
    int failures = 0;

    UF4_IDTableBind(g_id_table, sizeof(g_id_table) / sizeof(g_id_table[0]));
    UF4_Init(CaptureTx, NULL);

    const uint16_t request_len = UF4_BuildFrame(
        0x01,
        UF4_FLAG_ACK_REQ,
        UF4_CMD_READ_REQ,
        read_data,
        sizeof(read_data),
        request,
        sizeof(request));

    failures += Expect(request_len > 0u, "read request frame should build");
    failures += Expect(UF4_InputBuffer(request, request_len) == 1u, "read request should parse");
    failures += Expect(g_tx_len == 17u, "read response length should be 17 bytes");
    failures += Expect(g_tx_buffer[2] == 0x01u, "response seq should echo request seq");
    failures += Expect(g_tx_buffer[3] == UF4_FLAG_ACK_FRAME, "response should be ACK frame");
    failures += Expect(g_tx_buffer[4] == UF4_CMD_READ_RSP, "response command should be READ_RSP");
    failures += Expect(g_tx_buffer[6] == 0x0Au && g_tx_buffer[7] == 0x33u && g_tx_buffer[8] == 0x20u,
                       "input voltage should encode as 0x3320");

    if(failures == 0)
    {
        printf("UF4COM self-test passed.\n");
        return 0;
    }

    printf("UF4COM self-test failed: %d\n", failures);
    return 1;
}
