#!/bin/bash

echo "// This is a generated file; do not edit or check into version control." > "ios/Flutter/Custom.xcconfig"
echo GOOGLE_REVERSE_CLIENT_ID="$(cat ios/Runner/GoogleService-Info.plist | grep REVERSED_CLIENT_ID -A 1 | tail -1 | xargs | cut -c9- | rev | cut -c10- | rev)" >> "ios/Flutter/Custom.xcconfig"
