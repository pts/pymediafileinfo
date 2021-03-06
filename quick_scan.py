#! /bin/sh
# by pts@fazekas.hu at Sun Nov 24 12:08:24 CET 2019
#

""":" # quick_scan.py: Get size and mtime of files.

type python2.7 >/dev/null 2>&1 && exec python2.7 -- "$0" ${1+"$@"}
type python2.6 >/dev/null 2>&1 && exec python2.6 -- "$0" ${1+"$@"}
type python2.5 >/dev/null 2>&1 && exec python2.5 -- "$0" ${1+"$@"}
type python2.4 >/dev/null 2>&1 && exec python2.4 -- "$0" ${1+"$@"}
exec python -- ${1+"$@"}; exit 1

This script need Python 2.4, 2.5, 2.6 or 2.7. Python 3.x won't work.

Typical usage: quick_scan.py .

The quick scan doesn't compute sha256= (so no need to read the whole file)
or format= (so no need to read the file header).
"""

import os
import os.path
import stat
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


# --- From quick_scan.py .


def get_quick_info(filename, stat_obj):
  return {'mtime': int(stat_obj.st_mtime), 'size': stat_obj.st_size,
          'f': filename}, False


def get_symlink_info(filename, stat_obj):
  info = {'format': 'symlink', 'mtime': int(stat_obj.st_mtime), 'f': filename}
  try:
    info['symlink'] = os.readlink(filename)
    info['size'] = len(info['symlink'])
  except OSError, e:
    print >>sys.stderr, 'error: readlink: %s' % (filename, e)
    return info, True
  return info, False


def info_scan(dirname, outf, get_file_info_func):
  """Prints results sorted by filename."""
  had_error = False
  try:
    entries = os.listdir(dirname)
  except OSError, e:
    print >>sys.stderr, 'error: listdir %r: %s' % (dirname, e)
    had_error = True
    entries = ()
  files, subdirs = [], []
  for entry in entries:
    if dirname == '.':
      filename = entry
    else:
      filename = os.path.join(dirname, entry)
    try:
      stat_obj = os.lstat(filename)
    except OSError, e:
      print >>sys.stderr, 'error: lstat %r: %s' % (filename, e)
      stat_obj = None
    if stat_obj is None:
      had_error = True
    elif stat.S_ISDIR(stat_obj.st_mode):
      subdirs.append(filename)
    elif (stat.S_ISREG(stat_obj.st_mode) or
          stat.S_ISLNK(stat_obj.st_mode)):
      files.append((filename, stat_obj))
  for filename, stat_obj in sorted(files):
    if stat.S_ISLNK(stat_obj.st_mode):
      info, had_error_here = get_symlink_info(filename, stat_obj)
    else:
      info, had_error_here = get_file_info_func(filename, stat_obj)
    if had_error_here:
      had_error = True
    elif info.get('format') == '?':
      print >>sys.stderr, 'warning: unknown file format: %r' % filename
      had_error = True
    outf.write(format_info(info))
    outf.flush()
  for filename in sorted(subdirs):
    had_error |= info_scan(filename, outf, get_file_info_func)
  return had_error


def process(filename, outf, get_file_info_func):
  """Prints results sorted by filename."""
  try:
    stat_obj = os.lstat(filename)
  except OSError, e:
    print >>sys.stderr, 'error: missing file %r: %s' % (filename, e)
    return True
  if stat.S_ISDIR(stat_obj.st_mode):
    return info_scan(filename, outf, get_file_info_func)
  elif stat.S_ISREG(stat_obj.st_mode):
    info, had_error = get_file_info_func(filename, stat_obj)
    outf.write(format_info(info))
    outf.flush()
    if not had_error and info.get('format') == '?':
      print >>sys.stderr, 'warning: unknown file format: %r' % filename
      had_error = True
    return had_error
  elif stat.S_ISLNK(stat_obj.st_mode):
    info, had_error = get_symlink_info(filename, stat_obj)
    outf.write(format_info(info))
    outf.flush()
    return had_error
  else:
    return False


# ---


def set_fd_binary(fd):
  """Make sure that os.write(fd, ...) doesn't write extra \r bytes etc."""
  if sys.platform.startswith('win'):
    import os
    import msvcrt
    msvcrt.setmode(fd, os.O_BINARY)


def main(argv):
  if len(argv) < 2 or argv[1] == '--help':
    print >>sys.stderr, (
        'quick_scan.py: Get size and mtime of files.\n'
        'This is free software, GNU GPL >=2.0. '
        'There is NO WARRANTY. Use at your risk.\n'
        'Usage: %s [<flag> ...] <filename> [...]' % argv[0])
    sys.exit(1)
  i = 1
  mode = 'quick'
  while i < len(argv):
    arg = argv[i]
    i += 1
    if arg == '--':
      break
    if arg == '-' or not arg.startswith('-'):
      i -= 1
      break
    if arg in ('--quick', '--mode=quick'):
      # For compatibility with mediafileinfo.py and media_scan.py.
      mode = 'quick'
    elif arg.startswith('--mode='):
      sys.exit('Invalid flag value: %s' % arg)
    else:
      sys.exit('Unknown flag: %s' % arg)

  outf = sys.stdout
  set_fd_binary(outf.fileno())
  prefix = '.' + os.sep
  had_error = False
  get_file_info_func = get_quick_info
  # Keep the original argv order, don't sort.
  for filename in argv[i:]:
    if filename.startswith(prefix):
      filename = filename[len(prefix):]
    had_error |= process(filename, outf, get_file_info_func)
  if had_error:
    sys.exit(2)


if __name__ == '__main__':
  sys.exit(main(sys.argv))
