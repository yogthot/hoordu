import logging
from string import Template

__all__ = [
    'configure_logger'
]

class LoggingParentFilter:
    def filter(self, record):
        if record.name.startswith('hoordu.'):
            record.name = record.name.split('.', 1)[-1]
        
        return True

class ParentHandler(logging.Handler):
    terminator = '\n'
    
    def __init__(self, format):
        super().__init__()
        
        self._template = Template(format)
        self._open = dict()
    
    def close(self):
        self.acquire()
        try:
            for file in self._open.values():
                file.flush()
                file.close()
        
        finally:
            self.release()
    
    def emit(self, record):
        name = record.name
        msg = self.format(record)
        
        self.acquire()
        try:
            file = self._open.get(name)
            if file is None:
                path = self._template.substitute(name=name)
                file = open(path, 'a')
                self._open[name] = file
            
            file.write(msg + self.terminator)
            file.flush()
            
        finally:
            self.release()

logger = None
def configure_logger(basename, filename_format, level=logging.INFO):
    global logger
    
    if logger is not None:
        return logger
    
    logger = logging.getLogger(basename)
    logger.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter('[%(asctime)s] %(name)s | %(levelname)s | %(message)s', '%Y-%m-%d %H:%M:%S')
    
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)
    console.addFilter(LoggingParentFilter())
    
    logger.addHandler(console)
    
    file = ParentHandler(filename_format)
    file.setLevel(logging.DEBUG)
    file.setFormatter(formatter)
    file.addFilter(LoggingParentFilter())
    
    logger.addHandler(file)
    
    return logger
