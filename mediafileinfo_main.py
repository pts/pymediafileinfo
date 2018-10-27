#! /bin/sh
# by pts@fazekas.hu at Sun Sep 10 00:26:18 CEST 2017

""":" # mediafileinfo.py: Get codecs and dimension of media files.

type python2.7 >/dev/null 2>&1 && exec python2.7 -- "$0" ${1+"$@"}
type python2.6 >/dev/null 2>&1 && exec python2.6 -- "$0" ${1+"$@"}
type python2.5 >/dev/null 2>&1 && exec python2.5 -- "$0" ${1+"$@"}
type python2.4 >/dev/null 2>&1 && exec python2.4 -- "$0" ${1+"$@"}
exec python -- ${1+"$@"}; exit 1

This script need Python 2.4, 2.5, 2.6 or 2.7. Python 3.x won't work.

Typical usage: mediafileinfo.py *.mp4
"""

# Vocabulary:
#
# * analyze: use only in function names, with meaning: get media parameters.
# * extract: don't use, use ``get'' instead.
# * retrieve: don't use, use ``get'' instead.
# * parameters: use as ``media parameters''.
# * size: for width and height, use ``dimensions'' instead.

import mediafileinfo_detect

import struct
import sys


def format_info(info):
  def format_value(v):
    if isinstance(v, bool):
      return int(v)
    if isinstance(v, float):
      if abs(v) < 1e15 and int(v) == v:  # Remove the trailing '.0'.
        return int(v)
      return repr(v)
    if isinstance(v, (int, long)):
      return str(v)
    if isinstance(v, str):
      # Faster than a regexp if there are no matches.
      return (v.replace('%', '%25').replace('\0', '%00').replace('\n', '%0A')
              .replace(' ', '%20'))
    raise TypeError(type(v))
  output = ['format=%s' % format_value(info.get('format') or '?')]
  # TODO(pts): Display brands list.
  output.extend(
      ' %s=%s' % (k, format_value(v))
      for k, v in sorted(info.iteritems())
      if k != 'f' and k != 'format' and
      not isinstance(v, (tuple, list, dict, set)))
  filename = info.get('f')
  if filename is not None:
    if '\n' in filename or '\0' in filename:
      raise ValueError('Invalid byte in filename: %r' % filename)
    output.append(' f=%s' % filename)  # Emit ` f=' last.
  output.append('\n')
  return ''.join(output)


def main(argv):
  if len(argv) < 2 or argv[1] == '--help':
    print >>sys.stderr, (
        'mediafileinfo.py: Get parameters and dimension of media files.\n'
        'This is free software, GNU GPL >=2.0. '
        'There is NO WARRANTY. Use at your risk.\n'
        'Usage: %s <filename> [...]' % argv[0])
    sys.exit(1)
  if len(argv) > 1 and argv[1] in ('--info', '--mode=info'):
    # For compatibility with media_scan.py.
    del argv[1]
  if len(argv) > 1 and argv[1] == '--':
    del argv[1]
  had_error = False
  for filename in argv[1:]:
    try:
      f = open(filename, 'rb')
    except IOError, e:
      had_error = True
      print >>sys.stderr, 'error: missing file %r: %s' % (filename, e)
      continue
    filesize = None
    try:
      f.seek(0, 2)
      filesize = int(f.tell())
      f.seek(0)
    except (IOError, OSError, ValueError, AttributeError):
      pass
    try:
      had_error_here, info = True, {'f': filename}
      if filesize is not None:
        info['size'] = filesize
      try:
        info = mediafileinfo_detect.analyze(f, info, file_size_for_seek=filesize)
        had_error_here = False
      except ValueError, e:
        #raise
        info['error'] = 'bad_data'
        if e.__class__ == ValueError:
          print >>sys.stderr, 'error: bad data in file %r: %s' % (filename, e)
        else:
          print >>sys.stderr, 'error: bad data in file %r: %s.%s: %s' % (
              filename, e.__class__.__module__, e.__class__.__name__, e)
      except IOError, e:
        info['error'] = 'bad_read'
        print >>sys.stderr, 'error: error reading from file %r: %s.%s: %s' % (
            filename, e.__class__.__module__, e.__class__.__name__, e)
      except (KeyboardInterrupt, SystemExit):
        raise
      except Exception, e:
        #raise
        info['error'] = 'error'
        print >>sys.stderr, 'error: error detecting in %r: %s.%s: %s' % (
            filename, e.__class__.__module__, e.__class__.__name__, e)
      if had_error_here:
        had_error = True
      if not info.get('format'):
        info['format'] = '?'
      try:
        # header_end_offset, hdr_done_at: Offset we reached after parsing
        # headers.
        info['hdr_done_at'] = int(f.tell())
      except (IOError, OSError, ValueError, AttributeError):
        pass
      sys.stdout.write(format_info(info))
      sys.stdout.flush()
      if not had_error_here and info['format'] == '?':
        print >>sys.stderr, 'warning: unknown file format: %r' % filename
        had_error = True
    finally:
      f.close()
  if had_error:
    sys.exit(2)


if __name__ == '__main__':
  sys.exit(main(sys.argv))
