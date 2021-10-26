#! /bin/sh
# by pts@fazekas.hu at Thu Oct 17 21:23:44 CEST 2019

""":" # mediafileinfo_detect_test.py: Unit tests.

type python2.7 >/dev/null 2>&1 && exec python2.7 -- "$0" ${1+"$@"}
type python2.6 >/dev/null 2>&1 && exec python2.6 -- "$0" ${1+"$@"}
type python2.5 >/dev/null 2>&1 && exec python2.5 -- "$0" ${1+"$@"}
type python2.4 >/dev/null 2>&1 && exec python2.4 -- "$0" ${1+"$@"}
exec python -- ${1+"$@"}; exit 1

This script need Python 2.4, 2.5, 2.6 or 2.7. Python 3.x won't work.

Typical usage: mediafileinfo.py *.mp4
"""

import cStringIO
import struct
import sys
import unittest

import mediafileinfo_detect
import mediafileinfo_formatdb


# ---


class FormatDbTest(unittest.TestCase):
  maxDiff = None

  def test_get_spec_prefixes(self):
    f = mediafileinfo_formatdb.get_spec_prefixes
    self.assertEqual(('',), f((0, lambda header: (True, 1)))),
    self.assertEqual(('',), f((1, lambda header: (True, 1)))),
    self.assertEqual(('',), f((3, 'bar', 6, 'foo')))
    self.assertEqual(('foo',), f((0, 'foo')))
    self.assertEqual(('fo',), f((0, 'foo'), max_prefix_size=2))
    self.assertEqual(('foo',), f((0, 'foo'), max_prefix_size=3))
    self.assertEqual(('foo',), f((0, 'foo'), max_prefix_size=4))
    self.assertEqual(('foobar',), f((0, 'foo', 3, 'bar')))
    self.assertEqual(('foobar', 'foobar', 'foxbar'), f((0, ('foo', 'foo', 'fox'), 3, 'bar')))
    spec = (0, ('foo', 'foo', 'fox'), 3, 'bar', 6, '/', 7, ('baz', 'bez'))
    self.assertEqual(('foobar/baz', 'foobar/bez', 'foobar/baz', 'foobar/bez', 'foxbar/baz', 'foxbar/bez'), f(spec))
    self.assertEqual(('foobar/baz', 'foobar/bez', 'foobar/baz', 'foobar/bez', 'foxbar/baz', 'foxbar/bez'), f(spec, max_prefix_size=42))
    self.assertEqual(('foobar/baz', 'foobar/bez', 'foobar/baz', 'foobar/bez', 'foxbar/baz', 'foxbar/bez'), f(spec, max_prefix_size=10))
    self.assertEqual(('foobar/ba', 'foobar/be', 'foobar/ba', 'foobar/be', 'foxbar/ba', 'foxbar/be'), f(spec, max_prefix_size=9))
    self.assertEqual(('foobar/b', 'foobar/b', 'foobar/b', 'foobar/b', 'foxbar/b', 'foxbar/b'), f(spec, max_prefix_size=8))
    self.assertEqual(('foobar/','foobar/', 'foxbar/'), f(spec, max_prefix_size=7))
    self.assertEqual(('foobar/', 'foobar/', 'foxbar/'), f((0, ('foo', 'foo', 'fox'), 3, 'bar', 6, '/', 7, ('baz', 'bez')), count_limit=3))
    self.assertEqual(('foobar/', 'foobar/', 'foxbar/'), f((0, ('foo', 'foo', 'fox'), 3, 'bar', 6, '/', 8, ('baz', 'bez'))))
    self.assertEqual(('foobar', 'foobar', 'foxbar'), f((0, ('foo', 'foo', 'fox'), 3, 'bar', 6, lambda header: (True, 1), 8, ('baz', 'bez'))))
    self.assertEqual(('foobar',) * 50, f((0, ('foo',) * 50, 3, 'bar')))
    self.assertEqual(('',), f((0, ('foo',) * 51, 3, 'bar')))  # Over count_limit=50.
    self.assertEqual(('foo',), f((0, 'foo', 3, ('bar',) * 100, 6, 'done')))
    self.assertEqual(('foobar/',) * 10, f((0, ('foo',) * 10, 3, 'bar', 6, '/', 7, ('a', 'a')), count_limit=10))

  def test_analyze(self):
    def analyze_test1(fread, info, fskip):
      header = fread(8)
      if not header.startswith('prefix1'):
        raise ValueError
      info['format'], info['tracks'] = 'test1', []
      if len(header) >= 8:
        info['tracks'].append({'type': 'video', 'codec': 'mjpeg', 'width': 515, 'height': 513})
        info['tracks'].append({'type': 'audio', 'codec': 'adpcm'})

    def analyze_test2(fread, info, fskip):
      header = fread(8)
      if not header.startswith('prefix2'):
        raise ValueError
      info['format'], info['subformat'], info['tracks'] = 'test2', 'test2sub', []
      if len(header) >= 8:
        info['tracks'].append({'type': 'audio', 'codec': 'vorbis', 'channel_count': 1, 'sample_rate': 44100, 'sample_size': 16})

    format_db = mediafileinfo_formatdb.FormatDb((
        ('test1', (0, 'prefix1')),
        ('test2', (0, 'prefix2')),
    ))
    analyze_funcs_by_format = {
        'test1': analyze_test1,
        'test2': analyze_test2,
    }
    self.assertEqual(format_db.analyze(cStringIO.StringIO('prefix1'), analyze_funcs_by_format=analyze_funcs_by_format),
                     {'format': 'test1', 'tracks': []})
    self.assertEqual(format_db.analyze(cStringIO.StringIO('prefix1+'), analyze_funcs_by_format=analyze_funcs_by_format),
                     {'format': 'test1', 'vcodec': 'mjpeg', 'width': 515, 'height': 513, 'acodec': 'adpcm',
                      'tracks': [{'type': 'video', 'codec': 'mjpeg', 'width': 515, 'height': 513},
                                 {'type': 'audio', 'codec': 'adpcm'}]})
    self.assertEqual(format_db.analyze(cStringIO.StringIO('prefix2'), analyze_funcs_by_format=analyze_funcs_by_format),
                     {'format': 'test2', 'subformat': 'test2sub', 'tracks': []})
    self.assertEqual(format_db.analyze(cStringIO.StringIO('prefix2+'), analyze_funcs_by_format=analyze_funcs_by_format),
                     {'format': 'test2', 'subformat': 'test2sub', 'acodec': 'vorbis', 'anch': 1, 'arate': 44100, 'asbits': 16,
                      'tracks': [{'type': 'audio', 'codec': 'vorbis', 'channel_count': 1, 'sample_rate': 44100, 'sample_size': 16}]})

  def test_detect_unknown(self):
    format_db = mediafileinfo_formatdb.FormatDb((('test0', (0, 'pre0')), ('test1', (1, 'prefix1'))))
    self.assertEqual(format_db.detect('Unknown data'), ('?', 'Unknown '))  # Truncated to the longer spec size.


# ---


def analyze_string(data, expect_error=False, analyze_func=None,
                   _format_db=mediafileinfo_formatdb.FormatDb(mediafileinfo_detect),
                   _analyze_funcs_by_format=mediafileinfo_formatdb.get_analyze_funcs_by_format(mediafileinfo_detect)):
  info = {}
  detected_format = _format_db.detect(data)[0]
  analyze_func2 = _analyze_funcs_by_format.get(detected_format)
  if analyze_func is None:
    analyze_func = analyze_func2
  elif analyze_func is not analyze_func2:
    info['detected_analyze'] = analyze_func2
  if analyze_func is None:
    info['format'] = detected_format
  else:
    fread, fskip = mediafileinfo_detect.get_string_fread_fskip(data)
    if expect_error:
      try:
        analyze_func(fread, info, fskip)
        raise AssertionError('ValueError expected but not raised.')
      except ValueError, e:
        info['error'] = str(e)
    else:
      analyze_func(fread, info, fskip)
      if info.get('format') is None:
        raise AssertionError('Format not populated in info.')
    if info.get('format') is not None and info.get('format') not in _format_db.formats:
      raise RuntimeError('Unknown format in info: %r' % (info.get('format'),))
    if detected_format != info.get('format'):
      info['detected_format'] = detected_format
  return info


