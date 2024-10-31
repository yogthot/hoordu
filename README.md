# hoordu

hoordu is a database aiming to archive specific online content that also provides a full text search for any imported posts.

Right now only this database integration exists, but I'm planning on making a web UI to manage importing downloaded content as well as a search interface and content readers.

Ideally hoordu should communicate with downloader plugins to get the content from the web, but there's also the possibility of independent scripts using this library to download content directly, so it can later be managed via a user interface.


## TODO

- full text search


## File Storage

Every file added to the database will be stored in `<config.base_path>/files/<slot>/<file.id>.<file.ext>` where the `slot` is calculated as `file.id // config.files_slot_size`.

The thumbnails follow the same naming scheme but are stored in `<config.base_path>/thumbs/<slot>/<file.id>.jpg`.


