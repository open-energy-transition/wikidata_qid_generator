#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generalized_merge_qids_fixed.py
--------------------------------
Enrich ANY CSV by looking up Wikidata QIDs based on a candidate "code" column.
No harmonized columns required. If `_feature_id` and `_coords_json` exist,
they are used for optional [EXT:...] disambiguation; otherwise skipped cleanly.
"""

import os, time, json, re, argparse, hashlib
from typing import Dict, Any, List, Optional
from pathlib import Path

import pandas as pd
import requests

try:
    import yaml
except Exception:
    yaml = None

SPARQL_URL = "https://query.wikidata.org/sparql"
DEFAULT_USER_AGENT = "OET-wikidata-qid-generator/merge (mailto:info@openenergytransition.org)"
DEFAULT_CODE_CANDIDATES = ["Codigo","codigo","id_circuito","Code","code","ID","id"]

def sha1_token(fid: str, coords_json: str) -> str:
    basis = f"{fid}|{(coords_json or '')[:256]}"
    return hashlib.sha1(basis.encode("utf-8","ignore")).hexdigest()[:12]

def qid_from_uri(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]

def chunked(seq: List[str], n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i+n]

def http_post_sparql(query: str, user_agent: str, retries: int, backoff: float) -> Dict[str, Any]:
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": user_agent or DEFAULT_USER_AGENT,
    }
    attempt = 0
    while True:
        attempt += 1
        try:
            r = requests.post(SPARQL_URL, data={"query": query}, headers=headers, timeout=90)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"Retryable {r.status_code}")
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt >= retries:
                raise
            sleep_s = (backoff ** (attempt - 1)) + 0.1 * attempt
            print(f"[retry {attempt}/{retries}] WDQS -> {e}. Sleep {sleep_s:.1f}s", flush=True)
            time.sleep(sleep_s)

def build_values_list(codes: List[str]) -> str:
    return " ".join(f'"{str(c).replace(chr(34), "")}"' for c in codes if isinstance(c, str) and str(c).strip())

def build_sparql_for_codes(props: List[str], codes: List[str], lang_desc: str) -> str:
    values = build_values_list(codes)
    unions = []
    for p in props:
        p = p.strip()
        if not re.match(r"^P\d+$", p):
            continue
        unions.append(f"?item wdt:{p} ?code .")
    union_block = " UNION ".join("{" + u + "}" for u in unions) if unions else "{ ?item wdt:P528 ?code . }"
    return f"""
