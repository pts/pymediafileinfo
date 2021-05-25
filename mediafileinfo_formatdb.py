"""Defines FormatDb, class for detecting and analyzing file formats."""

module_type = type(__import__('struct'))


def get_spec_prefixes(spec, count_limit=50, max_prefix_size=0):
  """Calculates prefixes.

  Args:
    spec: A FormatDb format spec (tuple of even size).
    count_limit: Maximum size of the result, i.e. maximum number of prefixes.
    max_prefix_size: If positive, truncate each returned prefix to this size.
  Returns:
    tuple containing all possible prefix strings (of the same
    size) of any string spec matches. The result has at most count_limit
    elements; to achieve this, the prefixes may get truncated.
  """
  prefixes = ('',)
  if count_limit >= 2 and spec and spec[0] == 0:
    ofs = i = 0
    while i < len(spec):
      size, pattern = spec[i], spec[i + 1]
      i += 2
      if isinstance(pattern, str) and size == ofs:
        prefixes2 = (pattern,)
      elif isinstance(pattern, tuple) and size == ofs:
        prefixes2 = pattern
        if not prefixes2:
          raise ValueError('Empty pattern tuple.')
      else:
        break
      if len(prefixes) * len(prefixes2) > count_limit:
        break
      prefixes = tuple(p1 + p2 for p1 in prefixes for p2 in prefixes2)
      ofs += len(prefixes2[0])
      if ofs >= max_prefix_size > 0:
        if ofs > max_prefix_size:
          prefixes = tuple(p1[:max_prefix_size] for p1 in prefixes)
        break
  elif count_limit < 1:
    raise ValueError('Bad count_limit: %d' % count_limit)
  return prefixes


def preread_fread_and_fskip(f, data, file_size_for_seek):
  prebuf, data = [0, data], None

  def fread(n):
    """Reads from prebuf (header) first, then from f."""
    i, buf = prebuf
    if buf:
      j = n - len(buf) + i
      if j <= 0:
        prebuf[0] += n
        return buf[i : i + n]
      prebuf[1] = ''
      return buf[i:] + f.read(j)
    else:
      return f.read(n)

  if file_size_for_seek is None:
    def fskip(size):
      """Returns bool indicating whther f was long enough."""
      i, buf = prebuf
      if buf:
        j = size - len(buf) + i
        if j <= 0:
          prebuf[0] += size
          return True
        else:
          prebuf[1] = ''
          size = j
      while size >= 32768:
        if len(f.read(32768)) != 32768:
          return False
        size -= 32768
      return size == 0 or len(f.read(size)) == size
  else:
    def fskip(size):
      """Returns bool indicating whther f was long enough."""
      i, buf = prebuf
      if buf:
        j = size - len(buf) + i
        if j <= 0:
          prebuf[0] += size
          return True
        else:
          prebuf[1] = ''
          size = j
      if size < 32768:
        data = f.read(size)
        return len(data) == size
      else:
        f.seek(size, 1)
        return f.tell() <= file_size_for_seek

  return fread, fskip




# import math; print ["\0"+"".join(chr(int(100. / 8 * math.log(i) / math.log(2))) for i in xrange(1, 1084))]'
LOG2_SUB = '\0\0\x0c\x13\x19\x1d #%\')+,./0234566789::;<<==>??@@AABBBCCDDEEEFFFGGGHHHIIIJJJKKKKLLLLMMMMNNNNOOOOOPPPPPQQQQQRRRRRSSSSSSTTTTTTUUUUUUVVVVVVVWWWWWWWXXXXXXXXYYYYYYYYZZZZZZZZ[[[[[[[[[\\\\\\\\\\\\\\\\\\]]]]]]]]]]^^^^^^^^^^^___________```````````aaaaaaaaaaaaabbbbbbbbbbbbbcccccccccccccdddddddddddddddeeeeeeeeeeeeeeeeffffffffffffffffggggggggggggggggghhhhhhhhhhhhhhhhhhiiiiiiiiiiiiiiiiiiiijjjjjjjjjjjjjjjjjjjjkkkkkkkkkkkkkkkkkkkkklllllllllllllllllllllllmmmmmmmmmmmmmmmmmmmmmmmmnnnnnnnnnnnnnnnnnnnnnnnnnnoooooooooooooooooooooooooopppppppppppppppppppppppppppppqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrsssssssssssssssssssssssssssssssssttttttttttttttttttttttttttttttttttttuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{|||||||||||||||||||||||||||||||||||||||||||||||||||||||}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}~'
assert len(LOG2_SUB) == 1084, 'Unexpected LOG2_SUB size.'


