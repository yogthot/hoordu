
class ValidationError(ValueError):
    pass

class StopValidation(Exception):
    pass

class required:
    def __init__(self, message=None):
        if message is None:
            self.message = 'this field is required'
        else:
            self.message = message
    
    def __call__(self, field):
        if field.value is None or (isinstance(field.value, str) and not field.value.strip()):
            raise StopValidation(self.message)
