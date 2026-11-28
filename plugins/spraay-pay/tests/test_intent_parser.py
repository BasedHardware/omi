from decimal import Decimal

import pytest

from payment.intent_parser import parse_intent, parse_pay_command, words_to_int


@pytest.mark.parametrize(
    "text, amount, url",
    [
        ("Pay $5 to api.example.com", "5", "https://api.example.com"),
        ("please pay $5.50 to https://api.example.com/v1/data?x=1.", "5.50", "https://api.example.com/v1/data?x=1"),
        ("send $12 to data.example.org for the report", "12", "https://data.example.org"),
        ("pay five dollars to api dot example dot com", "5", "https://api.example.com"),
        ("send twenty five bucks to api.example.com", "25", "https://api.example.com"),
        ("pay two dollars and fifty cents to api.example.com", "2.50", "https://api.example.com"),
        ("pay fifty cents to api.example.com", "0.50", "https://api.example.com"),
        ("buy this for $3 at shop.example.com", "3", "https://shop.example.com"),
        ("purchase the report for 10 usdc from reports.example.io", "10", "https://reports.example.io"),
        ("subscribe to news.example.com for $4", "4", "https://news.example.com"),
        ("pay $1,250.75 to api.example.com", "1250.75", "https://api.example.com"),
    ],
)
def test_extracts_amount_and_target(text, amount, url):
    intent = parse_intent(text)
    assert intent is not None and intent.actionable
    assert intent.amount == Decimal(amount)
    assert intent.target_url == url


@pytest.mark.parametrize(
    "text",
    [
        "I don't want to pay $5 to api.example.com",
        "I would pay $5 for that",
        "should I pay $5 to api.example.com",
        "if you buy this for $5 tell me",
        "my pay was $500 last week",
        "the weather is lovely today",
        "never send $5 to api.example.com",
    ],
)
def test_ignores_non_requests(text):
    assert parse_intent(text) is None


def test_extracts_recipient_and_description():
    intent = parse_intent("send $5 to alice for lunch")
    assert intent.recipient == "alice"
    assert intent.description == "lunch"
    assert intent.target_url is None
    assert not intent.actionable


def test_pay_for_description_with_url():
    intent = parse_intent("Pay $5 to api.example.com for the weather data.")
    assert intent.description == "the weather data"


def test_missing_amount_is_not_actionable():
    intent = parse_intent("subscribe to news.example.com")
    assert intent.amount is None
    assert not intent.actionable


def test_rejects_precision_finer_than_usdc():
    assert parse_intent("pay $1.1234567 to api.example.com").amount is None


def test_amount_is_taken_from_the_same_sentence():
    assert parse_intent("It cost $9 before. Pay api.example.com now").amount is None


def test_decimal_amount_does_not_become_a_url():
    assert parse_intent("pay $5.50 for coffee").target_url is None


@pytest.mark.parametrize(
    "words, value",
    [("five", 5), ("twenty five", 25), ("twenty-five", 25), ("one hundred and five", 105), ("two thousand", 2000)],
)
def test_words_to_int(words, value):
    assert words_to_int(words) == value


@pytest.mark.parametrize("command", ["/pay $5 to api.example.com", "$5 to api.example.com", "pay $5 api.example.com"])
def test_pay_command_forms(command):
    intent = parse_pay_command(command)
    assert intent.amount == Decimal(5)
    assert intent.target_url == "https://api.example.com"