def copy_info_from_tracks(info):
  """Copies fields from info['tracks'] to top-level in info."""

  # Copy audio fields.
  audio_track_infos = [track for track in info['tracks']
                       if track['type'] == 'audio']
  if len(audio_track_infos) > 1:
    codecs_set = filter(None, set(ati.get('codec') for ati in audio_track_infos))
    if len(codecs_set) == 1:
      info['acodec'] = codecs_set[0]
    else:
      info['acodec'] = 'multiple'
  elif len(audio_track_infos) == 1:
    for key, value in sorted(audio_track_infos[0].iteritems()):
      if key == 'codec':
        key = 'acodec'  # Also used by medid.
      elif key == 'channel_count':
        key = 'anch'  # Also used by medid.
      elif key == 'sample_rate':
        key = 'arate'  # Also used by medid.
      elif key == 'sample_size':
        key = 'asbits'
      elif key == 'subformat':
        key = 'asubformat'
      elif key == 'type':
        continue
      else:
        key = 'audio_%s' % key
      info[key] = value
    info.setdefault('acodec', '?')

  # Copy video fields.
  video_track_infos = [track for track in info['tracks']
                       if track['type'] == 'video']
  if len(video_track_infos) > 1:
    # Some .mov files have the same (width, height) with codec=mp4a first,
    # and then with codec=jpeg. We keep only the first video track.
    dimens_set = set((vti.get('width'), vti.get('height'))
                     for vti in video_track_infos)
    if len(dimens_set) == 1:
      del video_track_infos[1:]
    else:
      codecs_set = filter(None, set(vti.get('codec') for vti in video_track_infos))
      if len(codecs_set) > 1:
        info['vcodec'] = 'multiple'
      elif codecs_set:
        info['vcodec'] = codecs_set[0]
      else:
        info['vcodec'] = '?'
  if len(video_track_infos) == 1:
    for key, value in sorted(video_track_infos[0].iteritems()):
      if key == 'codec':
        key = 'vcodec'  # Also used by medid.
      elif key == 'type':
        if value == 'video':
          continue
        key = 'vtype'
      elif key in ('width', 'height'):
        pass  # Also used by media_scan.py.
      else:
        # medid uses: fps, ht (we: height), wd (we: width).
        key = 'video_%s' % key
      info[key] = value
    info.setdefault('vcodec', '?')


def get_default_arg(func_obj, name):
  if not isinstance(func_obj, type(get_default_arg)):
    raise TypeError
  defaults = func_obj.func_defaults
  if defaults:
    varnames, i = func_obj.func_code.co_varnames, func_obj.func_code.co_argcount
    d = len(defaults) - i
    assert d <= 0, 'Too many defaults.'
    while i > 0:
      i -= 1
      if varnames[i] == name:
        return defaults[i + d]
  return None


def get_analyze_funcs_by_format(module_obj):
  if not isinstance(module_obj, module_type):
    raise TypeError('Module expected, got: %r' % type(module_obj))
  analyze_funcs_by_format = dict(module_obj.ANALYZE_FUNCS_BY_FORMAT)
  for name, obj in sorted(module_obj.__dict__.iteritems()):
    if callable(obj) and name.startswith('analyze_') and get_default_arg(obj, 'spec') is not None:
      format = get_default_arg(obj, 'format')
      if format is not None:
        analyze_funcs_by_format.setdefault(format, obj)
  return analyze_funcs_by_format


def get_format_items_from_module(module_obj):
  if not isinstance(module_obj, module_type):
    raise TypeError('Module expected, got: %r' % type(module_obj))
  format_items = list(module_obj.FORMAT_ITEMS)
  formats = set(item[0] for item in format_items)
  for name, obj in sorted(module_obj.__dict__.iteritems()):
    if callable(obj) and name.startswith('analyze_'):
      spec = get_default_arg(obj, 'spec')
      if spec is not None:
        format = get_default_arg(obj, 'format')
        extra_formats = get_default_arg(obj, 'extra_formats')
        if format is not None:
          if format in formats:
            raise ValueError('duplicate format= in analyze funcs: %s' % format)
          formats.add(format)
          if isinstance(spec[0], tuple):
            for spec2 in spec:
              format_items.append((format, spec2))
          else:
            format_items.append((format, spec))
          for extra_format in (extra_formats or ()):
            if extra_format in formats:
              raise ValueError('duplicate extra_format= in analyze funcs: %s' % extra_format)
            formats.add(extra_format)
            format_items.append((extra_format,))
        else:
          if extra_formats is not None:
            raise ValueError('extra_formats= without format= in analyze func %s' % name)
  return format_items


