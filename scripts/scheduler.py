#!/usr/local/share/venv/hoordu/bin/python

import sys
import asyncio
import random
from datetime import datetime, timedelta, timezone
import traceback
import contextlib
import os
import collections

import hoordu
from hoordu.models import *

from sqlalchemy.sql import or_, func
from sqlalchemy.orm import selectinload


#env vars
ERROR_DIRECTORY = os.environ.get('ERROR_DIRECTORY')
USE_SEND_MAIL = os.environ.get('USE_SENDMAIL', '0') != '0'
SENDMAIL_TO = os.environ.get('SENDMAIL_TO')
#


post_delay = 10
sub_delay = 60
retry_limit = 3

email_error_log = []

async def sendmail(to_, subject, body):
    proc = await asyncio.create_subprocess_exec(
        '/usr/bin/sendmail', to_,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    
    mail_lines = [
        f'Subject: {subject}',
        f'Content-Type: text/html; charset=UTF-8',
        f'',
        body.replace('\n', '\r\n'),
    ]
    stdin = '\r\n'.join(mail_lines)
    
    await proc.communicate(stdin.encode())


def printerr(msg):
    print(msg, file=sys.stderr)

async def handle_error(session, plugin, subscription, message, exc):
    plugin_name = plugin.name
    sub_name = subscription.name
    printerr(f'subscription "{sub_name}" ran into an error: {exc}')
    
    # really should escape stuff to avoid XSS
    email_error_log.append(f'<b>{plugin_name} {sub_name}</b>: {message}')
    
    if ERROR_DIRECTORY:
        try:
            fname = f'{ERROR_DIRECTORY}/{plugin_name}-{sub_name}.txt'
            with open(fname, 'w+') as f:
                f.write(exc)
            
        except: pass

async def fetch(session, plugin, subscription):
    iterator = None
    
    attempt = 0
    while True:
        attempt += 1
        try:
            iterator = plugin.update(subscription)
            
            
            async with contextlib.aclosing(iterator):
                async for remote_post in iterator:
                    await asyncio.sleep(post_delay)
            
            # update subscription updated_time
            #await session.refresh(subscription)
            subscription.last_feed_update_time = datetime.now(timezone.utc)
            session.add(subscription)
            await session.commit()
            return
            
        except Exception as e:
            message = ' | '.join(str(x) for x in e.args)
            if 'rate limit' in message.lower() and attempt <= retry_limit:
                await session.flush()
                sleep_time = random.randint(16 * 60, 20 * 60)
                print(f'rate limit reached; will sleep for {sleep_time} seconds')
                print(f'waiting until: {datetime.now() + timedelta(seconds=sleep_time)}')
                await asyncio.sleep(sleep_time)
                continue
            
            exc = traceback.format_exc()
            
            await handle_error(session, plugin, subscription, str(e), exc)
            await session.rollback()
            return

async def main():
    hrd = hoordu.hoordu(hoordu.load_config())
    async with hrd.session() as session:
        subs = await session.select(Subscription) \
                .join(Source) \
                .where(
                    or_(
                        Subscription.last_feed_update_time == None,
                        #Subscription.last_feed_update_time + Subscription.update_interval <= func.now(),
                        #and_(Subscription.update_interval == None, Subscription.last_feed_update_time + Source.update_interval <= func.now())
                        Subscription.last_feed_update_time + Source.update_interval <= func.now()
                    ),
                    Subscription.plugin_id != None
                ) \
                .order_by(Subscription.last_feed_update_time.asc()) \
                .options(
                    selectinload(Subscription.source),
                    selectinload(Subscription.plugin)
                ) \
                .all()
        
        subs = [sub for sub in subs if sub.enabled]
        
        if len(subs) == 0:
            print('nothing to update')
            return
        
        source_counts = collections.Counter(sub.source.name for sub in subs)
        for source, count in source_counts.items():
            print(f'{source} - {count} subscriptions')
        
        total = len(subs)
        for i, sub in enumerate(subs):
            if i > 0:
                await asyncio.sleep(sub_delay)
            
            await session.refresh(sub)
            
            print(f'getting all new posts for subscription \'{sub.name}\' ({i+1}/{total})')
            plugin = await session.plugin(sub.plugin.name)
            await fetch(session, plugin, sub)
            await session.commit()
    
    if USE_SEND_MAIL and len(email_error_log) > 0 and SENDMAIL_TO:
        subject = 'Hoordu update error summary'
        await sendmail(SENDMAIL_TO, subject, '<br>\n'.join(email_error_log))


if __name__ == '__main__':
    asyncio.run(main())