class MediaFileInfoDetectTest(unittest.TestCase):
  maxDiff = None

  JP2_HEADER = '0000000c6a5020200d0a870a00000014667479706a703220000000006a7032200000002d6a703268000000166968647200000120000001600003080700000000000f636f6c7201000000000012'.decode('hex')
  HXS_HEADER = 'ITOLITLS\1\0\0\0\x28\0\0\0????????\xc1\x07\x90\nv@\xd3\x11\x87\x89\x00\x00\xf8\x10WT'

  def test_yield_swapped_bytes(self):
    f = mediafileinfo_detect.yield_swapped_bytes
    self.assertEqual('', ''.join(f('')))
    self.assertEqual('ab\0r', ''.join(f(buffer('bar'))))
    self.assertEqual('oWlr!d', ''.join(f(buffer('World!'))))

  def test_yield_uint14s(self):
    f = mediafileinfo_detect.yield_uint14s
    self.assertEqual((0x1fff, 0x2800, 0x600), tuple(f('\x1f\xff\xe8\x00\x06')))
    self.assertEqual((8191, 10240, 2032, 15485, 12445, 12288, 13544, 0), tuple(f('1fffe80007f0fc7df09df000f4e80000'.decode('hex'))))
    self.assertEqual((8191, 10240, 2032, 15485, 12445, 12288, 13544, 3), tuple(f('1fffe80007f0fc7df09df000f4e80003'.decode('hex'))))

  def test_yield_convert_unit14s_to_bytes(self):
    f = mediafileinfo_detect.yield_convert_uint14s_to_bytes
    self.assertEqual('', ''.join(f(())))
    self.assertEqual('\x7f\xfe\x80\x01\x80\x00', ''.join(f((0x1fff, 0x2800, 0x600))))
    self.assertEqual('7ffe8001fc3c7dc277000d3a0000', ''.join(f((8191, 10240, 2032, 15485, 12445, 12288, 13544, 0))).encode('hex'))
    self.assertEqual('7ffe8001fc3c7dc277000d3a0003', ''.join(f((8191, 10240, 2032, 15485, 12445, 12288, 13544, 3))).encode('hex'))

  def do_test_specs(self, try_match, too_short_msg, no_sig_msg):
    spec = (0, 'foo', 4, ('bar', 'baz'), 8, lambda header: (header[3] in ',+', 87))
    self.assertEqual(try_match(spec, 'foo,barBAZ'), 'foo,barB')
    self.assertEqual(try_match(spec, 'foo,barC'), 'foo,barC')
    self.assertEqual(try_match(spec, 'foo+barC'), 'foo+barC')
    self.assertEqual(try_match(spec, 'foo+bar'), 'foo+bar')
    self.assertEqual(try_match(spec, 'foo,ba'), too_short_msg)
    self.assertEqual(try_match(spec, 'foo,baRC'), no_sig_msg)  # 'bar' doesn't match.
    self.assertEqual(try_match(spec, 'Foo,barC'), no_sig_msg)  # 'foo' doesn't match.
    self.assertEqual(try_match(spec, 'foo;barC'), no_sig_msg)  # lambda doesn't match.

    spec = ((0, 'foo'), (1, 'bar'))
    self.assertEqual(try_match(spec, 'fo'), too_short_msg)
    self.assertEqual(try_match(spec, 'foo'), 'foo')
    self.assertEqual(try_match(spec, 'foo!'), 'foo!')
    self.assertEqual(try_match(spec, 'bar'), no_sig_msg)
    self.assertEqual(try_match(spec, 'bar!'), no_sig_msg)
    self.assertEqual(try_match(spec, '!bar'), '!bar')
    self.assertEqual(try_match(spec, '!baz'), no_sig_msg)

    spec = ((0, 'fo'), (1, 'oo'))
    self.assertEqual(try_match(spec, 'foo'), 'foo')  # Both alternatives match.

  def test_match_spec(self):
    def try_match_spec(spec, header):
      fread, unused_fskip = mediafileinfo_detect.get_string_fread_fskip(header)
      format, info = 'testformat', {}
      try:
        header2 = mediafileinfo_detect.match_spec(spec, fread, info, format)
        if info.get('format') != format:
          raise ValueError('Unexpected format: %r' % (info.get('format'),))
      except ValueError, e:
        return 'error: %s' % e
      return header2

    self.do_test_specs(try_match_spec, 'error: Too short for testformat.', 'error: testformat signature not found.')

  def test_format_db(self):
    """Double check that match_spec behaves the same way as FormatDb."""

    def try_format_db(spec, header, _cache=[(), ()]):
      format = 'testformat'
      if spec is _cache[0]:
        format_db = _cache[1]
      else:
        specs = spec
        if not isinstance(specs[0], tuple):
          specs = (specs,)
        format_db = mediafileinfo_formatdb.FormatDb(
            tuple((format, spec1) for spec1 in specs))
        _cache[0], _cache[1] = spec, format_db
      format2, header2 = format_db.detect(header)
      if format2 != format:
        return '?'
      return header2

    self.do_test_specs(try_format_db, '?', '?')

  def test_get_mpeg_video_track_info(self):
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_video_track_info('000001b31600f01502d020a4000001b8'.decode('hex')),
        {'codec': 'mpeg-1', 'height': 240, 'type': 'video', 'width': 352})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_video_track_info('000001b31600f01502d020a4000001b8'.decode('hex'), expect_mpeg4=False),
        {'codec': 'mpeg-1', 'height': 240, 'type': 'video', 'width': 352})
    try:
      mediafileinfo_detect.get_mpeg_video_track_info('000001b31600f01502d020a4000001b8'.decode('hex'), expect_mpeg4=True)
      self.fail('ValueError not raised.')
    except ValueError, e:
      self.assertEqual(str(e), 'mpeg-video mpeg-4 signature not found.')
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_video_track_info('000001b31600f01502d020a4000001'.decode('hex')),
        {'codec': 'mpeg', 'height': 240, 'type': 'video', 'width': 352})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_video_track_info('000001b31600f01502d020a400000001b8'.decode('hex')),
        {'codec': 'mpeg-1', 'height': 240, 'type': 'video', 'width': 352})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_video_track_info('000001b001000001b58913000001000000012000c48d8800cd0b04241443'.decode('hex')),
        {'codec': 'mpeg-4', 'height': 288, 'profile_level': 1, 'type': 'video', 'width': 352})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_video_track_info('000001b001000001b58913000001000000012000c48d8800cd0b04241443'.decode('hex'), expect_mpeg4=True),
        {'codec': 'mpeg-4', 'height': 288, 'profile_level': 1, 'type': 'video', 'width': 352})
    try:
      mediafileinfo_detect.get_mpeg_video_track_info('000001b001000001b58913000001000000012000c48d8800cd0b04241443'.decode('hex'), expect_mpeg4=False)
      self.fail('ValueError not raised.')
    except ValueError, e:
      self.assertEqual(str(e), 'mpeg-video signature not found.')
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_video_track_info('000001b0f3000001b509000001010000012002044007a85820f0a21f'.decode('hex'), expect_mpeg4=True),
        {'codec': 'mpeg-4', 'height': 240, 'profile_level': 243, 'type': 'video', 'width': 352})

  def test_analyze_mpeg_video(self):
    self.assertEqual(analyze_string('000001b31600f01502d020a4000001b8'.decode('hex')),
                     {'format': 'mpeg-video',
                      'tracks': [{'codec': 'mpeg-1', 'height': 240, 'type': 'video', 'width': 352}]})
    self.assertEqual(analyze_string('000001b32d01e0240a1e62f8000001b5'.decode('hex')),
                     {'format': 'mpeg-video',
                      'tracks': [{'width': 720, 'codec': 'mpeg-2', 'type': 'video', 'height': 480}]})
    self.assertEqual(analyze_string('000001b0f3000001b509000001010000012002044007a85820f0a21f'.decode('hex')),
                     {'format': 'mpeg-video',
                      'tracks': [{'codec': 'mpeg-4', 'height': 240, 'profile_level': 243, 'type': 'video', 'width': 352}]})

  def test_analyze_h264(self):
    self.assertEqual(analyze_string('0000000109f0000000016764000dacd9416096c044000003000400000300c83c50a658'.decode('hex')),
                     {'format': 'h264',
                      'tracks': [{'width': 352, 'codec': 'h264', 'type': 'video', 'height': 288}]})
    self.assertEqual(analyze_string('0000000109100000000127640028ad8811214820444843151e4c2a4c9d6a522092349d24733213948426528efe217b255d7aeb5531a4d75ebebf5fd7ebebfd7f4c05a044fdffe0008000620000258000075301d0c001e848000225515de5c686000f424000112a8aef2e1f088451600000000128ee040572c00000000106000d804752006876004752006876408000000000000106055617ee8c60f84d11d98cd60800200c'.decode('hex')),
                     {'format': 'h264',  # Contains io['profile'] == 100 and io['seq_scaling_matrix_present_flag'] == 1.
                      'tracks': [{'width': 1440, 'codec': 'h264', 'type': 'video', 'height': 1080}]})

  def test_analyze_h265(self):
    self.assertEqual(analyze_string('000000014601500000000140010c01ffff01600000030090000003000003003c9598090000000142010101600000030090000003000003003ca00b08048596566924caf010100000030010000003019080'.decode('hex')),
                     {'format': 'h265',
                      'tracks': [{'width': 352, 'codec': 'h265', 'type': 'video', 'height': 288}]})

  def test_get_mpeg_ts_es_track_info(self):
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_es_track_info('\0\0\1\xb3\x16\x01\x20\x13\xff\xff\xe0\x18\0\0\1\xb8', 0x01),
        {'width': 352, 'codec': 'mpeg-1', 'type': 'video', 'height': 288})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_es_track_info('0000000109f0000000016764000dacd9416096c044000003000400000300c83c50a658'.decode('hex'), 0x1b),
        {'width': 352, 'codec': 'h264', 'type': 'video', 'height': 288})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_es_track_info('0000000109100000000001274d40289a6280f0088fbc07d404040500000303e90000ea60e8c0004c4b0002faf2ef380a'.decode('hex'), 0x1b),
        {'width': 1920, 'codec': 'h264', 'type': 'video', 'height': 1080})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_es_track_info('000000014601500000000140010c01ffff01600000030090000003000003003c9598090000000142010101600000030090000003000003003ca00b08048596566924caf010100000030010000003019080'.decode('hex'), 0x24),
        {'width': 352, 'codec': 'h265', 'type': 'video', 'height': 288})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_es_track_info('ffd8ffe000104a46494600010200000100010000fffe00104c61766335382e35342e31303000ffdb0043000804040404040505050505050606060606060606060606060607070708080807070706060707080808080909090808080809090a0a0a0c0c0b0b0e0e0e111114ffc400b70000010501010000000000000000000000030504000201060701000203010101000000000000000000000201050304000607100001020404040306050203040903050102031222050400135232426272f0069214822307c2b2a21543e2f233d2246353731683082534261154171835944401d5a5a3845164369174110001030203050408050305010100000002120003042232054252627206130792f082a214152317b2c2d2e2433316115393f273019183514494ffc00011080120016003012200021100031100ffda000c03010002110311003f00f2aa4ee09e215092a35ea910e9155aba5ca482e2491729090d954eea9f612a979f311515c52214901212e12149c29ff684852e1b4b1289d7677517c572196d1524c3ef455c2e99e738cad6'.decode('hex'), 0x06),
        {'width': 352, 'codec': 'mjpeg', 'type': 'video', 'height': 288})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_es_track_info(self.JP2_HEADER, 0x06),
        {'width': 352, 'codec': 'mjpeg2000', 'type': 'video', 'height': 288})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_es_track_info(self.JP2_HEADER, 0x21),
        {'width': 352, 'codec': 'mjpeg2000', 'type': 'video', 'height': 288})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_es_track_info('0b7739181c30e1'.decode('hex'), 0x81),
        {'sample_size': 16, 'codec': 'ac3', 'sample_rate': 48000, 'channel_count': 5, 'type': 'audio'})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_es_track_info('7ffe8001fc3c7db0b700093b80'.decode('hex'), 0x82),
        {'channel_count': 2, 'codec': 'dts', 'sample_rate': 48000, 'sample_size': 20, 'type': 'audio'})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_es_track_info('7ffe8001fc3c7dc277000d3a00'.decode('hex'), 0x85),
        {'channel_count': 5, 'codec': 'dts', 'sample_rate': 48000, 'sample_size': 16, 'type': 'audio'})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_es_track_info('1fffe80007f0fc7df09df000f4e80003'.decode('hex'), 0x85),
        {'channel_count': 5, 'codec': 'dts', 'sample_rate': 48000, 'sample_size': 16, 'type': 'audio'})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_es_track_info('ff1f00e8f0077dfc9df000f0e8f40300'.decode('hex'), 0x85),
        {'channel_count': 5, 'codec': 'dts', 'sample_rate': 48000, 'sample_size': 16, 'type': 'audio'})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_es_track_info('7ffe8001fc7cdff0a2c05d3a00'.decode('hex'), 0x85),
        {'channel_count': 2, 'codec': 'dts', 'sample_rate': 44100, 'sample_size': 16, 'type': 'audio'})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_es_track_info('fe7f01803cfcc27d00773a5d00'.decode('hex'), 0x85),
        {'channel_count': 5, 'codec': 'dts', 'sample_rate': 48000, 'sample_size': 16, 'type': 'audio'})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_es_track_info('7ffe8001fc3c7dc277000d3a40'.decode('hex'), 0x85),
        {'channel_count': 5, 'codec': 'dts', 'sample_rate': 48000, 'sample_size': 16, 'type': 'audio'})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_es_track_info('7ffe8001fc3c3ed275e01d3a40'.decode('hex'), 0x85),
        {'channel_count': 5, 'codec': 'dts', 'sample_rate': 48000, 'sample_size': 16, 'type': 'audio'})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_es_track_info('7ffe8001fc3c7db277001d3a40'.decode('hex'), 0x85),
        {'channel_count': 5, 'codec': 'dts', 'sample_rate': 48000, 'sample_size': 16, 'type': 'audio'})

  def test_get_mpeg_ts_pes_track_info(self):
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_pes_track_info('000001e000008080052100018ca100000109100000000001274d40289a6280f0088fbc07d404040500000303e90000ea60e8c0004c4b0002faf2ef380a'.decode('hex'), 0x1b),
        {'width': 1920, 'codec': 'h264', 'type': 'video', 'height': 1080})
    self.assertEqual(
        mediafileinfo_detect.get_mpeg_ts_pes_track_info('000001bd06088080052100018ca10b7739181c30e1'.decode('hex'), 0x81),
        {'sample_size': 16, 'codec': 'ac3', 'sample_rate': 48000, 'channel_count': 5, 'type': 'audio'})
    try:
      mediafileinfo_detect.get_mpeg_ts_pes_track_info('000001bd06088080052100018ca1'.decode('hex'), 0x81)
      self.fail('ValueError not raised.')
    except ValueError, e:
      self.assertEqual(str(e), 'EOF after mpeg-ts pes payload pes header: empty es packet.')
    try:
      mediafileinfo_detect.get_mpeg_ts_pes_track_info('000001bd06088080052100018ca10b'.decode('hex'), 0x81)
      self.fail('ValueError not raised.')
    except ValueError, e:
      self.assertEqual(str(e), 'EOF in mpeg-ts pes es packet: Too short for ac3.')
    try:
      mediafileinfo_detect.get_mpeg_ts_pes_track_info('000001bd000a8080052100018ca10b77'.decode('hex'), 0x81)
      self.fail('ValueError not raised.')
    except ValueError, e:
      self.assertEqual(str(e), 'Too short for ac3.')
    try:
      mediafileinfo_detect.get_mpeg_ts_pes_track_info('000001bd00008080052100018ca10b77'.decode('hex'), 0x81)
      self.fail('ValueError not raised.')
    except ValueError, e:
      self.assertEqual(str(e),  'EOF in mpeg-ts pes es packet: Too short for ac3.')

  def test_parse_mpeg_ps_pat(self):
    self.assertEqual(
        mediafileinfo_detect.parse_mpeg_ts_pat(buffer('0000b00d0001c300000001e10076578e5fffffff'.decode('hex'))),
        [(256, 1)])

  def test_parse_mpeg_ps_pmt(self):
    self.assertEqual(
        mediafileinfo_detect.parse_mpeg_ts_pmt(buffer('0002b0230001c10000f011f0001bf011f00081f100f00c0a04656e6700050441432d334a1fa123ffff'.decode('hex')), 1),
        [(0x1011, 0x1b), (0x1100, 0x81)])

  def test_analyze_ape(self):
    self.assertEqual(
        analyze_string('4d414320960f00003400000018000000580000002c00000014c5db00000000000000000068e379c7c0d13d822b738a67144f4248a00f0000008004001c840200160000001000020044ac'.decode('hex')),
        {'format': 'ape',
         'tracks': [{'channel_count': 2, 'codec': 'ape',
                     'sample_rate': 44100, 'sample_size': 16, 'type': 'audio'}]})

  def test_analyze_pnm(self):
    self.assertEqual(analyze_string('P1#f oo\n #bar\r\t123\x0b\x0c456#'),
                     {'codec': 'uncompressed-ascii', 'format': 'pnm', 'subformat': 'pbm', 'height': 456, 'width': 123})

  def test_analyze_lbm(self):
    self.assertEqual(analyze_string('FORM\0\0\0\x4eILBMBMHD\0\0\0\x14'),
                     {'codec': 'rle', 'format': 'lbm', 'subformat': 'ilbm'})
    self.assertEqual(analyze_string('FORM\0\0\0\x4eILBMBMHD\0\0\0\x14\1\3\1\5'),
                     {'codec': 'rle', 'format': 'lbm', 'subformat': 'ilbm', 'height': 261, 'width': 259})
    self.assertEqual(analyze_string('FORM\0\0\0\x4ePBM BMHD\0\0\0\x14\1\3\1\5'),
                     {'codec': 'uncompressed', 'format': 'lbm', 'subformat': 'pbm', 'height': 261, 'width': 259})
    self.assertEqual(analyze_string('FORM\0\0\0\x4eACBMBMHD\0\0\0\x14\1\3\1\5'),
                     {'codec': 'uncompressed', 'format': 'lbm', 'subformat': 'acbm', 'height': 261, 'width': 259})

  def test_analyze_deep(self):
    self.assertEqual(analyze_string('FORM\0\0\0\x4eDEEPDGBL\0\0\0\x08'),
                     {'format': 'deep'})
    self.assertEqual(analyze_string('FORM\0\0\0\x4eDEEPDGBL\0\0\0\x08\2\1\2\4\0\3'),
                     {'format': 'deep', 'height': 516, 'width': 513, 'codec': 'dynamic-huffman'})

  def test_analyze_pcx(self):
    self.assertEqual(analyze_string('\n\5\1\x08\0\0\0\0\2\1\4\1'),
                     {'format': 'pcx', 'codec': 'rle', 'height': 261, 'width': 259})
    self.assertEqual(analyze_string('\n\4\0\x08\0\0\0\0\2\1\4\1'),
                     {'format': 'pcx', 'codec': 'uncompressed', 'height': 261, 'width': 259})

  def test_analyze_spider(self):
    def build_spider_header(width, height, iform=1, fmt='>'):
      # iform=1 means 2D.
      slice_count = 1  # It means image.
      d, = struct.unpack(fmt + 'f', '~~!@')  # Dummy.
      return struct.pack(fmt + '12f', slice_count, height, d, d, iform,
                         d, d, d, d, d, d, width)

    self.assertEqual(analyze_string(build_spider_header(width=5678, height=1234, fmt='>')),
                     {'format': 'spider', 'codec': 'uncompressed', 'height': 1234, 'width': 5678})
    self.assertEqual(analyze_string(build_spider_header(width=5678, height=1234, fmt='<')),
                     {'format': 'spider', 'codec': 'uncompressed', 'height': 1234, 'width': 5678})
    self.assertEqual(analyze_string(build_spider_header(width=5678, height=1234, iform=3, fmt='<')),
                     {'format': '?'})  # spider images with iform=3 are not detected.

  def test_analyze_dcx(self):
    data_pcx = '\n\5\1\x08\0\0\0\0\2\1\4\1'
    data1 = '\xb1\x68\xde\x3a\x10\0\0\0????\0\0\0\0' + data_pcx
    self.assertEqual(analyze_string(data1),
                     {'format': 'dcx', 'codec': 'rle', 'height': 261, 'width': 259})
    self.assertEqual(analyze_string(data1[:4]),
                     {'format': 'dcx', 'codec': 'rle'})

  def test_analyze_xcf(self):
    self.assertEqual(analyze_string('gimp xcf v001\0\0\0\1\x0d\0\0\1\7'),
                     {'format': 'xcf', 'width': 269, 'height': 263})

  def test_analyze_psd(self):
    self.assertEqual(analyze_string('8BPS\0\1\0\0\0\0\0\0\0\1\0\0\1\5\0\0\1\3\0\1\0\0'),
                     {'format': 'psd', 'width': 259, 'height': 261})

  def test_analyze_tiff(self):
    self.assertEqual(analyze_string('49492a001600000078da5bc0f080210100062501e10011000001030001000000345600000101030001000000452300000201030001000000010000000301030001000000080000000601030001000000010000000a01030001000000010000000d0102000b000000f800000011010400010000000800000012010300010000000100000015010300010000000100000016010300010000000500000017010400010000000d0000001a01050001000000e80000001b01050001000000f00000001c0103000100000001000000280103000100000001000000290103000200000000000100'.decode('hex')),
                     {'format': 'tiff', 'width': 0x5634, 'height': 0x2345, 'codec': 'zip'})

  def test_analyze_tga(self):
    self.assertEqual(analyze_string('000002000000000000000000030105010800'.decode('hex')),
                     {'format': 'tga', 'width': 259, 'height': 261, 'codec': 'uncompressed'})
    self.assertEqual(analyze_string('000003000000000000000000030105010f00'.decode('hex')),
                     {'format': 'tga', 'width': 259, 'height': 261, 'codec': 'uncompressed'})

  def test_analyze_ps(self):
    data_preview = '\xc5\xd0\xd3\xc6 \0\0\0\x79\x69\7\0\0\0\0\0\0\0\0\0\x99\x69\7\0\xfd\x66\4\0\xff\xff\0\0'
    data_line1 = '%!PS-Adobe-3.0\tEPSF-3.0\r\n'
    data_more = '%%Creator: (ImageMagick)\n%%Title:\t(image.eps2)\r\n%%CreationDate: (2019-10-22T21:27:41+02:00)\n%%BoundingBox:\t-1 -0.8\t \t34 56.2\r\n%%HiResBoundingBox: 0\t0\t3 5\r%%LanguageLevel:\t2\r%%Pages: 1\r%%EndComments\nuserdict begin end'
    data_mps = '%!PS\n%%BoundingBox: 10 20 31 40\n'
    self.assertEqual(analyze_string(data_preview),
                     {'format': 'ps', 'subformat': 'preview', 'has_preview': True})
    self.assertEqual(analyze_string(data_line1),
                     {'format': 'ps', 'subformat': 'eps', 'has_preview': False})
    self.assertEqual(analyze_string(data_line1 + data_more),
                     {'format': 'ps', 'subformat': 'eps', 'has_preview': False, 'height': 57, 'width': 35})
    self.assertEqual(analyze_string(data_preview + data_line1 + data_more),
                     {'format': 'ps', 'subformat': 'eps', 'has_preview': True, 'height': 57, 'width': 35})
    self.assertEqual(analyze_string(data_mps),
                     {'format': 'ps', 'subformat': 'mps', 'has_preview': False, 'height': 20, 'width': 21})
    self.assertEqual(analyze_string(data_mps.replace('\n', '\r\n')),
                     {'format': 'ps', 'subformat': 'mps', 'has_preview': False, 'height': 20, 'width': 21})

  def test_analyze_jpeg2000(self):
    expected = {'format': 'jp2', 'bpc': 8, 'brands': ['jp2 '], 'codec': 'jpeg2000', 'component_count': 3, 'has_early_mdat': False, 'height': 288, 'minor_version': 0, 'subformat': 'jp2', 'tracks': [], 'width': 352}
    expected2 = dict(expected, detected_format='mov')
    expected3 = dict(expected2, detected_format='mov', detected_analyze=mediafileinfo_detect.analyze_mov)
    self.assertEqual(analyze_string(self.JP2_HEADER, analyze_func=mediafileinfo_detect.analyze_mov), expected2)
    self.assertEqual(analyze_string(self.JP2_HEADER), expected2)
    self.assertEqual(analyze_string(self.JP2_HEADER, analyze_func=mediafileinfo_detect.noformat_analyze_jpeg2000), expected3)
    data1 = '\xff\x4f\xff\x51\0\x29'
    data2 = '\xff\x4f\xff\x51\0\x2f\0\0\0\0\2\3\0\0\2\1\0\0\0\0\0\0\0\0'
    self.assertEqual(analyze_string(data1),
                     {'format': 'jpc', 'codec': 'jpeg2000'})
    expected = {'format': 'jpc', 'codec': 'jpeg2000', 'height': 513, 'width': 515}
    expected2 = dict(expected, detected_analyze=mediafileinfo_detect.analyze_jpc)
    self.assertEqual(analyze_string(data2, analyze_func=mediafileinfo_detect.analyze_jpc), expected)
    self.assertEqual(analyze_string(data2, analyze_func=mediafileinfo_detect.noformat_analyze_jpeg2000), expected2)

  def test_analyze_pnot(self):
    self.assertEqual(analyze_string('\0\0\0\x14pnot\1\2\3\4\0\0PICT\0\1\0\0\0\x0aPICT..' + self.JP2_HEADER),
                     {'format': 'jp2', 'detected_format': 'pnot', 'bpc': 8, 'brands': ['jp2 '], 'codec': 'jpeg2000', 'component_count': 3, 'has_early_mdat': False, 'height': 288, 'minor_version': 0, 'subformat': 'jp2', 'tracks': [], 'width': 352})

  def test_analyze_swf(self):
    self.assertEqual(analyze_string('FWS\n4\x07\x01\x00x\x00\x05_\x00\x00\x1f@\x00\x00\x18'),
                     {'codec': 'uncompressed', 'format': 'swf', 'height': 800, 'width': 550})
    self.assertEqual(analyze_string('FWS 4\x07\x01\x00p\x00\x0f\xa0\x00\x00\x8c\xa0\x00'),
                     {'codec': 'uncompressed', 'format': 'swf', 'height': 225, 'width': 400})

  def test_analyze_miff(self):
    self.assertEqual(analyze_string('id=ImageMagick\rrows=42\t \fcolumns=137:\x1arows=111'),
                     {'codec': 'uncompressed', 'format': 'miff', 'height': 42, 'width': 137})
    self.assertEqual(analyze_string('id=ImageMagick\rrows=42\t \fcolumns=137\ncompression=BZip:\x1arows=111'),
                     {'codec': 'bzip2', 'format': 'miff', 'height': 42, 'width': 137})

  def test_analyze_jbig2(self):
    self.assertEqual(analyze_string('\x97JB2\r\n\x1a\n\1\0\0\0\1\0\0\0\x000\0\1\0\0\0\x13\0\0\1\xa3\0\0\2\x16\0\0\0\0\0\0\0\0\1\0\0'),
                     {'codec': 'jbig2', 'format': 'jbig2', 'height': 534, 'width': 419, 'subformat': 'jbig2'})
    self.assertEqual(analyze_string('\0\0\0\x000\0\1\0\0\0\x13\0\0\1\xa3\0\0\2\x16\0\0\0\0\0\0\0\0\1\0\0'),
                     {'codec': 'jbig2', 'format': 'jbig2', 'height': 534, 'width': 419, 'subformat': 'pdf'})

  def test_analyze_djvu(self):
    self.assertEqual(analyze_string('AT&TFORM\0\0\x19bDJVUINFO\0\0\0\n\t\xf6\x0c\xe4'),
                     {'format': 'djvu', 'height': 3300, 'width': 2550, 'subformat': 'djvu'})
    self.assertEqual(analyze_string('AT&TFORM\0\0\1\0DJVMDIRM\0\0\0\5.....NAVM\0\0\0\6......FORM\0\0\0\7DJVI...FORM\0\0\0\4DJVUINFO\0\0\0\4\t\xf6\x0c\xe4'),
                     {'format': 'djvu', 'height': 3300, 'width': 2550, 'subformat': 'djvm'})

  def test_analyze_art(self):
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0'),
                     {'format': 'art', 'codec': 'art'})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\8\0\x40\x15\3\xdd\1\xe0\1'),  # Unrecognized header bytes.
                     {'format': 'art', 'codec': 'art'})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\7\0\x40\x15\3\xdd\1\xe0\1'),
                     {'format': 'art', 'codec': 'art', 'height': 480, 'width': 477})
    self.assertEqual(analyze_string('JG\3\x0e\0\0\0\4\x8e\x02\n\0\xeb\0\xd7\0'),
                     {'format': 'art', 'codec': 'art', 'height': 235, 'width': 215})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\7\0\x40\x15 \xd0\2\x40\2'),
                     {'format': 'art', 'codec': 'art', 'height': 576, 'width': 720})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\7\0\x40\x15\3\0\x05\xc0\x03'),
                     {'format': 'art', 'codec': 'art', 'height': 960, 'width': 1280})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\7\0\x40\x15\3\t\1\x93\1'),
                     {'format': 'art', 'codec': 'art', 'height': 403, 'width': 265})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\7\0\x40\x15\3\x7f\x02\xf4\0'),
                     {'format': 'art', 'codec': 'art', 'height': 244, 'width': 639})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\7\0\x40\x15\3\x80\x02\xe0\1'),
                     {'format': 'art', 'codec': 'art', 'height': 480, 'width': 640})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\7\0\x40\x15\3\x88\x01J\x02'),
                     {'format': 'art', 'codec': 'art', 'height': 586, 'width': 392})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\7\0\x40\x15\3\x90\1\xf0\0'),
                     {'format': 'art', 'codec': 'art', 'height': 240, 'width': 400})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\7\0\x40\x15\3\xa0\0\xbe\0'),
                     {'format': 'art', 'codec': 'art', 'height': 190, 'width': 160})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\7\0\x40\x15\3\xd2\0\xd2\0'),
                     {'format': 'art', 'codec': 'art', 'height': 210, 'width': 210})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\7\0\x40\x15\3\xd8\0\xa2\0'),
                     {'format': 'art', 'codec': 'art', 'height': 162, 'width': 216})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\7\0\x40\x15\3\xdc\0\xa8\0'),
                     {'format': 'art', 'codec': 'art', 'height': 168, 'width': 220})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\7\0\x40\x15\3\xf3\0\xe3\0'),
                     {'format': 'art', 'codec': 'art', 'height': 227, 'width': 243})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\7\0\x40\x15\3\xfa\0\xa6\0'),
                     {'format': 'art', 'codec': 'art', 'height': 166, 'width': 250})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\7\0\x40\x15\x03e\x03U\x02'),
                     {'format': 'art', 'codec': 'art', 'height': 597, 'width': 869})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\7\0\x40\x15\x03j\x03L\x02'),
                     {'format': 'art', 'codec': 'art', 'height': 588, 'width': 874})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\7\0\x40\x15\x03~\x02\x1d\1'),
                     {'format': 'art', 'codec': 'art', 'height': 285, 'width': 638})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\x8c\x16\0\0\xb8\1\xd8\1'),
                     {'format': 'art', 'codec': 'art', 'height': 440, 'width': 472})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\x8c\x16\0\x00F\1\xd8\1'),
                     {'format': 'art', 'codec': 'art', 'height': 326, 'width': 472})
    self.assertEqual(analyze_string('JG\4\x0e\0\0\0\0\x8c\x16\0\x00}\x02\x8c\2'),
                     {'format': 'art', 'codec': 'art', 'height': 637, 'width': 652})

  def test_analyze_ico(self):
    self.assertEqual(analyze_string('\0\0\1\0\1\0\x30\x31\0\0\1\0\x20\0\xa8\x25\0\0\x16\0\0\0'),
                     {'format': 'ico', 'height': 49, 'width': 48})
    self.assertEqual(analyze_string('\0\0\1\0\1\0\x30\x31\0\0\1\0\x20\0\xa8\x25\0\0\x17\0\0\0-(\0\0\0\x30\0\0\0\x62\0\0\0????\3\0\0\0'),
                     {'format': 'ico', 'subformat': 'bmp', 'codec': 'bitfields', 'height': 49, 'width': 48})
    self.assertEqual(analyze_string('\0\0\1\0\1\0\x30\x31\0\0\1\0\x20\0\xa8\x25\0\0\x18\0\0\0--\x89PNG????????IHDR????'),
                     {'format': 'ico', 'subformat': 'png', 'codec': 'flate', 'height': 49, 'width': 48})

  def test_analyze_cur(self):
    self.assertEqual(analyze_string('\0\0\2\0\1\0\x30\x31\0\0\1\0\x20\0\xa8\x25\0\0\x16\0\0\0'),
                     {'format': 'cur', 'height': 49, 'width': 48})

  def test_analyze_webp(self):
    self.assertEqual(analyze_string('524946466876000057454250565038205c760000d2be019d012a26027001'.decode('hex')),
                     {'codec': 'vp8', 'format': 'webp', 'height': 368, 'width': 550})
    self.assertEqual(analyze_string('RIFF\x7c\x3e\0\0WEBPVP8X\x0a\0\0\0\x18\0\0\0\2\2\0\0\2\0'),
                     {'format': 'webp', 'height': 513, 'width': 515, 'subformat': 'extended'})
    self.assertEqual(analyze_string('524946460e6c0000574542505650384c026c00002f8181621078'.decode('hex')),
                     {'codec': 'webp-lossless', 'format': 'webp', 'height': 395, 'width': 386})

  def test_analyze_vp8(self):
    self.assertEqual(analyze_string('d2be019d012a26027001'.decode('hex')),
                     {'format': 'vp8', 'tracks': [{'codec': 'vp8', 'height': 368, 'type': 'video', 'width': 550}]})

  def test_analyze_vp9(self):
    self.assertEqual(analyze_string('824983420031f0314600'.decode('hex')),
                     {'format': 'vp9', 'tracks': [{'codec': 'vp9', 'height': 789, 'type': 'video', 'width': 800}]})

  def test_analyze_av1(self):
    self.assertEqual(analyze_string('\x12\0\x0a\4'),
                     {'format': 'av1', 'tracks': [{'codec': 'av1', 'type': 'video'}]})
    self.assertEqual(analyze_string('\x12\0\x0a\4\x18\0\x10'),
                     {'format': 'av1', 'tracks': [{'codec': 'av1', 'height': 2, 'type': 'video', 'width': 1}]})
    self.assertEqual(analyze_string('\x12\0\x0a\x0b\0\0\0\x24\xce\x3f\x8f\xbf'),
                     {'format': 'av1', 'tracks': [{'codec': 'av1', 'height': 800, 'type': 'video', 'width': 800}]})

  def test_analyze_jpegxr(self):
    self.assertEqual(analyze_string('4949bc012000000024c3dd6f034efe4bb1853d77768dc90c0000000000000000080001bc0100100000000800000002bc0400010000000000000080bc040001000000a005000081bc0400010000006400000082bc0b00010000009af78f4283bc0b00010000009af78f42c0bc04000100000086000000c1bc040001000000369b0200'.decode('hex')),
                     {'codec': 'jpegxr', 'format': 'jpegxr', 'subformat': 'tagged', 'height': 100, 'width': 1440})
    self.assertEqual(analyze_string('WMPHOTO\0\x11\x45\xc0\x71\x05\x9f\x00\x63'),
                     {'codec': 'jpegxr', 'format': 'jpegxr', 'subformat': 'coded', 'height': 100, 'width': 1440})

  def test_analyze_flif(self):
    self.assertEqual(analyze_string('FLIF\x441\x83\x7f\x83\x7e'),
                     {'format': 'flif', 'codec': 'flif', 'width': 512, 'height': 511, 'component_count': 4, 'bpc': 8})

  def test_analyze_bpg(self):
    self.assertEqual(analyze_string('BPG\xfb\x20\x00\x8b\x1c\x85\x5a'),
                     {'format': 'bpg', 'codec': 'h265', 'width': 1436, 'height': 730})

  def test_parse_isobmff_ipma_box(self):
    self.assertEqual(mediafileinfo_detect.parse_isobmff_ipma_box(0, 0, '\x00\x00\x00\x02\x03\xea\x02\x81\x02\x03\xed\x02\x83\x04'),
                     {1002: [0, 1], 1005: [2, 3]})
    self.assertEqual(mediafileinfo_detect.parse_isobmff_ipma_box(0, 0, '\x00\x00\x00\x01\x00\x01\x03\x01\x02\x83'),
                     {1: [0, 1, 2]})

  def test_parse_isobmff_infe_box(self):
    self.assertEqual(mediafileinfo_detect.parse_isobmff_infe_box(2, 0, '\x03\xea\x00\x00hvc1HEVC Image\x00'),
                     {1002: (0, 'hvc1')})
    self.assertEqual(mediafileinfo_detect.parse_isobmff_infe_box(2, 0, '\x00\x01\x00\x00av01Image\x00'),
                     {1: (0, 'av01')})

  def test_analyze_isobmff_image(self):
    self.assertEqual(analyze_string('00000018667479706d696631000000006d69663168656963000001fe6d657461000000000000002168646c72000000000000000070696374000000000000000000000000000000000e7069746d0000000003ea00000034696c6f63000000004440000203ea00000000021600010000000800046a8003ed000000000216000100046a8800000e4a0000004c69696e660000000000020000001f696e66650200000003ea0000687663314845564320496d616765000000001f696e66650200000003ed0000687663314845564320496d616765000000001a69726566000000000000000e74686d6203ed000103ea0000012969707270000001076970636f0000006c68766343010160000000000000000000baf000fcfdf8f800000f03a00001001840010c01ffff016000000300000300000300000300baf024a10001001f420101016000000300000300000300000300baa002d0803c1fe5f9246d9ed9a2000100074401c190958112000000146973706500000000000005a0000003c00000006b68766343010160000000000000000000baf000fcfdf8f800000f03a00001001840010c01ffff016000000300000300000300000300baf024a10001001e420101016000000300000300000300000300baa01e20287f97e491b67b64a2000100074401c190958112000000146973706500000000000000f0000000a00000001a69706d61000000000000000203ea02810203ed028304000478d26d646174'.decode('hex')),
                     {'format': 'isobmff-image', 'detected_format': 'mov', 'brands': ['heic', 'mif1'], 'codec': 'h265', 'has_early_mdat': False, 'height': 960, 'minor_version': 0, 'subformat': 'heif', 'width': 1440})
    self.assertEqual(analyze_string('0000001c667479706d696631000000006d696631617669666d696166000000096d64617400000000536672656549736f4d656469612046696c652050726f64756365642077697468204750414320302e372e322d4445562d7265763935382d673564646439643163652d6769746875625f6d617374657200000000f56d657461000000000000003268646c720000000000000000706963740000000000000000000000004750414320706963742048616e646c6572000000000e7069746d0000000000010000001e696c6f630000000004400001000100000000002c00010000a42a0000002869696e660000000000010000001a696e6665020000000001000061763031496d616765000000006369707270000000456970636f00000014697370650000000000000500000002d000000010706173700000000100000001000000196176314381054c000a0b0000002d4cffb3dfff9c0c0000001669706d610000000000000001000103010283'.decode('hex')),
                     {'format': 'isobmff-image', 'detected_format': 'mov', 'brands': ['avif', 'miaf', 'mif1'], 'codec': 'av1', 'has_early_mdat': True, 'height': 720, 'minor_version': 0, 'subformat': 'avif', 'width': 1280})

  def test_analyze_png(self):
    data1 = '\x89PNG\r\n\x1a\n\0\0\0\rIHDR\0\0\5\1\0\0\3\2'
    data2 = data1 + '\x08\3\0\0\0????' '\0\0\0\x08acTL\0\0\0\x28\0\0\0\0????'
    self.assertEqual(analyze_string(data1),
                     {'format': 'png', 'codec': 'flate', 'width': 1281, 'height': 770})
    self.assertEqual(analyze_string(data2),
                     {'format': 'apng', 'detected_format': 'png', 'codec': 'flate', 'width': 1281, 'height': 770})
    self.assertEqual(analyze_string('\x89PNG\r\n\x1a\n\0\0\0\4CgBI\x50\0\x20\6\x2c\xb8\x77\x66' + data1[8:]),
                     {'format': 'png', 'subformat': 'apple', 'codec': 'flate', 'width': 1281, 'height': 770})

  def test_analyze_jng(self):
    self.assertEqual(analyze_string('\x8bJNG\r\n\x1a\n\0\0\0\rJHDR\0\0\5\1\0\0\3\2'),
                     {'format': 'jng', 'codec': 'jpeg', 'width': 1281, 'height': 770})

  def test_analyze_lepton(self):
    self.assertEqual(analyze_string('\xcf\x84\1Y'),
                     {'format': 'lepton', 'codec': 'lepton'})
    self.assertEqual(analyze_string('\xcf\x84\2Z'),
                     {'format': 'lepton', 'codec': 'lepton'})
    self.assertEqual(analyze_string('\xcf\x84\1X'),
                     {'format': 'lepton', 'codec': 'lepton'})

  def test_analyze_fuji_raf(self):
    self.assertEqual(analyze_string('FUJIFILMCCD-RAW 0200FF383501'),
                     {'format': 'fuji-raf', 'codec': 'raw'})
    self.assertEqual(analyze_string('FUJIFILMCCD-RAW 0201FF383501'),
                     {'format': 'fuji-raf', 'codec': 'raw'})

  def test_analyze_mng(self):
    self.assertEqual(analyze_string('\x8aMNG\r\n\x1a\n\0\0\0\rMHDR\0\0\5\1\0\0\3\2'),
                     {'format': 'mng', 'tracks': [{'codec': 'jpeg+png', 'width': 1281, 'height': 770}]})

  def test_analyze_mpeg_adts(self):
    self.assertEqual(analyze_string('\xff\xfb\x90\xc4'),
                     {'format': 'mp3', 'detected_format': 'mpeg-adts',
                      'tracks': [{'channel_count': 1, 'sample_size': 16, 'subformat': 'mpeg-1', 'codec': 'mp3', 'sample_rate': 44100, 'type': 'audio'}]})
    self.assertEqual(analyze_string('\xff\xfd\xb4\0'),
                     {'format': 'mpeg-adts',
                      'tracks': [{'channel_count': 2, 'sample_size': 16, 'subformat': 'mpeg-1', 'codec': 'mp2', 'sample_rate': 48000, 'type': 'audio'}]})
    self.assertEqual(analyze_string('\xff\xf9\x2c\x40'),
                     {'format': 'mpeg-adts',
                      'tracks': [{'channel_count': 1, 'sample_size': 16, 'subformat': 'mpeg-4', 'codec': 'aac', 'sample_rate': 8000, 'type': 'audio'}]})
    self.assertEqual(analyze_string('\xff\xf1P\x80'),
                     {'format': 'mpeg-adts',
                      'tracks': [{'channel_count': 2, 'sample_size': 16, 'subformat': 'mpeg-4', 'codec': 'aac', 'sample_rate': 44100, 'type': 'audio'}]})

  def test_analyze_id3v2(self):
    data = 'ID3\3\0\0\0\0\x03*TRCK\0\0\0\1\0\0\x00TENC\0\0\0\x01@\0\x00WXXX\0\0\0\x02\0\0\0\x00TCOP\0\0\0\1\0\0\x00TOPE\0\0\0\1\0\0\x00TCOM\0\0\0\1\0\0\x00COMM\0\0\0\x05\0\0\0\x00C\x93\x00TCON\0\0\0\1\0\0\x00TYER\0\0\0\1\0\0\x00TALB\0\0\0\x0c\0\0\x00MYALBUBNAMETPE1\0\0\0\x0c\0\0\0\xd6kr\xf6s FoobaTIT2\0\0\0\1' + '\0' * 270
    mp3_header = '\xff\xfb0L'
    self.assertEqual(analyze_string(''.join((data, mp3_header))),
                     {'format': 'mp3', 'detected_format': 'id3v2', 'id3_version': '2.3.0',
                      'tracks': [{'channel_count': 2, 'sample_size': 16, 'subformat': 'mpeg-1', 'codec': 'mp3', 'sample_rate': 44100, 'type': 'audio'}]})
    self.assertEqual(analyze_string(''.join((data, '\xff\0\0\0', mp3_header))),
                     {'format': 'mp3', 'detected_format': 'id3v2', 'id3_version': '2.3.0',
                      'tracks': [{'channel_count': 2, 'sample_size': 16, 'subformat': 'mpeg-1', 'codec': 'mp3', 'sample_rate': 44100, 'type': 'audio'}]})
    self.assertEqual(analyze_string(''.join((data, '\xff\0\0\0\0', mp3_header))),
                     {'format': 'mp3', 'detected_format': 'id3v2', 'id3_version': '2.3.0',
                      'tracks': [{'channel_count': 2, 'sample_size': 16, 'subformat': 'mpeg-1', 'codec': 'mp3', 'sample_rate': 44100, 'type': 'audio'}]})
    self.assertEqual(analyze_string(''.join((data, '\0\0\0\0\0', mp3_header))),
                     {'format': 'mp3', 'detected_format': 'id3v2', 'id3_version': '2.3.0',
                      'tracks': [{'channel_count': 2, 'sample_size': 16, 'subformat': 'mpeg-1', 'codec': 'mp3', 'sample_rate': 44100, 'type': 'audio'}]})

  def test_analyze_dirac(self):
    self.assertEqual(analyze_string('BBCD\0\0\0\0\x12\0\0\0\0\x6c\x1c\x1a'),
                     {'format': 'dirac', 'tracks': [{'type': 'video', 'codec': 'dirac', 'width': 720, 'height': 576}]})

  def test_analyze_theora(self):
    self.assertEqual(analyze_string('\x80theora\x03\2\0\0\x14\0\x0f\0\x01@\0\0\xf0\0\0\0\0\0\x1e\0\0\0\1\0\0\0\0\0\0\1\0\0\x00e\x00'),
                     {'format': 'theora', 'tracks': [{'type': 'video', 'codec': 'theora', 'width': 320, 'height': 240}]})

  def test_analyze_daala(self):
    self.assertEqual(analyze_string('\x80daala\0\0\0\0\0\1\2\0\0\3\4'),
                     {'format': 'daala', 'tracks': [{'type': 'video', 'codec': 'daala', 'width': 258, 'height': 772}]})

  def test_analyze_vorbis(self):
    self.assertEqual(analyze_string('\x01vorbis\0\0\0\0\x01D\xac\0\0'),
                     {'format': 'vorbis', 'tracks': [{'type': 'audio', 'codec': 'vorbis', 'channel_count': 1, 'sample_rate': 44100, 'sample_size': 16}]})
    self.assertEqual(analyze_string('\x01vorbis\0\0\0\0\x01"V\0\0'),
                     {'format': 'vorbis', 'tracks': [{'type': 'audio', 'codec': 'vorbis', 'channel_count': 1, 'sample_rate': 22050, 'sample_size': 16}]})

  def test_analyze_oggpcm(self):
    self.assertEqual(analyze_string('PCM     \0\0\0\0\0\0\0\x10\0\0\xbb\x80\x00\x02'),
                     {'format': 'oggpcm', 'tracks': [{'type': 'audio', 'codec': 'mulaw', 'channel_count': 2, 'sample_rate': 48000, 'sample_size': 8}]})
    self.assertEqual(analyze_string('PCM     \0\0\0\4\0\0\0\x20\0\0\xac\x44\x00\x01'),
                     {'format': 'oggpcm', 'tracks': [{'type': 'audio', 'codec': 'float', 'channel_count': 1, 'sample_rate': 44100, 'sample_size': 32}]})

  def test_analyze_opus(self):
    self.assertEqual(analyze_string('OpusHead\1\x02d\x01D\xac\0\0'),
                     {'format': 'opus', 'tracks': [{'type': 'audio', 'codec': 'opus', 'channel_count': 2, 'sample_rate': 44100, 'sample_size': 16}]})

  def test_analyze_speex(self):
    self.assertEqual(analyze_string('Speex   1.0.4\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\1\0\0\x00P\0\0\0\x80\xbb\0\0\x02\0\0\0\x04\0\0\0\1\0\0\0'),
                     {'format': 'speex', 'tracks': [{'type': 'audio', 'codec': 'speex', 'channel_count': 1, 'sample_rate': 48000, 'sample_size': 16}]})

  def test_analyze_ogg(self):
    self.assertEqual(analyze_string('OggS\0\2????????SSSS\0\0\0\0CCCC\1' '\1?'), {'format': 'ogg', 'tracks': []})
    self.assertEqual(analyze_string('4f67675300020000000000000000f6c8465100000000eb0c16bd012a807468656f72610302000014000f0001400000f000000000001e000000010000000000000100000065004f676753000200000000000000002c36d36d00000000dbc8fb60011e01766f72626973000000000122560000fffffffff0550000ffffffffaa01'.decode('hex')),
                     {'format': 'ogg', 'tracks': [{'codec': 'theora', 'height': 240, 'type': 'video', 'width': 320}, {'channel_count': 1, 'codec': 'vorbis', 'sample_rate': 22050, 'sample_size': 16, 'type': 'audio'}]})
    self.assertEqual(analyze_string('4f6767530002000000000000000063bb451200000000f480dc43011e01766f72626973000000000144ac0000000000008038010000000000b8014f6767530000000000000000000063bb45120100000087abaad202030461626364656667'.decode('hex')),
                     {'format': 'ogg', 'tracks': [{'channel_count': 1, 'codec': 'vorbis', 'sample_rate': 44100, 'sample_size': 16, 'type': 'audio'}]})

  def test_analyze_yuv4mpeg2(self):
    self.assertEqual(analyze_string('YUV4MPEG2 W384 H288 F25:1 Ip A0:0\nFRAME\n'),
                     {'format': 'yuv4mpeg2', 'tracks': [{'type': 'video', 'codec': 'uncompressed', 'width': 384, 'height': 288, 'colorspace': '420jpeg', 'subformat': 'yuv4mpeg2'}]})

  def test_analyze_realaudio(self):
    self.assertEqual(analyze_string('.ra\xfd\0\3\0\x3a\0\1'),
                     {'format': 'realaudio', 'tracks': [{'type': 'audio', 'codec': 'vslp-ra1', 'channel_count': 1, 'sample_rate': 8000, 'sample_size': 16, 'subformat': 'ra3'}]})
    self.assertEqual(analyze_string('.ra\xfd\0\x04\0\x00.ra4\0\1\x16\x1c\0\x04\0\0\x009\0\x02\0\0\x00&\0\1\x15\xe0\0\1\xbdP\0\1\xbdP\0\x0c\0\xe4\0\0\0\0\x1f@\0\0\0\x10\0\1\x04Int4\x0428_8'),
                     {'format': 'realaudio', 'tracks': [{'type': 'audio', 'codec': 'ld-celp-ra2', 'channel_count': 1, 'sample_rate': 8000, 'sample_size': 16, 'subformat': 'ra4'}]})
    self.assertEqual(analyze_string('.ra\xfd\0\x05\0\x00.ra5\0\0\0\0\0\x05\0\0\x00F\0\x08\0\0\x01 \0\0\x1b\0\0\0\xaf\xc8\0\0\xaf\xc8\0\x06\x01 \0\x18\0\0\0\0\x1f@\0\0\x1f@\0\0\0\x10\0\x01genrcook'),
                     {'format': 'realaudio', 'tracks': [{'type': 'audio', 'codec': 'cook', 'channel_count': 1, 'sample_rate': 8000, 'sample_size': 16, 'subformat': 'ra5'}]})

  def test_analyze_realvideo(self):
    self.assertEqual(analyze_string('\0\0\0\x20VIDORV20\0\xb0\x00p'),
                     {'format': 'realvideo', 'tracks': [{'type': 'video', 'codec': 'h263+-rv20', 'width': 176, 'height': 112}]})
    self.assertEqual(analyze_string('VIDORV20\0\xb0\x00p'),
                     {'format': 'realvideo', 'tracks': [{'type': 'video', 'codec': 'h263+-rv20', 'width': 176, 'height': 112}]})

  def test_analyze_ralf(self):
    self.assertEqual(analyze_string('LSD:\1\3\0\0\0\2\0\x10\0\0\xacD'),
                     {'format': 'ralf', 'tracks': [{'type': 'audio', 'codec': 'ralf', 'channel_count': 2, 'sample_rate': 44100, 'sample_size': 16}]})

  def test_analyze_realmedia(self):
    self.assertEqual(analyze_string('2e524d46000000120000000000000000000650524f5000000032000000036ee700036ee7000003fe0000031b00019b90002b939e00000e8204d85593000001a700020000434f4e5400000043000000205469636b6c652048656c6c204d6f766965206f6620546865205765656b206200000c5469636b6c652048656c6c000005a93230303400004d445052000000ac000000000000ac440000ac4400000280000002800000000000000e82002b94580c417564696f2053747265616d14617564696f2f782d706e2d7265616c617564696f0000005e2e7261fd000500002e726135660561c700050000004e0016000002800127f00000050bfe00050bfe00100280008000000000ac440000ac4400000010000267656e72636f6f6b0102000000000010010000030800002000000000000500054d44505200000074000000010002c2a30002c2a3000003fe0000031b0000000000000c33002b93ad0c566964656f2053747265616d14766964656f2f782d706e2d7265616c766964656f00000026000000265649444f52563330014000f0000c00000000001df854010a9030302020023c2c2820444154410542480b'.decode('hex')),
                     {'format': 'realmedia',
                      'tracks': [{'channel_count': 2, 'codec': 'cook', 'sample_rate': 44100, 'sample_size': 16, 'subformat': 'ra5', 'type': 'audio'},
                                 {'codec': 'h264-rv30', 'height': 240, 'type': 'video', 'width': 320}]})

  def test_analyze_flic(self):
    self.assertEqual(analyze_string('????\x11\xaf??\3\2\1\2\x08\0\3\0'),
                     {'format': 'flic', 'subformat': 'fli',
                      'tracks': [{'codec': 'rle', 'height': 513, 'type': 'video', 'width': 515}]}),
    self.assertEqual(analyze_string('????\x12\xaf??\3\2\1\2\x08\0\0\0'),
                     {'format': 'flic', 'subformat': 'flc',
                      'tracks': [{'codec': 'rle', 'height': 513, 'type': 'video', 'width': 515}]}),

  def test_analyze_xml(self):
    data1 = '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
    data2 = '<?xml\t\fencoding="UTF-8" standalone="no"?>'
    data3 = '<?xml\v\rstandalone="no"?>'
    data4 = '<?xml\v\r?>'
    data5 = '<?xml?>'
    data6 = '<!----><!-- hello\n-\r--\n->-\t>-->\t\f<!-- -->\v<?xml\t\f version="1.0"?>'
    data7 = '\r<!---->\n<!--data-->'
    self.assertEqual(analyze_string(data1), {'format': 'xml'})
    self.assertEqual(analyze_string(' ' + data1, analyze_func=mediafileinfo_detect.analyze_xml), {'format': 'xml', 'detected_format': '?', 'detected_analyze': None})
    self.assertEqual(analyze_string(data2), {'format': 'xml'})
    self.assertEqual(analyze_string(data3), {'format': 'xml'})
    self.assertEqual(analyze_string(data4), {'format': 'xml'})
    self.assertEqual(analyze_string(data5), {'format': 'xml'})
    self.assertEqual(analyze_string(data6), {'format': 'xml'})
    self.assertEqual(analyze_string(' ' + data6), {'format': 'xml'})
    self.assertEqual(analyze_string(data7), {'format': 'xml-comment', 'detected_format': 'xml'})

  def test_analyze_html(self):
    self.assertEqual(analyze_string('\t\f<!doctype\rhtml\r'), {'format': 'html'})
    self.assertEqual(analyze_string('\t\f<!doctype\rhtml>'), {'format': 'html'})
    self.assertEqual(analyze_string('\t\f<html\n'), {'format': 'html'})
    self.assertEqual(analyze_string('\t\f<html>'), {'format': 'html'})
    self.assertEqual(analyze_string('\t\f<head\n'), {'format': 'html'})
    self.assertEqual(analyze_string('\t\f<head>'), {'format': 'html'})
    self.assertEqual(analyze_string('\t\f<body\n'), {'format': 'html'})
    self.assertEqual(analyze_string('\t\f<body>'), {'format': 'html'})
    data2 = '<!--x-->\t\f<body>'
    self.assertEqual(analyze_string(data2), {'format': 'html', 'detected_format': 'xml'})
    self.assertEqual(analyze_string('\r\n' + data2), {'format': 'html', 'detected_format': 'xml'})
    self.assertEqual(analyze_string('\t\f<!doctype\rhtml=', expect_error=True, analyze_func=mediafileinfo_detect.analyze_xml), {'detected_format': '?', 'detected_analyze': None, 'error': 'xml signature not found.'})
    self.assertEqual(analyze_string('\t\f<html=', expect_error=True, analyze_func=mediafileinfo_detect.analyze_xml), {'detected_format': '?', 'detected_analyze': None, 'error': 'xml signature not found.'})

  def test_analyze_xhtml(self):
    data1 = '<html lang="en"\txmlns="http://www.w3.org/1999/xhtml">'
    data2 = '\t\f<!DOCTYPE\rhtml>\n' + data1
    data3 = '<?xml version="1.0"?>\r\n' + data2
    data4 = '<!-- hi --> ' + data3
    data5 = '\t\f<!DOCTYPE\rhtml>\n<!-- hi -->\r\n<!---->' + data1
    self.assertEqual(analyze_string(data1), {'format': 'xhtml', 'detected_format': 'html'})
    self.assertEqual(analyze_string(data2), {'format': 'xhtml', 'detected_format': 'html'})
    self.assertEqual(analyze_string(data3), {'format': 'xhtml', 'detected_format': 'xml'})
    self.assertEqual(analyze_string(data4), {'format': 'xhtml', 'detected_format': 'xml'})
    self.assertEqual(analyze_string(data5), {'format': 'xhtml', 'detected_format': 'html'})

  def test_analyze_texmacs_xml(self):
    self.assertEqual(analyze_string('<?xml version="1.0"?>\n\n<TeXmacs version="1.99.9">'), {'format': 'texmacs', 'detected_format': 'xml', 'subformat': 'xml'})

  def test_analyze_mathml(self):
    self.assertEqual(analyze_string('<?xml version="1.0" encoding="UTF-8"?>\n\n<math xmlns="http://www.w3.org/1998/Math/MathML" display="block"/>'),
                     {'format': 'mathml', 'detected_format': 'xml'})

  def test_analyze_uof(self):
    self.assertEqual(analyze_string('<?xml version="1.0" encoding="UTF-8"?>\r<uof:UOF xmlns:uof="http://schemas.uof.org/cn/2003/uof"/>'),
                     {'format': 'uof-xml', 'detected_format': 'xml'})
    self.assertEqual(analyze_string('<?xml version="1.0" encoding="UTF-8"?>\r<uof:UOF xmlns:uof="http://schemas.uof.org/cn/2003/uof" uof:mimetype="vnd.uof.presentation">'),
                     {'format': 'uof-uop', 'detected_format': 'xml'})
    self.assertEqual(analyze_string('<?xml version="1.0" encoding="UTF-8"?>\r<uof:UOF xmlns:uof="http://schemas.uof.org/cn/2003/uof" uof:mimetype="vnd.uof.spreadsheet">'),
                     {'format': 'uof-uos', 'detected_format': 'xml'})
    self.assertEqual(analyze_string('<?xml version="1.0" encoding="UTF-8"?>\r<uof:UOF xmlns:uof="http://schemas.uof.org/cn/2003/uof" uof:mimetype="vnd.uof.text">'),
                     {'format': 'uof-uot', 'detected_format': 'xml'})

  def test_analyze_odf_flatxml(self):
    self.assertEqual(analyze_string('<?xml version="1.0" encoding="UTF-8"?>\t<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"/>'),
                     {'format': 'odf-flatxml', 'detected_format': 'xml'})
    self.assertEqual(analyze_string('<?xml version="1.0" encoding="UTF-8"?>\t<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" office:mimetype="application/vnd.oasis.opendocument.graphics">'),
                     {'format': 'odf-flatxml-fodg', 'detected_format': 'xml'})
    self.assertEqual(analyze_string('<?xml version="1.0" encoding="UTF-8"?>\t<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" office:mimetype="application/vnd.oasis.opendocument.presentation">'),
                     {'format': 'odf-flatxml-fodp', 'detected_format': 'xml'})
    self.assertEqual(analyze_string('<?xml version="1.0" encoding="UTF-8"?>\t<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" office:mimetype="application/vnd.oasis.opendocument.spreadsheet">'),
                     {'format': 'odf-flatxml-fods', 'detected_format': 'xml'})
    self.assertEqual(analyze_string('<?xml version="1.0" encoding="UTF-8"?>\t<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" office:mimetype="application/vnd.oasis.opendocument.text">'),
                     {'format': 'odf-flatxml-fodt', 'detected_format': 'xml'})

  def test_parse_svg_dimen(self):
    f = mediafileinfo_detect.parse_svg_dimen
    self.assertRaises(ValueError, f, '')
    self.assertRaises(ValueError, f, '.')
    self.assertRaises(ValueError, f, '-5')
    self.assertEqual(f('0'), 0)
    self.assertEqual(f('00092'), 92)
    self.assertEqual(f('42.0'), 42)
    self.assertEqual(f('42.40000'), 42)
    self.assertEqual(f('42.5'), 43)  # Rounded up.
    self.assertEqual(f('2e3'), 2000)
    self.assertEqual(f('23456789e-3'), 23457)
    self.assertEqual(f('10 in'), 900)
    self.assertEqual(f('10 px'), 10)
    self.assertEqual(f('10 pt'), 13)  # 12.5 rounded up to 13.
    self.assertEqual(f('100pt'), 125)
    self.assertEqual(f('10pc'), 150)
    self.assertEqual(f('10.2pc'), 153)
    self.assertEqual(f('10mm'), 35)
    self.assertEqual(f('10cm'), 354)
    self.assertRaises(ValueError, f, '10sp')  # TeX unit sp not supported by SVG.
    self.assertRaises(ValueError, f, '10em')  # Font-based unit em not supported.
    self.assertRaises(ValueError, f, '10ex')  # Font-based unit ex not supported.

  def test_analyze_svg(self):
    self.assertEqual(analyze_string('<svg\t'),
                     {'format': 'svg'})
    self.assertEqual(analyze_string('<svg:svg>'),
                     {'format': 'svg'})
    self.assertEqual(analyze_string('<svg:svg>\f'),
                     {'format': 'svg'})
    self.assertEqual(analyze_string('<!-- --><svg>'),
                     {'format': 'svg', 'detected_format': 'xml'})
    self.assertEqual(analyze_string('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n<!-- Created with Sodipodi ("http://www.sodipodi.com/") -->\n<svg\n   xmlns:xml="http://www.w3.org/XML/1998/namespace"\n   xmlns:dc="http://purl.org/dc/elements/1.1/"\n   xmlns:cc="http://web.resource.org/cc/"\n   xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n   xmlns:svg="http://www.w3.org/2000/svg"\n   xmlns="http://www.w3.org/2000/svg"\n   xmlns:xlink="http://www.w3.org/1999/xlink"\n   xmlns:sodipodi="http://inkscape.sourceforge.net/DTD/sodipodi-0.dtd"\n   xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"\n   id="svg602"\n   sodipodi:version="0.32"\n   width="100.00000pt"\n   height="100.00000pt"\n   xml:space="preserve"\n   sodipodi:docname="english.svg"\n   sodipodi:docbase="/home/terry/.icons/nabi"\n   inkscape:version="0.41"\n   inkscape:export-filename="/home/terry/images/icon/png/NewDir/txtfile.png"\n   inkscape:export-xdpi="200.00000"\n   inkscape:export-ydpi="200.00000"><foo'),
                     {'format': 'svg', 'detected_format': 'xml', 'height': 125, 'width': 125})
    self.assertEqual(analyze_string('<?xml version="1.0" standalone="no"?>\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN"\n   "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n<!--\n    Designed after data from http://www.wacom-asia.com/download/manuals/BambooUsersManual.pdf\n    Size and positions of controls may not be accurate\n -->\n<svg\n   xmlns="http://www.w3.org/2000/svg"\n   version="1.1"\n   style="color:#000000;stroke:#7f7f7f;fill:none;stroke-width:.25;font-size:8"\n   id="bamboo-2fg"\n   width="208"\n   height="136">\n  <title'),
                     {'format': 'svg', 'detected_format': 'xml', 'height': 136, 'width': 208})
    self.assertEqual(analyze_string('<svg xmlns = \'http://www.w3.org/2000/svg\' width="099" height="0009px">'),
                     {'format': 'svg', 'height': 9, 'width': 99})
    self.assertEqual(analyze_string('<svg:svg xmlns = \'http://www.w3.org/2000/svg\' width="2e3" height="0009px">'),
                     {'format': 'svg', 'height': 9, 'width': 2000})
    self.assertEqual(analyze_string('<!-- my\ncomment -->\r\n <svg:svg xmlns = \'http://www.w3.org/2000/svg\' width="2e3" height="0009px">'),
                     {'format': 'svg', 'detected_format': 'xml', 'height': 9, 'width': 2000})
    data1 = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd" [\r\n	<!ENTITY ns_svg "http://www.w3.org/2000/svg">\r\n	<!ENTITY ns_xlink "http://www.w3.org/1999/xlink">\r\n]>\n<svg version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="128" height="129" viewBox="0 0 128 129" overflow="visible" enable-background="new 0 0 128 129" xml:space="preserve">'
    self.assertEqual(analyze_string(data1),
                     {'format': 'svg', 'detected_format': 'xml', 'height': 129, 'width': 128})
    self.assertEqual(analyze_string('\f' + data1, analyze_func=mediafileinfo_detect.analyze_xml),
                     {'format': 'svg', 'detected_format': '?', 'detected_analyze': None, 'height': 129, 'width': 128})
    self.assertEqual(analyze_string('<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="100%" height="100%" viewBox="0 -200 800 700">\n  <title>'),
                     {'format': 'svg', 'detected_format': 'xml', 'height': 700, 'width': 800})
    self.assertEqual(analyze_string('<?xml version="1.0"?>\n<svg:svg xmlns:svg="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="100%" height="100%" viewBox="0 -200 800 700">\n  <svg:title>'),
                     {'format': 'svg', 'detected_format': 'xml', 'height': 700, 'width': 800})
    self.assertEqual(analyze_string('<!----><svg xmlns="http://www.w3.org/2000/svg">\n  <view id="normal" viewBox="0 0 17 19"/>'),
                     {'format': 'svg', 'detected_format': 'xml', 'height': 19, 'width': 17})

  def test_analyze_smil(self):
    self.assertEqual(analyze_string('<smil>'),
                     {'format': 'smil'})
    self.assertEqual(analyze_string('<smil\r'),
                     {'format': 'smil'})
    self.assertEqual(analyze_string('<!-- my\ncomment -->\t\t<smil>'),
                     {'format': 'smil', 'detected_format': 'xml'})
    self.assertEqual(analyze_string('<?xml version="1.0" encoding="UTF-8"?>\n<!-- Comment --->\n<!DOCTYPE smil -->\t\f<smil xml:id="root" xmlns="http://www.w3.org/ns/SMIL" version="3.0" baseProfile="Tiny" >'),
                     {'format': 'smil', 'detected_format': 'xml'})
    self.assertEqual(analyze_string('<?xml version="1.0" encoding="UTF-8"?><smil:smil xml:id="root" xmlns:smil="http://www.w3.org/ns/SMIL" version="3.0" baseProfile="Tiny" >'),
                     {'format': 'smil', 'detected_format': 'xml'})

  def test_analyze_brunsli(self):
    self.assertEqual(analyze_string('\x0a\x04B\xd2\xd5N'),
                     {'format': 'jpegxl-brunsli', 'subformat': 'brunsli', 'codec': 'brunsli'})
    self.assertEqual(analyze_string('0a0442d2d54e120a08810410800418022011'.decode('hex')),
                     {'format': 'jpegxl-brunsli', 'subformat': 'brunsli', 'codec': 'brunsli', 'height': 512, 'width': 513})

  def test_analyze_fuif(self):
    self.assertEqual(analyze_string('FUIF3.'),
                     {'format': 'fuif', 'subformat': 'fuif', 'codec': 'fuif'})
    self.assertEqual(analyze_string('46554946332e84017e'.decode('hex')),
                     {'format': 'fuif', 'subformat': 'fuif', 'codec': 'fuif', 'component_count': 3, 'bpc': 8, 'height': 127, 'width': 514})

  def test_analyze_jpegxl(self):
    self.assertEqual(analyze_string('\xff\x0a--'),
                     {'format': 'jpegxl', 'subformat': 'jpegxl', 'codec': 'jpegxl', 'height': 184, 'width': 276})
    self.assertEqual(analyze_string('ff0af81f'.decode('hex')),
                     {'format': 'jpegxl', 'subformat': 'jpegxl', 'codec': 'jpegxl', 'height': 512, 'width': 512})
    self.assertEqual(analyze_string('ff0a7f00'.decode('hex')),
                     {'format': 'jpegxl', 'subformat': 'jpegxl', 'codec': 'jpegxl', 'height': 256, 'width': 256})
    self.assertEqual(analyze_string('ff0ab881a209'.decode('hex')),
                     {'format': 'jpegxl', 'subformat': 'jpegxl', 'codec': 'jpegxl', 'height': 56, 'width': 1234})

  def test_analyze_pik(self):
    self.assertEqual(analyze_string('P\xccK\x0a'),
                     {'format': 'pik', 'subformat': 'pik1', 'codec': 'pik'})
    self.assertEqual(analyze_string('50cc4b0a51319400'.decode('hex')),
                     {'format': 'pik', 'subformat': 'pik1', 'codec': 'pik', 'height': 404, 'width': 550})
    self.assertEqual(analyze_string('\xd7LM\x0a'),
                     {'format': 'pik', 'subformat': 'pik2', 'codec': 'pik'})
    self.assertEqual(analyze_string('d74c4d0a45931b00'.decode('hex')),
                     {'format': 'pik', 'subformat': 'pik2', 'codec': 'pik', 'height': 56, 'width': 1234})
    self.assertEqual(analyze_string('d74c4d0afce73f0e'.decode('hex')),
                     {'format': 'pik', 'subformat': 'pik2', 'codec': 'pik', 'height': 512, 'width': 512})

  def test_analyze_qtif(self):
    self.assertEqual(analyze_string('\0\1\0\x00idat'),
                     {'format': 'qtif'})
    self.assertEqual(analyze_string('\0\1\0\x00iicc'),
                     {'format': 'qtif'})
    self.assertEqual(analyze_string('\0\0\0\xffidsc'),
                     {'format': 'qtif'})
    self.assertEqual(analyze_string('\0\0\0\x0bidat\xff\xd8\xff\0\0\x00nidsc\0\0\x00fjpeg\0\0\0\0\0\0\0\0\0\x01\0\x01appl\0\0\0\0\0\0\x02\0\x01\0\x01m\x00H\0\0\x00H\0\0\0\x00Hq\0\x01\x0cPhoto - JPEG\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\x18\xff\xff\0\0\0\x0cgama\0\x01\xcc\xcc\0\0\0\0'),
                     {'format': 'qtif', 'codec': 'jpeg', 'height': 365, 'width': 256})
    self.assertEqual(analyze_string('\0\0\x00nidsc\0\0\x00fjpeg\0\0\0\0\0\0\0\0\0\x01\0\x01appl\0\0\0\0\0\0\x02\0\x01\0\x01m'),
                     {'format': 'qtif', 'codec': 'jpeg', 'height': 365, 'width': 256})

  def test_analyze_psp(self):
    data = 'Paint Shop Pro Image File\n\x1a\0\0\0\0\0\x05\0\0\x00~BK\0\0\x00.\0\0\x00.\0\0\0\xf4\1\0\0\xb9\1\0\0'
    self.assertEqual(analyze_string(data[:32]),
                     {'format': 'psp'})
    self.assertEqual(analyze_string(data),
                     {'format': 'psp', 'height': 441, 'width': 500})
    self.assertEqual(analyze_string(data + '\0\0\0\0\0\x00R@\1\2\0'),
                     {'format': 'psp', 'height': 441, 'width': 500, 'codec': 'lz77'})

  def test_analyze_ras(self):
    self.assertEqual(analyze_string('\x59\xa6\x6a\x95'),
                     {'format': 'ras'})
    self.assertEqual(analyze_string('\x59\xa6\x6a\x95\0\0\1\xe6\0\0\0\x78????????\0\0\0\2'),
                     {'format': 'ras', 'codec': 'rle', 'height': 120, 'width': 486})
    self.assertEqual(analyze_string('\x59\xa6\x6a\x95\0\0\1\xe6\0\0\0\x78????????\0\0\0\3'),
                     {'format': 'ras', 'height': 120, 'width': 486})

  def test_analyze_pam(self):
    self.assertEqual(analyze_string('P7\n#\nWIDTH 1\n', expect_error=True),
                     {'format': 'pam', 'codec': 'uncompressed', 'error': 'EOF in pam header before ENDHDR.'})
    self.assertEqual(analyze_string('P7\n\nHEIGHT\t2\n', expect_error=True),
                     {'format': 'pam', 'codec': 'uncompressed', 'error': 'EOF in pam header before ENDHDR.'})
    self.assertEqual(analyze_string('P7\nQ RS\nDEPTH\f3\n', expect_error=True),
                     {'format': 'pam', 'codec': 'uncompressed', 'error': 'EOF in pam header before ENDHDR.'})
    self.assertEqual(analyze_string('P7\nQ RS\nMAXVAL\v4\n', expect_error=True),
                     {'format': 'pam', 'codec': 'uncompressed', 'error': 'EOF in pam header before ENDHDR.'})
    self.assertEqual(analyze_string('P7\nENDHDR\n', expect_error=True),
                     {'format': 'pam', 'codec': 'uncompressed', 'error': 'Missing pam header keys: DEPTH, HEIGHT, MAXVAL, WIDTH'})
    self.assertEqual(analyze_string('P7\nQ RS\n', expect_error=True, analyze_func=mediafileinfo_detect.analyze_pam),
                     {'format': 'pam', 'detected_format': '?', 'detected_analyze': None, 'codec': 'uncompressed', 'error': 'EOF in pam header before ENDHDR.'})
    self.assertEqual(analyze_string('P7\nWIDTH 227\nDEPTH 3\n# WIDTH 42\nHEIGHT\t\f149\nMAXVAL 255\nTUPLTYPE RGB\nENDHDR\n'),
                     {'format': 'pam', 'codec': 'uncompressed', 'height': 149, 'width': 227})

  def test_analyze_xv_thumbnail(self):
    data1 = 'P7 332\n#XVVERSION:Version 2.28  Rev: 9/26/92\n#IMGINFO:512x440 Color JPEG\n#END_OF_COMMENTS\n48 40 255\n'
    self.assertEqual(analyze_string(data1[:data1.find('\n') + 1]),
                     {'format': 'xv-thumbnail', 'codec': 'uncompressed'})
    self.assertEqual(analyze_string(data1),
                     {'format': 'xv-thumbnail', 'codec': 'uncompressed', 'height': 40, 'width': 48})

  def test_analyze_gem(self):
    self.assertEqual(analyze_string('\0\1\0\x08\0\2\0\2'),
                     {'format': 'gem', 'subformat': 'nosig', 'codec': 'rle'})
    self.assertEqual(analyze_string('\0\1\0\x08\0\2\0\2\0\x55\0\x55\1\0\0\x40'),
                     {'format': 'gem', 'subformat': 'nosig', 'codec': 'rle', 'height': 64, 'width': 256})
    self.assertEqual(analyze_string('\0\2\0\x3b\0\4\0\1\0\x55\0\x55\1\0\0\x40XIMG\0\0'),
                     {'format': 'gem', 'subformat': 'ximg', 'codec': 'rle', 'height': 64, 'width': 256})

  def test_analyze_pcpaint_pic(self):
    data1 = '\x34\x12\x40\x01\xc8\0\0\0\0\0\x02\xff\x41\0\0\0\0\0\0'
    self.assertEqual(analyze_string(data1[:14]),
                     {'format': 'pcpaint-pic', 'codec': 'rle', 'height': 200, 'width': 320})
    self.assertEqual(analyze_string(data1),
                     {'format': 'pcpaint-pic', 'codec': 'uncompressed', 'height': 200, 'width': 320})

  def test_analyze_ivf(self):
    self.assertEqual(analyze_string('DKIF\0\0 \0'),
                     {'format': 'ivf', 'tracks': []})
    self.assertEqual(analyze_string('DKIF\0\0 \0VP80 \3 \4'),
                     {'format': 'ivf', 'tracks': [{'codec': 'vp8', 'height': 1056, 'type': 'video', 'width': 800}]})

  def test_analyze_wmf(self):
    self.assertEqual(analyze_string('\xd7\xcd\xc6\x9a\0\0'),
                     {'format': 'wmf'})
    self.assertEqual(analyze_string('\1\0\x09\0\0\3??????????\0\0'),
                     {'format': 'wmf'})
    self.assertEqual(analyze_string('\1\0\x09\0\0\3\x17\x85\0\0\4\0\xf0\x1a\0\0\0\0'),
                     {'format': 'wmf'})
    self.assertEqual(analyze_string('\xd7\xcd\xc6\x9a\0\0\x58\xf0\xce\xf2\xa8\x0f\x32\x0d\xe8\x03\0\0\0\0'),
                     {'format': 'wmf', 'height': 4232, 'width': 4141})

  def test_analyze_emf(self):
    data1 = '0100000084000000d80100003f02000088110000ac1800000000000000000000085200000474000020454d460000010054ff83005101000004000000'.decode('hex')
    data2 = '010000006c000000ffffffffffffffff640000006b0000000000000000000000f00700007708000020454d46000001005c0a00004c0000000200000000000000000000000000000040060000b004000040010000f000000000000000000000000000000000e2040080a90300460000002c00000020000000454d462b014001001c000000100000000210c0db01000000660000006c000000'.decode('hex')
    self.assertEqual(analyze_string(data1),
                     {'format': 'emf', 'subformat': 'emf', 'height': 842, 'width': 595})
    self.assertEqual(analyze_string(data2),
                     {'format': 'emf', 'subformat': 'dual', 'height': 61, 'width': 58})

  def test_analyze_pict(self):
    data_zeros1 = '\0' * 32 + '?' * (512 - 32)
    data_zeros2 = '\0' * 64 + '?' * (512 - 64)
    data_rle = '\x90??\1\1\2\2\6\6\5\5????'
    data_pict1 = '\0\0\0\0\0\0\2\1\2\3\x11\1\1\0\x0a\0\0\0\0\2\1\2\3\xff'
    data_uqt_jpeg = '\x82\0\0\0\x15\x82\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\x40\0\0\0\0\0\0\0\0\0\0\3\0\0\0\0\0\0\0\0\x56jpeg\0\0\0\0\0\0\0\0\0\1\0\x01appl\0\0\0\0\0\0\3\0\0\xa0\0\x78\0\x48\0\0\0\x48\0\0????\0\1\1???????????????????????????????\0\x18\xff\xff'
    data_jpeg = '\xff\xd8\xff'
    data_uqt_lbm = '\x82\0\0\0\x15\x82\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\x40\0\0\0\0\0\0\0\0\0\0\3\0\0\0\0\0\0\0\0\x56iff \0\0\0\0\0\0\0\0\0\1\0\x01appl\0\0\0\0\0\0\3\0\0\xa0\0\x78\0\x48\0\0\0\x48\0\0????\0\1\1???????????????????????????????\0\x18\xff\xff'
    data_lbm = 'FORM\0\0\0\x4ePBM BMHD\0\0\0\x14\1\3\1\5'
    data_pict2 = '\0\0\0\0\0\0\2\1\2\3\0\x11\2\xff\0\1\0\x0a\0\0\0\0\2\1\2\3' + data_uqt_jpeg + data_jpeg
    data_pict2ext = '\0\0\0\0\0\0\2\1\2\3\0\x11\2\xff\x0c\0\xff\xfe??????????????????????\0\1\0\x0a\0\0\0\0\2\1\2\3\0\xff'
    data_macbinary1 = '\0\x11Name of this file\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\x00PICT????\1\0\0\0\0\0\0\0\x80\0\0\0\x82\0\0\0\0\0\x99\xd4\x89\0\x99\xd4\x89\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0'
    self.assertEqual(analyze_string(data_pict1),
                     {'format': 'pict', 'height': 513, 'width': 515, 'subformat': '1', 'pt_height': 513, 'pt_width': 515})
    self.assertEqual(analyze_string(data_macbinary1 + data_pict1),
                     {'format': 'pict', 'detected_format': 'macbinary', 'height': 513, 'width': 515, 'subformat': '1', 'pt_height': 513, 'pt_width': 515})
    self.assertEqual(analyze_string(data_pict1[:16]),
                     {'format': 'pict', 'height': 513, 'width': 515, 'subformat': '1', 'pt_height': 513, 'pt_width': 515})
    self.assertEqual(analyze_string(data_pict1 + data_rle),
                     {'format': 'pict', 'height': 513, 'width': 515, 'subformat': '1', 'pt_height': 513, 'pt_width': 515})
    self.assertEqual(analyze_string(data_pict1[:-1] + data_rle),
                     {'format': 'pict', 'height': 1285, 'width': 771, 'codec': 'rle', 'sampled_format': 'pict', 'subformat': '1', 'pt_height': 513, 'pt_width': 515})
    self.assertEqual(analyze_string(data_zeros1 + data_pict1[:15], analyze_func=mediafileinfo_detect.analyze_pict),
                     {'format': 'pict', 'detected_format': '?-zeros32-64', 'detected_analyze': mediafileinfo_detect.analyze_zeros32_64, 'height': 513, 'width': 515, 'subformat': '1', 'pt_height': 513, 'pt_width': 515})
    self.assertEqual(analyze_string(data_zeros1 + data_pict1[:16], analyze_func=mediafileinfo_detect.analyze_pict),
                     {'format': 'pict', 'detected_format': '?-zeros32-64', 'detected_analyze': mediafileinfo_detect.analyze_zeros32_64, 'height': 513, 'width': 515, 'subformat': '1', 'pt_height': 513, 'pt_width': 515})
    self.assertEqual(analyze_string(data_zeros1 + data_pict1[:16]),
                     {'format': 'pict', 'detected_format': '?-zeros32-64', 'height': 513, 'width': 515, 'subformat': '1', 'pt_height': 513, 'pt_width': 515})
    self.assertEqual(analyze_string(data_pict2),
                     {'format': 'pict', 'height': 120, 'width': 160, 'codec': 'jpeg', 'sampled_format': 'jpeg', 'subformat': '2', 'pt_height': 513, 'pt_width': 515})
    self.assertEqual(analyze_string(data_pict2[:16]),
                     {'format': 'pict', 'height': 513, 'width': 515, 'subformat': '2', 'pt_height': 513, 'pt_width': 515})
    self.assertEqual(analyze_string(data_zeros2 + data_pict2[:16], analyze_func=mediafileinfo_detect.analyze_pict),
                     {'format': 'pict', 'detected_format': '?-zeros32-64', 'detected_analyze': mediafileinfo_detect.analyze_zeros32_64, 'height': 513, 'width': 515, 'subformat': '2', 'pt_height': 513, 'pt_width': 515})
    self.assertEqual(analyze_string(data_pict2ext),
                     {'format': 'pict', 'height': 513, 'width': 515, 'subformat': '2ext', 'pt_height': 513, 'pt_width': 515})
    self.assertEqual(analyze_string(data_pict2ext[:16]),
                     {'format': 'pict', 'height': 513, 'width': 515, 'subformat': '2', 'pt_height': 513, 'pt_width': 515})
    self.assertEqual(analyze_string(data_pict2ext[:-2] + data_uqt_lbm + data_lbm),
                     {'format': 'pict', 'height': 261, 'width': 259, 'codec': 'uncompressed', 'sampled_format': 'lbm', 'sampled_subformat': 'pbm', 'subformat': '2ext', 'pt_height': 513, 'pt_width': 515})
    self.assertEqual(analyze_string(data_macbinary1),
                     {'format': 'pict', 'detected_format': 'macbinary', 'subformat': 'macbinary'})

  def test_analyze_minolta_raw(self):
    self.assertEqual(analyze_string('\0MRM\0\1\2\3\0PRD\0\0\0\x18'),
                     {'format': 'minolta-raw', 'codec': 'raw'})
    self.assertEqual(analyze_string('\0MRM\0\1\2\3\0PRD\0\0\0\x1827820001\7\x88\x0a\x08\7\x80\x0a\0'),
                     {'format': 'minolta-raw', 'codec': 'raw', 'height': 1920, 'width': 2560})

  def test_analyze_dpx(self):
    self.assertEqual(analyze_string('SDPX\0\0 \0V2.0'),
                     {'format': 'dpx'})
    self.assertEqual(analyze_string('SDPX\0\0 \0V2.0\0' + 755 * '?' + '\0\0\0\2\0\0\2\3\0\0\2\1' + '?' * 26 + '\0\1'),
                     {'format': 'dpx', 'codec': 'rle', 'height': 513, 'width': 515})

  def test_analyze_cineon(self):
    self.assertEqual(analyze_string('\x80\x2a\x5f\xd7\0\0??'),
                     {'format': 'cineon', 'codec': 'uncompressed'})
    self.assertEqual(analyze_string('\xd7\x5f\x2a\x80??\0\0'),
                     {'format': 'cineon', 'codec': 'uncompressed'})
    self.assertEqual(analyze_string('\x80\x2a\x5f\xd7\0\0??' + '?' * 192 + '\0\0\2\3\0\0\2\1'),
                     {'format': 'cineon', 'codec': 'uncompressed', 'height': 513, 'width': 515})
    self.assertEqual(analyze_string('\xd7\x5f\x2a\x80??\0\0' + '?' * 192 + '\3\2\0\0\1\2\0\0'),
                     {'format': 'cineon', 'codec': 'uncompressed', 'height': 513, 'width': 515})

  def test_analyze_vicar(self):
    self.assertEqual(analyze_string('LBLSIZE=10'),
                     {'format': 'vicar'})
    self.assertEqual(analyze_string('LBLSIZE=10 NS=1 NL=2 FOO=bar'),
                     {'format': 'vicar'})
    self.assertEqual(analyze_string("LBLSIZE=94   FORMAT='HALF'  TYPE='IMAGE' U1='NS=12' FOO NS=34 U2='NS=56' NL = 789\0NL=5 FOO=bar"),
                     {'format': 'vicar', 'height': 789, 'width': 34})

  def test_analyze_pds(self):
    self.assertEqual(analyze_string('NJPL1I00PDS'),
                     {'format': 'pds'})
    self.assertEqual(analyze_string('PDS_VERSION_ID\f'),
                     {'format': 'pds'})
    self.assertEqual(analyze_string('CCSD3ZF'),
                     {'format': 'pds'})
    self.assertEqual(analyze_string('\xff\0NJPL1I00PDS', expect_error=True),
                     {'detected_format': 'pds', 'error': 'Too short for pds size.'})
    self.assertEqual(analyze_string('\x0b\0NJPL1I00PDS\0'),
                     {'format': 'pds'})
    self.assertEqual(analyze_string('\xff\0PDS_VERSION_ID\f', expect_error=True),
                     {'detected_format': 'pds', 'error': 'Too short for pds size.'})
    self.assertEqual(analyze_string('\x0f\0PDS_VERSION_ID\f\0'),
                     {'format': 'pds'})
    self.assertEqual(analyze_string('\xff\0CCSD3ZF', expect_error=True),
                     {'detected_format': 'pds', 'error': 'Too short for pds size.'})
    self.assertEqual(analyze_string('\7\0CCSD3ZF\0'),
                     {'format': 'pds'})
    self.assertEqual(analyze_string('CCSD3ZF0000100000001\nLINES = 42\r\n  IMAGE\0LINE_SAMPLES = 43'),
                     {'format': 'pds', 'height': 42, 'width': 43})
    self.assertEqual(analyze_string('\x20\0NJPL1I00PDS  = XV_COMPATIBILITY \0\x0e\0IMAGE_LINES=42\x0f\0LINE_SAMPLES=43\4\0 END\x0e\0IMAGE_LINES=44'),
                     {'format': 'pds', 'height': 42, 'width': 43})

  def test_analyze_ybm(self):
    self.assertEqual(analyze_string('!''!??'),
                     {'format': 'ybm', 'codec': 'uncompressed'})
    self.assertEqual(analyze_string('!''!\2\3\2\2'),
                     {'format': 'ybm', 'codec': 'uncompressed', 'height': 514, 'width': 515})

  def test_analyze_fbm(self):
    self.assertEqual(analyze_string('%bitmap\0'),
                     {'format': 'fbm', 'codec': 'uncompressed'})
    self.assertEqual(analyze_string('%bitmap\x00123\x00456\x007890\0???'),
                     {'format': 'fbm', 'codec': 'uncompressed', 'height': 7890, 'width': 123})

  def test_analyze_cmuwm(self):
    self.assertEqual(analyze_string('\xf1\0\x40\xbb'),
                     {'format': 'cmuwm', 'codec': 'uncompressed'})
    self.assertEqual(analyze_string('\xbb\x40\0\xf1'),
                     {'format': 'cmuwm', 'codec': 'uncompressed'})
    self.assertEqual(analyze_string('\xf1\0\x40\xbb\0\0\2\3\0\0\2\1\0\1'),
                     {'format': 'cmuwm', 'codec': 'uncompressed', 'height': 513, 'width': 515})
    self.assertEqual(analyze_string('\xbb\x40\0\xf1\3\2\0\0\1\2\0\0'),
                     {'format': 'cmuwm', 'codec': 'uncompressed', 'height': 513, 'width': 515})

  def test_detect_unixscript(self):
    self.assertEqual(analyze_string('#! /usr/bin/perl'), {'format': 'unixscript'})
    self.assertEqual(analyze_string('#!/usr/bin/perl'), {'format': 'unixscript'})

  def test_detect_windows_cmd(self):
    self.assertEqual(analyze_string('@echo off\r\n'), {'format': 'windows-cmd'})
    self.assertEqual(analyze_string('@ECho oFF\r\n'), {'format': 'windows-cmd'})

  def test_analyze_xwd(self):
    data1 = '\0\0\0\x65\0\0\0\7\0\0\0\2\0\0\0\x08\0\0\1\xd3\0\0\0\x3c\0\0\0\0'
    data2 = '\x65\0\0\0\7\0\0\0\2\0\0\0\x08\0\0\0\xd3\1\0\0\x3c\0\0\0\0\0\0\0'
    data3 = '\0\0\0\x65\0\0\0\6\0\0\0\0\0\0\0\1\0\0\0\0\0\0\1\xd3\0\0\0\x3c'
    data4 = '\x65\0\0\0\6\0\0\0\0\0\0\0\1\0\0\0\0\0\0\0\xd3\1\0\0\x3c\0\0\0'
    self.assertEqual(analyze_string(data1[:16]),
                     {'format': 'xwd', 'subformat': 'x11'})
    self.assertEqual(analyze_string(data1),
                     {'format': 'xwd', 'subformat': 'x11', 'height': 60, 'width': 467})
    self.assertEqual(analyze_string(data2[:16]),
                     {'format': 'xwd', 'subformat': 'x11'})
    self.assertEqual(analyze_string(data2),
                     {'format': 'xwd', 'subformat': 'x11', 'height': 60, 'width': 467})
    self.assertEqual(analyze_string(data3[:20]),
                     {'format': 'xwd', 'subformat': 'x10'})
    self.assertEqual(analyze_string(data3),
                     {'format': 'xwd', 'subformat': 'x10', 'height': 60, 'width': 467})
    self.assertEqual(analyze_string(data4[:20]),
                     {'format': 'xwd', 'subformat': 'x10'})
    self.assertEqual(analyze_string(data4),
                     {'format': 'xwd', 'subformat': 'x10', 'height': 60, 'width': 467})

  def test_analyze_dvi(self):
    data1 = '\xf7\2\1\x83\x92\xc0\x1c\x3b\0\0\0\0\3\xe8\x1b TeX output 2020.03.10:0921\x8b\0\0\0\1\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\xff\xff\xff\xff\xef\x21papersize=421.10078pt,597.50787pt'
    self.assertEqual(analyze_string(data1[:10]),
                     {'format': 'dvi'})
    self.assertEqual(analyze_string(data1),
                     {'format': 'dvi', 'height': 595, 'width': 420})

  def test_analyze_sun_icon(self):
    self.assertEqual(analyze_string('/* Format_version=1, Width=123, Height=45, Depth=1, Valid_bits_per_item=16\n */\n'),
                     {'format': 'sun-icon', 'height': 45, 'width': 123})
    self.assertEqual(analyze_string('/*\r\nFormat_version=1,Width=123,Height=45,'),
                     {'format': 'sun-icon', 'height': 45, 'width': 123})
    self.assertEqual(analyze_string('/* Format_version=1,'),
                     {'format': 'sun-icon'})

  def test_analyze_xbm(self):
    self.assertEqual(analyze_string('#define gs_l_m.xbm_width 4'),
                     {'format': 'xbm', 'codec': 'uncompressed-ascii'})
    self.assertEqual(analyze_string('#define test_width 16\n#define test_height 7\nstatic unsigned char test_bits[] = {\n  0x13, 0x00, 0x15, 0x00, 0x93, 0xcd, 0x55, 0xa5,'),
                     {'format': 'xbm', 'codec': 'uncompressed-ascii', 'height': 7, 'width': 16})
    self.assertEqual(analyze_string('#define test_width 16\n#define test_height 72'),
                     {'format': 'xbm', 'codec': 'uncompressed-ascii', 'height': 72, 'width': 16})

  def test_analyze_xpm(self):
    self.assertEqual(analyze_string('#define gs_l_m._format 1\r'),
                     {'format': 'xpm', 'subformat': 'xpm1', 'codec': 'uncompressed-ascii'})
    self.assertEqual(analyze_string('#define gs_l_m._format 1\n'),
                     {'format': 'xpm', 'subformat': 'xpm1', 'codec': 'uncompressed-ascii'})
    self.assertEqual(analyze_string('#define gs_l_m._format 1\n#define gs_l_m._width 16\r\n\n\n#define gs_l_m._height 72'),
                     {'format': 'xpm', 'subformat': 'xpm1', 'codec': 'uncompressed-ascii', 'height': 72, 'width': 16})
    self.assertEqual(analyze_string('! XPM2\r'),
                     {'format': 'xpm', 'subformat': 'xpm2', 'codec': 'uncompressed-ascii'})
    self.assertEqual(analyze_string('! XPM2\n'),
                     {'format': 'xpm', 'subformat': 'xpm2', 'codec': 'uncompressed-ascii'})
    self.assertEqual(analyze_string('! XPM2\r\n16\t7 '),
                     {'format': 'xpm', 'subformat': 'xpm2', 'codec': 'uncompressed-ascii', 'height': 7, 'width': 16})
    self.assertEqual(analyze_string('/* XPM */\n\r\t'),
                     {'format': 'xpm', 'subformat': 'xpm3', 'codec': 'uncompressed-ascii'})
    self.assertEqual(analyze_string('/* XPM */\r'),
                     {'format': 'xpm', 'subformat': 'xpm3', 'codec': 'uncompressed-ascii'})
    self.assertEqual(analyze_string('/* XPM */\nstatic char *foo_xpm[] = {\n/* columns rows colors chars-per-pixel */\n"12 \t3456 '),
                     {'format': 'xpm', 'subformat': 'xpm3', 'codec': 'uncompressed-ascii', 'height': 3456, 'width': 12})

  def test_analyze_bmp(self):
    data0 = 'BM????\0\0\0\0????\x0c\0\0\0\x80\2\xe0\1'
    data1 = 'BM????\0\0\0\0????\x28\0\0\0\x80\2\0\0\xe0\1\0\0\1\0\x08\0\1\0\0\0'
    data2 = 'BM????\0\0\0\0????@\0\0\0\x80\2\0\0\xe0\1\0\0\1\0\x08\0\1\0\0\0'
    self.assertEqual(analyze_string(data0),
                     {'format': 'bmp', 'codec': 'uncompressed', 'height': 480, 'width': 640})
    self.assertEqual(analyze_string(data1),
                     {'format': 'bmp', 'codec': 'rle', 'height': 480, 'width': 640})
    self.assertEqual(analyze_string(data1[:22]),
                     {'format': 'bmp'})
    self.assertEqual(analyze_string(data2),
                     {'format': 'bmp', 'codec': 'rle', 'height': 480, 'width': 640})

  def test_analyze_dib(self):
    data0 = '\x0c\0\0\0\x80\2\xe0\1\1\0\2\0'
    data1 = '\x28\0\0\0\x80\2\0\0\xe0\1\0\0\1\0\x08\0\1\0\0\0'
    data2 = '@\0\0\0\x80\2\0\0\xe0\1\0\0\1\0\x08\0\1\0\0\0'
    self.assertEqual(analyze_string(data0),
                     {'format': 'dib', 'codec': 'uncompressed', 'height': 480, 'width': 640})
    self.assertEqual(analyze_string(data1),
                     {'format': 'dib', 'codec': 'rle', 'height': 480, 'width': 640})
    self.assertEqual(analyze_string(data2),
                     {'format': 'dib', 'codec': 'rle', 'height': 480, 'width': 640})

  def test_analyze_rdib(self):
    data_bmp = 'BM????\0\0\0\0????\x28\0\0\0\x80\2\0\0\xe0\1\0\0\1\0\x08\0\1\0\0\0'
    data1 = 'RIFF????RDIB' + data_bmp
    data2 = 'RIFF????RDIBdata' + data_bmp
    data3 = 'RIFF????RDIBdata????' + data_bmp
    self.assertEqual(analyze_string(data1),
                     {'format': 'rdib', 'codec': 'rle', 'height': 480, 'width': 640})
    self.assertEqual(analyze_string(data1[:14]),
                     {'format': 'rdib'})
    self.assertEqual(analyze_string(data2),
                     {'format': 'rdib', 'codec': 'rle', 'height': 480, 'width': 640})
    self.assertEqual(analyze_string(data2[:16]),
                     {'format': 'rdib'})
    self.assertEqual(analyze_string(data3),
                     {'format': 'rdib', 'codec': 'rle', 'height': 480, 'width': 640})

  def test_analyze_utah_rle(self):
    self.assertEqual(analyze_string('\x52\xcc\x1c\0\x2c\0\x3e\0\x32\0\x05\x03\x08\0\x08'),
                     {'format': 'utah-rle', 'codec': 'rle', 'height': 50, 'width': 62})

  def test_detect_fig(self):
    self.assertEqual(analyze_string('#FIG 3.2\n'), {'format': 'fig'})

  def test_analyze_zip(self):
    def build_zip_entry(filename, data):  # Uncompressed.
      return ''.join(('PK\3\4\x14\0\0\x08\0\0\xe5rYS\7\x8a\xa8\x5b', struct.pack('<LLL', len(data), len(data), len(filename)), filename, data))

    def build_compressed_zip_entry(filename, data):
      import zlib
      zc = zlib.compressobj(1, 8, -15)
      uncompressed_size = len(data)
      data = ''.join((zc.compress(data), zc.flush()))
      return ''.join(('PK\3\4\x14\0\0\x08\x08\0\xe5rYS\7\x8a\xa8\x5b', struct.pack('<LLL', len(data), uncompressed_size, len(filename)), filename, data))

    self.assertEqual(analyze_string('PK\1\2'), {'format': 'zip'})
    self.assertEqual(analyze_string('PK\3\4'), {'format': 'zip'})
    self.assertEqual(analyze_string('PK00PK\5\6'), {'format': 'zip'})
    self.assertEqual(analyze_string('PK00PK\7\x08'), {'format': 'zip'})
    self.assertEqual(analyze_string('PK\6\6'), {'format': 'zip'})
    self.assertEqual(analyze_string(build_zip_entry('hi', 'hello')), {'format': 'zip'})
    self.assertEqual(analyze_string(build_zip_entry('mimetype', '')), {'format': 'odf-zip', 'detected_format': 'zip'})
    self.assertEqual(analyze_string(build_zip_entry('mimetype', 'application/vnd.oasis.opendocument.base')), {'format': 'odf-odb', 'detected_format': 'zip'})
    self.assertEqual(analyze_string(build_zip_entry('mimetype', 'application/vnd.oasis.opendocument.formula')), {'format': 'odf-odf', 'detected_format': 'zip'})
    self.assertEqual(analyze_string(build_zip_entry('mimetype', 'application/vnd.oasis.opendocument.graphics')), {'format': 'odf-odg', 'detected_format': 'zip'})
    self.assertEqual(analyze_string(build_zip_entry('mimetype', 'application/vnd.oasis.opendocument.presentation')), {'format': 'odf-odp', 'detected_format': 'zip'})
    self.assertEqual(analyze_string(build_zip_entry('mimetype', 'application/vnd.oasis.opendocument.spreadsheet')), {'format': 'odf-ods', 'detected_format': 'zip'})
    self.assertEqual(analyze_string(build_zip_entry('mimetype', 'application/vnd.oasis.opendocument.text')), {'format': 'odf-odt', 'detected_format': 'zip'})
    self.assertEqual(analyze_string(build_zip_entry('mimetype', 'application/vnd.oasis.opendocument.graphics-template')), {'format': 'odf-otg', 'detected_format': 'zip'})
    self.assertEqual(analyze_string(build_zip_entry('mimetype', 'application/vnd.oasis.opendocument.presentation-template')), {'format': 'odf-otp', 'detected_format': 'zip'})
    self.assertEqual(analyze_string(build_zip_entry('mimetype', 'application/vnd.oasis.opendocument.spreadsheet-template')), {'format': 'odf-ots', 'detected_format': 'zip'})
    self.assertEqual(analyze_string(build_zip_entry('mimetype', 'application/vnd.oasis.opendocument.text-template')), {'format': 'odf-ott', 'detected_format': 'zip'})
    # Usually compressed, but for speeding up tests we test only 1 compressed.
    self.assertEqual(analyze_string(build_zip_entry('[Content_Types].xml', '')), {'format': 'msoffice-zip', 'detected_format': 'zip'})
    self.assertEqual(analyze_string(build_compressed_zip_entry('[Content_Types].xml', '<?xml PartName="/word/')), {'format': 'msoffice-docx', 'detected_format': 'zip'})
    self.assertEqual(analyze_string(build_zip_entry('[Content_Types].xml', '<?xml PartName="/xl/ PartName="/xl/ ')), {'format': 'msoffice-xlsx', 'detected_format': 'zip'})
    self.assertEqual(analyze_string(build_zip_entry('[Content_Types].xml', '<?xml PartName="/ppt/')), {'format': 'msoffice-pptx', 'detected_format': 'zip'})
    self.assertEqual(analyze_string(build_zip_entry('[Content_Types].xml', '<?xml PartName="/word/ PartName="/xl/ ')), {'format': 'msoffice-zip', 'detected_format': 'zip'})

  def test_detect_zoo(self):
    self.assertEqual(analyze_string('ZOO 2.00 Archive.\x1a\0\0\xdc\xa7\xc4\xfd'), {'format': 'zoo'})
    self.assertEqual(analyze_string('ZOO 1.20 Archive.\x1a\0\0\xdc\xa7\xc4\xfd'), {'format': 'zoo'})

  def test_detect_arj(self):
    self.assertEqual(analyze_string('\x60\xea\xe0\4\x1e\6\1\0\x10\0\2'), {'format': 'arj'})

  def test_detect_lha(self):
    self.assertEqual(analyze_string('*9-lh5-\xa1\5\0\0\xb8\7\0\0\x36\x7d\x6b\x50\2\1'), {'format': 'lha'})

  def test_analyze_mpeg_ps(self):
    data1 = '000001ba4400040004010189c3f8000001bb001280c4e104e17fb9e0e8b8c020bde03abfe002000001e0007681c10d310001b8611100019c411e60e8000001b32c0240231755e38110111112121213131313141414141415151515151516161616161616171717171717171718181819181818191a1a1a1a191b1b1b1b1b1c1c1c1c1e1e1e1f1f21000001b5148200010000000001b52305050508721200000001b8'.decode('hex')
    data2 = '000001ba2100031941801b91000001bb0009801b9101e1ffe0e02e000001be00086162636465666768000001ba2100032c01801b91000001e0001c602e31000527911100050b71000001b31601208302cee0a4000001b8'.decode('hex')
    data_video_prev = '000001ba44e806d16e030189c3f8000001e0001c8100007428c0ade7649131f5c187e1b8005dc0d5acdb4c892a787137'.decode('hex')
    data_video = '000001ba44e80f07f4ad0189c3f8000001e0002781c00a313a05c2eb113a057c89000001b32d01e0240a1e62f8000001b5148200010000000001b8'.decode('hex')
    data_audio = '000001ba44e807716e030189c3f8000001bd0014818005213a0335a7800301850b779c6714404b7f'.decode('hex')
    data_dvd = ('000001ba44e80f0364010189c3f8000001bb001280c4e104e17fb9e0e8b8c020bde03abfe002000001bf03d4000007ffc100000000000000000e8149ff0e81f9f400000000000632d5' + '00' * 953 +
                '01bf03fa010e80e06c0007ffc10000006100000017000000250000003500010003000632d5000000000000000000000000000069931a20799a' + '00' * 182 +
                '80000062c0005a8bc0002db8c0001662c000079980000557800004f38000049380000431800003d08000036180000305800002ac8000024d800001ef8000018a80000125800000c38000006280000000800000628000006080000060800000c08000011d80000174800001d28000023f8000029e800002f88000034a800003a18000040480000466800004ce8000053080000589c000077ac0001686c0002d73c0005b7f80000060005e' +
                '00' * 613).decode('hex')
    track_info_audio = {'channel_count': 2, 'sample_size': 16, 'codec': 'ac3', 'sample_rate': 48000, 'header_ofs': 3, 'type': 'audio'}
    track_info_video0 = {'width': 720, 'codec': 'mpeg-2', 'type': 'video', 'header_ofs': 0, 'height': 480}
    track_info_video = {'width': 720, 'codec': 'mpeg-2', 'type': 'video', 'header_ofs': 25, 'height': 480}
    self.assertEqual(analyze_string('\0\0\1\xba'),
                     {'format': 'mpeg-ps'})
    self.assertEqual(analyze_string(data1),
                     {'format': 'mpeg-ps', 'pes_video_at': 0, 'hdr_skip_count': 0, 'subformat': 'mpeg-2', 'hdr_packet_count': 2, 'hdr_av_packet_count': 1,
                      'tracks': [{'width': 704, 'codec': 'mpeg-2', 'type': 'video', 'header_ofs': 0, 'height': 576}]})
    self.assertEqual(analyze_string(data2),
                     {'format': 'mpeg-ps', 'pes_video_at': 0, 'hdr_skip_count': 0, 'subformat': 'mpeg-1', 'hdr_packet_count': 3, 'hdr_av_packet_count': 1,
                     'tracks': [{'width': 352, 'codec': 'mpeg-1', 'type': 'video', 'header_ofs': 0, 'height': 288}]})
    self.assertEqual(analyze_string(data_video_prev + data_audio + data_dvd + data_video),
                     {'format': 'mpeg-ps', 'hdr_av_packet_count': 3, 'hdr_skip_count': 0, 'subformat': 'dvd-video', 'pes_audio_at': 3, 'hdr_packet_count': 6, 'pes_video_at': 25,
                      'tracks': [track_info_audio, track_info_video]})
    self.assertEqual(analyze_string(data_dvd + data_video + data_audio),
                     {'format': 'mpeg-ps', 'hdr_av_packet_count': 2, 'hdr_skip_count': 0, 'subformat': 'dvd-video', 'pes_audio_at': 3, 'hdr_packet_count': 5, 'pes_video_at': 0,
                      'tracks': [track_info_video0, track_info_audio]})
    self.assertEqual(analyze_string(data_dvd + data_video + data_dvd + data_audio + data_dvd),
                     {'format': 'mpeg-ps', 'hdr_av_packet_count': 2, 'hdr_skip_count': 0, 'subformat': 'dvd-video', 'pes_audio_at': 3, 'hdr_packet_count': 8, 'pes_video_at': 0,
                      'tracks': [track_info_video0, track_info_audio]})
    self.assertEqual(analyze_string(data_audio + data_video),
                     {'format': 'mpeg-ps', 'hdr_av_packet_count': 2, 'hdr_skip_count': 0, 'subformat': 'mpeg-2', 'pes_audio_at': 3, 'hdr_packet_count': 2, 'pes_video_at': 0,
                      'tracks': [track_info_audio, track_info_video0]})
    self.assertEqual(analyze_string(data_audio + data_video + data_dvd),
                     {'format': 'mpeg-ps', 'hdr_av_packet_count': 2, 'hdr_skip_count': 0, 'subformat': 'dvd-video', 'pes_audio_at': 3, 'hdr_packet_count': 5, 'pes_video_at': 0,
                      'tracks': [track_info_audio, track_info_video0]})

  def test_analyze_mpeg_cdxa(self):
    data_hdr = 'RIFF\xc4\x9d\x0b\x02CDXAfmt \x10\0\0\0\0\0\0\0\x11\x11\x58\x41\x02\0\0\0\0\0\0\x00data\xa0\x9d\x0b\x02'
    data_sechdr = '\0\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\0\x03\x40\x46\x02\x02\0\x60\0\x02\0\x60\x00'
    data_null_sector = ''.join((data_sechdr, '\0' * 2324, '????'))
    data_packhdr = '\0\0\1\xba\x21\0\1\x1c\x21\x80\x1b\x91'
    data_video = '\0\0\1\xe0\x00\x5c\x60\x2e\x31\0\1\xfd\x2d\x11\0\1\xb6\xcb\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\1\xb3\x16\0\xf0\xc4\x02\xcf\x60\xa4\0\0\1\xb8'
    data_audio = '\0\0\1\xc0\0\x0b\x40\x20\x21\0\1\xce\x41\xff\xfd\xb0\x84'
    self.assertEqual(analyze_string(data_hdr[:20]),
                     {'format': 'mpeg-cdxa'})
    self.assertEqual(analyze_string(data_hdr[:-8]),
                     {'format': 'mpeg-cdxa'})
    self.assertEqual(analyze_string(data_hdr),
                     {'format': 'mpeg-cdxa'})
    self.assertEqual(analyze_string(data_hdr + data_sechdr),
                     {'format': 'mpeg-cdxa'})
    self.assertEqual(analyze_string(''.join((data_hdr, data_sechdr, '\0\0\1\xba'))),
                     {'format': 'mpeg-cdxa'})
    self.assertEqual(analyze_string(''.join((data_hdr, data_sechdr, data_packhdr, data_video))),
                     {'format': 'mpeg-cdxa', 'pes_video_at': 64, 'hdr_skip_count': 0, 'subformat': 'mpeg-1', 'hdr_packet_count': 1, 'hdr_av_packet_count': 1,
                      'tracks': [{'width': 352, 'codec': 'mpeg-1', 'type': 'video', 'header_ofs': 64, 'height': 240}]})
    self.assertEqual(analyze_string(''.join((data_hdr, data_null_sector, data_null_sector, data_sechdr, data_packhdr, data_video, data_audio))),
                     {'format': 'mpeg-cdxa', 'pes_video_at': 64, 'pes_audio_at': 0, 'hdr_skip_count': 0, 'subformat': 'mpeg-1', 'hdr_packet_count': 2, 'hdr_av_packet_count': 2,
                      'tracks': [{'width': 352, 'codec': 'mpeg-1', 'type': 'video', 'header_ofs': 64, 'height': 240},
                                 {'channel_count': 2, 'codec': 'mp2', 'header_ofs': 0, 'sample_rate': 44100, 'sample_size': 16, 'subformat': 'mpeg-1', 'type': 'audio'}]})

  def test_analyze_rmmp(self):
    data1 = 'RIFF????RMMPcftc0\0\0\0\0\0\0\0cftc0\0\0\0\0\0\0\0\x0c\0\0\0'
    data_cftc_ver = 'ver \6\0\0\0\0\0\0\0\x48\0\0\0'
    data_cftc_dib = 'dib \x2e\0\0\0\0\4\0\0\x5a\0\0\0'
    data_ver = data_cftc_ver[:12] + '??????'
    data_dib = data_cftc_dib[:12] + '\0\0\x28\0\0\0\x80\2\0\0\xe0\1\0\0\1\0\x08\0\1\0\0\0????????????'
    self.assertEqual(analyze_string(data1),
                     {'format': 'rmmp', 'tracks': []}),
    self.assertEqual(analyze_string(''.join((data1, data_cftc_ver, data_cftc_dib, data_ver, data_dib))),
                     {'format': 'rmmp', 'tracks': [{'codec': 'rle', 'height': 480, 'type': 'video', 'width': 640}]})

  def test_analyze_flv(self):
    self.assertEqual(analyze_string('FLV\1\0\0\0\0\x09\0\0\0\0'), {'format': 'flv', 'tracks': []}),
    # TODO(pts): Add tests with audio and video tracks.

  def test_analyze_asf(self):
    self.assertEqual(analyze_string('0&\xb2u\x8ef\xcf\x11\xa6\xd9\0\xaa\x00b\xcel' '\x1e\0\0\0\0\0\0\0' '\0\0\0\0' '\1\2'), {'format': 'asf', 'tracks': []}),
    # TODO(pts): Add tests with audio and video tracks.

  def test_analyze_avi(self):
    self.assertEqual(analyze_string('RIFF????AVI '), {'format': 'avi', 'tracks': []}),
    # TODO(pts): Add tests with audio and video tracks.

  def test_analyze_dv(self):
    self.assertEqual(analyze_string('\x1f\7\0?'), {'format': 'dv', 'tracks': []})
    data = ('1f0700bff8787878ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'  # Block 0.
            '5f0702ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff60ffff20ff6103c8fdff62ffd5e90663ffc1d1e1ffffffffffffffffffffffff'  # Block 1.
           ).decode('hex')
    self.assertEqual(analyze_string(data), {'format': 'dv', 'tracks': [{'type': 'video', 'codec': 'dv', 'width': 720, 'height': 576}]})
    self.assertEqual(analyze_string(data[:80]), {'format': 'dv', 'tracks': []})
    self.assertEqual(analyze_string(data[:80] + ('\x5f\7\2' + '\xff' * 76)), {'format': 'dv', 'tracks': []})  # Block 1 too short.
    self.assertEqual(analyze_string(data[:80] + ('\x5f\7\2' + '\xfe' * 77)), {'format': 'dv', 'tracks': []})  # Bad stype in block 1.
    self.assertEqual(analyze_string(data[:80] + ('\x5f\7\2' + '\xff' * 77)), {'format': 'dv', 'tracks': [{'type': 'video', 'codec': 'dv', 'width': 720, 'height': 576}]})  # QuickTime 3.

  def test_analyze_mpeg_ts(self):
    self.assertEqual(analyze_string('G\0\x10\x10' + '\0' * 184, expect_error=True),
                     {'format': 'mpeg-ts', 'subformat': 'ts', 'tracks': [], 'error': 'Missing mpeg-ts pat payload.', 'hdr_aframes': 0, 'hdr_astreams': 0, 'hdr_ts_packet_count': 1, 'hdr_ts_payload_count': 1, 'hdr_ts_pusi_count': 0, 'hdr_vframes': 0, 'hdr_vstreams': 0})
    data = '474000110000b00d0001c300000001e10076578e5fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff474100110002b0230001c10000f011f0001bf011f00081f100f00c0a04656e6700050441432d334a1fa123ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff475011310790000001c97e1e000001e000008080052100018ca100000109100000000001274d40289a6280f0088fbc07d404040500000303e90000ea60e8c0004c4b0002faf2ef380a0000000128fe3c800000000106000780afc800000300400601510104004008148000000001218882220511161dffce9476e99daf8a53f6aaff59c484622613c2528d9e92c995737ce45d3d500db3e82dfff2ec1f0f6f362ba597fff77cf27fcdedf525fc9cead6ab045328af7f759ba8ee1c6547510011000001bd06088080052100018ca10b7739181c30e1c414ec9200fc2bfb52d49888a4ea87078707d2622293ae94404e25d28809c49aaae3214e84aa12e5ed92d27f5c8437cfab3dd70d33d88862499da953aa736df4441712aa56e2b5f7ea9ef4e953f4ab61c37b4dfb8af5e0bf86a5f7a95daa736df4441712aa56e2b5f7ea9effbe1c3736d33f72fdfa4c0fb59db0a5f7fbe1c3736d33f72fdfa4c0fb59db0a5f7727be5bd0993264c99326400c7b99b93f2fee8f583d74'.decode('hex')
    self.assertEqual(len(data) % 188, 0)
    self.assertEqual(analyze_string(data),
                     {'format': 'mpeg-ts', 'subformat': 'ts', 'hdr_vstreams': 1, 'hdr_ts_packet_count': 4, 'hdr_ts_payload_count': 4, 'hdr_vframes': 1, 'hdr_astreams': 1, 'hdr_ts_pusi_count': 4, 'hdr_aframes': 1,
                      'tracks': [{'width': 1920, 'codec': 'h264', 'type': 'video', 'height': 1080},
                                 {'sample_size': 16, 'codec': 'ac3', 'sample_rate': 48000, 'channel_count': 5, 'type': 'audio'}]})
    data2 = '\0???' + '????'.join(data[i : i + 188] for i in xrange(0, len(data), 188))
    self.assertEqual(analyze_string(data2),
                     {'format': 'mpeg-ts', 'subformat': 'bdav', 'hdr_vstreams': 1, 'hdr_ts_packet_count': 4, 'hdr_ts_payload_count': 4, 'hdr_vframes': 1, 'hdr_astreams': 1, 'hdr_ts_pusi_count': 4, 'hdr_aframes': 1,
                      'tracks': [{'width': 1920, 'codec': 'h264', 'type': 'video', 'height': 1080},
                                 {'sample_size': 16, 'codec': 'ac3', 'sample_rate': 48000, 'channel_count': 5, 'type': 'audio'}]})

  def test_detect_midi(self):
    data1 = 'MThd\0\0\0\6\0\0\0\1'
    data2 = 'MThd\0\0\0\6\0\2\3'
    self.assertEqual(analyze_string(data1), {'format': 'midi'})
    self.assertEqual(analyze_string(data2), {'format': 'midi'})
    self.assertEqual(analyze_string('RIFF\x1a\x69\x08\0RMIDdata\x76\0\0\0' + data2), {'format': 'midi-rmid'})

  def test_analyze_wav(self):
    data_riff = 'RIFF\x44\xc2\1\0WAVE'
    data_pcm = 'fmt \x12\0\0\0\1\0\1\0\x11\x2b\0\0\x22\x56\0\0\2\0\x10\0'
    data_mp3 = 'fmt \x1e\0\0\0\x55\0\1\0\x40\x1f\0\0\xd0\x07\0\0 \1\0\0\0'
    data_bext = 'bext\5\0\0\0??????'  # Round 5 to 6, to word boundary.
    self.assertEqual(analyze_string(data_riff + data_pcm),
                     {'format': 'wav', 'tracks': [{'channel_count': 1, 'codec': 'pcm', 'type': 'audio', 'sample_rate': 11025, 'sample_size': 16}]}),
    self.assertEqual(analyze_string(data_riff + data_mp3),
                     {'format': 'wav', 'tracks': [{'channel_count': 1, 'codec': 'mp3', 'type': 'audio', 'sample_rate': 8000, 'sample_size': 16}]})
    self.assertEqual(analyze_string(data_riff + data_bext),
                     {'format': 'wav', 'tracks': []})
    self.assertEqual(analyze_string(''.join((data_riff, data_bext, data_bext, data_mp3))),
                     {'format': 'wav', 'tracks': [{'channel_count': 1, 'codec': 'mp3', 'type': 'audio', 'sample_rate': 8000, 'sample_size': 16}]})
    self.assertEqual(analyze_string(''.join((data_riff[:-4] + 'RMP3', data_bext, data_bext, 'bext\xff\0\0\0' + '?' * 256, data_mp3))),
                     {'format': 'wav', 'tracks': [{'channel_count': 1, 'codec': 'mp3', 'type': 'audio', 'sample_rate': 8000, 'sample_size': 16}]})

  def test_analyze_aiff(self):
    data1 = 'FORM\0\1\2\3AIFFCOMM\0\0\0\x12\0\2????\0\x0a\x40\x0e\xac\x44\0\0\0\0\0\0'
    data2 = 'FORM\0\1\2\3AIFFCOMM\0\0\0\x12\0\1????\0\x08\x40\x0c\xad\xdd\x17\x44\0\0\0\0'
    self.assertEqual(analyze_string(data1),
                     {'format': 'aiff', 'tracks': [{'type': 'audio', 'codec': 'pcm', 'channel_count': 2, 'sample_rate': 44100, 'sample_size': 10}]})
    self.assertEqual(analyze_string(data1[:20]),
                     {'format': 'aiff', 'tracks': [{'type': 'audio', 'codec': 'pcm'}]})
    self.assertEqual(analyze_string(data2),
                     {'format': 'aiff', 'tracks': [{'type': 'audio', 'codec': 'pcm', 'channel_count': 1, 'sample_rate': 11127, 'sample_size': 8}]})

  def test_analyze_aifc(self):
    data1 = 'FORM\0\1\2\3AIFCFVER\0\0\0\4????COMM\0\0\0\x20\0\2????\0\x0a\x40\x0e\xac\x44\0\0\0\0\0\0none'
    data2 = 'FORM\0\1\2\3AIFCCOMM\0\0\0\x20\0\2????\0\x10\x40\x0b\xfa\0\0\0\0\0\0\0ulaw\x08\xb5law 2:1\0'
    self.assertEqual(analyze_string(data1),
                     {'format': 'aifc', 'tracks': [{'type': 'audio', 'codec': 'pcm', 'channel_count': 2, 'sample_rate': 44100, 'sample_size': 10}]})
    self.assertEqual(analyze_string(data1[:19]),
                     {'format': 'aifc', 'tracks': [{'type': 'audio'}]})
    self.assertEqual(analyze_string(data2),
                     {'format': 'aifc', 'tracks': [{'type': 'audio', 'codec': 'mulaw', 'channel_count': 2, 'sample_rate': 8000, 'sample_size': 16}]})

  def test_analyze_au(self):
    data1 = '.snd\0\0\0\x1c\0\1\x6b\xf5\0\0\0\1\0\0\x1f\x40\0\0\0\1'
    self.assertEqual(analyze_string(data1),
                     {'format': 'au', 'tracks': [{'type': 'audio', 'codec': 'mulaw', 'channel_count': 1, 'sample_rate': 8000, 'sample_size': 8}]})

  def test_analyze_ftc(self):
    data1 = 'FTC\0\1\1\2\1\x80\2\x90\1\x18\0\1\0'
    self.assertEqual(analyze_string(data1[:8]),
                     {'format': 'ftc', 'codec': 'fractal'})
    self.assertEqual(analyze_string(data1),
                     {'format': 'ftc', 'codec': 'fractal'})

  def test_analyze_fif(self):
    data1 = 'FIF\1\x75\0\3\2\0\0\1\2\0\0'
    self.assertEqual(analyze_string(data1[:4]),
                     {'format': 'fif', 'codec': 'fractal'})
    self.assertEqual(analyze_string(data1),
                     {'format': 'fif', 'codec': 'fractal', 'height': 513, 'width': 515})

  def test_analyze_spix(self):
    data1 = 'spix\3\2\0\0\1\2\0\0(\0\0\0????\0\1\0\0'
    data2 = 'spix\0\0\2\3\0\0\2\1\0\0\0(????\0\0\1\0'
    self.assertEqual(analyze_string(data1),
                     {'format': 'spix', 'codec': 'uncompressed', 'height': 513, 'width': 515})
    self.assertEqual(analyze_string(data2),
                     {'format': 'spix', 'codec': 'uncompressed', 'height': 513, 'width': 515})

  def test_analyze_sgi_rgb(self):
    self.assertEqual(analyze_string('\x01\xda\1\2\0\3\2\3\2\1\0\5'),
                     {'format': 'sgi-rgb', 'codec': 'rle', 'height': 513, 'width': 515})

  def test_analyze_xv_pm(self):
    self.assertEqual(analyze_string('VIEW\0\0\0\4\0\0\2\1\0\0\2\3\0\0\0\1\0\0\x80\1'),
                     {'format': 'xv-pm', 'codec': 'uncompressed', 'height': 513, 'width': 515})
    self.assertEqual(analyze_string('WEIV\4\0\0\0\1\2\0\0\3\2\0\0\1\0\0\0\1\x80\0\0'),
                     {'format': 'xv-pm', 'codec': 'uncompressed', 'height': 513, 'width': 515})

  def test_analyze_imlib_argb(self):
    data1 = 'ARGB 123 45 1\n'
    self.assertEqual(analyze_string(data1),
                     {'format': 'imlib-argb', 'codec': 'uncompressed', 'height': 45, 'width': 123})
    self.assertEqual(analyze_string(data1.replace('\n', '\r\n')),
                     {'format': 'imlib-argb', 'codec': 'uncompressed', 'height': 45, 'width': 123})

  def test_analyze_imlib_eim(self):
    data1 = 'EIM 1\nIMAGE 9'
    data_filename = 'Hello, World!\t\r\fThis is a filename!\r\vThe answer is 42 43'
    data2 = 'EIM 1\nIMAGE 16605 ' + data_filename + ' 123 45 7 6 5 4 3 2 1\n'
    self.assertEqual(analyze_string(data1),
                     {'format': 'imlib-eim', 'codec': 'uncompressed'})
    self.assertEqual(analyze_string(data2),
                     {'format': 'imlib-eim', 'codec': 'uncompressed', 'height': 45, 'width': 123})
    self.assertEqual(analyze_string(data2.replace('\n', '\r\n')),
                     {'format': 'imlib-eim', 'codec': 'uncompressed', 'height': 45, 'width': 123})

  def test_analyze_farbfeld(self):
    data1 = 'farbfeld\0\0\2\3\0\0\2\1'
    self.assertEqual(analyze_string(data1[:8]),
                     {'format': 'farbfeld', 'codec': 'uncompressed'})
    self.assertEqual(analyze_string(data1),
                     {'format': 'farbfeld', 'codec': 'uncompressed', 'height': 513, 'width': 515})

  def test_analyze_wbmp(self):
    data_dimens = '\x84\3\x84\1'
    data1 = '\0\0' + data_dimens
    data2 = '\0\x80\x80\xff\x81\x7f\x00\x7f' + data_dimens
    self.assertEqual(analyze_string(data1),
                     {'format': 'wbmp', 'codec': 'uncompressed', 'height': 513, 'width': 515})
    self.assertEqual(analyze_string(data2),
                     {'format': 'wbmp', 'codec': 'uncompressed', 'height': 513, 'width': 515})
    self.assertEqual(analyze_string('\0\0@\x10'),
                     {'format': 'wbmp', 'codec': 'uncompressed', 'height': 16, 'width': 64})
    self.assertEqual(analyze_string('\0\0@\x0f'),
                     {'format': '?'})  # Dimensions too small.

  def test_analyze_gd(self):
    self.assertEqual(analyze_string('\xff\xfe\2\3\2\1\1'),
                     {'format': 'gd', 'codec': 'uncompressed', 'height': 513, 'width': 515})
    self.assertEqual(analyze_string('\xff\xff\2\3\2\1\0\1\0'),
                     {'format': 'gd', 'codec': 'uncompressed', 'height': 513, 'width': 515})

  def test_analyze_gd2(self):
    self.assertEqual(analyze_string('gd2\0\0\2\2\3\2\1\0\1\0\2\0\1\0\1\0\1\0'),
                     {'format': 'gd2', 'codec': 'flate', 'height': 513, 'width': 515})
    self.assertEqual(analyze_string('gd2\0\0\2\2\3\2\1\0\1\0\3\0\1\0\1\1'),
                     {'format': 'gd2', 'codec': 'uncompressed', 'height': 513, 'width': 515})
    self.assertEqual(analyze_string('gd2\0\0\1\2\3\2\1\0\1\0\3\0\1\0\1\2'),
                     {'format': 'gd2', 'codec': 'uncompressed', 'height': 513, 'width': 515})

  def test_analyze_cups_raster(self):
    data1 = ''.join((
        'RaSt',
        '\0' * 276,
        '\0\0\0\1\0\0\0\1',  # (hw_resolution_x, hw_resolution_y).
        '\0' * 68,
        '\0\0\4\3\0\0\4\1',  # (pt_width, pt_height).
        '\0' * 12,
        '\0\0\2\3\0\0\2\1',  # (cups_width, cups_height).
        '\0\0\0\0',  # cups_media_type.
        '\0\0\0\1\0\0\0\1\0\0\0\1',  # (cups_bits_per_color, cups_bits_per_pixel, cups_bytes_per_line).
        '\0' * 8,
    ))
    # If detect_format returns '?', then comment it out, and
    # analyze_cups_raster will report a detailed error.
    self.assertEqual(analyze_string(data1[:4]),
                     {'format': 'cups-raster'})
    self.assertEqual(analyze_string(data1),
                     {'format': 'cups-raster', 'height': 513, 'width': 515, 'pt_height': 1025, 'pt_width': 1027})

  def test_analyze_alias_pix(self):
    self.assertEqual(analyze_string('\2\3\2\1\0\0\0\0\0\x18'),
                     {'format': 'alias-pix', 'codec': 'rle', 'height': 513, 'width': 515})

  def test_analyze_photocd(self):
    self.assertEqual(analyze_string(''.join(('\xff' * 32, '\0' * 2016, 'PCD_IPI'))),
                     {'format': 'photocd', 'codec': 'photocd', 'height': 768, 'width': 512})

  def test_analyze_fits(self):
    data1 = ''.join(s + ' ' * (80 - len(s)) for s in (
        "SIMPLE  =      T / Fits standard\nBITPIX  = -32 / Bits per pixel\nNAXIS   =  2 / Number of axes\nNAXIS1  =   515\nNAXIS2  =  513/ Axis Length\nOBJECT  = 'Cassiopeia A'\nEND".split('\n')))
    self.assertEqual(analyze_string('SIMPLE  = T'),
                     {'format': 'fits'})
    self.assertEqual(analyze_string('SIMPLE  =  T'),
                     {'format': 'fits'})
    self.assertEqual(analyze_string(data1[:80] + 'END' + ' ' * 77),
                     {'format': 'fits'})
    self.assertEqual(analyze_string(data1),
                     {'format': 'fits', 'height': 513, 'width': 515})

  def test_analyze_xloadimage_niff(self):
    data1 = 'NIFF\0\0\0\1\0\0\2\3\0\0\2\1'
    self.assertEqual(analyze_string(data1[:8]),
                     {'format': 'xloadimage-niff', 'codec': 'uncompressed'})
    self.assertEqual(analyze_string(data1),
                     {'format': 'xloadimage-niff', 'codec': 'uncompressed', 'height': 513, 'width': 515})

  def test_analyze_sun_taac(self):
    data1 = 'ncaa\nrank = 2;\rsize=123 45;  \nanswer = 42\n\f\nsize = 2 22\n'
    self.assertEqual(analyze_string(data1[:6]),
                     {'format': 'sun-taac', 'codec': 'uncompressed'})
    self.assertEqual(analyze_string(data1),
                     {'format': 'sun-taac', 'codec': 'uncompressed', 'height': 45, 'width': 123})

  def test_analyze_facesaver(self):
    data1 = 'FirstName: a\nLastName: b\r\nE-mail: \nTelephone:\nPicData: 123 45 8\r\nDate: 42\n\r\nPicData: 2 22 8\n\n\n'
    self.assertEqual(analyze_string(data1[:data1.find(':') + 1]),
                     {'format': 'facesaver', 'codec': 'uncompressed'})
    self.assertEqual(analyze_string(data1),
                     {'format': 'facesaver', 'codec': 'uncompressed', 'height': 45, 'width': 123})

  def test_analyze_mcidas_area(self):
    data1 = '\0\0\0\0\4\0\0\0\xb4\0\0\0\xcf\xc5\1\0\xfc\xc4\2\0\x2c\x0a\0\0\x38\x23\0\0\0\0\0\0\1\2\0\0\3\2\0\0'
    self.assertEqual(analyze_string(data1[:24]),
                     {'format': 'mcidas-area', 'codec': 'uncompressed'})
    self.assertEqual(analyze_string(data1),
                     {'format': 'mcidas-area', 'codec': 'uncompressed', 'height': 513, 'width': 515})
    self.assertEqual(analyze_string(struct.pack('>10L', *struct.unpack('<10L', data1))),
                     {'format': 'mcidas-area', 'codec': 'uncompressed', 'height': 513, 'width': 515})

  def test_analyze_macpaint(self):
    data_macbinary1 = '\0\x11Name of this file\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\x00PNTGMPNT\1\0\0\0\0\0\0\0\x80\0\0\0\x82\0\0\0\0\0\x99\xd4\x89\0\x99\xd4\x89\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0'
    self.assertEqual(analyze_string(data_macbinary1),
                     {'format': 'macpaint', 'detected_format': 'macbinary', 'subformat': 'macbinary', 'codec': 'rle', 'height': 720, 'width': 576})
    self.assertEqual(analyze_string('\0\0\0\2\0\0\0\0\0\0\0\0'),
                     {'format': 'macpaint', 'codec': 'rle', 'height': 720, 'width': 576})
    self.assertEqual(analyze_string('\0\0\0\3\xff\xff\xff\xff\xff\xff\xff\xff'),
                     {'format': 'macpaint', 'codec': 'rle', 'height': 720, 'width': 576})

  def test_analyze_fit(self):
    self.assertEqual(analyze_string('IT01\0\0\2\3\0\0\2\1\0\0\0\1'),
                     {'format': 'fit', 'height': 513, 'width': 515})

  def test_analyze_icns(self):
    data1 = 'icns\0\0\0@icm#\0\0\x008????????????????????????????????????????????????'
    data2 = 'icns\0\0\0Aicm#\0\0\x009?????????????????????????????????????????????????'
    self.assertEqual(analyze_string(data1[:8]),
                     {'format': 'icns', 'icon_count': 0})
    self.assertEqual(analyze_string(data1),
                     {'format': 'icns', 'subformat': 'icm#', 'codec': 'uncompressed', 'height': 12, 'width': 16, 'icon_count': 1})
    self.assertEqual(analyze_string(data2),
                     {'format': 'icns', 'subformat': 'icm#', 'codec': 'rle', 'height': 12, 'width': 16, 'icon_count': 1})
    self.assertEqual(analyze_string('icns\0\0\0aicm#\0\0\x009?????????????????????????????????????????????????ic07\0\0\0 \x89PNG\r\n\x1a\n\0\0\0\rIHDR\0\0\0\x0f\0\0\0\x0d'),
                     {'format': 'icns', 'subformat': 'ic07', 'codec': 'flate', 'height': 13, 'width': 15, 'icon_count': 2})
    self.assertEqual(analyze_string('icns\0\0\0aicm#\0\0\x009?????????????????????????????????????????????????ic07\0\0\0 \x89PNG\r\n\x1a\n\0\0\0\rIHDR\0\0\0\x0f\0\0\0\x0c'),  # PNG in ic07 has smaller dimensions, using icm#.
                     {'format': 'icns', 'subformat': 'icm#', 'codec': 'rle', 'height': 12, 'width': 16, 'icon_count': 2})

  def test_analyze_dds(self):
    self.assertEqual(analyze_string('DDS |\0\0\0????\1\2\0\0\3\2\0\0???????????????????????????????????????????????????????? \0\0\0\4\0\0\0DXT5'),
                     {'format': 'dds', 'codec': 'dxt5', 'height': 513, 'width': 515})

  def test_analyze_jpeg(self):
    data1 = '\xff\xd8\xff\xdb\x00\xc5\x00\x04\x03\x04\x05\x04\x03\x05\x05\x04\x05\x06\x06\x05\x06\x08\x0e\t\x08\x07\x07\x08\x11\x0c\r\n\x0e\x15\x12\x16\x15\x14\x12\x14\x13\x17\x1a!\x1c\x17\x18\x1f\x19\x13\x14\x1d\'\x1d\x1f"#%%%\x16\x1b)+($+!$%#\x01\x04\x06\x06\x08\x07\x08\x11\t\t\x11#\x17\x13\x14##################################################\x02\x04\x06\x06\x08\x07\x08\x11\t\t\x11#\x17\x13\x14##################################################\xff\xc0\x00\x11\x08\x00x\x00\xa0\x03\x01!\x00\x02\x11\x01\x03\x11\x02'
    self.assertEqual(analyze_string(data1[:3], analyze_func=mediafileinfo_detect.analyze_jpeg),
                     {'format': 'jpeg', 'detected_format': 'short3', 'detected_analyze': None, 'codec': 'jpeg'})
    self.assertEqual(analyze_string(data1[:4]),
                     {'format': 'jpeg', 'codec': 'jpeg'})
    self.assertEqual(analyze_string(data1[:5], expect_error=True),
                     {'format': 'jpeg', 'codec': 'jpeg', 'error': 'EOF in jpeg first.'})
    self.assertEqual(analyze_string(data1),
                     {'format': 'jpeg', 'codec': 'jpeg', 'height': 120, 'width': 160})
    data2 = data1[:2] + '\xff\xfe\0\5???' + data1[2:]  # Add COM marker.
    self.assertEqual(analyze_string(data2),
                     {'format': 'jpeg', 'codec': 'jpeg', 'height': 120, 'width': 160})
    data3 = data1[:2] + '\xff\xfe\0\5???+' '\xff\xfe\0\5???\0\0' + data1[2:]  # Add COM markers with extra + and \0\0.
    self.assertEqual(analyze_string(data3),
                     {'format': 'jpeg', 'codec': 'jpeg', 'height': 120, 'width': 160})

  def test_analyze_gif(self):
    self.assertEqual(analyze_string('GIF89a'),
                     {'format': 'gif', 'codec': 'lzw'})
    self.assertEqual(analyze_string('GIF89a\3\2\1\2'),
                     {'format': 'gif', 'codec': 'lzw', 'height': 513, 'width': 515})
    self.assertEqual(analyze_string('GIF87a\3\2\1\2\0??\x2c\0\0\0\0\0\0\0\0\0\0\0\x2c'),
                     {'format': 'agif', 'detected_format': 'gif', 'codec': 'lzw', 'height': 513, 'width': 515})
    self.assertEqual(analyze_string('GIF87a\3\2\1\2\0??!\1\5?????\2??\0\x2c\0\0\0\0\0\0\0\0\0\0\0\x2c'),
                     {'format': 'agif', 'detected_format': 'gif', 'codec': 'lzw', 'height': 513, 'width': 515})

  def test_analyze_ani(self):
    data1 = 'RIFF????ACONLIST\x2e\0\0\0INFOINAM\x14\0\0\0Disappearing Cheese\0IART\6\0\0\0lynne\0anih' + '24000000240000001800000019000000000000000000000000000000000000000a0000000300000072617465640000000a0000000a0000000a0000000a0000000a0000000a0000000a0000000a000000320000000a0000000a0000000a0000003c0000000a0000000a0000000a0000000a0000000a000000320000000a0000000a0000000a0000002800000005000000640000007365712064000000000000000100000002000000030000000400000005000000060000000700000008000000090000000a0000000b0000000c0000000d0000000e0000000f0000000e00000010000000110000001200000013000000140000001500000016000000170000004c495354944800006672616d69636f6efe0200000000020001002120000000000000e802000016000000'.decode('hex')
    self.assertEqual(analyze_string(data1[:16]),
                     {'format': 'ani', 'tracks': []})
    self.assertEqual(analyze_string(data1),
                     {'format': 'ani', 'tracks': [{'type': 'video', 'codec': 'uncompressed', 'width': 33, 'height': 32}]})

  def test_analyze_mkv(self):
    self.assertEqual(analyze_string('\x1a\x45\xdf\xa3'),
                     {'format': 'mkv', 'tracks': []})
    self.assertEqual(analyze_string('\x1aE\xdf\xa3\x01\0\0\0\0\0\0\x1fB\x86\x81\x01B\xf7\x81\x01B\xf2\x81\x04B\xf3\x81\x08B\x82\x84webmB\x87\x81\x02B\x85\x81\x02'),
                     {'format': 'webm', 'detected_format': 'mkv', 'subformat': 'webm', 'brands': ['mkv', 'webm'], 'tracks': []})

  def test_detect_xar(self):
    data1 = 'XARA\xa3\xa3\r\n\2\0\0\0\x25\0\0\0CXN????\0\0\0\0'
    self.assertEqual(analyze_string(data1), {'format': 'xara'})

  def test_detect_cdr(self):
    data1 = 'RIFF????CDR9vrsn\2\0\0\0DISP'
    self.assertEqual(analyze_string(data1), {'format': 'cdr'})
    self.assertEqual(analyze_string(data1[:20]), {'format': 'cdr'})

  def test_analyze_amv(self):
    data1 = 'RIFF????AMV LIST????hdrlamvh8\0\0\0' + '\0' * 32 + '\3\2\0\0\1\2\0\0'
    self.assertEqual(analyze_string(data1[:32]),
                     {'format': 'amv', 'tracks': []})
    self.assertEqual(analyze_string(data1),
                     {'format': 'amv',
                      'tracks': [{'type': 'video', 'codec': 'mjpeg', 'width': 515, 'height': 513},
                                 {'type': 'audio', 'codec': 'adpcm'}]})

  def test_analyze_4xm(self):
    data1 = 'RIFF????4XMVLIST\x72\1\0\0HEADLIST\x6e\0\0\0HNFOname)\x00\x00\x00E:\\brett\\ToyStory2\\test_240x112x6_8k.4xa\x00\x00info\x1f\x00\x00\x00Packed with 4xmovie v. 1.0.0.3\x00\x00std_\x08\x00\x00\x00\xf3&\x00\x00\x00\x00\xc8@LIST\xf0\x00\x00\x00TRK_LIST~\x00\x00\x00VTRKname&\x00\x00\x00E:\\brett\\ToyStory2\\test_240x112x6.avi\x00vtrkD\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x03\x00\x00\x00\xdd\x06\x00\x00\x00\x00\x00\x00\xdc\x06\x00\x00\xf0\x00\x00\x00p\x00\x00\x00\xf0\x00\x00\x00p\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00LIST^\x00\x00\x00STRKname"\x00\x00\x00E:\\brett\\ToyStory2\\TS2_7884Hz.wav\x00strk(\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00\x00\x00\x00\x01\x00\x03\x00\x00\x00\xdd\x06\x00\x00\x00\x00\x00\x00\xdc\x06\x00\x00\x01\x00\x00\x00\xcc\x1e\x00\x00\x10\x00\x00\x00'
    self.assertEqual(analyze_string(data1[:36]),
                     {'format': '4xm', 'tracks': []})
    self.assertEqual(analyze_string(data1),
                     {'format': '4xm',
                      'tracks': [{'type': 'video', 'codec': '4xm', 'width': 240, 'height': 112},
                                 {'type': 'audio', 'codec': 'adpcm2', 'channel_count': 1, 'sample_rate': 7884, 'sample_size': 16}]})

  def test_analyze_fpx(self):
    data1 = ''.join((
        '\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1',  # olecf magic.
        '\0' * 20,
        '\xfe\xff',  # byte_order.
        '\x09\0',  # sector_shift.
        '\0' * 16,
        '\1\0\0\0',  # sect_dir_start.
        '\0' * 972,
        'R\0' + '\0' * 62,
        '\x16\0\5\0\xff\xff\xff\xff\xff\xff\xff\xff\3\0\0\0',
        '\x00\x67\x61\x56\x54\xc1\xce\x11\x85\x53\x00\xaa\x00\xa1\xf9\x5b',  #  clsid.
    ))
    self.assertEqual(analyze_string(data1[:8]),
                     {'format': 'olecf'})
    self.assertEqual(analyze_string(data1),
                     {'format': 'fpx', 'detected_format': 'olecf'})

  def test_analyze_binhex(self):
    self.assertEqual(analyze_string('(Convert with\r#TEXT$\n***RESOURCE'),
                     {'format': 'binhex', 'subformat': 'hex', 'codec': 'uncompressed'})
    self.assertEqual(analyze_string('(Convert with\r#TEXT$\n\n\n***COMPRESSED'),
                     {'format': 'binhex', 'subformat': 'hcx', 'codec': 'uncompressed'})
    self.assertEqual(analyze_string('(This file must be converted; you knew that already.)\n\n:'),
                     {'format': 'binhex', 'subformat': 'hqx', 'codec': 'rle'})

  def test_analyze_flate(self):
    self.assertEqual(analyze_string('\x08\x9c', analyze_func=mediafileinfo_detect.analyze_flate),
                     {'format': 'flate', 'detected_format': 'short2', 'detected_analyze': None, 'codec': 'flate'})
    self.assertEqual(analyze_string('\x18\xda', analyze_func=mediafileinfo_detect.analyze_flate),
                     {'format': 'flate', 'detected_format': 'short2', 'detected_analyze': None, 'codec': 'flate'})
    self.assertEqual(analyze_string('\x28\x01', analyze_func=mediafileinfo_detect.analyze_flate),
                     {'format': 'flate', 'detected_format': 'short2', 'detected_analyze': None, 'codec': 'flate'})
    self.assertEqual(analyze_string('\x38\x5e', analyze_func=mediafileinfo_detect.analyze_flate),
                     {'format': 'flate', 'detected_format': 'short2', 'detected_analyze': None, 'codec': 'flate'})
    self.assertEqual(analyze_string('\x78\x9c??'),
                     {'format': 'flate', 'codec': 'flate'})

  def test_analyze_gz(self):
    self.assertEqual(analyze_string('\x1f\x8b\x08', analyze_func=mediafileinfo_detect.analyze_gz),
                     {'format': 'gz', 'detected_format': 'short3', 'detected_analyze': None, 'codec': 'flate'})
    self.assertEqual(analyze_string('\x1f\x8b\x08?'),
                     {'format': 'gz', 'codec': 'flate'})

  def test_analyze_xz(self):
    self.assertEqual(analyze_string('\xfd7zXZ\0'),
                     {'format': 'xz', 'codec': 'lzma'})

  def test_analyze_lzma(self):
    self.assertEqual(analyze_string('\x5d\0\0?????????\0'),
                     {'format': 'lzma', 'codec': 'lzma'})
    self.assertEqual(analyze_string('\x5d\0\0?????????\xff'),
                     {'format': 'lzma', 'codec': 'lzma'})

  def test_analyze_exe(self):
    self.assertEqual(analyze_string('MZ\xff\1' + '?' * 28),
                     {'format': 'dosexe', 'detected_format': 'exe', 'subformat': 'dos-weird-reloc', 'arch': '8086', 'binary_type': 'executable', 'endian': 'little', 'os': 'dos'})
    data1 = ''.join(('MZ\xff\1', '?' * 20, '\x3f\0', '?' * 6))
    self.assertEqual(analyze_string(data1),
                     {'format': 'dosexe', 'detected_format': 'exe', 'subformat': 'dos', 'arch': '8086', 'binary_type': 'executable', 'endian': 'little', 'os': 'dos'})
    self.assertEqual(mediafileinfo_detect.count_is_exe(data1), 336)
    self.assertEqual(analyze_string(''.join(('MZ\xff\1', '?' * 20, '\0\2', '?' * 6))),
                     {'format': 'dosexe', 'detected_format': 'exe', 'subformat': 'dos', 'arch': '8086', 'binary_type': 'executable', 'endian': 'little', 'os': 'dos'})
    self.assertEqual(analyze_string(''.join(('MZ\0\0\1\0\0\0', '?' * 16, '>TIPPACH'))),
                     {'format': 'dosxexe', 'detected_format': 'exe', 'subformat': 'wdosx', 'arch': 'i386', 'binary_type': 'executable', 'endian': 'little', 'os': 'dos'})
    self.assertEqual(analyze_string(''.join(('MZ\0\0\1\0', '?' * 22,  'PMODSTUB.EXE generated '))),
                     {'format': 'dosxexe', 'detected_format': 'exe', 'subformat': 'pmodedj', 'arch': 'i386', 'binary_type': 'executable', 'endian': 'little', 'os': 'dos'})
    self.assertEqual(analyze_string(''.join(('MZ\0\0\1\0\1\0', '?' * 16,  ' \0??????????\0\0\0\0\r\nCWSDPMI '))),
                     {'format': 'dosxexe', 'detected_format': 'exe', 'subformat': 'cwsdpmi', 'arch': 'i386', 'binary_type': 'executable', 'endian': 'little', 'os': 'dos'})
    self.assertEqual(analyze_string(''.join(('MZ\0\0\1\0\0\0', '?' * 14,  '\0' * 42, '\r\nstub.h generated from '))),
                     {'format': 'dosxexe', 'detected_format': 'exe', 'subformat': 'djgpp', 'arch': 'i386', 'binary_type': 'executable', 'endian': 'little', 'os': 'dos'})
    self.assertEqual(analyze_string(''.join(('MZ\0\0\1\0\0\0\2\0', '\0' * (512 - 10), '?' * (597 - 512), '\0\0\0\0\0\0\0DOS/4G  ', '?' * 12))),
                     {'format': 'dosxexe', 'detected_format': 'exe', 'subformat': 'dos4gw', 'arch': 'i386', 'binary_type': 'executable', 'endian': 'little', 'os': 'dos'})
    self.assertEqual(analyze_string(''.join(('MZ\0\0\1\0\0\0\2\0', '\0' * 12, 'x', '\0' * (512 - 10 - 13 - 72), '??????????Can\'t run DOS/4G(W)\r\n$\tDOS4GPATH\4PATHDOS4GW.EXE\0DOS4G.EXE\0????'))),
                     {'format': 'dosxexe', 'detected_format': 'exe', 'subformat': 'watcom', 'arch': 'i386', 'binary_type': 'executable', 'endian': 'little', 'os': 'dos'})
    self.assertEqual(analyze_string(''.join(('MZ\0\0\1\0\0\0\4\0', '\0' * 14, '@\0', '\0' * (6 + 32), '?' * (512 - 64 - 48), 'PATH=\r\ncannot find loader DPMILD32.EXE$\0\0\0\0\0\0\0\0\0'))),
                     {'format': 'dosxexe', 'detected_format': 'exe', 'subformat': 'hx', 'arch': 'i386', 'binary_type': 'executable', 'endian': 'little', 'os': 'dos'})
    self.assertEqual(analyze_string(''.join(('MZ\0\0\1\0\0\0\2\0', '\0' * 22, '?' * 20, 'PMODE/W v1.'))),
                     {'format': 'dosxexe', 'detected_format': 'exe', 'subformat': 'pmodew', 'arch': 'i386', 'binary_type': 'executable', 'endian': 'little', 'os': 'dos'})
    self.assertEqual(analyze_string(''.join(('MZ\0\0\1\0\0\0\2\0', '\0' * 22, '\xfa\x16\x1f\x26\xa1\x02\x00\x83\xe8\x40\x8e\xd0\xfb\x06\x16\x07'))),
                     {'format': 'dosxexe', 'detected_format': 'exe', 'subformat': 'causeway', 'arch': 'i386', 'binary_type': 'executable', 'endian': 'little', 'os': 'dos'})
    self.assertEqual(analyze_string(''.join(('MZ\0\0\1\0\0\0\3\0', '\0' * 38, '\n\rFatal error, DPMI host does not support 32 bit applications$\n\r'))),
                     {'format': 'dosxexe', 'detected_format': 'exe', 'subformat': 'x32vm', 'arch': 'i386', 'binary_type': 'executable', 'endian': 'little', 'os': 'dos'})
    self.assertEqual(analyze_string(''.join(('MZ\0\0\1\0\0\0\2\0', '\0' * 22, 'STUB/32A\0Copyright (C) 1996-'))),
                     {'format': 'dosxexe', 'detected_format': 'exe', 'subformat': 'dos32a', 'arch': 'i386', 'binary_type': 'executable', 'endian': 'little', 'os': 'dos'})
    self.assertEqual(analyze_string(''.join(('MZ\0\0\1\0\0\0\2\0', '\0' * 22, 'ID32', '?' * 24, 'STUB/32C\0Copyright (C) 1996-'))),
                     {'format': 'dosxexe', 'detected_format': 'exe', 'subformat': 'dos32a', 'arch': 'i386', 'binary_type': 'executable', 'endian': 'little', 'os': 'dos'})
    self.assertEqual(analyze_string(''.join(('MZ\0\0\1\0\0\0\2\0', '\0' * 22, 'ID32', '?' * 24, 'DOS/32A\0Copyright (C) 1996-'))),
                     {'format': 'dosxexe', 'detected_format': 'exe', 'subformat': 'dos32a', 'arch': 'i386', 'binary_type': 'executable', 'endian': 'little', 'os': 'dos'})
    data2 = ''.join(('MZ\xff\1', '?' * 56, 'A\0\0\0?PE\0\0', '?' * 20))
    self.assertEqual(analyze_string(data2),
                     {'format': 'pe-coff', 'detected_format': 'exe', 'subformat': 'pe', 'arch': '0x3f3f', 'endian': 'little'})
    self.assertEqual(mediafileinfo_detect.count_is_exe(data2), 926)
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?PE\0\0\x4c\1', '?' * 14, '\x18\0??\1\2'))),
                     {'format': 'pe', 'subformat': 'pe', 'detected_format': 'exe', 'binary_type': '0x201', 'arch': 'i386', 'endian': 'little'})
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?PE\0\0\x4c\1', '?' * 14, '\x18\0??\7\1'))),
                     {'format': 'pe', 'subformat': 'rom-image', 'detected_format': 'exe', 'arch': 'i386', 'binary_type': 'rom-image', 'endian': 'little'})
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?PE\0\0\x4c\1', '?' * 14, '\x60\0??\x0b\1', '?' * 90, '\0\0\0\0'))),
                     {'format': 'windll', 'subformat': 'pe32', 'detected_format': 'exe', 'arch': 'i386', 'binary_type': 'shlib', 'endian': 'little', 'os': 'windows'})
    data_pe_exe = ''.join(('PE\0\0\x4c\1', '?' * 14, '\x60\0\2\0\x0b\1', '?' * 90, '\0\0\0\0'))
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?', data_pe_exe))),
                     {'format': 'winexe', 'subformat': 'pe32', 'detected_format': 'exe', 'arch': 'i386', 'binary_type': 'executable', 'endian': 'little', 'os': 'windows'})
    self.assertEqual(analyze_string(''.join(('MZ\0\0\1\0\0\0\4\0', '\0' * 14, '@\0', '\0' * 34, '\0\2\0\0', '?' * (512 - 64 - 48), 'PATH=\r\ncannot find loader DPMILD32.EXE$\0\0\0\0\0\0\0\0\0', data_pe_exe))),
                     {'format': 'winexe', 'subformat': 'pe32-hx', 'detected_format': 'exe', 'arch': 'i386', 'binary_type': 'executable', 'endian': 'little', 'os': 'windows'})
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?PE\0\0\x4c\1', '?' * 14, '\x70\0??\x0b\2', '?' * 106, '\0\0\0\0'))),
                     {'format': 'windll', 'subformat': 'pe32+', 'detected_format': 'exe', 'arch': 'i386', 'binary_type': 'shlib', 'endian': 'little', 'os': 'windows'})
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?PE\0\0\x4c\1', '?' * 14, '\x70\0\2\0\x0b\2', '?' * 106, '\0\0\0\0'))),
                     {'format': 'winexe', 'subformat': 'pe32+', 'detected_format': 'exe', 'arch': 'i386', 'binary_type': 'executable', 'endian': 'little', 'os': 'windows'})
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?PE\0\0\x4c\1', '?' * 14, '\x70\0??\x0b\2', '?' * 66, '\x0a\00', '?' * 38, '\0\0\0\0'))),
                     {'format': 'efidll', 'subformat': 'pe32+', 'detected_format': 'exe', 'arch': 'i386', 'binary_type': 'shlib', 'endian': 'little', 'os': 'efi'})
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?PE\0\0\x4c\1', '?' * 14, '\x70\0\2\0\x0b\2', '?' * 66, '\x0a\00', '?' * 38, '\0\0\0\0'))),
                     {'format': 'efiexe', 'subformat': 'pe32+', 'detected_format': 'exe', 'arch': 'i386', 'binary_type': 'executable', 'endian': 'little', 'os': 'efi'})
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?NE\5\1????????\0\0', '?' * 40, '\2'))),
                     {'format': 'winexe', 'subformat': 'ne', 'detected_format': 'exe', 'arch': '8086', 'binary_type': 'executable', 'endian': 'little', 'os': 'windows'})
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?NE\5\1????????\0\x80', '?' * 40, '\2'))),
                     {'format': 'windll', 'subformat': 'ne', 'detected_format': 'exe', 'arch': '8086', 'binary_type': 'shlib', 'endian': 'little', 'os': 'windows'})
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?NE\5\1????????\0\0', '?' * 40, '\1'))),
                     {'format': 'os2exe', 'subformat': 'ne', 'detected_format': 'exe', 'arch': '80286', 'binary_type': 'executable', 'endian': 'little', 'os': 'os2'})
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?NE\5\1????????\0\x80', '?' * 40, '\1'))),
                     {'format': 'os2dll', 'subformat': 'ne', 'detected_format': 'exe', 'arch': '80286', 'binary_type': 'shlib', 'endian': 'little', 'os': 'os2'})
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?PE\0\0\x64\x86\0\0', '?' * 12, '\x18\0\0\0\x0b\1', '?' * 22))),
                     {'format': 'pe-nonexec', 'subformat': 'pe32', 'detected_format': 'exe', 'arch': 'amd64', 'endian': 'little'})
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?PE\0\0\x64\x86\1\0', '?' * 12, '\x18\0\0\0\x0b\1', '?' * 22, '.its\0\0\0\0\x50\0\0\0\x52\0\0\0', '?' * 24))),
                     {'format': 'pe-nonexec', 'subformat': 'pe32', 'detected_format': 'exe', 'arch': 'amd64', 'endian': 'little'})
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?PE\0\0\x64\x86\1\0', '?' * 12, '\x18\0\0\0\x0b\1', '?' * 22, '.its\0\0\0\0\x50\0\0\0\x52\0\0\0', '?' * 24, '-' * 9, self.HXS_HEADER))),
                     {'format': 'hxs', 'subformat': 'pe32', 'detected_format': 'exe', 'arch': 'amd64'})
    data3 = ''.join(('MZ?\0', '?' * 56, 'A\0\0\0?', 'LX\0\0\0\0\0\0\2\0\1\0????\0\0\0\0'))
    self.assertEqual(analyze_string(data3),
                     {'format': 'os2exe', 'subformat': 'lx', 'detected_format': 'exe', 'arch': 'i386', 'binary_type': 'executable', 'endian': 'little', 'os': 'os2'})
    self.assertEqual(mediafileinfo_detect.count_is_exe(data3), 1326)
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?', 'LX\0\0\0\0\0\0\1\0\1\0????\0\x80\0\0'))),
                     {'format': 'os2dll', 'subformat': 'lx', 'detected_format': 'exe', 'arch': '80286', 'binary_type': 'shlib', 'endian': 'little', 'os': 'os2'})
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?', 'LX\0\0\0\0\0\0\1\0\1\0????\0\x80\1\0'))),
                     {'format': 'exe', 'subformat': 'lx', 'arch': '80286', 'binary_type': 'pmlib', 'endian': 'little', 'os': 'os2'})
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?', 'LE\0\0\0\0\0\0\2\0\4\0????\0\x80\0\0'))),
                     {'format': 'vxd', 'subformat': 'le', 'detected_format': 'exe', 'arch': 'i386', 'binary_type': 'shlib', 'endian': 'little', 'os': 'windows'})
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?', 'LE\0\0\0\0\0\0\2\0\4\0????\0\x80\0\0', '?' * 44, '\x64\0\0\0\2\0\0\0', '?' * 28, '\0' * 24, '\0' * 24))),
                     {'format': 'vxd', 'subformat': 'le', 'detected_format': 'exe', 'arch': 'none', 'binary_type': 'shlib', 'endian': 'little', 'os': 'windows'})
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?', 'LE\0\0\0\0\0\0\2\0\4\0????\0\x80\0\0', '?' * 44, '\x64\0\0\0\2\0\0\0', '?' * 28, '?' * 8, '\4\0\0\0', '?' * 12, '\0' * 24, '\0' * 24))),
                     {'format': 'vxd', 'subformat': 'le', 'detected_format': 'exe', 'arch': '8086', 'binary_type': 'shlib', 'endian': 'little', 'os': 'windows'})
    self.assertEqual(analyze_string(''.join(('MZ?\0', '?' * 56, 'A\0\0\0?', 'LE\0\0\0\0\0\0\2\0\4\0????\0\x80\0\0', '?' * 44, '\x64\0\0\0\2\0\0\0', '?' * 28, '?' * 8, '\4 \0\0', '?' * 12, '?' * 8, '\4\0\0\0', '?' * 12))),
                     {'format': 'vxd', 'subformat': 'le', 'detected_format': 'exe', 'arch': '8086,i386', 'binary_type': 'shlib', 'endian': 'little', 'os': 'windows'})

  def test_analyze_macho(self):
    self.assertEqual(analyze_string('\xce\xfa\xed\xfe\7\0\0\0\3\0\0\0\2\0\0\0'),
                     {'format': 'macho', 'subformat': '32bit', 'binary_type': 'executable', 'arch': 'i386', 'endian': 'little'})
    self.assertEqual(analyze_string('\xcf\xfa\xed\xfe\7\0\0\1\3\0\0\0\4\0\0\0'),
                     {'format': 'macho', 'subformat': '64bit', 'binary_type': 'core', 'arch': 'amd64', 'endian': 'little'})
    self.assertEqual(analyze_string('\xfe\xed\xfa\xce\0\0\0\x12????\0\0\0\6'),
                     {'format': 'macho', 'subformat': '32bit', 'binary_type': 'shlib', 'arch': 'powerpc', 'endian': 'big'})
    self.assertEqual(analyze_string('\xfe\xed\xfa\xcf\1\0\0\x12????\0\0\0\1'),
                     {'format': 'macho', 'subformat': '64bit', 'binary_type': 'object', 'arch': 'powerpc64', 'endian': 'big'})
    self.assertEqual(analyze_string('\xca\xfe\xba\xbe\0\0\0\2\1\0\0\7\x80\0\0\3\0\0\x10\0\0\x00o\x10\0\0\0\x0c\0\0\0\7\0\0\0\3\0\0\x80\0\0\x00n \0\0\0\x0c'),
                     {'format': 'macho', 'subformat': 'universal', 'binary_type': 'executable', 'arch': 'amd64,i386', 'endian': 'big'})
    self.assertEqual(analyze_string('\xbe\xba\xfe\xca\2\0\0\0\7\0\0\1????????????????\7\0\0\0????????????????'),  # Maybe no such endian.
                     {'format': 'macho', 'subformat': 'universal', 'binary_type': 'executable', 'arch': 'amd64,i386', 'endian': 'little'})

  def test_analyze_python_pyc(self):
    self.assertEqual(analyze_string('\x99N\r\n????c\0\0\0\0????????????'),
                     {'format': 'python-pyc', 'subformat': '1.5'})
    self.assertEqual(analyze_string('\xfc\xc4\r\n????c\0\0\0\0????????????'),
                     {'format': 'python-pyc', 'subformat': '1.6'})
    self.assertEqual(analyze_string('\x88\xc6\r\n????c\0\0\0\0????????????'),
                     {'format': 'python-pyc', 'subformat': '2.0'})
    self.assertEqual(analyze_string('*\xeb\r\n????c\0\0\0\0????????????'),
                     {'format': 'python-pyc', 'subformat': '2.1'})
    self.assertEqual(analyze_string('.\xed\r\n????c\0\0\0\0????????????'),
                     {'format': 'python-pyc', 'subformat': '2.2'})
    self.assertEqual(analyze_string(';\xf2\r\n????c\0\0\0\0\0\0\0\0????????'),
                     {'format': 'python-pyc', 'subformat': '2.3'})
    self.assertEqual(analyze_string('m\xf2\r\n????c\0\0\0\0\0\0\0\0????????'),
                     {'format': 'python-pyc', 'subformat': '2.4'})
    self.assertEqual(analyze_string('\xb3\xf2\r\n????c\0\0\0\0\0\0\0\0????????'),
                     {'format': 'python-pyc', 'subformat': '2.5'})
    self.assertEqual(analyze_string('\xd1\xf2\r\n????c\0\0\0\0\0\0\0\0????????'),
                     {'format': 'python-pyc', 'subformat': '2.6'})
    self.assertEqual(analyze_string('\3\xf3\r\n????c\0\0\0\0\0\0\0\0????????'),
                     {'format': 'python-pyc', 'subformat': '2.7'})
    self.assertEqual(analyze_string('\3\xf3\r\n????c\0\0\0\0\0\0\0\0????????'),
                     {'format': 'python-pyc', 'subformat': '2.7'})
    self.assertEqual(analyze_string('\xb8\x0b\r\n????c\0\0\0\0\0\0\0\0????????'),
                     {'format': 'python-pyc', 'subformat': '3.0'})
    self.assertEqual(analyze_string('O\x0c\r\n????c\0\0\0\0\0\0\0\0????????'),
                     {'format': 'python-pyc', 'subformat': '3.1'})
    self.assertEqual(analyze_string('l\x0c\r\n????c\0\0\0\0\0\0\0\0????????'),
                     {'format': 'python-pyc', 'subformat': '3.2'})
    self.assertEqual(analyze_string('\x9e\x0c\r\n????????c\0\0\0\0\0\0\0\0????'),
                     {'format': 'python-pyc', 'subformat': '3.3'})
    self.assertEqual(analyze_string('\xee\x0c\r\n????????\xe3\0\0\0\0\0\0\0\0????'),
                     {'format': 'python-pyc', 'subformat': '3.4'})
    self.assertEqual(analyze_string('\x17\r\r\n????????\xe3\0\0\0\0\0\0\0\0????'),
                     {'format': 'python-pyc', 'subformat': '3.5'})
    self.assertEqual(analyze_string('3\r\r\n????????\xe3\0\0\0\0\0\0\0\0????'),
                     {'format': 'python-pyc', 'subformat': '3.6'})
    self.assertEqual(analyze_string('B\r\r\n\3\0\0\0????????\xe3\0\0\0\0\0\0\0\0'),
                     {'format': 'python-pyc', 'subformat': '3.7'})
    self.assertEqual(analyze_string('U\r\r\n\3\0\0\0????????\xe3\0\0\0\0\0\0\0\0'),
                     {'format': 'python-pyc', 'subformat': '3.8'})
    self.assertEqual(analyze_string('V\r\r\n\3\0\0\0????????\xe3\0\0\0\0\0\0\0\0'),
                     {'format': 'python-pyc', 'subformat': '3.8+'})

  def test_detect_micropython_mpy(self):
    self.assertEqual(analyze_string('M\0\2\x1f'), {'format': 'micropython-mpy'})
    self.assertEqual(analyze_string('M\5\x7f\x2f '), {'format': 'micropython-mpy'})

  def test_analyze_pef(self):
    self.assertEqual(analyze_string('Joy!peffpwpc\0\0\0\1????????????????\0\3\0\2'),
                     {'format': 'pef', 'binary_type': 'executable', 'arch': 'powerpc', 'endian': 'big'})

  def test_analyze_elf(self):
    self.assertEqual(analyze_string('\x7fELF\2\1\1\0\0\0\0\0\0\0\0\0\3\0>\0\1\0\0\0'),
                     {'format': 'elf', 'subformat': '64bit', 'binary_type': 'shlib', 'arch': 'amd64', 'endian': 'little', 'os': 'generic-sysv'})
    self.assertEqual(analyze_string('\x7fELF\1\1\1\3\0\0\0\0\0\0\0\0\2\0\3\0\1\0\0\0'),
                     {'format': 'elf', 'subformat': '32bit', 'binary_type': 'executable', 'arch': 'i386', 'endian': 'little', 'os': 'linux'})

  def test_analyze_wasm(self):
    self.assertEqual(analyze_string('\0asm\1\0\0\0'),
                     {'format': 'wasm', 'subformat': 'binary'})
    self.assertEqual(analyze_string('(module\t'),
                     {'format': 'wasm', 'subformat': 'ascii'})

  def test_detect_java_class(self):
    self.assertEqual(analyze_string('\xca\xfe\xba\xbe\0\3\0\x2d'), {'format': 'java-class'})

  def test_analyze_ocaml_bytecode(self):
    self.assertEqual(analyze_string('\x54\0\0\0\xdf\2\0\0'),
                     {'format': 'ocaml-bytecode'})
    self.assertEqual(analyze_string('\0\0\0\x54\0\0\2\xdf'),
                     {'format': 'ocaml-bytecode'})

  def test_analyze_lua_luac(self):
    self.assertEqual(analyze_string('\x1bLua\x24\2\4\x08\x34\x12'), {'format': 'lua-luac', 'subformat': '2.4'})
    self.assertEqual(analyze_string('\x1bLua\x25\2\4\x08\x34\x12'), {'format': 'lua-luac', 'subformat': '2.5'})
    self.assertEqual(analyze_string('\x1bLua\x31l\4'), {'format': 'lua-luac', 'subformat': '3.1'})
    self.assertEqual(analyze_string('\x1bLua\x32\4'), {'format': 'lua-luac', 'subformat': '3.2'})
    self.assertEqual(analyze_string('\x1bLua\x40\1\4\4\4 \6\x09'), {'format': 'lua-luac', 'subformat': '4.0'})
    self.assertEqual(analyze_string('\x1bLua\x50\1\4\4\4\6\x08\x09\x09\4'), {'format': 'lua-luac', 'subformat': '5.0'})
    self.assertEqual(analyze_string('\x1bLua\x51\0\1\4\4\4\4\0'), {'format': 'lua-luac', 'subformat': '5.1'})
    self.assertEqual(analyze_string('\x1bLua\x52\0\1\4\4\4\x08\0\x19\x93\r\n\x1a\n'), {'format': 'lua-luac', 'subformat': '5.2'})  # Observed in the wild.
    self.assertEqual(analyze_string('\x1bLua\x53\0\x19\x93\r\n\x1a\n\4\4\4\4\4\0\0\0\0'), {'format': 'lua-luac', 'subformat': '5.3'})
    self.assertEqual(analyze_string('\x1bLua\x54\0'), {'format': 'lua-luac', 'subformat': '5.4'})

  def test_detect_hxs(self):
    self.assertEqual(analyze_string(self.HXS_HEADER), {'format': 'hxs', 'detected_format': 'exe'})

  def test_detect_rtf(self):
    self.assertEqual(analyze_string(r'{\rtf1'), {'format': 'rtf'})
    self.assertEqual(mediafileinfo_detect.count_is_rtf(r'{\rtf1'), 600)
    self.assertEqual(mediafileinfo_detect.count_is_rtf(r'{\rtf1{\info\title '), 1200)
    self.assertEqual(mediafileinfo_detect.count_is_rtf(r'{\rtf1{\info \title '), 1300)
    self.assertEqual(mediafileinfo_detect.count_is_rtf(r'{\rtf1\ansi'), 1100)
    self.assertEqual(mediafileinfo_detect.count_is_rtf(r'{\rtf1 \ansi'), 1200)
    self.assertEqual(mediafileinfo_detect.count_is_rtf(r'{\rtf1 \ansi '), 1300)
    self.assertEqual(mediafileinfo_detect.count_is_rtf(r'{\rtf1 \ansicpg437'), 1500)
    self.assertEqual(mediafileinfo_detect.count_is_rtf(r'{\rtf1 \foo'), 700)
    self.assertEqual(mediafileinfo_detect.count_is_rtf(r'{\rtf1\foo'), 600)

  def test_detect_troff(self):
    self.assertEqual(analyze_string('.\\" DO NOT MODIFY THIS FILE!  \n.TH x'), {'format': 'troff'})
    self.assertEqual(analyze_string('.\\"****hello\n.\\"*'), {'format': 'troff'})
    self.assertEqual(analyze_string('.TH LS "1"'), {'format': 'troff'})
    self.assertEqual(analyze_string('.SH NAME'), {'format': 'troff'})
    self.assertEqual(analyze_string('.de xy'), {'format': 'troff'})
    self.assertEqual(analyze_string('.EF \'hi\''), {'format': 'troff'})

  def test_detect_info(self):
    self.assertEqual(analyze_string('This is grep.info-t, produced by t\n'), {'format': 'info'})
    data1 = 'This is grep.info-t, produced by makeinfo version 6.3 from grep.texi.\n'
    self.assertEqual(analyze_string(data1), {'format': 'info'})
    self.assertEqual(mediafileinfo_detect.count_is_info(data1), 5255)

  def test_detect_lyx(self):
    self.assertEqual(analyze_string('#LyX file created by tex2lyx ?.?\n\\lyxformat 544\n'), {'format': 'lyx'})
    self.assertEqual(analyze_string('#LyX 2.3 created this file. For more info see http://www.lyx.org/\n\\lyxformat 544\n'), {'format': 'lyx'})

  def test_detect_opentype(self):
    self.assertEqual(analyze_string('\0\1\0\0\0\x08\0\x80\0\3\0\0'), {'format': 'opentype'})
    self.assertEqual(analyze_string('\0\1\0\0\0\x08\0\x80\0\3\0\0glyf' + '\0' * 124), {'format': 'truetype', 'detected_format': 'opentype', 'glyph_format': 'truetype'})
    self.assertEqual(analyze_string('\0\1\0\0\0\x08\0\x80\0\3\0\0GSUB' + '\0' * 124), {'format': 'opentype'})
    self.assertEqual(analyze_string('\0\1\0\0\0\x08\0\x80\0\3\0\0GSUB????????????glyf' + '\0' * 108), {'format': 'opentype', 'glyph_format': 'truetype'})
    self.assertEqual(analyze_string('\0\1\0\0\0\x08\0\x80\0\3\0\0GSUB????????????CFF ' + '\0' * 108), {'format': 'opentype', 'glyph_format': 'cff'})
    self.assertEqual(analyze_string('\0\1\0\0\0\x08\0\x80\0\3\0\0GSUB????????????glyf????????????CFF ' + '\0' * 92), {'format': 'opentype'})

  def test_analyze_stuffit(self):
    data_macbinary1 = '\0\x11Name of this file\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\x00SIT5????\1\0\0\0\0\0\0\0\x80\0\0\0\x82\0\0\0\0\0\x99\xd4\x89\0\x99\xd4\x89\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0'
    self.assertEqual(analyze_string(data_macbinary1),
                     {'format': 'stuffit', 'detected_format': 'macbinary', 'subformat': 'macbinary'})
    self.assertEqual(analyze_string('SIT!??????rLau'), {'format': 'stuffit'})
    self.assertEqual(analyze_string('StuffIt (c)1997'), {'format': 'stuffit'})
    self.assertEqual(analyze_string('StuffIt?'), {'format': 'stuffitx'})

  def test_analyze_gpg_private_keys(self):
    self.assertEqual(analyze_string('\x94?\4????\x12'), {'format': 'gpg-private-keys'})
    self.assertEqual(analyze_string('\x95\1?\4????\x11'), {'format': 'gpg-private-keys'})
    self.assertEqual(analyze_string('\x95\3?\4????\x01'), {'format': 'gpg-private-keys'})
    self.assertEqual(analyze_string('-----BEGIN PGP PRIVATE KEY BLOCK-----\n'), {'format': 'gpg-private-keys'})

  def test_analyze_gpg_public_keys(self):
    self.assertEqual(analyze_string('\x98?\4????\x12'), {'format': 'gpg-public-keys'})
    self.assertEqual(analyze_string('\x99\1?\4????\x11'), {'format': 'gpg-public-keys'})
    self.assertEqual(analyze_string('\x99\3?\4????\x01'), {'format': 'gpg-public-keys'})
    self.assertEqual(analyze_string('-----BEGIN PGP PUBLIC KEY BLOCK-----\n'), {'format': 'gpg-public-keys'})

  def test_analyze_signify(self):
    self.assertEqual(analyze_string('untrusted comment: verify with keyname.pub\n'), {'format': 'signify-signature', 'detected_format': 'signify'})
    self.assertEqual(analyze_string('untrusted comment: mycomment public key\n'), {'format': 'signify-public-key', 'detected_format': 'signify'})
    self.assertEqual(analyze_string('untrusted comment: mycomment secret key\n'), {'format': 'signify-private-key', 'detected_format': 'signify'})
    self.assertEqual(analyze_string('untrusted comment: signature from minisign secret key\n'), {'format': 'signify-signature', 'subformat': 'minisign', 'detected_format': 'signify'})
    self.assertEqual(analyze_string('untrusted comment: minisign encrypted secret key\n'), {'format': 'signify-private-key', 'subformat': 'minisign', 'detected_format': 'signify'})
    self.assertEqual(analyze_string('untrusted comment: minisign public key 42\n'), {'format': 'signify-public-key', 'subformat': 'minisign', 'detected_format': 'signify'})
    self.assertEqual(analyze_string('untrusted comment: minisign foo\n'), {'format': 'signify', 'subformat': 'minisign'})
    self.assertEqual(analyze_string('untrusted comment: foo\n'), {'format': 'signify'})

  def test_analyze_sqlite2(self):
    self.assertEqual(analyze_string('** This file contains an SQLite 2.1 database **\x00\x28\x75\xe3\xda'), {'format': 'sqlite2'})

  def test_analyze_sqlite3(self):
    self.assertEqual(analyze_string('SQLite format 3\0\4\0\1\1'), {'format': 'sqlite3'})


if __name__ == '__main__':
  unittest.main(argv=[sys.argv[0], '-v'] + sys.argv[1:])
