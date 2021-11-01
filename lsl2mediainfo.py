#! /usr/bin/python
#
# lsl2mediainfo.py: convert `ls -l' output to mediainfo listing
# by pts@fazekas.hu at Mon Nov  1 14:49:52 CET 2021
#
# Input: output of `ls -l' or `ls -laR' on stdin
# Output: mediafileinfo lines (starting with format=) on stdout
#
 
import calendar
import re
import sys
import time


TOTAL_LINE_RE = re.compile(r'total \d+\Z')

NATURAL_DECIMAL_INT_RE = re.compile(r'\d+\Z')

YEAR_INT_RE = re.compile(r'[1-9]\d\d\d\Z')

HHMM_RE = re.compile(r'(?:0?\d|1[0-2]):[0-5]\d\Z')

MONTHS = ('', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
          'Oct', 'Nov', 'Dec')

FULL_DAY_RE = re.compile(r'[1-9]\d\d\d-(?:0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\Z')

FULL_TIME_RE = re.compile(r'(?:0?\d|1\d|2[0-3]):[0-5]\d:[0-5]\d(?:[.]\d+)?\Z')

TZDIFF_RE = re.compile(r'[+-]\d\d[0-5]\d\Z')


def process_lines(lines):
  state, current_dir, current_year = 0, '.', None
  for line in lines:
    line = line.rstrip('\n')
    if state:  # Inside a directory.
      if line.startswith('-'):
        items = line.split(None, 8)
        if len(items) != 9:
          sys.stderr.write('warning: bad item count, ignoring line: %r\n' %
                           line)
        elif not NATURAL_DECIMAL_INT_RE.match(items[1]):
          sys.stderr.write('warning: bad link count, ignoring line: %r\n' %
                           line)
        elif not NATURAL_DECIMAL_INT_RE.match(items[4]):
          sys.stderr.write('warning: bad file size, ignoring line: %r\n' %
                           line)
        else:
          info = {'format': '?', 'size': int(items[4])}
          if items[5] in MONTHS:
            if not (NATURAL_DECIMAL_INT_RE.match(items[6]) and
                    1 <= int(items[6]) <= 31):
              sys.stderr.write('warning: bad day of month, '
                               'ignoring line: %r\n' % line)
            elif not (YEAR_INT_RE.match(items[7]) or HHMM_RE.match(items[7])):
              sys.stderr.write('warning: bad hour:minute, '
                               'ignoring line: %r\n' % line)
            if YEAR_INT_RE.match(items[7]):
              year = int(items[7])
              hour = minute = second = 0
            else:
              if current_year is None:
                current_year = time.localtime()[0]
              year, second = current_year, 0
              hour, minute = map(int, items[7].split(':'))
            month = MONTHS.index(items[5])
            mday = int(items[6])
            info = {'format': '?', 'size': int(items[4])}
            mtimetuple = year, month, mday, hour, minute, second
            # mtime is approximate, `second' is always 0.
            mtime = int(time.mktime(mtimetuple + (0, 0, 0)))  # Uses local time.
            mtimetuple2 = time.localtime(mtime)[:6]
          elif FULL_DAY_RE.match(items[5]):
            # Output of GNU `ls -l --full-time'.
            year, month, mday = map(int, items[5].split('-'))
            if not FULL_TIME_RE.match(items[6]):
              sys.stderr.write('warning: bad hour:minute:second, '
                               'ignoring line: %r\n' % items[6])
            hour, minute, second = map(
                int, items[6].split('.', 1)[0].split(':'))
            if not TZDIFF_RE.match(items[7]):
              sys.stderr.write('warning: bad tzdiff, '
                               'ignoring line: %r\n' % line)
            sign = (-60, 60)[items[7].startswith('-')]
            mtimetuple = year, month, mday, hour, minute, second
            # mtime is approximate, nanosecond is always 0 here, but is more
            # accurate in items[6].
            mtime = calendar.timegm(mtimetuple)  # Uses UTC (GMT).
            mtimetuple2 = time.gmtime(mtime)[:6]
            mtime += sign * (int(items[7][1 : 3]) * 60 + int(items[7][3 : 5]))
          else:
            sys.stderr.write('warning: bad month or year-month-day, '
                             'ignoring line: %r\n' % line)
          if mtimetuple != mtimetuple2:
            print >>sys.stderr, (mtimetuple, mtimetuple2)
            sys.stderr.write('warning: bad time, '
                             'ignoring mtime: %r\n' % (mtimetuple,))
          info['mtime' ] = mtime
          filename = items[8]
          if current_dir != '.':
            filename = ''.join((current_dir, '/', filename))
          format = info.pop('format')
          yield 'format=%s%s f=%s\n' % (format, ''.join(
              ' %s=%s' % item
              for item in sorted(info.iteritems())), filename)
          #yield repr(items) + '\n'
      elif line.startswith('total ') and TOTAL_LINE_RE.match(line):
        pass
      elif not line:
        state = 0
    else:
      if line.startswith('format='):
        yield line  # Pass through.
      elif line.startswith('total ') and TOTAL_LINE_RE.match(line):
        state = 1
      elif line.endswith(':'):
        current_dir, state = line[:-1].strip('/'), 1
        i = 0
        while current_dir[i : i + 2] == './':
          i += 2
          while current_dir[i : i + 1] == '/':
            i += 1
        current_dir = current_dir[i:]
      elif line:
        sys.stderr.write('warning: syntax error, ignoring line: %r\n' % line)
      


def main(argv):
  of = sys.stdout
  for format_line in process_lines(sys.stdin):
    of.write(format_line)


if __name__ == '__main__':
  sys.exit(main(sys.argv))
