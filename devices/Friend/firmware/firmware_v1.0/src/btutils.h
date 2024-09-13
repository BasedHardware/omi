#include <zephyr/bluetooth/gatt.h>

static const char *phy2str(uint8_t phy)
{
    switch (phy) {
    case 0: return "No packets";
    case BT_GAP_LE_PHY_1M: return "LE 1M";
    case BT_GAP_LE_PHY_2M: return "LE 2M";
    case BT_GAP_LE_PHY_CODED: return "LE Coded";
    default: return "Unknown";
    }
}