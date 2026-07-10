import sys, os
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
