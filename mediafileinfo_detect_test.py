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


if __name__ == '__main__':
  unittest.main(argv=[sys.argv[0], '-v'] + sys.argv[1:])
