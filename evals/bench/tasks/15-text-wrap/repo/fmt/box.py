from fmt.wrap import wrap


def box(text: str, width: int = 20) -> str:
    lines = wrap(text, width)
    top = "+" + "-" * (width + 2) + "+"
    body = [f"| {line.ljust(width)} |" for line in lines]
    return "\n".join([top, *body, top])
