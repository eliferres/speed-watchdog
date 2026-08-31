#!/bin/sh
# Stands in for a harness hook that reads a rules file at session start.
# The sleep is the fictional cost, so the demo has a known answer offline.
set -e
cat "$(dirname "$0")/../rules.txt" > /dev/null
sleep 0.01
