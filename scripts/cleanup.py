#!/usr/bin/env python3

import asyncio
import shutil
import pathlib

import hoordu
from hoordu.models import *
from hoordu.session import HoorduSession

config = hoordu.load_config()
hrd = hoordu.hoordu(config)
basepath = pathlib.Path(config.settings.base_path)

debug = True

def delete_file(path):
    print('rm "{}"'.format(path))
    if not debug:
        try: path.unlink()
        except: pass

def move_file(src, dst):
    print('mv "{}" "{}"'.format(src, dst))
    if not debug:
        dst.parent.mkdir(parents=True, exist_ok=True)
        try: shutil.move(src, dst)
        except: pass

async def check(session: HoorduSession, path, isorig=True):
    for bucket in path.iterdir():
        for file in bucket.iterdir():
            file_id = None
            
            stem = file.stem
            try:
                file_id = int(stem)
            except:
                # not a valid file id
                delete_file(file)
                continue
            
            db_file = await session.select(File).where(File.id == file_id).one_or_none()
            if db_file is None:
                delete_file(file)
                
            else:
                # check if this file is in the right place, if not move it
                orig, thumb = hrd.get_file_paths(db_file)
                actual_path = pathlib.Path(orig if isorig else thumb)
                
                if file != actual_path:
                    move_file(file, actual_path)

def main():
    async with hrd.session() as session:
        check(session, basepath / 'files', True)
        check(session, basepath / 'thumbs', False)


asyncio.run(main())

