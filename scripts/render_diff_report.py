"""Side-by-side render diff: ORIGINAL (recorded run) vs NEW (replayed with
the selected-path reconstruction renderer), per sg block, no LLM involved
(the replay feeds the recorded assistant messages verbatim).

Pairs each retrieve_subgraph assistant call (the anchor) with its tool
response in BOTH trajectories and emits both renderings under it. Non-sg
messages are skipped (only the sg rendering changed). For the 12 scored
audit trajectories (or --cases with case prefixes).

Usage: python scripts/render_diff_report.py <recorded.json> <replay_dump.json> \
    --out specs/render_diff_2026-09-19.md
"""
import ast
import json
import sys

SG_HEAD = ("triples:", "fact_id:")


def load_trajs(path):
    recs = json.load(open(path))
    out = {}
    order = []
    for rec in recs:
        tr = rec["trajectory"]
        if isinstance(tr, str):
            tr = ast.literal_eval(tr)
        key = (rec["case_id"], str(rec.get("sample_idx")))
        out[key] = tr
        if rec["case_id"] not in order:
            order.append(rec["case_id"])
    return out, order


def load_replay(path):
    d = json.load(open(path))          # "ci|si" -> [[role, content], ...]
    return {tuple(k.split("|")): v for k, v in d.items()}, d


def sg_pairs(tr):
    """[(assistant_call_content, tool_response_content), ...] in order."""
    pairs = []
    i = 0
    while i < len(tr):
        m = tr[i]
        if m["role"] == "assistant" and "tool: retrieve_subgraph" in m["content"]:
            j = i + 1
            resp = None
            while j < len(tr) and tr[j]["role"] != "assistant":
                c = tr[j]["content"]
                if c.startswith(SG_HEAD) or "layer_action" in c \
                        or c.startswith('{"error'):
                    resp = c
                j += 1
            pairs.append((m["content"], resp))
            i = j
        else:
            i += 1
    return pairs


def call_head(call):
    c = next((l for l in call.split("\n") if l.startswith("center:")), "")
    r = next((l for l in call.split("\n") if l.startswith("relations:")), "")
    return f"{c.strip()}  |  {r.strip()[:130]}"


def stats(content):
    if content is None:
        return "(无 sg 响应)"
    if content.startswith('{"error') or content.startswith("error:"):
        return f"[错误响应] {content[:100]}"
    pats = next((l for l in content.split("\n")
                 if l.startswith("▸ patterns:")), "")
    n_pat = len(pats[len("▸ patterns:"):].split(" | ")) if pats else 0
    n_blk = sum(1 for l in content.split("\n") if l.startswith("── "))
    return f"模式 {n_pat} · 证据块 {n_blk} · {len(content)} 字符"


def main():
    rec_path, rep_path = sys.argv[1], sys.argv[2]
    out_path = "specs/render_diff_2026-09-19.md"
    picked = None
    for a in sys.argv[3:]:
        if a == "--out":
            out_path = sys.argv[sys.argv.index(a) + 1]
        if a == "--cases":
            picked = sys.argv[sys.argv.index(a) + 1].split(",")
    recs, order = load_trajs(rec_path)
    replay, raw = load_replay(rep_path)
    targets = json.load(open("specs/layer_op_probs_2026-09-17.json"))
    keys = sorted(targets.keys())
    with open(out_path, "w") as f:
        f.write("# 渲染对比：原始 vs 选中路径重建器（无 LLM 回放，逐块并排）\n\n"
                "锚点 = 同一条 retrieve_subgraph 调用（重放逐字喂入录制的 "
                "assistant 消息）。【旧】= v06_aligned 录制渲染；"
                "【新】= 选中路径重建器渲染。其余消息类型未变，不列。\n\n")
        for k in keys:
            cid, s = k.rsplit("|s", 1)
            if picked and not any(cid.startswith(p) for p in picked):
                continue
            ci = str(order.index(cid))
            rk = replay.get((ci, s))
            if rk is None:
                f.write(f"\n## {cid[:26]} s{s}: 重放缺失（case_idx {ci}）\n")
                continue
            old_tr = recs[(cid, s)]
            new_tr = [dict(role=a, content=b) for a, b in rk]
            old_pairs = sg_pairs(old_tr)
            new_pairs = sg_pairs(new_tr)
            f.write("\n" + "=" * 92 + "\n")
            f.write(f"## CASE {cid} s{s}\n")
            rec = next(r for r in json.load(open(rec_path))
                       if r["case_id"] == cid and str(r.get("sample_idx")) == s)
            f.write(f"Q: {rec.get('question','')[:100]}  f1={rec.get('f1')}\n")
            f.write(f"sg 调用数: 旧 {len(old_pairs)} / 新 {len(new_pairs)}\n\n")
            for i in range(max(len(old_pairs), len(new_pairs))):
                call_o = old_pairs[i][0] if i < len(old_pairs) else None
                call_n = new_pairs[i][0] if i < len(new_pairs) else None
                resp_o = old_pairs[i][1] if i < len(old_pairs) else None
                resp_n = new_pairs[i][1] if i < len(new_pairs) else None
                f.write("-" * 92 + "\n")
                f.write(f"### 块 #{i} 调用: {call_head(call_n or call_o or '')}\n")
                f.write(f"旧: {stats(resp_o)}\n新: {stats(resp_n)}\n\n")
                f.write("【旧渲染】\n```\n"
                        + (resp_o or "(无)")[:4000] + "\n```\n")
                f.write("【新渲染】\n```\n"
                        + (resp_n or "(无)")[:4000] + "\n```\n\n")
    print("wrote", out_path)


if __name__ == "__main__":
    main()
