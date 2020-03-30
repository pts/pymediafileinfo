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


class FormatDb(object):
  __slots__ = ('formats_by_prefix', 'header_preread_size', 'formats')

  def __init__(self, format_items, max_prefix_size=4, header_size_limit=512):
    # It's OK to have duplicate, e.g. 'cue'.
    #if len(dict(format_items)) != len(format_items):
    #  raise ValueError('Duplicate key in format_items.')
    hps = 0
    fbp = [{} for i in xrange(max_prefix_size + 1)]
    for format_spec in format_items:
      if len(format_spec) == 1:
        continue  # Indicates that analyze_* can generate this format.
      format, spec = format_spec
      fps = 0
      for i in xrange(0, len(spec), 2):
        size, pattern = spec[i], spec[i + 1]
        if size < fps:
          raise ValueError('Specs for format %s not in increasing order.' % format)
        if isinstance(pattern, str):
          fps = size + len(pattern)
        elif isinstance(pattern, tuple):
          if not pattern:
            raise ValueError('Empty pattern tuple.')
          if len(set(len(s) for s in pattern)) != 1:
            raise ValueError('Non-uniform pattern choice sizes for format %s: %r' % (format, pattern))
          if len(set(pattern)) != len(pattern):
            raise ValueError('Duplicate string in pattern tuple for format %s: %r' % (format, pattern))
          fps = size + len(pattern[0])
        else:
          fps = size
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
    self.formats = frozenset(item[0] for item in FORMAT_ITEMS)
