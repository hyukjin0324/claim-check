"""값 비교에 쓰는 정규화."""
import re
from datetime import date


def to_int(value):
    if value is None or isinstance(value, int):
        return value
    text = str(value).replace(",", "").replace("원", "").strip()
    return int(text) if re.fullmatch(r"-?\d+", text) else None


def clean(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def same_text(a, b):
    return re.sub(r"\s+", "", str(a)) == re.sub(r"\s+", "", str(b))


def masked_equal(a, b):
    """가려진 글자(*)를 빼고 같으면 참. 글자 수는 같아야 한다."""
    a, b = re.sub(r"\s+", "", str(a)), re.sub(r"\s+", "", str(b))
    if len(a) != len(b) or ("*" not in a and "*" not in b):
        return False
    return all(x == y or x == "*" or y == "*" for x, y in zip(a, b))


def to_date(value):
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
