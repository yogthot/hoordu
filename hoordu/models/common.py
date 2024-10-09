from enum import Enum

__all__ = [
    'TagCategory',
    'PostType',
]

class TagCategory(Enum):
    general = 1
    group = 2
    artist = 3
    copyright = 4
    character = 5
    # used for informational tags or personal reminders
    meta = 6


class PostType(Enum):
    set = 1 # bundle of unrelated files (or just a single file)
    collection = 2 # the files are related in some way
    blog = 3 # text with files in between (comment is formatted as json)
    # more types can be added as needed

