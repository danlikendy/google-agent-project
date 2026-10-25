"""Pull the few concrete anchors out of an issue: names, quotes, exceptions."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Words that show up in almost every issue and in almost every file.
# They are not evidence that a particular function is the one to edit.
STOP = frozenset(
    """
    a an the this that these those it its of to for from in on at by with
    and or but if then else when where while as into over under about above
    after before between during without within against per via than too very
    just only also not no nor so such same other another each few more most
    some any all both own same can cannot could would should may might must
    will shall do does did doing done be been being am is are was were has
    have had having get got using used use user users using fix fixed fixes
    bug bugs issue issues error errors fail fails failed failing failure
    problem problems please thanks thank hello hi using using code codes
    file files line lines function functions method methods class classes
    module modules package test tests testing tested call called calling
    return returns returned value values type types name names data info
    following expected actual instead still already because however like
    make makes made work works working example examples below above here
    there their they them you your we our shouldnt doesnt dont cant wont
    isnt arent wasnt werent hasnt havent hadnt
    true false none null self cls args kwargs var args
    """.split()
)

# A function literally named one of these is not identified by the issue
# just because the prose contains the same everyday word.
GENERIC_NAMES = frozenset(
    """
    main run setup init call test tests get set add new make load save
    read write open close update error helper utils data value name type
    item info config options wrap process handle execute render parse
    format copy clear reset apply create delete remove check validate
    build start stop send recv post put patch head
    """.split()
)

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
_QUOTED = re.compile(r"`([^`\n]{4,160})`|\"([^\"\n]{4,160})\"|'([^'\n]{4,160})'")
_PATH = re.compile(r"[A-Za-z0-9_./-]+\.py")

_BUILTIN_EXC = frozenset(
    """
    ArithmeticError AssertionError AttributeError EOFError FloatingPointError
    GeneratorExit ImportError IndentationError IndexError KeyError
    KeyboardInterrupt LookupError MemoryError NameError NotImplementedError
    OSError OverflowError RecursionError ReferenceError RuntimeError
    StopIteration SyntaxError SystemError SystemExit TabError TypeError
    UnboundLocalError UnicodeError UnicodeDecodeError UnicodeEncodeError
    ValueError ZeroDivisionError ConnectionError TimeoutError HTTPError
    JSONDecodeError FileNotFoundError PermissionError FileExistsError
    IsADirectoryError NotADirectoryError ProcessLookupError CancelledError
    """.split()
)


@dataclass(frozen=True)
class Anchors:
    identifiers: tuple[str, ...]
    tokens: tuple[str, ...]
    literals: tuple[str, ...]
    exceptions: tuple[str, ...]
    paths: tuple[str, ...]

    def ident_set(self) -> set[str]:
        return {item.lower() for item in self.identifiers}

    def token_set(self) -> set[str]:
        return set(self.tokens)


def split_ident(name: str) -> list[str]:
    parts: list[str] = []
    for piece in name.split("_"):
        if not piece:
            continue
        found = _CAMEL.findall(piece)
        parts.extend(found or [piece])
    return parts


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in _IDENT.findall(text):
        for part in split_ident(raw):
            token = part.lower()
            if len(token) < 3 or token in STOP or token in seen or token.isdigit():
                continue
            seen.add(token)
            out.append(token)
    return out


def is_exception_name(name: str) -> bool:
    return name in _BUILTIN_EXC or name.endswith(("Error", "Exception", "Warning"))


def extract(text: str) -> Anchors:
    if len(text) > 20000:
        text = text[:20000]

    identifiers: list[str] = []
    seen_idents: set[str] = set()
    for raw in _IDENT.findall(text):
        key = raw.lower()
        if len(raw) < 4 or key in STOP or key in seen_idents:
            continue
        seen_idents.add(key)
        identifiers.append(raw)
        if len(identifiers) >= 250:
            break

    literals: list[str] = []
    seen_lits: set[str] = set()
    for groups in _QUOTED.findall(text):
        raw = next(part for part in groups if part)
        snippet = " ".join(raw.split())
        key = snippet.casefold()
        if len(snippet) < 8 or len(snippet) > 160 or key in seen_lits:
            continue
        if key in STOP or " " not in snippet and key in GENERIC_NAMES:
            continue
        seen_lits.add(key)
        literals.append(snippet)
        if len(literals) >= 40:
            break

    exceptions = tuple(name for name in identifiers if is_exception_name(name))
    paths = tuple(dict.fromkeys(_PATH.findall(text)))
    return Anchors(
        identifiers=tuple(identifiers),
        tokens=tuple(tokenize(text)),
        literals=tuple(literals),
        exceptions=exceptions,
        paths=paths,
    )
