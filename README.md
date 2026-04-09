# NEXUS ROUTE

NEXUS ROUTE is a delivery route planning platform for cargo distribution centers. It takes address files, assigns or preserves distribution centers, calculates efficient delivery sequences, and generates both overview and per-vehicle route maps.

It is built for operations that start from one or more depots and need to deliver many packages to many addresses with practical constraints such as vehicle count, vehicle capacity, center coverage, Google Maps navigation, and operator notes.

## What It Does

- Accepts uploaded address files in CSV, Excel, JSON, GeoJSON, NDJSON, and text-derived formats
- Normalizes incoming data into a consistent routing schema
- Preserves existing center assignments by default, with optional nearest-center reassignment
- Optimizes routes with a local solver, Google routing, or automatic fallback
- Shows recommended minimum vehicle count and capacity guidance before the run
- Renders a main route map plus individual vehicle route maps
- Adds ordered stop numbering directly on the map
- Generates Google Maps navigation links for each stop and each vehicle route
- Uses Gemini to extract operational constraints and summarize route warnings

## Who It Is For

- Courier companies
- Urban last-mile delivery teams
- Multi-depot distribution operations
- Dispatchers who need a practical route plan instead of a generic map

## How It Works

1. Upload an address file in the web UI.
2. The app normalizes every record into a standard schema.
3. Stops are grouped by distribution center.
4. The system estimates required fleet size and capacity per center.
5. A routing provider is selected:
   - `local`: deterministic local optimization
   - `google`: Google-powered routing
   - `auto`: Google first, local fallback if needed
6. The platform generates:
   - `route_plan.json`
   - `metrics.json`
   - `route_map.html`
   - one HTML map per vehicle
7. Operators can inspect the route order, open Google Maps links, and review AI-generated operational notes.

## Routing Providers

### Local

The local provider uses a deterministic routing pipeline with exact solving for small route sets and heuristic solving for larger sets. It also includes:

- dynamic graph generation
- GraphML graph caching
- distance matrix caching
- geodesic fallback when road-network generation is too expensive
- center coverage checks

### Google

The Google provider supports two modes:

- Google Route Optimization API when `GOOGLE_ROUTE_OPTIMIZATION_PARENT` is available
- Google Routes API fallback for stop ordering and road geometry when only a standard Google Maps API key is available

This means you can still use Google-backed routing even if you do not have the full fleet optimization product configured yet.

## Gemini Copilot

Gemini is used for operational support, not for replacing the route solver.

Current copilot use cases:

- extract structured delivery constraints from free-text operation notes
- summarize route warnings and failed delivery patterns

## Quick Start

### 1. Clone the repository

```bash
git clone git@github.com:phinn12/NexusRoute.git
cd NexusRoute
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

You can run the project locally without Google or Gemini keys. Those integrations are optional.

### 4. Start the backend

```bash
./run_backend.sh
```

Default backend URL:

```text
http://127.0.0.1:8010
```

### 5. Start the Streamlit UI

Open a second terminal:

```bash
./run_streamlit.sh
```

Default UI URL:

```text
http://127.0.0.1:8501
```

## Example Input File

An example file is included here:

- `examples/sample_addresses.csv`

Expected normalized columns:

```text
id,merkez,mahalle,cadde_sokak,bina_adı,bina_no,kat,daire_no,formatted_address,lat,lng
```

You can upload the sample file directly from the UI and run a full test route.

## Recommended Test Flow

1. Start the backend and UI.
2. Upload `examples/sample_addresses.csv`.
3. Keep `preserve centers` enabled.
4. Try `local` first.
5. Review the recommended minimum vehicle counts shown in the UI.
6. Click `Create Route`.
7. Open:
   - the main route map
   - each vehicle map
   - the ordered stop list
8. If you want Google-backed routing:
   - enter a Google Maps API key in the sidebar
   - select `google` or `auto`
9. If you want AI assistance:
   - enter a Gemini API key
   - use the operations note box

## Example Outputs

Each routing job writes artifacts under:

```text
yerelden_output/jobs/<job_id>/
```

Typical outputs:

- `normalized.csv`
- `route_plan.json`
- `metrics.json`
- `route_map.html`
- `vehicle_maps/<vehicle>.html`

## Web UI Highlights

- file upload and normalization preview
- center-aware vehicle configuration
- recommended minimum vehicle count
- required capacity guidance
- numbered route markers
- Google Maps links per stop
- route-level Google Maps link per vehicle
- main map plus per-vehicle map viewers
- Gemini-powered operational note assistant

## API Endpoints

The backend exposes:

- `POST /api/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/artifacts`
- `POST /api/copilot/extract-constraints`
- `POST /api/copilot/summarize-failures`

## Repository Layout

```text
NexusRoute/
├── kargo_backend/          # FastAPI backend, routing providers, rendering, storage
├── tests/                  # unit and integration tests
├── examples/               # sample input files
├── web_normalize.py        # Streamlit frontend
├── normalize_addresses.py  # data normalization pipeline
├── process_local_inbox.py  # batch file ingestion
├── run_backend.sh
├── run_streamlit.sh
├── run_all.sh
├── requirements.txt
└── merkez_koordinatlari.json
```

## Environment Variables

Key variables are documented in `.env.example`.

Most important ones:

- `BACKEND_HOST`
- `BACKEND_PORT`
- `BACKEND_BASE_URL`
- `GOOGLE_MAPS_API_KEY`
- `GOOGLE_ROUTE_OPTIMIZATION_PARENT`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `OUTPUT_DIR`
- `GRAPH_CACHE_DIR`

## Production Deployment

For Linux deployment, the repository also includes:

- `kargo-api.service`
- `kargo-streamlit.service`
- `nginx.conf.example`
- `full_setup.sh`
- `setup_nginx.sh`

These files are intended for systemd + Nginx deployments.

## Testing

Run the test suite:

```bash
pytest -q
```

## Why This Project Exists

NEXUS ROUTE exists to solve a real operational problem:

- packages arrive at one or more distribution centers
- addresses come from inconsistent file formats
- fleets have hard limits
- dispatchers need a route that is practical, visible, and fast to act on

This project turns that process into a repeatable workflow with clear operational outputs instead of ad-hoc manual planning.
