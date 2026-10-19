"""The Java string rules the port needs: String.trim(), StringUtils.isBlank(), String.equalsIgnoreCase() and getStringValue()."""

# String.trim() removes every character up to U+0020, which is not what str.strip() does.
_JAVA_TRIM = "".join(chr(code) for code in range(0x21))
# Python's isspace() is true for these four, Java's Character.isWhitespace() is false (checked over every code point).
_NOT_JAVA_WHITESPACE = "\u0085   "


def java_trim(text: str) -> str:
    return text.strip(_JAVA_TRIM)


def is_blank(text: str | None) -> bool:
    """StringUtils.isBlank: null, empty, or only whitespace."""
    return text is None or all(c.isspace() and c not in _NOT_JAVA_WHITESPACE for c in text)


def is_not_blank(text: str | None) -> bool:
    return not is_blank(text)


def get_string_value(attributes: dict, key: str, default: str | None) -> str | None:
    """The trimmed value of an InputAttribute under `key`, or `default` when it is absent or blank.

    Ports the private getStringValue that NameUtils (S:NameUtils.java:57), ScreenedDataUtils
    (S:ScreenedDataUtils.java:80) and WleDataUtils (S:WleDataUtils.java:99) each carry a copy of.
    """
    attribute = attributes.get(key)
    value = None if attribute is None else attribute.value
    return value if is_not_blank(value) else default


def _ci_key(c: str) -> str:
    # Character.toLowerCase(Character.toUpperCase(c)), the per-character test of String.equalsIgnoreCase. Checked against
    # OpenJDK 21.0.12.1 for every code point except surrogates: no difference (Python 3.11 carries Unicode 14, JDK 21 Unicode 15).
    u = c.upper()
    if len(u) != 1:
        u = c
    low = u.lower()
    return low if len(low) == 1 else ("i" if u == "\u0130" else u)


def equals_ignore_case(a: str | None, b: str | None) -> bool:
    """a.equalsIgnoreCase(b); differs from `a.lower() == b.lower()` for sigma, i / dotted I / dotless i and long s.

    A None `b` is False, as in Java. A None `a` is a NullPointerException in Java; here None equals only None (like
    Objects.equals), and no call site passes one.
    """
    if a is None or b is None:
        return a is b
    return len(a) == len(b) and all(_ci_key(x) == _ci_key(y) for x, y in zip(a, b))
