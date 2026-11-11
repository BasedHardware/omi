# Battery host regression

Run `bash omi/firmware/omi/tests/battery/run.sh` from the repository root.
The suite compiles production battery.c against explicit GPIO/ADC/kernel shims,
and extracts the production broadcast function to exercise disconnected BAS,
raw diagnostic voltage, and the corrected-voltage shutdown threshold. It covers
charger boot, frozen SOC, unplug rebase, edge-spanning samples, ADC/GPIO failures
and saturated edge counts. No hardware access or firmware build is performed.
The existing 25-byte diagnostics GATT layout is unchanged; battery-only detail
remains internal through battery_get_diagnostics().

Target qualification still needs charging/unplug voltage and SOC traces, GPIO
edge timing, idle current and a firmware build with the CV1 toolchain.
