import unittest
from pydantic import ValidationError

from models.other import CreatePerson


class TestCreatePersonValidation(unittest.TestCase):
    def test_valid_name(self):
        person = CreatePerson(name="Alice")
        self.assertEqual(person.name, "Alice")

    def test_strips_surrounding_whitespace(self):
        person = CreatePerson(name="  Bob Smith  ")
        self.assertEqual(person.name, "Bob Smith")

    def test_minimum_two_characters(self):
        person = CreatePerson(name="Bo")
        self.assertEqual(person.name, "Bo")

    def test_maximum_forty_characters(self):
        name = "A" * 40
        person = CreatePerson(name=name)
        self.assertEqual(person.name, name)

    def test_rejects_empty_string(self):
        with self.assertRaises(ValidationError):
            CreatePerson(name="")

    def test_rejects_whitespace_only(self):
        for invalid in ["   ", "\t", "\n  \t "]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValidationError):
                    CreatePerson(name=invalid)

    def test_rejects_single_character(self):
        for short in ["A", " A ", "B\t"]:
            with self.subTest(short=short):
                with self.assertRaises(ValidationError):
                    CreatePerson(name=short)

    def test_rejects_over_forty_characters(self):
        with self.assertRaises(ValidationError):
            CreatePerson(name="A" * 41)

    def test_rejects_over_forty_characters_with_padding(self):
        with self.assertRaises(ValidationError):
            CreatePerson(name="  " + ("A" * 41) + "  ")


if __name__ == "__main__":
    unittest.main()
