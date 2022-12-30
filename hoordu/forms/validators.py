from typing import Protocol, Optional


class ValidationError(ValueError):
    pass

class StopValidation(Exception):
    pass


class Validator(Protocol):
    def __call__(self, entry: 'FormEntry') -> None:
        ...

class required(Validator):
    def __init__(self, message: Optional[str] = None):
        self.message: str
        if message is None:
            self.message = 'this field is required'
        else:
            self.message = message
    
    def __call__(self, field: 'FormEntry'):
        if field.value is None or (isinstance(field.value, str) and not field.value.strip()):
            raise StopValidation(self.message)
