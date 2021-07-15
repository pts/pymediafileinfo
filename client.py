#! /usr/bin/python
#
# client.py: sample client for mediafileinfo.py --pipe in Python 2 and 3
# by pts@fazekas.hu at Thu Jul 15 01:58:20 CEST 2021
#
# Most of the complexity (e.g. lots of .encode(...) calls) below is caused by
# maintaining compatibility with Python 2 and 3.
#

import subprocess, sys

bytes_type = type(''.encode('ascii'))
nlb = '\n'.encode('ascii')
prefixb = 'format='.encode('ascii')
spfb = ' f='.encode('ascii')
p = subprocess.Popen(('./mediafileinfo.py', '--pipe'),
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE)
try:
  # Treat each command-line argument as a filename.
  for filename in sys.argv[1:]:
    filenameb = filename
    if not isinstance(filename, bytes_type):
      filenameb = filename.encode(sys.getfilesystemencoding())
    p.stdin.write(filenameb + nlb)  # Send request.
    p.stdin.flush()
    response = p.stdout.readline()  # Wait for and receive response.
    assert response.endswith(nlb), 'incomplete response'
    assert response.startswith(prefixb), 'response prefix: %r' % response
    suffixb = spfb + filenameb + nlb
    assert response.endswith(suffixb), 'response suffix: %r' % response
    response = response[:-len(suffixb)]
    if not isinstance(response, type('')):
      response = response.decode('ascii')
    h = dict(e.split('=', 1) for e in response.split(' '))  # Parse response.
    h['f'] = filename
    print(repr(h))  # Pretty-print parsed response to an STDOUT line.
    sys.stdout.flush()
finally:
  p.stdin.close()
  exit_code = p.wait()
if exit_code:
  raise RuntimeError('server failed')
