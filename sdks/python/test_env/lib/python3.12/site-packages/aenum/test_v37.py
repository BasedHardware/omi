from . import Enum
from dataclasses import dataclass
from unittest import TestCase


class TestEnumV37(TestCase):

        def test_repr_with_dataclass(self):
            "ensure dataclass-mixin has correct repr()"
            #
            # check overridden dataclass __repr__ is used
            #
            from dataclasses import dataclass, field
            @dataclass(repr=False)
            class Foo:
                __qualname__ = 'Foo'
                a: int
                def __repr__(self):
                    return 'ha hah!'
            class Entries(Foo, Enum):
                ENTRY1 = 1
            self.assertEqual(repr(Entries.ENTRY1), '<Entries.ENTRY1: ha hah!>')
            self.assertEqual(Entries.ENTRY1.value, Foo(1))
            self.assertTrue(isinstance(Entries.ENTRY1, Foo))
            self.assertTrue(Entries._member_type_ is Foo, Entries._member_type_)
            #
            # check auto-generated dataclass __repr__ is not used
            #
            @dataclass
            class CreatureDataMixin:
                __qualname__ = 'CreatureDataMixin'
                size: str
                legs: int
                tail: bool = field(repr=False, default=True)
            class Creature(CreatureDataMixin, Enum):
                __qualname__ = 'Creature'
                BEETLE = ('small', 6)
                DOG = ('medium', 4)
            self.assertEqual(repr(Creature.DOG), "<Creature.DOG: size='medium', legs=4>")
            #
            # check inherited repr used
            #
            class Huh:
                def __repr__(self):
                    return 'inherited'
            @dataclass(repr=False)
            class CreatureDataMixin(Huh):
                __qualname__ = 'CreatureDataMixin'
                size: str
                legs: int
                tail: bool = field(repr=False, default=True)
            class Creature(CreatureDataMixin, Enum):
                __qualname__ = 'Creature'
                BEETLE = ('small', 6)
                DOG = ('medium', 4)
            self.assertEqual(repr(Creature.DOG), "<Creature.DOG: inherited>")
            #
            # check default object.__repr__ used if nothing provided
            #
            @dataclass(repr=False)
            class CreatureDataMixin:
                __qualname__ = 'CreatureDataMixin'
                size: str
                legs: int
                tail: bool = field(repr=False, default=True)
            class Creature(CreatureDataMixin, Enum):
                __qualname__ = 'Creature'
                BEETLE = ('small', 6)
                DOG = ('medium', 4)
            self.assertRegex(repr(Creature.DOG), "<Creature.DOG: .*CreatureDataMixin object at .*>")


if __name__ == '__main__':
    raise RuntimeError("'test_v3.py' should not be run by itself; it's included in 'test.py'")

