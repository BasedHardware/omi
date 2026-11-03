"""Per-kind schema semantics selected by the capability registry."""


def payload(item):
    return item.model_dump(exclude={'value', 'why_it_matters', 'effective_from'})


def edit(item):
    from models.dream_edit import Edit

    Edit.model_validate(payload(item))


def hygiene(item):
    from models.dream_edit import MemoryHygieneEdit

    item.after = item.after.strip()
    MemoryHygieneEdit.model_validate(item.model_dump(exclude={'value', 'why_it_matters'}))


def merge(item):
    if not item.other or item.other == item.target or item.after:
        raise ValueError('A merge needs a distinct other ref and preserves its text')


def memory_merge(item):
    if not item.other or item.other == item.target or not item.after.strip() or len(item.after) > 2000:
        raise ValueError('A memory merge requires a distinct other ref and combined fact text')
    edit(item)


def retire(item):
    if item.other or item.after:
        raise ValueError('Dismissal and retirement change status only')


def required_intake(item):
    if item.after or not item.before.strip() or '#' in item.target or '#' in item.other:
        raise ValueError('Required intake preserves the submission; other optionally names its existing duplicate')
    if item.other and item.other == item.target:
        raise ValueError('Required intake needs a distinct survivor')


def language(item):
    if item.other or not item.after.strip() or len(item.after) > 32:
        raise ValueError('Language requires a bounded tag, not a second record')


def term(item):
    from models.dream_edit import Term

    Term.model_validate(item.model_dump())
