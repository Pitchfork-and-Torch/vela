"""Path law: the declared model is the one the sim runs.

A `path` block is not a comment. Check parses it, eval binds the
handover rails the sibling sim actually takes, and the receipt
commits the declared law. Calendar `p_ho` still comes from past
gaps. CSV traces wire via `from_csv` into the same PathModel
object; the digest commits the CSV content hash. Lab still is
not orbit; path Mbps are rails or replay, not dish measurements.
"""
from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from vela.ast import PathModel
from vela.digest import tagged
from vela.types import KNOWN_SCENARIOS

PATH_FIELDS = frozenset(
    {"handover", "rtt_jump", "capacity", "mobility_loss", "from_csv"}
)
PARAMETRIC_FIELDS = frozenset(
    {"handover", "rtt_jump", "capacity", "mobility_loss"}
)

# Program name -> contract scenario. Unmapped names stay unbound.
PATH_SCENARIO = {
    "LeoFastHO": "leo_fast_ho",
    "leo_fast_ho": "leo_fast_ho",
    "LeoSingle": "leo_single",
    "leo_single": "leo_single",
    "Terrestrial": "terrestrial",
    "terrestrial": "terrestrial",
    "LeoMulti": "leo_multi",
    "leo_multi": "leo_multi",
}

# House leo_fast_ho rails. Flagship examples already write these.
HOUSE_HANDOVER_INTERVAL_S = 12.0
HOUSE_HANDOVER_JITTER_S = 4.0

_NUM = r"([0-9]+(?:\.[0-9]+)?)"
_HANDOVER = re.compile(
    rf"^every\s+{_NUM}(ms|s)\s+jitter\s+{_NUM}(ms|s)$",
    re.IGNORECASE,
)
_UNIFORM = re.compile(
    rf"^uniform\s+{_NUM}(ms|s|mbps|kbps|bps)\s+{_NUM}(ms|s|mbps|kbps|bps)$",
    re.IGNORECASE,
)
_BURST = re.compile(
    rf"^burst\s+p\s*=\s*{_NUM}\s+window\s*=?\s*{_NUM}(ms|s)$",
    re.IGNORECASE,
)


def _to_seconds(value: str, unit: str) -> float:
    n = float(value)
    u = unit.lower()
    if u == "ms":
        return n / 1000.0
    if u == "s":
        return n
    raise ValueError(f"not a time unit: {unit}")


def _to_bps(value: str, unit: str) -> float:
    n = float(value)
    u = unit.lower()
    if u == "mbps":
        return n * 1e6
    if u == "kbps":
        return n * 1e3
    if u == "bps":
        return n
    raise ValueError(f"not a rate unit: {unit}")


@dataclass
class PathLaw:
    name: str
    scenario: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    handover_interval_s: float | None = None
    handover_jitter_s: float | None = None
    rtt_jump_lo_s: float | None = None
    rtt_jump_hi_s: float | None = None
    capacity_lo_bps: float | None = None
    capacity_hi_bps: float | None = None
    mobility_p: float | None = None
    mobility_window_s: float | None = None
    csv_path: str = ""
    csv_sha256: str = ""
    csv_n_rows: int = 0
    csv_n_handover: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def bound(self) -> bool:
        if self.csv_path and self.csv_sha256 and not self.errors:
            return True
        return bool(self.scenario) and self.handover_interval_s is not None

    @property
    def house(self) -> bool:
        if self.csv_path:
            return False
        return (
            self.scenario == "leo_fast_ho"
            and self.handover_interval_s is not None
            and self.handover_jitter_s is not None
            and abs(self.handover_interval_s - HOUSE_HANDOVER_INTERVAL_S) < 1e-9
            and abs(self.handover_jitter_s - HOUSE_HANDOVER_JITTER_S) < 1e-9
        )

    def as_dict(self) -> dict:
        out = {
            "name": self.name,
            "scenario": self.scenario,
            "handover_interval_s": self.handover_interval_s,
            "handover_jitter_s": self.handover_jitter_s,
            "fields": dict(self.fields),
        }
        if self.csv_path:
            out["csv_path"] = self.csv_path
            out["csv_sha256"] = self.csv_sha256
            out["csv_n_rows"] = self.csv_n_rows
            out["csv_n_handover"] = self.csv_n_handover
            out["kind"] = "csv"
        return out

    def stamp(self) -> str:
        if self.csv_path and self.csv_sha256:
            short = self.csv_sha256[:12]
            scen = self.scenario or "csv"
            return (
                f"{self.name}:{scen} from_csv "
                f"sha256:{short} n={self.csv_n_rows} (csv)"
            )
        if self.handover_interval_s is None:
            return f"{self.name}  (unbound)"
        jitter = self.handover_jitter_s
        jtxt = f"+/-{jitter:g}s" if jitter is not None else ""
        rail = "house" if self.house else "named"
        scen = self.scenario or "unbound"
        return f"{self.name}:{scen} {self.handover_interval_s:g}s{jtxt} ({rail})"


