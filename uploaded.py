#!/usr/bin/env python3
import argparse
import asyncio
import requests
import os
import sys
import re
import time
import signal
import configparser
import subprocess
import tempfile

home = os.getenv('HOME')

config = configparser.ConfigParser()

config.read(os.path.join(home, '.uploaded.py.conf'))

try:
    login_data = {
        'id': config['UPLOADED']['id'],
        'pw': config['UPLOADED']['pw'],
    }
except KeyError:
    login_data = None

try:
    download_dir = config['UPLOADED']['dir']
except KeyError:
    download_dir = os.path.join(home, 'Downloads')

colors = {
    'resume':  '\033[93m',
    'working': '\033[94m',
    'error':   '\033[91m',
    'done':    '\033[92m',
    'new':     '\033[93m',
    'end':     '\033[0m',
}

progress = {}
chunk_size = 4096
running = 0
workers = 1

signal.signal(signal.SIGINT, lambda *_: sys.exit(0))  # die with style... not 100% working yet.. investigate

session = requests.Session()
url_pattern = r'https?://(uploaded\.net/file|ul\.to)/.+'

downloads = []


def current_millis():
    return int(round(time.time() * 1000))


def human_readable_size(num, suffix='B'):
    for unit in ('', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi'):
        if abs(num) < 1024.0:
            return '{:3.1f}{}{}'.format(num, unit, suffix)
        num /= 1024.0
    return '{.1f}{}{}'.format(num, 'Yi', suffix)


def login():
    """start a session and login using the login credentials"""
    r = session.post('https://uploaded.net/io/login', data=login_data, headers={'Referer': 'https://uploaded.net/'})
    if r.text != '{loc:"me"}':
        exit('Invalid login')


def resolve_dlc(dlc):
    """resolve all urls for a dlc container"""
    r = requests.post('http://dcrypt.it/decrypt/paste', data={'content': dlc})
    json = r.json()
    if 'success' not in json:
        exit('error resolving DLC')
    return [link for link in r.json()['success']['links'] if re.match(url_pattern, link)]


def resolve_link(in_url):
    """get the real download url for the public link"""
    return in_url  # FIXME not needed anymore, allow_redirects fixed it
    time.sleep(0.1)
    r = session.get(in_url, allow_redirects=True)
    try:
        out_url = re.findall('<form method="post" action="(.+?)"', r.text)[0]
        print('{} -> {}'.format(in_url, out_url))

    except IndexError:
        exit('error resolving link: {}'.format(in_url))
    return out_url


def resolve_file_info(url):
    """get the file name and content length for the download"""
    r = session.head(url, allow_redirects=True)
    # print(r.headers)
    file_name = re.findall('filename="([^"]+)"', r.headers['content-disposition'])[0]
    file_length_total = int(r.headers['content-length'])
    return file_name, file_length_total


def resolve_uploaded_folder(url):
    print('resolving uploaded folder url {}'.format(url))
    r = session.get(url, allow_redirects=True)
    urls = re.findall('href="(file/[^""]+)"', r.text)
    return ['https://uploaded.net/{}'.format(url) for url in urls]


def resolve_linkcrypt(url):
    print('resolving linkcrypt url {}'.format(url))
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(bytes('''
            var page = require('webpage').create();
                page.open('{}', function () {{
                console.log(page.content);
                phantom.exit();
            }});
        '''.format(url), 'UTF-8'))

    result = subprocess.check_output(['phantomjs', f.name])
    os.unlink(f.name)
    matches = re.search('<a href="(http://linkcrypt.ws/container/[^"]+)" target="_blank" alt="Click">', result.decode())
    if matches:
        dlc_url = matches.groups()[0]
        r = requests.get(dlc_url, allow_redirects=True)
        return resolve_dlc(r.text)


@asyncio.coroutine
def read_source(download):
    try:
        yield from _read_source(download)
    except:
        sys.exit(0)


@asyncio.coroutine
def _read_source(download):
    """download a single download"""
    global running
    running += 1

    r = session.post(download['real_url'], headers=download['headers'], stream=True)
    download['status'] = 'working'

    # yield chunks of data
    with open(download['file_path'], download['file_mode']) as fp:
        for chunk in r.iter_content(chunk_size):
            fp.write(chunk)
            download['progress'] += len(chunk)
            yield

    if download['progress'] == download['file_length_total']:
        download['status'] = 'done'
    else:
        download['status'] = 'error'  # resume?

    running -= 1

    # start a new download worker
    if running < workers and len(downloads) > 0:
        queue_next_download()


@asyncio.coroutine
def print_progress():
    """clear the screen and print out the progress for every download"""

    last_millis = current_millis()
    last_total_progress = 0

    while True:
        all_done = True
        os.system('clear')

        downloads_print = []
        total_length = 0
        total_progress = 0
        for download in downloads:
            total_length += download['file_length_total']
            total_progress += download['progress']

            percent = download['progress'] / download['file_length_total']

            percent_str = '{:.2%}'.format(percent)
            downloads_print.append('{color}{percent:>7} of {size:>9} {file_name} {end}'.format(
                percent=percent_str,
                file_name=download['file_name'],
                color=colors[download['status']],
                size=human_readable_size(download['file_length_total']),
                end=colors['end']
            ))

            if download['status'] == 'working':
                all_done = False  # at least one download is not finished

        now_millis = current_millis()
        diff_millis = now_millis - last_millis
        diff_progress = total_progress - last_total_progress
        last_millis = now_millis
        last_total_progress = total_progress

        rate = 1000 * diff_progress / diff_millis

        rate = human_readable_size(rate)

        total_percent = total_progress / total_length
        print('Downloading {num_downloads} files to {download_dir} ({num_workers} workers) progress: {percent} of {size} ({rate}/s)'.format(
            num_downloads=len(downloads),
            download_dir=download_dir,
            num_workers=workers,
            percent='{:.2%}'.format(total_percent),
            size=human_readable_size(total_length),
            rate=rate
        ))
        print('\n'.join(downloads_print))

        if all_done is True:
            print('all done')
            exit()

        yield from asyncio.sleep(1)


def queue_next_download():
    """queue the next download"""
    try:
        while True:  # skip finished downloads
            download = next(downloads_gen)

            if download['status'] in ('new', 'resume'):
                asyncio.async(read_source(download))

                return

    except StopIteration:  # no more downloads left
        pass


def add_download(url, dlc=None):
    """add a public uploaded url to the list of downloads
    resolve the real url, file size...
    """

    real_url = resolve_link(url)
    print(real_url)
    file_name, file_length_total = resolve_file_info(real_url)
    file_path = os.path.join(download_dir, file_name)

    headers = {
        'User-agent': 'Mozilla/5.0',
    }

    try:
        # resume
        downloaded_size = os.path.getsize(file_path)

        status = 'resume'

        # file is already complete
        if downloaded_size >= file_length_total:
            status = 'done'

        headers['Range'] = 'bytes={}-'.format(downloaded_size)
        file_mode = 'ab'

    except FileNotFoundError:
        # start a new download

        status = 'new'
        downloaded_size = 0
        file_mode = 'wb'

    downloads.append({
        'url':               url,
        'dlc':               dlc,
        'real_url':          real_url,
        'progress':          downloaded_size,
        'file_name':         file_name,
        'file_length_total': file_length_total,
        'file_path':         file_path,
        'headers':           headers,
        'downloaded_size':   downloaded_size,
        'file_mode':         file_mode,
        'status':            status,
    })

if __name__ == "__main__":

    # create the file .uploaded.py.conf in your home dir:
    '''
        [UPLOADED]
        id = XXXXXXX
        pw = XXXXXX
        dir = /home/XXXXX/Downloads
    '''

    parser = argparse.ArgumentParser(description='uploaded')
    parser.add_argument('--workers', '-w', help='number of simultaneus downloads', type=int, default=3)
    parser.add_argument('urls', nargs='+', help='list of urls or .dlc files to download (can be mixed). eg:  http://uploaded.net/file/abcdefgh foo.dlc')
    parser.add_argument('--id', help='login id')
    parser.add_argument('--pw', help='login password')
    parser.add_argument('--download_dir', '-d', help='download directory')

    args = parser.parse_args()

    if args.id and args.pw:
        login_data = {
            'id': args.id,
            'pw': args.pw,
        }

    if not login_data:
        exit('error: please provide valid login credentials!')

    if args.download_dir:
        download_dir = args.download_dir

    os.system('clear')
    print('resolving urls...')

    workers = args.workers
    urls = args.urls

    login()

    for url in urls:
        if url.endswith('.dlc'):
            dlc = url
            for url in resolve_dlc(open(dlc).read()):
                add_download(url, dlc=dlc)
        elif re.match('https://uploaded.net/f/\w+', url):
            for url in resolve_uploaded_folder(url):
                add_download(url)
        elif re.match('http://linkcrypt.ws/\w+', url):
            for url in resolve_linkcrypt(url):
                add_download(url)
        else:
            if not re.match(url_pattern, url):
                exit('invalid filename {}'.format(url))
            add_download(url)

    downloads.sort(key=lambda download: download['file_name'])
    downloads_gen = (download for download in downloads)

    # start the first n workers
    for i in range(workers):
        queue_next_download()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(print_progress())
