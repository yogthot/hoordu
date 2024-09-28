from typing import Optional, Protocol, Any
from collections import OrderedDict

from .validators import Validator, ValidationError, StopValidation

__all__ = [
    'FormEntry',
    'Label',
    'HiddenInput',
    'Input',
    'PasswordInput',
    'ChoiceInput'
]


class FormEntry:
    def __init__(self, identifier: str = None):
        self.id = identifier
    
    def clear(self) -> None:
        pass
    
    def fill(self, value:Any) -> None:
        pass
    
    def validate(self) -> bool:
        return True
    
    @property
    def errors(self) -> list[str]:
        return []


class Label(FormEntry):
    def __init__(self, label: str):
        super().__init__()
        
        self.label = label


class HiddenInput(FormEntry):
    def __init__(self, value: Optional[str] = None):
        super().__init__()
        
        self.initial_value = value
        self.value = value
    
    def clear(self) -> None:
        self.value = self.initial_value
    
    def fill(self, value):
        self.value = value
    
    def validate(self):
        self._errors = []
        if self.value is None:
            self._errors.append('hidden input cannot be empty')
        
        return len(self._errors) == 0
    
    @property
    def errors(self) -> list[str]:
        return self._errors


class Input(FormEntry):
    def __init__(self,
        label: str,
        validators: Optional[list[Validator]] = None,
        identifier: str = None,
        default: Optional[str] = None
    ):
        super().__init__(identifier)

        if validators is None: validators = []
        
        self.label: str = label
        self._value: str | None = None
        self.validators: list[Validator] = validators
        self.default: str | None = default
        
        self._errors: list[str] = []
    
    def clear(self) -> None:
        self._value = None
    
    def fill(self, value: str) -> None:
        self._value = value
    
    def validate(self) -> bool:
        self._errors = []
        
        try:
            for validator in self.validators:
                try:
                    validator(self)
                except ValidationError as err:
                    self._errors.append(str(err))
            
            return len(self._errors) == 0
            
        except StopValidation as err:
            message = str(err)
            if message:
                self._errors.append(message)
            return False
    
    @property
    def value(self) -> str | None:
        if self._value is not None:
            return self._value
        else:
            return self.default
    
    @value.setter
    def value(self, value: str) -> None:
        self._value = value
    
    @property
    def errors(self) -> list[str]:
        return self._errors


class PasswordInput(Input):
    pass


class ChoiceInput(Input):
    def __init__(self,
        label: str,
        choices: list[tuple[str, str]],
        validators:Optional[list[Validator]] = None,
        identifier: Optional[str] = None,
        default: Optional[str] = None
    ):
        if validators is None: validators = []
        validators = [self._validate_choice] + validators

        super().__init__(label, validators, identifier, default)
        
        self.choices = OrderedDict(choices)
        self.value: str | None = default
    
    def _validate_choice(self, field: FormEntry = None) -> None:
        if self.value not in self.choices:
            raise StopValidation('{} is not a valid choice'.format(self.value))


class FileInput(Input):
    def __init__(self,
        label: str,
        validators: Optional[list[Validator]] = None,
        identifier: Optional[str] = None
    ):
        super().__init__(label, validators, identifier)

