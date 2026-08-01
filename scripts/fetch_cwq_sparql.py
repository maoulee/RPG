#!/usr/bin/env python3
"""Fetch all drt/complex_web_questions train+val rows (ID, sparql, answers...)
via the HF datasets-server /rows API (paginated JSON; bypasses the Dropbox raw
files and the script-loader). Saves data/cwq_sparql_full/{split}.json as a
{ID: {sparql, question, ...}} map, usable as the gold-query source for the
SPARQL-driven train repair."""
import argparse, json, os, sys, time
import requests

DS = "https://datasets-server.huggingface.co/rows"
DATASET = "drt/complex_web_questions"
OUT = "/zhaoshu/subgraph/data/cwq_sparql_full"


def fetch_split(split, config="complex_web_questions", length=100):
    os.makedirs(OUT, exist_ok=True)
    out = {}
    offset = 0
    # first call to get total
    j = None
    for a in range(8):
        try:
            r = requests.get(DS, params={"dataset": DATASET, "config": config,
                                         "split": split, "offset": 0, "length": length},
                             timeout=40)
            if r.status_code == 200:
                j = r.json(); break
            print(f"  [0] status {r.status_code}", flush=True)
        except Exception as e:
            print(f"  [0] retry {a}: {str(e)[:60]}", flush=True)
        time.sleep(3)
    if j is None:
        sys.exit(f"could not fetch first page of {split}")
    total = j.get("num_rows_total", 0)
    print(f"[{split}] total={total}", flush=True)
    for rr in j.get("rows", []):
        row = rr["row"]; out[row["ID"]] = row
    offset += len(j.get("rows", []))
    while offset < total:
        ok = False
        for a in range(6):
            try:
                r = requests.get(DS, params={"dataset": DATASET, "config": config,
                                             "split": split, "offset": offset, "length": length},
                                 timeout=40)
                if r.status_code == 200:
                    rows = r.json().get("rows", [])
                    for rr in rows:
                        row = rr["row"]; out[row["ID"]] = row
                    offset += len(rows); ok = True; break
            except Exception:
                pass
            time.sleep(2)
        if not ok:
            print(f"  stuck at offset {offset}, skipping page", flush=True)
            offset += length
        if offset % 2000 == 0 or offset >= total:
            print(f"  [{split}] {offset}/{total}", flush=True)
    # slim down: keep only sparql + question + answers + webqsp_ID
    slim = {k: {"sparql": v.get("sparql", ""), "question": v.get("question", ""),
                "answers": v.get("answers"), "webqsp_ID": v.get("webqsp_ID")}
            for k, v in out.items()}
    p = os.path.join(OUT, f"{split}.json")
    json.dump(slim, open(p, "w"))
    print(f"[{split}] wrote {len(slim)} -> {p} ({os.path.getsize(p)//1024} KB)", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", default="train,validation")
    args = ap.parse_args()
    for sp in args.splits.split(","):
        fetch_split(sp.strip())
