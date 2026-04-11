
#!/usr/bin/env bash

pip3 install pandas xlsxwriter

set -euo pipefail

EXCEL_FILE="${1:-}"

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$BASE_DIR/logs"
PID_FILE="$BASE_DIR/benchmark.pid"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/benchmark_$(date +%Y%m%d_%H%M%S).log"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "benchmark already running, pid=$(cat "$PID_FILE")"
  exit 1
fi

CMD=(
  python3 benchmark_serving_multi_turn.py
  --model /models/Qwen3-235B-A22B-Instruct-2507
  --url http://0.0.0.0:9100
  --served-model-name /models/Qwen3-235B-A22B-Instruct-2507
  --input-file new_conversations.json
  --num-clients 64
  --max-active-conversations 64
  --excel-output
  --request-timeout-sec 60000
  --no-early-stop
  --conversation-start-rate 8
  --warmup-step
  --warmup-mode random
)

if [[ -n "$EXCEL_FILE" ]]; then
  CMD+=(--excel-output-file "$EXCEL_FILE")
fi

setsid "${CMD[@]}" >"$LOG_FILE" 2>&1 < /dev/null &
echo $! > "$PID_FILE"

echo "started, pid=$(cat "$PID_FILE")"
echo "log=$LOG_FILE"


# --output-file updated_conversations.json \