Minimalistic download manager for files on uploaded.net (needs premium account).

Supports DLCs.

Needs Python3.

    usage: uploaded.py [-h] [--workers WORKERS] [--id ID] [--pw PW]
                       [--download_dir DOWNLOAD_DIR]
                       urls [urls ...]

    uploaded

    positional arguments:
      urls                  list of urls or .dlc files to download (can be mixed).
                            eg: http://uploaded.net/file/abcdefgh foo.dlc

    optional arguments:
      -h, --help            show this help message and exit
      --workers WORKERS, -w WORKERS
                            number of simultaneus downloads
      --id ID               login id
      --pw PW               login password
      --download_dir DOWNLOAD_DIR, -d DOWNLOAD_DIR
                            download directory
