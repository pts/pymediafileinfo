#! /usr/bin/python
#
# merge_mediainfo_lines.py: merge mediainfo file lines by filename
# by pts@fazekas.hu at Thu Jan  6 13:38:11 CET 2022
#
# Input: mediainfo lines (cat mscan*.out) on stdin
# Output: mediainfo lines on stdout (as many duplicates as possible by filename merged), merge errors on stderr
#

import re
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
      if ' ' in v or '\n' in v:
        raise ValueError('Bad info string value: %r' % v)
      return v
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


def merge_infos(infos):
  info2, mismatches = {}, {}
  for info1 in infos:
    for k, v in info1.iteritems():
      if k not in info2:
        info2[k] = v
      elif info2[k] != v:
        if k not in mismatches:
          mismatches[k] = [info2[k]]
        mismatches[k].append(v)
  if mismatches and tuple(mismatches) == ('mtime',):
    info2['mtime'] = str(min(map(int, mismatches['mtime'])))  # Use smallest (earliest) mtime.
    mismatches.clear()
  return info2, mismatches


def merge_by_key(infos, key):
  infos_by_key = {}
  for info in infos:
    v = info.get(key)
    if key == 'size' and isinstance(v, str):
      v = int(v)
    if v not in infos_by_key:
      infos_by_key[v] = []
    infos_by_key[v].append(info)
  infos3 = []
  for v, infos1 in sorted(infos_by_key.iteritems()):
    info2, mismatches = merge_infos(infos1)
    if mismatches:
      infos3.extend(infos1)
    else:
      infos3.append(info2)
  # assert 0, (len(infos), len(infos3), infos3)
  return infos3


def main(argv):
  f, of = sys.stdin, sys.stdout
  infos_by_fn = {}
  for line in f:
    line = line.rstrip('\n')  # Don't remove '\r', it's binary.
    i = line.find(' f=')
    if i < 0:
      raise ValueError('f= not found: %d' % line_source.tell())
    fn = line[line.find('=', i) + 1:]
    info = {'f': fn}
    for item in line[:i].split(' '):
      kv = item.split('=', 1)
      if len(kv) != 2:
        raise ValueError('Expected key=value, got: %s in line %r' % (kv, line))
      if kv[0] in info:
        raise ValueError('Duplicate key %r in info line %r' % (kv[0], line))
      info[kv[0]] = kv[1]
    if fn not in infos_by_fn:
      infos_by_fn[fn] = []
    infos_by_fn[fn].append(info)
  for fn, infos in sorted(infos_by_fn.iteritems()):
    info2, mismatches = merge_infos(infos)
    if not mismatches:
      of.write(format_info(info2))
      continue
    if 'size' in mismatches:
      print >>sys.stderr, 'warning: found size mismatches: fn=%r' % fn
      infos = merge_by_key(infos, 'size')
    elif 'sha256' in mismatches:
      print >>sys.stderr, 'warning: found sha256 mismatches: fn=%r' % fn
      infos = merge_by_key(infos, 'sha256')
    else:
      print >>sys.stderr, 'warning: found mismatches: fn=%r info=%r mismatches=%r' % (fn, info2, mismatches)
    for info2 in infos:
      of.write(format_info(info2))

if __name__ == '__main__':
  sys.exit(main(sys.argv))
