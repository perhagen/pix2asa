# pix2asa

Convert Cisco PIX firewall configurations to ASA format.

A **standalone Python 3** tool with a FastAPI REST API, React UI, and designed for a future Rust port.

---

## Table of Contents

1. [CLI Reference](#cli-reference)
2. [HTTP Client Reference](#http-client-reference)
3. [REST API Reference](#rest-api-reference)
4. [React UI](#react-ui)
5. [Library Usage](#library-usage)
6. [Architecture](#architecture)
7. [Module Reference](#module-reference)
8. [Pattern-Matching Engine](#pattern-matching-engine)
9. [Device Model](#device-model)
10. [Rust Port Guide](#rust-port-guide)
11. [Sample Configs](#sample-configs)
12. [License](#license)


See [INSTALL.md](INSTALL.md) for installation instructions and [requirements.txt](requirements.txt) for pinned dependencies.

---

## CLI Reference

```
pix2asa [OPTIONS]
```

| Flag | Description |
|---|---|
| `-f / --input-file FILE` | PIX config to read (stdin not yet supported) |
| `-o / --output-file FILE` | Write converted ASA config here (default: stdout) |
| `-t / --target-platform SLUG` | Target ASA platform slug (see `--list-platforms`) |
| `-m / --map-interface SRC@DST` | Explicit interface mapping, repeatable. Implies `--target-platform custom`. E.g. `ethernet0@GigabitEthernet0/0` |
| `-b / --boot-system-file FILE` | File containing the ASA boot system image path |
| `-7 / --pix7` | Source config is PIX OS 7.x (default: 6.x) |
| `-5 / --pix5505` | Emit ASA 5505 embedded-switch default configuration stanzas |
| `-T / --target-version 84` | Target ASA OS version (default: `84` for ASA 8.4+) |
| `-d / --debug` | Print log to stdout along with the converted config |
| `-l / --log-file FILE` | Write log to FILE (overwrite) |
| `-a / --append-log-file FILE` | Append log to FILE |
| `--serve [PORT]` | Start the REST API server on PORT (default 8000). Blocks. |
| `--list-platforms` | Print all supported target platform slugs and exit |
| `--version` | Print version and exit |

### Examples

```sh
# Basic conversion
pix2asa -f pix.cfg -t asa-5520

# PIX 7.x source, save log separately
pix2asa -f pix7.cfg -t asa-5540 -7 -o asa.cfg -l conversion.log

# Explicit interface remapping (custom platform)
pix2asa -f pix.cfg \
  -m ethernet0@GigabitEthernet0/0 \
  -m ethernet1@GigabitEthernet0/1 \
  -o asa.cfg

# Launch REST API on port 9000
pix2asa --serve 9000
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success (no errors) |
| `1` | Conversion completed but one or more `ERROR:` lines were emitted |

---

## HTTP Client Reference

`pix2asa-client` is a companion CLI that mirrors the standalone `pix2asa` command but sends work to a running API server. It can also fall back to local conversion when the server is unavailable.

Start the server first, then run the client:
```sh
pix2asa --serve 8000 &
pix2asa-client -f pix.cfg -t asa-5520
```

### Synopsis

```
pix2asa-client [SERVER OPTIONS] [CONVERSION OPTIONS]
```

### Server options

| Flag | Default | Description |
|---|---|---|
| `--server URL` | `http://localhost:8000` | pix2asa API server base URL |
| `--timeout SECONDS` | `30.0` | HTTP request timeout |
| `--fallback` | off | Fall back to local library conversion if the server is unreachable |

### Conversion options

Identical to the standalone `pix2asa` CLI:

| Flag | Description |
|---|---|
| `--list-platforms` | Print available target platforms (fetched from server) and exit |
| `-f / --input-file FILE` | PIX config to read |
| `-o / --output-file FILE` | Write converted config (default: stdout) |
| `-t / --target-platform SLUG` | Target ASA platform slug |
| `-m / --map-interface SRC@DST` | Explicit interface mapping, repeatable |
| `-b / --boot-system-file FILE` | File containing the ASA boot system image path |
| `-7 / --pix7` | Source is PIX OS 7.x (default: 6.x) |
| `-5 / --pix5505` | Emit ASA 5505 switch default config |
| `-d / --debug` | Print log to stdout |
| `-l / --log-file FILE` | Write log to FILE (overwrite) |
| `-a / --append-log-file FILE` | Append log to FILE |
| `--no-convert-names` | Pass `name` commands through unchanged |

### Examples

```sh
# Basic remote conversion
pix2asa-client -f pix.cfg -t asa-5520 --server http://192.168.1.10:8000

# Fall back to local if server is down
pix2asa-client -f pix.cfg -t asa-5520 --fallback

# List platforms from server
pix2asa-client --list-platforms --server http://192.168.1.10:8000
```

### Library usage

`Pix2asaClient` can be used directly as a Python library:

```python
from pix2asa.client import Pix2asaClient
from pix2asa.converter import ConversionOptions
from pix2asa.models import SourceVersion, TargetVersion

with Pix2asaClient("http://localhost:8000") as client:
    if not client.ping():
        print("server not available")
        raise SystemExit(1)

    print(client.server_version())      # e.g. "1.0.0"
    devices = client.list_devices()     # list[RemoteDevice]

    options = ConversionOptions(
        target_platform="asa-5520",
        source_version=SourceVersion.PIX6,
        target_version=TargetVersion.ASA84,
    )
    result = client.convert(config_text, options)
    print(result.output)
```

#### `Pix2asaClient`

```python
class Pix2asaClient:
    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 30.0)

    def ping() -> bool                              # True if server reachable
    def server_version() -> str                     # package version from server
    def list_devices() -> list[RemoteDevice]        # all target platforms
    def convert(config_text, options) -> ConversionResult
```

#### Exceptions

```python
class ClientError(Exception):
    status: int     # HTTP status code
    detail: str     # error message from server

class ServerUnavailableError(ClientError):
    url: str        # server URL that could not be reached
```

`ServerUnavailableError` is a subclass of `ClientError` with `status = 0`.

#### `RemoteDevice`

```python
@dataclass(frozen=True)
class RemoteDevice:
    slug:         str
    display_name: str
    interfaces:   tuple[str, ...]
    max_vlans:    int
```

**No extra dependencies** — uses only the Python standard library (`urllib` + `json`).

---

## REST API Reference

Start the server:
```sh
pix2asa --serve 8000
# or
uvicorn pix2asa.api:app --reload
```

Interactive docs: `http://localhost:8000/docs`

---

### `GET /api/version`

Returns the package version.

**Response**
```json
{ "version": "1.0.0" }
```

---

### `GET /api/devices`

Returns all supported target ASA platform slugs.

**Response** — array of device objects:
```json
[
  {
    "slug": "asa-5520",
    "display_name": "ASA 5520",
    "interfaces": ["GigabitEthernet0/0", "GigabitEthernet0/1", "GigabitEthernet0/2", "GigabitEthernet0/3", "Management0/0"],
    "max_vlans": 150
  },
  ...
]
```

---

### `POST /api/convert`

Convert a PIX configuration.

**Request body**
```json
{
  "config":              "<raw PIX config text>",
  "target_platform":     "asa-5520",
  "source_version":      6,
  "target_version":      84,
  "interface_map":       { "ethernet0": "GigabitEthernet0/0" },
  "custom_5505":         false,
  "boot_system":         "",
  "convert_names":       true,
  "debug":               false,
  "source_filename":     "pix38.txt",
  "context_mode":        false,
  "virtual_interfaces":  []
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `config` | string | **required** | Raw PIX configuration text |
| `target_platform` | string | `""` | Platform slug from `/api/devices` |
| `source_version` | int | `6` | PIX OS major version: `6` or `7` |
| `target_version` | int | `84` | ASA OS version: `84` (ASA 8.4+) |
| `interface_map` | object | `{}` | Explicit source→dest interface overrides |
| `custom_5505` | bool | `false` | Emit ASA 5505 switch default config stanzas |
| `boot_system` | string | `""` | Boot system image path |
| `convert_names` | bool | `true` | Convert PIX `name` commands to host objects (false = pass through unchanged) |
| `debug` | bool | `false` | Log extra debug info (NAT translation table, remap events) to the conversion log |
| `source_filename` | string | `""` | Original input filename, recorded in the log header |
| `context_mode` | bool | `false` | Prepend a `:::: system-config ::::` block for multi-context ASA deployments |
| `virtual_interfaces` | array | `[]` | Virtual interface mappings for context mode. Each element: `{"src_pix_if": "ethernet0", "physical": "Port-channel1.1400", "nameif": "outside"}` |

**Response**
```json
{
  "output":          "<converted ASA config text>",
  "log":             "<full INFO/WARNING/ERROR log>",
  "warnings":        ["WARNING: ...", ...],
  "errors":          ["ERROR: ...", ...],
  "converted_names": { "wmmgt.wm.example.com": "10.50.50.100", ... }
}
```

| Field | Type | Description |
|---|---|---|
| `output` | string | Converted ASA configuration text |
| `log` | string | Full INFO/WARNING/ERROR conversion log |
| `warnings` | array | Lines from `log` that start with `WARNING:` |
| `errors` | array | Lines from `log` that start with `ERROR:` |
| `converted_names` | object | name→IP map for all PIX `name` commands that were converted to host objects |

**Example — minimal conversion:**
```sh
curl -s http://localhost:8000/api/convert \
  -H 'Content-Type: application/json' \
  -d '{"config": "hostname pix\ninterface ethernet0\nnameif ethernet0 outside security0\n"}' \
  | python3 -m json.tool
```

**Example — with debug and explicit interface map:**
```sh
curl -s http://localhost:8000/api/convert \
  -H 'Content-Type: application/json' \
  -d '{
    "config": "'"$(cat configs/pix38.txt)"'",
    "target_platform": "asa-5520",
    "debug": true,
    "interface_map": {"ethernet0": "GigabitEthernet0/0"}
  }' | python3 -m json.tool
```

**HTTP error codes**

| Code | Condition |
|---|---|
| `422` | `source_version` not 6 or 7; `target_version` not 84; unknown `target_platform` |

---

## React UI

A single-page React application served by the FastAPI server at `http://localhost:8000/`. It provides a guided 4-step wizard for converting PIX configurations.

### Running the UI

**Production (bundled, served by FastAPI):**
```sh
pix2asa --serve 8000
# open http://localhost:8000
```

**Development (Vite dev server with hot reload):**
```sh
cd ui
npm install
npm run dev        # starts on http://localhost:5173
                   # /api requests are proxied to http://localhost:8000
```

**Build:**
```sh
cd ui
npm run build      # outputs to ui/dist/ (served by FastAPI)
```

### Wizard steps

The UI guides users through four sequential steps:

| Step | Component | Description |
|---|---|---|
| 1 | `ConfigInput` | Paste config text or load a `.txt`/`.cfg` file. Shows line and character count. |
| 2 | `DeviceSelector` | Pick the target ASA platform from a dropdown (fetched from `/api/devices`). |
| 3 | `InterfaceMapper` | Map each PIX source interface to a destination ASA interface. Defaults to **auto** (sequential assignment); explicit overrides are applied on top. |
| 4 | `ConversionPanel` | Set options, then convert. After conversion, view source config, target config, or log in a modal viewer. |

### Conversion options (Step 4)

| Option | Description |
|---|---|
| Source PIX version | `PIX 6` or `PIX 7` |
| Target ASA version | `ASA 8.4+` (only supported target) |
| Boot image path | Optional `flash:/...`, `disk0:/...`, or `tftp://...` path |
| ASA 5505 | Emit default switchport configuration for the ASA 5505 embedded switch |
| Name commands | Convert PIX `name` commands to `object network host` objects (checked by default) |
| Debug | Include NAT translation table and remap events in the conversion log (off by default; useful for troubleshooting conduit/NAT translation) |

### After conversion

Three view buttons appear after a successful conversion:

| Button | Content |
|---|---|
| **View source config** | Original PIX config |
| **View target config** | Converted ASA config (copy-paste ready) |
| **View log** | Full INFO/WARNING/ERROR conversion log |

Errors and warnings from the conversion are also shown inline below the buttons.

### Running the frontend tests

A Playwright end-to-end test suite lives in `tests/test_frontend.py`. It requires both servers running and `pytest-playwright` installed:

```sh
# Install dependencies
pip install pytest-playwright
playwright install chromium

# Start both servers
pix2asa --serve 8000 &
cd ui && npm run dev &

# Run the frontend tests
cd ..
pytest tests/test_frontend.py -v

# Or target the production build (FastAPI serving the SPA)
BASE_URL=http://localhost:8000 pytest tests/test_frontend.py -v
```

Tests automatically skip with a clear message if either server is unreachable — they won't break the main `pytest` suite.

| Test | What it covers |
|---|---|
| `test_page_loads` | Page title contains "pix2asa"; Step 1 panel and textarea are visible |
| `test_full_wizard_flow` | Complete 4-step wizard with minimal PIX 6 config → verify "ASA Version" in output modal |
| `test_view_log` | "View log" modal shows `INFO:` lines after conversion |
| `test_debug_log_shows_nat_table` | When Debug checked, log contains "NAT Translation Table" header |
| `test_convert_button_disabled_on_empty_config` | Convert button is disabled when no config is entered |
| `test_view_source_config` | "View source config" modal shows original PIX hostname |
| `test_step_navigation` | Back/Next buttons navigate correctly; config persists through Back |

### Source layout

```
ui/
├── src/
│   ├── main.jsx            React entry point
│   ├── App.jsx             Root component — all state, wizard orchestration
│   ├── api.js              Thin fetch wrapper for /api/devices, /api/version, /api/convert
│   ├── styles/index.css    Tailwind CSS + component utilities
│   └── components/
│       ├── Header.jsx          App title + server version badge
│       ├── ConfigInput.jsx     Textarea + file loader (Step 1)
│       ├── StatusBar.jsx       Line/char count, first-line detection
│       ├── DeviceSelector.jsx  Platform dropdown (Step 2)
│       ├── InterfaceMapper.jsx Source→dest interface table (Step 3)
│       ├── ConversionPanel.jsx Options form + action buttons (Step 4)
│       └── ConfigViewer.jsx    Full-screen modal for source/target/log
├── dist/                   Production build (served by FastAPI)
├── index.html
├── vite.config.js          Vite config — /api proxy to :8000
├── tailwind.config.js
└── package.json
```

### Environment variable

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE` | `""` (relative) | Override the API base URL for non-proxied deployments |

---

## Library Usage

The converter can be used directly as a Python library with no subprocess or file I/O:

```python
from pix2asa.converter import convert, ConversionOptions
from pix2asa.models import SourceVersion, TargetVersion

config_text = open("pix.cfg").read()

options = ConversionOptions(
    target_platform="asa-5520",
    source_version=SourceVersion.PIX6,
    target_version=TargetVersion.ASA84,
)

result = convert(config_text, options)

print(result.output)      # converted ASA config
print(result.log)         # full log
print(result.warnings)    # list[str] — WARNING: lines
print(result.errors)      # list[str] — ERROR: lines
```

### ConversionOptions

```python
@dataclass
class ConversionOptions:
    target_platform:    str = ""
    source_version:     SourceVersion = SourceVersion.PIX6
    target_version:     TargetVersion = TargetVersion.ASA84
    interface_map:      dict[str, str] = {}   # src → dst overrides
    custom_5505:        bool = False
    boot_system:        str = ""
    convert_names:      bool = True           # convert PIX 'name' commands to host objects
    debug:              bool = False          # log NAT translation table and remap events
    source_filename:    str = ""             # recorded in the log header
    context_mode:       bool = False          # prepend :::: system-config :::: block
    virtual_interfaces: list[VirtualInterface] = []  # for context_mode
```

### VirtualInterface

```python
@dataclass
class VirtualInterface:
    src_pix_if: str   # PIX source interface name   e.g. "ethernet0"
    physical:   str   # system-level allocate-interface  e.g. "Port-channel1.1400"
    nameif:     str   # logical name used for context nameif  e.g. "outside"
```

### ConversionResult

```python
@dataclass
class ConversionResult:
    output:          str          # converted ASA config
    log:             str          # full log text
    warnings:        list[str]    # WARNING: lines
    errors:          list[str]    # ERROR: lines
    converted_names: dict[str, str]  # name → IP for all converted 'name' commands
```

---

## Architecture

### High-level overview

```
┌─────────────────────────────────────────────────────────────┐
│                       Entry points                          │
│                                                             │
│   CLI (cli.py)              REST API (api.py / FastAPI)     │
│   argparse                  POST /api/convert               │
└──────────────┬──────────────────────────┬───────────────────┘
               │                          │
               ▼                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    converter.py                             │
│                                                             │
│   convert(config_text, ConversionOptions)                   │
│        → ConversionResult                                   │
│                                                             │
│   1. Build ConversionContext                                │
│   2. build_dispatcher(ctx)     ──► actions/                 │
│   3. Parse loop: dispatcher.dispatch(line, ctx)             │
│   4. Post-processing (5 steps, see call flow below)         │
│   5. _render_config(ctx, buf)  ──► templates/*.j2           │
│   6. Return ConversionResult                                │
└──────────────────────────────────────────────────────────────┘
               │
       ┌───────┴──────────────────────┐
       ▼                              ▼
┌─────────────┐              ┌────────────────────┐
│  engine.py  │              │    context.py       │
│             │              │                     │
│  Rule       │◄─────────────│  ConversionContext  │
│  Dispatcher │              │  (all mutable state)│
└──────┬──────┘              └────────┬────────────┘
       │                              │
       ▼                              ▼
┌──────────────────────┐     ┌────────────────────┐
│  actions/            │     │    models.py        │
│  ├── rules.py        │     │                     │
│  ├── interfaces.py   │     │  TargetDevice       │
│  ├── nat.py          │     │  InterfaceConfig    │
│  ├── nat_emit.py     │     │  ConfigLine         │
│  ├── conduit.py      │     │  Inspect            │
│  ├── names.py        │     └────────┬────────────┘
│  ├── inspect.py      │              │
│  ├── failover.py     │     ┌────────▼────────────┐
│  └── misc.py         │     │  data/devices.json  │
└──────┬───────────────┘     │  (device model)     │
       │                     └─────────────────────┘
       ▼
┌─────────────┐
│ rendering.py│
│ Jinja2 env  │
│ templates/  │
└─────────────┘
```

### Call flow for `convert()`

```
convert(config_text, options)               [converter.py]
│
├── ConversionContext(...)                  [context.py]
│
├── setup_custom_if(src, dst, ctx)          [actions/]  ← if interface_map set
│
├── build_dispatcher(ctx)                  [actions/]
│   ├── RULES_COMMON                        Rule list
│   ├── RULES_V6 | RULES_V7                Rule list (version-selected)
│   └── Dispatcher(rules)                  [engine.py]
│       └── _keyed: dict[str, list[Rule]]  (O(1) by first token)
│
├── for line in config_text.splitlines():
│   └── dispatcher.dispatch(line, ctx)     [engine.py]
│       ├── keyword = line.split()[0].lower()
│       ├── try _keyed[keyword]            O(1) lookup
│       │   └── rule.pattern.match(line)
│       │       └── handler(match, ctx)    [actions.py handler_*]
│       │           └── ctx.interfaces[if].set_nameif(...)  [models.py]
│       │           └── ctx.log(...)       [context.py]
│       └── else: append ConfigLine to ctx.config_lines
│
├── Post-processing                        [actions/]
│   ├── emit_default_mtus(ctx)             emit MTU for interfaces without explicit mtu
│   ├── emit_nat_rules(ctx)                group nat+global → ASA 8.4 nat stanzas
│   ├── apply_nat_remap_to_names(ctx)      catch-up remap for static-before-name ordering
│   ├── emit_conduit_access_groups(ctx)    conduit → extended ACLs + access-group
│   └── apply_name_substitutions(ctx)      substitute name-objects into ACL text
│
├── _render_config(ctx, buf)               [converter.py]
│   ├── render_template("version_header.j2", ...)
│   ├── [optional] render_template("asa5505_switch.j2", ...)
│   ├── for cfg_line in ctx.config_lines:
│   │   ├── is_interface_marker() → InterfaceConfig.render()  (interface_stanza.j2)
│   │   └── else cfg_line.render()
│   └── _render_inspects(ctx, buf)
│       └── render_template("inspect_stanza.j2", ...)
│           └── policy-map / service-policy block
│
└── return ConversionResult(output, log, warnings, errors)
```

### Dispatcher dispatch sequence

```
dispatcher.dispatch(line, ctx)
│
├── keyword ← line.split()[0].lower()      e.g. "nameif"
│
├── bucket ← _keyed.get(keyword, [])       O(1) dict lookup
│   └── for rule in bucket:
│       └── m = rule.pattern.match(line)
│           if m:
│             └── rule.handler(m, ctx) → True  ← stop
│
├── (if no match in bucket)
│   └── for rule in _fallback:             ordered list
│       └── m = rule.pattern.match(line)
│           if m:
│             └── rule.handler(m, ctx) → True  ← stop
│
└── return False  ← unmatched → caller appends ConfigLine
```

---

## Module Reference

### `pix2asa.models`

Domain dataclasses. All are plain `@dataclass` or `@dataclass(frozen=True)` — no ORM, no hidden state.

#### `SourceVersion(IntEnum)`
```
PIX6 = 6
PIX7 = 7
```

#### `TargetVersion(IntEnum)`
```
ASA84 = 84   # ASA 8.4+ (only supported target)
```

#### `TargetDevice`
```python
@dataclass(frozen=True)
class TargetDevice:
    slug:         str
    display_name: str
    interfaces:   tuple[str, ...]   # ordered physical interface names
    max_vlans:    int

    def is_5505(self) -> bool
```

Loaded at import from `pix2asa/data/devices.json` into `TARGET_DEVICES: dict[str, TargetDevice]` and `VALID_TARGET_SLUGS: frozenset[str]`.

#### `InterfaceConfig`
```python
@dataclass
class InterfaceConfig:
    physical_name: str
    mapped_name:   str = ""     # destination physical name
    nameif:        str = ""     # logical name (ASA nameif)
    security_level: int = 0
    ip_address:    str = ""
    netmask:       str = ""
    standby_ip:    str = ""
    mtu:           str = ""
    speed:         str = ""
    vlan:          str = ""
    is_logical:    bool = False
    is_failover_lan:   bool = False
    is_failover_state: bool = False
    dhcp:          bool = False
    dhcp_setroute: bool = False
    pppoe:         bool = False
    pppoe_setroute: bool = False
    shutdown:      bool = False

    def set_nameif(name, level)    # set logical name + security level
    def set_logical()              # mark as a sub-interface
    def set_vlan(vlan)
    def set_dhcp(set_route)
    def set_pppoe(set_route)
    def set_failover_lan()
    def set_failover_state()
    def render() -> str            # emit full ASA interface stanza
```

#### `ConfigLine`
```python
@dataclass
class ConfigLine:
    text:            str
    _interface:      str = ""   # set by mark_interface()
    _is_inspect:     bool = False
    _failover_lan:   str = ""
    _failover_link:  str = ""

    def mark_interface(name)
    def mark_inspect()
    def set_failover_lan(if_id)
    def set_failover_link(if_id)

    def is_interface_marker() -> bool
    def get_interface()       -> str
    def is_inspect_marker()   -> bool
    def is_failover_lan()     -> bool
    def is_failover_link()    -> bool
    def render()              -> str
```

A `ConfigLine` is a placeholder in the ordered output. Interface and inspect markers tell `_render_config()` to expand the associated `InterfaceConfig` or inject the `policy-map` block at the right position.

#### `Inspect`
```python
@dataclass
class Inspect:
    name:    str          # protocol (ftp, http, dns, ...)
    port:    str = ""     # non-default port or dns max-length
    negated: bool = False # True when "no fixup protocol ..."

    def render() -> str   # "  inspect <name>" or "  no inspect <name>"
```

#### `Rule`
See [Pattern-Matching Engine](#pattern-matching-engine).

---

### `pix2asa.context`

#### `ConversionContext`
```python
@dataclass
class ConversionContext:
    # options (set at construction)
    source_version:  SourceVersion
    target_version:  TargetVersion
    target_platform: str
    custom_5505:     bool
    boot_system:     str
    convert_names:   bool        # convert 'name' commands to host objects
    debug:           bool

    # name→IP table (from PIX 'name' commands)
    converted_names:   dict[str, str]   # name → IP
    converted_names_r: dict[str, str]   # IP → safe object name

    # NAT state
    pix_nat_rules:   dict[int, list[...]]   # collected nat lines, by nat_id
    pix_global_rules: dict[int, list[...]]  # collected global lines, by nat_id
    static_objects:  dict[str, ...]         # auto-generated objects from static NAT
    # mapped_ip → (src_if, dst_if, real_ip, mask) — built by _handle_pix_static
    static_nat_map:  dict[str, tuple[str, str, str, str]]

    # Conduit tracking
    conduit_seen:         bool          # True once any conduit command is parsed
    conduit_outside_ifs:  set[str]      # outside interfaces seen in static commands
    conduit_entries:      list[dict]    # parsed conduit entries (translated in post-processing)

    # conversion state
    config_lines:           list[ConfigLine]
    interfaces:             dict[str, InterfaceConfig]
    name_ifs:               dict[str, str]   # logical → physical
    name_ifs_r:             dict[str, str]   # physical → logical
    logical_to_phys:        dict[str, str]   # PIX6 sub-iface mapping
    platform_if_mapping:    dict[str, str]   # src → dst
    platform_if_mapping_r:  dict[str, str]   # dst → src
    platform_if_exceeded:   bool
    inspects:               list[Inspect]
    vpdn_groups:            list[str]
    failover_lan_if:        str
    failover_link_if:       str

    def log(message: str)                    # append to internal log buffer
    def get_log() -> str                     # return full log as string
    def map_interface(source, target)        # update both mapping dicts atomically
    def get_real_phys(name: str) -> str      # resolve logical → physical
    def reset()                              # clear all state for reuse
```

**Rule:** Never set `platform_if_mapping` / `platform_if_mapping_r` directly. Always use `map_interface()` to keep both sides in sync.

---

### `pix2asa.engine`

#### `Rule`
```python
@dataclass(frozen=True)
class Rule:
    keyword: str            # first CLI token, lowercased; "" = fallback
    pattern: re.Pattern     # pre-compiled, IGNORECASE, named capture groups
    handler: Callable[[re.Match, ConversionContext], bool]
    negated: bool = False   # True for "no <keyword>" rules
```

#### `Dispatcher`
```python
class Dispatcher:
    def __init__(self, rules: list[Rule])
    def dispatch(self, line: str, ctx: ConversionContext) -> bool
```

`dispatch()` looks up the first token of `line` in `_keyed`. If there is a match, the handler is called and `True` is returned. If no keyed rule matches, the fallback list is tried. Returns `False` if no rule matches.

#### `_r(pattern: str) -> re.Pattern`

Helper — compiles `pattern` with `re.IGNORECASE`.

---

### `pix2asa.actions`

The `actions/` package is split into nine focused submodules, each responsible for a coherent domain:

| Submodule | Responsibility |
|---|---|
| `rules.py` | Rule tables (`RULES_COMMON`, `RULES_V6`, `RULES_V7`) and `build_dispatcher()` |
| `interfaces.py` | `nameif`, `ip address`, `interface`, sub-interface handlers (PIX 6 + 7) |
| `nat.py` | `static`, `nat`, `global` handlers; `_remap_name_to_real_ip()` helper |
| `nat_emit.py` | `emit_nat_rules()`, `emit_default_mtus()` — post-processing NAT output |
| `conduit.py` | `conduit` handler (collect); `emit_conduit_access_groups()` (translate + emit) |
| `names.py` | `name` handler; `apply_name_substitutions()`; `apply_nat_remap_to_names()` |
| `inspect.py` | `fixup`/`no fixup` handlers → `ctx.inspects` for deferred policy-map output |
| `failover.py` | `failover` handlers (lan interface, link, poll, IP address) |
| `misc.py` | `hostname`, `vpdn group`, `_ignore`, `_repeat`, `_not_supported` handlers |

#### Public surface

| Symbol | Description |
|---|---|
| `setup_custom_if(src, dst, ctx)` | Register a single explicit interface mapping. Returns `False` if `dst` is not a valid ASA interface name. |
| `build_dispatcher(ctx)` | Create a `Dispatcher` pre-loaded with the rule tables appropriate for `ctx.source_version`. |
| `RULES_COMMON` | `list[Rule]` — rules shared between PIX 6 and PIX 7 |
| `RULES_V6` | `list[Rule]` — PIX 6–specific rules (nameif, fixup) |
| `RULES_V7` | `list[Rule]` — PIX 7–specific rules (interface blocks) |

#### Handler categories

| Handler(s) | Module | Trigger |
|---|---|---|
| `_handle_interface` | `interfaces.py` | `interface <phys>` (PIX 7) |
| `_handle_logical_interface` | `interfaces.py` | `interface <phys>.<n>` |
| `_handle_nameif` | `interfaces.py` | `nameif <phys> <logical> <sec>` (PIX 6) |
| `_handle_ip_static` | `interfaces.py` | `ip address <if> <ip> <mask>` |
| `_handle_ip_dhcp` | `interfaces.py` | `ip address <if> dhcp` |
| `_handle_ip_pppoe` | `interfaces.py` | `ip address <if> pppoe` |
| `_handle_fixup` / `_neg(_handle_fixup)` | `inspect.py` | `[no] fixup protocol <proto> <port>` — collected into `ctx.inspects` |
| `_handle_fixup_dns` | `inspect.py` | `[no] fixup protocol dns maximum-length <n>` |
| `_handle_fixup_h323_bare` | `inspect.py` | `fixup protocol h323 <port>` — emits both `inspect h323 h225` and `inspect h323 ras` |
| `_handle_failover_poll` | `failover.py` | `failover poll <n>` |
| `_handle_failover_lan_interface` | `failover.py` | `failover lan interface <tag> <phys>` |
| `_handle_failover_link` | `failover.py` | `failover link <tag> <phys>` |
| `_handle_vpdn_group` | `misc.py` | `vpdn group <name> ...` |
| `_handle_hostname` | `misc.py` | `hostname <name>` |
| `_handle_nat` | `nat.py` | `nat (<if>) <id> <net> <mask>` — collected for deferred `emit_nat_rules` |
| `_handle_global` | `nat.py` | `global (<if>) <id> <ip_or_range_or_interface>` — collected for deferred `emit_nat_rules` |
| `_handle_pix_static` | `nat.py` | `static (<real>,<mapped>) <ext_ip> <int_ip>` — produces ASA `nat (if,if) static`; also calls `_remap_name_to_real_ip()` |
| `_handle_pix_port_redirect` | `nat.py` | `static (<real>,<mapped>) tcp <ext_ip> <ext_port> <int_ip> <int_port>` — port-redirect static; also calls `_remap_name_to_real_ip()` |
| `_handle_conduit` | `conduit.py` | `conduit permit\|deny ...` — parsed and collected in `ctx.conduit_entries` for deferred translation |
| `_handle_name` | `names.py` | `name <ip> <name>` — populates `ctx.converted_names`; emits `object network <name> host <ip>` |
| `_handle_access_group` | `misc.py` | `access-group <acl> in interface <if>` |
| `_ignore` | `misc.py` | Lines removed from output (PIX version banner, `: end`, `Cryptochecksum:`) |
| `_repeat` | `misc.py` | Lines passed through unchanged |
| `_not_supported` | `misc.py` | Lines that emit a `WARNING: not supported` log entry |

#### Name remapping — how named objects track real IPs

PIX `name` commands create host objects (`object network <name> host <ip>`). The problem: when a `name` is assigned to a **mapped/external** IP (an address visible outside NAT), the object should ultimately point to the **real/internal** IP so that ASA ACLs referencing that object see the correct address.

Two complementary mechanisms handle both config orderings:

**Engine-pass remap** (`_remap_name_to_real_ip` in `nat.py`):
Called at the start of `_handle_pix_static` and `_handle_pix_port_redirect`. If the mapped IP is already in `ctx.converted_names_r` (meaning the `name` command appeared before the `static` command), the corresponding object body line is patched from `host <mapped_ip>` to `host <real_ip>` in-place, and both `converted_names` and `converted_names_r` are updated. The NAT statement is emitted correctly referencing the already-corrected object.

**Post-processing catch-up remap** (`apply_nat_remap_to_names` in `names.py`):
Runs after the full engine pass, before `emit_conduit_access_groups`. Handles the reverse ordering — when `static` appears before `name` in the config. At that point both `static_nat_map` and `converted_names_r` are fully populated, so any named object whose IP is a mapped address (and whose real IP isn't already named) gets patched. A `WARNING` is logged because the NAT statement was already emitted using auto-generated object names.

#### Post-processing functions

Called in order by `convert()` after the engine pass:

| Order | Function | Module | Purpose |
|---|---|---|---|
| 1 | `emit_default_mtus(ctx)` | `nat_emit.py` | Emit MTU commands for interfaces that don't have an explicit mtu configured |
| 2 | `emit_nat_rules(ctx)` | `nat_emit.py` | Group collected `nat`/`global` pairs by `(nat_id, dst_if)`; emit ASA 8.4 `nat (src,dst) source dynamic ... pat-pool ...` stanzas |
| 3 | `apply_nat_remap_to_names(ctx)` | `names.py` | Catch-up remap for named objects whose `static` appeared before their `name` command |
| 4 | `emit_conduit_access_groups(ctx)` | `conduit.py` | Translate collected conduit entries (mapped→real via `static_nat_map`); emit `access-list ACL-Global extended` lines + `access-group` statements |
| 5 | `apply_name_substitutions(ctx)` | `names.py` | Rewrite `host <ip>` tokens in all config lines with `object <name>` using the combined map from `converted_names_r` + `static_objects` |

#### `_neg(handler)` wrapper

Creates a negated variant of a handler without duplicating the function body:

```python
_handle_fixup_neg = _neg(_handle_fixup)
```

Inside the handler, `m._rule_negated` is `True`, so the handler can branch on polarity.

---

### `pix2asa.converter`

```python
def convert(config_text: str, options: ConversionOptions) -> ConversionResult
```

Pure function. No file I/O, no global state, no stdout side-effects. All output is captured into `io.StringIO`.

Internal call sequence:

```
convert()
  └── ConversionContext(...)
  └── [setup_custom_if() for each interface_map entry]
  └── build_dispatcher(ctx)
  └── for line: dispatcher.dispatch(line, ctx)
  └── [post-processing: emit_default_mtus → emit_nat_rules → apply_nat_remap_to_names → emit_conduit_access_groups → apply_name_substitutions]
  └── _render_config(ctx, buf)
       └── render_template("version_header.j2", ...)
       └── [render_template("asa5505_switch.j2", ...)]
       └── for cfg_line: cfg_line.render() or InterfaceConfig.render()
       └── _render_inspects → render_template("inspect_stanza.j2", ...)
  └── ConversionResult(output, log, warnings, errors)
```

---

### `pix2asa.rendering`

Shared Jinja2 environment. All ASA output text lives in `pix2asa/templates/*.j2`.

```python
render_template(tpl_name: str, variables: dict) -> str
emit_lines(tpl_name: str, variables: dict, ctx: ConversionContext) -> None
```

`emit_lines` renders the template and appends each non-empty line as a `ConfigLine` into `ctx.config_lines`. Blank lines are silently dropped.

Key templates:

| Template | Purpose |
|---|---|
| `version_header.j2` | `ASA Version 8.4(2)` + optional `boot system` |
| `asa5505_switch.j2` | Default switchport config for ASA 5505 embedded switch |
| `interface_stanza.j2` | Full ASA interface block (nameif, security-level, ip, dhcp, pppoe, vlan, mtu) |
| `inspect_stanza.j2` | `policy-map type inspect dns` + `policy-map global_policy` + `service-policy` |
| `dynamic_nat.j2` | `nat (src,dst) source dynamic <real> [pat-pool] <mapped> destination static any any` |
| `static_nat.j2` | `nat (real,mapped) static source <obj> <obj>` |
| `nat_pool_group.j2` | `object-group network` for multi-entry pools |
| `auto_object.j2` | Auto-generated `object network` for NAT/static IP addresses |
| `name_object.j2` | `object network <name> host <ip>` from PIX `name` commands |
| `passthrough.j2` | Lines passed through without modification |

**Rust port note:** The same `.j2` files can be loaded unchanged by `minijinja` in the Rust engine.

---

### `pix2asa.api`

FastAPI application object: `pix2asa.api.app`

Three routes (see [REST API Reference](#rest-api-reference)).  
All request/response models are Pydantic v2 `BaseModel` subclasses.

---

### `pix2asa.cli`

Entry point: `pix2asa.cli:main`

Registered as `pix2asa` console script in `pyproject.toml`.

```python
def main(argv: list[str] | None = None) -> int
```

Pass `argv` explicitly for testing:
```python
from pix2asa.cli import main
rc = main(["-f", "pix.cfg", "-t", "asa-5520"])
```

---

## Pattern-Matching Engine

### Design

```
Rule (frozen dataclass)
├── keyword:  str           first token of the CLI line, lowercased
├── pattern:  re.Pattern    pre-compiled, IGNORECASE, named groups
├── handler:  Callable      (m: re.Match, ctx: ConversionContext) → bool
└── negated:  bool          True for "no <proto>" polarity rules

Dispatcher
├── _keyed:    dict[str, list[Rule]]   O(1) bucket by first token
└── _fallback: list[Rule]              ordered list for multi-keyword rules
```

**Dispatch is O(1)** for the common case — a single dict lookup by the first token routes to a small bucket (typically 1–4 rules). Only unkeyed fallback rules remain O(n).

**All patterns use named capture groups:**
```python
Rule("nameif",
     _r(r"nameif\s+(?P<phys>\S+)\s+(?P<logical>\S+)\s+security(?P<level>\d+)"),
     _handle_nameif)
```

Handlers read `m["phys"]` instead of `m.group(1)`.

**Negated rules share the handler** via `_neg()`:
```python
_handle_fixup_neg = _neg(_handle_fixup)

Rule("no", _r(r"no\s+fixup\s+protocol\s+(?P<proto>\S+).*"), _handle_fixup_neg)
```

Inside `_handle_fixup`, `m._rule_negated` determines whether to add `Inspect(negated=True)`.

**Rule tables are module-level constants** (not hidden inside a function), so individual rules can be unit-tested:
```python
from pix2asa.actions import RULES_V6
fixup_rule = next(r for r in RULES_V6 if "fixup" in r.keyword)
```

### Rust mapping

```rust
struct Rule {
    keyword: &'static str,
    pattern: Regex,
    handler: fn(&Captures, &mut Context) -> bool,
    negated: bool,
}

struct Dispatcher {
    keyed:    HashMap<&'static str, Vec<Rule>>,
    fallback: Vec<Rule>,
}
```

---

## Device Model

Device model data lives in `pix2asa/data/devices.json`. It is the **single source of truth** for all supported target platforms — no code changes are needed to add a new platform.

### Schema

```json
{
  "targets": [
    {
      "slug":         "asa-5520",
      "display_name": "ASA 5520",
      "interfaces":   ["GigabitEthernet0/0", "GigabitEthernet0/1", ...],
      "max_vlans":    150
    }
  ],
  "sources": [
    {
      "slug":       "pix-535",
      "interfaces": ["gb-ethernet0", "gb-ethernet1", "ethernet0", ...]
    }
  ]
}
```

### Adding a new target platform

1. Add an entry to `targets` in `devices.json`.
2. Re-run `pix2asa --list-platforms` to confirm it appears.
3. No code changes required.

### Python access

```python
from pix2asa.models import TARGET_DEVICES, VALID_TARGET_SLUGS

device = TARGET_DEVICES["asa-5520"]
print(device.interfaces)    # ("GigabitEthernet0/0", ...)
print(device.max_vlans)     # 150
print("asa-9999" in VALID_TARGET_SLUGS)  # False
```

---

## Rust Port Guide

The Python package was designed to port cleanly to Rust. Key conventions:

| Python | Rust |
|---|---|
| `@dataclass(frozen=True)` | `struct` with `Copy`/`Clone` |
| `@dataclass` | `struct` with `mut` fields |
| `IntEnum` | `enum` with `#[repr(u8)]` |
| `dict[str, T]` | `HashMap<String, T>` |
| `list[T]` | `Vec<T>` |
| `tuple[str, ...]` | `&[&str]` or `Vec<String>` |
| `io.StringIO` | `std::io::Cursor<Vec<u8>>` |
| `re.Pattern` (named groups) | `regex::Regex` (named captures) |
| Jinja2 templates (`*.j2`) | `minijinja` — same `.j2` files work unchanged |
| `devices.json` | same file, parsed with `serde_json` |
| `ConversionContext` | `struct Context` (passed as `&mut`) |
| `convert()` pure function | `fn convert(input: &str, opts: &Options) -> Result` |

### Data sharing

`pix2asa/data/devices.json` is designed to be consumed directly by Rust:

```rust
use serde::Deserialize;

#[derive(Deserialize)]
struct TargetDevice {
    slug: String,
    display_name: String,
    interfaces: Vec<String>,
    max_vlans: u32,
}

let data: serde_json::Value = serde_json::from_str(include_str!("data/devices.json"))?;
```

### No global state

`ConversionContext` carries all mutable state as explicit fields. The `convert()` function is pure. This maps directly to Rust's ownership model — there is no shared mutable global state to work around.

---

## Sample Configs

The `configs/` directory contains real PIX configuration files for testing:

| File | Platform | Notes |
|---|---|---|
| `pix38.txt` | PIX 535 | 8-interface firewall with failover |
| `pix535.txt` | PIX 535 | Trunk interfaces |
| `pix-535_with_trunk.cfg` | PIX 535 | VLAN trunks |
| `515-fo.cfg` | PIX 515 | Failover pair |
| `PIX-525-fake-FO.txt` | PIX 525 | Latin-1 encoded |
| `PIX501conf2003Aug13.txt` | PIX 501 | Small office |
| `PIX501conf2003Sep24.txt` | PIX 501 | Updated version |
| `conduit.txt` | PIX (various) | Conduit-style ACLs |

```sh
# Convert all samples
for f in configs/*.txt configs/*.cfg; do
  pix2asa -f "$f" -t asa-5520 -o /dev/null && echo "OK: $f"
done
```

---

## License

MIT License — see [LICENSE](LICENSE).
