"""VELA abstract syntax."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Span:
    line: int
    col: int


@dataclass
class TypeRef:
    name: str
    inner: Optional["TypeRef"] = None
    at_epoch: Optional[str] = None
    span: Optional[Span] = None


@dataclass
class Signal:
    name: str
    typ: TypeRef
    span: Optional[Span] = None


@dataclass
class Expr:
    kind: str
    value: object = None
    left: Optional["Expr"] = None
    right: Optional["Expr"] = None
    args: list["Expr"] = field(default_factory=list)
    name: str = ""
    span: Optional[Span] = None


@dataclass
class Stmt:
    kind: str
    args: list[object] = field(default_factory=list)
    body: list["Stmt"] = field(default_factory=list)
    expr: Optional[Expr] = None
    name: str = ""
    span: Optional[Span] = None


@dataclass
class MatchArm:
    pattern: str
    body: list[Stmt]


@dataclass
class OnClause:
    event: str
    binder: str = ""
    match_arms: list[MatchArm] = field(default_factory=list)
    body: list[Stmt] = field(default_factory=list)
    span: Optional[Span] = None


@dataclass
class WhenClause:
    pred: Expr
    body: list[Stmt]
    span: Optional[Span] = None


@dataclass
class EveryClause:
    tick: str
    body: list[Stmt]
    span: Optional[Span] = None


@dataclass
class Controller:
    name: str
    extends: Optional[str]
    compose: list[str]
    signals: list[Signal]
    ons: list[OnClause]
    whens: list[WhenClause]
    everys: list[EveryClause]
    span: Optional[Span] = None


@dataclass
class ContractAssert:
    left: str
    op: str
    right: str
    span: Optional[Span] = None


@dataclass
class Contract:
    name: str
    baseline: str
    seeds: list[int]
    scenarios: list[str]
    duration_s: float
    asserts: list[ContractAssert]
    reports: list[str]
    span: Optional[Span] = None


@dataclass
class PathModel:
    name: str
    fields: dict[str, str]
    span: Optional[Span] = None


@dataclass
class Program:
    version: str
    uses: list[str]
    controllers: list[Controller]
    contracts: list[Contract]
    paths: list[PathModel] = field(default_factory=list)
    source_name: str = "<input>"
