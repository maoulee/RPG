#!/usr/bin/env bash
# Start the Freebase Virtuoso SPARQL endpoint (:8890) serving the 148GB dump.
# Usage: bash scripts/start_freebase_virtuoso.sh   (backgrounds itself; tail the log)
set -e
VIRT_ENV=/root/miniconda3/envs/virt
DB_DIR=/zhaoshu/_data_archive/virtuoso_db
INI=$DB_DIR/virtuoso.ini
LOG=$DB_DIR/virtuoso.run.log

if ! ss -ltn 2>/dev/null | grep -q ":8890 "; then
  echo "[start] launching virtuoso-t (foreground-to-bg)..."
  cd "$DB_DIR"
  nohup "$VIRT_ENV/bin/virtuoso-t" -f -c "$INI" > "$LOG" 2>&1 &
  echo "[start] PID $! ; warming up the 148GB DB (can take 5-20 min before SPARQL answers)"
else
  echo "[start] port 8890 already in use — Virtuoso may already be running."
fi

echo "[wait] polling SPARQL endpoint until it answers a Freebase query..."
for i in $(seq 1 240); do
  ANS=$(curl -s --max-time 10 -G "http://localhost:8890/sparql" \
        --data-urlencode 'query=SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o } LIMIT 1' \
        -H "Accept: application/sparql-results+json" 2>/dev/null || true)
  if echo "$ANS" | grep -q '"value"'; then
    echo "[ready] Virtuoso SPARQL up. Triple count response:"
    echo "$ANS" | head -c 400; echo
    exit 0
  fi
  sleep 5
done
echo "[TIMEOUT] endpoint did not answer in 20 min. Tail of run log:"
tail -20 "$LOG"
exit 1
