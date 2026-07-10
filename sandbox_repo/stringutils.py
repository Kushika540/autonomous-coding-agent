"""String utility library."""


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