def path_needs_std_error() -> str:
    return "path requires `use std.path` (same model as the sim; not a comment)"


def path_unknown_field_error(name: str, field: str) -> str:
    known = ", ".join(sorted(PATH_FIELDS))
    return f"path {name}: unknown field {field} (known: {known})"


def path_parse_error(name: str, field: str) -> str:
    return f"path {name}: cannot parse {field} (path law)"


def path_empty_error(name: str) -> str:
    return f"path {name}: empty model (path law; a claim needs rails)"


def path_csv_mix_error(name: str) -> str:
    return (
        f"path {name}: from_csv cannot mix with parametric "
        "handover/rtt_jump/capacity/mobility_loss"
    )


def path_csv_missing_error(name: str, path: str) -> str:
    return f"path {name}: from_csv missing file: {path}"


def path_csv_headers_error(name: str, path: str, got: str) -> str:
    return (
        f"path {name}: from_csv bad headers in {path} "
        f"(need t, rtt, capacity; got {got})"
    )


def path_csv_capacity_error(name: str, path: str, row: int, value: float) -> str:
    return (
        f"path {name}: from_csv non-positive capacity "
        f"in {path} row {row}: {value}"
    )


def path_csv_time_error(
    name: str, path: str, row: int, prev: float, cur: float
) -> str:
    return (
        f"path {name}: from_csv inverted time "
        f"in {path} row {row}: {prev} -> {cur}"
    )


def path_csv_empty_error(name: str, path: str) -> str:
    return f"path {name}: from_csv empty trace: {path}"


def path_csv_parse_error(name: str, path: str, detail: str) -> str:
    return f"path {name}: from_csv cannot parse {path}: {detail}"


def normalize_csv_ref(raw: str) -> str:
    """Strip quotes; repair unquoted path tokens joined as a / b . csv."""
    s = str(raw).strip().strip('"').strip("'")
    if " / " in s or " . " in s:
        s = s.replace(" / ", "/").replace(" . ", ".")
    return s.strip()


def resolve_csv_path(raw: str, base_dir: Path | None = None) -> Path:
    """Resolve from_csv against source dir, repo root, and cwd."""
    p = Path(raw)
    if p.is_absolute():
        return p
    candidates: list[Path] = []
    if base_dir is not None:
        candidates.append(base_dir / p)
        candidates.append(base_dir.parent / p)
    candidates.append(Path.cwd() / p)
    for c in candidates:
        if c.is_file():
            return c.resolve()
    if base_dir is not None:
        return (base_dir / p).resolve()
    return p.resolve()


_CSV_T = ("t_s", "time_s", "t", "time")
_CSV_RTT = ("rtt_ms", "rtt_s", "rtt")
_CSV_CAP = (
    "capacity_mbps",
    "bw_mbps",
    "capacity_bps",
    "bw_bps",
    "udp_sat_mbps",
    "cubic_goodput_mbps",
)
_CSV_LOSS = ("loss_p", "loss", "loss_rate")
_CSV_REC = ("reconfig", "handover", "reconfigured")


def _pick_col(fields: dict[str, str], names: tuple[str, ...]) -> str | None:
    for n in names:
        if n in fields:
            return fields[n]
    return None


