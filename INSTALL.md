# Installation

## Requirements

- Python 3.11+
- pip

## Install

```sh
git clone git@github.com:perhagen/pix2asa.git
cd pix2asa
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Install with pinned dependencies

```sh
pip install -r requirements.txt
pip install -e .
```

## Install dev dependencies (for testing)

```sh
pip install -e '.[dev]'
```

## Verify

```sh
pix2asa --list-platforms
```

## React UI (optional)

```sh
cd ui
npm install
npm run dev
```
