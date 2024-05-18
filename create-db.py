#!/usr/bin/env python3
import hoordu
import asyncio

if __name__ == '__main__':
    conf = hoordu.load_config()
    conf.debug = True
    asyncio.run(hoordu.hoordu.create_all(conf))

