from hashlib import md5 as _md5

__all__ = ['mime_from_file', 'md5']

# handle both python-magic libraries
import magic
if hasattr(magic, 'open'):
    __magic = magic.open(magic.MAGIC_MIME_TYPE)
    __magic.load()
    mime_from_file = __magic.file
else:
    mime_from_file = lambda path: magic.from_file(path, mime=True)
# /

def md5(fname):
    hash = _md5()
    with open(fname, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash.update(chunk)
    return hash.digest()
