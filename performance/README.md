# ABAC performance harness

Seeds a synthetic dataset (default 1M resources in graph A, 200k in graph B) into a
dedicated `abac_perf` database and benchmarks every rule type plus the framework.
Not part of CI (lives outside `tests/`). No product code is touched.

## Setup

```bash
python -m venv ~/.venvs/abac-perf && . ~/.venvs/abac-perf/bin/activate
pip install --upgrade pip && pip install . --group dev   # arches from PyPI

# credentials come from the environment only; the DB user needs CREATEDB
export ABAC_PERF_DB_USER=... ABAC_PERF_DB_PASSWORD=...
# optional: ABAC_PERF_DB_HOST (localhost), ABAC_PERF_DB_PORT (5418)
export DJANGO_SETTINGS_MODULE=performance.settings
export ABAC_PERF_SIZE=1k    # must match --size below; selects database and scale
```

## Sizes

`ABAC_PERF_SIZE` picks the preset and the database (`abac_perf_<size>`, except `1m` -> `abac_perf`).
`--size` (default `1k`) on both commands must match it.

| Size | Graph A | Graph B | "High" = every Nth | Set sizes |
|---|---|---|---|---|
| `1k` | 1,000 | 200 | 250 | 10 / 100 / 500 |
| `50k` | 50,000 | 10,000 | 1,000 | 500 / 5,000 / 25,000 |
| `100k` | 100,000 | 20,000 | 2,500 | 1,000 / 10,000 / 50,000 |
| `1m` | 1,000,000 | 200,000 | 10,000 | 100 / 10,000 / 500,000 |

**Safety:** both commands refuse to run unless `DEBUG` is True (`performance/settings.py` sets it) and the
database name starts with `abac_perf`.

## Seed

```bash
python manage.py abac_perf_seed --size 1k [--recreate]
```

- Creates the database from `template_postgis` if missing, runs `migrate`, then seeds.
  Refuses an already-seeded database unless `--recreate` (drops and rebuilds it).
- Bulk SQL (`generate_series`); graphs, nodes, lifecycle and resource sets via the ORM.
- Adds the `es` language; creates its own 3-state lifecycle (70/20/10 split).
- Arches has no trigger filling `geojson_geometries`; the seed runs an INSERT equivalent to
  `refresh_geojson_geometries()` limited to geometry nodes.
- Two per-row `tiles` triggers (excess-tile check, spatial-views update) are disabled
  during the bulk insert and re-enabled afterwards.
- Ends with `VACUUM ANALYZE`. `1m` takes ~43 minutes; `1k` about 20 seconds.

## Run

```bash
python manage.py abac_perf_run --size 1k --repeat 5 --output results.json \
    [--only lifecycle_state|resource_set|tile_node_value|spatial|framework] \
    [--with-indexes | --without-indexes] [--timeout 180] [--resume] \
    [--framework-counts 0,1,5,20] [--ops matches_,count,e_]
```

- Default runs both variants (without, then with the `get_index_sql` indexes, built in `abac_perf` only).
- A case whose first run exceeds 2s stops after 2 runs; `runs` is recorded per case.
- `--resume` keeps and skips finished results in `--output`; the file is rewritten after every case.
- Rules, user and group created by the run are removed afterwards.
- `--framework-counts`: rule counts for the framework cases (default `0,1,5,20`).
- `--ops`: comma-separated op-name prefixes to run (e.g. `matches_,e_,f_`).
