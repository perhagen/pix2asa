# PIX-to-ASA Migration Tool — Copilot Instructions

## What this project does

Converts Cisco PIX firewall configurations to ASA 8.4+ format.

A **standalone Python 3 package** with a FastAPI REST API and React UI, designed for a future Rust port.

---

## New Python 3 Package (primary)

### Package layout

```
pix2asa/                    ← installable Python package (pip install -e .)
  __init__.py               ← version 1.0.0
  __main__.py               ← python -m pix2asa support
  data/
    devices.json            ← device model data; shared with future Rust port
  templates/                ← Jinja2 templates (*.j2) for ASA output
  models.py                 ← dataclasses: TargetDevice, InterfaceConfig, ConfigLine, Inspect, Rule
  context.py                ← ConversionContext (all mutable state)
  engine.py                 ← Rule dataclass + Dispatcher (keyword-first O(1) dispatch)
  actions/                  ← handler package (rules, interfaces, nat, conduit, names, etc.)
  rendering.py              ← shared Jinja2 environment + render_template / emit_lines
  converter.py              ← convert(config_text, options) → ConversionResult (pure)
  cli.py                    ← argparse CLI (entry point: pix2asa)
  client.py                 ← HTTP client CLI + Pix2asaClient library
  api.py                    ← FastAPI app
```

### Build & install

```sh
cd /path/to/pix2asa
python3 -m venv .venv && source .venv/bin/activate
pip install -e .          # installs pix2asa + fastapi + uvicorn + pydantic
```

### Running

```sh
# CLI
pix2asa -f configs/pix38.txt -t asa-5520 -o asa.cfg
pix2asa -f configs/pix38.txt -t asa-5520 -d   # debug log to stdout
pix2asa --list-platforms                        # list supported target ASA slugs
pix2asa --serve 8000                            # start FastAPI server

# REST API
uvicorn pix2asa.api:app --reload
```

### CLI flags

| Flag | Description |
|---|---|
| `-f / --input-file FILE` | PIX config to read |
| `-o / --output-file FILE` | Write ASA config here (default: stdout) |
| `-t / --target-platform SLUG` | Target ASA platform (e.g. `asa-5520`) |
| `-m / --map-interface SRC@DST` | Explicit interface mapping (repeatable) |
| `-b / --boot-system-file FILE` | File containing boot system image path |
| `-7 / --pix7` | Source is PIX OS 7.x (default: 6.x) |
| `-5 / --pix5505` | Generate ASA 5505 switch default config |
| `-T / --target-version 84` | ASA target OS version (default: 84) |
| `-d / --debug` | Enable debug logging |
| `-l / --log-file FILE` | Write log to FILE |
| `-a / --append-log-file FILE` | Append log to FILE |
| `--serve [PORT]` | Start REST API server (default port 8000) |
| `--list-platforms` | List supported platform slugs and exit |

### REST API endpoints

```
GET  /api/version           → { "version": "1.0.0" }
GET  /api/devices           → list of { slug, display_name, interfaces, max_vlans }
POST /api/convert           → ConversionResult
  body: {
    config:           string,        # raw PIX config text
    target_platform:  string,        # e.g. "asa-5520"
    source_version:   int (6|7),
    target_version:   int (84),
    interface_map:    {src: dst},    # optional explicit overrides
    custom_5505:      bool,
    boot_system:      string
  }
  response: {
    output:   string,                # converted ASA config
    log:      string,                # INFO/WARNING/ERROR log
    warnings: list[str],
    errors:   list[str]
  }
```

---

## Architecture

### Pattern-matching engine (`engine.py` + `actions/`)

The engine uses a **keyword-first dispatcher**:

- `Rule(keyword, pattern, handler, negated=False)` — frozen dataclass  
  `keyword` = first CLI token (lowercased), used for O(1) bucket lookup  
  `pattern` = pre-compiled `re.Pattern` with **named capture groups throughout**  
  `handler(m: re.Match, ctx: ConversionContext) -> bool`

- `Dispatcher._keyed: dict[str, list[Rule]]` + `_fallback: list[Rule]`  
  `dispatch(line, ctx)` looks up the first token, tries that bucket, then the fallback list.

- Declarative `RULES_COMMON`, `RULES_V6`, `RULES_V7` module-level constants (not inside a function) for easy unit testing of individual rules.

- `negated=True` rules (e.g. `no fixup`) share the same handler via `_neg(handler)` wrapper — no duplicated logic.

**Rust mapping:**
```rust
struct Rule { keyword: &'static str, pattern: Regex, handler: fn(&Captures, &mut Context) -> bool }
// Dispatcher → HashMap<&str, Vec<Rule>>
```

### ConversionContext (`context.py`)

All mutable state lives in a single `ConversionContext` dataclass:

| Field | Purpose |
|---|---|
| `config_lines` | Ordered `ConfigLine` objects for the output pass |
| `interfaces` | `dict[str, InterfaceConfig]` keyed by physical interface name |
| `name_ifs` / `name_ifs_r` | Bidirectional logical name ↔ physical name |
| `logical_to_phys` | PIX 6 nameif mappings |
| `platform_if_mapping` / `_r` | Bidirectional source IF ↔ destination IF |
| `inspects` | `list[Inspect]` for policy-map rendering |
| `vpdn_groups` | PPPoE VPDN groups (must precede interface stanzas) |

`map_interface(src, dst)` always updates both directions. `reset()` clears everything for reuse.

### Device model (`data/devices.json`)

Loaded at module import into `TARGET_DEVICES: dict[str, TargetDevice]`. **The same JSON file will be consumed by the Rust port.**

Adding a new target platform: add an entry to `devices.json` only — no code changes needed.

---

## Rust-port conventions (apply throughout)

- **Full type hints** on every function and dataclass field.
- **`dataclasses.dataclass`** / `pydantic.BaseModel` — no `__dict__` tricks, no `**kwargs`.
- **Enums** for fixed sets: `SourceVersion`, `TargetVersion`.
- **Pure functions** in `actions/` and `converter.py` — receive `ConversionContext` as a parameter.
- **`io.StringIO`** throughout (maps to `std::io::Cursor`).
- **No global state** — `ConversionContext` is the sole carrier of mutable state.
- **`devices.json`** is the single source of truth for platform data.

---

## Key conventions

- **Log message prefixes.** All log output uses `INFO:`, `WARNING:`, or `ERROR:` prefixes via `ctx.log(...)`. Inline config annotations use `::::` prefix (appear in converted output).
- **Interface mapping is always bidirectional.** Use `ctx.map_interface(src, dst)` — updates both directions atomically.
- **Named capture groups everywhere.** Patterns use `(?P<name>...)` syntax. Handlers read `m["name"]`, not `m.group(1)`.
- **`devices.json` is the single source of truth.** Adding a new target platform = add one JSON entry.

---

