import re

_INLINE_COMMENT = re.compile(r"\s+#.*$")


def _parse_value(raw: str) -> str:
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        quote = raw[0]
        end = raw.find(quote, 1)
        if end != -1:
            inner = raw[1:end]
            return inner.replace("\\n", "\n") if quote == '"' else inner
    return _INLINE_COMMENT.sub("", raw).strip()


def parse(text: str) -> dict[str, str]:
    values = {}
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            raise ValueError(f"line {number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        values[key.strip()] = _parse_value(value)
    return values
