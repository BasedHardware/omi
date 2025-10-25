#!/bin/bash
cd /Users/eulices/omi-fork-4/app/ios
xcodebuild -project Runner.xcodeproj \
  -target omiWatchApp \
  -sdk watchsimulator \
  -arch arm64 \
  -configuration Debug \
  CODE_SIGN_IDENTITY="" \
  CODE_SIGNING_REQUIRED=NO \
  CODE_SIGNING_ALLOWED=NO \
  ONLY_ACTIVE_ARCH=YES \
  build
