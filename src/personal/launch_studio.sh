#!/bin/bash
is_internal=0
version_dirs=("$HOME"/.var/app/org.vinegarhq.Vinegar/data/vinegar/versions/version-*)
if [[ -e "${version_dirs[0]}" ]]; then
  version_dir=$(printf '%s\n' "${version_dirs[@]}" | sort -V | tail -n 1)
  studio_path="$version_dir/RobloxStudioBeta.exe"
  patched_marker="$version_dir/.patched"
  if [[ -f "$studio_path" && ! -f "$patched_marker" ]]; then
    if [[ -f "$HOME/Documents/EMPLOYEE.exe" ]]; then
      wine "$HOME/Documents/EMPLOYEE.exe" "$studio_path" && touch "$patched_marker"
    else
      echo "EMPLOYEE.exe not found, skipping Studio patch" >&2
    fi
  fi
  [[ -f "$patched_marker" ]] && is_internal=1
fi

rpc_script="$HOME/Documents/RPC.py"
if [[ -f "$rpc_script" ]] && command -v python >/dev/null 2>&1; then
  rpc_args=()
  (( is_internal )) && rpc_args+=(--internal)
  rpc_args+=(--hide-placeid)
  python "$rpc_script" "${rpc_args[@]}" &
else
  echo "RPC.py or python not found, skipping Discord presence" >&2
fi

exec /usr/bin/flatpak run --branch=stable --arch=x86_64 --command=vinegar --file-forwarding org.vinegarhq.Vinegar @@u "$@" @@
