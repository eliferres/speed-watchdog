#!/bin/sh
# The deliberately slowed hook: someone added a second lookup pass here,
# each one "too small to matter". This is the probe the demo report catches.
set -e
cat "$(dirname "$0")/../rules.txt" > /dev/null
sleep 0.03
cat "$(dirname "$0")/../payload.json" > /dev/null
sleep 0.05
