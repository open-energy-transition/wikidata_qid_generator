# Wikidata QID Generator

The **Wikidata QID Generator** automates the enrichment of national electricity datasets with corresponding **Wikidata QIDs** and produces **QuickStatements (QS)** for batch upload.  
It supports harmonized CSVs from sources such as **UPME**, **MHE**, or **SIGET**, and can now handle *any properly structured CSV* thanks to the **generalized merge stage**.

---

## 🧩 Repository Structure

| File | Description |
|------|-------------|
| `harmonize_transmission_data.py` | Harmonizes raw CSVs into a standardized schema ready for Wikidata enrichment. |
| `generalized_merge_qids.py` | **New module.** Enriches any CSV file by finding and merging Wikidata QIDs automatically based on identifiers (`Codigo`, `id_circuito`, etc.). |
| `generate_qs_csv_updated.py` | Converts enriched CSVs into QuickStatements CSVs for Wikidata upload. |
| `harmonize_config.yaml` | Configuration file that defines dataset metadata, mappings, and Wikidata merge parameters. |

---

## ⚙️ Installation

### Requirements
- Python ≥ 3.9

### Dependencies
```bash
pip install pandas requests pyyaml
```

---

## 🚀 Usage

### 1. Harmonize the Source Data

Prepare your raw CSVs and run the harmonization step to standardize column names and units:

```bash
python harmonize_transmission_data.py
```

This creates a file such as:
```
upme_lineas_harmonized_for_qs.csv
```

---

### 2. Merge Wikidata QIDs (New Functionality)

The **`generalized_merge_qids.py`** script can enrich *any harmonized CSV* by matching local identifiers to Wikidata QIDs.  
It no longer requires dataset-specific logic — everything is controlled via your YAML configuration or command-line arguments.

#### ✅ Basic command
```bash
python generalized_merge_qids.py   --input data/input/upme_lineas_harmonized_for_qs.csv   --output data/output/upme_lineas_enriched.csv
```

#### 🧠 What it does
- Reads the input CSV using UTF-8 encoding.  
- Detects or infers the correct code column (`Codigo`, `id_circuito`, etc.).  
- Uses SPARQL queries to search Wikidata for matching identifiers.  
- Supports multiple properties (e.g., `P528`, `P712`).  
- Optionally uses `_feature_id` and `_coords_json` for extra disambiguation via `[EXT:...]` tokens.  
- Batches requests to the Wikidata Query Service with throttling and retries.  
- Outputs a new CSV containing an inserted `wikidata` column.  

#### Example output summary
```
[INFO] Matching properties: P528, P712
[INFO] Code candidates: Codigo, id_circuito
[INFO] Unique codes to resolve: 512
[SUMMARY] rows=512 | with_qid=489 | unresolved=23 | ambiguous=0
[OK] CSV written -> data/output/upme_lineas_enriched.csv
```

---

### 3. Generate QuickStatements

Use the enriched CSV as input for the QS generator:

```bash
python generate_qs_csv_updated.py data/output/upme_lineas_enriched.csv
```

This produces a file such as:
```
qs_upme_lineas_no_p1114.csv
```

Each record includes:
- `P31` — instance of (e.g., overhead power line `Q2144320`)
- `P17` — country
- `P625` — coordinates
- `P528` — code or identifier
- `P2436` — voltage
- `P2043` — length
- `S248`, `s854`, `s813` — source references and access time

---

## 🧾 YAML Configuration Example (`harmonize_config.yaml`)

```yaml
wikidata_merge:
  wikidata_match_props: ["P528", "P712"]
  user_agent: "OET-wikidata-qid-generator/1.0"
  code_candidates: ["Codigo", "codigo", "id_circuito", "Code", "code", "ID", "id"]
  batch_size: 75
  throttle: 3.0
  retries: 5
  backoff: 1.6
  language: "es"

datasets:
  - name: upme_lineas
    path: "data/input/upme_lineas_harmonized_for_qs.csv"
    output: "data/output/upme_lineas_enriched.csv"
    match_keys: ["Codigo"]
    wikidata_properties: ["P528", "P712"]
    schema:
      country: "Colombia"
      P17: "Q739"
      P31: "Q2144320"
      S248: "Q136714077"
      s854: "https://geo.upme.gov.co/layers/geonode:transmision_sin_20250131"
      s813: "+2025-10-16T00:00:00Z/11"
```

---

## 🧠 Notes

- The merge process can handle **any CSV** with an identifiable code column.  
- `_feature_id` and `_coords_json` are optional but improve match accuracy.  
- The script automatically detects candidate code fields when not specified.  
- SPARQL batches are throttled to avoid WDQS rate limits.

---

## 📤 Outputs

| File | Description |
|------|-------------|
| `*_harmonized_for_qs.csv` | Standardized dataset ready for enrichment. |
| `*_enriched.csv` | QID-enriched file after `generalized_merge_qids.py`. |
| `*_qs_no_p1114.csv` | Final QuickStatements file for Wikidata upload. |

---

## 🧩 Summary of New Functionality

| Feature | Description |
|----------|-------------|
| **Generalized QID Merge** | A universal enrichment script that handles any dataset with a known identifier. |
| **Config-Driven Workflow** | Fully managed through YAML — no code edits required. |
| **Automatic Field Detection** | Finds `Codigo` or equivalent columns heuristically. |
| **SPARQL Optimization** | Batch requests with retry/backoff control. |
| **Scalable** | Works for transmission lines, substations, generators, or any infrastructure type. |

---

## 👥 Authors

**Open Energy Transition (OET)**  
<https://openenergytransition.org>

---
