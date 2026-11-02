/* Host acceptance/demo only. Actual shared C crypto/journal/copy/boot services;
 * transport, flash, isolation, owner ACK and boot result are explicit simulations.
 * Never linked to target firmware. No BLE, device path, debugger or flash tool. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../shared/secure_services.h"
#define INTERNAL_SIZE 0x100000u
#define EXTERNAL_SIZE 0x200000u
#define BANK0 0x130000u
#define BANK1 0x190000u
#define TRIAL_BASE 0xf0000u
#define REF_BASE 0xf2000u
#define PERSONAL_BASE 0x54000u
#define DATA_BASE 0xf4000u
#define OWNER 1u
struct device;
struct view {
    struct device *d;
    unsigned reference;
};
struct bank {
    struct device *d;
    unsigned slot;
    uint64_t epoch;
    int leased;
};
struct device {
    uint8_t internal[INTERNAL_SIZE], external[EXTERNAL_SIZE];
    struct cv1_policy policy;
    struct view trial, reference;
    struct bank bank[2];
    int powered, upload_active, upload_slot, initializing;
    uint32_t upload_expected, upload_offset;
    uint64_t boot_nonce;
    struct cv1_boot_token pending;
    int outcome, pending_ack;
    long cut, units;
    unsigned bounds_rejections;
    uint8_t initial_data_hash[32], initial_root_hash[32], initial_external_guards[32];
};
static struct device d;
static struct cv1_policy fixture_registry;
static uint32_t get32(const uint8_t *p)
{
    return (uint32_t) p[0] | ((uint32_t) p[1] << 8) | ((uint32_t) p[2] << 16) | ((uint32_t) p[3] << 24);
}
static uint32_t base(unsigned slot)
{
    return slot ? BANK1 : BANK0;
}
static int hash(const uint8_t *p, size_t n, uint8_t out[32])
{
    return cv1_psa_crypto.sha256(p, n, out);
}
static void hex(const uint8_t h[32], char out[65])
{
    static const char a[] = "0123456789abcdef";
    for (unsigned k = 0; k < 32; k++) {
        out[2 * k] = a[h[k] >> 4];
        out[2 * k + 1] = a[h[k] & 15];
    }
    out[64] = 0;
}
static int fail(const char *stage, int code)
{
    fprintf(stderr, "FAIL %s (%d)\n", stage, code);
    return code ? code : -99;
}
static void event(const char *stage, const uint8_t digest[32], const char *detail)
{
    char h[65];
    hex(digest, h);
    printf("{\"stage\":\"%s\",\"artifact_sha256\":\"%s\",\"detail\":\"%s\",\"layer\":\"HOST SIMULATION; not "
           "BLE/CPU/SPU proof\"}\n",
           stage,
           h,
           detail);
}
static uint8_t *area(struct view *v, enum cv1_area kind, uint32_t off, size_t n)
{
    size_t cap;
    uint32_t start;
    if (kind == CV1_JOURNAL) {
        cap = CV1_JOURNAL_BYTES;
        start = v->reference ? REF_BASE : TRIAL_BASE;
    } else if (kind == CV1_PERSONAL && !v->reference) {
        cap = CV1_PERSONAL_BYTES;
        start = PERSONAL_BASE;
    } else {
        v->d->bounds_rejections++;
        return NULL;
    }
    if (off > cap || n > cap - off) {
        v->d->bounds_rejections++;
        return NULL;
    }
    return v->d->internal + start + off;
}
static int rd(void *p, enum cv1_area a, uint32_t off, uint8_t *out, size_t n)
{
    struct view *v = p;
    uint8_t *q = area(v, a, off, n);
    if (!v->d->powered || !q)
        return -1;
    memcpy(out, q, n);
    return 0;
}
static int mutation(struct device *dev)
{
    if (!dev->powered)
        return -1;
    if (dev->cut >= 0 && dev->units++ == dev->cut) {
        dev->powered = 0;
        return -1;
    }
    return 0;
}
static int erase(void *p, enum cv1_area a, uint32_t off, size_t n)
{
    struct view *v = p;
    uint8_t *q = area(v, a, off, n);
    if (!q || off % CV1_PAGE || n != CV1_PAGE)
        return -1;
    for (size_t k = 0; k < n; k += 4) {
        if (mutation(v->d))
            return -1;
        memset(q + k, 255, 4);
    }
    return 0;
}
static int program(void *p, enum cv1_area a, uint32_t off, const uint8_t *in, size_t n)
{
    struct view *v = p;
    uint8_t *q = area(v, a, off, n);
    if (!q || off % 4 || n % 4)
        return -1;
    for (size_t k = 0; k < n; k += 4) {
        if (mutation(v->d))
            return -1;
        for (unsigned j = 0; j < 4; j++) {
            if ((q[k + j] & in[k + j]) != in[k + j])
                return -1;
            q[k + j] = in[k + j];
        }
    }
    return 0;
}
static int isolation(void *p)
{
    return ((struct view *) p)->d->powered ? 1 : 0;
} /* HOST STUB ONLY */
static struct cv1_flash flash(struct view *v)
{
    return (struct cv1_flash) {v, rd, erase, program, isolation};
}
static uint32_t bank_size(struct bank *b)
{
    const uint8_t *p = b->d->external + base(b->slot);
    uint32_t n = get32(p + 24);
    if (get32(p) != 0x324e574f || n < 512 || n > CV1_CAP - CV1_PREFIX)
        return 0;
    return n + CV1_PREFIX;
}
static int acquire(void *p, uint32_t n, uint64_t *lease)
{
    struct bank *b = p;
    if (!b->d->powered || b->leased || (b->d->upload_active && b->d->upload_slot == (int) b->slot) || n != bank_size(b))
        return -1;
    b->leased = 1;
    b->epoch++;
    if (!b->epoch)
        b->epoch = 1;
    *lease = b->epoch;
    return 0;
}
static int check(void *p, uint64_t lease)
{
    struct bank *b = p;
    return b->d->powered && b->leased && b->epoch == lease ? 0 : -1;
}
static int source_read(void *p, uint64_t lease, uint32_t off, uint8_t *out, size_t n)
{
    struct bank *b = p;
    uint32_t size = bank_size(b);
    if (check(p, lease) || off > size || n > size - off)
        return -1;
    memcpy(out, b->d->external + base(b->slot) + off, n);
    return 0;
}
static int release(void *p, uint64_t lease)
{
    struct bank *b = p;
    if (check(p, lease))
        return -1;
    b->leased = 0;
    return 0;
}
static int admit(unsigned slot, struct cv1_image *image)
{
    struct cv1_source s = {&d.bank[slot], acquire, source_read, check, release};
    memset(image, 0, sizeof(*image));
    return cv1_image_admit(image, bank_size(&d.bank[slot]), &s, &d.policy, &cv1_psa_crypto);
}
static int load_ref(struct cv1_record *r)
{
    struct cv1_flash f = flash(&d.reference);
    int rc = cv1_journal_load(&f, r);
    return rc ? rc : r->phase == CV1_CONFIRMED ? 0 : CV1_ESTATE;
}
static int find_artifact_bank(const struct cv1_record *r)
{
    for (unsigned slot = 0; slot < 2; slot++) {
        struct cv1_image image;
        int rc = admit(slot, &image);
        if (!rc) {
            int match = image.size == r->size && image.generation == r->generation &&
                        !memcmp(image.container_hash, r->hash, 32);
            cv1_image_forget(&image);
            if (match)
                return (int) slot;
        }
    }
    return -1;
}
static int mirror(struct view *view, struct cv1_record *r)
{
    struct cv1_flash f = flash(view);
    for (unsigned k = 0; k < 2; k++) {
        if (r->sequence == UINT64_MAX)
            return CV1_ESTATE;
        r->sequence++;
        int rc = cv1_journal_store(&f, r);
        if (rc)
            return rc;
    }
    return 0;
}
static int current_artifact(uint8_t out[32])
{
    struct cv1_record r;
    struct cv1_flash f = flash(&d.trial);
    if (cv1_journal_load(&f, &r))
        return -1;
    memcpy(out, r.hash, 32);
    return 0;
}
static int preserve(void)
{
    uint8_t h[32];
    if (hash(d.internal + DATA_BASE, INTERNAL_SIZE - DATA_BASE, h) || memcmp(h, d.initial_data_hash, 32))
        return -1;
    if (hash(d.internal, PERSONAL_BASE, h) || memcmp(h, d.initial_root_hash, 32))
        return -2;
    if (hash(d.external, BANK0, h) || memcmp(h, d.initial_external_guards, 32))
        return -3;
    return d.bounds_rejections ? -4 : 0;
}
/* Transport adapter stub: sequential bounded chunks, NO BLE or authenticated
 * phone session. The fixture-owner registry is RAM-only test setup. */
