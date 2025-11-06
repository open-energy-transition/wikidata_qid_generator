# Wikidata QID Generator

The **Wikidata QID Generator** automates the transformation of national electricity lines and circuits datasets into **QuickStatements (QS)** files for Wikidata batch upload.  
It also provides a generalized method to enrich datasets with Wikidata **QIDs** after upload or for cross-verification.

All stages are managed through the `harmonize_config.yaml` file — enabling reproducible and scalable workflows across datasets such as the ones presents for Colombia in UPME or for Bolivia in their interactive map.

---

## 🧩 Repository Structure

| File | Description |
|------|-------------|
| `harmonize_transmission_data.py` | Harmonizes raw CSVs into a unified schema ready for Wikidata ingestion. |
| `generate_qs_csv.py` | Converts harmonized datasets into **QuickStatements CSVs** for batch upload to Wikidata. |
| `generalized_merge_qids.py` | Enriches harmonized datasets with QIDs from Wikidata once items exist in the database. |
| `harmonize_config.yaml` | Central configuration for file paths, dataset mappings, and Wikidata reference metadata. |

---

## ⚙️ Installation

### Requirements
- Python ≥ 3.9

### Dependencies
```bash
pip install pandas requests pyyaml
```

Optional (for development):
```bash
python -m pip install ruff black
```

---

## 🚀 Workflow Overview

### Step 1: Harmonize the Source Data

Prepare your raw dataset and define its mapping in `harmonize_config.yaml`, then run:

```bash
python harmonize_transmission_data.py
```

This creates a harmonized file such as:

```
upme_lineas_harmonized_for_qs.csv
```

with standardized column order:

```
country,qid,Codigo,TRAMO,Un,Long,_feature_id,_coords_json
```

**Column meanings:**
- `country` — Country of the dataset (e.g., Colombia)
- `qid` — Existing QID if available (blank for new)
- `Codigo` — Unique circuit or line code
- `TRAMO` — Section name or description
- `Un` — Nominal voltage (kV)
- `Long` — Line length (km or m)
- `_feature_id` — Unique hash ID
- `_coords_json` — Line geometry as WKT or JSON (`LINESTRING(...)`)

---

### Step 2: Generate QuickStatements

Once harmonized, create a QuickStatements file for batch upload to Wikidata using:

```bash
python generate_qs_csv.py data/input/upme_lineas_harmonized_for_qs.csv
```

This produces a file such as:

```
qs_transmision_upload_no_p1114.csv
```

Each record includes:
- **P31** → Instance of (e.g., Overhead power line `Q2144320`)
- **P17** → Country
- **P625** → Coordinates
- **P528** → Circuit code or identifier
- **P2436** → Voltage level
- **P2043** → Length
- **S248**, **s854**, **s813** → Source, reference URL, and retrieval date