SELECT ?item ?code ?desc WHERE {{
  VALUES ?code {{ {values} }}
  {union_block}
  OPTIONAL {{
    ?item schema:description ?desc .
    FILTER (LANG(?desc) = "{lang_desc}")
  }}
}}
"""

def read_merge_cfg(cfg_path: Optional[str]) -> dict:
    defaults = {
        "wikidata_match_props": ["P528"],
        "user_agent": DEFAULT_USER_AGENT,
        "code_candidates": DEFAULT_CODE_CANDIDATES,
        "batch_size": 75,
        "throttle": 3.0,
        "retries": 5,
        "backoff": 1.6,
        "language": "es",
    }
    if not cfg_path or not yaml:
        return defaults
    try:
        cfg = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8")) or {}
    except Exception:
        return defaults
    merge = cfg.get("wikidata_merge", {}) or {}
    for k, v in defaults.items():
        merge.setdefault(k, v)
    if not isinstance(merge.get("wikidata_match_props"), list) or not merge["wikidata_match_props"]:
        merge["wikidata_match_props"] = defaults["wikidata_match_props"]
    if not isinstance(merge.get("code_candidates"), list) or not merge["code_candidates"]:
        merge["code_candidates"] = defaults["code_candidates"]
    return merge

def heuristic_code_candidates(columns: List[str]) -> List[str]:
    ranked = []
    for c in columns:
        score = 0
        cl = c.lower()
        if "codigo" in cl or "código" in cl: score += 3
        if "code" in cl: score += 2
        if "id" == cl or cl.startswith("id_") or cl.endswith("_id"): score += 1
        if "circuit" in cl: score += 1
        if score:
            ranked.append((score, c))
    ranked.sort(reverse=True)
    return [c for _, c in ranked]

def select_code_column(df: pd.DataFrame, override: Optional[str], configured: List[str]) -> str:
    if override and override in df.columns:
        return override
    for c in configured:
        if c in df.columns:
            return c
    guesses = heuristic_code_candidates(df.columns.tolist())
    if guesses:
        print(f"[INFO] Heuristic picked code column: {guesses[0]} (candidates tried: {', '.join(guesses)})")
        return guesses[0]
    raise ValueError("Could not auto-detect a code column. Use --code-col to specify it.")

def main():
    ap = argparse.ArgumentParser(description="Enrich a CSV by merging Wikidata QIDs from identifier matches.")
    ap.add_argument("--input", required=True, help="Input CSV to enrich")
    ap.add_argument("--output", required=True, help="Output CSV with 'wikidata' inserted after the code column")
    ap.add_argument("--config", help="Optional harmonize_config.yaml (reads wikidata_merge section)")
    ap.add_argument("--code-col", help="Override the code column name (e.g., Codigo, id_circuito, code)")
    ap.add_argument("--props", nargs="+", help="Override identifier properties (e.g., P528 P712)")
    ap.add_argument("--lang", help="Description language (default from YAML or 'es')")
    ap.add_argument("--batch-size", type=int, help="Override batch size")
    ap.add_argument("--throttle", type=float, help="Override throttle seconds between batches")
    ap.add_argument("--retries", type=int, help="Override retries")
    ap.add_argument("--backoff", type=float, help="Override exponential backoff base")
    ap.add_argument("--user-agent", help="Override User-Agent header for WDQS")
    args = ap.parse_args()

    df = pd.read_csv(args.input, dtype=str, encoding="utf-8", low_memory=False)
    df.columns = [c.strip() for c in df.columns]

    cfg = read_merge_cfg(args.config)
    match_props = args.props if args.props else cfg["wikidata_match_props"]
    code_candidates = cfg["code_candidates"]
    ua = args.user_agent if args.user_agent else cfg["user_agent"]
    lang = args.lang if args.lang else cfg["language"]
    batch_size = args.batch_size if args.batch_size else cfg["batch_size"]
    throttle = args.throttle if args.throttle else cfg["throttle"]
    retries = args.retries if args.retries else cfg["retries"]
    backoff = args.backoff if args.backoff else cfg["backoff"]

    print(f"[INFO] Matching properties: {', '.join(match_props)}")
    print(f"[INFO] Code candidates: {', '.join(code_candidates)}")
    print(f"[INFO] Using UA: {ua}")
    print(f"[INFO] lang={lang} batch={batch_size} throttle={throttle}s retries={retries} backoff={backoff}")

    code_col = select_code_column(df, args.code_col, code_candidates)

    have_feature = "_feature_id" in df.columns
    have_coords = "_coords_json" in df.columns
    if have_feature and have_coords:
        ext_tokens = [
            sha1_token(str(fid or ""), str(cj or ""))
            for fid, cj in zip(df["_feature_id"].fillna(""), df["_coords_json"].fillna(""))
        ]
    else:
        ext_tokens = [""] * len(df)

    codes = sorted({str(x).strip() for x in df[code_col].fillna("").astype(str) if str(x).strip()})
    print(f"[INFO] Unique codes to resolve: {len(codes)}")

    def build_sparql_for_codes(props: List[str], codes: List[str], lang_desc: str) -> str:
        values = " ".join(f'"{str(c).replace(chr(34), "")}"' for c in codes if isinstance(c, str) and str(c).strip())
        unions = []
        for p in props:
            p = p.strip()
            if not re.match(r"^P\d+$", p):
                continue
            unions.append(f"?item wdt:{p} ?code .")
        union_block = " UNION ".join("{" + u + "}" for u in unions) if unions else "{ ?item wdt:P528 ?code . }"
        return f"""
SELECT ?item ?code ?desc WHERE {{
  VALUES ?code {{ {values} }}
  {union_block}
  OPTIONAL {{
    ?item schema:description ?desc .
    FILTER (LANG(?desc) = "{lang_desc}")
  }}
}}
"""

    code_hits: Dict[str, List[Dict[str, str]]] = {}
    total = 0
    for batch in (codes[i:i+batch_size] for i in range(0, len(codes), batch_size)):
        q = build_sparql_for_codes(match_props, batch, lang)
        start = time.time()
        data = http_post_sparql(q, ua, retries, backoff)
        for b in data.get("results", {}).get("bindings", []):
            code = b.get("code", {}).get("value", "")
            item = b.get("item", {}).get("value", "")
            desc = b.get("desc", {}).get("value", "")
            if code and item:
                code_hits.setdefault(code, []).append({"qid": qid_from_uri(item), "desc": desc or ""})
                total += 1
        elapsed = time.time() - start
        if elapsed < throttle:
            time.sleep(throttle - elapsed)
        print(f"[INFO] batch size={len(batch)} -> cumulative candidates={total}")

    chosen: List[Optional[str]] = []
    unresolved = ambiguous = 0
    for i, row in df.iterrows():
        code = str(row.get(code_col, "")).strip()
        token = ext_tokens[i]
        hits = code_hits.get(code, [])

        if not hits:
            chosen.append("")
            unresolved += 1
            continue

        if len(hits) == 1 or not token:
            chosen.append(hits[0]["qid"]); continue

        tag = f"[EXT:{token}]"
        with_ext = [h for h in hits if tag in h["desc"]]
        if len(with_ext) == 1:
            chosen.append(with_ext[0]["qid"])
        else:
            ambiguous += 1
            chosen.append("")

    df["wikidata"] = chosen
    print(f"[SUMMARY] rows={len(df)} | with_qid={df['wikidata'].astype(bool).sum()} | unresolved={unresolved} | ambiguous={ambiguous}")

    cols = list(df.columns)
    if "wikidata" in cols:
        cols.remove("wikidata")
    if code_col not in cols:
        raise ValueError(f"Code column '{code_col}' not found when arranging columns.")
    insert_at = cols.index(code_col) + 1
    cols.insert(insert_at, "wikidata")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    df[cols].to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[OK] CSV written -> {out}")

if __name__ == "__main__":
    main()
