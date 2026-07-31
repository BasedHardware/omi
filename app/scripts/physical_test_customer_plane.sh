#!/usr/bin/env bash

# Single executable authority for authenticated physical-device acceptance.
# Android and iOS use isolated development package identities, but exercise the
# customer data plane so auth, live transcription, and sync evidence are real.
# shellcheck disable=SC2034 # Consumed by scripts that source this contract.
OMI_PHYSICAL_TEST_API_BASE_URL="https://api.omi.me/"
OMI_PHYSICAL_TEST_FIREBASE_PROJECT_ID="based-hardware"
