import re
from urllib.parse import unquote

re_filename = re.compile('filename= *([^;]+)', re.IGNORECASE)
re_simple = re.compile('filename= *(.*)', re.IGNORECASE)
re_ext = re.compile('filename\*= *UTF-8\'[^\']*\'(.*)', re.IGNORECASE)

def _sanitize(path):
    if path in ('.', '..'):
        return None
    
    return path.replace('/', '_')

def _parse_filename(value):
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    
    value = unquote(value)
    
    return _sanitize(value)

def filename(header):
    parts = [x.strip() for x in header.split(';')]
    simple_filenames = None
    disp_type = None
    
    disposition_type = parts[0]
    parts = parts[1:]
    
    for parm in parts:
        match_simple = re_simple.match(parm)
        if match_simple:
            name = _parse_filename(match_simple.group(1))
            
            if name:
                simple_filenames = name
            
            # keep trying for an utf-8 filename
            continue
        
        match_ext = re_ext.match(parm)
        if match_ext:
            name = _parse_filename(match_ext.group(1))
            if name:
                # return immediately on utf-8 filename
                return name
    
    return simple_filenames

def safe_filename(header):
    try:
        return filename(header)
        
    except Exception:
        try:
            return _parse_filename(re_filename.search(header).group(1))
        
        except Exception:
            return None