def load_path_csv(path: Path, *, name: str) -> tuple[str, int, int, list[str]]:
    """Validate a Starlink-class CSV; return sha256, rows, handovers, errors.

    Fail-closed on missing file, bad headers, non-positive capacity,
    inverted time, or empty body. Hash is over raw file bytes so the
    receipt commits the exact trace bytes.
    """
    errors: list[str] = []
    if not path.is_file():
        errors.append(path_csv_missing_error(name, str(path)))
        return "", 0, 0, errors
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        text_body = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        errors.append(path_csv_parse_error(name, str(path), str(e)))
        return digest, 0, 0, errors
    reader = csv.DictReader(text_body.splitlines())
    if not reader.fieldnames:
        errors.append(path_csv_headers_error(name, str(path), "empty"))
        return digest, 0, 0, errors
    fields = {h.lower().strip(): h for h in reader.fieldnames if h is not None}
    t_key = _pick_col(fields, _CSV_T)
    rtt_key = _pick_col(fields, _CSV_RTT)
    cap_key = _pick_col(fields, _CSV_CAP)
    loss_key = _pick_col(fields, _CSV_LOSS)
    rec_key = _pick_col(fields, _CSV_REC)
    if not t_key or not rtt_key or not cap_key:
        got = ",".join(reader.fieldnames)
        errors.append(path_csv_headers_error(name, str(path), got))
        return digest, 0, 0, errors
    n_rows = 0
    n_ho = 0
    prev_t: float | None = None
    for i, row in enumerate(reader, start=2):
        try:
            t = float(row[t_key])
            rtt_raw = float(row[rtt_key])
            cap_raw = float(row[cap_key])
        except (TypeError, ValueError, KeyError) as e:
            errors.append(path_csv_parse_error(name, str(path), f"row {i}: {e}"))
            return digest, n_rows, n_ho, errors
        if cap_raw <= 0.0:
            errors.append(path_csv_capacity_error(name, str(path), i, cap_raw))
            return digest, n_rows, n_ho, errors
        if prev_t is not None and t < prev_t:
            errors.append(path_csv_time_error(name, str(path), i, prev_t, t))
            return digest, n_rows, n_ho, errors
        if rtt_raw < 0.0:
            errors.append(
                path_csv_parse_error(
                    name, str(path), f"row {i}: negative rtt {rtt_raw}"
                )
            )
            return digest, n_rows, n_ho, errors
        if loss_key and row.get(loss_key) not in (None, ""):
            try:
                float(row[loss_key])
            except (TypeError, ValueError) as e:
                errors.append(
                    path_csv_parse_error(name, str(path), f"row {i} loss: {e}")
                )
                return digest, n_rows, n_ho, errors
        if rec_key and row.get(rec_key) not in (None, ""):
            if str(row[rec_key]).strip().lower() in ("1", "true", "yes", "y"):
                n_ho += 1
        prev_t = t
        n_rows += 1
    if n_rows == 0:
        errors.append(path_csv_empty_error(name, str(path)))
        return digest, 0, 0, errors
    return digest, n_rows, n_ho, errors


def parse_path_model(
    model: PathModel, *, base_dir: Path | None = None
) -> PathLaw:
    law = PathLaw(name=model.name, fields=dict(model.fields))
    law.scenario = PATH_SCENARIO.get(model.name, "")
    if not model.fields:
        law.errors.append(path_empty_error(model.name))
        return law
    has_csv = "from_csv" in model.fields
    has_param = any(k in PARAMETRIC_FIELDS for k in model.fields)
    if has_csv and has_param:
        law.errors.append(path_csv_mix_error(model.name))
        return law
    for key, raw in model.fields.items():
        if key not in PATH_FIELDS:
            law.errors.append(path_unknown_field_error(model.name, key))
            continue
        if key == "from_csv":
            ref = normalize_csv_ref(raw)
            if not ref:
                law.errors.append(path_parse_error(model.name, key))
                continue
            resolved = resolve_csv_path(ref, base_dir)
            digest, n_rows, n_ho, errs = load_path_csv(resolved, name=model.name)
            law.csv_path = str(resolved)
            law.errors.extend(errs)
            if not errs:
                law.csv_sha256 = digest
                law.csv_n_rows = n_rows
                law.csv_n_handover = n_ho
            continue
        text = " ".join(
            str(raw).replace("(", " ").replace(")", " ").replace(",", " ").split()
        )
        if key == "handover":
            m = _HANDOVER.match(text)
            if not m:
                law.errors.append(path_parse_error(model.name, key))
                continue
            try:
                law.handover_interval_s = _to_seconds(m.group(1), m.group(2))
                law.handover_jitter_s = _to_seconds(m.group(3), m.group(4))
            except ValueError:
                law.errors.append(path_parse_error(model.name, key))
        elif key == "rtt_jump":
            m = _UNIFORM.match(text)
            if not m:
                law.errors.append(path_parse_error(model.name, key))
                continue
            try:
                law.rtt_jump_lo_s = _to_seconds(m.group(1), m.group(2))
                law.rtt_jump_hi_s = _to_seconds(m.group(3), m.group(4))
            except ValueError:
                law.errors.append(path_parse_error(model.name, key))
        elif key == "capacity":
            m = _UNIFORM.match(text)
            if not m:
                law.errors.append(path_parse_error(model.name, key))
                continue
            try:
                law.capacity_lo_bps = _to_bps(m.group(1), m.group(2))
                law.capacity_hi_bps = _to_bps(m.group(3), m.group(4))
            except ValueError:
                law.errors.append(path_parse_error(model.name, key))
        elif key == "mobility_loss":
            m = _BURST.match(text)
            if not m:
                law.errors.append(path_parse_error(model.name, key))
                continue
            p = float(m.group(1))
            if not (0.0 <= p <= 1.0):
                law.errors.append(path_parse_error(model.name, key))
                continue
            try:
                law.mobility_p = p
                law.mobility_window_s = _to_seconds(m.group(2), m.group(3))
            except ValueError:
                law.errors.append(path_parse_error(model.name, key))
    return law


