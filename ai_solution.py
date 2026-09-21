```python
def task_accepted(self, task, calendar_id):
    if not task or task.id == 0:
        self._set_reminder(calendar_id, task)
    elif task.repeat:
        self._set_reminder(calendar_id, task)
    return task
```