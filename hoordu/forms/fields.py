from collections import OrderedDict

from .validators import *

__all__ = [
    'Label',
    'Input',
    'PasswordInput',
    'ChoiceInput'
]

class FormEntry:
    def __init__(self, id=None, ):
        self.id = id
    
    def clear(self):
        pass
    
    def fill(self, value):
        pass
    
    def validate(self):
        return True
    
    @property
    def errors(self):
        return []

class Label(FormEntry):
    def __init__(self, label):
        super().__init__()
        
        self.label = label

class Input(FormEntry):
    def __init__(self, label, validators=[], id=None, default=None):
        super().__init__(id)
        
        self.label = label
        self._value = None
        self.validators = validators
        self.default = default
        
        self._errors = []
    
    def clear(self):
        self._value = None
    
    def fill(self, value):
        self._value = value
    
    def pre_validate(self):
        pass
    
    def validate(self):
        self._errors = []
        
        try:
            for validator in self.validators:
                try:
                    validator(self)
                except ValidationError as err:
                    self._errors.append(str(err))
            
            return True
            
        except StopValidation as err:
            message = str(err)
            if message:
                self._errors.append(message)
            return False
    
    @property
    def value(self):
        if self._value is not None:
            return self._value
        else:
            return self.default
    
    @value.setter
    def value(self, value):
        self._value = value
    
    @property
    def errors(self):
        return self._errors

class PasswordInput(Input):
    pass

class ChoiceInput(Input):
    def __init__(self, label, choices, validators=[], id=None, default=None):
        validators = [self._validate_choice] + validators
        super().__init__(id, label, validators, id, default)
        
        self.choices = OrderedDict(choices)
        self.value = default
    
    def _validate_choice(self, field=None):
        if self.value not in self.choices:
            raise StopValidation('{} is not a valid choice'.format(self.value))

