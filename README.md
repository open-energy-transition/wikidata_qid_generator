# Wikidata QID Generator

A lightweight Python toolset to harmonize national electricity datasets and generate **QuickStatements (QS)** files for batch uploads to **Wikidata**.

This repository provides a reproducible workflow that converts raw GIS or tabular data (e.g., **UPME**, **MHE**, **SIGET**) into properly referenced Wikidata items for power-grid infrastructure such as **transmission lines**, **substations**, or **power plants**.

---

## Repository Structure

| File | Description |
|------|-------------|
| `harmonize_transmission_data.py` | Harmonizes raw input data into a unified schema readable by the QS generator. Produces files like `*_harmonized_for_qs.csv`. |
| `generalized_merge_qids.py` | **New module.** Merges Wikidata QIDs into harmonized CSVs based on configured matching properties. Supports any dataset defined in `harmonize_config.yaml`. |
| `generate_qs_csv_updated.py` | Converts harmonized or enriched CSVs into **Wikidata QuickStatements** (no `P1114`), using YAML configuration for references and metadata. |
| `harmonize_config.yaml` | Defines country metadata, data sources (QIDs/URLs), access time, and per-dataset column mappings and Wikidata match properties. |

---

## ⚙️ Installation

### Requirements
- Python ≥ 3.9

### Dependencies
```bash
pip install pandas pyyaml requests
```

Optional (for development):
```bash
python -m pip install ruff black
```

---

## Usage

### 1) Harmonize the Source Data

Prepare the raw CSV from your source dataset and configure its mapping in `harmonize_config.yaml`.  
Then run:

```bash
python harmonize_transmission_data.py
```

This creates a harmonized file, for example:

```
upme_lineas_harmonized_for_qs.csv
```

with standardized column order:

```
country,qid,Codigo,TRAMO,Un,Long,_feature_id,_coords_json
```

**Column meanings:**
- `country` — country name from YAML (e.g., `Colombia`)
- `qid` — existing Wikidata QID for the asset (leave blank to create new)
- `Codigo` — unique dataset code or circuit ID
- `TRAMO` — human-readable section name/description
- `Un` — nominal voltage (kV by default)
- `Long` — line length (metres or kilometres)
- `_feature_id` — deterministic unique ID (hash)
- `_coords_json` — geometry as JSON or WKT (`LINESTRING(...)`)

---

### 2) Merge Wikidata QIDs (New Generalized Stage)

The **`generalized_merge_qids.py`** script replaces dataset-specific merge logic.  
It reads harmonized CSVs, matches codes against Wikidata, and merges existing QIDs automatically.

Run:
```bash
python generalized_merge_qids.py
```

#### Functionality
- Reads dataset definitions from `harmonize_config.yaml`
- Loads each harmonized CSV
- Uses declared matching properties (e.g., `P528`, `P712`) to query Wikidata
- Matches on identifiers (e.g., `Codigo`, `id_circuito`)
- Merges discovered QIDs into the dataset
- Produces a unified summary:
  ```
  [SUMMARY] rows=512 | with_qid=489 | unresolved=23 | ambiguous=0
  ```

#### Example YAML Definition
```yaml
datasets:
  - name: upme_lineas
    path: data/input/upme_lineas_harmonized_for_qs.csv
    output: data/output/upme_lineas_enriched.csv
    match_keys: ["Codigo", "id_circuito"]
    wikidata_properties: ["P528", "P712"]
```

#### Output
- Enriched CSV with QIDs merged back (`*_enriched.csv`)
- Summary logs of matched, unresolved, and ambiguous entries
- Ready-to-use input for the next stage (`generate_qs_csv_updated.py`)

---

### 3) Generate QuickStatements

Use the enriched file as input for QS generation:

```bash
python generate_qs_csv_updated.py upme_lineas_enriched.csv
```

This creates a file like:
```
qs_upme_lineas_no_p1114.csv
```

Each statement includes:
- Instance type (`P31`)
- Country (`P17`)
- Coordinates (`P625`)
- Code or identifier (`P528`)
- Voltage (`P2436`)
- Length (`P2043`)
- Full reference metadata (`S248`, `s854`, `s813`)

---

## 🔧 Configuration Example (`harmonize_config.yaml`)

Updated format supporting the generalized merge logic:

```yaml
wikidata:
  endpoint: "https://query.wikidata.org/sparql"
  user_agent: "OET-wikidata/1.0"

datasets:
  - name: upme_lineas
    path: "data/input/upme_lineas_harmonized_for_qs.csv"
    output: "data/output/upme_lineas_enriched.csv"
    match_keys: ["Codigo"]
    wikidata_properties: ["P528"]
    schema:
      country: "Colombia"
      P17: "Q739"
      P31: "Q2144320"
      S248: "Q136714077"
      s854: "https://geo.upme.gov.co/layers/geonode:transmision_sin_20250131"
      s813: "+2025-10-16T00:00:00Z/11"
```

You can define multiple datasets under the same YAML, each with its own structure and Wikidata matching configuration.

---

### 4) Outputs

After running all stages, your output folder will contain:

| File | Description |
|------|-------------|
| `*_harmonized_for_qs.csv` | Standardized dataset ready for enrichment. |
| `*_enriched.csv` | QID-merged file after `generalized_merge_qids.py`. |
| `*_qs_no_p1114.csv` | QuickStatements upload file. |

---

## 🧠 Summary of the New Functionality

| Feature | Description |
|----------|-------------|
| **Generalized QID Merge** | One script (`generalized_merge_qids.py`) handles QID enrichment for all datasets defined in YAML. |
| **Config-Driven Logic** | No hardcoding — datasets, key fields, and matching Wikidata properties are all declared in YAML. |
| **Automatic Reporting** | Prints counts of matched/unresolved items. |
| **Scalable Architecture** | Easily extendable to other infrastructure layers (e.g., substations, generators). |

---

## Authors
**Open Energy Transition (OET)**  
<https://openenergytransition.org>

---
