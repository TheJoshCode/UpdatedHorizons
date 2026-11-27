#!/usr/bin/env bash
# Build Distant Horizons for every Minecraft version in src/versionProperties.
# Requires a JDK 25 installation (set JAVA_HOME) and plenty of time/disk.
set -uo pipefail
cd "$(dirname "$0")" || exit 1

export JAVA_HOME="${JAVA_HOME:-/path/to/jdk25}"

versions=(
  1.7.10 1.12.2 1.16.5 1.17.1 1.18.2 1.19.2 1.19.4
  1.20.1 1.20.2 1.20.4 1.20.6 1.21.1 1.21.3 1.21.4 1.21.5
  1.21.6 1.21.8 1.21.9 1.21.10 1.21.11
  26.1.2 26.2.0 26.3.0
)

failed=()
for v in "${versions[@]}"; do
  echo "=== Building Minecraft $v ==="
  if ./gradlew build -PmcVer="$v" --no-daemon --console=plain; then
    echo "=== OK: $v ==="
  else
    echo "=== FAILED: $v ==="
    failed+=("$v")
  fi
done

echo "=== Summary: $((${#versions[@]} - ${#failed[@]}))/${#versions[@]} succeeded ==="
if [ ${#failed[@]} -gt 0 ]; then
  echo "Failed versions: ${failed[*]}"
  exit 1
fi
