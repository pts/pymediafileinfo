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

import sys
import unittest

import mediafileinfo_detect


def get_string_fread_fskip(data):
  i_ary = [0]

  def fread(n):
    result = data[i_ary[0] : i_ary[0] + n]
    i_ary[0] += len(result)
    return result

  def fskip(n):
    return len(fread(n)) == n

  return fread, fskip


def analyze_string(analyze_func, data):
  fread, fskip = get_string_fread_fskip(data)
  info = {}
  analyze_func(fread, info, fskip)
  if info.get('format') not in mediafileinfo_detect.FORMAT_DB.formats:
    raise RuntimeError('Unknown format in info: %r' % (info.get('format'),))
  return info


class MediaFileInfoDetectTest(unittest.TestCase):
  maxDiff = None

  JP2_HEADER = '0000000c6a5020200d0a870a00000014667479706a703220000000006a7032200000002d6a703268000000166968647200000120000001600003080700000000000f636f6c7201000000000012'.decode('hex')

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
        analyze_string(mediafileinfo_detect.analyze_ape, '4d414320960f00003400000018000000580000002c00000014c5db00000000000000000068e379c7c0d13d822b738a67144f4248a00f0000008004001c840200160000001000020044ac'.decode('hex')),
        {'format': 'ape',
         'tracks': [{'channel_count': 2, 'codec': 'ape',
                     'sample_rate': 44100, 'sample_size': 16, 'type': 'audio'}]})

  def test_analyze_pnm(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_pnm, 'P1#f oo\n #bar\r\t123\x0b\x0c456#'),
                     {'codec': 'uncompressed-ascii', 'format': 'pnm', 'subformat': 'pbm', 'height': 456, 'width': 123})

  def test_analyze_lbm(self):
    self.assertEqual(mediafileinfo_detect.detect_format('FORM\0\0\0\x4eILBMBMHD\0\0\0\x14')[0], 'lbm')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_lbm, 'FORM\0\0\0\x4eILBMBMHD\0\0\0\x14\1\3\1\5'),
                     {'codec': 'rle', 'format': 'lbm', 'subformat': 'ilbm', 'height': 261, 'width': 259})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_lbm, 'FORM\0\0\0\x4ePBM BMHD\0\0\0\x14\1\3\1\5'),
                     {'codec': 'uncompressed', 'format': 'lbm', 'subformat': 'pbm', 'height': 261, 'width': 259})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_lbm, 'FORM\0\0\0\x4eACBMBMHD\0\0\0\x14\1\3\1\5'),
                     {'codec': 'uncompressed', 'format': 'lbm', 'subformat': 'acbm', 'height': 261, 'width': 259})

  def test_analyze_deep(self):
    self.assertEqual(mediafileinfo_detect.detect_format('FORM\0\0\0\x4eDEEPDGBL\0\0\0\x08')[0], 'deep')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_deep, 'FORM\0\0\0\x4eDEEPDGBL\0\0\0\x08'),
                     {'format': 'deep'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_deep, 'FORM\0\0\0\x4eDEEPDGBL\0\0\0\x08\2\1\2\4\0\3'),
                     {'format': 'deep', 'height': 516, 'width': 513, 'codec': 'dynamic-huffman'})

  def test_analyze_pcx(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_pcx, '\n\5\1\x08\0\0\0\0\2\1\4\1'),
                     {'codec': 'rle', 'format': 'pcx', 'height': 261, 'width': 259})

  def test_analyze_xcf(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xcf, 'gimp xcf v001\0\0\0\1\x0d\0\0\1\7'),
                     {'format': 'xcf', 'width': 269, 'height': 263})

  def test_analyze_psd(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_psd, '8BPS\0\1\0\0\0\0\0\0\0\1\0\0\1\5\0\0\1\3\0\1\0\0'),
                     {'format': 'psd', 'width': 259, 'height': 261})

  def test_analyze_tiff(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_tiff, '49492a001600000078da5bc0f080210100062501e10011000001030001000000345600000101030001000000452300000201030001000000010000000301030001000000080000000601030001000000010000000a01030001000000010000000d0102000b000000f800000011010400010000000800000012010300010000000100000015010300010000000100000016010300010000000500000017010400010000000d0000001a01050001000000e80000001b01050001000000f00000001c0103000100000001000000280103000100000001000000290103000200000000000100'.decode('hex')),
                     {'format': 'tiff', 'width': 0x5634, 'height': 0x2345, 'codec': 'zip'})

  def test_analyze_tga(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_tga, '000003000000000000000000030105010800'.decode('hex')),
                     {'format': 'tga', 'width': 259, 'height': 261, 'codec': 'uncompressed'})

  def test_analyze_ps(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_ps, '%!PS-Adobe-3.0\tEPSF-3.0\r\n%%Creator: (ImageMagick)\n%%Title:\t(image.eps2)\r\n%%CreationDate: (2019-10-22T21:27:41+02:00)\n%%BoundingBox:\t-1 -0.8\t \t34 56.2\r\n%%HiResBoundingBox: 0\t0\t3 5\r%%LanguageLevel:\t2\r%%Pages: 1\r%%EndComments\nuserdict begin end'),
                     {'format': 'ps', 'height': 57, 'subformat': 'eps', 'width': 35})

  def test_analyze_mp4_jp2(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_mp4, self.JP2_HEADER),
                     {'bpc': 8, 'brands': ['jp2 '], 'codec': 'jpeg2000', 'component_count': 3, 'format': 'jp2', 'has_early_mdat': False, 'height': 288, 'minor_version': 0, 'subformat': 'jp2', 'tracks': [], 'width': 352})

  def test_analyze_pnot(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_pnot, '\0\0\0\x14pnot\1\2\3\4\0\0PICT\0\1\0\0\0\x0aPICT..' + self.JP2_HEADER),
                     {'bpc': 8, 'brands': ['jp2 '], 'codec': 'jpeg2000', 'component_count': 3, 'format': 'jp2', 'has_early_mdat': False, 'height': 288, 'minor_version': 0, 'subformat': 'jp2', 'tracks': [], 'width': 352})

  def test_analyze_swf(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_swf, 'FWS\n4\x07\x01\x00x\x00\x05_\x00\x00\x1f@\x00\x00\x18'),
                     {'codec': 'uncompressed', 'format': 'swf', 'height': 800, 'width': 550})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_swf, 'FWS 4\x07\x01\x00p\x00\x0f\xa0\x00\x00\x8c\xa0\x00'),
                     {'codec': 'uncompressed', 'format': 'swf', 'height': 225, 'width': 400})

  def test_analyze_miff(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_miff, 'id=ImageMagick\rrows=42\t \fcolumns=137:\x1arows=111'),
                     {'codec': 'uncompressed', 'format': 'miff', 'height': 42, 'width': 137})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_miff, 'id=ImageMagick\rrows=42\t \fcolumns=137\ncompression=BZip:\x1arows=111'),
                     {'codec': 'bzip2', 'format': 'miff', 'height': 42, 'width': 137})

  def test_analyze_jbig2(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_jbig2, '\x97JB2\r\n\x1a\n\1\0\0\0\1\0\0\0\x000\0\1\0\0\0\x13\0\0\1\xa3\0\0\2\x16\0\0\0\0\0\0\0\0\1\0\0'),
                     {'codec': 'jbig2', 'format': 'jbig2', 'height': 534, 'width': 419, 'subformat': 'jbig2'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_jbig2, '\0\0\0\x000\0\1\0\0\0\x13\0\0\1\xa3\0\0\2\x16\0\0\0\0\0\0\0\0\1\0\0'),
                     {'codec': 'jbig2', 'format': 'jbig2', 'height': 534, 'width': 419, 'subformat': 'pdf'})

  def test_analyze_djvu(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_djvu, 'AT&TFORM\0\0\x19bDJVUINFO\0\0\0\n\t\xf6\x0c\xe4'),
                     {'format': 'djvu', 'height': 3300, 'width': 2550, 'subformat': 'djvu'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_djvu, 'AT&TFORM\0\0\1\0DJVMDIRM\0\0\0\5.....NAVM\0\0\0\6......FORM\0\0\0\7DJVI...FORM\0\0\0\4DJVUINFO\0\0\0\4\t\xf6\x0c\xe4'),
                     {'format': 'djvu', 'height': 3300, 'width': 2550, 'subformat': 'djvm'})

  def test_analyze_art(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_art, 'JG\4\x0e\0\0\0\0\7\0\x40\x15\3\xdd\1\xe0\1'),
                     {'format': 'art', 'codec': 'art', 'height': 480, 'width': 477})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_art, 'JG\4\x0e\0\0\0\0\8\0\x40\x15\3\xdd\1\xe0\1'),
                     {'format': 'art', 'codec': 'art'})

  def test_analyze_ico(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_ico, '\0\0\1\0\1\0\x30\x31\0\0\1\0\x20\0\xa8\x25\0\0\x16\0\0\0'),
                     {'format': 'ico', 'height': 49, 'width': 48})

  def test_analyze_webp(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_webp, '524946466876000057454250565038205c760000d2be019d012a26027001'.decode('hex')),
                     {'codec': 'vp8', 'format': 'webp', 'height': 368, 'width': 550})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_webp, '524946460e6c0000574542505650384c026c00002f8181621078'.decode('hex')),
                     {'codec': 'webp-lossless', 'format': 'webp', 'height': 395, 'width': 386})

  def test_analyze_vp8(self):
    self.assertEqual(mediafileinfo_detect.detect_format('d2be019d012a26027001'.decode('hex'))[0], 'vp8')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_vp8, 'd2be019d012a26027001'.decode('hex')),
                     {'format': 'vp8', 'tracks': [{'codec': 'vp8', 'height': 368, 'type': 'video', 'width': 550}]})

  def test_analyze_vp9(self):
    data1 = '824983420031f0314600'.decode('hex')
    self.assertEqual(mediafileinfo_detect.detect_format(data1)[0], 'vp9')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_vp9, data1),
                     {'format': 'vp9', 'tracks': [{'codec': 'vp9', 'height': 789, 'type': 'video', 'width': 800}]})

  def test_analyze_av1(self):
    data1 = '\x12\0\x0a\4'
    data2 = '\x12\0\x0a\4\x18\0\x10'
    data3 = '\x12\0\x0a\x0b\0\0\0\x24\xce\x3f\x8f\xbf'
    self.assertEqual(mediafileinfo_detect.detect_format(data1)[0], 'av1')
    self.assertEqual(mediafileinfo_detect.detect_format(data2)[0], 'av1')
    self.assertEqual(mediafileinfo_detect.detect_format(data3)[0], 'av1')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_av1, data1),
                     {'format': 'av1', 'tracks': [{'codec': 'av1', 'type': 'video'}]})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_av1, data2),
                     {'format': 'av1', 'tracks': [{'codec': 'av1', 'height': 2, 'type': 'video', 'width': 1}]})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_av1, data3),
                     {'format': 'av1', 'tracks': [{'codec': 'av1', 'height': 800, 'type': 'video', 'width': 800}]})

  def test_analyze_jpegxr(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_jpegxr, '4949bc012000000024c3dd6f034efe4bb1853d77768dc90c0000000000000000080001bc0100100000000800000002bc0400010000000000000080bc040001000000a005000081bc0400010000006400000082bc0b00010000009af78f4283bc0b00010000009af78f42c0bc04000100000086000000c1bc040001000000369b0200'.decode('hex')),
                     {'codec': 'jpegxr', 'format': 'jpegxr', 'subformat': 'tagged', 'height': 100, 'width': 1440})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_jpegxr, 'WMPHOTO\0\x11\x45\xc0\x71\x05\x9f\x00\x63'),
                     {'codec': 'jpegxr', 'format': 'jpegxr', 'subformat': 'coded', 'height': 100, 'width': 1440})

  def test_analyze_flif(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_flif, 'FLIF\x441\x83\x7f\x83\x7e'),
                     {'format': 'flif', 'codec': 'flif', 'width': 512, 'height': 511, 'component_count': 4, 'bpc': 8})

  def test_analyze_bpg(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_bpg, 'BPG\xfb\x20\x00\x8b\x1c\x85\x5a'),
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
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_mp4, '00000018667479706d696631000000006d69663168656963000001fe6d657461000000000000002168646c72000000000000000070696374000000000000000000000000000000000e7069746d0000000003ea00000034696c6f63000000004440000203ea00000000021600010000000800046a8003ed000000000216000100046a8800000e4a0000004c69696e660000000000020000001f696e66650200000003ea0000687663314845564320496d616765000000001f696e66650200000003ed0000687663314845564320496d616765000000001a69726566000000000000000e74686d6203ed000103ea0000012969707270000001076970636f0000006c68766343010160000000000000000000baf000fcfdf8f800000f03a00001001840010c01ffff016000000300000300000300000300baf024a10001001f420101016000000300000300000300000300baa002d0803c1fe5f9246d9ed9a2000100074401c190958112000000146973706500000000000005a0000003c00000006b68766343010160000000000000000000baf000fcfdf8f800000f03a00001001840010c01ffff016000000300000300000300000300baf024a10001001e420101016000000300000300000300000300baa01e20287f97e491b67b64a2000100074401c190958112000000146973706500000000000000f0000000a00000001a69706d61000000000000000203ea02810203ed028304000478d26d646174'.decode('hex')),
                     {'brands': ['heic', 'mif1'], 'codec': 'h265', 'format': 'isobmff-image', 'has_early_mdat': False, 'height': 960, 'minor_version': 0, 'subformat': 'heif', 'width': 1440})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_mp4, '0000001c667479706d696631000000006d696631617669666d696166000000096d64617400000000536672656549736f4d656469612046696c652050726f64756365642077697468204750414320302e372e322d4445562d7265763935382d673564646439643163652d6769746875625f6d617374657200000000f56d657461000000000000003268646c720000000000000000706963740000000000000000000000004750414320706963742048616e646c6572000000000e7069746d0000000000010000001e696c6f630000000004400001000100000000002c00010000a42a0000002869696e660000000000010000001a696e6665020000000001000061763031496d616765000000006369707270000000456970636f00000014697370650000000000000500000002d000000010706173700000000100000001000000196176314381054c000a0b0000002d4cffb3dfff9c0c0000001669706d610000000000000001000103010283'.decode('hex')),
                     {'brands': ['avif', 'miaf', 'mif1'], 'codec': 'av1', 'format': 'isobmff-image', 'has_early_mdat': True, 'height': 720, 'minor_version': 0, 'subformat': 'avif', 'width': 1280})

  def test_analyze_png(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_png, '\x89PNG\r\n\x1a\n\0\0\0\rIHDR\0\0\5\1\0\0\3\2'),
                     {'format': 'png', 'codec': 'flate', 'width': 1281, 'height': 770})

  def test_analyze_jng(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_jng, '\x8bJNG\r\n\x1a\n\0\0\0\rJHDR\0\0\5\1\0\0\3\2'),
                     {'format': 'jng', 'codec': 'jpeg', 'width': 1281, 'height': 770})

  def test_analyze_mng(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_mng, '\x8aMNG\r\n\x1a\n\0\0\0\rMHDR\0\0\5\1\0\0\3\2'),
                     {'format': 'mng', 'tracks': [{'codec': 'jpeg+png', 'width': 1281, 'height': 770}]})

  def test_analyze_dirac(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_dirac, 'BBCD\0\0\0\0\x12\0\0\0\0\x6c\x1c\x1a'),
                     {'format': 'dirac', 'tracks': [{'type': 'video', 'codec': 'dirac', 'width': 720, 'height': 576}]})

  def test_analyze_theora(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_theora, '\x80theora\x03\2\0\0\x14\0\x0f\0\x01@\0\0\xf0\0\0\0\0\0\x1e\0\0\0\1\0\0\0\0\0\0\1\0\0\x00e\x00'),
                     {'format': 'theora', 'tracks': [{'type': 'video', 'codec': 'theora', 'width': 320, 'height': 240}]})

  def test_analyze_daala(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_daala, '\x80daala\0\0\0\0\0\1\2\0\0\3\4'),
                     {'format': 'daala', 'tracks': [{'type': 'video', 'codec': 'daala', 'width': 258, 'height': 772}]})

  def test_analyze_vorbis(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_vorbis, '\x01vorbis\0\0\0\0\x01D\xac\0\0'),
                     {'format': 'vorbis', 'tracks': [{'type': 'audio', 'codec': 'vorbis', 'channel_count': 1, 'sample_rate': 44100, 'sample_size': 16}]})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_vorbis, '\x01vorbis\0\0\0\0\x01"V\0\0'),
                     {'format': 'vorbis', 'tracks': [{'type': 'audio', 'codec': 'vorbis', 'channel_count': 1, 'sample_rate': 22050, 'sample_size': 16}]})

  def test_analyze_oggpcm(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_oggpcm, 'PCM     \0\0\0\0\0\0\0\x10\0\0\xbb\x80\x00\x02'),
                     {'format': 'oggpcm', 'tracks': [{'type': 'audio', 'codec': 'mulaw', 'channel_count': 2, 'sample_rate': 48000, 'sample_size': 8}]})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_oggpcm, 'PCM     \0\0\0\4\0\0\0\x20\0\0\xac\x44\x00\x01'),
                     {'format': 'oggpcm', 'tracks': [{'type': 'audio', 'codec': 'float', 'channel_count': 1, 'sample_rate': 44100, 'sample_size': 32}]})

  def test_analyze_opus(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_opus, 'OpusHead\1\x02d\x01D\xac\0\0'),
                     {'format': 'opus', 'tracks': [{'type': 'audio', 'codec': 'opus', 'channel_count': 2, 'sample_rate': 44100, 'sample_size': 16}]})

  def test_analyze_speex(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_speex, 'Speex   1.0.4\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\1\0\0\x00P\0\0\0\x80\xbb\0\0\x02\0\0\0\x04\0\0\0\1\0\0\0'),
                     {'format': 'speex', 'tracks': [{'type': 'audio', 'codec': 'speex', 'channel_count': 1, 'sample_rate': 48000, 'sample_size': 16}]})

  def test_analyze_ogg(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_ogg, '4f67675300020000000000000000f6c8465100000000eb0c16bd012a807468656f72610302000014000f0001400000f000000000001e000000010000000000000100000065004f676753000200000000000000002c36d36d00000000dbc8fb60011e01766f72626973000000000122560000fffffffff0550000ffffffffaa01'.decode('hex')),
                     {'format': 'ogg', 'tracks': [{'codec': 'theora', 'height': 240, 'type': 'video', 'width': 320}, {'channel_count': 1, 'codec': 'vorbis', 'sample_rate': 22050, 'sample_size': 16, 'type': 'audio'}]})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_ogg, '4f6767530002000000000000000063bb451200000000f480dc43011e01766f72626973000000000144ac0000000000008038010000000000b8014f6767530000000000000000000063bb45120100000087abaad202030461626364656667'.decode('hex')),
                     {'format': 'ogg', 'tracks': [{'channel_count': 1, 'codec': 'vorbis', 'sample_rate': 44100, 'sample_size': 16, 'type': 'audio'}]})

  def test_analyze_yuv4mpeg2(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_yuv4mpeg2, 'YUV4MPEG2 W384 H288 F25:1 Ip A0:0\nFRAME\n'),
                     {'format': 'yuv4mpeg2', 'tracks': [{'type': 'video', 'codec': 'uncompressed', 'width': 384, 'height': 288, 'colorspace': '420jpeg', 'subformat': 'yuv4mpeg2'}]})

  def test_analyze_realaudio(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_realaudio, '.ra\xfd\0\3\0\x3a\0\1'),
                     {'format': 'realaudio', 'tracks': [{'type': 'audio', 'codec': 'vslp-ra1', 'channel_count': 1, 'sample_rate': 8000, 'sample_size': 16, 'subformat': 'ra3'}]})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_realaudio, '.ra\xfd\0\x04\0\x00.ra4\0\1\x16\x1c\0\x04\0\0\x009\0\x02\0\0\x00&\0\1\x15\xe0\0\1\xbdP\0\1\xbdP\0\x0c\0\xe4\0\0\0\0\x1f@\0\0\0\x10\0\1\x04Int4\x0428_8'),
                     {'format': 'realaudio', 'tracks': [{'type': 'audio', 'codec': 'ld-celp-ra2', 'channel_count': 1, 'sample_rate': 8000, 'sample_size': 16, 'subformat': 'ra4'}]})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_realaudio, '.ra\xfd\0\x05\0\x00.ra5\0\0\0\0\0\x05\0\0\x00F\0\x08\0\0\x01 \0\0\x1b\0\0\0\xaf\xc8\0\0\xaf\xc8\0\x06\x01 \0\x18\0\0\0\0\x1f@\0\0\x1f@\0\0\0\x10\0\x01genrcook'),
                     {'format': 'realaudio', 'tracks': [{'type': 'audio', 'codec': 'cook', 'channel_count': 1, 'sample_rate': 8000, 'sample_size': 16, 'subformat': 'ra5'}]})

  def test_analyze_realvideo(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_realvideo, '\0\0\0\x20VIDORV20\0\xb0\x00p'),
                     {'format': 'realvideo', 'tracks': [{'type': 'video', 'codec': 'h263+-rv20', 'width': 176, 'height': 112}]})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_realvideo, 'VIDORV20\0\xb0\x00p'),
                     {'format': 'realvideo', 'tracks': [{'type': 'video', 'codec': 'h263+-rv20', 'width': 176, 'height': 112}]})

  def test_analyze_ralf(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_ralf, 'LSD:\1\3\0\0\0\2\0\x10\0\0\xacD'),
                     {'format': 'ralf', 'tracks': [{'type': 'audio', 'codec': 'ralf', 'channel_count': 2, 'sample_rate': 44100, 'sample_size': 16}]})

  def test_analyze_realmedia(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_realmedia, '2e524d46000000120000000000000000000650524f5000000032000000036ee700036ee7000003fe0000031b00019b90002b939e00000e8204d85593000001a700020000434f4e5400000043000000205469636b6c652048656c6c204d6f766965206f6620546865205765656b206200000c5469636b6c652048656c6c000005a93230303400004d445052000000ac000000000000ac440000ac4400000280000002800000000000000e82002b94580c417564696f2053747265616d14617564696f2f782d706e2d7265616c617564696f0000005e2e7261fd000500002e726135660561c700050000004e0016000002800127f00000050bfe00050bfe00100280008000000000ac440000ac4400000010000267656e72636f6f6b0102000000000010010000030800002000000000000500054d44505200000074000000010002c2a30002c2a3000003fe0000031b0000000000000c33002b93ad0c566964656f2053747265616d14766964656f2f782d706e2d7265616c766964656f00000026000000265649444f52563330014000f0000c00000000001df854010a9030302020023c2c2820444154410542480b'.decode('hex')),
                     {'format': 'realmedia',
                      'tracks': [{'channel_count': 2, 'codec': 'cook', 'sample_rate': 44100, 'sample_size': 16, 'subformat': 'ra5', 'type': 'audio'},
                                 {'codec': 'h264-rv30', 'height': 240, 'type': 'video', 'width': 320}]})

  def test_analyze_xml(self):
    data1 = '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
    data2 = '<?xml\t\fencoding="UTF-8" standalone="no"?>'
    data3 = '<?xml\v\rstandalone="no"?>'
    data4 = '<?xml\v\r?>'
    data5 = '<?xml?>'
    data6 = '<!----><!-- hello\n-\r--\n->-\t>-->\t\f<!-- -->\v<?xml\t\f version="1.0"?>'
    data7 = '\r<!---->\n<!--data-->'
    self.assertEqual(mediafileinfo_detect.detect_format(data1)[0], 'xml')
    self.assertNotEqual(mediafileinfo_detect.detect_format(' ' + data1)[0], 'xml')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, data1), {'format': 'xml'})
    self.assertEqual(mediafileinfo_detect.detect_format(data2)[0], 'xml')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, data2), {'format': 'xml'})
    self.assertEqual(mediafileinfo_detect.detect_format(data3)[0], 'xml')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, data3), {'format': 'xml'})
    self.assertEqual(mediafileinfo_detect.detect_format(data4)[0], 'xml')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, data4), {'format': 'xml'})
    self.assertEqual(mediafileinfo_detect.detect_format(data5)[0], 'xml')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, data5), {'format': 'xml'})
    self.assertEqual(mediafileinfo_detect.detect_format(data6)[0], 'xml-comment')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, data6), {'format': 'xml'})
    self.assertEqual(mediafileinfo_detect.detect_format(' ' + data6)[0], 'xml-comment')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, ' ' + data6), {'format': 'xml'})
    self.assertEqual(mediafileinfo_detect.detect_format(data7)[0], 'xml-comment')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, data7), {'format': 'xml-comment'})

  def test_analyze_html(self):
    data1 = '\t\f<!doctype\rhtml\r'
    self.assertEqual(mediafileinfo_detect.detect_format(data1)[0], 'html')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, data1), {'format': 'html'})
    self.assertEqual(mediafileinfo_detect.detect_format('\t\f<!doctype\rhtml>')[0], 'html')
    self.assertNotEqual(mediafileinfo_detect.detect_format('\t\f<!doctype\rhtml=')[0], 'html')
    self.assertEqual(mediafileinfo_detect.detect_format('\t\f<html\n')[0], 'html')
    self.assertEqual(mediafileinfo_detect.detect_format('\t\f<html>')[0], 'html')
    self.assertNotEqual(mediafileinfo_detect.detect_format('\t\f<html=')[0], 'html')
    self.assertEqual(mediafileinfo_detect.detect_format('\t\f<head\n')[0], 'html')
    self.assertEqual(mediafileinfo_detect.detect_format('\t\f<head>')[0], 'html')
    self.assertEqual(mediafileinfo_detect.detect_format('\t\f<body\n')[0], 'html')
    self.assertEqual(mediafileinfo_detect.detect_format('\t\f<body>')[0], 'html')
    data2 = '<!--x-->\t\f<body>'
    self.assertEqual(mediafileinfo_detect.detect_format(data2)[0], 'xml-comment')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, data2), {'format': 'html'})
    self.assertEqual(mediafileinfo_detect.detect_format('\r\n' + data2)[0], 'xml-comment')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '\r\n' + data2), {'format': 'html'})

  def test_analyze_xhtml(self):
    data1 = '<html lang="en"\txmlns="http://www.w3.org/1999/xhtml">'
    data2 = '\t\f<!DOCTYPE\rhtml>\n' + data1
    data3 = '<?xml version="1.0"?>\r\n' + data2
    data4 = '<!-- hi --> ' + data3
    data5 = '\t\f<!DOCTYPE\rhtml>\n<!-- hi -->\r\n<!---->' + data1
    self.assertEqual(mediafileinfo_detect.detect_format(data1)[0], 'html')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, data1), {'format': 'xhtml'})
    self.assertEqual(mediafileinfo_detect.detect_format(data2)[0], 'html')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, data2), {'format': 'xhtml'})
    self.assertEqual(mediafileinfo_detect.detect_format(data3)[0], 'xml')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, data3), {'format': 'xhtml'})
    self.assertEqual(mediafileinfo_detect.detect_format(data4)[0], 'xml-comment')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, data4), {'format': 'xhtml'})
    self.assertEqual(mediafileinfo_detect.detect_format(data5)[0], 'html')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, data5), {'format': 'xhtml'})

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
    self.assertEqual(mediafileinfo_detect.detect_format('<svg\t')[0], 'svg')
    self.assertEqual(mediafileinfo_detect.detect_format('<svg:svg\f')[0], 'svg')
    self.assertEqual(mediafileinfo_detect.detect_format('<svg:svg>')[0], 'svg')
    self.assertEqual(mediafileinfo_detect.detect_format('<!-- --><svg>')[0], 'xml-comment')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n<!-- Created with Sodipodi ("http://www.sodipodi.com/") -->\n<svg\n   xmlns:xml="http://www.w3.org/XML/1998/namespace"\n   xmlns:dc="http://purl.org/dc/elements/1.1/"\n   xmlns:cc="http://web.resource.org/cc/"\n   xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n   xmlns:svg="http://www.w3.org/2000/svg"\n   xmlns="http://www.w3.org/2000/svg"\n   xmlns:xlink="http://www.w3.org/1999/xlink"\n   xmlns:sodipodi="http://inkscape.sourceforge.net/DTD/sodipodi-0.dtd"\n   xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"\n   id="svg602"\n   sodipodi:version="0.32"\n   width="100.00000pt"\n   height="100.00000pt"\n   xml:space="preserve"\n   sodipodi:docname="english.svg"\n   sodipodi:docbase="/home/terry/.icons/nabi"\n   inkscape:version="0.41"\n   inkscape:export-filename="/home/terry/images/icon/png/NewDir/txtfile.png"\n   inkscape:export-xdpi="200.00000"\n   inkscape:export-ydpi="200.00000"><foo'),
                     {'format': 'svg', 'height': 125, 'width': 125})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '<?xml version="1.0" standalone="no"?>\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN"\n   "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n<!--\n    Designed after data from http://www.wacom-asia.com/download/manuals/BambooUsersManual.pdf\n    Size and positions of controls may not be accurate\n -->\n<svg\n   xmlns="http://www.w3.org/2000/svg"\n   version="1.1"\n   style="color:#000000;stroke:#7f7f7f;fill:none;stroke-width:.25;font-size:8"\n   id="bamboo-2fg"\n   width="208"\n   height="136">\n  <title'),
                     {'format': 'svg', 'height': 136, 'width': 208})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '<svg xmlns = \'http://www.w3.org/2000/svg\' width="099" height="0009px">'),
                     {'format': 'svg', 'height': 9, 'width': 99})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '<svg:svg xmlns = \'http://www.w3.org/2000/svg\' width="2e3" height="0009px">'),
                     {'format': 'svg', 'height': 9, 'width': 2000})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '<!-- my\ncomment -->\r\n <svg:svg xmlns = \'http://www.w3.org/2000/svg\' width="2e3" height="0009px">'),
                     {'format': 'svg', 'height': 9, 'width': 2000})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '\f<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd" [\r\n	<!ENTITY ns_svg "http://www.w3.org/2000/svg">\r\n	<!ENTITY ns_xlink "http://www.w3.org/1999/xlink">\r\n]>\n<svg version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="128" height="129" viewBox="0 0 128 129" overflow="visible" enable-background="new 0 0 128 129" xml:space="preserve">'),
                     {'format': 'svg', 'height': 129, 'width': 128})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '<?xml version="1.0"?>\n<svg xmlns:svg="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="100%" height="100%" viewBox="0 -200 800 700">\n  <title>'),
                     {'format': 'svg', 'height': 700, 'width': 800})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '<!----><svg xmlns="http://www.w3.org/2000/svg">\n  <view id="normal" viewBox="0 0 17 19"/>'),
                     {'format': 'svg', 'height': 19, 'width': 17})

  def test_analyze_smil(self):
    self.assertEqual(mediafileinfo_detect.detect_format('<smil\r')[0], 'smil')
    self.assertEqual(mediafileinfo_detect.detect_format('<smil>')[0], 'smil')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '<smil>'),
                     {'format': 'smil'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '<!-- my\ncomment -->\t\t<smil>'),
                     {'format': 'smil'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '<?xml version="1.0" encoding="UTF-8"?>\n<!-- Comment --->\n<!DOCTYPE smil -->\t\f<smil xml:id="root" xmlns="http://www.w3.org/ns/SMIL" version="3.0" baseProfile="Tiny" >'),
                     {'format': 'smil'})

  def test_analyze_brunsli(self):
    self.assertEqual(mediafileinfo_detect.detect_format('\x0a\x04B\xd2\xd5N')[0], 'jpegxl-brunsli')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_brunsli, '0a0442d2d54e120a08810410800418022011'.decode('hex')),
                     {'format': 'jpegxl-brunsli', 'subformat': 'brunsli', 'codec': 'brunsli', 'height': 512, 'width': 513})

  def test_analyze_fuif(self):
    self.assertEqual(mediafileinfo_detect.detect_format('FUIF3.')[0], 'fuif')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_fuif, '46554946332e84017e'.decode('hex')),
                     {'format': 'fuif', 'subformat': 'fuif', 'codec': 'fuif', 'component_count': 3, 'bpc': 8, 'height': 127, 'width': 514})

  def test_analyze_jpegxl(self):
    self.assertEqual(mediafileinfo_detect.detect_format('\xff\x0a--')[0], 'jpegxl')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_jpegxl, 'ff0af81f'.decode('hex')),
                     {'format': 'jpegxl', 'subformat': 'jpegxl', 'codec': 'jpegxl', 'height': 512, 'width': 512})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_jpegxl, 'ff0a7f00'.decode('hex')),
                     {'format': 'jpegxl', 'subformat': 'jpegxl', 'codec': 'jpegxl', 'height': 256, 'width': 256})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_jpegxl, 'ff0ab881a209'.decode('hex')),
                     {'format': 'jpegxl', 'subformat': 'jpegxl', 'codec': 'jpegxl', 'height': 56, 'width': 1234})

  def test_analyze_pik(self):
    self.assertEqual(mediafileinfo_detect.detect_format('P\xccK\x0a')[0], 'pik')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_pik, '50cc4b0a51319400'.decode('hex')),
                     {'format': 'pik', 'subformat': 'pik1', 'codec': 'pik', 'height': 404, 'width': 550})
    self.assertEqual(mediafileinfo_detect.detect_format('\xd7LM\x0a')[0], 'pik')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_pik, 'd74c4d0a45931b00'.decode('hex')),
                     {'format': 'pik', 'subformat': 'pik2', 'codec': 'pik', 'height': 56, 'width': 1234})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_pik, 'd74c4d0afce73f0e'.decode('hex')),
                     {'format': 'pik', 'subformat': 'pik2', 'codec': 'pik', 'height': 512, 'width': 512})

  def test_analyze_qtif(self):
    self.assertEqual(mediafileinfo_detect.detect_format('\0\1\0\x00idat')[0], 'qtif')
    self.assertEqual(mediafileinfo_detect.detect_format('\0\1\0\x00iicc')[0], 'qtif')
    self.assertEqual(mediafileinfo_detect.detect_format('\0\0\0\xffidsc')[0], 'qtif')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_qtif, '\0\0\0\x0bidat\xff\xd8\xff\0\0\x00nidsc\0\0\x00fjpeg\0\0\0\0\0\0\0\0\0\x01\0\x01appl\0\0\0\0\0\0\x02\0\x01\0\x01m\x00H\0\0\x00H\0\0\0\x00Hq\0\x01\x0cPhoto - JPEG\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\x18\xff\xff\0\0\0\x0cgama\0\x01\xcc\xcc\0\0\0\0'),
                     {'format': 'qtif', 'codec': 'jpeg', 'height': 365, 'width': 256})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_qtif, '\0\0\x00nidsc\0\0\x00fjpeg\0\0\0\0\0\0\0\0\0\x01\0\x01appl\0\0\0\0\0\0\x02\0\x01\0\x01m'),
                     {'format': 'qtif', 'codec': 'jpeg', 'height': 365, 'width': 256})

  def test_analyze_psp(self):
    self.assertEqual(mediafileinfo_detect.detect_format('Paint Shop Pro Image File\n\x1a\0\0\0\0\0')[0], 'psp')
    data = 'Paint Shop Pro Image File\n\x1a\0\0\0\0\0\x05\0\0\x00~BK\0\0\x00.\0\0\x00.\0\0\0\xf4\1\0\0\xb9\1\0\0'
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_psp, data),
                     {'format': 'psp', 'height': 441, 'width': 500})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_psp, data + '\0\0\0\0\0\x00R@\1\2\0'),
                     {'format': 'psp', 'height': 441, 'width': 500, 'codec': 'lz77'})

  def test_analyze_ras(self):
    self.assertEqual(mediafileinfo_detect.detect_format('\x59\xa6\x6a\x95')[0], 'ras')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_ras, '\x59\xa6\x6a\x95\0\0\1\xe6\0\0\0\x78'),
                     {'format': 'ras', 'height': 120, 'width': 486})

  def test_analyze_pam(self):
    self.assertEqual(mediafileinfo_detect.detect_format('P7\n#\nWIDTH 1\n')[0], 'pam')
    self.assertEqual(mediafileinfo_detect.detect_format('P7\n\nHEIGHT\t2\n')[0], 'pam')
    self.assertEqual(mediafileinfo_detect.detect_format('P7\nQ RS\nDEPTH\f3\n')[0], 'pam')
    self.assertEqual(mediafileinfo_detect.detect_format('P7\nQ RS\nMAXVAL\v4\n')[0], 'pam')
    self.assertEqual(mediafileinfo_detect.detect_format('P7\nENDHDR\n')[0], 'pam')
    self.assertNotEqual(mediafileinfo_detect.detect_format('P7\nQ RS\n')[0], 'pam')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_pam, 'P7\nWIDTH 227\nDEPTH 3\n# WIDTH 42\nHEIGHT\t\f149\nMAXVAL 255\nTUPLTYPE RGB\nENDHDR\n'),
                     {'format': 'pam', 'codec': 'uncompressed', 'height': 149, 'width': 227})

  def test_analyze_xv_thumbnail(self):
    self.assertEqual(mediafileinfo_detect.detect_format('P7 332\n')[0], 'xv-thumbnail')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_pnm, 'P7 332\n#XVVERSION:Version 2.28  Rev: 9/26/92\n#IMGINFO:512x440 Color JPEG\n#END_OF_COMMENTS\n48 40 255\n'),
                     {'format': 'xv-thumbnail', 'codec': 'uncompressed', 'height': 40, 'width': 48})

  def test_analyze_gem(self):
    self.assertEqual(mediafileinfo_detect.detect_format('\0\1\0\x08\0\2\0\2')[0], 'gem')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_gem, '\0\1\0\x08\0\2\0\2\0\x55\0\x55\1\0\0\x40'),
                     {'format': 'gem', 'subformat': 'nosig', 'codec': 'rle', 'height': 64, 'width': 256})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_gem, '\0\2\0\x3b\0\4\0\1\0\x55\0\x55\1\0\0\x40XIMG\0\0'),
                     {'format': 'gem', 'subformat': 'ximg', 'codec': 'rle', 'height': 64, 'width': 256})

  def test_analyze_pcpaint_pic(self):
    self.assertEqual(mediafileinfo_detect.detect_format('\x34\x12\x40\x01\xc8\0\0\0\0\0\x02\xff\0\0')[0], 'pcpaint-pic')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_pcpaint_pic, '\x34\x12\x40\x01\xc8\0\0\0\0\0\x02\xff\x41\0\0\0\0\2\0'),
                     {'format': 'pcpaint-pic', 'codec': 'rle', 'height': 200, 'width': 320})

  def test_analyze_ivf(self):
    self.assertEqual(mediafileinfo_detect.detect_format('DKIF\0\0 \0')[0], 'ivf')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_ivf, 'DKIF\0\0 \0VP80 \3 \4'),
                     {'format': 'ivf', 'tracks': [{'codec': 'vp8', 'height': 1056, 'type': 'video', 'width': 800}]})

  def test_analyze_wmf(self):
    self.assertEqual(mediafileinfo_detect.detect_format('\xd7\xcd\xc6\x9a\0\0')[0], 'wmf')
    self.assertEqual(mediafileinfo_detect.detect_format('\1\0\x09\0\0\3\x17\x85\0\0\4\0\xf0\x1a\0\0\0\0')[0], 'wmf')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_wmf, '\xd7\xcd\xc6\x9a\0\0'),
                     {'format': 'wmf'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_wmf, '\1\0\x09\0\0\3'),
                     {'format': 'wmf'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_wmf, '\1\0\x09\0\0\3\x17\x85\0\0\4\0\xf0\x1a\0\0\0\0'),
                     {'format': 'wmf'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_wmf, '\xd7\xcd\xc6\x9a\0\0\x58\xf0\xce\xf2\xa8\x0f\x32\x0d\xe8\x03\0\0\0\0'),
                     {'format': 'wmf', 'height': 4232, 'width': 4141})

  def test_analyze_emf(self):
    data1 = '0100000084000000d80100003f02000088110000ac1800000000000000000000085200000474000020454d460000010054ff83005101000004000000'.decode('hex')
    data2 = '010000006c000000ffffffffffffffff640000006b0000000000000000000000f00700007708000020454d46000001005c0a00004c0000000200000000000000000000000000000040060000b004000040010000f000000000000000000000000000000000e2040080a90300460000002c00000020000000454d462b014001001c000000100000000210c0db01000000660000006c000000'.decode('hex')
    self.assertEqual(mediafileinfo_detect.detect_format(data1)[0], 'emf')
    self.assertEqual(mediafileinfo_detect.detect_format(data2)[0], 'emf')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_emf, data1),
                     {'format': 'emf', 'subformat': 'emf', 'height': 842, 'width': 595})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_emf, data2),
                     {'format': 'emf', 'subformat': 'dual', 'height': 61, 'width': 58})

  def test_analyze_minolta_raw(self):
    self.assertEqual(mediafileinfo_detect.detect_format('\0MRM\0\1\2\3\0PRD\0\0\0\x18')[0], 'minolta-raw')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_minolta_raw, '\0MRM\0\1\2\3\0PRD\0\0\0\x18'),
                     {'format': 'minolta-raw', 'codec': 'raw'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_minolta_raw, '\0MRM\0\1\2\3\0PRD\0\0\0\x1827820001\7\x88\x0a\x08\7\x80\x0a\0'),
                     {'format': 'minolta-raw', 'codec': 'raw', 'height': 1920, 'width': 2560})

  def test_analyze_dpx(self):
    self.assertEqual(mediafileinfo_detect.detect_format('SDPX\0\0 \0V2.0')[0], 'dpx')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_dpx, 'SDPX\0\0 \0V2.0'),
                     {'format': 'dpx'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_dpx, 'SDPX\0\0 \0V2.0\0' + 755 * '?' + '\0\0\0\2\0\0\2\3\0\0\2\1' + '?' * 26 + '\0\1'),
                     {'format': 'dpx', 'codec': 'rle', 'height': 513, 'width': 515})

  def test_analyze_cineon(self):
    self.assertEqual(mediafileinfo_detect.detect_format('\x80\x2a\x5f\xd7\0\0??')[0], 'cineon')
    self.assertEqual(mediafileinfo_detect.detect_format('\xd7\x5f\x2a\x80??\0\0')[0], 'cineon')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_cineon, '\x80\x2a\x5f\xd7\0\0??'),
                     {'format': 'cineon', 'codec': 'uncompressed'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_cineon, '\x80\x2a\x5f\xd7\0\0??' + '?' * 192 + '\0\0\2\3\0\0\2\1'),
                     {'format': 'cineon', 'codec': 'uncompressed', 'height': 513, 'width': 515})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_cineon, '\xd7\x5f\x2a\x80??\0\0' + '?' * 192 + '\3\2\0\0\1\2\0\0'),
                     {'format': 'cineon', 'codec': 'uncompressed', 'height': 513, 'width': 515})

  def test_analyze_vicar(self):
    self.assertEqual(mediafileinfo_detect.detect_format('LBLSIZE=10')[0], 'vicar')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_vicar, 'LBLSIZE=10'),
                     {'format': 'vicar'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_vicar, 'LBLSIZE=10 NS=1 NL=2 FOO=bar'),
                     {'format': 'vicar'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_vicar, "LBLSIZE=94   FORMAT='HALF'  TYPE='IMAGE' U1='NS=12' FOO NS=34 U2='NS=56' NL = 789\0NL=5 FOO=bar"),
                     {'format': 'vicar', 'height': 789, 'width': 34})

  def test_analyze_vicar(self):
    self.assertEqual(mediafileinfo_detect.detect_format('LBLSIZE=10')[0], 'vicar')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_vicar, 'LBLSIZE=10'),
                     {'format': 'vicar'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_vicar, 'LBLSIZE=10 NS=1 NL=2 FOO=bar'),
                     {'format': 'vicar'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_vicar, "LBLSIZE=94   FORMAT='HALF'  TYPE='IMAGE' U1='NS=12' FOO NS=34 U2='NS=56' NL = 789\0NL=5 FOO=bar"),
                     {'format': 'vicar', 'height': 789, 'width': 34})

  def test_analyze_pds(self):
    self.assertEqual(mediafileinfo_detect.detect_format('NJPL1I00PDS')[0], 'pds')
    self.assertEqual(mediafileinfo_detect.detect_format('PDS_VERSION_ID\f')[0], 'pds')
    self.assertEqual(mediafileinfo_detect.detect_format('CCSD3ZF')[0], 'pds')
    self.assertEqual(mediafileinfo_detect.detect_format('\xff\0NJPL1I00PDS')[0], 'pds')
    self.assertEqual(mediafileinfo_detect.detect_format('\xff\0PDS_VERSION_ID\f')[0], 'pds')
    self.assertEqual(mediafileinfo_detect.detect_format('\xff\0CCSD3ZF')[0], 'pds')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_pds, 'CCSD3ZF0000100000001\nLINES = 42\r\n  IMAGE\0LINE_SAMPLES = 43'),
                     {'format': 'pds', 'height': 42, 'width': 43})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_pds, '\x20\0NJPL1I00PDS  = XV_COMPATIBILITY \0\x0e\0IMAGE_LINES=42\x0f\0LINE_SAMPLES=43\4\0 END\x0e\0IMAGE_LINES=44'),
                     {'format': 'pds', 'height': 42, 'width': 43})

  def test_analyze_ybm(self):
    self.assertEqual(mediafileinfo_detect.detect_format('!!??')[0], 'ybm')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_ybm, '!!??'),
                     {'format': 'ybm', 'codec': 'uncompressed'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_ybm, '!!\2\3\2\2'),
                     {'format': 'ybm', 'codec': 'uncompressed', 'height': 514, 'width': 515})

  def test_analyze_fbm(self):
    self.assertEqual(mediafileinfo_detect.detect_format('%bitmap\0')[0], 'fbm')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_fbm, '%bitmap\x00'),
                     {'format': 'fbm', 'codec': 'uncompressed'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_fbm, '%bitmap\x00123\x00456\x007890\0???'),
                     {'format': 'fbm', 'codec': 'uncompressed', 'height': 7890, 'width': 123})

  def test_detect_unixscript(self):
    self.assertEqual(mediafileinfo_detect.detect_format('#! /usr/bin/perl')[0], 'unixscript')
    self.assertEqual(mediafileinfo_detect.detect_format('#!/usr/bin/perl')[0], 'unixscript')

  def test_detect_windows_cmd(self):
    self.assertEqual(mediafileinfo_detect.detect_format('@echo off\r\n')[0], 'windows-cmd')
    self.assertEqual(mediafileinfo_detect.detect_format('@ECho oFF\r\n')[0], 'windows-cmd')

  def test_analyze_xwd(self):
    self.assertEqual(mediafileinfo_detect.detect_format('\0\0\0\x65\0\0\0\7\0\0\0\2\0\0\0\x08')[0], 'xwd')
    self.assertEqual(mediafileinfo_detect.detect_format('\x65\0\0\0\7\0\0\0\2\0\0\0\x08\0\0\0')[0], 'xwd')
    self.assertEqual(mediafileinfo_detect.detect_format('\0\0\0\x65\0\0\0\6\0\0\0\0\0\0\0\1\0\0\0\0')[0], 'xwd')
    self.assertEqual(mediafileinfo_detect.detect_format('\x65\0\0\0\6\0\0\0\0\0\0\0\1\0\0\0\0\0\0\0')[0], 'xwd')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xwd, '\0\0\0\x65\0\0\0\7\0\0\0\2\0\0\0\x08\0\0\1\xd3\0\0\0\x3c\0\0\0\0'),
                     {'format': 'xwd', 'subformat': 'x11', 'height': 60, 'width': 467})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xwd, '\x65\0\0\0\7\0\0\0\2\0\0\0\x08\0\0\0\xd3\1\0\0\x3c\0\0\0\0\0\0\0'),
                     {'format': 'xwd', 'subformat': 'x11', 'height': 60, 'width': 467})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xwd, '\0\0\0\x65\0\0\0\6\0\0\0\0\0\0\0\1\0\0\0\0\0\0\1\xd3\0\0\0\x3c'),
                     {'format': 'xwd', 'subformat': 'x10', 'height': 60, 'width': 467})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xwd, '\x65\0\0\0\6\0\0\0\0\0\0\0\1\0\0\0\0\0\0\0\xd3\1\0\0\x3c\0\0\0'),
                     {'format': 'xwd', 'subformat': 'x10', 'height': 60, 'width': 467})

  def test_analyze_dvi(self):
    data1 = '\xf7\2\1\x83\x92\xc0\x1c\x3b\0\0\0\0\3\xe8\x1b TeX output 2020.03.10:0921\x8b\0\0\0\1\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\xff\xff\xff\xff\xef\x21papersize=421.10078pt,597.50787pt'
    self.assertEqual(mediafileinfo_detect.detect_format(data1[:10])[0], 'dvi')
    self.assertEqual(mediafileinfo_detect.detect_format(data1)[0], 'dvi')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_dvi, data1[:10]),
                     {'format': 'dvi'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_dvi, data1),
                     {'format': 'dvi', 'height': 595, 'width': 420})

  def test_analyze_sun_icon(self):
    data1 = '/* Format_version=1, Width=123, Height=45, Depth=1, Valid_bits_per_item=16\n */\n'
    data2 = '/*\r\nFormat_version=1,Width=123,Height=45,'
    data3 = '/* Format_version=1,'
    self.assertEqual(mediafileinfo_detect.detect_format(data1)[0], 'sun-icon')
    self.assertEqual(mediafileinfo_detect.detect_format(data2)[0], 'sun-icon')
    self.assertEqual(mediafileinfo_detect.detect_format(data3)[0], 'sun-icon')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_sun_icon, data1),
                     {'format': 'sun-icon', 'height': 45, 'width': 123})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_sun_icon, data2),
                     {'format': 'sun-icon', 'height': 45, 'width': 123})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_sun_icon, data3),
                     {'format': 'sun-icon'})

  def test_analyze_xbm(self):
    data1 = '#define gs_l_m.xbm_width 4'
    data2 = '#define test_width 16\n#define test_height 7\nstatic unsigned char test_bits[] = {\n  0x13, 0x00, 0x15, 0x00, 0x93, 0xcd, 0x55, 0xa5,'
    self.assertEqual(mediafileinfo_detect.detect_format(data1)[0], 'xbm')
    self.assertEqual(mediafileinfo_detect.detect_format(data2)[0], 'xbm')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xbm, data1),
                     {'format': 'xbm', 'codec': 'uncompressed-ascii'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xbm, data2),
                     {'format': 'xbm', 'codec': 'uncompressed-ascii', 'height': 7, 'width': 16})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xbm, '#define test_width 16\n#define test_height 72'),
                     {'format': 'xbm', 'codec': 'uncompressed-ascii', 'height': 72, 'width': 16})

  def test_analyze_xpm(self):
    self.assertEqual(mediafileinfo_detect.detect_format('#define gs_l_m._format 1\r')[0], 'xpm')
    self.assertEqual(mediafileinfo_detect.detect_format('! XPM2\r')[0], 'xpm')
    self.assertEqual(mediafileinfo_detect.detect_format('/* XPM */\r')[0], 'xpm')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xpm, '#define gs_l_m._format 1\n'),
                     {'format': 'xpm', 'subformat': 'xpm1', 'codec': 'uncompressed-ascii'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xpm, '#define gs_l_m._format 1\n#define gs_l_m._width 16\r\n\n\n#define gs_l_m._height 72'),
                     {'format': 'xpm', 'subformat': 'xpm1', 'codec': 'uncompressed-ascii', 'height': 72, 'width': 16})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xpm, '! XPM2\n'),
                     {'format': 'xpm', 'subformat': 'xpm2', 'codec': 'uncompressed-ascii'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xpm, '! XPM2\r\n16\t7 '),
                     {'format': 'xpm', 'subformat': 'xpm2', 'codec': 'uncompressed-ascii', 'height': 7, 'width': 16})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xpm, '/* XPM */\n\r\t'),
                     {'format': 'xpm', 'subformat': 'xpm3', 'codec': 'uncompressed-ascii'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xpm, '/* XPM */\nstatic char *foo_xpm[] = {\n/* columns rows colors chars-per-pixel */\n"12 \t3456 '),
                     {'format': 'xpm', 'subformat': 'xpm3', 'codec': 'uncompressed-ascii', 'height': 3456, 'width': 12})

  def test_detect_fig(self):
    self.assertEqual(mediafileinfo_detect.detect_format('#FIG 3.2\n')[0], 'fig')

  def test_detect_zoo(self):
    self.assertEqual(mediafileinfo_detect.detect_format('ZOO 2.00 Archive.\x1a\0\0\xdc\xa7\xc4\xfd')[0], 'zoo')
    self.assertEqual(mediafileinfo_detect.detect_format('ZOO 1.20 Archive.\x1a\0\0\xdc\xa7\xc4\xfd')[0], 'zoo')

  def test_detect_arj(self):
    self.assertEqual(mediafileinfo_detect.detect_format('\x60\xea\xe0\4\x1e\6\1\0\x10\0\2')[0], 'arj')

  def test_detect_lha(self):
    self.assertEqual(mediafileinfo_detect.detect_format('*9-lh5-\xa1\5\0\0\xb8\7\0\0\x36\x7d\x6b\x50\2\1')[0], 'lha')

  def test_detect_unknown(self):
    self.assertEqual(mediafileinfo_detect.detect_format('Unknown'), ('?', 'Unknown'))

  def test_analyze_mpeg(self):
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
    self.assertEqual(mediafileinfo_detect.detect_format('\0\0\1\xba')[0], 'mpeg-ps')
    self.assertEqual(mediafileinfo_detect.detect_format(data1)[0], 'mpeg-ps')
    self.assertEqual(mediafileinfo_detect.detect_format(data2)[0], 'mpeg-ps')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_mpeg_ps, '\0\0\1\xba'),
                     {'format': 'mpeg-ps'})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_mpeg_ps, data1),
                     {'format': 'mpeg-ps', 'pes_video_at': 0, 'hdr_skip_count': 0, 'subformat': 'mpeg-2', 'hdr_packet_count': 2, 'hdr_av_packet_count': 1,
                      'tracks': [{'width': 704, 'codec': 'mpeg-2', 'type': 'video', 'header_ofs': 0, 'height': 576}]})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_mpeg_ps, data2),
                     {'format': 'mpeg-ps', 'pes_video_at': 0, 'hdr_skip_count': 0, 'subformat': 'mpeg-1', 'hdr_packet_count': 3, 'hdr_av_packet_count': 1,
                     'tracks': [{'width': 352, 'codec': 'mpeg-1', 'type': 'video', 'header_ofs': 0, 'height': 288}]})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_mpeg_ps, data_video_prev + data_audio + data_dvd + data_video),
                     {'format': 'mpeg-ps', 'hdr_av_packet_count': 3, 'hdr_skip_count': 0, 'subformat': 'dvd-video', 'pes_audio_at': 3, 'hdr_packet_count': 6, 'pes_video_at': 25,
                      'tracks': [track_info_audio, track_info_video]})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_mpeg_ps, data_dvd + data_video + data_audio),
                     {'format': 'mpeg-ps', 'hdr_av_packet_count': 2, 'hdr_skip_count': 0, 'subformat': 'dvd-video', 'pes_audio_at': 3, 'hdr_packet_count': 5, 'pes_video_at': 0,
                      'tracks': [track_info_video0, track_info_audio]})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_mpeg_ps, data_dvd + data_video + data_dvd + data_audio + data_dvd),
                     {'format': 'mpeg-ps', 'hdr_av_packet_count': 2, 'hdr_skip_count': 0, 'subformat': 'dvd-video', 'pes_audio_at': 3, 'hdr_packet_count': 8, 'pes_video_at': 0,
                      'tracks': [track_info_video0, track_info_audio]})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_mpeg_ps, data_audio + data_video),
                     {'format': 'mpeg-ps', 'hdr_av_packet_count': 2, 'hdr_skip_count': 0, 'subformat': 'mpeg-2', 'pes_audio_at': 3, 'hdr_packet_count': 2, 'pes_video_at': 0,
                      'tracks': [track_info_audio, track_info_video0]})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_mpeg_ps, data_audio + data_video + data_dvd),
                     {'format': 'mpeg-ps', 'hdr_av_packet_count': 2, 'hdr_skip_count': 0, 'subformat': 'dvd-video', 'pes_audio_at': 3, 'hdr_packet_count': 5, 'pes_video_at': 0,
                      'tracks': [track_info_audio, track_info_video0]})


if __name__ == '__main__':
  unittest.main(argv=[sys.argv[0], '-v'] + sys.argv[1:])
