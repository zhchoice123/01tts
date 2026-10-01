"""Rewrite technical English into a form TTS voices read naturally.

Only the text sent to the speech provider changes. Displayed passages and
word-timing alignment keep the original text.
"""
import re

_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve "
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen"
).split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()

# Applied in order; longer and more specific patterns come first.
_TERMS = (
    (r"\bCI/CD\b", "C I C D"),
    (r"\bk8s\b", "Kubernetes"),
    (r"\bi18n\b", "internationalization"),
    (r"\bN\+1\b", "N plus one"),
    (r"\bgRPC\b", "G R P C"),
    (r"\bnginx\b", "engine X"),
    (r"\bkubectl\b", "kube control"),
    (r"\be\.g\.,?", "for example,"),
    (r"\bi\.e\.,?", "that is,"),
    (r"\betc\.", "et cetera."),
    (r"\bvs\.?(?=\s)", "versus"),
    (r"\s*(?:->|→)\s*", " to "),
)
_UNITS = {
    "ms": "milliseconds",
    "µs": "microseconds",
    "us": "microseconds",
    "ns": "nanoseconds",
    "KB": "kilobytes",
    "MB": "megabytes",
    "GB": "gigabytes",
    "TB": "terabytes",
    "KiB": "kibibytes",
    "MiB": "mebibytes",
    "GiB": "gibibytes",
}


def number_to_words(value: int) -> str:
    if value < 20:
        return _ONES[value]
    if value < 100:
        tens, ones = divmod(value, 10)
        return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")
    if value < 1000:
        hundreds, rest = divmod(value, 100)
        return f"{_ONES[hundreds]} hundred" + (f" {number_to_words(rest)}" if rest else "")
    raise ValueError("number_to_words supports values below 1000")


def _percentile(match: re.Match) -> str:
    digits = match.group(1)
    if len(digits) == 2:
        return f"P {number_to_words(int(digits))}"
    return "P " + " ".join(_ONES[int(digit)] for digit in digits)


def _identifier(match: re.Match) -> str:
    token = match.group(0)
    token = re.sub(r"\(\)$", "", token)
    token = token.replace("_", " ")
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", token)


def to_spoken_text(text: str) -> str:
    spoken = text.replace("`", "")
    for pattern, replacement in _TERMS:
        spoken = re.sub(pattern, replacement, spoken)
    spoken = re.sub(r"\bp(\d{2,3})\b", _percentile, spoken)
    unit_pattern = "|".join(sorted(map(re.escape, _UNITS), key=len, reverse=True))
    spoken = re.sub(
        rf"\b(\d+(?:\.\d+)?)\s?({unit_pattern})\b",
        lambda match: f"{match.group(1)} {_UNITS[match.group(2)]}",
        spoken,
    )
    spoken = re.sub(r"\b(\d+(?:\.\d+)?)x\b", r"\1 times", spoken)
    spoken = re.sub(r"@([A-Z]\w*)(?:\s+annotation)?", r"\1 annotation", spoken)
    # camelCase, snake_case, and call syntax: findById() -> find By Id
    spoken = re.sub(
        r"\b[A-Za-z]+(?:_[A-Za-z0-9]+)+\b(?:\(\))?|\b[a-z]+[a-z0-9]*(?:[A-Z][a-z0-9]*)+\b(?:\(\))?",
        _identifier,
        spoken,
    )
    spoken = re.sub(r"\b(\w+)\(\)", r"\1", spoken)
    return re.sub(r"[ \t]{2,}", " ", spoken).strip()
