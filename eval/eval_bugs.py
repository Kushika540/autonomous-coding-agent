"""
Bug definitions for the evaluation harness.

Each entry is a fully self-contained scenario: the buggy file contents,
the correct tests that should catch the bug, and a task description
(mirroring what a real bug report / GitHub issue would say). The harness
resets sandbox_repo/ to exactly these files before each run.

Bugs are deliberately varied in module, bug type, and difficulty so the
eval result means something beyond "can it fix this one specific bug."
"""

BUGS = [
    {
        "id": "palindrome_self_compare",
        "difficulty": "easy",
        "task": "The test suite in tests/test_stringutils.py is failing. "
                "Explore the repo, find the bug, fix it, and confirm all tests pass.",
        "files": {
            "stringutils.py": '''"""String utility library."""


def is_palindrome(s: str) -> bool:
    """Return True if s is a palindrome, ignoring case and spaces."""
    cleaned = s.lower().replace(" ", "")
    return cleaned == cleaned  # BUG: compares string to itself


def count_vowels(s: str) -> int:
    vowels = set("aeiou")
    return sum(1 for ch in s.lower() if ch in vowels)


def reverse_words(s: str) -> str:
    return " ".join(s.split()[::-1])


def title_case(s: str) -> str:
    return " ".join(word.capitalize() for word in s.split())
''',
            "tests/test_stringutils.py": '''import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from stringutils import is_palindrome, count_vowels, reverse_words, title_case

def test_is_palindrome_true():
    assert is_palindrome("racecar") is True
    assert is_palindrome("Was it a car or a cat I saw") is True

def test_is_palindrome_false():
    assert is_palindrome("hello") is False

def test_count_vowels():
    assert count_vowels("hello world") == 3

def test_reverse_words():
    assert reverse_words("the quick brown fox") == "fox brown quick the"

def test_title_case():
    assert title_case("hello world") == "Hello World"
''',
        },
    },
    {
        "id": "vowel_count_off_by_missing_y",
        "difficulty": "easy",
        "task": "The test suite in tests/test_stringutils.py is failing. "
                "Explore the repo, find the bug, fix it, and confirm all tests pass.",
        "files": {
            "stringutils.py": '''"""String utility library."""

VOWELS = set("aeiouy")  # BUG: 'y' should not count as a vowel here


def count_vowels(s: str) -> int:
    return sum(1 for ch in s.lower() if ch in VOWELS)


def reverse_words(s: str) -> str:
    return " ".join(s.split()[::-1])
''',
            "tests/test_stringutils.py": '''import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from stringutils import count_vowels, reverse_words

def test_count_vowels_no_y():
    assert count_vowels("sky") == 0

def test_count_vowels_normal():
    assert count_vowels("hello world") == 3

def test_reverse_words():
    assert reverse_words("a b c") == "c b a"
''',
        },
    },
    {
        "id": "average_wrong_divisor",
        "difficulty": "medium",
        "task": "The test suite in tests/test_mathutils.py is failing. "
                "Explore the repo, find the bug, fix it, and confirm all tests pass.",
        "files": {
            "mathutils.py": '''"""Math utility library."""


def average(numbers):
    """Return the arithmetic mean of a list of numbers."""
    if not numbers:
        raise ValueError("cannot average an empty list")
    return sum(numbers) / (len(numbers) - 1)  # BUG: off-by-one divisor


def is_prime(n: int) -> bool:
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True


def factorial(n: int) -> int:
    if n < 0:
        raise ValueError("factorial undefined for negative numbers")
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result
''',
            "tests/test_mathutils.py": '''import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from mathutils import average, is_prime, factorial

def test_average():
    assert average([1, 2, 3, 4]) == 2.5
    assert average([5, 5, 5]) == 5

def test_is_prime():
    assert is_prime(7) is True
    assert is_prime(8) is False
    assert is_prime(1) is False

def test_factorial():
    assert factorial(5) == 120
    assert factorial(0) == 1
''',
        },
    },
    {
        "id": "dedupe_loses_order",
        "difficulty": "medium",
        "task": "The test suite in tests/test_listutils.py is failing. "
                "Explore the repo, find the bug, fix it, and confirm all tests pass.",
        "files": {
            "listutils.py": '''"""List utility library."""


def dedupe(items):
    """Remove duplicates while preserving first-seen order."""
    return list(set(items))  # BUG: set() does not preserve order


def flatten(nested):
    result = []
    for item in nested:
        if isinstance(item, list):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result


def chunk(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]
''',
            "tests/test_listutils.py": '''import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from listutils import dedupe, flatten, chunk

def test_dedupe_preserves_order():
    assert dedupe([3, 1, 3, 2, 1]) == [3, 1, 2]

def test_flatten():
    assert flatten([1, [2, 3], [4, [5, 6]]]) == [1, 2, 3, 4, 5, 6]

def test_chunk():
    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
''',
        },
    },
    {
        "id": "multi_file_helper_bug",
        "difficulty": "hard",
        "task": "The test suite in tests/test_report.py is failing. "
                "The bug is not necessarily in the file the tests import directly -- "
                "explore the repo to find the actual root cause, fix it, and confirm "
                "all tests pass.",
        "files": {
            "formatting.py": '''"""Low-level formatting helpers used by report.py."""


def format_percentage(value: float) -> str:
    """Format a 0-1 float as a percentage string, e.g. 0.5 -> '50.0%'."""
    return f"{value * 100:.1f}"  # BUG: missing the '%' suffix
''',
            "report.py": '''"""Generates a simple summary report. Depends on formatting.py."""
from formatting import format_percentage


def summarize(pass_count: int, total: int) -> str:
    if total == 0:
        return "No results."
    rate = pass_count / total
    return f"{pass_count}/{total} passed ({format_percentage(rate)})"
''',
            "tests/test_report.py": '''import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from report import summarize

def test_summarize_full():
    assert summarize(10, 10) == "10/10 passed (100.0%)"

def test_summarize_partial():
    assert summarize(3, 4) == "3/4 passed (75.0%)"

def test_summarize_empty():
    assert summarize(0, 0) == "No results."
''',
        },
    },
    {
        "id": "chunk_wrong_boundary",
        "difficulty": "medium",
        "task": "The test suite in tests/test_listutils.py is failing. "
                "Explore the repo, find the bug, fix it, and confirm all tests pass.",
        "files": {
            "listutils.py": '''"""List utility library."""


def dedupe(items):
    seen = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def flatten(nested):
    result = []
    for item in nested:
        if isinstance(item, list):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result


def chunk(items, size):
    """Split items into chunks of the given size."""
    return [items[i:i + size + 1] for i in range(0, len(items), size)]  # BUG: off-by-one in slice end
''',
            "tests/test_listutils.py": '''import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from listutils import dedupe, flatten, chunk

def test_dedupe():
    assert dedupe([1, 1, 2, 3, 2]) == [1, 2, 3]

def test_flatten():
    assert flatten([[1], [2, [3]]]) == [1, 2, 3]

def test_chunk():
    assert chunk([1, 2, 3, 4, 5, 6], 3) == [[1, 2, 3], [4, 5, 6]]
    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
''',
        },
    },
    {
        "id": "mutable_default_argument",
        "difficulty": "hard",
        "task": "The test suite in tests/test_cart.py is failing. "
                "Explore the repo, find the bug, fix it, and confirm all tests pass.",
        "files": {
            "cart.py": '''"""Shopping cart helper."""


def add_item(item, cart=[]):
    """Add an item to a cart and return it. If no cart is given, starts fresh."""
    cart.append(item)
    return cart
''',
            "tests/test_cart.py": '''import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cart import add_item

def test_default_cart_is_fresh_each_call():
    cart_a = add_item("apple")
    cart_b = add_item("banana")
    assert cart_a == ["apple"]
    assert cart_b == ["banana"]

def test_explicit_cart_still_works():
    my_cart = []
    result = add_item("milk", my_cart)
    assert result == ["milk"]
''',
        },
    },
    {
        "id": "inverted_priority_sort",
        "difficulty": "hard",
        "task": "The test suite in tests/test_sorting.py is failing. "
                "Explore the repo, find the bug, fix it, and confirm all tests pass.",
        "files": {
            "sorting.py": '''"""Task priority sorting."""


def sort_by_priority(tasks):
    """Sort tasks so the highest-priority task comes first.
    Priority is a number where LOWER means MORE important (priority 1
    outranks priority 3), matching how most ticket systems define it."""
    return sorted(tasks, key=lambda t: -t["priority"])
''',
            "tests/test_sorting.py": '''import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorting import sort_by_priority

def test_lower_priority_number_sorts_first():
    tasks = [
        {"name": "a", "priority": 2},
        {"name": "b", "priority": 1},
        {"name": "c", "priority": 3},
    ]
    result = sort_by_priority(tasks)
    assert [t["name"] for t in result] == ["b", "a", "c"]
''',
        },
    },
    {
        "id": "duplicated_config_constant",
        "difficulty": "hard",
        "task": "The test suite in tests/test_client.py is failing. "
                "The relevant constant already exists somewhere in the repo -- "
                "explore before assuming you need to invent a new value. "
                "Fix the bug and confirm all tests pass.",
        "files": {
            "config.py": '''"""Shared configuration constants."""

MAX_RETRIES = 3
''',
            "client.py": '''"""Network client with retry logic."""
from config import MAX_RETRIES


def fetch_with_retries(fetch_fn):
    """Call fetch_fn, retrying on failure up to MAX_RETRIES times total.
    Returns (result, attempts_used) on success, re-raises the last error
    if every attempt fails."""
    attempts = 0
    last_error = None
    for _ in range(5):
        attempts += 1
        try:
            return fetch_fn(), attempts
        except Exception as e:
            last_error = e
    raise last_error
''',
            "tests/test_client.py": '''import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from client import fetch_with_retries
from config import MAX_RETRIES

def test_gives_up_after_exactly_max_retries():
    calls = {"count": 0}
    def always_fails():
        calls["count"] += 1
        raise ValueError("simulated failure")

    try:
        fetch_with_retries(always_fails)
    except ValueError:
        pass

    actual = calls["count"]
    assert actual == MAX_RETRIES, f"expected exactly {MAX_RETRIES} attempts, got {actual}"

def test_succeeds_within_budget():
    calls = {"count": 0}
    def fails_once_then_succeeds():
        calls["count"] += 1
        if calls["count"] < 2:
            raise ValueError("simulated failure")
        return "ok"

    result, attempts_used = fetch_with_retries(fails_once_then_succeeds)
    assert result == "ok"
    assert attempts_used == 2
''',
        },
    },
    {
        "id": "missing_right_subtree_recursion",
        "difficulty": "hard",
        "task": "The test suite in tests/test_treeutils.py is failing. "
                "Explore the repo, find the bug, fix it, and confirm all tests pass.",
        "files": {
            "treeutils.py": '''"""Binary tree utilities.

Trees are represented as nested dicts:
{"value": int, "left": dict | None, "right": dict | None}
"""


def tree_sum(node):
    """Return the sum of all values in the tree rooted at node."""
    if node is None:
        return 0
    total = node["value"]
    if node.get("left"):
        total += tree_sum(node["left"])
    return total
''',
            "tests/test_treeutils.py": '''import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from treeutils import tree_sum

def test_sums_both_branches():
    tree = {
        "value": 1,
        "left": {"value": 2, "left": None, "right": None},
        "right": {"value": 3, "left": None, "right": None},
    }
    assert tree_sum(tree) == 6

def test_single_node():
    assert tree_sum({"value": 5, "left": None, "right": None}) == 5

def test_empty_tree():
    assert tree_sum(None) == 0

def test_deeper_right_branch():
    tree = {
        "value": 1,
        "left": None,
        "right": {
            "value": 2,
            "left": None,
            "right": {"value": 3, "left": None, "right": None},
        },
    }
    assert tree_sum(tree) == 6
''',
        },
    },
]
