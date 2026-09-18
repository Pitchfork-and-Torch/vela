"""Content-addressed VELA identities.

Domain-separated SHA-256. A number without a digest is a rumor.
This is scientific commitment, not packet encryption, and not
self-modifying code.
"""
from __future__ import annotations

import hashlib
import json
from typing import Iterable

from vela.types import STDLIB_MECHANISMS

DOMAIN = "VELA1"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tagged(tag: str, payload: str | bytes) -> str:
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return sha256_hex(DOMAIN.encode("ascii") + b"|" + tag.encode("ascii") + b"|" + payload)


def source_digest(src: str) -> str:
    # Bind the exact text. Comments are part of the claim.
    return tagged("src", src.replace("\r\n", "\n"))


def mechanism_digest(name: str, spec: dict | None = None) -> str:
    spec = spec if spec is not None else STDLIB_MECHANISMS.get(name, {})
    reads = ",".join(sorted(spec.get("reads", ())))
    writes = ",".join(sorted(spec.get("writes", ())))
    cuts = str(spec.get("cuts", "none"))
    phase = str(spec.get("phase", "ack"))
    body = f"{name}|r={reads}|w={writes}|c={cuts}|p={phase}"
    return tagged("mech", body)


def compose_digest(names: Iterable[str]) -> str:
    parts = [f"{n}:{mechanism_digest(n)[:16]}" for n in names]
    return tagged("compose", "+".join(parts))


def config_digest(obj: dict) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return tagged("cfg", blob)


def row_digest(row: dict) -> str:
    leaf = "|".join(
        [
            str(row.get("scenario", "")),
            str(row.get("seed", "")),
            str(row.get("cca", "")),
            f"{float(row.get('goodput_mbps', 0.0)):.4f}",
            f"{float(row.get('p95_rtt_ms', 0.0)):.2f}",
        ]
    )
    return tagged("row", leaf)


def merkle(hex_leaves: list[str]) -> str:
    if not hex_leaves:
        return tagged("tree", "empty")
    nodes = list(hex_leaves)
    while len(nodes) > 1:
        nxt: list[str] = []
        i = 0
        while i < len(nodes):
            if i + 1 < len(nodes):
                nxt.append(tagged("node", nodes[i] + nodes[i + 1]))
            else:
                nxt.append(nodes[i])
            i += 2
        nodes = nxt
    return nodes[0]


def stdlib_catalog() -> dict[str, str]:
    return {name: mechanism_digest(name, spec) for name, spec in sorted(STDLIB_MECHANISMS.items())}
