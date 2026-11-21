/* Real PSA verification-only adapter. Never run on target in this research. */
#include <psa/crypto.h>
#include <string.h>

#include "secure_services.h"
static int psa_verify_public(const uint8_t public_key[65], const uint8_t hash[32], const uint8_t signature[64])
{
    psa_key_attributes_t attr = PSA_KEY_ATTRIBUTES_INIT;
    mbedtls_svc_key_id_t key = 0;
    psa_status_t status = psa_crypto_init();
    if (status != PSA_SUCCESS)
        return status;
    psa_set_key_usage_flags(&attr, PSA_KEY_USAGE_VERIFY_HASH);
    psa_set_key_algorithm(&attr, PSA_ALG_ECDSA(PSA_ALG_SHA_256));
    psa_set_key_type(&attr, PSA_KEY_TYPE_ECC_PUBLIC_KEY(PSA_ECC_FAMILY_SECP_R1));
    psa_set_key_bits(&attr, 256);
    status = psa_import_key(&attr, public_key, 65, &key); /* transient PUBLIC verification input only */
    psa_reset_key_attributes(&attr);
    if (status != PSA_SUCCESS)
        return status;
    status = psa_verify_hash(key, PSA_ALG_ECDSA(PSA_ALG_SHA_256), hash, 32, signature, 64);
    psa_status_t cleanup = psa_destroy_key(key);
    return status != PSA_SUCCESS ? status : cleanup;
}

static int sha256(const uint8_t *data, size_t length, uint8_t out[32])
{
    size_t n = 0;
    psa_status_t s = psa_crypto_init();
    if (s != PSA_SUCCESS)
        return s;
    s = psa_hash_compute(PSA_ALG_SHA_256, data, length, out, 32, &n);
    return s == PSA_SUCCESS && n == 32 ? 0 : -1;
}
_Static_assert(sizeof(psa_hash_operation_t) <= sizeof(struct cv1_digest), "hash state budget exceeded");
static int begin(struct cv1_digest *s)
{
    memset(s, 0, sizeof(*s));
    psa_status_t rc = psa_crypto_init();
    return rc == PSA_SUCCESS ? psa_hash_setup((psa_hash_operation_t *) s, PSA_ALG_SHA_256) : rc;
}
static int update(struct cv1_digest *s, const uint8_t *p, size_t n)
{
    return psa_hash_update((psa_hash_operation_t *) s, p, n);
}
static int finish(struct cv1_digest *s, uint8_t out[32])
{
    size_t n = 0;
    psa_status_t rc = psa_hash_finish((psa_hash_operation_t *) s, out, 32, &n);
    return rc == PSA_SUCCESS && n == 32 ? 0 : -1;
}
static void abort_hash(struct cv1_digest *s)
{
    psa_hash_abort((psa_hash_operation_t *) s);
    memset(s, 0, sizeof(*s));
}
const struct cv1_crypto cv1_psa_crypto = {sha256, psa_verify_public, begin, update, finish, abort_hash};
