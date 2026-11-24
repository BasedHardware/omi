/* Runner-side (host libc) half of the simulator power model. It is linked into
 * the native_simulator runner, not the Zephyr image, so it may use stdio.
 * Files live in the boot's working directory, chosen by scenario_runner.py:
 *   boot.cfg      this boot's pre-state and hardware timeline (text)
 *   retained.bin  retained RAM; present only across warm resets
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../sim_plan.h"

static struct omi_sim_plan plan;
static int loaded;

static void load(void)
{
    loaded = 1;
    plan.battery_mv = 3900;
    FILE *cfg = fopen("boot.cfg", "r");
    if (cfg) {
        char line[256];
        while (fgets(line, sizeof(line), cfg)) {
            char word[32] = {0};
            long long t = 0;
            int a = 0, b = 0, c = 0;
            char key[40] = {0};
            if (sscanf(line, "%31s", word) != 1 || word[0] == '#') {
                continue;
            }
            if (!strcmp(word, "reset")) {
                unsigned int reason = 0;
                sscanf(line, "%*s %u", &reason);
                plan.reset_reason = reason;
            } else if (!strcmp(word, "button")) {
                sscanf(line, "%*s %d", &plan.button_pressed);
            } else if (!strcmp(word, "charging")) {
                sscanf(line, "%*s %d", &plan.charging);
            } else if (!strcmp(word, "battery_mv")) {
                sscanf(line, "%*s %d", &plan.battery_mv);
            } else if (!strcmp(word, "connected")) {
                sscanf(line, "%*s %d", &plan.connected);
            } else if (!strcmp(word, "sd")) {
                sscanf(line, "%*s %d %d", &plan.sd_state, &plan.sd_ready_ms);
            } else if (!strcmp(word, "event") && plan.n_events < OMI_SIM_MAX_EVENTS &&
                       sscanf(line, "%*s %lld %d %d", &t, &a, &b) == 3) {
                plan.events[plan.n_events++] = (struct omi_sim_event){.t_ms = t, .kind = a, .value = b};
            } else if (!strcmp(word, "fault") && plan.n_faults < OMI_SIM_MAX_FAULTS &&
                       sscanf(line, "%*s %d %d %d %39s", &a, &b, &c, key) >= 3) {
                struct omi_sim_fault *f = &plan.faults[plan.n_faults++];
                f->op = a;
                f->rc = b;
                f->remaining = c;
                strncpy(f->key, key, sizeof(f->key) - 1);
            } else {
                fprintf(stderr, "SIM: boot.cfg: unknown line: %s", line);
                exit(70);
            }
        }
        fclose(cfg);
    }
    FILE *ram = fopen("retained.bin", "rb");
    if (ram) {
        size_t n = fread(plan.retained, 1, sizeof(plan.retained), ram);
        fclose(ram);
        plan.retained_len = (uint32_t) n;
        plan.retained_loaded = n > 0;
    }
}

const struct omi_sim_plan *omi_sim_host_plan(void)
{
    if (!loaded) {
        load();
    }
    return &plan;
}

int omi_sim_host_save_retained(const void *data, uint32_t len)
{
    FILE *ram = fopen("retained.bin.tmp", "wb");
    if (!ram) {
        return -1;
    }
    size_t n = fwrite(data, 1, len, ram);
    if (fclose(ram) || n != len) {
        return -1;
    }
    return rename("retained.bin.tmp", "retained.bin");
}

int omi_sim_host_load_file(const char *name, void *data, uint32_t len)
{
    FILE *f = fopen(name, "rb");
    if (!f) {
        return -1;
    }
    size_t n = fread(data, 1, len, f);
    fclose(f);
    return n == len ? 0 : -1;
}

int omi_sim_host_save_file(const char *name, const void *data, uint32_t len)
{
    char tmp[256];
    snprintf(tmp, sizeof(tmp), "%s.tmp", name);
    FILE *f = fopen(tmp, "wb");
    if (!f) {
        return -1;
    }
    size_t n = fwrite(data, 1, len, f);
    if (fclose(f) || n != len) {
        return -1;
    }
    return rename(tmp, name);
}

void omi_sim_host_print(const char *line)
{
    fflush(stdout);
    fputs(line, stdout);
    fputc('\n', stdout);
    fflush(stdout);
}
