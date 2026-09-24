"""
Fixed folder database operations: Exclude deleted folder as default target, guard null metadata.
"""

def delete_folder(uid: str, folder_id: str, move_to_folder_id: str = None, folders: list = None):
    # Fix 1: Exclude folder_id when resolving default_folder
    if folders:
        default_folders = [f for f in folders if f.get('is_default') and f.get('id') != folder_id]
        if default_folders:
            return default_folders[0].get('id')
    return move_to_folder_id

def update_folder(uid: str, folder_id: str, form_data: dict):
    # Fix 2: Strip explicit None values for non-nullable Folder fields (name, color, icon, order)
    # while preserving description=None.
    non_nullable_fields = ['name', 'color', 'icon', 'order']
    for field in non_nullable_fields:
        if field in form_data and form_data[field] is None:
            del form_data[field]
    return form_data

def create_folder(uid: str, form_data: dict, max_order = 0):
    # Fix 3: Guard max_order against None/non-integer values
    if max_order is None or not isinstance(max_order, int):
        max_order = 0
    return max_order + 1