These statements can be uploaded directly to **[QuickStatements](https://quickstatements.toolforge.org/)** to create new items in Wikidata.

---

### Step 3: Enrich a Dataset with QIDs (Post-Upload)

After uploading to Wikidata, the **`generalized_merge_qids.py`** script can reprocess your harmonized CSVs and insert the QIDs corresponding to newly created items.  
This is useful for maintaining data consistency and enabling bidirectional linkage between local datasets and Wikidata.

#### Basic Command
```bash
python generalized_merge_qids.py --input input_file.csv --output output_file.csv --config harmonize_config.yaml
```

#### What It Does
- Reads the harmonized CSV (UTF-8).  
- Detects or uses declared identifier fields (`Codigo`, `id_circuito`, etc.).  
- Queries Wikidata via SPARQL for existing QIDs using defined properties (`P528`, `P712`).  
- Optionally uses `_feature_id` or `_coords_json` hints (`[EXT:...]`).  
- Writes a new CSV containing an additional `wikidata` column with matched QIDs.  

#### Example Log Output
```
[INFO] Matching properties: P528, P712
[INFO] Code candidates: Codigo, id_circuito
[INFO] Unique codes to resolve: 512
[SUMMARY] rows=512 | with_qid=489 | unresolved=23 | ambiguous=0
[OK] CSV written -> data/output/upme_lineas_enriched.csv
```

---

## 🧾 YAML Configuration Example (`harmonize_config.yaml`)

All stages use the same configuration file for consistency and reproducibility. Whenever a new dataset is added check for the candidates in the columns data to add a new name if missing so that the generator works.

```inputs:
  - path: upme_lineas.csv
    profile: qs_input_schema
    country:
      label: "Colombia"
      country_qid: "Q739"
      source_qid: "Q136714077"              
      source_url: "https://geo.upme.gov.co/server/rest/services/Capas_EnergiaElectrica/Sistema_transmision_lineas_construidas/FeatureServer/17" # TODO
      access_time: "+2025-11-05T00:00:00Z/11"
    columns:
      Long:
        candidates: [longitud_tramo_km, Long, Shape__Length]
        transform: km_to_m
      _coords_json:
        candidates: [location, _coords_json, geometry, wkt]
        transform: to_coords_json
      Un:
        candidates: [tension, Un, nivel_tension_circuito]
        transform: to_number_str
      Codigo:
        candidates: [id_circuito, Codigo, code, CODIGO, ID]
      TRAMO:
        candidates: [nombre_circuito, nombre_trazado, TRAMO, NAME, NOMBRE]

  - path: bolivia_lineas_construidas.csv
    profile: qs_input_schema
    country:
      label: "Bolivia"
      country_qid: "Q750"
      source_qid: "QXXXX_BOLIVIA_DATASET"     # TODO
      source_url: "https://<bolivia-dataset-url>" # TODO
      access_time: "+2025-11-05T00:00:00Z/11"
    columns:
      Long:
        candidates: [longitud_km, Long]
        transform: km_to_m
      _coords_json:
        candidates: [location, _coords_json, geometry, wkt]
        transform: to_coords_json
      Un:
        candidates: [tension_kV, Un]
        transform: to_number_str
      Codigo:
        candidates: [codigo, Codigo, id]
      TRAMO:
        candidates: [tramo, TRAMO, nombre]

profiles:
  qs_input_schema:
    columns:
      qid:
        candidates: [qid, QID]
        transform: passthrough
      Codigo:
        candidates: [Codigo, id_circuito, code, CODIGO, ID]
        transform: passthrough
      TRAMO:
        candidates: [TRAMO, nombre_circuito, nombre_trazado, tramo, NAME, NOMBRE, nombre]
        transform: passthrough
      Un:              # kV in source; QS will convert to V with unit
        candidates: [Un, tension, VOLTAJE_kV, nivel_tension_circuito]
        transform: to_number_str
      Long:            # default assumes metres; override per input if km
        candidates: [Long, length_m, longitud_m, longitud, longitud_tramo_km, long_km]
        transform: m_passthrough
      _feature_id:
        candidates: [_feature_id, fid, OBJECTID, ID_TRAMO, ID_SEGMENTO]
        transform: passthrough
      _coords_json:    # WKT/GeoJSON/array -> MultiLine array JSON
        candidates: [_coords_json, location, geometry, wkt, GEOMETRY]
        transform: to_coords_json

wikidata_merge:
  user_agent: "OET-wikidata-qid-generator/merge (mailto:info@openenergytransition.org)"
  wikidata_match_props: ["P528"]

  # Optional: custom naming heuristics for the code column
  code_candidates: ["Codigo", "codigo", "id_circuito", "Code", "code", "ID", "id"]

  # Optional: control query performance (defaults are good)
  batch_size: 50
  throttle: 3.0
  retries: 5
  backoff: 1.6
  language: "es, en"

```

---

## 📤 Outputs

| File | Description |
|------|-------------|
| `*_harmonized_for_qs.csv` | Standardized dataset ready for QuickStatements generation. |
| `qs_transmision_upload_no_p1114.csv` | Default QuickStatements output file generated by `generate_qs_csv.py`. |
| `*_with_qid.csv` | File enriched with matched Wikidata QIDs (contains a `wikidata` column). |

---

## 🧠 Summary of the Workflow

| Stage | Script | Purpose |
|--------|---------|----------|
| **1. Harmonize Data** | `harmonize_transmission_data.py` | Standardizes datasets to a common structure. |
| **2. Generate QuickStatements** | `generate_qs_csv.py` | Builds CSVs ready for Wikidata batch creation. |
| **3. Merge QIDs** | `generalized_merge_qids.py` | Finds and reinserts Wikidata QIDs for synchronization. |

All steps are configured and controlled from `harmonize_config.yaml`.

---

## 👥 Authors

**Open Energy Transition (OET)**  
<https://openenergytransition.org>

---
