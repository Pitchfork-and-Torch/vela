"""VELA recursive-descent parser."""
from __future__ import annotations

from vela.ast import (
    Contract,
    ContractAssert,
    Controller,
    EveryClause,
    Expr,
    MatchArm,
    OnClause,
    PathModel,
    Program,
    Signal,
    Span,
    Stmt,
    TypeRef,
    View,
    WhenClause,
)
from vela.lexer import LexError, Token, tokenize

ALLOWED_CUTS_COMPOSE = frozenset({"min"})
ALLOWED_GROWTH_COMPOSE = frozenset({"min", "max", "sum"})


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, src: str, name: str = "<input>"):
        self.tokens = tokenize(src)
        self.i = 0
        self.name = name
        self._src_text = src

    def cur(self) -> Token:
        return self.tokens[self.i]

    def at(self, *kinds: str) -> bool:
        t = self.cur()
        if t.kind in kinds:
            return True
        if t.kind == "KW" and t.value in kinds:
            return True
        return False

    def eat(self, *kinds: str) -> Token:
        t = self.cur()
        if kinds and not self.at(*kinds):
            want = "|".join(kinds)
            raise ParseError(
                f"{self.name}:{t.line}:{t.col}: expected {want}, got {t.kind} {t.value!r}"
            )
        self.i += 1
        return t

    def span(self) -> Span:
        t = self.cur()
        return Span(t.line, t.col)

    def parse(self) -> Program:
        if not (self.at("lang") or (self.at("KW") and self.cur().value == "lang")):
            raise ParseError(f"{self.name}: missing 'lang vela <version>' header")
        self.eat("lang")
        self.eat("vela")
        ver_tok = self.eat("NUMBER", "IDENT")
        uses: list[str] = []
        controllers: list[Controller] = []
        contracts: list[Contract] = []
        paths: list[PathModel] = []
        views: list[View] = []
        while not self.at("EOF"):
            if self.at("use"):
                self.eat("use")
                uses.append(self._dotted())
            elif self.at("controller"):
                controllers.append(self._controller())
            elif self.at("contract"):
                contracts.append(self._contract())
            elif self.at("path"):
                paths.append(self._path())
            elif self.at("view"):
                views.append(self._view())
            else:
                t = self.cur()
                raise ParseError(
                    f"{self.name}:{t.line}:{t.col}: unexpected {t.kind} {t.value!r}"
                )
        return Program(
            version=ver_tok.value,
            uses=uses,
            controllers=controllers,
            contracts=contracts,
            paths=paths,
            views=views,
            source_name=self.name,
            source_text=self._src_text,
        )

    def _name(self) -> str:
        t = self.cur()
        if t.kind == "IDENT" or t.kind == "KW":
            self.i += 1
            return t.value
        raise ParseError(
            f"{self.name}:{t.line}:{t.col}: expected name, got {t.kind} {t.value!r}"
        )

    def _dotted(self) -> str:
        parts = [self._name()]
        while self.at("DOT"):
            self.eat("DOT")
            parts.append(self._name())
        return ".".join(parts)

    def _controller(self) -> Controller:
        sp = self.span()
        self.eat("controller")
        name = self.eat("IDENT").value
        extends = None
        if self.at("extends"):
            self.eat("extends")
            extends = self.eat("IDENT").value
        self.eat("LBRACE")
        compose: list[str] = []
        cuts_compose: str | None = None
        growth_compose: str | None = None
        signals: list[Signal] = []
        ons: list[OnClause] = []
        whens: list[WhenClause] = []
        everys: list[EveryClause] = []
        authority: dict = {}
        while not self.at("RBRACE"):
            if self.at("compose"):
                self.eat("compose")
                names, cuts, growth = self._compose_directive()
                if names is not None:
                    compose = names
                if cuts is not None:
                    cuts_compose = cuts
                if growth is not None:
                    growth_compose = growth
            elif self.at("signals"):
                self.eat("signals")
                self.eat("COLON")
                while self.at("IDENT"):
                    signals.append(self._signal())
            elif self.at("authority"):
                self.eat("authority")
                authority.update(self._authority())
            elif self.at("on"):
                ons.append(self._on())
            elif self.at("integrate"):
                self.eat("integrate")
                if not self.at("when"):
                    t = self.cur()
                    raise ParseError(
                        f"{self.name}:{t.line}:{t.col}: integrate must precede when"
                    )
                w = self._when()
                w.integrate = True
                whens.append(w)
            elif self.at("when"):
                whens.append(self._when())
            elif self.at("every"):
                everys.append(self._every())
            else:
                t = self.cur()
                raise ParseError(
                    f"{self.name}:{t.line}:{t.col}: unexpected in controller: {t.value!r}"
                )
        self.eat("RBRACE")
        return Controller(
            name=name,
            extends=extends,
            compose=compose,
            signals=signals,
            ons=ons,
            whens=whens,
            everys=everys,
            authority=authority,
            cuts_compose=cuts_compose,
            growth_compose=growth_compose,
            span=sp,
        )

    def _authority(self) -> dict:
        out: dict = {}
        if self.at("LBRACE"):
            self.eat("LBRACE")
            while not self.at("RBRACE"):
                key = self._name()
                if self.at("COLON"):
                    self.eat("COLON")
                raw = self.eat("NUMBER").value
                out[key] = int(float(raw.rstrip("s")))
                if self.at("COMMA"):
                    self.eat("COMMA")
            self.eat("RBRACE")
            return out
        key = self._name()
        raw = self.eat("NUMBER").value
        out[key] = int(float(raw.rstrip("s")))
        return out

    def _view(self) -> View:
        sp = self.span()
        self.eat("view")
        name = self.eat("IDENT").value
        self.eat("of")
        ofc = self.eat("IDENT").value
        self.eat("LBRACE")
        compose: list[str] = []
        while not self.at("RBRACE"):
            if self.at("compose"):
                self.eat("compose")
                compose = self._compose_list()
            else:
                t = self.cur()
                raise ParseError(
                    f"{self.name}:{t.line}:{t.col}: unexpected in view: {t.value!r}"
                )
        self.eat("RBRACE")
        return View(name=name, of_controller=ofc, compose=compose, span=sp)

    def _peek(self, n: int = 1) -> Token:
        j = self.i + n
        if 0 <= j < len(self.tokens):
            return self.tokens[j]
        return self.tokens[-1]

    def _at_compose_combinator(self) -> bool:
        t = self.cur()
        if t.kind != "IDENT" or t.value not in ("cuts", "growth"):
            return False
        return self._peek(1).kind == "EQ_SIGN"

    def _at_trailing_compose_combinator(self) -> bool:
        if not self.at("compose"):
            return False
        nxt = self._peek(1)
        nxt2 = self._peek(2)
        return (
            nxt.kind == "IDENT"
            and nxt.value in ("cuts", "growth")
            and nxt2.kind == "EQ_SIGN"
        )

    def _compose_combinator(self) -> tuple[str, str]:
        kind = self.eat("IDENT").value
        self.eat("EQ_SIGN")
        val_tok = self.cur()
        val = self._name()
        if kind == "cuts":
            if val not in ALLOWED_CUTS_COMPOSE:
                raise ParseError(
                    f"{self.name}:{val_tok.line}:{val_tok.col}: "
                    f"compose cuts must be min, got {val!r}"
                )
        elif kind == "growth":
            if val not in ALLOWED_GROWTH_COMPOSE:
                raise ParseError(
                    f"{self.name}:{val_tok.line}:{val_tok.col}: "
                    f"compose growth must be min | max | sum, got {val!r}"
                )
        else:
            raise ParseError(
                f"{self.name}:{val_tok.line}:{val_tok.col}: "
                f"unknown compose combinator {kind!r}"
            )
        return kind, val

    def _compose_directive(self) -> tuple[list[str] | None, str | None, str | None]:
        names: list[str] | None = None
        cuts: str | None = None
        growth: str | None = None
        if self._at_compose_combinator():
            kind, val = self._compose_combinator()
            if kind == "cuts":
                cuts = val
            else:
                growth = val
        else:
            names = self._compose_list()
        while self._at_trailing_compose_combinator():
            self.eat("compose")
            kind, val = self._compose_combinator()
            if kind == "cuts":
                cuts = val
            else:
                growth = val
        return names, cuts, growth

    def _compose_list(self) -> list[str]:
        names = [self.eat("IDENT").value]
        while self.at("PLUS"):
            self.eat("PLUS")
            names.append(self.eat("IDENT").value)
        return names

    def _signal(self) -> Signal:
        sp = self.span()
        name = self.eat("IDENT").value
        self.eat("COLON")
        typ = self._type()
        return Signal(name=name, typ=typ, span=sp)

    def _type(self) -> TypeRef:
        sp = self.span()
        name = self.eat("IDENT").value
        inner = None
        if self.at("LT"):
            self.eat("LT")
            inner = self._type()
            self.eat("GT")
        at_epoch = None
        if self.at("AT"):
            self.eat("AT")
            at_epoch = self.eat("IDENT").value
        return TypeRef(name=name, inner=inner, at_epoch=at_epoch, span=sp)

    def _on(self) -> OnClause:
        sp = self.span()
        self.eat("on")
        event = self.eat("IDENT").value
        binder = ""
        if self.at("LPAREN"):
            self.eat("LPAREN")
            binder = self.eat("IDENT").value
            self.eat("RPAREN")
        match_arms: list[MatchArm] = []
        body: list[Stmt] = []
        if self.at("match"):
            self.eat("match")
            if self.at("IDENT"):
                self.eat("IDENT")
            self.eat("LBRACE")
            while not self.at("RBRACE"):
                pat = self.eat("IDENT").value
                self.eat("ARROW")
                arm_body = self._stmt_or_block()
                if self.at("COMMA"):
                    self.eat("COMMA")
                match_arms.append(MatchArm(pattern=pat, body=arm_body))
            self.eat("RBRACE")
        else:
            body = self._block()
        return OnClause(
            event=event,
            binder=binder,
            match_arms=match_arms,
            body=body,
            span=sp,
        )

    def _when(self) -> WhenClause:
        sp = self.span()
        self.eat("when")
        pred = self._expr()
        body = self._block()
        return WhenClause(pred=pred, body=body, span=sp)

    def _every(self) -> EveryClause:
        sp = self.span()
        self.eat("every")
        tick = self.eat("IDENT").value
        body = self._block()
        return EveryClause(tick=tick, body=body, span=sp)

    def _block(self) -> list[Stmt]:
        self.eat("LBRACE")
        out: list[Stmt] = []
        while not self.at("RBRACE"):
            out.append(self._stmt())
        self.eat("RBRACE")
        return out

    def _stmt_or_block(self) -> list[Stmt]:
        if self.at("LBRACE"):
            return self._block()
        return [self._stmt()]

    def _stmt(self) -> Stmt:
        sp = self.span()
        if self.at("invalidate"):
            self.eat("invalidate")
            names = [self.eat("IDENT").value]
            while self.at("COMMA"):
                self.eat("COMMA")
                names.append(self.eat("IDENT").value)
            return Stmt(kind="invalidate", args=names, span=sp)
        if self.at("enter"):
            self.eat("enter")
            name = self.eat("IDENT").value
            args: list[object] = []
            if self.at("LPAREN"):
                args = self._call_args()
            return Stmt(kind="enter", name=name, args=args, span=sp)
        if self.at("freeze"):
            self.eat("freeze")
            names = [self.eat("IDENT").value]
            while self.at("COMMA"):
                self.eat("COMMA")
                names.append(self.eat("IDENT").value)
            dur = None
            if self.at("for"):
                self.eat("for")
                dur = self._expr()
            return Stmt(kind="freeze", args=names, expr=dur, span=sp)
        if self.at("hold"):
            self.eat("hold")
            return Stmt(kind="hold", span=sp)
        if self.at("cut"):
            self.eat("cut")
            expr = None
            if self.at("LPAREN"):
                self.eat("LPAREN")
                expr = self._expr()
                self.eat("RPAREN")
            return Stmt(kind="cut", expr=expr, span=sp)
        if self.at("chase"):
            self.eat("chase")
            what = self.eat("IDENT").value
            self.eat("toward")
            target = self._expr()
            rollback = None
            if self.at("rollback"):
                self.eat("rollback")
                self.eat("if")
                rollback = self._expr()
            return Stmt(
                kind="chase",
                name=what,
                expr=target,
                args=[rollback] if rollback else [],
                span=sp,
            )
        if self.at("require"):
            self.eat("require")
            pred = self._expr()
            self.eat("then")
            then_body = self._stmt_or_block()
            else_body: list[Stmt] = []
            if self.at("else"):
                self.eat("else")
                else_body = self._stmt_or_block()
            return Stmt(
                kind="require",
                expr=pred,
                body=then_body,
                args=else_body,
                span=sp,
            )
        if self.at("let"):
            self.eat("let")
            name = self.eat("IDENT").value
            self.eat("EQ_SIGN")
            expr = self._expr()
            return Stmt(kind="let", name=name, expr=expr, span=sp)
        # assignment / scale: pace *= 0.94
        if self.at("IDENT"):
            name = self.eat("IDENT").value
            if self.at("STAREQ", "PLUSEQ", "MINUSEQ", "SLASHEQ", "EQ_SIGN"):
                op = self.eat("STAREQ", "PLUSEQ", "MINUSEQ", "SLASHEQ", "EQ_SIGN")
                expr = self._expr()
                return Stmt(kind="assign", name=name, args=[op.value], expr=expr, span=sp)
            raise ParseError(
                f"{self.name}:{sp.line}:{sp.col}: unexpected identifier {name!r}"
            )
        t = self.cur()
        raise ParseError(f"{self.name}:{t.line}:{t.col}: unknown statement {t.value!r}")

    def _call_args(self) -> list[object]:
        self.eat("LPAREN")
        args: list[object] = []
        if not self.at("RPAREN"):
            while True:
                nxt = self.tokens[self.i + 1] if self.i + 1 < len(self.tokens) else None
                if (self.at("IDENT") or self.cur().kind == "KW") and nxt is not None and nxt.kind == "COLON":
                    key = self._name()
                    self.eat("COLON")
                    args.append((key, self._expr()))
                else:
                    args.append(self._expr())
                if not self.at("COMMA"):
                    break
                self.eat("COMMA")
        self.eat("RPAREN")
        return args

    def _expr(self) -> Expr:
        return self._or_cmp()

    def _or_cmp(self) -> Expr:
        left = self._add()
        while self.at("GT", "LT", "GE", "LE", "EQ", "NE"):
            op = self.eat("GT", "LT", "GE", "LE", "EQ", "NE")
            right = self._add()
            left = Expr(kind="binop", name=op.value, left=left, right=right, span=left.span)
        return left

    def _add(self) -> Expr:
        left = self._mul()
        while self.at("PLUS", "MINUS"):
            op = self.eat("PLUS", "MINUS")
            right = self._mul()
            left = Expr(kind="binop", name=op.value, left=left, right=right, span=left.span)
        return left

    def _mul(self) -> Expr:
        left = self._unary()
        while self.at("STAR", "SLASH"):
            op = self.eat("STAR", "SLASH")
            right = self._unary()
            left = Expr(kind="binop", name=op.value, left=left, right=right, span=left.span)
        return left

    def _unary(self) -> Expr:
        if self.at("MINUS"):
            sp = self.span()
            self.eat("MINUS")
            inner = self._unary()
            return Expr(kind="neg", left=inner, span=sp)
        return self._primary()

    def _primary(self) -> Expr:
        sp = self.span()
        if self.at("NUMBER"):
            raw = self.eat("NUMBER").value
            return Expr(kind="num", value=raw, span=sp)
        if self.at("STRING"):
            return Expr(kind="str", value=self.eat("STRING").value, span=sp)
        if self.at("LPAREN"):
            self.eat("LPAREN")
            inner = self._expr()
            self.eat("RPAREN")
            return inner
        if self.at("LBRACK"):
            self.eat("LBRACK")
            xs: list[Expr] = []
            if not self.at("RBRACK"):
                xs.append(self._expr())
                while self.at("COMMA"):
                    self.eat("COMMA")
                    xs.append(self._expr())
            self.eat("RBRACK")
            return Expr(kind="list", args=xs, span=sp)
        if self.at("IDENT") or self.at("hold", "cut"):
            name = self.eat("IDENT", "hold", "cut").value
            expr = Expr(kind="name", name=name, span=sp)
            while True:
                if self.at("DOT"):
                    self.eat("DOT")
                    attr = self.eat("IDENT").value
                    call_args: list[Expr] = []
                    if self.at("LPAREN"):
                        self.eat("LPAREN")
                        if not self.at("RPAREN"):
                            call_args.append(self._expr())
                            while self.at("COMMA"):
                                self.eat("COMMA")
                                call_args.append(self._expr())
                        self.eat("RPAREN")
                        expr = Expr(
                            kind="call",
                            name=attr,
                            left=expr,
                            args=call_args,
                            span=sp,
                        )
                    else:
                        expr = Expr(kind="attr", name=attr, left=expr, span=sp)
                    continue
                if self.at("LPAREN"):
                    self.eat("LPAREN")
                    call_args = []
                    if not self.at("RPAREN"):
                        call_args.append(self._expr())
                        while self.at("COMMA"):
                            self.eat("COMMA")
                            call_args.append(self._expr())
                    self.eat("RPAREN")
                    expr = Expr(kind="call", name=name, left=expr, args=call_args, span=sp)
                    continue
                break
            return expr
        t = self.cur()
        raise ParseError(f"{self.name}:{t.line}:{t.col}: expected expression, got {t.value!r}")

    def _contract(self) -> Contract:
        sp = self.span()
        self.eat("contract")
        name = self.eat("IDENT").value
        baseline = "BBRv3approx"
        if self.at("vs"):
            self.eat("vs")
            baseline = self.eat("IDENT").value
        self.eat("LBRACE")
        seeds: list[int] = [13, 7, 42, 99, 123]
        scenarios = ["leo_fast_ho"]
        duration_s = 90.0
        asserts: list[ContractAssert] = []
        reports: list[str] = []
        while not self.at("RBRACE"):
            if self.at("seeds") or (self.at("IDENT") and self.cur().value == "seeds"):
                if self.at("seeds"):
                    self.eat("seeds")
                else:
                    self.eat("IDENT")
                self.eat("EQ_SIGN")
                lst = self._expr()
                seeds = [int(float(_num_text(e))) for e in lst.args]
            elif self.at("scenario"):
                self.eat("scenario")
                scenarios = [self.eat("IDENT").value]
                if self.at("duration"):
                    self.eat("duration")
                    duration_s = _parse_duration(self.eat("NUMBER").value)
            elif self.at("assert"):
                self.eat("assert")
                left = self._contract_ref()
                op = self.eat("GE", "LE", "GT", "LT", "EQ").value
                right = self._contract_ref()
                asserts.append(ContractAssert(left=left, op=op, right=right, span=sp))
            elif self.at("report"):
                self.eat("report")
                reports.append(self._dotted_or_call())
                while self.at("COMMA"):
                    self.eat("COMMA")
                    reports.append(self._dotted_or_call())
            elif self.at("IDENT") and self.cur().value == "duration":
                self.eat("IDENT")
                self.eat("EQ_SIGN")
                duration_s = _parse_duration(self.eat("NUMBER").value)
            else:
                t = self.cur()
                raise ParseError(
                    f"{self.name}:{t.line}:{t.col}: unexpected in contract: {t.value!r}"
                )
        self.eat("RBRACE")
        return Contract(
            name=name,
            baseline=baseline,
            seeds=seeds,
            scenarios=scenarios,
            duration_s=duration_s,
            asserts=asserts,
            reports=reports,
            span=sp,
        )

    def _contract_ref(self) -> str:
        if self.at("NUMBER"):
            raw = self.eat("NUMBER").value
            if self.at("IDENT") and self.cur().value in ("Mbps", "ms", "s"):
                raw = raw + self.eat("IDENT").value
            return raw
        parts = [self.eat("IDENT").value]
        while self.at("DOT") or self.at("LPAREN"):
            if self.at("DOT"):
                self.eat("DOT")
                parts.append(self.eat("IDENT").value)
            else:
                self.eat("LPAREN")
                inner = self.eat("IDENT").value
                self.eat("RPAREN")
                parts[-1] = f"{parts[-1]}({inner})"
        return ".".join(parts)

    def _dotted_or_call(self) -> str:
        name = self.eat("IDENT").value
        if self.at("LPAREN"):
            self.eat("LPAREN")
            arg = ""
            if not self.at("RPAREN"):
                arg = self.eat("NUMBER", "IDENT").value
            self.eat("RPAREN")
            return f"{name}({arg})"
        return name

    def _path(self) -> PathModel:
        sp = self.span()
        self.eat("path")
        name = self.eat("IDENT").value
        self.eat("LBRACE")
        fields: dict[str, str] = {}
        while not self.at("RBRACE"):
            key = self.eat("IDENT").value
            if self.at("TILDE"):
                self.eat("TILDE")
            elif self.at("EQ_SIGN"):
                self.eat("EQ_SIGN")
            # slurp until newline-ish: next ident-at-bol or rbrace. We take rest of "statement"
            bits: list[str] = []
            while not self.at("RBRACE") and not (
                self.at("IDENT") and self._looks_like_field_start()
            ):
                bits.append(self.eat(self.cur().kind).value)
                if len(bits) > 24:
                    break
            fields[key] = " ".join(bits)
        self.eat("RBRACE")
        return PathModel(name=name, fields=fields, span=sp)

    def _looks_like_field_start(self) -> bool:
        nxt = self.tokens[self.i + 1] if self.i + 1 < len(self.tokens) else None
        return nxt is not None and nxt.kind in ("TILDE", "EQ_SIGN")


def _num_text(e: Expr) -> str:
    if e.kind == "num":
        return str(e.value)
    if e.kind == "neg" and e.left is not None:
        return "-" + _num_text(e.left)
    raise ParseError("expected number in list")


def _parse_duration(raw: str) -> float:
    s = raw.strip().lower()
    if s.endswith("ms"):
        return float(s[:-2]) / 1000.0
    if s.endswith("s"):
        return float(s[:-1])
    return float(s)


def parse(src: str, name: str = "<input>") -> Program:
    try:
        return Parser(src, name).parse()
    except LexError as e:
        raise ParseError(str(e)) from e
