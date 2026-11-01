"""Registry-selected display transforms, independent of the agent caller."""

from models.agent_refs import base_ref


def default(edit, records):
    from utils.agent_capabilities.change_view import label

    return (
        edit.before or label(records[base_ref(edit.target)]),
        edit.after or (label(records[base_ref(edit.other)]) if edit.other else ''),
        [],
    )


def merge_memory(edit, records):
    from utils.agent_capabilities.change_view import label

    _before, after, refs = default(edit, records)
    return label(records[base_ref(edit.target)]) + ' + ' + label(records[base_ref(edit.other)]), after, refs


def merge_people(edit, records):
    from utils.agent_capabilities.change_view import label
    from models.review import ChangeRef

    left = label(records[base_ref(edit.target)])
    return (
        left + ' + ' + label(records[base_ref(edit.other)]),
        left,
        [
            ChangeRef(type='person', id=base_ref(ref).split('/', 1)[1], label=label(records[base_ref(ref)]))
            for ref in (edit.target, edit.other)
        ],
    )
