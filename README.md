# hoordu

hoordu is a database aiming to archive specific online content that also provides a full text search for any imported posts.

Right now only this database integration exists, but I'm planning on making a web UI to manage importing downloaded content as well as a search interface and content readers.

Ideally hoordu should communicate with downloader plugins to get the content from the web, but there's also the possibility of independent scripts using this library to download content directly, so it can later be managed via a user interface.


## TODO

- PostgreSQL full text search
- Thumbnail generation


## Requirements

I recommend using a [PostgreSQL](https://www.postgresql.org/) backend due to the way this is supposed to work, but sqlite should be compatible as well.
It's also up to you to pick the [SQLAlchemy](https://www.sqlalchemy.org/) driver you want to communicate with the database, along with any system dependencies.


## Configuration

The config is simply a python source file with the following fields:

- `debug`: optional (default=False), right now it only makes SQLAlchemy print every query
- `database`: required, the database connection string passed to SQLAlchemy
- `base_path`: required, the base path in which to store the files
- `files_slot_size`: required, the maximum number of files that should be placed in a single folder
- `loglevel`: optional (default=logging.WARNING), the log level for the file logger
- `logto`: optional (default=None), the file to write the logs to

An example can be found in [config.conf](./config.conf).


## File Storage

Every file added to the database will be stored in `<config.base_path>/files/<slot>/<file.id>.<file.ext>` where the `slot` is calculated as `file.id // config.files_slot_size`.

The thumbnails follow the same naming scheme but are stored in `<config.base_path>/thumbs/<slot>/<file.id>.jpg`.