static int upload_begin(uint32_t total)
{
    if (!d.powered || d.upload_active || d.pending_ack || total > CV1_CAP || total < 1024)
        return -1;
    struct cv1_flash active_view = flash(&d.trial);
    struct cv1_record active_record;
    int active_rc = cv1_journal_load(&active_view, &active_record);
    if ((!active_rc && active_record.phase != CV1_CONFIRMED) || (active_rc && !d.initializing))
        return -1;
    struct cv1_record r;
    int known = -1;
    if (!load_ref(&r))
        known = find_artifact_bank(&r);
    else if (!d.initializing)
        return -1;
    if (known < 0 && !d.initializing)
        return -1;
    int slot = known < 0 ? 0 : 1 - known;
    if (d.bank[slot].leased)
        return -1;
    memset(d.external + base((unsigned) slot), 255, CV1_CAP);
    d.upload_active = 1;
    d.upload_slot = slot;
    d.upload_expected = total;
    d.upload_offset = 0;
    return slot;
}
static int upload_chunk(uint32_t off, const uint8_t *bytes, size_t n)
{
    if (!d.powered || !d.upload_active || off != d.upload_offset || !n || n > 137 || off > d.upload_expected ||
        n > d.upload_expected - off || d.bank[d.upload_slot].leased)
        return -1;
    uint8_t *q = d.external + base((unsigned) d.upload_slot) + off;
    for (size_t k = 0; k < n; k++) {
        if ((q[k] & bytes[k]) != bytes[k])
            return -1;
        q[k] = bytes[k];
    }
    d.upload_offset += (uint32_t) n;
    return 0;
}
static int upload(const uint8_t *blob, uint32_t n, uint32_t limit)
{
    int slot = upload_begin(n);
    if (slot < 0)
        return -1;
    uint32_t end = limit < n ? limit : n;
    for (uint32_t off = 0; off < end;) {
        size_t take = end - off;
        if (take > 137)
            take = 137;
        if (upload_chunk(off, blob + off, take))
            return -1;
        off += (uint32_t) take;
    }
    if (end == n)
        d.upload_active = 0;
    return slot;
}
static void restart(void)
{
    memset(&d.policy, 0, sizeof(d.policy));
    d.policy = fixture_registry;
    d.outcome = 0;
    d.powered = 1;
    d.cut = -1;
    d.units = 0;
    d.upload_active = 0;
    d.upload_expected = d.upload_offset = 0;
    d.pending_ack = 0;
    memset(&d.pending, 0, sizeof(d.pending));
    for (unsigned k = 0; k < 2; k++) {
        d.bank[k].leased = 0;
        d.bank[k].epoch++;
    }
}
static int trial(unsigned slot, struct cv1_boot_token *token)
{
    memset(token, 0, sizeof(*token));
    struct cv1_image image;
    int rc = admit(slot, &image);
    if (rc)
        return rc;
    struct cv1_flash f = flash(&d.trial);
    rc = cv1_copy_verified(&f, &image);
    if (!rc) {
        struct cv1_boot_token plan;
        rc = cv1_prepare_boot(&f, &image, &plan);
        if (!rc)
            rc = cv1_authorize_boot(&f, &plan, token);
    }
    cv1_image_forget(&image);
    return rc;
}
static void simulated_boot(const struct cv1_boot_token *token, int healthy)
{
    if (token->valid != CV1_TOKEN) {
        fputs("invalid simulatedboot token", stderr);
        exit(3);
    }
    d.boot_nonce++;
    d.pending = *token;
    d.outcome = healthy;
    struct cv1_flash f = flash(&d.trial);
    struct cv1_record active;
    d.pending_ack = !cv1_journal_load(&f, &active) && active.phase == CV1_TRIAL &&
                    active.sequence == token->journal_sequence && !memcmp(active.hash, token->hash, 32);
    event("simulated_boot",
          token->hash,
          healthy ? "CPU outcome stub HEALTHY; no target execution" : "CPU outcome stub FAULT; no target execution");
}
static int confirm(unsigned fixture_owner, uint64_t nonce, const uint8_t digest[32])
{
    if (fixture_owner != OWNER || !d.pending_ack || !d.outcome || nonce != d.boot_nonce ||
        memcmp(digest, d.pending.hash, 32))
        return -1;
    struct cv1_flash f = flash(&d.trial);
    struct cv1_record r;
    if (cv1_journal_load(&f, &r) || r.phase != CV1_TRIAL || r.sequence != d.pending.journal_sequence ||
        memcmp(r.hash, digest, 32))
        return -1;
    uint8_t personal_hash[32];
    if (find_artifact_bank(&r) < 0 || hash(d.internal + PERSONAL_BASE, r.size, personal_hash) ||
        memcmp(personal_hash, r.hash, 32)) {
        d.pending_ack = 0;
        return -1;
    }
    r.phase = CV1_CONFIRMED;
    if (mirror(&d.trial, &r))
        return -1;
    struct cv1_record prior;
    int rc = load_ref(&prior);
    r.sequence = rc ? 0 : prior.sequence;
    r.phase = CV1_CONFIRMED;
    if (mirror(&d.reference, &r))
        return -1;
    d.pending_ack = 0;
    event("explicit_healthy_confirmation",
          digest,
          "fixture owner ACK bound to boot nonce+digest; not real enrollment/session");
    return 0;
}
static int restore_known_good(struct cv1_boot_token *token)
{
    memset(token, 0, sizeof(*token));
    struct cv1_record ref;
    if (load_ref(&ref))
        return -1;
    int slot = find_artifact_bank(&ref);
    if (slot < 0)
        return -1;
    struct cv1_image image;
    if (admit((unsigned) slot, &image))
        return -1;
    struct cv1_flash f = flash(&d.trial);
    int rc = cv1_copy_verified(&f, &image);
    if (!rc) {
        struct cv1_record r;
        if (cv1_journal_load(&f, &r) || r.phase != CV1_VERIFIED || memcmp(r.hash, ref.hash, 32))
            rc = -1;
        else {
            r.phase = CV1_CONFIRMED;
            rc = mirror(&d.trial, &r);
        }
    }
    if (!rc) {
        struct cv1_boot_token plan;
        rc = cv1_prepare_boot(&f, &image, &plan);
        if (!rc)
            rc = cv1_authorize_boot(&f, &plan, token);
    }
    cv1_image_forget(&image);
    if (!rc)
        event("return_to_known_good",
              token->hash,
              "reference journal+actual PSA+copy/readback; host boot outcome simulated");
    return rc;
}
static int boot_or_recover(struct cv1_boot_token *token)
{
    memset(token, 0, sizeof(*token));
    struct cv1_flash f = flash(&d.trial);
    struct cv1_record r;
    if (cv1_journal_load(&f, &r))
        return -1;
    if (r.phase == CV1_TRIAL || r.phase == CV1_COPY || r.phase == CV1_VERIFIED)
        return restore_known_good(token);
    if (r.phase != CV1_CONFIRMED)
        return -1;
    int slot = find_artifact_bank(&r);
    if (slot < 0)
        return restore_known_good(token);
    struct cv1_image image;
    if (admit((unsigned) slot, &image))
        return -1;
    struct cv1_boot_token plan;
    int rc = cv1_prepare_boot(&f, &image, &plan);
    if (!rc)
        rc = cv1_authorize_boot(&f, &plan, token);
    cv1_image_forget(&image);
    return rc;
}
static int read_blob(const char *name, uint8_t **out, uint32_t *size)
{
    FILE *f = fopen(name, "rb");
    if (!f)
        return -1;
    if (fseek(f, 0, SEEK_END)) {
        fclose(f);
        return -1;
    }
    long n = ftell(f);
    if (n < 1024 || n > CV1_CAP || fseek(f, 0, SEEK_SET)) {
        fclose(f);
        return -1;
    }
    *out = malloc((size_t) n);
    if (!*out) {
        fclose(f);
        return -1;
    }
    int ok = fread(*out, 1, (size_t) n, f) == (size_t) n && !ferror(f);
    fclose(f);
    *size = (uint32_t) n;
    return ok ? 0 : -1;
}
static int read_policy(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f)
        return -1;
    uint8_t b[109];
    int ok = fread(b, 1, sizeof(b), f) == sizeof(b) && fgetc(f) == EOF;
    fclose(f);
    if (!ok)
        return -1;
    d.policy.board = get32(b);
    d.policy.abi = get32(b + 4);
    d.policy.generation = get32(b + 8);
    memcpy(d.policy.network_hash, b + 12, 32);
    memcpy(d.policy.public_key, b + 44, 65);
    fixture_registry = d.policy;
    return 0;
}
int main(int argc, char **argv)
{
    if (argc != 8)
        return fail("args: policy A B C wrongowner modified wrongABI", -1);
    memset(&d, 0, sizeof(d));
    memset(d.internal, 255, sizeof(d.internal));
    memset(d.external, 0xd4, sizeof(d.external));
    memset(d.external + BANK0, 255, 2 * CV1_CAP);
    memset(d.internal, 0xa5, PERSONAL_BASE);
    memset(d.internal + DATA_BASE, 0x5a, INTERNAL_SIZE - DATA_BASE);
    d.powered = 1;
    d.cut = -1;
    d.initializing = 1;
    d.trial = (struct view) {&d, 0};
    d.reference = (struct view) {&d, 1};
    for (unsigned k = 0; k < 2; k++)
        d.bank[k] = (struct bank) {&d, k, 0, 0};
    if (read_policy(argv[1]) || hash(d.internal + DATA_BASE, INTERNAL_SIZE - DATA_BASE, d.initial_data_hash) ||
        hash(d.internal, PERSONAL_BASE, d.initial_root_hash) || hash(d.external, BANK0, d.initial_external_guards))
        return fail("init", -1);
    uint8_t *blob[6] = {0};
    uint32_t size[6];
    for (unsigned k = 0; k < 6; k++)
        if (read_blob(argv[k + 2], &blob[k], &size[k]))
            return fail("fixture read", -1);
    uint8_t digest[6][32];
    for (unsigned k = 0; k < 6; k++)
        if (hash(blob[k], size[k], digest[k]))
            return fail("fixturehash", -1);
    struct cv1_boot_token token;
    int slot = upload(blob[0], size[0], size[0]);
    if (slot < 0 || trial((unsigned) slot, &token))
        return fail("initial A trial", -1);
    event("chunked_upload_and_verified_trial", token.hash, "137-byte transport stub chunks; actual PSA/core services");
    simulated_boot(&token, 1);
    uint8_t wrong_ack[32];
    memcpy(wrong_ack, token.hash, 32);
    wrong_ack[0] ^= 1;
    if (confirm(OWNER, d.boot_nonce, wrong_ack) == 0 || confirm(OWNER + 1, d.boot_nonce, token.hash) == 0 ||
        confirm(OWNER, d.boot_nonce + 1, token.hash) == 0)
        return fail("bad ACK accepted", -1);
    event("invalid_confirmation_rejected", token.hash, "wrong fixture owner, nonce and digest ACKs rejected");
    if (confirm(OWNER, d.boot_nonce, token.hash))
        return fail("confirm A", -1);
    d.initializing = 0;
    slot = upload(blob[1], size[1], size[1]);
    if (slot < 0 || trial((unsigned) slot, &token))
        return fail("B trial", -1);
    simulated_boot(&token, 1);
    if (upload_begin(size[2]) >= 0)
        return fail("upload replaced pending trial", -1);
    event("pending_trial_upload_rejected", token.hash, "pending/durable trial prevents overwriting backing artifact");
    if (confirm(OWNER, d.boot_nonce, token.hash))
        return fail("confirm B", -1);
    for (unsigned k = 3; k < 6; k++) {
        uint8_t before[32], after[32];
        if (hash(d.internal + PERSONAL_BASE, CV1_PERSONAL_BYTES, before))
            return -1;
        slot = upload(blob[k], size[k], size[k]);
        if (slot < 0 || trial((unsigned) slot, &token) == 0)
            return fail("negative candidate accepted", -1);
        if (hash(d.internal + PERSONAL_BASE, CV1_PERSONAL_BYTES, after) || memcmp(before, after, 32) || preserve())
            return fail("negative modified active/data", -1);
        event(k == 3   ? "wrong_owner_rejected"
              : k == 4 ? "modified_image_rejected"
                       : "wrong_ABI_rejected",
              digest[k],
              "actual PSA/header admission; active image and user data unchanged");
    }
    /* A forged healthy ACK cannot promote a missing/corrupted backing bank. */
    slot = upload(blob[2], size[2], size[2]);
    if (slot < 0 || trial((unsigned) slot, &token))
        return fail("storage fault trial", -1);
    simulated_boot(&token, 1);
    d.external[base((unsigned) slot) + size[2] - 1] ^= 1;
    if (confirm(OWNER, d.boot_nonce, token.hash) == 0)
        return fail("missing backing bank confirmed", -1);
    event("confirmation_storage_fault_rejected",
          token.hash,
          "out-of-band host fault; backing artifact re-admission blocks promotion");
    restart();
    if (boot_or_recover(&token) || memcmp(token.hash, digest[1], 32))
        return fail("storage fault recovery", -1);
    slot = upload(blob[2], size[2], size[2]);
    if (slot < 0 || trial((unsigned) slot, &token))
        return fail("bad candidate trial", -1);
    simulated_boot(&token, 0);
    if (confirm(OWNER, d.boot_nonce, token.hash) == 0)
        return fail("fault confirmed", -1);
    event("unhealthy_confirmation_rejected", token.hash, "FAULT outcome cannot receive healthy confirmation");
    restart();
    if (boot_or_recover(&token) || memcmp(token.hash, digest[1], 32))
        return fail("bad candidate recovery", -1);
    simulated_boot(&token, 1);
    slot = upload(blob[2], size[2], 411);
    if (slot < 0)
        return fail("partial upload", -1);
    restart();
    struct cv1_image incomplete;
    if (admit((unsigned) slot, &incomplete) == 0) {
        cv1_image_forget(&incomplete);
        return fail("partial upload admitted", -1);
    }
    event("interrupted_upload_restart",
          digest[2],
          "partial bank fails real verification; retransmit required; active known-good retained");
    if (boot_or_recover(&token) || memcmp(token.hash, digest[1], 32))
        return fail("upload interruption changed boot", -1);
    /* Reset in the real core's VERIFIED state, before trial authorization. */
    slot = upload(blob[2], size[2], size[2]);
    if (slot < 0)
        return fail("verified upload", -1);
    struct cv1_image verified;
    struct cv1_flash active_flash = flash(&d.trial);
    if (admit((unsigned) slot, &verified) || cv1_copy_verified(&active_flash, &verified))
        return fail("verified copy", -1);
    cv1_image_forget(&verified);
    restart();
    if (boot_or_recover(&token) || memcmp(token.hash, digest[1], 32))
        return fail("VERIFIED reset recovery", -1);
    event("completed_copy_before_trial_restart",
          token.hash,
          "VERIFIED is unconfirmed; restore reference, do not auto-trial");
    slot = upload(blob[2], size[2], size[2]);
    if (slot < 0)
        return fail("reupload", -1);
    d.units = 0;
    d.cut = 1088 + 25;
    if (trial((unsigned) slot, &token) == 0 || d.powered)
        return fail("copy cut missing", -1);
    restart();
    if (boot_or_recover(&token) || memcmp(token.hash, digest[1], 32))
        return fail("copy cut recovery", -1);
    event("interrupted_copy_restart",
          token.hash,
          "durable COPY intent; actual known-good re-admission/copy; no partial boot");
    slot = upload(blob[2], size[2], size[2]);
    if (slot < 0 || trial((unsigned) slot, &token))
        return fail("unconfirmed trial", -1);
    restart();
    if (boot_or_recover(&token) || memcmp(token.hash, digest[1], 32))
        return fail("unconfirmed restart", -1);
    event("unconfirmed_trial_restart", token.hash, "mirrored TRIAL blocks repeat; restored confirmed artifact");
    if (preserve())
        return fail("user data/root bounds", -1);
    event("user_data_bounds_preserved",
          d.initial_data_hash,
          "all reserved user bytes F4000..100000 and root/legacy guards unchanged");
    uint8_t final[32];
    if (current_artifact(final) || memcmp(final, digest[1], 32))
        return fail("final identity", -1);
    event("PASS", final, "host-only end-to-end acceptance; hardware/SPU/BLE/CPU not qualified");
    for (unsigned k = 0; k < 6; k++)
        free(blob[k]);
    return 0;
}
