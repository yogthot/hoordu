#!/usr/bin/env python3
import asyncio
import sys
import traceback
from getpass import getpass

from sqlalchemy.orm import selectinload

import hoordu
from hoordu.models import *
from hoordu.plugins import FetchDirection
from hoordu.forms import *
from hoordu.oauth.server import OAuthServer

from sqlalchemy.exc import IntegrityError

def fail(error):
    print(f'error: {error}', file=sys.stderr)
    sys.exit(1)

def usage():
    print(f'python {sys.argv[0]} <command> [command arguments]')
    print(f'python {sys.argv[0]} <url> [<url>...]')
    print("")
    print("global arguments:")
    print("    -p <plugin id>, --plugin <plugin id>")
    print("        selects a plugin (this affects subsequent arguments)")
    print("")
    print("    -s <source>, --source <source>")
    print("        selects a source (this affects subsequent arguments)")
    print("")
    print("    -d, --disabled")
    print("        list: lists disabled subscriptions instead")
    print("")
    print("available commands:")
    print("    createdb")
    print("        creates all the relations in the database if they haven't been created yet")
    print("")
    print("    setup")
    print("        sets up a plugin (requires --plugin)")
    print("")
    print("    list")
    print("        lists all enabled subscriptions for a source (requires --source)")
    print("")
    print("    update [[<source>:]<subscription name>]")
    print("        gets all new posts for a subscription")
    print("        ':' won't be used as a separator if a source is specified")
    print("")
    print("        gets all new posts for all subscriptions if")
    print("        no subscription is specified (requires --plugin or --source)")
    print("")
    print("    fetch [<source>:]<subscription name> <n>")
    print("        gets 'n' older posts for a subscription")
    print("")
    print("    rfetch [<source>:]<subscription name> <n>")
    print("        gets 'n' newer posts from a subscription")
    print("")
    print("    related <url> <related url> [<related url>...]")
    print("        downloads 'url' and all 'related url's")
    print("")
    print("alternative usage:")
    print("    when passed a list of urls, this command will attempt to download")
    print("    all of them, unless one of them corresponds to a list of posts")

def parse_sub_name(arg, args):
    if args.source is None and ':' in arg:
        args.source, args.subscription = arg.split(':')
        
    else:
        args.subscription = arg

async def parse_url(hrd, arg, args):
    if args.local:
        return None, int(arg)
    
    plugins = await hrd.parse_url(arg)
    if len(plugins) == 0:
        fail(f'unable to download url: {arg}')
    
    # this process should be manual
    if args.plugin_id is not None:
        plugin, options = next(((p, o) for p, o in plugins if p.id == args.plugin_id), (None, None))
        if plugin is None:
            fail(f'plugin \'{args.plugin_id}\' can\'t to download url: {arg}')
        
        return plugin, options
    
    source = args.source
    if args.plugin_id is None and args.source is None:
        sources = {plugins[0][0].name}
        for p, _ in plugins:
            if p.name not in sources:
                fail(f'multiple sources can download: {arg}')
        
        source = sources.pop()
    
    plugins = [(p, o) for p, o in plugins if p.name == source]
    if len(plugins) == 0:
        fail(f'no plugin for source \'{args.source}\' can download url: {arg}')
    
    async with hrd.session() as session:
        source_db = await session.select(Source) \
                .options(selectinload(Source.preferred_plugin)) \
                .where(Source.name == source) \
                .one()
        preferred_plugin = source_db.preferred_plugin
    
    plugin, options = next(((p, o) for p, o in plugins if p.id == preferred_plugin.name), (None, None))
    if plugin is None:
        fail(f'preferred plugin for \'{source}\' can\'t download url: {arg}')
    
    return plugin, options

