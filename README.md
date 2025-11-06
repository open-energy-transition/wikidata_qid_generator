# Wikidata QID Generator

A lightweight Python toolset to harmonize national electricity datasets and generate **QuickStatements (QS)** files for batch uploads to **Wikidata**.

This repository provides a reproducible workflow that converts raw GIS or tabular data (e.g., **UPME**, **MHE**, **SIGET**) into properly referenced Wikidata items for power‑grid infrastructure such as **transmission lines**, **substations**, or **power plants**.

---

## Repository Structure

| File | Description |
|------|-------------|
| `harmonize_transmission_data.py` | Harmonizes raw input data into a unified, minimal schema readable by the QS generator. Produces files like `*_harmonized_for_qs.csv`. |
| `generate_qs_csv_updated.py` | Converts harmonized CSVs into **Wikidata QuickStatements** (no `P1114`), using YAML configuration for references/metadata. |
| `harmonize_config.yaml` | Defines country metadata, data sources (QIDs/URLs), access time, and per‑dataset column mappings / transforms. |

---

## ⚙️ Installation

### Requirements
- Python ≥ 3.9

### Dependencies
```bash
pip install pandas pyyaml
```

Optional (for development):
```bash
python -m pip install ruff black
```

---

## 🚀 Usage

### 1) Harmonize the source data

Prepare the raw CSV from your source (e.g., UPME, MHE, SIGET) and configure its mapping in `harmonize_config.yaml` (see **Configuration** below).  
Then run:

```bash
python harmonize_transmission_data.py
```

This creates a harmonized file, for example:

```
upme_lineas_harmonized_for_qs.csv
```

with the following columns **in this exact order**:

```
country,qid,Codigo,TRAMO,Un,Long,_feature_id,_coords_json
```

**Column meanings**
- `country` — human label from YAML (e.g., `Colombia`)
- `qid` — existing Wikidata QID for the asset (leave blank to create new)
- `Codigo` — your dataset’s line/segment code
- `TRAMO` — human‑readable section name/description
- `Un` — nominal voltage (kV by default; see YAML to override)
- `Long` — length (metres or kilometres; convert via mapping)
- `_feature_id` — stable ID (hash) used only to generate a deterministic token for descriptions
- `_coords_json` — geometry as **JSON** (list of coordinates) or **WKT** (`LINESTRING(...)` / `MULTILINESTRING(...)`)

---

### 2) Generate the QuickStatements CSV

Use the harmonized file as input for the generator:

```bash
python generate_qs_csv_updated.py upme_lineas_harmonized_for_qs.csv
```

The output file will be:

```
qs_transmision_upload_no_p1114.csv
```

This file follows the required QuickStatements structure (each property block includes references from YAML):

```
qid,Len,Les,Den,Des,
P31,S248,s854,s813,
P17,S248,s854,s813,
P625,S248,s854,s813,
P528,S248,s854,s813,
P2436,S248,s854,s813,
P2043,S248,s854,s813
```

**Notes**
- `P31` is set to overhead power line (`Q2144320`).
- `P17` (country), `S248` (stated in), `s854` (reference URL), `s813` (access time) are read from YAML.
- `P625` is computed as the centroid of the provided geometry and supports **JSON**, **LINESTRING(...)**, and **MULTILINESTRING(...)**.
- `P2436` (voltage) is emitted in **volts** with unit `U25250`. If your input is kV, set `voltage_unit: kV` (default) in YAML.
- `P2043` (length) is emitted in **metres** with unit `U828224`.

---

## Configuration (`harmonize_config.yaml`)

Your YAML drives both *harmonization* and *QS generation*. The generator matches an input block to the harmonized CSV by **filename stem** (e.g., `upme_lineas.csv` ↔ `upme_lineas_harmonized_for_qs.csv`).

### Minimal example

```yaml
inputs:
  - path: upme_lineas.csv
    profile: qs_input_schema
    country:
      label: "Colombia"
      country_qid: "Q739"           # P17
      source_qid: "Q136714077"      # S248 (UPME dataset/item)
      source_url: "https://geo.upme.gov.co/server/rest/services/.../Sistema_transmision_lineas_construidas/FeatureServer/17"
      access_time: "+2025-11-05T00:00:00Z/11"  # s813
    columns:
      Long:
        candidates: [longitud_tramo_km, Long, Shape__Length]
        transform: km_to_m          # convert km → m
      _coords_json:
        candidates: [location, _coords_json, geometry, wkt]
        transform: to_coords_json   # parse WKT MULTILINESTRING → JSON (fallback keeps raw)
      Un:
        candidates: [tension, Un, nivel_tension_circuito]
        transform: to_number_str
      Codigo:
        candidates: [id_circuito, Codigo, code, CODIGO, ID]
      TRAMO:
        candidates: [nombre_circuito, nombre_trazado, TRAMO, NAME, NOMBRE]
```

> You can add multiple `inputs` blocks—one per dataset (e.g., Bolivia, El Salvador).

---

## Example

**Input (harmonized)**

```
country,qid,Codigo,TRAMO,Un,Long,_feature_id,_coords_json
Colombia,,CARTSMAR2301,LT Cartago - San Marcos 230 kV - 1,230.0,146720.0,c1aa46ab724c,"LINESTRING(-75.9097 4.7291, -76.4866 3.6071)"
```

**Resulting QS (selected fields)**

```
P625:   @4.159668675830926/-76.17644889624685
P2436:  230000.0U25250
P2043:  +146720.0U828224
```

---


## How It Works (Under the Hood)

1. **Harmonization**
   - Robust CSV reader (UTF‑8/BOM).
   - Column detection via candidate lists; value transforms (e.g., `km_to_m`).
   - Optional WKT → JSON conversion for geometries; preserves raw if parsing fails.
   - Emits a minimal, consistent schema for all downstream steps.

2. **QS Generation**
   - Reads metadata from YAML and builds fully referenced QS statements.
   - Geometry parser supports JSON / `MULTILINESTRING` / `LINESTRING`.
   - Tolerant numeric parsing for voltage/length; emits correct QS units.

---

## QuickStatements Tips

- Upload small batches first to validate descriptions/coords.  
- Always include `S248` + `s854` + `s813` for data provenance.  
- Prefer creating **items first** and then adding **statements** to avoid conflicts.

---

## Contributing

PRs are welcome. Please:
- Keep code **idempotent** and **dataset‑agnostic**.
- Avoid hardcoding country‑specific constants in code; use YAML.
- Format with `black`, lint with `ruff`.

---

## 👥 Authors

**Open Energy Transition (OET)**  
<https://openenergytransition.org>

---

## 🪪 License

This project is released under the **MIT License**.
