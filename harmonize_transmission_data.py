#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Harmonize arbitrary transmission CSVs into the QS schema with a leading 'country' column.
Final output columns (in this exact order):
country,qid,Codigo,TRAMO,Un,Long,_feature_id,_coords_json
"""
import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

import pandas as pd
import yaml

TARGET_COLUMNS = ['country','qid','Codigo','TRAMO','Un','Long','_feature_id','_coords_json']

# ---------------- YAML helpers ----------------
def read_yaml(path: Path) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}

# ---------------- CSV helpers ----------------
def strip_bom(s: str) -> str:
    return s.lstrip('\ufeff') if isinstance(s, str) else s

def load_csv_safely(path: Path) -> pd.DataFrame:
    """
    Robust CSV reader that also repairs rows exported as a single giant quoted cell.
    Ensures UTF-8 handling and preserves commas correctly.
    """
    raw = path.read_text(encoding='utf-8', errors='replace')
    lines = raw.splitlines()
    if not lines:
        return pd.DataFrame()

    header = lines[0]
    repaired = [header.lstrip('\ufeff')]
    for line in lines[1:]:
        L = line.strip()
        # Repair case: entire row is quoted and uses doubled quotes for inner quotes
        if len(L) >= 2 and L[0] == '"' and L[-1] == '"' and '""' in L:
            inner = L[1:-1].replace('""','"')
            repaired.append(inner)
        else:
            repaired.append(line)

    try:
        df = pd.read_csv(io.StringIO('\n'.join(repaired)), encoding='utf-8')
    except Exception:
        # Fallback to utf-8-sig if BOM present
        df = pd.read_csv(path, encoding='utf-8-sig')

    df.columns = [strip_bom(c) for c in df.columns]
    return df

# ---------------- Value transforms ----------------
def to_number_str(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val,(int,float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return None
    s = s.replace(',', '.')
    m = re.search(r'[-+]?\d+(?:\.\d+)?', s)
    return float(m.group(0)) if m else None

def km_to_m(val: Any) -> Optional[float]:
    num = to_number_str(val)
    return num*1000.0 if num is not None else None

def extract_kv_from_text(s: str) -> Optional[float]:
    if not isinstance(s,str):
        return None
    m = re.search(r'(\d+(?:\.\d+)?)\s*kV', s, flags=re.I)
    return float(m.group(1)) if m else None

def to_coords_json_from_wkt_multilinestring(wkt: str) -> Optional[str]:
    if not isinstance(wkt,str) or not wkt.strip():
        return None
    text = wkt.strip()
    if text.startswith("'"):
        text = text[1:]
    if text.endswith("'") or text.endswith('"'):
        text = text[:-1]
    m = re.search(r'MULTILINESTRING\s*\(\((.*)\)\)\s*$', text, flags=re.I|re.S)
    if not m:
        return None
    inner = m.group(1)
    segments = re.split(r'\)\s*,\s*\(', inner)
    multilines = []
    for seg in segments:
        pts = []
        for pair in seg.split(','):
            pair = pair.strip()
            if not pair:
                continue
            parts = pair.split()
            if len(parts) >= 2:
                lon = float(parts[0]); lat = float(parts[1])
                pts.append([lon, lat])
        if pts:
            multilines.append(pts)
    return json.dumps(multilines, ensure_ascii=False)

# ---------------- Column mapping ----------------
def first_present(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    cols = set(df.columns)
    for c in candidates:
        cc = strip_bom(c)
        if cc in cols:
            return cc
        # case-insensitive match
        for col in df.columns:
            if col.lower() == cc.lower():
                return col
    return None

def derive_mapping(df: pd.DataFrame, profile_cols: dict, override_cols: dict) -> dict:
    mapping = {}
    for target_col in ['qid','Codigo','TRAMO','Un','Long','_feature_id','_coords_json']:
        spec = (override_cols or {}).get(target_col, {})
        spec_profile = (profile_cols or {}).get(target_col, {})
        candidates = spec.get('candidates') or spec_profile.get('candidates') or [target_col]
        transform = spec.get('transform') or spec_profile.get('transform') or 'passthrough'
        found = first_present(df, candidates)
        mapping[target_col] = {'_col': found, '_transform': transform, '_candidates': candidates}
    return mapping

# ---------------- Row build ----------------
def build_output_row(row: dict, mapping: dict, country_value: str) -> dict:
    qid = str(row.get(mapping['qid']['_col'], '')).strip() if mapping['qid'].get('_col') else ''
    codigo = str(row.get(mapping['Codigo']['_col'], '')).strip()
    tramo = str(row.get(mapping['TRAMO']['_col'], '')).strip()

    un_val = None
    if mapping['Un'].get('_col'):
        un_val = to_number_str(row.get(mapping['Un']['_col']))
    if un_val is None and 'nivel_tension_circuito' in row:
        un_val = extract_kv_from_text(str(row.get('nivel_tension_circuito')))

    long_val = None
    if mapping['Long'].get('_col'):
        if mapping['Long'].get('_transform') == 'km_to_m':
            long_val = km_to_m(row.get(mapping['Long']['_col']))
        else:
            long_val = to_number_str(row.get(mapping['Long']['_col']))
    if long_val is None and 'Shape__Length' in row:
        long_val = to_number_str(row.get('Shape__Length'))

    coords_json = None
    if mapping['_coords_json'].get('_col'):
        if mapping['_coords_json'].get('_transform') == 'to_coords_json':
            raw_geom = str(row.get(mapping['_coords_json']['_col']))
            coords_json = to_coords_json_from_wkt_multilinestring(raw_geom)
            if coords_json is None:
                # fallback: keep raw text if parser fails (e.g., truncated WKT)
                g = (raw_geom or '').strip()
                if g.startswith("'"):
                    g = g[1:]
                if g.endswith("'") or g.endswith('"'):
                    g = g[:-1]
                coords_json = g
        else:
            coords_json = str(row.get(mapping['_coords_json']['_col']) or '').strip() or None

    # stable feature id based on key fields
    h = hashlib.sha1()
    h.update((codigo or '').encode('utf-8'))
    h.update(str(long_val or '').encode('utf-8'))
    h.update((coords_json or '').encode('utf-8'))
    feature_id = h.hexdigest()[:12]

    return {
        'country': country_value or '',
        'qid': qid or '',
        'Codigo': codigo,
        'TRAMO': tramo,
        'Un': un_val if un_val is not None else '',
        'Long': long_val if long_val is not None else '',
        '_feature_id': feature_id,
        '_coords_json': coords_json or ''
    }

# ---------------- Runner ----------------
def run_profile(input_path: Path, profiles: dict, inp_block: dict) -> Path:
    df = load_csv_safely(input_path)

    # Determine profile: explicit or default to 'qs_input_schema' if present
    prof_name = inp_block.get('profile')
    profile = {}
    if prof_name and prof_name in profiles:
        profile = profiles[prof_name]
    elif 'qs_input_schema' in profiles:
        print(f"[WARN] No valid profile specified for {input_path.name}; using 'qs_input_schema'")
        profile = profiles['qs_input_schema']
    else:
        print(f"[WARN] No profile found for {input_path.name}; using empty mapping")
        profile = {'columns': {}}

    profile_cols = (profile or {}).get('columns', {})
    override_cols = (inp_block or {}).get('columns', {})

    mapping = derive_mapping(df, profile_cols, override_cols)

    # Country may be missing; leave blank if not provided
    country_value = ((inp_block or {}).get('country') or {}).get('label') or ''

    records = []
    for _, r in df.iterrows():
        row_dict = {strip_bom(k): r[k] for k in df.columns}
        rec = build_output_row(row_dict, mapping, country_value)
        if rec['Codigo']:
            records.append(rec)

    out_df = pd.DataFrame(records, columns=TARGET_COLUMNS)
    out_path = input_path.with_name(input_path.stem + '_harmonized_for_qs.csv')
    out_df.to_csv(out_path, index=False, encoding='utf-8-sig', quoting=csv.QUOTE_MINIMAL)
    print(f"[INFO] Wrote {len(out_df)} rows -> {out_path}")
    return out_path

def main():
    base = Path(__file__).parent
    yaml_path = base / 'harmonize_config.yaml'
    if not yaml_path.exists():
        print(f'[ERROR] Missing config: {yaml_path}')
        sys.exit(1)

    cfg = read_yaml(yaml_path)
    profiles = cfg.get('profiles', {})
    inputs = cfg.get('inputs', [])
    if not inputs:
        print('[WARN] No inputs configured.')
        return

    for inp in inputs:
        path = Path(inp.get('path',''))
        if not path.is_absolute():
            path = base / path
        if not path.exists():
            print(f'[WARN] Missing file: {path} — skipping')
            continue

        run_profile(path, profiles, inp)

if __name__ == '__main__':
    main()
