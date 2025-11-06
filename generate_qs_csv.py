#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QuickStatements CSV generator, country-aware via harmonize_config.yaml.

Usage:
  python generate_qs_csv.py <input_harmonized.csv> [output_dir]
"""
import os, sys, re, json, hashlib
from decimal import Decimal, InvalidOperation
from pathlib import Path
import pandas as pd
import yaml

# ---------------- CLI ----------------
if len(sys.argv) < 2:
    print("Usage: python generate_qs_csv_updated.py <input_harmonized.csv> [output_dir]")
    sys.exit(1)

INPUT_CSV = sys.argv[1]
OUTPUT_DIR = sys.argv[2] if len(sys.argv) >= 3 else "qs_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)
QS_OUT = os.path.join(OUTPUT_DIR, "qs_transmision_upload_no_p1114.csv")

BASE_DIR = Path(__file__).parent
CFG_PATH = BASE_DIR / "harmonize_config.yaml"

# ---------------- YAML helpers ----------------
def read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def as_time_str(s: str) -> str:
    if not s:
        return ""
    if isinstance(s, str) and s.startswith("+") and s.endswith("/11"):
        return s
    if isinstance(s, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return f"+{s}T00:00:00Z/11"
    return ""

def find_input_block_for_csv(cfg: dict, input_csv_path: str):
    inputs = (cfg or {}).get("inputs", []) or []
    target = os.path.basename(input_csv_path)
    for inp in inputs:
        p = inp.get("path","")
        if p and os.path.basename(p) == target:
            return inp
        if p and os.path.abspath(p) == os.path.abspath(input_csv_path):
            return inp
    stem = os.path.basename(input_csv_path).replace("_harmonized_for_qs.csv","")
    for inp in inputs:
        p = inp.get("path","")
        if p and os.path.basename(p).startswith(stem):
            return inp
    return {}

CFG = read_yaml(CFG_PATH)
INP_BLOCK = find_input_block_for_csv(CFG, INPUT_CSV)
COUNTRY_META = (INP_BLOCK.get("country") if INP_BLOCK else {}) or {}

# ---------------- Constants (schema/units only) ----------------
Q_OVERHEAD_LINE = "Q2144320"   # P31 (overhead power line)
U_METRE         = "U828224"    # unit for P2043
Q_VOLT          = "Q25250"     # volt

# ---------------- Resolve metadata strictly from YAML ----------------
COUNTRY_QID = COUNTRY_META.get("country_qid") or ""
S248_QID    = COUNTRY_META.get("source_qid")  or ""
S854_URL    = COUNTRY_META.get("source_url")  or ""
S813_TIME   = as_time_str(COUNTRY_META.get("access_time","")) or ""

# Explicitly quote URL same as P528
if S854_URL:
    S854_URL = f'"{S854_URL}"'

# ---------------- Column names expected from harmonizer ----------------
COL_QID     = "qid"
COL_CODE    = "Codigo"
COL_TRAMO   = "TRAMO"
COL_VOLTAGE = "Un"
COL_LENGTH  = "Long"
COL_FID     = "_feature_id"
COL_COORDSJ = "_coords_json"

# ---------------- Helpers (robust parsing, same output) ----------------
def plain_decimal(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if not s:
        return ""
    s = s.replace(",", ".")
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return ""
    try:
        d = Decimal(m.group(0))
        return format(d, "f")
    except (InvalidOperation, ValueError):
        return ""

def volts_from_kv(vkv) -> str:
    s = plain_decimal(vkv)
    if not s:
        return ""
    try:
        d = Decimal(s) * Decimal(1000)
        return f"{format(d, 'f')}U{Q_VOLT[1:]}"
    except Exception:
        return ""

def ext_token(fid: str, coords_json: str) -> str:
    basis = f"{fid}|{(coords_json or '')[:256]}"
    return hashlib.sha1(basis.encode("utf-8", "ignore")).hexdigest()[:12]

def coord_from_any(coords_in: str) -> str:
    """
    Return '@lat/lon' for QS P625.
    Accepts JSON [[[lon,lat],...], ...], WKT MULTILINESTRING(...), or WKT LINESTRING(...).
    """
    if not coords_in:
        return ""
    s = coords_in.strip().strip("'").strip('"')

    # 1) JSON
    try:
        geom = json.loads(s)
        pts = [(lon, lat) for line in geom for lon, lat in line]
        if pts:
            lon_mean = sum(p[0] for p in pts) / len(pts)
            lat_mean = sum(p[1] for p in pts) / len(pts)
            return f"@{lat_mean}/{lon_mean}"
    except Exception:
        pass

    # 2) MULTILINESTRING
    m = re.search(r"MULTILINESTRING\s*\(\((.*)\)\)", s, flags=re.I | re.S)
    if m:
        inner = m.group(1)
        segs = re.split(r"\)\s*,\s*\(", inner)
        pts = []
        for seg in segs:
            for pair in seg.split(","):
                parts = pair.strip().split()
                if len(parts) >= 2:
                    try:
                        lon = float(parts[0]); lat = float(parts[1])
                        pts.append((lon, lat))
                    except Exception:
                        continue
        if pts:
            lon_mean = sum(p[0] for p in pts) / len(pts)
            lat_mean = sum(p[1] for p in pts) / len(pts)
            return f"@{lat_mean}/{lon_mean}"

    # 3) LINESTRING
    m = re.search(r"LINESTRING\s*\((.*)\)", s, flags=re.I | re.S)
    if m:
        inner = m.group(1)
        pts = []
        for pair in inner.split(","):
            parts = pair.strip().split()
            if len(parts) >= 2:
                try:
                    lon = float(parts[0]); lat = float(parts[1])
                    pts.append((lon, lat))
                except Exception:
                    continue
        if pts:
            lon_mean = sum(p[0] for p in pts) / len(pts)
            lat_mean = sum(p[1] for p in pts) / len(pts)
            return f"@{lat_mean}/{lon_mean}"

    return ""

def build_row(rec: dict) -> list:
    out = []
    out += [rec["qid"], rec["Len"], rec["Les"], rec["Den"], rec["Des"]]
    out += [Q_OVERHEAD_LINE, S248_QID, S854_URL, S813_TIME]    # P31 + refs
    out += [COUNTRY_QID,   S248_QID, S854_URL, S813_TIME]      # P17 + refs
    out += [rec["P625"],   S248_QID, S854_URL, S813_TIME]      # P625 + refs
    out += [f'"{rec["P528"]}"', S248_QID, S854_URL, S813_TIME] # P528 + refs
    out += [rec["P2436"],  S248_QID, S854_URL, S813_TIME]      # P2436 + refs
    out += [f'+{rec["P2043"]}{U_METRE}' if rec["P2043"] else "", S248_QID, S854_URL, S813_TIME]  # P2043 + refs
    return out

def main():
    df = pd.read_csv(
        INPUT_CSV,
        encoding="utf-8-sig",           # handles BOM safely
        sep=",",
        quotechar='"',
        doublequote=True,
        escapechar="\\",
        engine="python",
        dtype=str,
        keep_default_na=False,
    )

    rows = []
    for _, r in df.iterrows():
        qid = r.get(COL_QID)
        qid_cell = qid if (isinstance(qid, str) and str(qid).startswith("Q")) else ""

        code  = (r.get(COL_CODE) or "").strip()
        tramo = (r.get(COL_TRAMO) or "").strip()

        coords_json = (r.get(COL_COORDSJ) or "").strip()
        coords = coord_from_any(coords_json)

        token = ext_token(str(r.get(COL_FID, "")), coords_json)

        voltage_str = volts_from_kv(r.get(COL_VOLTAGE))
        length_str  = plain_decimal(r.get(COL_LENGTH))

        label = code or "Linea/circuito del SIN"
        desc_text_es = (tramo or "Linea/circuito del SIN de país") + f" [EXT:{token}]"
        desc_text_en = desc_text_es

        rec = {
            "qid": qid_cell,
            "Len": label,
            "Les": label,
            "Den": desc_text_en,
            "Des": desc_text_es,
            "P625": coords,
            "P528": label,
            "P2436": voltage_str,
            "P2043": length_str,
        }
        rows.append(build_row(rec))

    header = [
        "qid","Len","Les","Den","Des",
        "P31","S248","s854","s813",
        "P17","S248","s854","s813",
        "P625","S248","s854","s813",
        "P528","S248","s854","s813",
        "P2436","S248","s854","s813",
        "P2043","S248","s854","s813",
    ]

    pd.DataFrame(rows, columns=header).to_csv(QS_OUT, index=False, encoding="utf-8-sig")
    print(f"[OK] File created: {QS_OUT} ({len(rows)} rows)")

if __name__ == "__main__":
    main()
