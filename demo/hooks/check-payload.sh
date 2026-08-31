#!/bin/sh
# Stands in for a pre-tool hook that inspects the tool call before it runs.
set -e
grep -q '"tool"' "$(dirname "$0")/../payload.json"
sleep 0.03
