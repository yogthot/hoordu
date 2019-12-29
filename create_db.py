#!/usr/bin/env python3
import hoordu

if __name__ == '__main__':
    conf = hoordu.load_config('config.conf')
    conf.debug = True
    hrd = hoordu.hoordu(conf)
    hrd.create_all()

