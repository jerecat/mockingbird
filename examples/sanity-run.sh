#!/bin/sh
set -eu

case "${1:-}" in
  pwd)
    pwd
    ;;
  list_directory)
    ls -la
    ;;
  make_directory)
    d="$(mktemp -d)"
    rmdir "$d"
    ;;
  remove_directory)
    f="$(mktemp)"
    rm -f "$f"
    ;;
  *)
    echo "unknown sanity job: ${1:-<missing>}" >&2
    exit 2
    ;;
esac
