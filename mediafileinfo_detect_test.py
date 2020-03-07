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
  return info


class MediaFileInfoDetectTest(unittest.TestCase):

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
                     {'codec': 'rawascii', 'format': 'pnm', 'subformat': 'pbm', 'height': 456, 'width': 123})

  def test_analyze_lbm(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_lbm, 'FORM\0\0\0\x4eILBMBMHD\0\0\0\x14\1\3\1\5'),
                     {'codec': 'rle', 'format': 'lbm', 'height': 261, 'width': 259})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_lbm, 'FORM\0\0\0\x4ePBM BMHD\0\0\0\x14\1\3\1\5'),
                     {'codec': 'uncompressed', 'format': 'lbm', 'height': 261, 'width': 259})

  def test_analyze_pcx(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_pcx, '\n\5\1\x08\0\0\0\0\2\1\4\1'),
                     {'codec': 'rle', 'format': 'pcx', 'height': 261, 'width': 259})

  def test_analyze_xpm(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xpm, '/* XPM */\nstatic char *foo_xpm[] = {\n/* columns rows colors chars-per-pixel */\n"12 3456 '),
                     {'codec': 'uncompressed', 'format': 'xpm', 'height': 3456, 'width': 12})

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
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_vp8, 'd2be019d012a26027001'.decode('hex')),
                     {'format': 'vp8', 'tracks': [{'codec': 'vp8', 'height': 368, 'type': 'video', 'width': 550}]})

  def test_analyze_jpegxr(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_jpegxr, '4949bc012000000024c3dd6f034efe4bb1853d77768dc90c0000000000000000080001bc0100100000000800000002bc0400010000000000000080bc040001000000a005000081bc0400010000006400000082bc0b00010000009af78f4283bc0b00010000009af78f42c0bc04000100000086000000c1bc040001000000369b0200'.decode('hex')),
                     {'codec': 'jpegxr', 'format': 'jpegxr', 'subformat': 'tagged', 'height': 100, 'width': 1440})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_jpegxr, 'WMPHOTO\0\x11\x45\xc0\x71\x05\x9f\x00\x63'),
                     {'codec': 'jpegxr', 'format': 'jpegxr', 'subformat': 'coded', 'height': 100, 'width': 1440})

  def test_analyze_flif(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_flif, 'FLIF\x441\x83\x7f\x83\x7e'),
                     {'format': 'flif', 'codec': 'flif', 'width': 512, 'height': 511})

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

  def test_detect_xml(self):
    self.assertEqual(mediafileinfo_detect.detect_format('<?xml version="1.0" encoding="UTF-8" standalone="no"?>')[0], 'xml')

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

  def test_analyze_xml_svg(self):
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n<!-- Created with Sodipodi ("http://www.sodipodi.com/") -->\n<svg\n   xmlns:xml="http://www.w3.org/XML/1998/namespace"\n   xmlns:dc="http://purl.org/dc/elements/1.1/"\n   xmlns:cc="http://web.resource.org/cc/"\n   xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n   xmlns:svg="http://www.w3.org/2000/svg"\n   xmlns="http://www.w3.org/2000/svg"\n   xmlns:xlink="http://www.w3.org/1999/xlink"\n   xmlns:sodipodi="http://inkscape.sourceforge.net/DTD/sodipodi-0.dtd"\n   xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"\n   id="svg602"\n   sodipodi:version="0.32"\n   width="100.00000pt"\n   height="100.00000pt"\n   xml:space="preserve"\n   sodipodi:docname="english.svg"\n   sodipodi:docbase="/home/terry/.icons/nabi"\n   inkscape:version="0.41"\n   inkscape:export-filename="/home/terry/images/icon/png/NewDir/txtfile.png"\n   inkscape:export-xdpi="200.00000"\n   inkscape:export-ydpi="200.00000"><foo'),
                     {'format': 'svg', 'height': 125, 'width': 125})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '<?xml version="1.0" standalone="no"?>\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN"\n   "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n<!--\n    Designed after data from http://www.wacom-asia.com/download/manuals/BambooUsersManual.pdf\n    Size and positions of controls may not be accurate\n -->\n<svg\n   xmlns="http://www.w3.org/2000/svg"\n   version="1.1"\n   style="color:#000000;stroke:#7f7f7f;fill:none;stroke-width:.25;font-size:8"\n   id="bamboo-2fg"\n   width="208"\n   height="136">\n  <title'),
                     {'format': 'svg', 'height': 136, 'width': 208})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '<svg xmlns = \'http://www.w3.org/2000/svg\' width="099" height="0009px">'),
                     {'format': 'svg', 'height': 9, 'width': 99})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '<svg:svg xmlns = \'http://www.w3.org/2000/svg\' width="2e3" height="0009px">'),
                     {'format': 'svg', 'height': 9, 'width': 2000})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd" [\r\n	<!ENTITY ns_svg "http://www.w3.org/2000/svg">\r\n	<!ENTITY ns_xlink "http://www.w3.org/1999/xlink">\r\n]>\n<svg version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="128" height="129" viewBox="0 0 128 129" overflow="visible" enable-background="new 0 0 128 129" xml:space="preserve">'),
                     {'format': 'svg', 'height': 129, 'width': 128})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '<?xml version="1.0"?>\n<svg xmlns:svg="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="100%" height="100%" viewBox="0 -200 800 700">\n  <title>'),
                     {'format': 'svg', 'height': 700, 'width': 800})
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_xml, '<svg xmlns="http://www.w3.org/2000/svg">\n  <view id="normal" viewBox="0 0 17 19"/>'),
                     {'format': 'svg', 'height': 19, 'width': 17})

  def test_analyze_brunsli(self):
    self.assertEqual(mediafileinfo_detect.detect_format('\x0a\x04B\xd2\xd5N')[0], 'jpegxl-brunsli')
    self.assertEqual(analyze_string(mediafileinfo_detect.analyze_brunsli, '0a0442d2d54e120a08810410800418022011'.decode('hex')),
                     {'format': 'jpegxl-brunsli', 'subformat': 'brunsli', 'codec': 'brunsli', 'height': 512, 'width': 513})


if __name__ == '__main__':
  unittest.main(argv=[sys.argv[0], '-v'] + sys.argv[1:])
