#!/bin/sh
set -eu

run_sanity() {
case "${1:-}" in
  pwd)
    pwd
    ;;
  list_directory)
    ls -la
    ;;
  make_directory)
    d="$(mktemp -d)" || return 1
    rmdir "$d"
    ;;
  remove_directory)
    f="$(mktemp)" || return 1
    rm -f "$f"
    ;;
  *)
    echo "unknown sanity job: ${1:-<missing>}" >&2
    return 2
    ;;
esac
}

# Project-owned evidence; MB does not interpret this path or judgement policy.
: "${MB_RUN_ID:?}" "${MB_JOB_ID:?}"
out="work/sanity-results/$MB_RUN_ID"
mkdir -p "$out"
if run_sanity "$@"; then
  printf '{"status":"PASS"}\n' > "$out/$MB_JOB_ID.json"
else
  printf '{"status":"FAIL"}\n' > "$out/$MB_JOB_ID.json"
  exit 1
fi

