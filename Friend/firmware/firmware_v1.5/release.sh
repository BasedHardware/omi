set -e

# Cleanup
rm -fr release

# Define the board
BOARD="xiao_ble"

# List all configuration files
CONFIGS=(
    "bubble_pcm" 
    "bubble_mulaw" 
    "bubble_opus"
    "friend_pcm"
    "friend_mulaw"
    "friend_opus"
)

# Loop through each configuration and build the firmware
for CONFIG in "${CONFIGS[@]}"
do
    echo "Building with configuration $CONFIG"
    # Run the build command
    west build --pristine -b $BOARD -d release/$CONFIG -- -DCONF_FILE="prj.conf prj_$CONFIG.conf"
done

# Copy
mkdir -p release/firmware
cp -r release/bubble_pcm/zephyr/zephyr.uf2 release/firmware/bubble_pcm.uf2
cp -r release/bubble_mulaw/zephyr/zephyr.uf2 release/firmware/bubble_mulaw.uf2
cp -r release/bubble_opus/zephyr/zephyr.uf2 release/firmware/bubble_opus.uf2
cp -r release/friend_pcm/zephyr/zephyr.uf2 release/firmware/friend_pcm.uf2
cp -r release/friend_mulaw/zephyr/zephyr.uf2 release/firmware/friend_mulaw.uf2
cp -r release/friend_opus/zephyr/zephyr.uf2 release/firmware/friend_opus.uf2
