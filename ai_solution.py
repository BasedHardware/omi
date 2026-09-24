```python
def parse_form_json(data):
    from backend.models import FormSchema
    try:
        return_val = FormSchema(**data)
        return return_val.dict()
    except Exception as e:
        if isinstance(e, RequestValidationException):
            return f"Invalid {e.field_name}: {e.message}"
        else:
            return f"Malformed JSON: {str(e)}"
    return data

def retrieve_file_paths(files, filename):
    try:
        paths = [str(f) for f in files]
        return {"paths": paths}
    except Exception as e:
        return f"Failed to write file {filename}"
```

```python
def parse_form_json(data):
    from backend.models import FormSchema
    try:
        return_val = FormSchema(**data)
        return return_val.dict()
    except Exception as e:
        if isinstance(e, RequestValidationException):
            return f"Invalid {e.field_name}: {e.message}"
        else:
            return f"Malformed JSON: {str(e)}"
    return data

def retrieve_file_paths(files, filename):
    try:
        paths = [str(f) for f in files]
        return {"paths": paths}
    except Exception as e:
        return f"Failed to write file {filename}"
```