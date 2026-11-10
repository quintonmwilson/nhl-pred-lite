"""
remote_model.py - serve the newest committed model files without waiting for Streamlit Cloud to redeploy.

Same approach as the NBA app: Streamlit Cloud doesn't reliably pull the data-only commits the Daily refresh
Action pushes, so the deployed app copies model/ straight from GitHub every couple of minutes. A file is
rewritten only when its bytes change, so its mtime (which keys every cache in streamlit_app.py) moves only
on real updates. No token needed: the repo is public and raw.githubusercontent.com isn't API-rate-limited.

Local runs: set NHL_MODEL_SOURCE=local to read your own model/ files instead.
"""

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import requests
import streamlit as st

RAW_BASE = "https://raw.githubusercontent.com/quintonmwilson/nhl-pred-lite/main/model/"
MODEL_FILES = ["model_artifact.json", "prediction_log.csv", "edge_log.csv"]
SYNC_TTL = 120          # seconds between GitHub checks (raw.githubusercontent.com itself caches ~5 min)
USE_REMOTE = os.environ.get("NHL_MODEL_SOURCE", "github").lower() != "local"
SYNC_DIR = Path(tempfile.gettempdir()) / "nhl_model_synced"


@st.cache_data(ttl=SYNC_TTL, show_spinner=False)
def _sync(local_dir: str) -> None:
    """Copy the latest model/ files from GitHub into SYNC_DIR, keeping the last good copy on any failure."""
    local = Path(local_dir)
    SYNC_DIR.mkdir(parents=True, exist_ok=True)
    stamp = int(datetime.now().timestamp() // 60)
    for name in MODEL_FILES:
        dest = SYNC_DIR / name
        if not dest.exists() and (local / name).exists():          # seed from the deployed copy
            shutil.copyfile(local / name, dest)
        try:
            r = requests.get(RAW_BASE + name, params={"t": stamp}, timeout=10)
        except requests.RequestException:
            continue
        if r.status_code != 200 or not r.content:
            continue
        if dest.exists() and dest.read_bytes() == r.content:
            continue
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_bytes(r.content)
        tmp.replace(dest)                                             # atomic: readers never see half a file


def resolve_model_files(local_dir: Path):
    """Returns (artifact_path, prediction_log_path, edge_log_path, version_key)."""
    d = local_dir
    if USE_REMOTE:
        _sync(str(local_dir))
        d = SYNC_DIR
    art = d / MODEL_FILES[0]
    version = art.stat().st_mtime if art.exists() else 0.0
    return art, d / MODEL_FILES[1], d / MODEL_FILES[2], version