async def parse_args(hrd):
    # parse arguments
    args = hoordu.Dynamic()
    args.source = None
    args.plugin_id = None
    args.command = None
    args.urls = []
    args.subscription = None
    args.num_posts = None
    args.disabled = False
    args.local = False
    
    argi = 1
    sargi = 0 # sub argument count
    argc = len(sys.argv)
    while argi < argc:
        arg = sys.argv[argi]
        argi += 1
        
        # global commands
        if arg == '-h' or arg == '--help':
            usage()
            sys.exit(0)
        
        elif arg == '-p' or arg == '--plugin':
            args.plugin_id = sys.argv[argi]
            argi += 1
            
        elif arg == '-s' or arg == '--source':
            args.source = sys.argv[argi]
            argi += 1
            
        elif arg == '-d' or arg == '--disabled':
            args.disabled = True
            
        elif arg == '-l' or arg == '--local':
            args.local = True
            
        elif args.command is None:
            # pick command, or append to list or urls
            if arg in ('createdb', 'setup', 'list', 'enable', 'disable', 'update', 'fetch', 'rfetch', 'related', 'info', 'files'):
                args.command = arg
                sargi = 0
                
            else:
                args.urls.append(await parse_url(hrd, arg, args))
            
        else:
            # sub-command arguments
            if args.command in ('enable', 'disable', 'update') and sargi < 1:
                parse_sub_name(arg, args)
                sargi += 1
                
            elif args.command in ('fetch', 'rfetch') and sargi < 2:
                if sargi == 0:
                    parse_sub_name(arg, args)
                    
                else:
                    args.num_posts = int(arg)
                
                sargi += 1
                
            elif args.command in ('related', 'info', 'files'):
                args.urls.append(await parse_url(hrd, arg, args))
                sargi += 1
                
            else:
                fail(f'unknown argument: {arg}')
    
    # verify arguments
    urlc = len(args.urls)
    if urlc >= 2:
        for id, options in args.urls:
            if isinstance(options, hoordu.Dynamic):
                fail('can only process one search url at a time')
    
    if args.command == 'related' and urlc <= 1:
        fail('the related sub-command requires at least 2 urls')
    
    if args.command in ('list',) and args.source is None:
        fail(f'{args.command} sub-command requires a source to be specified')
    
    if args.command in ('setup',) and args.plugin_id is None:
        fail(f'{args.command} sub-command requires a plugin to be specified')
    
    if args.command in ('enable', 'disable', 'fetch', 'rfetch') and args.subscription is None:
        fail(f'{args.command} sub-command requires a subscription to be specified')
    
    if args.command == 'update' and args.subscription is None and args.plugin_id is None and args.source is None:
        fail(f'update sub-command requires a plugin, a source or a subscription to be specified')
    
    return args

# plugin setup
async def _cli_form(form):
    form.clear()
    
    print(f'== {form.label} ===========')
    if isinstance(form, OAuthForm):
        print('Please visit the following url and authorize to continue.')
        print(form.url)
        oauth_server = OAuthServer(8941)
        path, params = await oauth_server.wait_for_request()
        
        plugin_id = path[1:]
        form.fill(params)
        return
    
    for entry in form.entries:
        if isinstance(entry, Section):
            print(f'-- {entry.label} ----------')
            print()
            await _cli_form(entry)
            print('--------------' + '-' * len(entry.label))
        
        else:
            if entry.errors:
                for error in entry.errors:
                    print(f'error: {error}')
                
            if isinstance(entry, Label):
                print(entry.label)
                print()
                
            elif isinstance(entry, PasswordInput):
                value = getpass('{entry.label}: ')
                if value: entry.value = value
                
            elif isinstance(entry, ChoiceInput):
                print(f'{entry.label}:')
                for k, v in entry.choices:
                    print(f'    {k}: {v}')
                value = input('pick a choice: ')
                if value: entry.value = value
                
            elif isinstance(entry, Input):
                value = input(f'{entry.label}: ')
                if value: entry.value = value
                
            else:
                print()

async def cli_form(form):
    await _cli_form(form)
    while not form.validate():
        await _cli_form(form)

# this should be the general approach to setting up a plugin
async def setup_plugin(hrd, id):
    form = None
    
    while True:
        parameters = None
        if form is not None:
            parameters = form.value
        
        # attempt to init
        success, form = await hrd.setup_plugin(id, parameters=parameters)
        
        if success:
            return True
        
        elif form is not None:
            # if not successful but something else was returned
            # then attempt to ask the user for input
            
            await cli_form(form)
        
        else:
            fail('something went wrong with the plugin setup')


async def safe_fetch(session, iterator):
    posts = {}
    while True:
        try:
            async for remote_post in iterator:
                posts[remote_post.id] = remote_post
            
            return posts
            
        except Exception:
            traceback.print_exc()
            if iterator.subscription is not None:
                subscription = iterator.subscription
                name = subscription.name
                print(f'subscription "{name}" ran into an error')
                print('y = retry; d = rollback, ignore and disable subscription; n = just rollback and ignore')
                v = input('do you want to retry? (Ynd) ').lower()
                if not v: v = 'y'
                if v == 'y':
                    # make sure we retry from a valid db state
                    await session.flush()
                    continue
                    
                elif v == 'd':
                    await session.rollback()
                    
                    await session.refresh(subscription)
                    subscription.enabled = False
                    session.add(subscription)
                    await session.commit()
                    return
                    
                else:
                    await session.rollback()
                    return

async def process_sub(session, plugin_id, options):
    plugin = await session.plugin(plugin_id)
    
    details = await plugin.get_search_details(options)
    
    if details is not None:
        description = details.description or ''
        description = description.replace('\n', '\n    ')
        related = '\n    '.join(details.related_urls)
        
        print(f"""
hint: {details.hint}
title: {details.title}
description:
    {description}
related:
    {related}
        """.strip())
        
        sub_name = details.hint
        
    else:
        sub_name = input('pick a name for the subscription: ')
        if not sub_name:
            sys.exit(0)
    
    try:
        return await plugin.subscribe(sub_name, options=options)
        
    except IntegrityError:
        await session.rollback()
        
        is_name_conflict = await session.select(Subscription) \
                .where(Subscription.name == sub_name) \
                .exists().select() \
                .one_or_none()
        
        print()
        if is_name_conflict:
            fail('a subscription with the same name already exists')
            
        else:
            fail(f'this subscription already exists')

