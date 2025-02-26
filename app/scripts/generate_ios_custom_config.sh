#!/bin/bash#
# Generate iOS Custom.xcconfig
# Usages:
# - $bash generate_ios_custom_config.sh <google_service_info_plist_file_path> <output_dir>
#
echo "// This is a generated file; do not edit or check into version control." > "$2/Custom.xcconfig"
echo GOOGLE_REVERSE_CLIENT_ID="$(cat $1 | grep REVERSED_CLIENT_ID -A 1 | tail -1 | xargs | cut -c9- | rev | cut -c10- | rev)" >> "$2/Custom.xcconfig"
