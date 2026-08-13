"""VELA lexer."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator


KEYWORDS = {
    "lang",
    "vela",
    "use",
    "controller",
    "extends",
    "compose",
    "signals",
    "on",
    "when",
    "every",
    "match",
    "contract",
    "vs",
    "assert",
    "require",
    "report",
    "let",
    "enter",
    "invalidate",
    "freeze",
    "hold",
    "cut",
    "chase",
    "rollback",
    "if",
    "then",
    "else",
    "for",
    "toward",
    "path",
    "mechanism",
    "type",
    "of",
    "integrate",
    "authority",
    "view",
    "duration",
    "scenario",
    "seeds",
}

MULTI = {
    ">=": "GE",
    "<=": "LE",
    "==": "EQ",
    "!=": "NE",
    "=>": "ARROW",
    "*=": "STAREQ",
    "+=": "PLUSEQ",
    "-=": "MINUSEQ",
    "/=": "SLASHEQ",
}


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    col: int


class LexError(Exception):
    pass


def tokenize(src: str) -> list[Token]:
    return list(_tokenize(src))


def _tokenize(src: str) -> Iterator[Token]:
    i = 0
    n = len(src)
    line = 1
    col = 1

    def peek(k: int = 0) -> str:
        j = i + k
        return src[j] if j < n else ""

    def adv(k: int = 1) -> None:
        nonlocal i, line, col
        for _ in range(k):
            if i < n:
                if src[i] == "\n":
                    line += 1
                    col = 1
                else:
                    col += 1
                i += 1

    while i < n:
        ch = src[i]
        if ch in " \t\r":
            adv()
            continue
        if ch == "\n":
            adv()
            continue
        if ch == "/" and peek(1) == "/":
            while i < n and src[i] != "\n":
                adv()
            continue
        if ch == "#" and (col == 1 or src[i - 1] in " \t"):
            while i < n and src[i] != "\n":
                adv()
            continue
        sl, sc = line, col
        two = ch + peek(1)
        if two in MULTI:
            yield Token(MULTI[two], two, sl, sc)
            adv(2)
            continue
        if ch in "{}()[],.:|+*/=@~<>":
            kind = {
                "{": "LBRACE",
                "}": "RBRACE",
                "(": "LPAREN",
                ")": "RPAREN",
                "[": "LBRACK",
                "]": "RBRACK",
                ",": "COMMA",
                ".": "DOT",
                ":": "COLON",
                "|": "PIPE",
                "+": "PLUS",
                "*": "STAR",
                "/": "SLASH",
                "=": "EQ_SIGN",
                "@": "AT",
                "~": "TILDE",
                "<": "LT",
                ">": "GT",
            }[ch]
            yield Token(kind, ch, sl, sc)
            adv()
            continue
        if ch == "-":
            if peek(1).isdigit():
                start = i
                adv()
                while peek().isdigit() or peek() in ".eE":
                    adv()
                yield Token("NUMBER", src[start:i], sl, sc)
                continue
            yield Token("MINUS", "-", sl, sc)
            adv()
            continue
        if ch.isdigit():
            start = i
            while peek().isdigit() or peek() in ".eE":
                adv()
            # units glued to numbers: ms Mbps s
            while peek().isalpha():
                adv()
            yield Token("NUMBER", src[start:i], sl, sc)
            continue
        if ch.isalpha() or ch == "_":
            start = i
            while peek().isalnum() or peek() == "_":
                adv()
            word = src[start:i]
            kind = "KW" if word in KEYWORDS else "IDENT"
            yield Token(kind, word, sl, sc)
            continue
        if ch in "\"'":
            quote = ch
            adv()
            start = i
            while i < n and src[i] != quote:
                if src[i] == "\n":
                    raise LexError(f"{line}:{col}: unterminated string")
                adv()
            val = src[start:i]
            if peek() != quote:
                raise LexError(f"{line}:{col}: unterminated string")
            adv()
            yield Token("STRING", val, sl, sc)
            continue
        raise LexError(f"{line}:{col}: unexpected {ch!r}")
    yield Token("EOF", "", line, col)
