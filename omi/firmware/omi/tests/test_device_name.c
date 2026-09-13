/*
 * Host-side tests for the device-name policy in src/lib/core/device_name.h.
 * Run with tests/run_device_name_test.sh (plain gcc, no Zephyr).
 */

#include <stdio.h>
#include <string.h>

/* Relative include on purpose: putting src/lib/core on the include path would shadow glibc's <features.h>. */
#include "../src/lib/core/device_name.h"

static int failures = 0;

#define CHECK(cond)                                                                                                    \
    do {                                                                                                               \
        if (!(cond)) {                                                                                                 \
            failures++;                                                                                                \
            fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);                                            \
        }                                                                                                              \
    } while (0)

static bool valid(const char *s)
{
    return omi_device_name_is_valid((const uint8_t *) s, strlen(s));
}

static void test_limits_match_advertising_budget(void)
{
    /* Single ATT Write Request at the default MTU: 23 - 3 (opcode + handle). */
    CHECK(OMI_DEVICE_NAME_MAX_LEN == 23 - 3);
    /* 31-byte scan response: 4 bytes DIS UUID16 + 2-byte name header + name. */
    CHECK(OMI_DEVICE_NAME_SCAN_RSP_BUDGET == 31 - 4 - 2);
    CHECK(OMI_DEVICE_NAME_MAX_LEN <= OMI_DEVICE_NAME_SCAN_RSP_BUDGET);
    /* 31-byte advertisement: 3 bytes flags + 18 bytes UUID128 + 2-byte name header + name. */
    CHECK(3 + 18 + 2 + OMI_DEVICE_NAME_ADV_MAX_LEN == 31);
}

static void test_accepts_plain_and_unicode_names(void)
{
    CHECK(valid("Omi"));
    CHECK(valid("Ana's Omi"));
    CHECK(valid("Omi #2"));
    CHECK(valid("L\xC3\xA9o"));                           /* Léo */
    CHECK(valid("\xE2\x9C\xA8 Omi"));                     /* ✨ Omi */
    CHECK(valid("Omi \xF0\x9F\x8E\xA7"));                 /* Omi 🎧 */
    CHECK(valid("\xE6\x97\xA5\xE6\x9C\xAC\xE8\xAA\x9E")); /* 日本語 */
    CHECK(valid("A"));
    CHECK(valid("12345678901234567890")); /* exactly 20 bytes */
}

static void test_rejects_empty_and_too_long(void)
{
    CHECK(!omi_device_name_is_valid((const uint8_t *) "", 0));
    CHECK(!omi_device_name_is_valid(NULL, 3));
    CHECK(!valid("123456789012345678901")); /* 21 bytes */
    /* 19 ASCII bytes + a 2-byte character = 21 bytes: over the byte budget even though it is 20 characters. */
    CHECK(!valid("1234567890123456789\xC3\xA9"));
}

static void test_rejects_control_characters_and_padding(void)
{
    CHECK(!valid(" Omi"));
    CHECK(!valid("Omi "));
    CHECK(!valid(" "));
    CHECK(!valid("Omi\n"));
    CHECK(!valid("Om\ti"));
    CHECK(!valid("Omi\x7F"));
    CHECK(!omi_device_name_is_valid((const uint8_t *) "Om\0i", 4));
}

static void test_rejects_malformed_utf8(void)
{
    CHECK(!valid("\xC3"));             /* truncated 2-byte sequence */
    CHECK(!valid("Omi\xE2\x9C"));      /* truncated 3-byte sequence */
    CHECK(!valid("\x80Omi"));          /* stray continuation byte */
    CHECK(!valid("\xC0\xAF"));         /* overlong encoding */
    CHECK(!valid("\xED\xA0\x80"));     /* UTF-16 surrogate */
    CHECK(!valid("\xF5\x80\x80\x80")); /* above U+10FFFF */
    CHECK(!valid("\xC3\x41"));         /* bad continuation byte */
}

static void test_shortened_prefix_never_splits_a_character(void)
{
    const char *ascii = "My Omi Device";
    CHECK(omi_device_name_utf8_prefix_len((const uint8_t *) ascii, strlen(ascii), OMI_DEVICE_NAME_ADV_MAX_LEN) == 8);

    /* Fits entirely: returned unchanged. */
    CHECK(omi_device_name_utf8_prefix_len((const uint8_t *) "Omi", 3, OMI_DEVICE_NAME_ADV_MAX_LEN) == 3);

    /* "Omi Léo" is 8 bytes when é is 2 bytes; but "Omi Lé" + "on" = "Omi Léon" is 9 bytes. */
    const char *leon = "Omi L\xC3\xA9on";
    CHECK(strlen(leon) == 9);
    CHECK(omi_device_name_utf8_prefix_len((const uint8_t *) leon, 9, OMI_DEVICE_NAME_ADV_MAX_LEN) == 8);

    /* A 4-byte emoji straddling the cut is dropped entirely, not split. */
    const char *emoji = "Omi 12\xF0\x9F\x8E\xA7"; /* 6 + 4 = 10 bytes; byte 8 is inside the emoji */
    CHECK(strlen(emoji) == 10);
    CHECK(omi_device_name_utf8_prefix_len((const uint8_t *) emoji, 10, OMI_DEVICE_NAME_ADV_MAX_LEN) == 6);

    /* Three 3-byte characters (9 bytes): the cut at 8 falls inside the third, so keep two. */
    const char *cjk = "\xE6\x97\xA5\xE6\x9C\xAC\xE8\xAA\x9E";
    CHECK(omi_device_name_utf8_prefix_len((const uint8_t *) cjk, 9, OMI_DEVICE_NAME_ADV_MAX_LEN) == 6);
}

int main(void)
{
    test_limits_match_advertising_budget();
    test_accepts_plain_and_unicode_names();
    test_rejects_empty_and_too_long();
    test_rejects_control_characters_and_padding();
    test_rejects_malformed_utf8();
    test_shortened_prefix_never_splits_a_character();

    if (failures) {
        fprintf(stderr, "%d device-name policy check(s) failed\n", failures);
        return 1;
    }
    printf("device-name policy tests passed\n");
    return 0;
}