async def main():
    argc = len(sys.argv)
    if argc == 1:
        usage()
        sys.exit(1)
    
    config = hoordu.load_config()
    
    if sys.argv[1] == 'createdb':
        await hoordu.hoordu.create_all(config)
        return
    
    hrd = hoordu.hoordu(config)
    
    args = await parse_args(hrd)
    
    async with hrd.session() as session:
        if args.command is None:
            if len(args.urls) == 1 and isinstance(args.urls[0][1], hoordu.Dynamic):
                plugin_id, options = args.urls[0]
                await process_sub(session, plugin_id, options)
            
            else:
                for plugin_id, post_id in args.urls:
                    plugin = await session.plugin(plugin_id)
                    await plugin.download(post_id)
                    await session.commit()
        
        
        elif args.command == 'setup':
            await setup_plugin(hrd, args.plugin_id)
            
            
        elif args.command == 'list':
            subs = await session.select(Subscription) \
                    .join(Source) \
                    .where(Source.name == args.source) \
                    .all()
            
            for sub in subs:
                if sub.enabled ^ args.disabled:
                    print(f'\'{sub.name}\': {(sub.repr)}')
            
            
        elif args.command in ('enable', 'disable'):
            if args.source is not None:
                sub = await session.select(Subscription) \
                        .join(Source) \
                        .where(
                            Source.name == args.source,
                            Subscription.name == args.subscription
                        ).one()
                
            else:
                sub = await session.select(Subscription) \
                        .where(
                            Subscription.name == args.subscription
                        ).one()
            
            sub.enabled = (args.command == 'enable')
            session.add(sub)
            
            
        elif args.command == 'update' and args.subscription is None:
            if args.plugin_id is not None:
                # filter by plugin
                subs = await session.select(Subscription) \
                        .join(Plugin) \
                        .where(Plugin.name == args.plugin_id) \
                        .all()
                
            else:
                # filter by source
                subs = await session.select(Subscription) \
                        .join(Source) \
                        .where(Source.name == args.source) \
                        .all()
            
            for sub in subs:
                if sub.enabled:
                    print(f'getting all new posts for subscription \'{sub.name}\'')
                    plugin = await session.plugin((await sub.fetch('plugin')).name)
                    it = await plugin.create_iterator(sub, direction=FetchDirection.newer, num_posts=None)
                    await safe_fetch(session, it)
                    await session.commit()
            
        elif args.command in ('update', 'fetch', 'rfetch'):
            if args.plugin_id is not None:
                # filter by plugin
                sub = await session.select(Subscription) \
                        .join(Plugin) \
                        .where(
                            Plugin.name == args.plugin_id,
                            Subscription.name == args.subscription
                        ) \
                        .one_or_none()
                
            else:
                # filter by source
                sub = await session.select(Subscription) \
                        .join(Source) \
                        .where(
                            Source.name == args.source,
                            Subscription.name == args.subscription
                        ) \
                        .one_or_none()
            
            if sub is None:
                fail(f'subscription \'{args.subscription}\' doesn\'t exist')
            
            direction = FetchDirection.older if args.command == 'fetch' else FetchDirection.newer
            
            plugin = await session.plugin((await sub.fetch('plugin')).name)
            it = await plugin.create_iterator(sub, direction=direction, num_posts=args.num_posts)
            await safe_fetch(session, it)
            
            if sub.plugin_id != plugin.plugin.id:
                # set the preferred plugin to last used plugin
                sub.plugin_id = plugin.plugin.id
                session.add(sub)
                await session.commit()
            
        elif args.command == 'related':
            plugin_id, post_id = args.urls[0]
            plugin = await session.plugin(plugin_id)
            post = await plugin.download(post_id)
            await session.commit()
            
            for plugin_id, post_id in args.urls[1:]:
                plugin = await session.plugin(plugin_id)
                related_post = await plugin.download(post_id)
                session.add(Related(related_to=post, remote=related_post))
                await session.commit()
            
        elif args.command in ('info', 'files'):
            if not args.local:
                plugin, id = args.urls[0]
                
                if not isinstance(id, str):
                    fail('failed to parse post url')
                
                post = await session.select(RemotePost) \
                        .options(selectinload(RemotePost.files)) \
                        .where(RemotePost.original_id == id) \
                        .one_or_none()
                
            else:
                plugin, id = args.urls[0]
                
                post = await session.select(RemotePost) \
                        .options(selectinload(RemotePost.files)) \
                        .where(RemotePost.id == id) \
                        .one_or_none()
            
            if post is None:
                fail('post does not exist')
            
            if args.command == 'info':
                if plugin:
                    print(f'plugin: {plugin.name}')
                print(f'local id: {post.id}')
                print(f'original id: {post.original_id}')
                
                for rel in await post.fetch(RemotePost.related):
                    print(f'  related: {rel.remote_id}')
            
            for f in post.files:
                orig, thumb = hrd.get_file_paths(f)
                print(orig)


asyncio.run(main())
