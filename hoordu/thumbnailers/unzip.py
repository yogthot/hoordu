from .common import async_exec

__all__ = [
    'Unzip'
]

class Unzip:
    def __init__(self, archive: str):
        self.archive = archive
    
    async def list(self):
        stdout = await async_exec(
            '7z', 'l',
            '-slt',
            '-ba',
            '-p',
            self.archive
        )
        
        sections = stdout.strip().split(b'\n\n')
        files = []
        for s in sections:
            parts = s.split(b'\n')
            
            details = {}
            for p in parts:
                k, v = p.split(b'=')
                details[k.decode().strip().lower().replace(' ', '_')] = v.strip()
            
            files.append(details)
        
        return files
    
    async def extract(self, file, dst):
        stdout = await async_exec(
            '7z', 'x',
            #f'-i@{file}',
            '-p', #  to guarantee it doesn't block
            f'-so',
            '--',
            self.archive,
            file,
            
            out=dst
        )
