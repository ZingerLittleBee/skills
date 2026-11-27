#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
shortcuts="$repo_dir/rex/shortcuts.lua"
config="${REX_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/rex/init.lua}"
rex_bin="${REX_BIN:-$(command -v rex || true)}"
if [[ -z "$rex_bin" ]]; then
  rex_bin="$HOME/Library/Application Support/com.superlogical.rex/RexServer/Versions/Current/Rex Server.app/Contents/MacOS/rex"
fi
if ! command -v "$rex_bin" >/dev/null; then
  echo "error: Rex CLI not found. Install Rex or set REX_BIN." >&2
  exit 1
fi

if [[ -L "$config" ]]; then
  config="$(realpath "$config")"
fi
if [[ -e "$config" && ! -f "$config" ]]; then
  echo "error: $config must be a file." >&2
  exit 1
fi
mkdir -p "$(dirname "$config")"
staged="$(mktemp "$config.tmp.XXXXXX")"
trap 'rm -f "$staged"' EXIT

input=/dev/null
if [[ -f "$config" ]]; then
  input="$config"
  cp -p "$config" "$staged"
fi

if ! awk -v source="$shortcuts" \
  -v begin='-- BEGIN skills Rex shortcuts' \
  -v finish='-- END skills Rex shortcuts' '
  function emit(    line, status) {
    print begin
    print "do"
    while ((status = getline line < source) > 0) print line
    if (status < 0) exit 1
    close(source)
    print "end"
    print finish
  }
  $0 == begin {
    if (seen) { invalid = 1; exit 1 }
    seen = inside = 1
    offset = count
    next
  }
  $0 == finish {
    if (!inside) { invalid = 1; exit 1 }
    inside = 0
    next
  }
  !inside { lines[++count] = $0 }
  END {
    if (invalid || inside) exit 1
    for (i = 1; i <= offset; i++) print lines[i]
    emit()
    if (!seen && count) print ""
    for (i = offset + 1; i <= count; i++) print lines[i]
  }
' "$input" > "$staged"; then
  echo "error: Could not update the managed block in $config." >&2
  exit 1
fi

"$rex_bin" --autostart=false config check "$staged"
backup=""
changed=false
if ! cmp -s "$staged" "$config"; then
  if [[ -f "$config" ]]; then
    backup="$(mktemp "$config.bak.XXXXXX")"
    cp -p "$config" "$backup"
    echo "Backed up $config to $backup"
  fi
  mv "$staged" "$config"
  changed=true
fi

if "$rex_bin" --autostart=false whoami >/dev/null 2>&1; then
  if ! "$rex_bin" --autostart=false config reload; then
    if [[ "$changed" == true ]]; then
      if [[ -n "$backup" ]]; then
        cp -p "$backup" "$staged"
        mv "$staged" "$config"
      else
        rm "$config"
      fi
    fi
    exit 1
  fi
fi

echo "Rex shortcuts are installed in $config"
