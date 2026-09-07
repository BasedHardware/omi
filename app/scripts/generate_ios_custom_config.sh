#!/bin/bash#
# Generate iOS Custom.xcconfig
# Usages:
# - $bash generate_ios_custom_config.sh <google_service_info_plist_file_path> <output_dir>
#
echo "// This is a generated file; do not edit or check into version control." > "$2/Custom.xcconfig"

# Only write the key when the plist actually carries a value. This file is
# included after Base.xcconfig, so an empty assignment here would override the
# default there rather than fall back to it — and the prebuilt community Firebase
# config carries no REVERSED_CLIENT_ID, which is exactly the case the default is
# for. Runner/Info.plist emits this as a CFBundleURLSchemes entry, so an empty
# value ships a malformed URL scheme.
reverse_client_id="$(cat $1 | grep REVERSED_CLIENT_ID -A 1 | tail -1 | xargs | cut -c9- | rev | cut -c10- | rev)"
if [ -n "$reverse_client_id" ]; then
  echo GOOGLE_REVERSE_CLIENT_ID="$reverse_client_id" >> "$2/Custom.xcconfig"
fi
