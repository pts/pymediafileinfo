#! /usr/bin/python
# by pts@fazekas.hu at Sun Sep 10 00:26:18 CEST 2017

import struct
import sys

import mediafileinfo_detect


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
    print >>sys.exit(
        'mediafileinfo.py: Get parameters and dimension of media files.\n'
        'This is free software, GNU GPL >=2.0. '
        'There is NO WARRANTY. Use at your risk.\n'
        'Usage: %s <filename> [...]' % argv[0])
    sys.exit(1)
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
    try:
      had_error_here, info = True, {}
      try:
        info = mediafileinfo_detect.detect(f, info, is_seek_ok=True)
        had_error_here = False
      except (KeyboardInterrupt, SystemExit):
        raise
      except (IOError, ValueError), e:
        info['error'] = 'bad_file'
        if e.__class__ == ValueError:
          print >>sys.stderr, 'error: bad file %r: %s' % (filename, e)
        else:
          print >>sys.stderr, 'error: bad file %r: %s.%s: %s' % (
              filename, e.__class__.__module__, e.__class__.__name__, e)
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
      except (IOError, OSError, AttributeError):
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