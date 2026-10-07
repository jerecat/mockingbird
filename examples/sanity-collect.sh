#!/bin/sh
set -eu
: "${MB_RUN_ID:?}" "${MB_JOB_ID:?}"
result="work/sanity-results/$MB_RUN_ID/$MB_JOB_ID.json"
if [ -f "$result" ]; then
  cat "$result"
else
  printf '{"status":"PENDING"}\n'
fi
