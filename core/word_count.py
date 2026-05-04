DURATION_TARGETS = {
    "30 seconds": (65, 85),
    "45 seconds": (95, 115),
    "60 seconds": (120, 150),
}


def target_for(duration: str) -> tuple[int, int]:
    return DURATION_TARGETS.get(duration, (95, 115))


def count_words(text: str) -> int:
    return len([w for w in text.split() if w.strip()])


def is_within_target(text: str, duration: str) -> bool:
    lo, hi = target_for(duration)
    return lo <= count_words(text) <= hi
