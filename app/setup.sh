#!/bin/bash
#
# Set up the Omi Mobile Project(iOS/Android).
# Docs: https://docs.omi.me/docs/get_started/Setup
# Styleguide: https://google.github.io/styleguide/shellguide.html
#

# UTILS
#
err() {
  echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')]: $*" >&2
}

log() {
  echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')]: $*"
}

echo "👋 Yo folks! Welcome to the OMI Mobile Project - We're hiring! Join us on Discord: http://discord.omi.me"