class FormatDb(object):
  """Class for detection and analyzing of file formats.

  Detection is done using the domain-specific language called Spec. The Spec
  for each format is passed within format_items to __init__. If the file
  header matches multiple Specs, then the most specific match (i.e. the one
  which matches more bits, approximately) will be used. For example, if a format
  starts with '\\0\\0\\0', and the mp4 format has header[4 : 8] == 'ftyp', and
  the file starts with '\\0\\0\\0\\x18ftyp', then mediafileinfo.py will detect
  the file as mp4, because that has matched 4 bytes ('ftyp'), and the other
  format only matched 3 bytes (at the beginning). This strategy leads to the
  most likely match even if detection of new file formats with short matches
  get added in the future.

  A Spec is tuple of even size, a concatenation of (ofs, pattern) tuples,
  where ofs is nonnegative and strictly increasing. An empty Spec is OK, but
  it's useless, because it doesn't match anything. A non-empty Spec can be
  tried whether it matches a string (prefix, header of a file). If it
  matches, the match also has a confidence, which is a positive integer
  which is approximately 100 times the number of bytes literally matched.
  When matching multiple Specs against the same header, the match with the
  largest total confidence will be chosen (on a tie, the format later in
  lexicographic ordering will be chosen).

  If the pattern in a Spec is a (byte) string, then it's matched literally
  starting at ofs, i.e. `header[ofs : ofs + len(pattern)] == pattern'. If
  pattern is a tuple containing (byte) strings, then it's elements are
  matched literally starting at ofs, i.e. `header[ofs : ofs +
  len(pattern[0])] in pattern'. The confidences is calculated from the
  pattern, e.g. confidence for pattern ('foo', 'bar', 'baz', 'bat') is 275,
  because it would be 300 becasuse it matches 3 bytes, but 2 bits
  (confidence 25) are subtracted because there are 4 options.

  If the pattern in a Spec is a callable, then it will be called as
  `is_matching, confidence = pattern(header[:ofs + ...])', where ... is
  anthing, but the callable must not examine header[ofs:]. Thus the callable
  equivalent of (ofs, pattern) value (100, ('foo', 'bar', 'baz', 'bat')) is
  `(103, lambda header: (header[100 : 103] in ('foo', 'bar', 'baz', 'bat'),
  275))'. The callable must calculate the confidence of its own match, and
  this can depend on the header.

  There is no regexp (regular expression) matching support in Spec, but it
  can be emulated with a callable pattern. Please note that the confidence
  must be calculated. Returning an inaccurate confidence (e.g. the dummy
  value of 1) risks misidentifying the file format if multiple Specs match.

  FormatDb uses a speed optimization to avoid looking at all Specs (most of
  which probably won't match anyway): first it looks at the 4-byte prefix of
  the header, and it considers only those Specs which match the prefix. This
  prefix-to-Specs mapping is stored in self.formats_by_prefix, and is
  populated once by __init__.
  """

  __slots__ = ('formats_by_prefix', 'header_preread_size', 'formats')

  def __init__(self, format_items, max_prefix_size=4, header_size_limit=512):
    if isinstance(format_items, module_type):
      format_items = get_format_items_from_module(format_items)
    # It's OK to have duplicate, e.g. 'cue'.
    #if len(dict(format_items)) != len(format_items):
    #  raise ValueError('Duplicate key in format_items.')
    hps = 0
    fbp = [{} for i in xrange(max_prefix_size + 1)]
    for format_spec in format_items:
      if len(format_spec) == 1:
        continue  # Indicates that analyze_* can generate this format.
      format, spec = format_spec
      if not isinstance(spec, tuple):
        raise TypeError('spec must be tuple.')
      if len(spec) & 1:
        raise TypeError('spec must be of even size.')
      fps = 0
      for i in xrange(0, len(spec), 2):
        ofs, pattern = spec[i], spec[i + 1]
        if not isinstance(ofs, int):
          raise TypeError('ofs must be int.')
        if ofs < fps:
          raise ValueError('Specs for format %s not in increasing order.' % format)
        if isinstance(pattern, str):
          if not pattern:
            raise ValueError('Empty pattern string.')
          fps = ofs + len(pattern)
        elif isinstance(pattern, tuple):
          if not pattern:
            raise ValueError('Empty pattern tuple.')
          if len(set(len(s) for s in pattern)) != 1:
            raise ValueError('Non-uniform pattern choice sizes for format %s: %r' % (format, pattern))
          if len(set(pattern)) != len(pattern):
            raise ValueError('Duplicate string in pattern tuple for format %s: %r' % (format, pattern))
          if not pattern[0]:
            raise ValueError('Empty pattern tuple item.')
          fps = ofs + len(pattern[0])
        elif callable(pattern):
          fps = ofs
        else:
          raise TypeError('Bad pattern type: %r' % type(pattern))
        if fps > header_size_limit:
          raise ValueError('Header too long.')
        hps = max(hps, fps)
      for prefix in get_spec_prefixes(spec, max_prefix_size=max_prefix_size):
        fbp2 = fbp[len(prefix)]
        if prefix in fbp2:
          fbp2[prefix].append(format_spec)
        else:
          fbp2[prefix] = [format_spec]
    self.header_preread_size = hps  # Typically 64, we have 408.
    if hps > header_size_limit:
      raise AssertionError('Header too long, maximum size is %s.' % header_size_limit)
    self.formats_by_prefix = fbp
    self.formats = frozenset(item[0] for item in format_items)

  def detect(self, f):
    """Detects the file format.

    Matches all Specs (in self.formats_by_prefix), returns the match with
    the largest total confidence.

    Args:
      f: A .read(...) method of a file-like object, a file-like object, or
          an str.
    Returns:
      (format, header), where format is a non-empty string (can be '?'),
      header is a string containing the prefix of f, and exactly this many
      bytes were read from f. The match with the largest total confidence is
      returned (on a tie, the legixographically largest format is used).
    """
    log2_sub, lmi = LOG2_SUB, len(LOG2_SUB) - 1
    size = self.header_preread_size
    if isinstance(f, (str, buffer)):
      header = f[:size]
    elif callable(getattr(f, 'read', None)):
      header = f.read(size)
    else:
      header = f(size)
    if not isinstance(header, str):
      raise TypeError
    best_match = ()
    fbp = self.formats_by_prefix
    for j in xrange(min(len(header), len(fbp) - 1), -1, -1):
      for format, spec in fbp[j].get(header[:j], ()):
        confidence = 0
        i = 0
        prev_ofs = 0
        while i < len(spec):
          ofs = spec[i]
          pattern = spec[i + 1]
          if isinstance(pattern, str):
            if header[ofs : ofs + len(pattern)] != pattern:
              break
            confidence += 100 * len(pattern) - 10 * min(ofs - prev_ofs, 10)
            prev_ofs = ofs + len(pattern)
          elif isinstance(pattern, tuple):
            # TODO(pts): Check that each str in pattern has the same len.
            header_sub = header[ofs : ofs + len(pattern[0])]
            if not [1 for pattern2 in pattern if header_sub == pattern2]:
              break
            # We use log2_sub here to decrease the confidence when there are
            # many patterns. We use `-ofs' to increase the confidence when
            # matching near the start of the string.
            confidence += (
                100 * len(header_sub) - ord(log2_sub[min(len(pattern), lmi)]) -
                10 * min(ofs - prev_ofs, 10))
            prev_ofs = ofs + len(pattern[0])
          elif callable(pattern):
            # Don't update prev_ofs, ofs is too large here.
            is_matching, cadd = pattern(header)
            if not is_matching:
              break
            if not isinstance(cadd, int) or cadd <= 0:
              raise ValueError(
                  'Bad confidence in callable pattern for format %s: %r' %
                  (format, cadd))
            confidence += cadd
          else:
            raise AssertionError(type(pattern))
          i += 2
        if i == len(spec):  # The spec has matched.
          best_match = max(best_match, (confidence, format))
    return (best_match or (-1, '?'))[1], header

  def analyze(self, f, info=None, file_size_for_seek=None, analyze_funcs_by_format=None):
    """Detects file format, and gets media parameters in file f.

    For audio or video, info['tracks'] is a list with an item for each video
    or audio track (info['tracks'][...]['type'] in ('video', 'audio').
    Presence and parameters of subtitle tracks are not reported. The most
    important fields from info['tracks'] is also copied to info, e.g.
    info['tracks'][0]['codec'] is copied to info['acodec'] (for audio) or
    info['vcodec'] (for video).

    Args:
      f: File-like object with a .read(n) method and an optional .seek(n) method,
          should do buffering for speed, and must return exactly n bytes unless
          at EOF. Seeking will be avoided if possible.
      info: A dict to update with the info found, or None to create a new one.
      file_size_for_seek: None or an integer specifying the file size up to which
          it is OK to seek forward (fskip).
      analyze_funcs_by_format: A dict mapping from formats to analyze_... funcs,
          or None.
    Returns:
      The info dict.
    """
    if info is None:
      info = {}
    # Set it early, in case of an exception.
    info.setdefault('format', '?')
    format, header = self.detect(f)
    info['format'] = format
    if analyze_funcs_by_format:
      analyze_func = analyze_funcs_by_format.get(format)
      try:
        if analyze_func is not None:
          fread, fskip = preread_fread_and_fskip(f, header, file_size_for_seek)
          analyze_func(fread, info, fskip)
      finally:
        if info.get('tracks'):
          copy_info_from_tracks(info)
      if info['format'] not in self.formats and info['format'] != '?':
        raise RuntimeError('Analyzing of format %s returned unknown format: %r' % (format, info['format']))
    return info
