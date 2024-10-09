import asyncio
import contextlib

__all__ = [
    'async_exec'
]

async def async_exec(*args, out=None):
    with contextlib.ExitStack() as stack:
        if out is not None:
            proc_out = stack.enter_context(open(out, 'w+'))
            
        else:
            proc_out = asyncio.subprocess.PIPE
        
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=proc_out,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            message = f'Command {args[0]} failed with {proc.returncode}'
            if stderr:
                message += '\n' + stderr.decode()
                
            raise Exception(message)
        
        return stdout

