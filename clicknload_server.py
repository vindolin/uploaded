#!/usr/bin/env python
from flask import Flask, request
from urllib import unquote
from base64 import standard_b64decode
from binascii import unhexlify
from Crypto.Cipher import AES
from urllib import quote
import subprocess

url_filter_str = 'uploaded'

app = Flask(__name__)


def eval_js(script):
    return subprocess.check_output(
        ['js', '-e', '''console.log(eval(unescape('{}')))'''.format(quote(script))]
    ).strip()


@app.route('/jdcheck.js')
def jdcheck():
    return "jdownloader=true;\nvar version='10629';\n"


@app.route('/flash/addcrypted2', methods=['POST'])
def addcrypted2():
    crypted = request.form['crypted']
    jk = request.form['jk']

    crypted = standard_b64decode(
        unquote(
            crypted.replace(" ", "+")
        )
    )
    jk = '{} f()'.format(jk)
    jk = eval_js(jk)
    Key = unhexlify(jk)
    IV = Key

    obj = AES.new(Key, AES.MODE_CBC, IV)
    result = obj.decrypt(crypted).replace('\x00', '').replace('\r', '').split('\n')

    print ' '.join([url for url in result if url != '' and url_filter_str in url])

    return 'success'


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=9666)