def _base_dir_for_source(source_name: str | None) -> Path | None:
    if not source_name or source_name in ("<input>", "<stdin>"):
        return None
    p = Path(source_name)
    parent = p.parent
    if str(parent) in ("", "."):
        return Path(".")
    return parent


def parse_program_paths(
    models: list[PathModel],
    *,
    base_dir: Path | None = None,
    source_name: str | None = None,
) -> list[PathLaw]:
    root = base_dir if base_dir is not None else _base_dir_for_source(source_name)
    return [parse_path_model(m, base_dir=root) for m in models]


def path_digest(laws: list[PathLaw] | list[dict]) -> str:
    rows: list[dict] = []
    for item in laws:
        if isinstance(item, PathLaw):
            rows.append(item.as_dict())
        else:
            row = {
                "name": item.get("name", ""),
                "scenario": item.get("scenario", ""),
                "handover_interval_s": item.get("handover_interval_s"),
                "handover_jitter_s": item.get("handover_jitter_s"),
                "fields": dict(item.get("fields") or {}),
            }
            if item.get("csv_sha256"):
                row["csv_path"] = item.get("csv_path", "")
                row["csv_sha256"] = item.get("csv_sha256", "")
                row["kind"] = "csv"
            rows.append(row)
    parts: list[str] = []
    for r in rows:
        head = (
            f"{r.get('name','')}:{r.get('scenario','')}:"
            f"{r.get('handover_interval_s')}:{r.get('handover_jitter_s')}:"
        )
        if r.get("csv_sha256"):
            parts.append(head + f"csv={r.get('csv_sha256')}")
        else:
            parts.append(
                head
                + ",".join(
                    f"{k}={v}" for k, v in sorted((r.get("fields") or {}).items())
                )
            )
    return tagged("path", "|".join(parts) or "empty")


def path_overlay(
    scenario: str, cfg
) -> tuple[float | None, float | None]:
    """Handover rails declared for this scenario, or (None, None)."""
    if cfg is None:
        return None, None
    for item in getattr(cfg, "paths", None) or []:
        if isinstance(item, dict) and item.get("scenario") == scenario:
            return item.get("handover_interval_s"), item.get("handover_jitter_s")
    if getattr(cfg, "path_scenario", "") == scenario:
        return (
            getattr(cfg, "handover_interval_s", None),
            getattr(cfg, "handover_jitter_s", None),
        )
    return None, None


def path_trace_csv(scenario: str, cfg) -> str | None:
    """Resolved CSV path bound for this scenario, if any."""
    if cfg is None:
        return None
    for item in getattr(cfg, "paths", None) or []:
        if not isinstance(item, dict) or not item.get("csv_path"):
            continue
        if item.get("scenario") == scenario:
            return str(item["csv_path"])
    if getattr(cfg, "path_scenario", "") == scenario:
        top = getattr(cfg, "trace_csv", None)
        if top:
            return str(top)
        for item in getattr(cfg, "paths", None) or []:
            if isinstance(item, dict) and item.get("csv_path"):
                if item.get("name") == getattr(cfg, "path_name", ""):
                    return str(item["csv_path"])
    return None


def house_mismatch_warning(law: PathLaw) -> str | None:
    if law.csv_path:
        return None
    if law.scenario != "leo_fast_ho" or not law.bound or law.house:
        return None
    return (
        f"path {law.name}: leo_fast_ho handover "
        f"{law.handover_interval_s:g}s+/-{law.handover_jitter_s:g}s "
        f"is not the house {HOUSE_HANDOVER_INTERVAL_S:g}s+/-"
        f"{HOUSE_HANDOVER_JITTER_S:g}s rail"
    )


def unbound_path_warning(law: PathLaw) -> str | None:
    if law.csv_path and law.csv_sha256 and not law.errors:
        return None
    if law.scenario:
        return None
    known = ", ".join(sorted(KNOWN_SCENARIOS))
    return (
        f"path {law.name}: name does not bind a known scenario "
        f"({known}); eval keeps house defaults"
    )
