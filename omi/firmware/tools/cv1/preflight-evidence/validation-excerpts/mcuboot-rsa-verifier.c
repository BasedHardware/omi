48: /*
49:  * Constants for this particular constrained implementation of
50:  * RSA-PSS. In particular, we support RSA 2048, with a SHA256 hash,
51:  * and a 32-byte salt.  A signature with different parameters will be
52:  * rejected as invalid.
53:  */
54:
55: /* The size, in octets, of the message. */
56: #define PSS_EMLEN (MCUBOOT_SIGN_RSA_LEN / 8)
57:
58: /* The size of the hash function.  For SHA256, this is 32 bytes. */
59: #define PSS_HLEN 32
60:
61: /* Size of the salt, should be fixed. */
62: #define PSS_SLEN 32
63:
64: /* The length of the mask: emLen - hLen - 1. */
65: #define PSS_MASK_LEN (PSS_EMLEN - PSS_HLEN - 1)
115: /*
116:  * Validate an RSA signature, using RSA-PSS, as described in PKCS #1
117:  * v2.2, section 9.1.2, with many parameters required to have fixed
118:  * values. RSASSA-PSS-VERIFY RFC8017 section 8.1.2
119:  */
120: static fih_ret
121: bootutil_cmp_rsasig(bootutil_rsa_context *ctx, uint8_t *hash, uint32_t hlen,
122:   uint8_t *sig, size_t slen)
123: {
124:     bootutil_sha_context shactx;
125:     uint8_t em[MBEDTLS_MPI_MAX_SIZE];
126:     uint8_t db_mask[PSS_MASK_LEN];
127:     uint8_t h2[PSS_HLEN];
128:     int i;
129:     FIH_DECLARE(fih_rc, FIH_FAILURE);
130:
131:     /* The caller has already verified that slen == bootutil_rsa_get_len(ctx) */
132:     if (slen != PSS_EMLEN ||
133:         PSS_EMLEN > MBEDTLS_MPI_MAX_SIZE) {
134:         goto out;
135:     }
136:
137:     if (hlen != PSS_HLEN) {
138:         goto out;
243:   uint8_t *sig, size_t slen)
244: {
245:     int rc = -1;
246:     FIH_DECLARE(fih_rc, FIH_FAILURE);
247:
248:     /* PSA Crypto APIs allow the verification in a single call */
249:     rc = bootutil_rsassa_pss_verify(ctx, hash, hlen, sig, slen);
250:
251:     fih_rc = fih_ret_encode_zero_equality(rc);
252:     if (FIH_NOT_EQ(fih_rc, FIH_SUCCESS)) {
253:         FIH_SET(fih_rc, FIH_FAILURE);
