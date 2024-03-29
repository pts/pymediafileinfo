# by pts@fazekas.hu at Sun Sep 10 00:26:18 CEST 2017

import struct

# --- Helpers for file format detection for many file formats and getting
# media parameters for some.


def adjust_confidence(base_confidence, confidence):
  return (confidence, max(1, confidence - base_confidence))


XML_WHITESPACE_TAGEND = ('\t', '\n', '\x0b', '\x0c', '\r', ' ', '>')

# Python whitespace (.isspace()).
WHITESPACE = ('\t', '\n', '\x0b', '\x0c', '\r', ' ')

# https://tools.ietf.org/html/draft-ietf-openpgp-rfc4880bis-09#section-9.1
GPG_PUBKEY_ENCRYPTED_ALGOS = ('\1', '\x10', '\x12', '\x13', '\x15', '\x16', '\x17', '\x18')
GPG_PUBKEY_SIGNED_ALGOS = ('\1', '\x11', '\x12', '\x13', '\x15', '\x16', '\x17', '\x18')
# TODO(pts): Are '\2' (RSA encrypt-only), '\3' (RSA sign-only), '\x10' (Elgamal encrypt-only) allowed here? '\x01' and '\x11' are allowed.
GPG_PUBKEY_KEY_ALGOS = ('\1', '\x11', '\x12', '\x13', '\x15', '\x16', '\x17', '\x18')

# https://tools.ietf.org/html/draft-ietf-openpgp-rfc4880bis-09#section-9.3
GPG_CIPHER_ALGOS = ('\1', '\2', '\3', '\4', '\7', '\x08', '\x09', '\x0a')

# https://tools.ietf.org/html/draft-ietf-openpgp-rfc4880bis-09#section-9.5
GPG_DIGEST_ALGOS = ('\1', '\2', '\3', '\x08', '\x09', '\x0a', '\x0b')

# Max byte size: 9 * 256. Typically it's less than 4 * 256 bytes for RSA.
GPG_KEY_BYTE_SHR8_SIZES = ('\0', '\1', '\2', '\3', '\4', '\5', '\6', '\7', '\x08')

MAX_CONFIDENCE = 100000

FORMAT_ITEMS = []


def add_format(format, fclass, spec):  # Call with kwargs.
  # TODO(pts): Check for duplicates.
  if isinstance(spec[0], tuple):
    for spec1 in spec:
      FORMAT_ITEMS.append((format, spec1))
  else:
    FORMAT_ITEMS.append((format, spec))


# ---


def match_spec(spec, fread, info, format):
  """Check whether the beginning of the file matches the Spec.

  See FormatDb for the details of the domain-specific language Spec.

  Returns:
    str containing the first few bytes (header) read with fread.
    Also sets info['format'] to format iff there is a match.
  Raises:
    ValueError: If the header doesn't match the Spec spec.
  """
  specs = spec
  if not isinstance(specs[0], tuple):
    specs = (specs,)
  min_ofs = max_ofs = 0
  for spec in specs:
    ofs1 = ofs2 = 0
    for i in xrange(0, len(spec), 2):
      ofs, pattern = spec[i], spec[i + 1]
      if isinstance(pattern, str):
        ofs1 = ofs = ofs + len(pattern)
      elif isinstance(pattern, tuple):
        ofs1 = ofs = ofs + len(pattern[0])
    min_ofs, max_ofs = min(min_ofs or ofs1, ofs1), max(max_ofs, ofs)
  header = fread(max_ofs)
  if len(header) < min_ofs:
    raise ValueError('Too short for %s.' % format)
  for spec in specs:
    ofs = ofs2 = 0
    for i in xrange(0, len(spec), 2):
      ofs, pattern = spec[i], spec[i + 1]
      if isinstance(pattern, str):
        if header[ofs : ofs + len(pattern)] != pattern:
          break
      elif isinstance(pattern, tuple):
        if header[ofs : ofs + len(pattern[0])] not in pattern:
          break
      elif not pattern(header)[0]:
        break
    else:
      break
  else:
    raise ValueError('%s signature not found.' % format)
  info['format'] = format
  return header


# ---


def set_video_dimens(video_track_info, width, height):
  if width is not None and height is not None:
    video_track_info['width'] = width
    video_track_info['height'] = height
    # We don't check `(height & 7) == 0', because sometimes height == 262.
    if not (16 <= width <= 16383):
      raise ValueError('Unreasonable width: %d' % width)
    if not (16 <= height <= 16383):
      raise ValueError('Unreasonable height: %d' % height)


def set_channel_count(audio_track_info, codec, channel_count):
  if not 1 <= channel_count <= 15:
    raise ValueError('Unreasonable %s channel_count: %d' % (codec, channel_count))
  audio_track_info['channel_count'] = channel_count


def set_sample_rate(audio_track_info, codec, sample_rate):
  if not 1000 <= sample_rate <= 1000000:
    raise ValueError('Unreasonable %s sample_rate: %d' % (codec, sample_rate))
  audio_track_info['sample_rate'] = sample_rate


def set_sample_size(audio_track_info, codec, sample_size):
  if sample_size not in (8, 12, 16, 20, 24, 32, 48, 64):
    raise ValueError('Unreasonable %s sample_size: %d' % (codec, sample_size))
  audio_track_info['sample_size'] = sample_size


# --- flv


def analyze_flv(fread, info, fskip, format='flv', fclass='media',
                spec=(0, 'FLV\1', 5, '\0\0\0\x09\0\0\0\0')):
  # by pts@fazekas.hu at Sun Sep 10 00:26:18 CEST 2017
  #
  # Documented here (starting on page 68, Annex E):
  # http://download.macromedia.com/f4v/video_file_format_spec_v10_1.pdf
  data = fread(13)
  if len(data) < 13:
    raise ValueError('Too short for flv.')

  if not data.startswith('FLV'):
    raise ValueError('flv signature not found.')
  info['format'] = 'flv'
  if data[3] != '\1':
    # Not found any files with other versions in 2017.
    raise ValueError('Only flv version 1 is supported.')
  if data[5 : 9] != '\0\0\0\x09':
    raise ValueError('Bad flv header size.')
  flags = ord(data[4])
  has_audio = bool(flags & 4)
  has_video = bool(flags & 1)
  # Number of tags after which we stop reading.
  audio_remaining, video_remaining = int(has_audio), int(has_video)
  need_script = 1
  # Actually, flag bit 8 should also be 0, but there was an flv in the wild
  # which had this bit set.
  if (flags & ~(5 | 8)) != 0:
    raise ValueError('Nonzero reserved flags: 0x%x' % (flags & ~5))
  if data[9 : 13] != '\0\0\0\0':
    raise ValueError('PreviousTagSize is not 0.')
  info['format' ] = 'flv'
  info['tracks'] = []
  if has_audio:
    audio_track_info = {'type': 'audio'}
    info['tracks'].append(audio_track_info)
  if has_video:
    video_track_info = {'type': 'video'}
    info['tracks'].append(video_track_info)
  nalu_size_size = None
  max_nonaudio_frame_count = 4

  while audio_remaining or video_remaining:
    data = fread(11)
    if len(data) != 11:
      if not data:
        raise ValueError('EOF in flv, waiting for audio=%d video=%d' %
                         (audio_remaining, video_remaining))
      raise ValueError('EOF in flv tag header, got: %d' % len(data))
    size, timestamp, stream_id = struct.unpack('>LL3s', data)
    xtype, size = size >> 24, size & 0xffffff
    if xtype & 0xc0:  # Would affect size.
      raise ValueError('Nonzero reserved xtype flags.')
    if xtype & 0x20:  # Would affect size.
      raise ValueError('Encrypted tag not supported.')
    if xtype not in (8, 9, 15, 18):
      raise ValueError('Unknown tag type: %d' % xtype)
    if stream_id != '\0\0\0':
      raise ValueError('Unexpected stream ID.')
    if xtype != 8:
      if max_nonaudio_frame_count <= 0:
        break  # Don't wait for: EOF in flv, waiting for audio=1 video=0
      max_nonaudio_frame_count -= 1
    if xtype == 8:  # Audio.
      if size < 1:
        raise ValueError('Audio tag too small.')
      if size > 8191:  # TODO(pts): Estimate better.
        raise ValueError('Audio tag unreasonably large: %d' % size)
      data = fread(size)
      if len(data) != size:
        raise ValueError('EOF in tag data.')
      if audio_remaining:
        audio_remaining -= 1
        b = ord(data[0])
        audio_codec_id = b >> 4
        audio_track_info['codec'] = (
            ('pcm', 'adpcm', 'mp3', 'pcm', 'nellymoser', 'nellymoser',
             'nellymoser', 'alaw', 'mulaw', 'reserved9', 'aac',
             'speex', 'reserved13', 'mp3', 'reserved15')[audio_codec_id])
        audio_track_info['sample_rate'] = (  # Sample rate in Hz.
            (5512, 11025, 22050, 44100)[(b >> 2) & 3])
        audio_track_info['sample_size'] = (  # Sample size in bits.
            (8, 16)[(b >> 1) & 1])
        audio_track_info['channel_count'] = (1, 2)[b & 1]
    elif xtype == 9:  # Video.
      if size < 4:
        raise ValueError('Video tag too small.')
      if size >= (1 << 22):  # TODO(pts): Estimate better.
        raise ValueError('Video tag unreasonably large: %d' % size)
      data = fread(size)  # TODO(pts): Skip over most of the tag, save memory.
      if len(data) != size:
        raise ValueError('EOF in tag data.')
      b = ord(data[0])
      video_frame_type_id, video_codec_id = b >> 4, b & 15
      if (video_remaining and
          video_frame_type_id != 5):  # 5 doesn't contain dimensions.
        video_remaining -= 1
        video_track_info['codec'] = (
            ('reserved0', 'reserved1', 'flv1', 'screen', 'vp6',
             'vp6alpha', 'screen2', 'h264', 'u8', 'u9', 'u10',
             'u11', 'u12', 'u13', 'u14', 'u15')[video_codec_id])
        if video_codec_id == 2:  # 'h263', 'flv1', modified H.263, Sorenson Spark.
          # 736 of 1531 .flv files have this codec.
          # See H263VIDEOPACKET in swf-file-format-spec.pdf, v19.
          # https://www.adobe.com/content/dam/acom/en/devnet/pdf/swf-file-format-spec.pdf
          if len(data) < 9:
            raise ValueError('flv1 video tag too short.')
          b, = struct.unpack('>Q', data[1 : 9])
          picture_start_code, version = int(b >> 47), int((b >> 42) & 31)
          if picture_start_code != 1:
            raise ValueError(
                'Bad picture_start_code: 0x%x' % picture_start_code)
          if version not in (0, 1):  # TODO(pts): Do we care?
            raise ValueError('Bad version: 0x%x' % version)
          dimen_id = int((b >> 31) & 7)
          if dimen_id == 0:
            width, height = int((b >> 23) & 255), int((b >> 15) & 255)
          elif dimen_id == 1:
            if len(data) < 10:
              raise ValueError('flv1 video tag too short.')
            b1 = ord(data[9])
            width = int((b >> 15) & 65535)
            height = int((int(b & 32767) << 1) | b1 >> 7)
          elif dimen_id == 7:
            raise ValueError('Bad PictureSize: %d' % dimen_id)
          else:
            width, height = ((352, 288), (176, 144), (128, 96), (320, 240),
                             (160, 120))[dimen_id - 2]
          set_video_dimens(video_track_info, width, height)
        elif video_codec_id in (3, 5):  # ('screen', 'screen2').
          # 0 of 1531 .flv files have this codec. Untested.
          # See SCREENVIDEOPACKET in swf-file-format-spec.pdf, v19.
          # See SCREENV2VIDEOPACKET in swf-file-format-spec.pdf, v19.
          if len(data) < 9:
            raise ValueError('flv screen video frame too short.')
          width, height = struct.unpack('>HH', data[1 : 9])
          width, height = width & 4095, height & 4095
          set_video_dimens(video_track_info, width, height)
        elif video_codec_id in (4, 5):  # ('vp6', 'vp6alpha').
          # https://wiki.multimedia.cx/index.php/On2_VP6#Format
          if len(data) < 10:
            raise ValueError('flv vp6* video frame too short.')
          b = ord(data[1])
          adjust_wd, adjust_ht = b >> 4, b & 15
          if video_codec_id == 4:  # 23 of 1531 .flv files have this codec.
            i = 2
          else:  # 0 of 1531 .flv files have this codec. Untested.
            color_frame_size = struct.unpack('>L', data[2 : 6])[0] >> 8
            if not (8 <= color_frame_size <= len(data) - 4):
              # Actually, AlphaData is also present afterwards, so instead of
              # `- 4' above, we could use `- 12' for stricter checking.
              raise ValueError('Invalid flv vp6alpha color frame size.')
            if len(data) < 13:
              raise ValueError('flv vp6alpha video frame too short.')
            i = 5
          b = ord(data[i])
          frame_mode, qp, marker = b >> 7, (b >> 1) & 63, b & 1
          if frame_mode:
            raise ValueError('Expected first flv vp6* frame as intra frame.')
          version2 = (ord(data[i + 1]) >> 1) & 3
          i += 2 + 2 * (marker or version2 == 0)
          mb_ht16, mb_wd16, display_ht16, display_wd16 = struct.unpack(
              '>BBBB', data[i : i + 4])
          # TODO(pts): Why not use mb_ht16 here?
          width  = (display_wd16 << 4) - adjust_wd
          height = (display_ht16 << 4) - adjust_ht
          set_video_dimens(video_track_info, width, height)
        elif video_codec_id == 7:  # 'avc' and 'h264' are the same.
          # 772 of 1531 .flv files have this codec.
          #
          # We get the dimensions from the SPS in the AVCC.
          # Best explanation of AVCC and NALU:
          # https://stackoverflow.com/a/24890903/97248
          packet_type = ord(data[1])
          if packet_type:  # Packat types 0, 1 and 2 are valid; 0 first.
            # Expecting packet_type 0: AVCDecoderConfigurationRecord (AVCC).
            # Sampe as the avcC box in MP4.
            raise ValueError('Unexpected flv h264 packet type: %d' %
                             packet_type)
          version, lsm, sps_count = ord(data[5]), ord(data[9]), ord(data[10])
          if version != 1:
            raise ValueError('Invalid flv h264 avcc version: %d' % version)
          expected = data[6 : 9]
          # The spec says it should be 255 for both, but here are some .flv
          # files in the wild where these reserved bits are all 0.
          if not ((lsm | 3) in (3, 255) or (sps_count | 31) in (31, 255)):
            raise ValueError('flv h264 avcc reserved bits unset.')
          sps_count &= 31  # Also: lsm &= 3.
          if sps_count != 1:
            raise ValueError('Expected 1 flv h264 avcc sps, got %d' % sps_count)
          if len(data) < 14:
            raise ValueError('EOF in flv h264 avcc sps size.')
          sps_size, = struct.unpack('>H', data[11 : 13])
          if 13 + sps_size > len(data):
            raise ValueError('EOF in flv h264 avcc sps.')
          if data[13] != '\x67':
            raise ValueError('Bad flv h264 avcc sps type.')
          if data[14 : 17] != expected:
            raise ValueError('Unexpected start of flv h264 sps.')
          h264_sps_info = parse_h264_sps(
              buffer(data, 14, sps_size - 1), expected_sps_id=0)
          set_video_dimens(video_track_info,
                           h264_sps_info['width'], h264_sps_info['height'])
    elif xtype in (15, 18):
      # The script tag for YouTube .flv doesn't contain width and height.
      # There are width and height fields defined, they are just not filled
      # in many .flv files, so instead of using this data, we do codec-specific
      # video frame parsing above.
      # TODO(pts): Get more metadata from script.
      if size > 400000:  # 250k was found in the wild.
        raise ValueError('Script tag unreasonably large: %d' % size)
      # The ScriptTagBody contains SCRIPTDATA encoded in the Action Message
      # Format (AMF), which is a compact binary format used to serialize
      # ActionScript object graphs. The specification for AMF0 is available
      # at:
      # http://opensource.adobe.com/wiki/display/blazeds/Developer+Documentation
      script_format = ('amf0', 'amf3')[xtype == 15]
      if not fskip(size):
        raise ValueError('EOF in tag data.')
    data = fread(4)
    if len(data) != 4:
      raise ValueError('EOF in PreviousTagSize.')
    prev_size, = struct.unpack('>L', data)
    # Many .flv files have garbage in the prev_size field, so we are not
    # not checking it. Some garbage: expected=983 got=173;
    # expected=990 got=64880640; expected=533 got=173; expected=29 got=224.
    # The values are sometimes even larger than the file size.
    #if prev_size not in (0, size + 11):
    #  raise ValueError(
    #      'Unexpected PreviousTagSize: expected=%d got=%d' %
    #      (size + 11, prev_size))

  if audio_remaining:
    info['tracks'][:] = [track for track in info['tracks']
                         if track['type'] != 'audio']


# --- mkv

MKV_DOCTYPES = {'matroska': 'mkv', 'webm': 'webm'}

# https://www.matroska.org/technical/specs/codecid/index.html
MKV_CODEC_IDS = {
    'V_UNCOMPRESSED': 'pcm',
    #'V_MS/VFW/$(FOURCC)',  # Microsoft Windows, $(FOURCC) subst.
    #'V_MPEG4/ISO/$(TYPE)',   # $(TYPE) substituted.
    #'V_REAL/$(TYPE)',   # $(TYPE) substituted.
    'V_MPEG4/ISO/SP': 'divx4',
    'V_MPEG4/ISO/ASP': 'divx5',
    'V_MPEG4/ISO/AVC': 'h264',
    'V_MPEG4/ISO/HEVC': 'h265',
    'V_MPEG4/MS/V3': 'divx3',
    'V_MPEGH/ISO/HEVC': 'h265',
    'V_MPEG1': 'mpeg1',
    'V_MPEG2': 'mpeg2',	
    'V_REAL/RV10': 'rv5',
    'V_REAL/RV20': 'rvg2',
    'V_REAL/RV30': 'rv8',
    'V_REAL/RV30': 'rv9',
    'V_QUICKTIME': 'qt',  # Sorenson or Cinepak, more info in CodecPrivate.
    'V_THEORA': 'theora',
    'V_DAALA': 'daala',
    'V_PRORES': 'prores',
    'V_VP3': 'vp3',
    'V_VP4': 'vp4',
    'V_VP5': 'vp5',
    'V_VP6': 'vp6',
    'V_VP7': 'vp7',
    'V_VP8': 'vp8',
    'V_VP9': 'vp9',
    'V_VP10': 'vp10',
    'V_VP11': 'vp11',

    'A_MPEG/L3': 'mp3',
    'A_MPEG/L2': 'mp2',
    'A_MPEG/L1': 'mp1',
    'A_PCM/INT/BIG': 'pcm',  # PCM == linear PCM == raw, uncompressed audio.
    'A_PCM/INT/LIT': 'pcm',
    'A_PCM/FLOAT/IEEE': 'pcm',
    'A_MPC': 'mpc',
    'A_AC3': 'ac3',   # ATSC A/52a https://wiki.multimedia.cx/index.php/A52
    'A_EC3': 'eac3',  # ATSC A/52b https://wiki.multimedia.cx/index.php/A52
    'A_TRUEHD': 'truehd',
    'A_ALAC': 'alac',
    'A_DTS': 'dts',
    'A_DTS/EXPRESS': 'dts-express',
    'A_DTS/LOSSLESS': 'dts-lossless',
    'A_VORBIS': 'vorbis',
    'A_FLAC': 'flac',
    #'A_REAL/$(TYPE)',
    'A_REAL/14_4': 'vslp-ra1',
    'A_REAL/28_8': 'ld-celp-ra2',
    'A_REAL/COOK': 'cook',
    'A_REAL/SIPR': 'sipro',
    'A_REAL/RALF': 'ralf',
    'A_REAL/ATRC': 'atrac3',
    'A_MS/ACM': 'acm',
    #'A_AAC/$(TYPE)/$(SUBTYPE)',
    'A_AAC': 'aac',
    'A_AAC/MPEG2/MAIN': 'aac',
    'A_AAC/MPEG2/LC': 'aac',
    'A_AAC/MPEG2/LC/SBR': 'aac',
    'A_AAC/MPEG2/SSR': 'aac',
    'A_AAC/MPEG4/MAIN': 'aac',
    'A_AAC/MPEG4/LC': 'aac',
    'A_AAC/MPEG4/LC/SBR': 'aac',
    'A_AAC/MPEG4/SSR': 'aac',
    'A_AAC/MPEG4/LTP': 'aac',
    'A_QUICKTIME': 'qt',
    #'A_QUICKTIME/$(TYPE),
    'A_QUICKTIME/QDMC': 'qdmc',
    'A_QUICKTIME/QDM2': 'qdmc2',
    'A_TTA1': 'tta1',
    'A_WAVPACK4': 'wavpack4',
    'A_OPUS': 'opus',
}


def analyze_mkv(fread, info, fskip, format='mkv', extra_formats=('webm',), fclass='media',
                spec=(0, '\x1a\x45\xdf\xa3')):
  # Can also be .webm as a subformat.
  # https://matroska.org/technical/specs/index.html

  # list so that inner functions can modify it.
  #
  # Invariant: ofs_list[0] == f.tell().
  #
  # We use ofs_list so that we don't have to call f.tell(). This is useful
  # for unseekable files.
  ofs_list = [0]

  def read_n(n):
    data = fread(n)
    ofs_list[0] += len(data)
    return data

  def read_id(c=''):
    c = c or read_n(1)
    if not c:
      raise ValueError('EOF in mkv ID 1')
    b = ord(c)
    if b > 127:
      return c
    if b > 63:
      data = read_n(1)
      if not data:
        raise ValueError('EOF in mkv ID 2')
      return c + data
    if b > 31:
      data = read_n(2)
      if len(data) != 2:
        raise ValueError('EOF in mkv ID 3')
      return c + data
    if b > 15:
      data = read_n(3)
      if len(data) != 3:
        raise ValueError('EOF in mkv ID 4')
      return c + data
    raise ValueError('Invalid ID prefix: %d' % b)

  def read_size(c=''):
    c = c or read_n(1)
    if not c:
      raise ValueError('EOF in mkv element size 5')
    if c == '\1':
      data = read_n(7)
      if len(data) != 7:
        raise ValueError('EOF in mkv element size 6')
      if data == '\xff\xff\xff\xff\xff\xff\xff':  # Streaming size.
        raise ValueError('EOF in mkv element size 7')
      return struct.unpack('>Q', '\0' + data)[0]
    b = ord(c)
    if b > 127:
      return b & 127
    if b > 63:
      data = read_n(1)
      if not data:
        raise ValueError('EOF in mkv element size 8')
      return (b & 63) << 8 | ord(data)
    if b > 31:
      data = read_n(2)
      if len(data) != 2:
        raise ValueError('EOF in mkv element size 9')
      return (b & 31) << 16 | struct.unpack('>H', data)[0]
    if b > 15:
      data = read_n(3)
      if len(data) != 3:
        raise ValueError('EOF in mkv element size 10')
      return (b & 15) << 24 | struct.unpack('>L', '\0' + data)[0]
    if b > 7:
      data = read_n(4)
      if len(data) != 4:
        raise ValueError('EOF in mkv element size 11')
      return (b & 7) << 32 | struct.unpack('>L', data)[0]
    if b > 3:
      data = read_n(5)
      if len(data) != 5:
        raise ValueError('EOF in mkv element size 12')
      return (b & 3) << 40 | struct.unpack('>Q', '\0\0\0' + data)[0]
    if b > 1:
      data = read_n(6)
      if len(data) != 6:
        raise ValueError('EOF in mkv element size 13')
      return (b & 1) << 48 | struct.unpack('>Q', '\0\0' + data)[0]
    raise ValueError('Invalid ID prefix: %d' % b)

  def read_id_skip_void(c=''):
    while 1:
      xid, c = read_id(c), ''
      if xid != '\xec':  # Void.
        return xid
      size = read_size()
      if not fskip(size):
        raise ValueError('EOF in Void element.')
      ofs_list[0] += size

  xid = read_n(4)  # xid = read_id()
  if len(xid) != 4:
    raise ValueError('Too short for mkv.')

  if xid != '\x1a\x45\xdf\xa3':
    raise ValueError('mkv signature not found.')
  info['format'], info['tracks'] = 'mkv', []
  c = fread(1)
  if not c:
    return
  ofs_list[0] += 1
  size = read_size(c)
  if size >= 256:
    raise ValueError('mkv header unreasonably large: %d' % size)
  header_end = ofs_list[0] + size
  while ofs_list[0] < header_end:
    xid = read_id_skip_void()
    size = read_size()
    if ofs_list[0] + size > header_end:
      raise ValueError('Size of in-header element too large.')
    data = read_n(size)
    if len(data) != size:
      raise ValueError('EOF in header element.')
    if xid == '\x42\x82':  # DocType.
      # 'matroska' for .mkv, 'webm' for .webm.
      if data not in ('matroska', 'webm'):
        raise ValueError('Unknown mkv DocType: %r' % data)
      info['subformat'] = MKV_DOCTYPES[data]
      if info['subformat'] == 'webm':
        info['brands'] = ['mkv', 'webm']
        info['format'] = 'webm'
      else:
        info['brands'] = ['mkv']
  if 'subformat' not in info:
    raise('mkv DocType not found.')
  c = fread(1)
  if not c:
    return
  ofs_list[0] += 1
  xid = read_id_skip_void(c)
  if xid != '\x18\x53\x80\x67':  # Segment.
    raise ValueError('Expected Segment element, got: %s' % xid.encode('hex'))
  size = read_size()
  segment_end = ofs_list[0] + size
  while ofs_list[0] < segment_end:
    xid = read_id_skip_void()
    size = read_size()
    if ofs_list[0] + size > segment_end:
      raise ValueError('Size of in-Segment element too large.')
    if (xid == '\x11\x4d\x9b\x74' or  # SeekHead.
        xid == '\x15\x49\xa9\x66'):  # Info.
      data = read_n(size)
      if len(data) != size:
        raise ValueError('EOF in SeekHead or Info element.')
    elif xid == '\x16\x54\xae\x6b':  # Tracks.
      tracks_end = ofs_list[0] + size
      while ofs_list[0] < tracks_end:
        xid = read_id_skip_void()
        size = read_size()
        if ofs_list[0] + size > tracks_end:
          raise ValueError('Size of in-Tracks element too large.')
        if xid == '\xbf':  # Some (buggy?) .mkv files have it.
          data = read_n(size)
          if len(data) != size:
            raise ValueError('EOF in bf element.')
          continue
        if xid != '\xae':  # Track.
          raise ValueError('Expected Track element, got: %s' % xid.encode('hex'))
        track_end = ofs_list[0] + size
        track_info = {}
        while ofs_list[0] < track_end:
          xid = read_id_skip_void()
          size = read_size()
          if ofs_list[0] + size > track_end:
            raise ValueError('Size of in-Track element too large.')
          if xid == '\xe0':  # Video.
            track_info['type'] = 'video'
            video_end = ofs_list[0] + size
            width = height = None
            while ofs_list[0] < video_end:
              xid = read_id_skip_void()
              size = read_size()
              if ofs_list[0] + size > video_end:
                raise ValueError('Size of in-Video element too large.')
              data = read_n(size)
              if len(data) != size:
                raise ValueError('EOF in Video element.')
              #print [xid.encode('hex')]
              if xid == '\xb0':  # Width.
                width, = struct.unpack('>Q', '\0' * (8 - len(data)) + data)
              if xid == '\xba':  # Height.
                height, = struct.unpack('>Q', '\0' * (8 - len(data)) + data)
            set_video_dimens(track_info, width, height)
          elif xid == '\xe1':  # Audio.
            track_info['type'] = 'audio'
            audio_end = ofs_list[0] + size
            width = height = None
            while ofs_list[0] < audio_end:
              xid = read_id_skip_void()
              size = read_size()
              if ofs_list[0] + size > audio_end:
                raise ValueError('Size of in-Audio element too large.')
              data = read_n(size)
              if len(data) != size:
                raise ValueError('EOF in Audio element.')
              if xid == '\xb5':  # SamplingFrequency. In Hz.
                if size == 8:
                  track_info['sample_rate'], = struct.unpack('>d', data)
                elif size == 4:
                  track_info['sample_rate'], = struct.unpack('>f', data)
                else:
                  raise ValueError('Expected size float, got size: %d' % size)
              if xid == '\x9f':  # Channels.
                track_info['channel_count'], = struct.unpack(
                    '>Q', '\0' * (8 - len(data)) + data)
              if xid == '\x62\x64':  # BitDepth.
                track_info['sample_size'], = struct.unpack(
                    '>Q', '\0' * (8 - len(data)) + data)
          elif xid == '\x86':  # CodecID.
            data = read_n(size)
            if len(data) != size:
              raise ValueError('EOF in CodecID element.')
            data = data.rstrip('\0')  # Broken, but some mkv files have it.
            track_info['codec'] = MKV_CODEC_IDS.get(data, data)
          elif xid == '\x63\xA2':  # CodecPrivate.
            data = read_n(size)
            if len(data) != size:
              raise ValueError('EOF in CodecPrivate element.')
            track_info['codec_private'] = data
          elif xid == '\x25\x86\x88':  # CodecName.
            data = read_n(size)
            if len(data) != size:
              raise ValueError('EOF in CodecName element.')
            track_info['codec_name'] = data  # Usually not set in .webm.
          else:
            data = read_n(size)
            if len(data) != size:
              raise ValueError('EOF in in-Track element.')
        if 'type' in track_info:
          data = track_info.pop('codec_private', None)
          if data and track_info['codec'] == 'V_MS/VFW/FOURCC':
            dib_info = {}
            try:
              parse_dib_header(dib_info, data)  # Function dependency.
            except ValueError:
              pass
            try:
              codec = int(dib_info.get('codec', ''))
            except ValueError:
              codec = None
            if codec:
              # Function dependency.
              track_info['codec'] = get_windows_video_codec(struct.pack('<L', codec))
            for key in ('width', 'height'):
              if key in dib_info:
                track_info[key] = dib_info[key]
          info['tracks'].append(track_info)
      break  #  in Segment, don't read anything beyond Tracks, they are large.
    else:
      # TODO(pts): Ignore: Unexpected ID in Segment: 1043a770
      raise ValueError('Unexpected ID in Segment: %s' % xid.encode('hex'))
  return info


# --- mp4

# See all on: http://mp4ra.org/codecs.html
# All keys are converted to lowercase, and whitespace-trimmed.
MP4_VIDEO_CODECS = {
    'avc1': 'h264',
    'h264': 'h264',
    'mp4v': 'divx5',  # https://en.wikipedia.org/wiki/MPEG-4_Part_2
    'mp4s': 'divx5',
    'rv60': 'rv6',  # RealVideo.
    's263': 'h263',
    'mjp2': 'mjpeg2000',
    'mjpa': 'mjpeg',
    'mjpb': 'mjpeg',
    'mjpg': 'mjpeg',
    'svq1': 'sorenson1',
    'svq3': 'sorenson3',
    'mpgv': 'mpeg2',
    'div1': 'divx',
    'divx': 'divx',
    'xvid': 'divx',
    'dx50': 'divx5',
    'fmp4': 'divx5',
    'dvav': 'h264',
    'dvhc': 'h265',
    'hev1': 'h265',  # Difference between hev1 and hvc1 (both h265): https://stackoverflow.com/a/63471265 .
    'hvc1': 'h265',
    'av01': 'av1',
    'vc-1': 'vc1',
    'vp03': 'vp3',
    'vp04': 'vp4',
    'vp05': 'vp5',
    'vp06': 'vp6',
    'vp07': 'vp7',
    'vp08': 'vp8',
    'vp09': 'vp9',
    'vp10': 'vp10',
    'vp11': 'vp11',
    'jpeg': 'jpeg',  # For qtif.
    'kpcd': 'photocd',  # For pict.
}

# See all on: http://mp4ra.org/#/codecs
# All keys are converted to lowercase, and whitespace-trimmed.
# Also includes AIFC (AIFF_C) codecs.
MP4_AUDIO_CODECS = {
    'raw':  'pcm',
    'sowt': 'pcm',
    'twos': 'pcm',
    'in24': 'pcm',
    'in32': 'pcm',
    'fl32': 'pcm',
    'fl64': 'pcm',
    'none': 'pcm',
    'pcm' : 'pcm',
    'sowt': 'pcm',
    'alaw': 'alaw',   # Logarithmic PCM wih A-Law
    'ulaw': 'mulaw',  # Logarithmic PCM wih mu-Law.
    'ace2': 'ace2',
    'ace8': 'ace8',
    'mac3': 'mac3',
    'mac6': 'mac6',
    '.mp3': 'mp3',
    'mp3':  'mp3',
    'mp4a': 'mp4a',  # Similar to aac, but contains more.
    'mp4s': 'mp4a',
    'samr': 'samr',
    'mpga': 'mp2',
    'sawb': 'sawb',
    'dts+': 'dts',
    'dts-': 'dts',
    'dtsc': 'dts',
    'dtse': 'dts',
    'dtsh': 'dts',
    'dtsl': 'dts',
    'dtsx': 'dts',
    'ac-3': 'ac3',
    'ec-3': 'enhanced-ac3',
    'ac-4': 'ac4',
}

JP2_CODECS = {
    0: 'uncompressed',
    1: 'huffman2',
    2: 'read2',
    3: 'read3',
    4: 'jbig',
    5: 'jpeg',
    6: 'jpegls',
    7: 'jpeg2000',
    8: 'jbig2',
}


ISOBMFF_IMAGE_SUBFORMATS = {
    'hvc1': 'heif',  # *.heic.
    'av01': 'avif',  # *.avif.
}


def is_mp4(header):
  return len(header) >= 4 and header.startswith('\0\0\0') and ord(header[3]) >= 16 and (ord(header[3]) & 3) == 0


def parse_isobmff_ipma_box(version, flags, data):
  # https://github.com/gpac/mp4box.js/blob/master/src/parsing/ipma.js
  i, size = 0, len(data)
  if i + 4 > size:
    raise ValueError('EOD in isobmff ipma entry_count.')
  entry_count, = struct.unpack('>L', buffer(data, i, 4))
  i += 4
  result = {}
  for _ in xrange(entry_count):
    assoc_id_size = 2 + (bool(version) << 1)
    assoc_id_fmt = ('>H', '>L')[bool(version)]
    if i + assoc_id_size > size:
      raise ValueError('EOD in isobmff ipma assoc_id.')
    assoc_id, = struct.unpack(assoc_id_fmt, buffer(data, i, assoc_id_size))
    if assoc_id in result:
      raise ValueError('Duplicate isobmff ipma assoc_id.')
    i += assoc_id_size
    if i >= size:
      raise ValueError('EOD in isobmff ipma assoc_count.')
    assoc_count = ord(data[i])
    i += 1
    assoc_property_indexes = []
    for _ in xrange(assoc_count):
      property_index_size = 1 + (flags & 1)
      property_index_fmt = ('>B', '>H')[flags & 1]
      if i + property_index_size > size:
        raise ValueError('EOD in isobmff ipma property_index.')
      property_index, = struct.unpack(property_index_fmt, buffer(data, i, property_index_size))
      i += property_index_size
      property_index = (property_index & (0x7f, 0x7fff)[flags & 1]) - 1
      if property_index < 0:
        raise ValueError('Bad isobmff ipma property_index.')
      assoc_property_indexes.append(property_index)
    if len(set(assoc_property_indexes)) != len(assoc_property_indexes):
      raise ValueError('Bad isobmff ipma assoc_property_indexes, it has duplicates.')
    result[assoc_id] = assoc_property_indexes
  return result


def parse_isobmff_infe_box(version, flags, data):
  # https://github.com/gpac/mp4box.js/blob/master/src/parsing/infe.js
  i, size = 0, len(data)
  item_id_size = 2 + ((version == 3) << 1)
  item_id_fmt = ('>H', '>L')[item_id_size > 2]
  if i + item_id_size > size:
    raise ValueError('EOD in isobmff infe item_id.')
  item_id, = struct.unpack(item_id_fmt, buffer(data, i, item_id_size))
  i += item_id_size
  if i + 2 > size:
    raise ValueError('EOD in isobmff infe item_protection_index.')
  item_protection_index, = struct.unpack('>H', buffer(data, i, 2))
  i += 2
  if version >= 2:
    if i + 4 > size:
      raise ValueError('EOD in isobmff infe item_type.')
    item_type = data[i : i + 4]
    i += 4
  else:
    item_type = None
  return {item_id: (item_protection_index, item_type)}


def is_jp2(header):
  return (len(header) >= 28 and
          header.startswith('\0\0\0\x0cjP  \r\n\x87\n\0\0\0') and
          header[16 : 20] == 'ftyp' and
          header[20 : 24] in ('jp2 ', 'jpm ', 'jpx '))


def analyze_mov(
    fread, info, fskip, header='', format='mov', fclass='media',
    extra_formats=('mp4', 'jp2', 'isobmff-image', 'f4v'),
    spec=(
        # TODO(pts): Add support for ftyp=mis1 (image sequence) or ftyp=hevc, ftyp=hevx.
        (0, '\0\0\0', 4, 'ftyp', 8, ('qt  ', 'f4v ', 'isom', 'mp41', 'mp42', 'jp2 ', 'jpm ', 'jpx '), 12, lambda header: (is_mp4(header), 26)),
        (0, '\0\0\0', 4, 'ftyp', 8, lambda header: (is_mp4(header), 26)),
        (4, 'mdat'),  # TODO(pts): Analyze mpeg inside, if any.
        # This box ('wide', 'free' or 'skip'), after it's data, is immediately
        # followed by an 'mdat' box (typically 4-byte size, then 'mdat'), but we
        # can't detect 'mdat' here, it's too far for us.
        (0, '\0\0', 4, ('wide', 'free', 'skip', 'junk')),
        (0, '\0', 1, ('\0', '\1', '\2', '\3', '\4', '\5', '\6', '\7', '\x08'), 4, ('moov',)),
        (0, '\0\0\0', 4, 'ftypmif1', 12, lambda header: (is_mp4(header), 26)),  # 'isobmff-image'.
        # format='jp2': JPEG 2000 container format.
        (0, '\0\0\0\x0cjP  \r\n\x87\n\0\0\0', 28, lambda header: (is_jp2(header), 750)),
    )):
  # Documented here: http://xhelmboyx.tripod.com/formats/mp4-layout.txt
  # Also apple.com has some .mov docs.

  data, header = header, None
  info['format'] = 'mov'
  info['brands'] = []
  info['tracks'] = []
  info['has_early_mdat'] = False

  # Empty or contains the type of the last hdlr.
  last_hdlr_type_list = []

  infe_count_ary = []
  item_infos = {}  # {item_id: (item_protection_index, item_type)}.
  primary_item_id_ary = []
  ipco_boxes = []
  ipma_values = []

  def process_ftyp(data):
    # See also: http://www.ftyps.com/
    # See also: http://www.ftyps.com/3gpp.html
    # Typically major_brand in (
    #    'qt  ', 'dash', 'MSNV', 'M4A ', 'M4V ', 'f4v ',
    #    '3gp5', 'avc1', 'iso2', 'iso5', 'iso6', 'isom', 'mp41', 'mp42').
    if len(data) < 8:
      raise ValueError('EOF in mp4 ftyp.')
    major_brand, info['minor_version'] = struct.unpack('>4sL', data[:8])
    # Usually 0, but has some high (binary) value for major_brand ==
    # 'qt '.
    info['minor_version'] = int(info['minor_version'])
    if major_brand == 'qt  ':
      info['format'] = 'mov'
    elif major_brand == 'f4v ':
      info['format'] = 'f4v'
    elif major_brand in ('jp2 ', 'jpm ', 'jpx '):
      info['format'] = 'jp2'  # JPEG 2000.
    elif major_brand == 'mif1':
      # Contains items in /meta.
      info['format'] = 'isobmff-image'
    else:
      info['format'] = None
    info['subformat'] = major_brand.strip()
    brands = set(data[i : i + 4] for i in xrange(8, len(data), 4))
    brands.discard('\0\0\0\0')
    brands.add(major_brand)
    if info['format'] is not None:
      pass
    elif 'mif1' in brands:  # iPhone .heic files have major_brand == 'heic'.
      info['format'] = 'isobmff-image'
    else:
      info['format'] = 'mp4'
    brands = sorted(brands)
    info['brands'] = brands  # Example: ['isom', 'mp42'].

  def process_box(size):
    """Dumps the box, and must read it (size bytes)."""
    xtype = xtype_path[-1]
    xytype = '/'.join(xtype_path[-2:])
    # Only the composites we care about.
    is_composite = xytype in (
        '/moov', '/jp2h', 'moov/trak', 'trak/mdia', 'mdia/minf', 'minf/stbl',
        '/meta', 'meta/iprp', 'iprp/ipco', 'meta/iinf')
    #print 'process_box xtypes=%r size=%d is_composite=%d' % ('/'.join(xtype_path), size, is_composite)
    if xtype == 'mdat':  # 816 of 2962 mp4 files have it.
      # Videos downloaded by youtube-dl (usually) don't have it: in the corpus
      # only 11 of 1418 videos have it, but maybe they were downloaded
      # differently.
      #
      # mdat boxes are huge (because they contain all the audio and video
      # frames), and an early mdat box (before the moov box) indicates that
      # the user needs to download the entire file before playback can start
      # (because the interpretation of the mdat box depends on the contents
      # of the moov box).
      info['has_early_mdat'] = True
    if xytype == '/meta' and info['format'] != 'isobmff-image':
      is_composite = False
    elif xytype in ('/meta', 'meta/iinf', 'meta/pitm', 'iprp/ipma', 'iinf/infe'):
      if size < 4:
        raise ValueError('mp4 full box too small.')
      data = fread(4)
      if len(data) < 4:
        raise ValueError('EOF in mp4 full box header.')
      version, = struct.unpack('>L', data)
      flags = version & 0xffffff
      version >>= 3
      size -= 4
    if xytype in ('meta/iinf', 'meta/pitm'):
      if infe_count_ary:
        raise ValueError('Multiple many %s boxes.' % xytype)
      count_size = 2 + (bool(version) << 1)
      if size < count_size:
        raise ValueError('mp4 %s too small for count_size.' % xytype)
      size -= count_size
      data = fread(count_size)
      if len(data) < count_size:
        raise ValueError('EOF in mp4 %s count.' % xytype)
      if count_size == 2:
        count, = struct.unpack('>H', data)
      else:
        count, = struct.unpack('>L', data)
    if is_composite:
      if xytype == 'trak/mdia':
        if last_hdlr_type_list and 'd' not in last_hdlr_type_list:
          # stsd not found, still report the track.
          if last_hdlr_type_list[0] == 'vide':
            info['tracks'].append({'type': 'video'})
          elif last_hdlr_type_list[0] == 'soun':
            info['tracks'].append({'type': 'audio'})
        del last_hdlr_type_list[:]
      elif xytype == 'meta/iinf':
        infe_count_ary.append(count)
      ofs_limit = size
      while ofs_limit > 0:  # Dump sequences of boxes inside.
        #print 'composite xtypes=%r ofs_limit=%d' % ('/'.join(xtype_path), ofs_limit)
        if ofs_limit < 8:
          raise ValueError('EOF in mp4 composite box size.')
        size2, xtype2 = struct.unpack('>L4s', fread(8))
        if not (8 <= size2 <= ofs_limit):
          raise ValueError(
              'EOF in mp4 composite box, xtype=%r size=%d ofs_limit=%d' %
              (xtype2, size2, ofs_limit))
        ofs_limit -= size2
        xtype_path.append(xtype2)
        process_box(size2 - 8)
        xtype_path.pop()
    else:
      if size > 16383 or xtype in ('free', 'skip', 'wide', 'junk', 'mdat'):
        if not fskip(size):
          raise ValueError('EOF while skipping mp4 box, xtype=%r' % xtype)
      else:
        data = fread(size)
        if len(data) != size:
          raise ValueError('EOF in mp4 box, xtype=%r' % xtype)
        if xytype == '/ftyp':
          process_ftyp(data)
        elif xytype == 'jp2h/ihdr':  # JPEG 2000.
          if len(data) < 12:
            raise ValueError('EOF in jp2 ihdr.')
          # https://sno.phy.queensu.ca/~phil/exiftool/TagNames/Jpeg2000.html#ImageHeader
          height, width, component_count, bpc, codec = struct.unpack(
              '>LLHBB', data[:12])
          info['width'] = width
          info['height'] = height
          info['component_count'] = component_count
          info['bpc'] = bpc  # Bits per component.
          # TODO(pts): JPX (http://fileformats.archiveteam.org/wiki/JPX),
          # major_brand == 'jpx ' allows other codecs as well.
          info['codec'] = JP2_CODECS.get(codec, str(codec))
        #elif xytype == 'trak/tkhd':  # /moov/trak/tkhd
        #  # Don't process tkhd, it's unreliable in some mp4 files.
        #  if track_tkhd_data[0] == '\0':  # 32-bit.
        #    width, height = struct.unpack('>LL', track_tkhd_data[74 : 74 + 8])
        #  else:  # 64-bit.
        #    width, height = struct.unpack('>LL', track_tkhd_data[86 : 86 + 8])
        elif xytype == 'mdia/hdlr':  # /moov/trak/mdia/hdlr
          del last_hdlr_type_list[:]
          if len(data) < 12:
            raise ValueError('EOF in mp4 hdlr.')
          last_hdlr_type_list.append(data[8 : 12])
        elif xytype == 'stbl/stsd':  # /moov/trak/mdia/minf/stbl/stsd
          if not last_hdlr_type_list:
            raise ValueError('Found mp4 stsd without a hdlr first.')
          if len(data) < 8:
            raise ValueError('mp4 ststd too short.')
          version_and_flags, count = struct.unpack('>LL', data[:8])
          if version_and_flags:
            raise ValueError('Bad mp4 stsd bad_version_and_flags=%d' % version_and_flags)
          i = 8
          while i < len(data):
            if len(data) - i < 8:
              raise ValueError('mp4 stsd item size too short.')
            if not count:
              raise ValueError('Too few mp4 stsd items.')
            # codec usually indicates the codec, e.g. 'avc1' for video and 'mp4a' for audio.
            ysize, codec = struct.unpack('>L4s', data[i : i + 8])
            codec = codec.strip().lower()  # Remove whitespace, e.g. 'raw'.
            if ysize < 8 or i + ysize > len(data):
              raise ValueError('Bad mp4 stsd item size.')
            yitem = data[i + 8 : i + ysize]
            last_hdlr_type_list.append('d')  # Signal above.
            # The 'rle ' codec has ysize < 28.
            if last_hdlr_type_list[0] == 'vide':
              # Video docs: https://developer.apple.com/library/content/documentation/QuickTime/QTFF/QTFFChap3/qtff3.html#//apple_ref/doc/uid/TP40000939-CH205-BBCGICBJ
              if ysize < 28:
                raise ValueError('Video stsd too short.')
              reserved1, data_reference_index, version, revision_level, vendor, temporal_quality, spatial_quality, width, height = struct.unpack('>6sHHH4sLLHH', yitem[:28])
              video_track_info = {
                  'type': 'video',
                  'codec': MP4_VIDEO_CODECS.get(codec, codec),
              }
              if codec == 'rle' and (width < 16 or height < 16):
                # Skip it, typically width=32 height=2. Some .mov files have it.
                pass
              else:
                info['tracks'].append(video_track_info)
                set_video_dimens(video_track_info, width, height)
            elif last_hdlr_type_list[0] == 'soun':
              # Audio: https://developer.apple.com/library/content/documentation/QuickTime/QTFF/QTFFChap3/qtff3.html#//apple_ref/doc/uid/TP40000939-CH205-BBCGGHJH
              # Version can be 0 or 1.
              # Audio version 1 adds 4 new 4-byte fields (samples_per_packet, bytes_per_packet, bytes_per_frame, bytes_per_sample)
              if ysize < 28:
                raise ValueError('Audio stsd too short.')
              reserved1, data_reference_index, version, revision_level, vendor, channel_count, sample_size_bits, compression_id, packet_size, sample_rate_hi, sample_rate_lo = struct.unpack('>6sHHHLHHHHHH', yitem[:28])
              info['tracks'].append({
                  'type': 'audio',
                  'codec': MP4_AUDIO_CODECS.get(codec, codec),
                  'channel_count': channel_count,
                  'sample_size': sample_size_bits,
                  'sample_rate': sample_rate_hi + (sample_rate_lo / 65536.0),
              })
            i += ysize
            count -= 1
          if count:
            raise ValueError('Too many mp4 stsd items.')
        elif xytype == 'iinf/infe':
          for item_id, item_info in sorted(parse_isobmff_infe_box(version, flags, data).iteritems()):
            if item_id in item_infos:
              raise ValueError('Duplicate isobmff-image item_id.')
            item_infos[item_id] = item_info
        elif xytype == 'meta/pitm':
          if primary_item_id_ary:
            raise ValueError('Duplicate box meta/pitm.')
          primary_item_id_ary.append(count)
        elif xytype == 'iprp/ipma':
          if ipma_values:
            raise ValueError('Duplicate box iprp/ipma.')
          ipma_values.append(parse_isobmff_ipma_box(version, flags, data))
        elif xytype.startswith('ipco/'):
          ipco_boxes.append((xtype, data))

  xtype_path = ['']
  toplevel_xtypes = set()
  while 1:
    if len(data) < 8:
      data = fread(8 - len(data))
      if len(data) < 8:
        # Sometimes this happens, there is a few bytes of garbage, but we
        # don't reach it, because we break after 'moov' earlier below.
        toplevel_xtypes.discard('free')
        toplevel_xtypes.discard('skip')
        toplevel_xtypes.discard('wide')
        toplevel_xtypes.discard('junk')
        if 'mdat' in toplevel_xtypes and len(toplevel_xtypes) == 1:
          # This happens. The mdat can be any video, we could process
          # recursively. (But it's too late to seek back.)
          # TODO(pts): Convert this to bad_file_mdat_only error.
          # TODO(pts): Allow mpeg file (from mac).
          raise ValueError('mov file with only an mdat box.')
        if 'moov' in toplevel_xtypes:  # Can't happen, see break below.
          raise AssertionError('moov forgotten.')
        raise ValueError('mp4 moov box not found.')
    size, xtype = struct.unpack('>L4s', data[:8])
    toplevel_xtypes.add(xtype)
    if size >= 8 and xtype in ('ftyp', 'jP  '):
      if size > 16383 + 8:
        raise ValueError('mp4 %s box size too large.' % xtype)
      if len(data) < size:
        data += fread(size - len(data))
        if len(data) < size:
          raise ValueError('EOF in mp4 %s box.' % xtype)
      if xtype == 'ftyp':
        process_ftyp(data[8 : size])
      data = data[size:]
    elif len(data) > 8:
      raise ValueError('mp4 preread too long.')
    else:
      data = ''
      if size == 1:  # Read 64-bit size.
        data = fread(8)
        if len(data) < 8:
          raise ValueError('EOF in top-level 64-bit mp4 box size.')
        size, = struct.unpack('>Q', data)
        if size < 16:
          raise ValueError('64-bit mp4 box size too small.')
        size -= 16
        data = ''
      elif size >= 8:
        size -= 8
      else:
        # We don't allow size == 0 (meaning until EOF), because we want to
        # finish the small track parameter boxes first (before EOF).
        raise ValueError('mp4 box size too small for xtype %r: %d' % (xtype, size))
      xtype_path.append(xtype)
      process_box(size)
      xtype_path.pop()
    if info['format'] == 'jp2':
      if xtype == 'jp2h':  # All JP2 track parameters already found, stop looking.
        break
    elif info['format'] == 'isobmff-image':
      if xtype == 'meta':  # All mif1 image parameters already found, stop looking.
        break
    else:
      if xtype == 'moov':  # All track parameters already found, stop looking.
        break

  if info['format'] == 'isobmff-image':
    # https://standards.iso.org/ittf/PubliclyAvailableStandards/c068960_ISO_IEC_14496-12_2015.zip
    # isobmff is technically incorrect, it doesn't have moov.
    # https://github.com/m-hiki/isobmff
    # https://mpeg.chiariglione.org/standards/mpeg-h/image-file-format/text-isoiec-cd-23008-12-image-file-format
    # https://nokiatech.github.io/heif/technical.html
    # https://gpac.github.io/mp4box.js/test/filereader.html
    # https://www.w3.org/TR/mse-byte-stream-format-isobmff/
    # https://aomediacodec.github.io/av1-isobmff/
    # https://aomediacodec.github.io/av1-avif/
    # https://github.com/AOMediaCodec/av1-avif/wiki
    assert not info['tracks'], 'Unexpected tracks.'
    del info['tracks']
    if not infe_count_ary:
      raise ValueError('Missing isobmff-image item information.')
    if len(item_infos) != infe_count_ary[0]:
      raise ValueError('Inconsistent isobmff-image infe box count.')
    if not primary_item_id_ary:
      raise ValueError('Missing isobmff-image primary_item_id.')
    if not ipma_values:
      raise ValueError('Missing isobmff-image ipma box.')
    if not ipco_boxes:
      raise ValueError('Missing isobmff-image ipco boxes.')
    if primary_item_id_ary[0] not in item_infos:
      raise ValueError('Missing isobmff-image item info for primary_item_id.')
    if primary_item_id_ary[0] not in ipma_values[0]:
      raise ValueError('Missing isobmff-image ipco for primary_item_id.')
    primary_ispe_boxes = []
    for ipco_idx in ipma_values[0][primary_item_id_ary[0]]:
      if ipco_idx >= len(ipco_boxes):
        raise ValueError('Bad isobmff-image ipco index for primary_item_id.')
      if ipco_boxes[ipco_idx][0] == 'ispe':
        primary_ispe_boxes.append(ipco_boxes[ipco_idx][1])
    if not primary_ispe_boxes:
      raise ValueError('Missing isobmff-image ispe for primary_item_id.')
    if len(primary_ispe_boxes) > 1:
      raise ValueError('Duplicate isobmff-image ispe for primary_item_id.')
    if len(primary_ispe_boxes[0]) < 12:
      raise ValueError('EOD in isobmff-image ispe.')
    info['width'], info['height'] = struct.unpack('>LL', buffer(primary_ispe_boxes[0], 4, 8))
    codec = item_infos[primary_item_id_ary[0]][1].strip().lower()
    if codec == 'grid':
      gcodecs = [gcodec for gcodec in
                 (item_info[1] for item_info in item_infos.itervalues())
                 if gcodec not in ('mime', 'Exif', 'grid')]
      # In iPhone .heic files gcodecs contains 50 instances of 'hvc1'. We
      # will use the most common gcodec with count >= 4.
      gccs = {}
      for gcodec in gcodecs:
        gccs[gcodec] = gccs.get(gcodec, 0) + 1
      gccs = [(item[1], item[0]) for item in gccs.iteritems() if item[1] >= 4]
      if gccs:
        codec = max(gccs)[1]
    if codec is not None:
      # Typically codec is 'hvc1' for .heic and 'av01' or .avif.
      info['codec'] = MP4_VIDEO_CODECS.get(codec, codec)
      subformat = ISOBMFF_IMAGE_SUBFORMATS.get(codec)
      if subformat:
        info['subformat'] = subformat


def noformat_analyze_jp2(fread, info, fskip):
  header = fread(28)
  if len(header) < 28:
    raise ValueError('Too short for jp2.')
  if not is_jp2(header):
    raise ValueError('jp2 signature not found.')
  info['format'] = 'jp2'  # analyze_mov also sets it from ftyp.
  analyze_mov(fread, info, fskip, header=header)


def is_jpc(header):
  return (len(header) >= 6 and
          header.startswith('\xff\x4f\xff\x51\0') and
          # 1..10 components.
          ord(header[5]) % 3 == 2 and 41 <= ord(header[5]) <= 68)


def analyze_jpc(fread, info, fskip, header='', format='jpc', fclass='image',
                spec=(0, '\xff\x4f\xff\x51\0', 5, tuple(chr(38 + 3 * c) for c in xrange(1, 11)))):
  # JPEG 2000 codestream (elementary stream, bitstream).
  # http://fileformats.archiveteam.org/wiki/JPEG_2000_codestream
  # Annex A of http://www.hlevkin.com/Standards/fcd15444-1.pdf
  if len(header) < 24:
    header += fread(24 - len(header))
  if len(header) < 6:
    raise ValueError('Too short for jpc.')
  if not is_jpc(header):
    raise ValueError('jpc signature not found.')
  info['format'], info['codec'] = 'jpc', 'jpeg2000'
  if len(header) >= 24:
    (magic, lsiz, rsiz, xsiz, ysiz, xosiz, yosiz,
    ) = struct.unpack('>4sHHLLLL', header[:24])
    info['width'], info['height'] = struct.unpack('>LL', header[8 : 16])


def noformat_analyze_jpeg2000(fread, info, fskip):
  header = fread(28)
  if len(header) < 6:
    raise ValueError('Too short for jpeg2000.')
  if is_jp2(header):
    info['format'] = 'jp2'  # analyze_mov also sets it from ftyp.
    analyze_mov(fread, info, fskip, header=header)
  elif is_jpc(header):
    analyze_jpc(fread, info, fskip, header=header)
  else:
    raise ValueError('jpeg2000 signature not found.')


def analyze_pnot(fread, info, fskip):
  # https://wiki.multimedia.cx/index.php/QuickTime_container#pnot
  # https://developer.apple.com/standards/qtff-2001.pdf
  header = fread(20)
  if len(header) < 20:
    raise ValueError('Too short for pnot.')
  atom_size, atom_type, modification_date, version, preview_type, preview_index = struct.unpack(
      '>L4sLH4sH', header)
  if atom_size != 20 or atom_type != 'pnot' or version != 0:
    raise ValueError('pnot signature not found.')
  if preview_type != 'PICT':
    raise ValueError('Bad pnot preview type: %r' % preview_type)
  if preview_index != 1:
    raise ValueError('Bad pnot preview index: %r' % preview_index)
  info['format'] = 'pnot'
  header = fread(8)
  if len(header) < 8:
    raise ValueError('Too short for pnot preview.')
  atom_size, atom_type = struct.unpack('>L4s', header)
  if atom_size < 8:
    raise ValueError('pnot preview atom size too small.')
  if atom_type != preview_type:
    raise ValueError('Bad pnot preview type (expecting %r): %r' % (preview_type, atom_type))
  if not fskip(atom_size - 8):
    raise ValueError('EOF in pnot preview data.')
  analyze_mov(fread, info, fskip)


# --- swf.


def get_bitstream(
    data,
    _hextable='0123456789abcdef',
    _hex_to_bits='0000 0001 0010 0011 0100 0101 0110 0111 1000 1001 1010 1011 1100 1101 1110 1111'.split()):
  if not isinstance(data, (str, buffer)):
    raise TypeError
  return iter(''.join(  # Convert to binary.
      _hex_to_bits[_hextable.find(c)]
      for c in data[:].encode('hex')))


def yield_bits_lsbfirst(fread):
  while 1:
    c = fread(1)
    if not c:
      break
    c = ord(c)
    for i in xrange(8):
      yield (c >> i) & 1


def yield_bits_msbfirst(fread):
  while 1:
    c = fread(1)
    if not c:
      break
    c = ord(c)
    for i in xrange(7, -1, -1):
      yield (c >> i) & 1


def analyze_swf(fread, info, fskip, format='swf', fclass='vector',
                spec=(0, ('FWS', 'CWS', 'ZWS'), 3, tuple(chr(c) for c in xrange(1, 40)))):
  # https://www.adobe.com/content/dam/acom/en/devnet/pdf/swf-file-format-spec.pdf
  header = fread(8)
  if len(header) < 8:
    raise ValueError('Too short for swf.')
  signature, version, file_size = struct.unpack('<3sBL', header)
  if not (signature in ('FWS', 'CWS', 'ZWS') and 1 <= version < 40):
    raise ValueError('swf signature not found.')
  info['format'] = 'swf'
  read_size = 17
  if signature == 'FWS':
    info['codec'] = codec = 'uncompressed'
  elif signature == 'CWS' and version >= 6:
    info['codec'] = codec = 'flate'
    read_size += 256  # Educated guess.
  elif signature == 'ZWS' and version >= 13:
    info['codec'] = codec = 'lzma'
    read_size += 256  # Educated guess.
  else:
    raise ValueError('Bad swf version %d for signature: %r' % (version, signature))
  if codec == 'flate':
    try:
      import zlib
    except ImportError:
      return
    try:
      data = zlib.decompressobj().decompress(fread(read_size))
    except zlib.error:
      raise ValueError('Bad swf flate stream.')
  elif codec == 'lzma':
    try:
      import lzma
    except ImportError:
      try:
        import liblzma as lzma
      except ImportError:
        return
    dc = lzma.LZMADecompressor()
    if len(fread(4)) != 4:
      raise ValueError('EOF in swf lzma compressed_size.')
    data = fread(5)
    if len(data) != 5:
      raise ValueError('EOF in swf lzma properties.')
    output = []
    try:
      # https://helpx.adobe.com/flash-player/kb/exception-thrown-you-decompress-lzma-compressed.html
      output.append(dc.decompress(data))
      output.append(dc.decompress('\xff\xff\xff\xff\xff\xff\xff\xff'))
      output.append(dc.decompress(fread(read_size)))
    except lzma.error:
      raise ValueError('Bad swf lzma stream.')
    data = ''.join(output)
    del dc, output  # Save memory.
  else:
    data = fread(read_size)

  bitstream = get_bitstream(buffer(data, 0, 17))
  def read_1():
    return int(bitstream.next() == '1')
  def read_n(n):
    r = 0
    for _ in xrange(n):
      r = r << 1 | (bitstream.next() == '1')
    return r
  try:
    nb = read_n(5)
    if not nb:
      raise ValueError('Bad swf FrameSize RECT bitcount.')
    xmin = read_n(nb)
    xmax = read_n(nb)
    ymin = read_n(nb)
    ymax = read_n(nb)
  except StopIteration:
    raise ValueError('EOF in swf FrameSize RECT.')
  if xmax < xmin:
    raise ValueError('Bad swf FrameSize x order.')
  if ymax < ymin:
    raise ValueError('Bad swf FrameSize y order.')
  info['width'], info['height'] =  (
      (xmax - xmin + 10) // 20, (ymax - ymin + 10) // 20)


# --- dv: DIF (digital interface format) DV (digital video).

def analyze_dv(fread, info, fskip, format='dv', fclass='media',
               spec=(0, '\x1f\7\0')):
  # IEC 61834 (paid)
  # https://github.com/FFmpeg/FFmpeg/blob/da5497a1a22d06d6979a888d2ded79521c428d29/libavcodec/dv_profile.c#L73-L292
  # https://github.com/FFmpeg/FFmpeg/blob/da5497a1a22d06d6979a888d2ded79521c428d29/libavformat/dv.c#L641
  # https://github.com/MediaArea/MediaInfoLib/blob/c567c176f5d145efeb5821b67467fba33d87354c/Source/MediaInfo/Multiple/File_DvDif.cpp
  header = fread(80)  # Block 0.
  if len(header) < 3:
    raise ValueError('Too short for dv.')
  if not header.startswith('\x1f\7\0'):
    raise ValueError('dv signature not found.')
  info['format'] = 'dv'
  width = height = None
  if len(header) == 80:
    for _ in xrange(5):
      data = fread(80)  # Next block.
      # Typical first 6 prefixes: ('\x1f\7\0', '\x3f\7\0', '\x3f\7\1', '\x5f\7\0', '\x5f\7\1', '\x5f\7\2').
      if len(data) < 80 or data.startswith('\x5f\7\2'):
        break
    stype = is_pal = None
    if len(data) == 80 and data.startswith('\x5f\7\2'):
      dsf = (ord(header[3]) & 0x80) >> 7
      if (ord(header[3]) & 0x7f) == 0x3f and data[51] == '\xff':
        # Created by QuickTime 3. https://trac.ffmpeg.org/ticket/217
        stype, is_pal = 0, dsf
      else:
        stype, is_pal = ord(data[51]) & 0x1f, (ord(data[51]) & 0x20) >> 5
        if dsf == is_pal and stype in (0, 1, 4, 0x14, 0x15, 0x18):
          pass
        else:
          dsf = stype = is_pal = None
    if stype is not None and is_pal is not None:
      if stype in (0, 1, 4):
        width, height = 720, (576, 480)[not is_pal]
      elif stype in (0x14, 0x15):
        width, height = (1440, 1280)[not is_pal], (1080, 1035)[stype != 0x14]
      elif stype == 0x18:
        width, height = 960, 720
  info['tracks'] = []
  if width and height:
    video_track_info = {'type': 'video', 'codec': 'dv', 'width': width, 'height': height}
    info['tracks'].append(video_track_info)
  # TODO(pts): Add info about the audio track.


# --- ogg.


def get_ogg_es_track_info(header):
  """Returns track info dict or None if unknown."""
  # The .startswith(...) checks below must be mutually exclusive, so that
  # the order of the `if's doesn't matter.

  # --- xiph.org free codecs:
  if header.startswith('\x01vorbis\0\0\0\0'):
    return get_track_info_from_analyze_func(header, analyze_vorbis)
  elif header.startswith('\x80theora'):
    return get_track_info_from_analyze_func(header, analyze_theora)
  elif header.startswith('\x80daala'):
    return get_track_info_from_analyze_func(header, analyze_daala)
  elif header.startswith('fLaC'):
    return get_track_info_from_analyze_func(header, analyze_flac)
  elif header.startswith('BBCD\0\0\0\0'):
    return get_track_info_from_analyze_func(header, analyze_dirac)
  elif header.startswith('PCM     \0\0\0'):
    return get_track_info_from_analyze_func(header, analyze_oggpcm)
  elif header.startswith('OpusHead'):
    return get_track_info_from_analyze_func(header, analyze_opus)
  elif header.startswith('Speex   1.'):
    return get_track_info_from_analyze_func(header, analyze_speex)
  # --- Other possible codecs:
  elif header.startswith('YUV4MPEG2 '):
    return get_track_info_from_analyze_func(header, analyze_yuv4mpeg2)
  elif (header.startswith('\0\0\1\xb3') or
        header.startswith('\0\0\1\xb5') or
        (header.startswith('\0\0\1\xb0') and header[5 : 9] == '\0\0\1\xb5')):
    return get_track_info_from_analyze_func(header, analyze_mpeg_video)
  elif header.startswith('\xff\xd8\xff'):
    track_info = {'type': 'video', 'codec': 'mjpeg'}
    track_info['width'], track_info['height'] = get_jpeg_dimensions(
        get_string_fread(header))
    return track_info
  elif header.startswith('\0\0\0\x0cjP  \r\n\x87\n\0\0\0'):
    return get_track_info_from_analyze_func(header, noformat_analyze_jp2)
  elif header.startswith('\xff\x4f\xff\x51\0'):
    return get_track_info_from_analyze_func(header, analyze_jpc)
  elif header.startswith('\xff\x0a'):
    return get_track_info_from_analyze_func(header, analyze_jpegxl)
  elif header.startswith('\x0a\x04B\xd2\xd5N'):
    return get_track_info_from_analyze_func(header, analyze_brunsli)
  elif header.startswith('WMPHOTO\0') or header.startswith('II\xbc\x01'):
    return get_track_info_from_analyze_func(header, analyze_jpegxr)
  elif header.startswith('\x89PNG\r\n\x1a\n\0\0\0'):
    return get_track_info_from_analyze_func(header, analyze_png)
  elif header.startswith('GIF87a') or header.startswith('GIF89a'):
    return get_track_info_from_analyze_func(header, analyze_gif)
  elif header.startswith('BM'):
    return get_track_info_from_analyze_func(header, analyze_bmp)
  elif (header.startswith('RIFF') and header[8 : 15] == 'WEBPVP8' and (header[15] or 'x') in ' LX'):
    return get_track_info_from_analyze_func(header, analyze_webp)
  elif header.startswith('MM\x00\x2a') or header.startswith('II\x2a\x00'):
    return get_track_info_from_analyze_func(header, analyze_tiff)
  elif header.startswith('\0\0\1\0'):  # Apparently this doesn't conflict with codecs below.
    return get_track_info_from_analyze_func(header, analyze_ico)
  elif header.startswith('\0\0\2\0'):
    return get_track_info_from_analyze_func(header, analyze_cur)
  elif header.startswith('#define'):
    return get_track_info_from_analyze_func(header, analyze_xbm)
  elif header.startswith('\0\0\0') and len(header) >= 12 and 8 <= ord(header[3]) <= 255 and header[4 : 12] == 'ftypmif1':  # This doesn't conflict with the codecs below.
    return get_track_info_from_analyze_func(header, analyze_mov)  # HEIF or AVIF.
  elif (header.startswith('\0\0\0\1\x09') or
        header.startswith('\0\0\0\1\x27') or
        header.startswith('\0\0\0\1\x47') or
        header.startswith('\0\0\0\1\x67') or
        header.startswith('\0\0\1\x09') or
        header.startswith('\0\0\1\x27') or
        header.startswith('\0\0\1\x47') or
        header.startswith('\0\0\1\x67')):
    return get_track_info_from_analyze_func(header, analyze_h264)
  elif (header.startswith('\0\0\0\1\x46\1') or
        header.startswith('\0\0\0\1\x40\1') or
        header.startswith('\0\0\0\1\x42\1') or
        header.startswith('\0\0\1\x46\1') or
        header.startswith('\0\0\1\x40\1') or
        header.startswith('\0\0\1\x42\1')):
    return get_track_info_from_analyze_func(header, analyze_h265)
  elif header.startswith('MAC '):
    return get_track_info_from_analyze_func(header, analyze_ape)
  elif header.startswith('\x0b\x77'):
    # TODO(pts): Use get_ac3_track_info here and etc. elsewhere for speed.
    return get_track_info_from_analyze_func(header, analyze_ac3)
  elif (header.startswith('\x1f\xff\xe8\x00') or
        header.startswith('\xff\x1f\x00\xe8') or
        header.startswith('\x7f\xfe\x80\x01') or
        header.startswith('\xfe\x7f\x01\x80')):
    return get_track_info_from_analyze_func(header, analyze_dts)
  elif (header.startswith('\xff\xe2') or
        header.startswith('\xff\xe3') or
        header.startswith('\xff\xf2') or
        header.startswith('\xff\xf3') or
        header.startswith('\xff\xf4') or
        header.startswith('\xff\xf5') or
        header.startswith('\xff\xf6') or
        header.startswith('\xff\xf7') or
        header.startswith('\xff\xfa') or
        header.startswith('\xff\xfb') or
        header.startswith('\xff\xfc') or
        header.startswith('\xff\xfd') or
        header.startswith('\xff\xfe') or
        header.startswith('\xff\xff') or
        header.startswith('\xff\xf0') or
        header.startswith('\xff\xf1') or
        header.startswith('\xff\xf8') or
        header.startswith('\xff\xf9')):  # Includes mp3 and aac.
    return get_track_info_from_analyze_func(header, analyze_mpeg_adts)
  elif header.startswith('.ra\xfd'):
    return get_realaudio_track_info(header)
  elif (header.startswith('VIDORV') or
        header.startswith('VIDOCLV1')):
    return get_realvideo_track_info(header)
  elif header.startswith('LSD:'):
    return get_ralf_track_info(header)
  elif (header.startswith('\x80\x49\x83\x42') or header.startswith('\x81\x49\x83\x42') or header.startswith('\x82\x49\x83\x42') or header.startswith('\x83\x49\x83\x42') or
        header.startswith('\xa0\x49\x83\x42') or header.startswith('\xa1\x49\x83\x42') or header.startswith('\xa2\x49\x83\x42') or header.startswith('\xa3\x49\x83\x42') or
        header.startswith('\x90\x49\x83\x42') or header.startswith('\x91\x49\x83\x42') or header.startswith('\x92\x49\x83\x42') or header.startswith('\x93\x49\x83\x42') or
        header.startswith('\xb0\x24\xc1\xa1') or header.startswith('\xb0\xa4\xc1\xa1') or header.startswith('\xb1\x24\xc1\xa1') or header.startswith('\xb1\xa4\xc1\xa1')):
    return get_vp9_track_info(header)
  elif header.startswith('\x12\0\x0a') and len(header) > 3 and 3 <= ord(header[3]) <= 127:
    return get_av1_track_info(header)
  else:
    # We can't detect vcodec=vp8 here, because its 3-byte prefix can be
    # anything.
    #
    # TODO(pts): Add detection of many other codecs with a known prefix.
    return None


def analyze_ogg(fread, info, fskip, format='ogg', fclass='media',
                spec=(0, 'OggS\0\2', 18, '\0\0\0\0', 26, '\1')):
  # https://xiph.org/ogg/
  # https://xiph.org/ogg/doc/oggstream.html
  # https://en.wikipedia.org/wiki/Ogg#File_format
  packets = {}
  page_sequences = {}
  while 1:
    header = fread(27)  # Read ogg page header.
    if len(header) < 27:
      if packets and not header:
        break
      raise ValueError('Too short for ogg.')
    signature, version, flag, granule_position, stream_id, page_sequence, checksum, segment_count = struct.unpack(
        '<4sBBQLLlB', header)
    info['format'] = 'ogg'
    if signature != 'OggS':
      raise ValueError('ogg signature not found.')
    if version:
      raise ValueError('Bad ogg version: %d' % version)
    #print (flag, granule_position, stream_id, page_sequence, segment_count)
    if flag != 2:
      if not (packets and 0 <= flag <= 7):
        raise ValueError('Bad flag: 0x%02x' % flag)
    if page_sequence != page_sequences.get(stream_id, 0):
      raise ValueError('Bad page_sequence, expecting %d: %d' %
                       (page_sequences.get(stream_id, 0), page_sequence))
    if flag != 2:  # End of stream headers.
      break
    if segment_count != 1:
      raise ValueError('Bad segment_count: %d' % segment_count)
    if stream_id in packets:
      raise ValueError('Multiple ogg first page.')
    header = fread(1)
    if not header:
      raise ValueError('EOF in ogg segment_table.')
    packet_size = ord(header)
    if not 1 <= packet_size <= 254:
      raise ValueError('Bad packet_size: %d' % packet_size)
    data = fread(packet_size)
    if len(data) < packet_size:
      raise ValueError('EOF in ogg packet.')
    packets[stream_id] = data
    page_sequences[stream_id] = 1 + page_sequences.get(stream_id, 0)
  info['tracks'] = []
  for _, header in sorted(packets.iteritems()):
    # It seems that all the elementary stream headers are in the beginning of
    # the ogg file, with flag == 2.
    track_info = get_ogg_es_track_info(header)
    if track_info is not None:
      info['tracks'].append(track_info)


def is_mime_type(data):
  i, size = 1, len(data)
  if size == 0 or not data[0].isalpha():
    return False
  while i < size and (data[i].isalnum() or data[i] == '-'):
    i += 1
  if i + 1 >= size or data[i] != '/' or not data[i - 1].isalnum() or not data[i + 1].isalpha():
    return False
  i += 2
  while i < size and (data[i].isalnum() or data[i] == '-'):
    i += 1
  if i != size or not data[i - 1].isalnum():
    return False
  return True


def analyze_realmedia(fread, info, fskip, format='realmedia', fclass='media',
                      spec=(0, '.RMF\0\0\0', 8, lambda header: (len(header) >= 8 and ord(header[7]) >= 8, 2))):
  # https://wiki.multimedia.cx/index.php/RealMedia
  # https://github.com/MediaArea/MediaInfoLib/blob/4c8a5a6ef8070b3635003eade494dcb8c74e946f/Source/MediaInfo/Multiple/File_Rm.cpp
  # http://samples.mplayerhq.hu/real/
  data = fread(8)
  if len(data) < 8:
    raise ValueError('Too short for realmedia.')
  signature, chunk_size = struct.unpack('>4sL', data)
  if signature != '.RMF':
    raise ValueError('realmedia signature not found.')
  if not 8 <= chunk_size <= 255:
    raise ValueError('Bad realmedia rmf chunk size: %d' % chunk_size)
  if not fskip(chunk_size - 8):
    raise ValueError('EOF in realmedia rmf header.')
  info['format'], info['tracks'] = 'realmedia', []
  while 1:
    data = fread(8)
    if not data:
      break
    if len(data) < 8:
      raise ValueError('EOF in realmedia chunk header')
    chunk_type, chunk_size = struct.unpack('>4sL', data)
    if chunk_type in ('RMMD', 'RJMD', 'RMJE') or chunk_type.startswith('TAG'):
      # https://github.com/MediaArea/MediaInfoLib/blob/4c8a5a6ef8070b3635003eade494dcb8c74e946f/Source/MediaInfo/Multiple/File_Rm.cpp#L111
      # These don't seem to be present in sample files.
      raise ValueError('Irregular realmedia chunk %r size.' % chunk_type)
    if chunk_size < 8:
      raise ValueError('Bad realmedia chunk %r size: %d' % (chunk_type, chunk_size))
    # * signature == '.RMF' contains file version info.
    # * chunk_type == 'CONT' contains title and performer.
    # * chunk_type == 'DATA' contains all audio and video data in packets.
    # * chunk_type == 'INDX' contains (timestamp, file_offset) pairs, for
    #    seeking.
    # * chunk_type == 'MDPR' contains media properties (including codec, video
    #   height, audio sampling rate), one MDPR per track.
    if chunk_type in ('DATA', 'INDX'):
      break
    if chunk_type != 'MDPR':
      if not fskip(chunk_size - 8):
        raise ValueError('EOF in realmedia chunk %r.' % chunk_type)
      continue
    if chunk_size > 8192:
      raise ValueError('realmedia chunk %r too long.' % chunk_type)
    data = fread(chunk_size - 8)
    if len(data) != chunk_size - 8:
      raise ValueError('EOF in realmedia chunk %r.' % chunk_type)
    #print (chunk_type, data)
    i = 32
    if i >= len(data):
      raise ValueError('realmedia mdpr too short for stream_name_size.')
    if not data.startswith('\0\0'):
      raise ValueError('Bad realmedia mdpr chunk_version.')
    stream_name_size = ord(data[i])
    i += 1
    if i + stream_name_size > len(data):
      raise ValueError('realmedia mdpr too short for stream_name.')
    stream_name = data[i : i + stream_name_size]
    i += stream_name_size
    if i >= len(data):
      raise ValueError('realmedia mdpr too short for mime_type_size.')
    mime_type_size = ord(data[i])
    i += 1
    if i + mime_type_size > len(data):
      raise ValueError('realmedia mdpr too short for mime_type.')
    mime_type = data[i : i + mime_type_size]
    i += mime_type_size
    if i + 4 > len(data):
      raise ValueError('realmedia mdpr too short for codec_data_size.')
    codec_data_size, = struct.unpack('>L', buffer(data, i, 4))
    i += 4
    if i + codec_data_size > len(data):
      raise ValueError('realmedia mdpr too short for codec_data.')
    if i + codec_data_size < len(data):
      raise ValueError('Extra data after realmedia mdpr codec_data.')
    if mime_type == 'logical-fileinfo':
      pass  # With invalid mime type (not is_mime_type(mime_type)).
    elif mime_type == 'logical-audio/x-pn-multirate-realaudio':
      # Multiple audio streams.
      info['tracks'].append({'type': 'audio', 'codec': 'multirate-realaudio'})
    elif mime_type in ('audio/x-pn-realaudio',
                       'audio/x-pn-multirate-realaudio',
                       'audio/x-pn-realaudio-encrypted'):
      info['tracks'].append(get_realaudio_track_info(buffer(data, i)))
    elif mime_type == 'logical-video/x-pn-multirate-realvideo':
      # Multiple video streams.
      info['tracks'].append({'type': 'audio', 'codec': 'multirate-realvideo'})
    elif mime_type in ('video/x-pn-realvideo',
                       'video/x-pn-multirate-realvideo',
                       'video/x-pn-realvideo-encrypted'):
      if i + 4 > len(data):
        raise ValueError('realmedia mdpr too short for codec_data_size2.')
      codec_data_size2, = struct.unpack('>L', buffer(data, i, 4))
      i += 4
      if codec_data_size != codec_data_size:
        raise ValueError('Bad realmedia mdpr codec_data_size2.')
      codec_data_size -= 4
      info['tracks'].append(get_realvideo_track_info(buffer(data, i)))
    elif mime_type == 'audio/X-MP3-draft-00':
      # codec_data was empty.
      # TODO(pts): Extract first few audio frames from chunk_type == 'DATA'
      # in MP3 ADU frame format (https://tools.ietf.org/html/rfc3119).
      info['tracks'].append({'type': 'audio', 'codec': 'mp3'})
    elif mime_type in ('audio/x-ralf-mpeg4',
                       'audio/x-ralf-mpeg4-generic'):
      info['tracks'].append(get_ralf_track_info(buffer(data, i)))
    else:
      if not is_mime_type(mime_type):
        raise ValueError('Bad realmedia mdpr mime_type: %r' % mime_type)
      # Other mime-type found: application/x-pn-imagemap
      # Other mime-type found: logical-application/x-pn-multirate-imagemap
      # Other mime-type found: application/x-pn-multirate-imagemap


def analyze_ivf(fread, info, fskip, format='ivf', fclass='media',
                spec=(0, 'DKIF\0\0 \0')):
  # https://wiki.multimedia.cx/index.php/IVF
  # https://formats.kaitai.io/vp8_ivf/
  # samples: https://gitlab.com/mbunkus/mkvtoolnix/issues/2553
  data = fread(8)
  if len(data) < 8:
    raise ValueError('Too short for ivf.')
  if data != 'DKIF\0\0 \0':
    raise ValueError('ivf signature not found.')
  info['format'], info['tracks'] = 'ivf', []
  data = fread(8)
  if len(data) == 8:
    codec, width, height = struct.unpack('<4sHH', data)
    info['tracks'].append({'type': 'video', 'codec': get_windows_video_codec(codec), 'width': width, 'height': height})


def analyze_amv(fread, info, fskip, format='amv', fclass='media',
                spec=(0, 'RIFF', 8, 'AMV LIST', 20, 'hdrlamvh\x38\0\0\0')):
  # http://fileformats.archiveteam.org/wiki/MTV_Video_(.AMV)
  # https://wiki.multimedia.cx/index.php/AMV
  # http://svn.rot13.org/cgi-bin/viewvc.cgi/amv/amv.pl?view=markup
  # Samples: https://samples.ffmpeg.org/amv/
  header = fread(72)
  if len(header) < 32:
    raise ValueError('Too short for amv.')
  if not (header.startswith('RIFF') and header[8 : 16] == 'AMV LIST' and header[20 : 32] == 'hdrlamvh\x38\0\0\0'):
    raise ValueError('amv signature not found.')
  info['format'], info['tracks'] = 'amv', []
  if len(header) >= 72:
    width, height = struct.unpack('<LL', header[64 : 72])
    info['tracks'].append({'type': 'video', 'codec': 'mjpeg', 'width': width, 'height': height})  # Modified MJPEG codec.
    info['tracks'].append({'type': 'audio', 'codec': 'adpcm'})  # Modified ADPCM codec.


X4XM_AUDIO_CODECS = {
    0: 'pcm',
    1: 'adpcm',  # Modified.
    2: 'adpcm2',  # Modified.
}


def analyze_4xm(fread, info, fskip, format='4xm', fclass='media',
                spec=(0, 'RIFF', 8, '4XMVLIST', 20, 'HEADLIST', 32, 'HNFO')):
  # https://wiki.multimedia.cx/index.php/4xm_Format
  # Samples: http://samples.mplayerhq.hu/game-formats/4xm/
  data = fread(36)
  if len(data) < 36:
    raise ValueError('Too short for 4xm.')
  if not (data.startswith('RIFF') and data[8 : 16] == '4XMVLIST' and data[20 : 28] == 'HEADLIST' and data[32 : 36] == 'HNFO'):
    raise ValueError('4xm signature not found.')
  info['format'], info['tracks'] = '4xm', []
  head_size, hnfo_size = struct.unpack('<L8xL', data[16 : 32])
  if hnfo_size < 4:
    raise ValueError('4xm hnfo_size too small.')
  if head_size < hnfo_size + 12:
    raise ValueError('4xm hnfo_size too large, exceeds head_size.')
  size = hnfo_size - 4 + (hnfo_size & 1)
  if fskip(size):
    def parse_list_items(items_size, list_id):
      while items_size >= 8:
        data = fread(8)
        if len(data) < 8:
          raise ValueError('EOF in 4xm list item size.')
        chunk_id, chunk_size = struct.unpack('<4sL', data)
        items_size -= chunk_size + 8
        if items_size < 0:
          raise ValueError('4xm list chunk too small.')
        #print (list_id, chunk_id, chunk_size)
        chunk_delta = (chunk_size & 1)
        item_id = None
        if list_id in ('HEAD', 'TRK_') and chunk_id == 'LIST':
          item_id = fread(4)
          if len(item_id) < 4:
            raise ValueError('EOF in 4xm sublist item ID.')
          #print (list_id, chunk_id, item_id, chunk_size)
          chunk_size -= 4
          if ((list_id == 'HEAD' and item_id == 'TRK_') or
              (list_id == 'TRK_' and item_id in ('VTRK', 'STRK'))):
            if chunk_size < 4:
              raise ValueError('4xm list item %s too small.' % item_id)
            parse_list_items(chunk_size, item_id)
            chunk_size = 0
        elif ((list_id == 'VTRK' and chunk_id == 'vtrk') or
              (list_id == 'STRK' and chunk_id == 'strk')):
          if chunk_size > 1023:
            raise ValueError('Chunk %s too long: %d' % (chunk_id, chunk_size))
          data = fread(chunk_size)
          if len(data) < chunk_size:
            raise ValueError('EOF in 4xm chunk %s.' % chunk_id)
          chunk_size = 0
          if chunk_id == 'vtrk':
            if len(data) < 36:
              raise ValueError('4xm vtrk chunk too small.')
            width, height = struct.unpack('<LL', data[28 : 36])
            info['tracks'].append({'type': 'video', 'codec': '4xm', 'width': width, 'height': height})
          elif chunk_id == 'strk':
            if len(data) < 40:
              raise ValueError('4xm strk chunk too small.')
            codec, channel_count, sample_rate, sample_size = struct.unpack('<4xL20xLLL', data)
            codec = X4XM_AUDIO_CODECS.get(codec, str(codec))
            info['tracks'].append({'type': 'audio', 'codec': codec})
            set_channel_count(info['tracks'][-1], codec, channel_count)
            set_sample_rate(info['tracks'][-1], codec, sample_rate)
            set_sample_size(info['tracks'][-1], codec, sample_size)
        if not fskip(chunk_size + chunk_delta):
          if item_id:
            raise ValueError('EOF in 4xm list %s.' % item_id)
          else:
            raise ValueError('EOF in 4xm chunk %s.' % chunk_id)
      if items_size:
        raise ValueError('4xm list remainder too small: %d' % items_size)

    parse_list_items(head_size - size - 16, 'HEAD')


# --- Windows

# Only BMP (DIB) image codecs. Also used in AVI etc. for keyframe-only video codecs.
# See also WINDOWS_VIDEO_CODECS for more video codecs.
DIB_CODECS = {
    0: 'uncompressed',
    1: 'rle',
    2: 'rle',
    3: 'bitfields',
    4: 'jpeg',
    5: 'flate',  # PNG.
    6: 'bitfields',
    11: 'uncompressed',
    12: 'rle',
    13: 'rle',
}


def parse_dib_header(info, data):
  # BITMAPINFOHEADER struct in data.
  # https://docs.microsoft.com/en-us/windows/win32/api/wingdi/ns-wingdi-bitmapinfoheader
  if not isinstance(data, (str, buffer)):
    raise TypeError
  if len(data) < 8:
    raise ValueError('Too short for dib.')
  bi_size, = struct.unpack('<L', data[:4])
  #if bi_size not in (12, 40, 64, 108, 124):  # From Pillow-8.4.0.
  if 12 <= bi_size < 40:
    # BITMAPCOREHEADER struct: bc_size, bc_width, bc_height, bc_planes, bc_bitcnt = struct.unpack('<LHHHH')
    info['width'], info['height'] = struct.unpack('<HH', data[4 : 8])
    info['codec'] = 'uncompressed'
  elif 40 <= bi_size <= 127:
    if len(data) >= 12:
      info['width'], info['height'] = struct.unpack('<LL', data[4 : 12])
      if len(data) >= 20:
        bi_compression, = struct.unpack('<L', data[16 : 20])
        info['codec'] = DIB_CODECS.get(bi_compression, str(bi_compression))
  else:
    raise ValueError('Bad dib bi_size: %d' % bi_size)


# FourCC.
# See some on: http://www.fourcc.org/
# See many on: https://github.com/MediaArea/MediaInfoLib/blob/master/Source/Resource/Text/DataBase/CodecID_Video_Riff.csv
# See all on: https://github.com/MediaArea/MediaInfoLib/blob/9c77babfa699347c4ca4a79650cc1f3ce6fcd6c8/Source/Resource/Text/DataBase/CodecID_Video_Riff.csv
# All keys are converted to lowercase, and whitespace-trimmed.
# TODO(pts): Merge this with MP4_VIDEO_CODECS?
# TODO(pts): Fill this.
WINDOWS_VIDEO_CODECS = {
    'avc1': 'h264',
    'dx50': 'divx5',
    'fmp4': 'divx5',
    'mpg4': 'divx5',
    'mp42': 'divx5',  # Isn't compatible with mpg4.
    'divx': 'divx',
    'div3': 'divx',
    'div4': 'divx',
    'dvx4': 'divx',
    '3iv2': 'divx',
    'h264': 'h264',
    'x264': 'h264',
    'xvid': 'divx',
    'mjpg': 'mjpeg',
    'msvc': 'msvc',
    'cram': 'msvc',
    'h265': 'h265',
    'x265': 'h265',
    'iv50': 'indeo5',
    'iv41': 'indeo4',
    'dvsd': 'dv',
    'dvsl': 'dv',
    'dvhd': 'dv',
    'mpeg': 'mpeg',
    'wmv3': 'wmv3',
    'vp30': 'vp3',
    'vp40': 'vp4',
    'vp50': 'vp5',
    'vp60': 'vp6',
    'vp6f': 'vp6',
    'vp70': 'vp7',
    'vp80': 'vp8',
    'vp90': 'vp9',
    'iv31': 'indeo3',
    'iv32': 'indeo3',
    'vcr2': 'vcr2',
    'av01': 'av1',
    'flv1': 'flv1',  # Flash Player 6, modified H.263, Sorenson Spark.
    'wvc1': 'vc1',
    # TODO(pts): Add these.
    # 13 ffds: Not a specific codec, but anything ffdshow (ffmpeg) supports.
    #  7 uldx
    #  6 pim1
    #  4 divf
    #  2 1cva
}


def get_windows_video_codec(codec):
  bi_compression, = struct.unpack('<L', codec)
  if bi_compression <= 31:  # Just a random limit.
    return DIB_CODECS.get(bi_compression, str(bi_compression))
  if bi_compression in (0x10000001, 0x10000002):
    return 'mpeg'
  codec = codec.strip().lower()  # Canonicalize FourCC.
  if '\0' in codec:
    raise ValueError('NUL in Windows video codec %r.' % codec)
  return WINDOWS_VIDEO_CODECS.get(codec, codec)


# http://www.onicos.com/staff/iz/formats/wav.html
# See many on: https://github.com/MediaArea/MediaInfoLib/blob/master/Source/Resource/Text/DataBase/CodecID_Audio_Riff.csv
# See many on: https://github.com/MediaArea/MediaInfoLib/blob/9c77babfa699347c4ca4a79650cc1f3ce6fcd6c8/Source/Resource/Text/DataBase/CodecID_Audio_Riff.csv
# TODO(pts): Find more.
WINDOWS_AUDIO_FORMATS = {
    0x0001: 'pcm',
    0x0002: 'adpcm',
    0x0003: 'pcm',  #  'ieee_float',
    0x0006: 'alaw',
    0x0007: 'mulaw',
    0x0009: 'dts',
    0x0009: 'drm',
    0x000a: 'wma',
    0x0010: 'adpcm',
    0x0011: 'adpcm',
    0x0012: 'adpcm',
    0x0013: 'adpcm',
    0x0017: 'adpcm',
    0x0018: 'adpcm',
    0x0020: 'adpcm',
    0x0028: 'lrc',
    0x0030: 'ac2',
    0x0036: 'adpcm',
    0x003b: 'adpcm',
    0x0050: 'mp2',  # MPEG-1 or MPEG-2.
    0x0055: 'mp3',
    0x0064: 'adpcm',
    0x0065: 'adpcm',
    0x0075: 'rt29',  # Voxware MetaSound.
    0x0092: 'ac3',  # 'dolby_ac3_spdif'.
    0x00ff: 'aac',  # 'raw_aac1',
    0x0160: 'wmav1',
    0x0161: 'wmav2',
    0x0162: 'wma-pro',
    0x0163: 'wma-lossless',
    0x0164: 'wma-spdif',
    0x0200: 'adpcm',
    0x0240: 'raw_sport',
    0x0241: 'esst_ac3',
    0x1600: 'aac',  # mpeg_adts_aac',
    0x1602: 'mpeg_loas',
    0x1610: 'mpeg_heaac',
    0x2000: 'dvm',
    0x2001: 'dts2',
    0xfffe: 'extensible-?',
}


def guid(s):
  """Encodes hex and shuffles bytes around."""
  s = s.replace('-', '').decode('hex')
  args = struct.unpack('<LHH8s', s)
  return struct.pack('>LHH8s', *args)


# See some near the end of: https://github.com/MediaArea/MediaInfoLib/blob/master/Source/Resource/Text/DataBase/CodecID_Audio_Riff.csv
# See many with prefix KSDATAFORMAT_SUBTYPE_ in: https://github.com/tpn/winsdk-10/blob/38ad81285f0adf5f390e5465967302dd84913ed2/Include/10.0.10240.0/shared/ksmedia.h
WINDOWS_GUID_AUDIO_FORMATS = {
    guid('00000003-0cea-0010-8000-00aa00389b71'): 'mp1',
    guid('00000004-0cea-0010-8000-00aa00389b71'): 'mp2',
    guid('00000005-0cea-0010-8000-00aa00389b71'): 'mp3',
    guid('00000006-0cea-0010-8000-00aa00389b71'): 'aac',
    guid('00000008-0cea-0010-8000-00aa00389b71'): 'atrac',
    guid('00000009-0cea-0010-8000-00aa00389b71'): '1bit',
    guid('0000000a-0cea-0010-8000-00aa00389b71'): 'dolby-digitalplus',
    guid('0000000b-0cea-0010-8000-00aa00389b71'): 'dts-hd',
    guid('0000000c-0cea-0010-8000-00aa00389b71'): 'dolby-mlp',
    guid('0000000d-0cea-0010-8000-00aa00389b71'): 'dst',
    guid('36523b22-8ee5-11d1-8ca3-0060b057664a'): 'mp1',
    guid('36523b24-8ee5-11d1-8ca3-0060b057664a'): 'mp2',
    guid('36523b25-8ee5-11d1-8ca3-0060b057664a'): 'ac3',
    guid('518590a2-a184-11d0-8522-00c04fd9baf3'): 'dsound',
    guid('58cb7144-23e9-bfaa-a119-fffa01e4ce62'): 'atrac3',
    guid('6dba3190-67bd-11cf-a0f7-0020afd156e4'): 'analog',
    guid('ad98d184-aac3-11d0-a41c-00a0c9223196'): 'vc',
    guid('a0af4f82-e163-11d0-bad9-00609744111a'): 'dss',
    guid('e06d802b-db46-11cf-b4d1-00805f6cbbea'): 'mp2',
    guid('e06d802c-db46-11cf-b4d1-00805f6cbbea'): 'ac3',
    guid('e06d8032-db46-11cf-b4d1-00805f6cbbea'): 'pcm',
    guid('e06d8033-db46-11cf-b4d1-00805f6cbbea'): 'dts',
    guid('e06d8034-db46-11cf-b4d1-00805f6cbbea'): 'sdds',
}


# --- avi


def analyze_avi(fread, info, fskip, format='avi', fclass='media',
                spec=(0, 'RIFF', 8, 'AVI ')):
  # Documented here: https://msdn.microsoft.com/en-us/library/ms779636.aspx
  #
  # OpenDML (ODML, for >2GB AVI) documented here:
  # http://www.jmcgowan.com/odmlff2.pdf
  #
  # We don't care about OpenDML, because the 'hdrl' (track info) is near the
  # beginning of the file, which is a regular AVI.
  #
  # In addition to the chunks we use here:
  #
  # * hdrl contains non-LIST avih.
  # * strh may contain non-LIST indx and vprp.
  # * RIFF may contain LIST info, which may contain non-LIST ISFT.
  #

  in_strl_chunks = {}
  info['tracks'] = []
  do_stop_ary = []

  def process_list(ofs_limit, parent_id):
    if parent_id == 'RIFF':
      what = 'top-level'
    else:
      what = 'in-%s' % parent_id
    list_idx = -1
    while ofs_limit is None or ofs_limit > 0 and not do_stop_ary:
      list_idx += 1
      if ofs_limit is not None and ofs_limit < 8:
        raise ValueError('No room for avi %s chunk.' % what)
      data = fread(8)
      if len(data) < 8:
        if not data and not list_idx and parent_id == 'RIFF':
          break
        raise ValueError('EOF in avi %s chunk header.' % what)
      chunk_id, size = struct.unpack('<4sL', data)
      size += size & 1
      if ofs_limit is not None:
        ofs_limit -= 8 + size
      if (size >= 4 and (ofs_limit is None or ofs_limit + size >= 4) and
          chunk_id == 'LIST'):
        chunk_id = fread(4) + '+'
        if len(chunk_id) < 5:
          raise ValueError('EOF in avi %s LIST chunk ID.' % what)
        size -= 4
      # Some buggy .avi files have this within hdrl.
      if chunk_id == 'movi+':
        do_stop_ary.append('s')
        break
      if ofs_limit is not None and ofs_limit < 0:
        raise ValueError('avi %s chunk too long: id=%r' % (what, chunk_id))
      if chunk_id == 'hdrl+' and parent_id == 'RIFF':
        process_list(size, chunk_id[:4])
        break
      elif chunk_id == 'strl+' and parent_id == 'hdrl':
        in_strl_chunks.clear()
        process_list(size, chunk_id[:4])
        strh_data = in_strl_chunks.get('strh')
        strf_data = in_strl_chunks.get('strf')
        in_strl_chunks.clear()
        if strh_data is None:
          raise ValueError('Missing strh in strl.')
        if strf_data is None:
          raise ValueError('Missing strf in strl.')
        if len(strh_data) < ((1 + (strh_data[:4] == 'vids')) << 2):
          raise ValueError('avi strh chunk to short.')
        if strh_data[:4] == 'vids':
          if len(strf_data) < 20:
            raise ValueError('avi strf chunk to short for video track.')
          # strf_data contains BITMAPINFO, which starts with BITMAPINFOHEADER.
          # https://msdn.microsoft.com/en-us/library/windows/desktop/dd183376(v=vs.85).aspx
          tmp_info = {}
          parse_dib_header(tmp_info, strf_data)
          if strh_data[4 : 8] != '\0\0\0\0':
            video_codec = strf_data[16 : 20]
          else:
            video_codec = strh_data[4 : 8]
          video_codec = get_windows_video_codec(video_codec)
          track_info = {'type': 'video', 'codec': video_codec}
          set_video_dimens(track_info, tmp_info['width'], tmp_info['height'])
          info['tracks'].append(track_info)
        elif strh_data[:4] == 'auds':
          if len(strf_data) < 16:
            raise ValueError('avi strf chunk to short for audio track.')
          wave_format, = struct.unpack('<H', strf_data[:2])
          codec = None
          if wave_format == 0xfffe:  # WAVE_FORMAT_EXTENSIBLE
            # The structure is interpreted as a WAVEFORMATEXTENSIBLE structure.
            # It starts with WAVEFORMATEX afterwards.
            # https://msdn.microsoft.com/en-us/library/ms788113.aspx
            if len(strf_data) < 40:
              raise ValueError(
                  'avi strf chunk to short for extensible audio track.')
            guid_str = strf_data[24 : 24 + 16]
            if guid_str.endswith('\0\0\0\0\x10\0\x80\0\0\xaa\0\x38\x9b\x71'):
              wave_format, = struct.unpack('<H', guid_str[:2])
            elif guid_str in WINDOWS_GUID_AUDIO_FORMATS:
              codec = WINDOWS_GUID_AUDIO_FORMATS[guid_str]
            else:
              codec = 'guid-?-' + guid_str.encode('hex')  # Fallback.
          if codec is None:
            codec = WINDOWS_AUDIO_FORMATS.get(wave_format, '0x%x' % wave_format)
          # Everything else including WAVE_FORMAT_MPEG and
          # MPEGLAYER3WAVEFORMAT also start with WAVEFORMATEX.
          # sample_size is in bits.
          # WAVEFORMATEX: https://msdn.microsoft.com/en-us/library/ms788112.aspx
          channel_count, sample_rate, _, _,  sample_size = struct.unpack(
              '<HLLHH', strf_data[2 : 16])
          info['tracks'].append({
              'type': 'audio',
              'codec': codec,
              'channel_count': channel_count,
              'sample_rate': sample_rate,
              # With 'codec': 'mp3', sample_size is usually 0.
              'sample_size': sample_size or 16,
          })
      elif chunk_id in ('strh', 'strf') and parent_id == 'strl':
        if chunk_id in in_strl_chunks:
          raise ValueError('Duplicate %s chunk in avi %s chunk.' %
                           (chunk_id, parent_id))
        # Typically shorter than 100 bytes, but found 66000 bytes in the
        # wild.
        if size > 99999:
          raise ValueError(
              'Unreasonable size of avi %s chunk: id=%r size=%r' %
              (what, chunk_id, size))
        data = fread(size)
        if len(data) < size:
          raise ValueError('EOF in avi %s chunk: id=%r' % (what, chunk_id))
        in_strl_chunks[chunk_id] = data
      elif (parent_id == 'RIFF' and
            chunk_id in ('idx1', 'indx', 'movi+') or chunk_id.startswith('00')):
        raise ValueError(
            'Unexpected avi %s chunk id=%r before hdrl.' % (what, chunk_id))
      elif size >= (1 << (16 + 4 * (chunk_id == 'JUNK'))):
        # 'JUNK' can be everywhere. We skip it here and elsewhere.
        raise ValueError(
            'Unreasonable size of avi %s chunk: id=%r size=%r' %
            (what, chunk_id, size))
      else:
        if not fskip(size):
          raise ValueError('EOF in avi %s chunk: id=%r' % (what, chunk_id))
    else:  # No `break.'
      if parent_id == 'RIFF':
        raise ValueError('Missing avi hdrl chunk.')

  data = fread(12)
  if len(data) < 12:
    raise ValueError('Too short for avi.')
  riff_id, ofs_limit, avi_id = struct.unpack('<4sL4s', data)
  if riff_id != 'RIFF' or avi_id != 'AVI ':
    raise ValueError('avi signature not found.')
  info['format'] = 'avi'
  if ofs_limit == 0:
    ofs_limit = None
  else:
    ofs_limit -= 4  # len(avi_id).
  process_list(ofs_limit, 'RIFF')


# --- rmmp


def analyze_rmmp(fread, info, fskip, format='rmmp', fclass='media', ext='.mmm',
                 spec=(0, 'RIFF', 8, 'RMMPcftc', 20, '\0\0\0\0cftc', 32, '\0\0\0\0\x0c\0\0\0')):
  # http://fileformats.archiveteam.org/wiki/RIFF_Multimedia_Movie
  # https://www.aelius.com/njh/wavemetatools/doc/riffmci.pdf
  # Samples (in the .iso file): https://archive.org/download/Microsoft_Works_-_Gateway_2000_Edition_Microsoft_1991
  data = fread(40)
  if len(data) < 40:
    raise ValueError('Too short for rmmp.')
  if not (data.startswith('RIFF') and data[8 : 16] == 'RMMPcftc' and data[20 : 28] == '\0\0\0\0cftc' and data[32 : 40] == '\0\0\0\0\x0c\0\0\0'):
    raise ValueError('rmmp signature not found.')
  info['format'], info['tracks'] = 'rmmp', []
  # Find width and height of the first image (dip).
  cftc_size, cftc_size2 = struct.unpack('<L8xL', data[16: 32])
  if cftc_size != cftc_size2:
    raise ValueError('Mismatch in rmmp cftc size.')
  if cftc_size < 16:
    raise ValueError('Bad rmmp cftc size: %d' % cftc_size)
  min_ofs, dib_ofs, dib_chunk_size, dib_sequence_id = cftc_size + 20, None, None, None
  read_ofs = len(data)
  for i in xrange(16, cftc_size, 16):
    data = fread(16)
    read_ofs += len(data)
    if len(data) < 16:
      if i == 16 and not data:
        return
      raise ValueError('EOF in rmmp cftc.')
    if data == '\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0':
      break
    chunk_type, chunk_size, sequence_id, ofs = struct.unpack('<4sLLL', data)
    ct = chunk_type.rstrip(' ')
    if not ct.isalpha() and ct == ct.lower():
      raise ValueError('Bad rmmp chunk type: %r' % chunk_type)
    if ofs < min_ofs:
      raise ValueError('rmmp chunk %r ofs %s too small, expected >= %d' % (chunk_type, ofs, min_ofs))
    min_ofs = ofs + 12 + chunk_size
    # Sequence ID is not increasing, e.g. rmmp chunk 'clut' sequence_id 1119 too small, expected >= 1121.
    #print (chunk_type, chunk_size, ofs)
    if chunk_type == 'dib ' and not dib_ofs:
      dib_chunk_size, dib_sequence_id, dib_ofs = chunk_size, sequence_id, ofs
  if dib_ofs:
    assert dib_ofs >= read_ofs
    if not fskip(dib_ofs - read_ofs):
      raise ValueError('EOF when seeking to rmmp div.')
    data = fread(26)
    if len(data) < 26:
      raise ValueError('EOF in rmmp div.')
    chunk_type, chunk_size, sequence_id, padding, header_size, width, height = struct.unpack('<4sLLHLLL', data)
    if chunk_type != 'dib ':
      raise ValueError('Bad rmmp dib chunk type.')
    if chunk_size != dib_chunk_size:
      raise ValueError('Mismatch rmmp dib chunk size.')
    if chunk_size < 46:
      raise ValueError('rmmp dib chunk too small.')
    if sequence_id != dib_sequence_id:
      raise ValueError('Mismatch rmmp dib sequence_id.')
    if header_size < 40:  # See also analyze_bmp for the limit of 40.
      raise ValueError('rmmp dib header too small.')
    if padding and padding != 0xe500:
      raise ValueError('Bad rmmp dib padding: %r', data[12 : 14])
    # Some width and height values are unreasonable for set_video_dimens.
    track_info = {'type': 'video', 'width': width, 'height': height}
    if header_size != 64:
      data = fread(8)
      if len(data) >= 8:
        codec, = struct.unpack('<4xL', data[:8])
        track_info['codec'] = DIB_CODECS.get(codec, str(codec))
    info['tracks'].append(track_info)


def analyze_ani(fread, info, fskip, format='ani', fclass='media', ext='.ani',
                spec=(0, 'RIFF', 8, 'ACON', 12, ('LIST', 'anih', 'seq ', 'rate'))):
  # http://fileformats.archiveteam.org/wiki/Windows_Animated_Cursor
  # https://www.daubnet.com/en/file-format-ani
  # https://web.archive.org/web/20130530192915/http://oreilly.com/www/centers/gff/formats/micriff
  data = fread(16)
  if len(data) < 16:
    raise ValueError('Too short for ani.')
  if not (data.startswith('RIFF') and data[8 : 12] == 'ACON' and data[12 : 16] in ('LIST', 'anih', 'seq ', 'rate')):
    raise ValueError('ani signature not found.')
  info['format'], info['tracks'] = 'ani', []
  chunk_id, had_anih = data[12 : 16], False
  width = height = None
  while 1:
    size = fread(4)
    if len(size) < 4:
      break
    size0, = struct.unpack('<L', size)
    size = size0 + (size0 & 1)
    if chunk_id in ('rate', 'seq '):
      if not fskip(size):
        break
    elif chunk_id == 'LIST':
      if size < 4:
        raise ValueError('ani LIST too small.')
      list_id = fread(4)
      if len(list_id) < 4:
        break
      if list_id == 'fram':
        if not had_anih:
          raise ValueError('Missing ani anih.')
        data = fread(16)
        if len(data) < 16:
          break
        item_id, item_size, reserved, item_type, image_count, width, height = struct.unpack('<4sLHHHBB', data)
        if item_id != 'icon':
          raise ValueError('Bad ani fram item_id: %r' % item_id)
        if item_size < 10:
          raise ValueError('Bad ani fram item_size: %d' % item_size)
        if reserved:
          raise ValueError('Bad ani fram reserved: %d' % reserved)
        if item_type not in (1, 2):
          raise ValueError('Bad ani fram item_type: %d' % item_type)
        if image_count != 1:
          raise ValueError('Bad ani fram image_count: %d' % image_count)
        break
      if not fskip(size - 4):
        break
    elif chunk_id == 'anih':
      if had_anih:
        raise ValueError('Duplicate ani anih.')
      had_anih = True
      data = fread(36)
      if len(data) < 36:
        raise ValueError
      size2, frame_count, step_count, width, height, bit_count, plane_count, display_rate, flags = struct.unpack('<9L', data)
      if size != size2:
        raise ValueError('ani anih size mismatch.')
      if not flags & 1:
        break
    else:
      raise ValueError('Unknown ani chunk_id: %r' % chunk_id)
    chunk_id = fread(4)
    if len(chunk_id) < 4:
      break
  if width is not None and height is not None:
    info['tracks'].append({'type': 'video', 'codec': 'uncompressed', 'width': width, 'height': height})


# --- asf

ASF_Header_Object = guid('75b22630-668e-11cf-a6d9-00aa0062ce6c')
ASF_Stream_Properties_Object = guid('b7dc0791-a9b7-11cf-8ee6-00c00c205365')
ASF_Audio_Media = guid('f8699e40-5b4d-11cf-a8fd-00805f5c442b')
ASF_Video_Media = guid('bc19efc0-5b4d-11cf-a8fd-00805f5c442b')


def analyze_asf(fread, info, fskip, format='asf', extra_formats=('wmv', 'wma'), fclass='media',
                spec=(0, '0&\xb2u\x8ef\xcf\x11\xa6\xd9\0\xaa\x00b\xcel')):
  header = fread(30)
  if len(header) < 30:
    raise ValueError('Too short for asf.')
  guid, size, count, reserved12 = struct.unpack('<16sQLH', header)
  if guid != ASF_Header_Object:
    raise ValueError('asf signature not found.')
  if reserved12 != 0x201:
    raise ValueError('Unexpected asf reserved12 value: 0x%x' % reserved12)
  if size < 30:
    raise ValueError('Too short for asf with header object.')
  ofs_limit = size - 30
  if ofs_limit > 500000:  # Typical maximum size is 5500 bytes.
    raise ValueError('Unreasonable size of asf header object: %d' % ofs_limit)
  info['tracks'] = []
  info['format'] = 'asf'
  while ofs_limit > 0:
    if count <= 0:
      raise ValueError('Expected no more objects in asf header.')
    if ofs_limit < 24:
      raise ValueError('No room for asf in-header object header.')
    data = fread(24)
    if len(data) < 24:
      raise ValueError('EOF in asf in-header object header.')
    guid, size = struct.unpack('<16sQ', data)
    if size < 24:
      raise ValueError('asf in-header object too small.')
    ofs_limit -= size
    count -= 1
    if ofs_limit < 0:
      raise ValueError('No room for asf in-header object.')
    size -= 24
    if size > 350000:  # Typical maximum size is 4500 bytes.
      raise ValueError('Unreasonable size of asf in-header object: %d' % size)
    if guid == ASF_Stream_Properties_Object:
      data = fread(size)
      if len(data) < size:
        raise ValueError('EOF in asf stream properties.')
      (stream_type_guid, error_correction_type_guid, time_offset, ts_size,
       ec_size, flags, reserved) = struct.unpack('<16s16sQLLHL', data[:54])
      if 54 + ts_size > len(data):
        raise ValueError('No room for asf stream properties.')
      if stream_type_guid == ASF_Audio_Media:
        if len(data) < 70:
          raise ValueError('asf audio properties too short.')
        (wave_format, channel_count, sample_rate, _, _, sample_size,
        ) = struct.unpack('<HHLLHH', data[54 : 70])
        # TODO(pts): Try to make sense of GUID if codec == 'extensible-?'.
        info['tracks'].append({
            'type': 'audio',
            'codec': WINDOWS_AUDIO_FORMATS.get(
                wave_format, '0x%x' % wave_format),
            'channel_count': channel_count,
            'sample_rate': sample_rate,
            # With 'codec': 'mp3', sample_size is usually 0.
            'sample_size': sample_size or 16,
        })
      elif stream_type_guid == ASF_Video_Media:
        if len(data) < 85:
          raise ValueError('asf video properties too short.')
        (width, height, reserved, format_data_size, format_data_size2, width2,
         height2, reserved2, bits_per_pixel, video_codec,
        ) = struct.unpack('<LLBHLLLHH4s', data[54 : 85])
        if format_data_size != format_data_size2:
          raise ValueError('Mismatch in asf video format_data_size.')
        if format_data_size + 11 != ts_size:
          raise ValueError('Unexpected asf video format_data_size.')
        if width != width2 or height != height2:
          raise ValueError('Mismatch in asf video dimensions.')
        video_codec = get_windows_video_codec(video_codec)
        track_info = {'type': 'video', 'codec': video_codec}
        set_video_dimens(track_info, width, height)
        info['tracks'].append(track_info)
    elif not fskip(size):
      raise ValueError('EOF in asf in-header object.')
  # Not failing on this, some ASF files have it in the wild.
  #if count != 0:
  #  raise ValueError('Expected more objects in asf header.')
  # We ignore anything beyond the ASF_Header_Object.

  if [1 for track in info['tracks'] if track['type'] == 'video']:
    info['format'] = 'wmv'
  elif [1 for track in info['tracks'] if track['type'] == 'audio']:
    info['format'] = 'wma'
  else:
    info['format'] = 'asf'


# --- flac.


def analyze_flac(fread, info, fskip, header=''):
  if len(header) < 5:
    header += fread(5 - len(header))
  if len(header) < 5:
    raise ValueError('Too short for flac.')
  if not header.startswith('fLaC'):
    raise ValueError('flac signature not found.')
  info['format'] = 'flac'
  if header[4] not in '\0\x80':
    raise ValueError('STREAMINFO metadata block expected in flac.')
  size = fread(3)
  if len(size) != 3:
    raise ValueError('EOF in flac STREAMINFO metadata block size.')
  size, = struct.unpack('>L', '\0' + size)
  if not 34 <= size <= 255:
    raise ValueError(
        'Unreasonable size of flac STREAMINFO metadata block: %d' % size)
  data = fread(18)
  if len(data) != 18:
    raise ValueError('EOF in flac STREAMINFO metadata block.')
  # https://xiph.org/flac/format.html#metadata_block_streaminfo
  i, = struct.unpack('>Q', data[10 : 18])
  info['tracks'] = []
  info['tracks'].append({
      'type': 'audio',
      'codec': 'flac',
      'channel_count': int((i >> 41) & 7) + 1,
      'sample_size': int((i >> 36) & 31) + 1,
      'sample_rate': int(i >> 44),
  })


# --- ape.


def analyze_ape(fread, info, fskip, header=''):
  # Monkey's Audio.
  # http://fileformats.archiveteam.org/wiki/Monkey%27s_Audio
  # Can be reverse engineered from the source code: https://monkeysaudio.com/developers.html
  if len(header) < 10:
    header += fread(10 - len(header))
  if len(header) < 5:
    raise ValueError('Too short for ape.')
  if not header.startswith('MAC '):
    raise ValueError('ape signature not found.')
  info['format'] = 'ape'
  version, = struct.unpack('<H', header[4 : 6])
  info['tracks'] = [{'type': 'audio', 'codec': 'ape', 'sample_size': 16}]
  if version > 0xf8b:
    header_size, = struct.unpack('<H', header[8 : 10])
    if header_size < 10:
      raise ValueError('ape header too short.')
    assert header_size >= len(header), 'Supplied ape header too long.'
    if not fskip(header_size - len(header)):
      raise ValueError('EOF in ape header.')
    data = fread(22)
    if len(data) < 22:
      raise ValueError('EOF in ape parameters.')
    data = buffer(data, 18, 4)
  else:
    if len(header) < 14:
      header += fread(14 - len(header))
    data = buffer(data, 10, 4)
  info['tracks'][-1]['channel_count'], info['tracks'][-1]['sample_rate'] = struct.unpack('<HH', data)


# --- vorbis.


def analyze_vorbis(fread, info, fskip):
  # https://xiph.org/vorbis/doc/Vorbis_I_spec.html
  header = fread(16)
  if len(header) < 16:
    raise ValueError('Too short for vorbis.')
  signature, version, channel_count, sample_rate = struct.unpack(
      '<7sLBL', header)
  if signature != '\x01vorbis':
    raise ValueError('vorbis signature not found.')
  if version:
    raise ValueError('Bad vorbis version: %d' % version)
  info['format'] = 'vorbis'
  info['tracks'] = [{'type': 'audio', 'codec': 'vorbis', 'sample_size': 16}]
  set_channel_count(info['tracks'][0], 'vorbis', channel_count)
  set_sample_rate(info['tracks'][0], 'vorbis', sample_rate)


# --- oggpcm.


def analyze_oggpcm(fread, info, fskip):
  # https://wiki.xiph.org/index.php?title=OggPCM&mobileaction=toggle_view_desktop
  header = fread(22)
  if len(header) < 22:
    raise ValueError('Too short for oggpcm.')
  signature, major_version, minor_version, pcm_format, sample_rate, bit_count, channel_count = struct.unpack(
      '>8sHHLLBB', header)
  if signature != 'PCM     ':
    raise ValueError('oggpcm signature not found.')
  if major_version:
    raise ValueError('Bad oggpcm major_version: %d' % major_version)
  if minor_version > 255:
    raise ValueError('Bad oggpcm minor_version: %d' % minor_version)
  info['format'] = 'oggpcm'
  info['tracks'] = [{'type': 'audio', 'codec': 'oggpcm'}]
  set_channel_count(info['tracks'][0], 'oggpcm', channel_count)
  set_sample_rate(info['tracks'][0], 'oggpcm', sample_rate)
  if pcm_format < 8:
    info['tracks'][0]['codec'], sample_size = 'pcm', ((pcm_format >> 1) + 1) << 3
  elif pcm_format == 0x10:
    info['tracks'][0]['codec'], sample_size = 'mulaw', 8
  elif pcm_format == 0x11:
    info['tracks'][0]['codec'], sample_size = 'alaw', 8
  elif 0x20 <= pcm_format < 0x24:
    info['tracks'][0]['codec'], sample_size, bit_count = 'float', ((pcm_format >> 1) - 0xf) << 5, 0
  else:  # Unknown.
    info['tracks'][0]['codec'], sample_size = 'unknown', bit_count
  if 0 < bit_count < sample_size:
    info['tracks'][0]['sample_size'] = bit_count
  else:
    info['tracks'][0]['sample_size'] = sample_size


# --- opus.


def analyze_opus(fread, info, fskip):
  # https://tools.ietf.org/html/rfc7845.html
  header = fread(16)
  if len(header) < 16:
    raise ValueError('Too short for opus.')
  signature, version, channel_count, pre_skip, sample_rate = struct.unpack(
      '<8sBBHL', header)
  if signature != 'OpusHead':
    raise ValueError('opus signature not found.')
  info['format'] = 'opus'
  if not 1 <= version <= 15:
    raise ValueError('Bad opus version: %d' % version)
  info['tracks'] = [{'type': 'audio', 'codec': 'opus', 'sample_size': 16}]
  set_channel_count(info['tracks'][0], 'opus', channel_count)
  set_sample_rate(info['tracks'][0], 'opus', sample_rate)


# --- speex.


def analyze_speex(fread, info, fskip):
  # Based on speex-1.2.0/include/speex/speex_header.h in
  # http://downloads.us.xiph.org/releases/speex/speex-1.2.0.tar.gz
  header = fread(52)
  if len(header) < 52:
    raise ValueError('Too short for speex.')
  signature, version_str, version, header_size, sample_rate, mode, mode_bitstream_version, channel_count = struct.unpack(
      '<8s20sLLLLLL', header)
  if signature != 'Speex   ':
    raise ValueError('speex signature not found.')
  info['format'] = 'speex'
  version_str = version_str.rstrip('\0')
  if not version_str.startswith('1.'):
    raise ValueError('Bad speex version_str: %r' % version_str)
  if version != 1:
    raise ValueError('Bad speex version: %d' % version)
  if not 80 <= header_size <= 255:  # 80 is found on the wire.
    raise ValueError('Bad speex header_size: %d' % header_size)
  if mode > 7:  # 0, 1 and 2 are found on the wire.
    raise ValueError('Bad speex mode: %d' % mode)
  if mode_bitstream_version > 255:  # 4 is found on the wire.
    raise ValueError('Bad speex mode_bitstream_version: %d' % mode_bitstream_version)
  info['tracks'] = [{'type': 'audio', 'codec': 'speex', 'sample_size': 16}]
  set_channel_count(info['tracks'][0], 'speex', channel_count)
  set_sample_rate(info['tracks'][0], 'speex', sample_rate)


# --- RealAudio ra.

REALAUDIO_CODECS = {
    'lpcJ': 'vslp-ra1',
    '14_4': 'vslp-ra1',
    '28_8': 'ld-celp-ra2',
    'dnet': 'ac3',
    'sipr': 'sipro',
    'cook': 'cook',
    'atrc': 'atrac3',
    'ralf': 'ralf',
    'raac': 'aac',
    'racp': 'aac-he',
}


def is_fourcc(data):
  return len(data) == 4 and not sum(not (c.isalnum() or c == '_') for c in data.rstrip(' '))


def get_realaudio_track_info(header):
  # https://github.com/MediaArea/MediaInfoLib/blob/4c8a5a6ef8070b3635003eade494dcb8c74e946f/Source/MediaInfo/Multiple/File_Rm.cpp#L450
  # http://samples.mplayerhq.hu/real/
  # https://wiki.multimedia.cx/index.php/RealMedia
  if len(header) < 6:
    raise ValueError('Too short for realaudio.')
  signature, version = struct.unpack('>4sH', buffer(header, 0, 6))
  if signature != '.ra\xfd':
    raise ValueError('realaudio signature not found.')
  if version not in (3, 4, 5):
    raise ValueError('Bad realaudio version: %d' % version)
  size = (0, 0, 0, 10, 66, 70)[version]
  if len(header) < size:
    raise ValueError('EOF in realaudio header.')
  audio_track_info = {'type': 'audio', 'subformat': 'ra%d' % version}
  # TODO(pts): Get the fourcc codec value.
  if version == 3:
    sample_rate, sample_size, fourcc = 8000, 16, 'lpcJ'
    channel_count, = struct.unpack('>H', buffer(header, 8, 2))
  else:
    sample_rate, sample_size, channel_count = struct.unpack(
        '>H2xHH', buffer(header, 48 + 6 * (version == 5), 8))
    fourcc = buffer(header, 62 + 4 * (version == 5), 4)[:]
  if not is_fourcc(fourcc):
    raise ValueError('Bad realaudio fourcc: %r' % fourcc)
  audio_track_info['codec'] = REALAUDIO_CODECS.get(fourcc, fourcc)
  set_channel_count(audio_track_info, 'realaudio', channel_count)
  set_sample_rate(audio_track_info, 'realaudio', sample_rate)
  set_sample_size(audio_track_info, 'realaudio', sample_size)
  return audio_track_info


def analyze_realaudio(fread, info, fskip):
  header = fread(6)
  if len(header) < 6:
    raise ValueError('Too short for realaudio.')
  signature, version = struct.unpack('>4sH', header)
  if signature != '.ra\xfd':
    raise ValueError('realaudio signature not found.')
  info['format'] = 'realaudio'
  size = (0, 0, 0, 4, 60, 64)[min(version, 5)]
  data = fread(size)
  if len(data) < size:
    raise ValueError('EOF in realaudio header.')
  header += data
  info['tracks'] = [get_realaudio_track_info(header)]


# --- RealAudio lossless ralf.


def get_ralf_track_info(header):
  if len(header) < 16:
    raise ValueError('Too short for ralf.')
  signature, version, version2, channel_count, sample_size, sample_rate = struct.unpack(
      '>4sBB2xHHL', buffer(header, 0, 16))
  if signature != 'LSD:':
    raise ValueError('ralf signature not found.')
  if version not in (1, 2, 3):
    raise ValueError('Bad ralf version: %d' % version)
  audio_track_info = {'type': 'audio', 'codec': 'ralf'}
  set_channel_count(audio_track_info, 'ralf', channel_count)
  set_sample_rate(audio_track_info, 'ralf', sample_rate)
  set_sample_size(audio_track_info, 'ralf', sample_size)
  return audio_track_info


def analyze_ralf(fread, info, fskip):
  # RealAudio lossless.
  # https://wiki.multimedia.cx/index.php/Real_Lossless_Codec
  header = fread(16)
  if len(header) < 16:
    raise ValueError('Too short for ralf.')
  if not header.startswith('LSD:'):
    raise ValueError('ralf signature not found.')
  info['format'] = 'ralf'
  info['tracks'] = [get_ralf_track_info(header)]


# --- Other audio.


def round_apple_float80(e, m, is_large_ok=True):
  """Returns the nearest integer."""
  # Also https://en.wikipedia.org/wiki/Extended_precision#x86_extended_precision_format
  f = e & 0x7fff
  if f in (0, 0x7fff):
    raise ValueError('Unsupported float80 special e.')
  m &= 0xffffffffffffffff
  if not m >> 63:
    raise ValueError('Unsupported float80 unnormal m.')
  s = (0x3fff + 63) - f
  if s > 0:
    m = (m + (1 << (s - 1))) >> s
  elif is_large_ok:
    m <<= -s
  else:
    raise ValueError('float80 value too large.')
  if e & 0x8000:
    m = -m
  return int(m)


def analyze_aiff(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/AIFF
  # http://www-mmsp.ece.mcgill.ca/Documents/AudioFormats/AIFF/Docs/AIFF-1.3.pdf
  header = fread(38)
  if len(header) < 20:
    raise ValueError('Too short for aiff.')
  if not (header.startswith('FORM') and
          header[8 : 20] == 'AIFFCOMM\0\0\0\x12'):
    raise ValueError('aiff signature not found.')
  info['format'] = 'aiff'
  info['tracks'] = [{'type': 'audio', 'codec': 'pcm'}]
  if len(header) >= 38:
    (channel_count, frame_count, sample_size, sample_rate2, sample_rate8,
    ) = struct.unpack('>HLHHQ', header[20 : 38])
    set_channel_count(info['tracks'][-1], 'aiff', channel_count)
    set_sample_rate(info['tracks'][-1], 'aiff',
                    round_apple_float80(sample_rate2, sample_rate8, False))
    if not 1 <= sample_size <= 32:
      raise ValueError('Bad aiff sample_size: %d' % sample_size)
    info['tracks'][-1]['sample_size'] = sample_size


def analyze_aifc(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/AIFC
  # http://www-mmsp.ece.mcgill.ca/Documents/AudioFormats/AIFF/Docs/AIFF-C.9.26.91.pdf
  # Samples: http://www-mmsp.ece.mcgill.ca/Documents/AudioFormats/AIFF/Samples.html
  header = fread(20)
  if len(header) < 19:
    raise ValueError('Too short for aifc.')
  if not (header.startswith('FORM') and header[8 : 12] == 'AIFC' and
          header[12 : 16] in ('FVER', 'COMM') and header[16 : 19] == '\0\0\0'):
    raise ValueError('aifc signature not found.')
  info['format'] = 'aifc'
  info['tracks'] = [{'type': 'audio'}]
  if len(header) < 20:
    return
  xtype, size = struct.unpack('>4sL', header[12 : 20])
  while 1:
    if xtype == 'COMM':  # Data is in the 'SSND' chunk.
      if not 23 <= size <= 255:
        raise ValueError('Bad aifc COMM chunk size: %d' % size)
      data = fread(22)
      if len(data) < 22:
        raise ValueError('EOF in aifc COMM chunk.')
      (channel_count, frame_count, sample_size, sample_rate2, sample_rate8,
       codec) = struct.unpack('>HLHHQ4s', data)
      codec = codec.strip().lower()
      info['tracks'][-1]['codec'] = MP4_AUDIO_CODECS.get(codec, codec)
      set_channel_count(info['tracks'][-1], 'aifc', channel_count)
      set_sample_rate(info['tracks'][-1], 'aifc',
                      round_apple_float80(sample_rate2, sample_rate8, False))
      if not 1 <= sample_size <= 32:
        raise ValueError('Bad aifc sample_size: %d' % sample_size)
      info['tracks'][-1]['sample_size'] = sample_size
      break
    elif not (xtype.strip().isalnum() and xtype == xtype.upper()):
      raise ValueError('Bad aifc chunk type: %r' % xtype)
    elif not fskip(size):
      raise ValueError('EOF in aifc %s chunk.' % xtype)
    data = fread(8)
    if not data:
      break
    if len(data) < 8:
      raise ValueError('EOF in aifc chunk header.')
    xtype, size = struct.unpack('>4sL', data)


AU_CODECS = {
    1: ('mulaw', 8),
    2: ('pcm', 8),
    3: ('pcm', 16),
    4: ('pcm', 24),
    5: ('pcm', 32),
    6: ('pcm', 32),  # Float.
    7: ('pcm', 64),  # Float.
    23: ('adpcm', 4),  # G.721.
    24: ('adpcm', 1),  # G.722. Bit count not specified.
    25: ('adpcm', 3),  # G.723.
    26: ('adpcm', 5),  # G.723.
    27: ('alaw', 8),
}


def analyze_au(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/AU
  # https://pubs.opengroup.org/external/auformat.html
  # Sample: http://file.fyicenter.com/14_Audio_.AU_File_Extension_for_Audio_Files.html
  header = fread(24)
  if len(header) < 24:
    raise ValueError('Too short for au.')
  if not header.startswith('.snd\0\0\0'):
    raise ValueError('au signature not found.')
  (header_size, data_size, encoding, sample_rate, channel_count,
  ) = struct.unpack('>5L', header[4 : 24])
  if not 24 <= header_size <= 255:
    raise ValueError('Bad au header_size: %d' % header_size)
  if encoding not in AU_CODECS:
    raise ValueError('Unknown au encoding: %d' % encoding)
  codec, sample_size = AU_CODECS[encoding]
  if not 1 <= channel_count <= 16:
    raise ValueError('Bad au channel_count: %d' % header_size)
  info['format'] = 'au'
  info['tracks'] = [{'type': 'audio', 'codec': codec, 'channel_count': channel_count, 'sample_size': sample_size}]
  set_sample_rate(info['tracks'][-1], 'au', sample_rate)


# --- H.264.


def has_bad_emulation_prevention(data):
  """Returns true iff \0\0\3 is followed by anything else than \0 or \1 or \2 ."""
  i = 0
  while 1:
    i = data.find('\0\0\3', i) + 3
    if i < 3 or i >= len(data):
      return False
    if data[i] not in '\0\1\2\3':
      return True


def count_is_h264(header):
  """Returns confidence (100 * size) or 0."""
  # Allowed prefix hex regexp: ((00)?00000109(10|30|50|70|90|b0|d0|f0))?(00)?000001(27|47|67)
  #
  # We check that forbidden_zero_bit is 0, nal_refc_idc is 0 for AUD and 1,
  # 2 or 3 for SPS and PPS NAL unit types.
  if has_bad_emulation_prevention(header):
    return False
  i = 4 * header.startswith('\0\0\1\x09') or 5 * header.startswith('\0\0\0\1\x09')
  if i:
    if i >= len(header) or header[i] not in '\x10\x30\x50\x70\x90\xb0\xd0\xf0':
      return False
    i += 1
  if header[i : i + 3] == '\0\0\0':
    i += 1
    if header[i : i + 3] == '\0\0\0':
      i += 1
  if header[i : i + 3] != '\0\0\1':
    return False
  i += 3
  if i >= len(header) or header[i] not in '\x27\x47\x67':
    return False
  i += 1
  if i >= len(header):
    return False
  return i * 100


def parse_h264_sps(data, expected_sps_id=0):
  """Parses a H.264 sequence parameter set (SPS) NAL unit data."""
  # Based on function read_seq_parameter_set_rbsp in
  # https://github.com/aizvorski/h264bitstream/blob/29489957c016c95b495f1cce6579e35040c8c8b0/h264_stream.c#L356
  # , except for the very first byte.
  #
  # The formula for width and height is based on:
  # https://stackoverflow.com/a/31986720
  #
  # TODO(pts): Estimate how many bytes are used (looks like data[:10], data[:22]).
  if len(data) < 4:
    raise ValueError('h264 avcc sps too short.')
  if len(data) > 4096:  # Typically just 22 bytes, also observed 101 bytes (with io['seq_scaling_matrix_present_flag'] == 1).
    raise ValueError('h264 avcc sps too long.')
  io = {}
  io['chroma_format'] = 1
  io['profile'] = ord(data[0])
  io['compatibility'] = ord(data[1])
  io['level'] = ord(data[2])
  io['residual_color_transform_flag'] = 0
  # TODO(pts): Maybe bit shifting is faster.
  data = get_bitstream(buffer(data, 3))
  def read_1():
    return int(data.next() == '1')
  def read_n(n):
    r = 0
    for _ in xrange(n):
      r = r << 1 | (data.next() == '1')
    return r
  def read_ue():  # Unsigned varint.
    r = n = 0
    while data.next() == '0' and n < 32:
      n += 1
    for _ in xrange(n):
      r = r << 1 | (data.next() == '1')
    return r + (1 << n) - 1
  def read_se():  # Signed varint.
    r = read_ue()
    if r & 1:
      return (r + 1) >> 1;
    else:
      return -(r >> 1)
  def read_scaling_list(size):  # Return value ingored.
    # Maximum number of bits read: size * 64.
    # Untested, based on h264_stream.c
    last_scale, next_scale = 8, 8
    for j in xrange(size):
      if next_scale:
        next_scale = (last_scale + read_se()) & 255
      if next_scale:
        last_scale = next_scale
  try:
    io['sps_id'] = read_ue()
    if expected_sps_id is not None and io['sps_id'] != expected_sps_id:
      raise ValueError('Unexpected flv h264 avcc sps id: expected=%d, got=%d' %
                       (expected_sps_id, io['sps_id']))
    if io['profile'] in (
        100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134):
      io['chroma_format'] = read_ue()
      if io['chroma_format'] == 3:
        io['residual_colour_transform_flag'] = read_1()
      io['bit_depth_luma_minus8'] = read_ue()
      io['bit_depth_chroma_minus8'] = read_ue()
      io['qpprime_y_zero_transform_bypass_flag'] = read_1()
      io['seq_scaling_matrix_present_flag'] = read_1()
      if io['seq_scaling_matrix_present_flag']:
        # Maximum number of bits read in the loop below:
        # 8 + (16 * 6 + 64 * 2) * 64 == 14344.
        for si in xrange(8):
          if read_1():
            read_scaling_list((64, 16)[si < 6])
    io['log2_max_frame_num'] = 4 + read_ue()
    io['pic_order_cnt_type'] = read_ue()
    if io['pic_order_cnt_type'] == 0:
      io['log2_max_pic_order_cnt'] = 4 + read_ue()
    elif io['pic_order_cnt_type'] == 1:
      io['log2_max_pic_order_cnt'] = 0
      io['delta_pic_order_always_zero_flag'] = read_1()
      io['offset_for_non_ref_pic'] = read_se()
      io['offset_for_top_to_bottom_field'] = read_se()
      for _ in read_ue():  # Practically unlimited number of bits.
        read_se()
    elif io['pic_order_cnt_type'] == 2:
      io['log2_max_pic_order_cnt'] = 0
    else:
      raise ValueError('Unknown h264 avcc sps pic_order_cnt_type: %d' %
                       io['pic_order_cnt_type'])
    io['num_ref_frames'] = read_ue()
    io['gaps_in_frame_num_value_allowed_flag'] = read_1()
    io['width_in_mbs'] = read_ue() + 1
    io['height_in_map_units'] = read_ue() + 1
    io['frame_mbs_only_flag'] = read_1()
    if not io['frame_mbs_only_flag']:
      io['mb_adaptive_frame_field_flag'] = read_1()
    io['direct_8x8_inference_flag'] = read_1()
    io['frame_cropping_flag'] = read_1()
    if io['frame_cropping_flag']:
      io['crop_left'] = read_ue()
      io['crop_right'] = read_ue()
      io['crop_top'] = read_ue()
      io['crop_bottom'] = read_ue()
    else:
      io['crop_left'] = io['crop_right'] = 0
      io['crop_top'] = io['crop_bottom'] = 0
    # Stop parsing here, we are not interested in the VUI parameters which
    # follow.

    if io['chroma_format'] == 0:
      io['color_mode'], io['sub_width_c'], io['sub_height_c'] = 'monochrome', 0, 0
    elif io['chroma_format'] == 1:
      io['color_mode'], io['sub_width_c'], io['sub_height_c'] = '4:2:0', 2, 2
    elif io['chroma_format'] == 2:
      io['color_mode'], io['sub_width_c'], io['sub_height_c'] = '4:2:2', 2, 1
    elif io['chroma_format'] == 3 and io['residual_color_transform_flag'] == 0:
      io['color_mode'], io['sub_width_c'], io['sub_height_c'] = '4:4:4', 1, 1
    elif io['chroma_format'] == 3 and io['residual_color_transform_flag'] == 1:
      io['color_mode'], io['sub_width_c'], io['sub_height_c'] = '4:4:4', 0, 0
    else:
      raise ValueError('Unknown h264 sps chroma_format: %d' % io['chroma_format'])
    io['height_in_mbs'] = (2 - io['frame_mbs_only_flag']) * io['height_in_map_units']
    io['width'] =  (io['width_in_mbs']  << 4) - io['sub_width_c']  * (io['crop_left'] + io['crop_right'])
    io['height'] = (io['height_in_mbs'] << 4) - io['sub_height_c'] * (2 - io['frame_mbs_only_flag']) * (io['crop_top'] + io['crop_bottom'])
    return io  # h264_sps_info.
  except StopIteration:
    raise ValueError('EOF in h264 avcc sps.')


def analyze_h264(fread, info, fskip, format='h264', fclass='video',
                 spec=(0, ('\0\0\0\1', '\0\0\1\x09', '\0\0\1\x27', '\0\0\1\x47', '\0\0\1\x67'), 128, lambda header: adjust_confidence(400, count_is_h264(header)))):
  # H.264 is also known as MPEG-4 AVC.
  #
  # https://www.itu.int/rec/dologin_pub.asp?lang=e&id=T-REC-H.264-201610-S!!PDF-E&type=items
  # http://gentlelogic.blogspot.com/2011/11/exploring-h264-part-2-h264-bitstream.html
  # https://yumichan.net/video-processing/video-compression/introduction-to-h264-nal-unit/
  header = fread(13)
  i = count_is_h264(header) // 100
  if not i:
    raise ValueError('h264 signature not found.')
  assert i <= len(header), 'h264 preread header too short.'
  x = header[:i]
  header = header[i:]
  info['format'], info['tracks'] = 'h264', [{'type': 'video', 'codec': 'h264'}]
  if len(header) < 4096:
    header += fread(4096 - len(header))
  if has_bad_emulation_prevention(header):
    raise ValueError('Bad emulation prevention in h264.')
  i = header.find('\0\0\1')
  if i >= 0:
    header = header[:i]  # Keep until end of SPS NAL unit.
  # Remove emulation_prevention_three_byte()s.
  header = header.replace('\0\0\3', '\0\0')
  h264_sps_info = parse_h264_sps(header)
  set_video_dimens(info['tracks'][0],
                   h264_sps_info['width'], h264_sps_info['height'])


# --- H.265.


def count_is_h265(header):
  # Allowed prefix hex regexp: ((00)?0000014601(10|30|50))?(00)?000001(40|42)01
  #
  # We check that forbidden_zero_bit is 0, nuh_layer_id is 1,
  # nuh_temporal_id_plus1 == 1. According to the H.265 spec, these are true
  # for AUD, VPS and SPS NAL unit types.
  if has_bad_emulation_prevention(header):
    return False
  i = 5 * header.startswith('\0\0\1\x46\1') or 6 * header.startswith('\0\0\0\1\x46\1')
  if i:
    if i >= len(header) or header[i] not in '\x10\x30\x50':
      return False
    i += 1
  if header[i : i + 3] == '\0\0\0':
    i += 1
    if header[i : i + 3] == '\0\0\0':
      i += 1
  if header[i : i + 3] != '\0\0\1':
    return False
  i += 3
  if header[i : i + 2] not in ('\x40\1', '\x42\1'):
    return False
  i += 2
  if i >= len(header):
    return False
  return i * 100


def parse_h265_sps(data):
  """Parses H.256 sequence_parameter_set.

  Args:
    data: str or buffer containing the sequence_parameter_set RBSP.
  Returns:
    tuple of (width, height).
  """
  # https://www.itu.int/rec/dologin.asp?lang=e&id=T-REC-H.265-201504-S!!PDF-E&type=items
  # https://github.com/MediaArea/MediaInfoLib/blob/5acd58a3fc11688a29bf50a512920fecb3ddcd46/Source/MediaInfo/Video/File_Hevc.cpp#L1445
  #
  # Maximum byte size we scan of the sps is 165, with hugely overestimating
  # the allowed read_ue() sizes.
  bitstream = get_bitstream(buffer(data, 0, 165))
  def read_1():
    return int(bitstream.next() == '1')
  def read_n(n):
    r = 0
    for _ in xrange(n):
      r = r << 1 | (bitstream.next() == '1')
    return r
  def skip_n(n):
    for _ in xrange(n):
      bitstream.next()
  def read_ue():  # Unsigned varint in Exp-Golomb code, ue(v).
    r = n = 0
    while bitstream.next() == '0':
      n += 1
      if n > 32:
        raise ValueError('h265 varint too long.')
    for _ in xrange(n):
      r = r << 1 | (bitstream.next() == '1')
    return r + (1 << n) - 1
  try:
    skip_n(4)  # sps_video_parameter_set_id.
    msl = read_n(3)  # sps_max_sub_layers_minus1.
    read_1()  # sps_temporal_id_nesting_flag.
    if 1:  # profile_tier_level(1, sps_max_sub_layers_minus1).
      layer_bits = 0x30000  # general_* layer is always present.
      if msl:
        layer_bits |= read_n(16)  # sub_layer_profile_present_flag, sub_layer_level_present_flag.
        if layer_bits & ((1 << ((8 - msl) << 1)) - 1):
          raise ValueError('Bad h264 sub_layer trailing bits.')
      mask = 1 << 17
      for _ in xrange(msl + 1):
        if layer_bits & mask:  # sub_layer_profile_present_flag[i].
          #read_n(2)  # general_profile_space or sub_layer_profile_space.
          #read_1()  # sub_layer_tier_flag.
          #read_n(5)  # sub_layer_profile_idc.
          #read_n(32)  # sub_layer_profile_compatitibility_flag.
          #read_n(4)  # sub_layer_progressive_source_flag, sub_layer_interlaced_source_flag, sub_layer_non_packed_constraint_flag, sub_layer_frame_only_constraint_flag.
          #read_n(22)  # First half of sub_layer_reserved_zero_43bits.
          #read_n(21)  # Second half of sub_layer_reserved_zero_43bits.
          #read_n(1)  # sub_layer_inbld_flag (or reserved 0 bit).
          skip_n(88)
        mask >>= 1
        if layer_bits & mask:  # sub_layer_level_predent_flag[i].
          skip_n(8)  # sub_layer_idc.
        mask >>= 1
    read_ue()  # sps_seq_parameter_set_id.
    chroma_format_idc = read_ue()
    if chroma_format_idc > 3:
      raise ValueError('Bad h265 chroma_format_idc: %d' % chroma_format_idc)
    separate_colour_plane_flag = int(chroma_format_idc == 3) and read_1()
    chroma_array_type = int(not separate_colour_plane_flag) and chroma_format_idc
    crop_unit_x = (1, 2, 2, 1)[chroma_array_type]
    crop_unit_y = (1, 2, 1, 1)[chroma_array_type]
    width = read_ue()  # pic_width_in_luma_samples.
    height = read_ue()  # pic_height_in_luma_samples.
    if read_1():  # conformance_window_flag.
      width -= read_ue() * crop_unit_x  # conf_win_left_offset.
      width -= read_ue() * crop_unit_x  # conf_win_right_offset.
      height -= read_ue() * crop_unit_y  # conf_win_top_offset.
      height -= read_ue() * crop_unit_y  # conf_win_bottom_offset.
    return width, height
  except StopIteration:
    raise ValueError('EOF in h265 sequence_parameter_set.')


def analyze_h265(fread, info, fskip, format='h265', fclass='video',
                 spec=(0, ('\0\0\0\1\x46', '\0\0\0\1\x40', '\0\0\0\1\x42', '\0\0\1\x46\1', '\0\0\1\x40\1', '\0\0\1\x42\1'), 128, lambda header: adjust_confidence(500, count_is_h265(header)))):
  # H.265 is also known as MPEG-4 HEVC.
  #
  # https://www.itu.int/rec/dologin.asp?lang=e&id=T-REC-H.265-201504-S!!PDF-E&type=items
  # https://www.codeproject.com/Tips/896030/The-Structure-of-HEVC-Video
  header = fread(15)
  i = count_is_h265(header) // 100
  if not i:
    raise ValueError('h265 signature not found.')
  assert i <= len(header), 'h265 preread header too short.'
  info['format'], info['tracks'] = 'h265', [{'type': 'video', 'codec': 'h265'}]
  if len(header) - i < 165:
    header += fread(165 - (len(header) - i))
  if has_bad_emulation_prevention(header):
    raise ValueError('Bad emulation prevention in h265.')
  if header[i - 2] == '\x40':  # Ignore video parameter set (VPS).
    i = header.find('\0\0\1', i)
    if i < 0:
      raise ValueError('EOF in h265 vps.')
    i += 5
  if header[i - 2: i] != '\x42\1':
    raise ValueError('Expected h265 sps, got nalu_type=%d' %
                     ((ord(header[i - 2]) >> 1) & 63))
  if len(header) - i < 165:
    header += fread(165 - (len(header) - i))
  i, j = header.find('\0\0\1', i), i
  if i < 0:
    i = len(header)
  header = header[j : i]  # Keep until end of SPS NAL unit.
  # Remove emulation_prevention_three_byte()s.
  header = header.replace('\0\0\3', '\0\0')
  width, height = parse_h265_sps(header)
  set_video_dimens(info['tracks'][0], width, height)


# --- Audio streams in MPEG.


def is_mpeg_adts(header, expect_aac=None):
  # Works with: isinstance(header, (str, buffer)).
  return (len(header) >= 4 and header[0] == '\xff' and
          ((header[1] in '\xe2\xe3' '\xf2\xf3\xf4\xf5\xf6\xf7\xfa\xfb\xfc\xfd\xfe\xff' and
           ord(header[2]) >> 4 not in (0, 15) and ord(header[2]) & 0xc != 12) or
           (expect_aac is not False and header[1] in '\xf0\xf1\xf8\xf9' and not ord(header[2]) & 2 and ((ord(header[2]) >> 2) & 15) < 13)))


def get_mpeg_adts_track_info(header, expect_aac=None):
  # https://en.wikipedia.org/wiki/Elementary_stream
  if len(header) < 4:
    raise ValueError('Too short for mpeg-adts.')
  track_info = {'type': 'audio'}
  is_aac = header[0] == '\xff' and header[1] in '\xf0\xf1\xf8\xf9'
  if expect_aac or (expect_aac is None and is_aac):
    # https://wiki.multimedia.cx/index.php/ADTS
    # AAC is also known as MPEG-4 Part 3 audio, MPEG-2 Part 7 audio.
    if not is_aac:
      raise ValueError('mpeg-adts aac signature not found.')
    track_info['codec'] = 'aac'
    track_info['subformat'] = 'mpeg-4'
    sfi = (ord(header[2]) >> 2) & 15
    if sfi > 12:
      raise ValueError('Invalid mpeg-adts AAC sampling frequency index: %d' % sfi)
    track_info['sample_rate'] = (96000, 88200, 6400, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000, 7350, 0, 0, 0)[sfi]
    if ord(header[2]) & 2:
      raise ValueError('Unexpected mpeg-adts AAC private bit.')
    cc = ord(header[2]) >> 7 << 2 | ord(header[3]) >> 6
    if cc:
      track_info['channel_count'] = cc + (cc == 7)
  else:
    sfi = (ord(header[2]) >> 2) & 3
    if (header.startswith('\xff\xe2') or header.startswith('\xff\xe3')) and (
        (ord(header[1]) & 6) == 2):
      track_info['subformat'] = 'mpeg-25'  # 2.5.
      track_info['sample_rate'] = (11025, 12000, 8000, 0)[sfi]
    elif header.startswith('\xff') and ord(header[1]) >> 4 == 0xf:
      if (ord(header[1]) >> 4) & 1:
        track_info['subformat'] = 'mpeg-1'
        track_info['sample_rate'] = (44100, 48000, 32000, 0)[sfi]
      else:
        track_info['subformat'] = 'mpeg-2'
        track_info['sample_rate'] = (22050, 24000, 16000, 0)[sfi]
    else:
      raise ValueError('mpeg-adts signature not found.')
    layer = 4 - ((ord(header[1]) >> 1) & 3)
    if layer == 4:
      raise ValueError('Invalid layer.')
    if ord(header[2]) >> 4 in (0, 15):
      raise ValueError('Invalid bit rate index %d.' % ord(header[2]) >> 4)
    if sfi == 3:
      raise ValueError('Invalid sampling frequency index 3.')
    track_info['codec'] = ('', 'mp1', 'mp2', 'mp3')[layer]
    track_info['channel_count'] = 1 + ((ord(header[3]) & 0xc0) != 0xc0)
  track_info['sample_size'] = 16
  return track_info


def analyze_mpeg_adts(fread, info, fskip, format='mpeg-adts', extra_formats=('mp3',), fclass='audio',
                      spec=(0, '\xff', 1, ('\xe2', '\xe3', '\xf2', '\xf3', '\xf4', '\xf5', '\xf6', '\xf7', '\xfa', '\xfb', '\xfc', '\xfd', '\xfe', '\xff', '\xf0', '\xf1', '\xf8', '\xf9'), 3, lambda header: (is_mpeg_adts(header), 30)),
                      header=''):
  # MPEG audio elementary stream. https://en.wikipedia.org/wiki/Elementary_stream
  if len(header) < 4:
    header += fread(4 - len(header))
  info['tracks'] = [get_mpeg_adts_track_info(header)]
  if (info['tracks'][0]['codec'] == 'mp3' and
      info['tracks'][0]['subformat'] == 'mpeg-1'):
    info['format'] = 'mp3'
  else:
    info['format'] = 'mpeg-adts'


def is_ac3(header):
  # Works with: isinstance(header, (str, buffer)).
  return (len(header) >= 7 and
          header[0] == '\x0b' and header[1] == '\x77' and
          ord(header[4]) >> 6 != 3)


def get_ac3_track_info(header):
  # https://raw.githubusercontent.com/trms/dvd_import/master/Support/a_52a.pdf
  if len(header) < 7:
    raise ValueError('Too short for ac3.')
  if not header.startswith('\x0b\x77'):
    raise ValueError('ac3 signature not found.')
  arate = (48000, 44100, 32000, 0)[ord(header[4]) >> 6]  # fscod.
  if arate == 0:
    raise ValueError('Invalid ac3 fscode (arate).')
  anch = (2, 1, 2, 3, 3, 4, 4, 5)[ord(header[6]) >> 5]  # acmod.
  track_info = {'type': 'audio'}
  track_info['codec'] = 'ac3'
  track_info['sample_size'] = 16
  track_info['sample_rate'] = arate
  track_info['channel_count'] = anch
  return track_info


def analyze_ac3(fread, info, fskip):
  header = fread(7)
  info['format'] = 'ac3'
  info['tracks'] = [get_ac3_track_info(header)]


def is_dts(header):
  # Works with: isinstance(header, (str, buffer)).
  return ((len(header) >= 4 and header[:4] == '\x7f\xfe\x80\x01') or
          (len(header) >= 4 and header[:4] == '\xfe\x7f\x01\x80') or
          (len(header) >= 5 and header[:4] == '\x1f\xff\xe8\x00' and 4 <= ord(header[4]) <= 7) or
          (len(header) >= 6 and header[:4] == '\xff\x1f\x00\xe8' and 4 <= ord(header[5]) <= 7))


def yield_swapped_bytes(data):
  if not isinstance(data, (str, buffer)):
    raise TypeError
  data = iter(data)
  for b0 in data:
    for b1 in data:
      yield b1
      break
    else:
      yield '\0'
    yield b0


def yield_uint14s(data):
  if not isinstance(data, (str, buffer)):
    raise TypeError
  data = iter(data)
  for b0 in data:
    b0 = ord(b0)
    if (b0 >> 5) not in (0, 7):
      raise ValueError('Invalid 14-to-16 sign-extension.')
    for b1 in data:
      yield (b0 & 63) << 8 | ord(b1)
      break
    else:
      yield (b0 & 63) << 8


def yield_convert_uint14s_to_bytes(uint14s):
  uint14s = iter(uint14s)
  for v in uint14s:
    # Now v has 14 bits.
    yield chr(v >> 6)
    for w in uint14s:
      v = (v & 63) << 14 | w  # 20 bits.
      break
    else:
      yield chr((v & 63) << 2)
      break
    yield chr((v >> 12) & 255)
    yield chr((v >> 4) & 255)
    for w in uint14s:
      v = (v & 15) << 14 | w  # 18 bits.
      break
    else:
      yield chr((v & 15) << 4)
      break
    yield chr((v >> 10) & 255)
    yield chr((v >> 2) & 255)
    for w in uint14s:
      v = (v & 3) << 14 | w  # 16 bits.
      break
    else:
      yield chr((v & 3) << 6)
      break
    yield chr(v >> 8)
    yield chr(v & 255)


def get_dts_track_info(header):
  # https://en.wikipedia.org/wiki/DTS_(sound_system)
  # http://www.ac3filter.net/wiki/DTS
  # https://wiki.multimedia.cx/index.php/DTS
  # https://github.com/MediaArea/MediaInfoLib/blob/master/Source/MediaInfo/Audio/File_Dts.cpp
  if len(header) < 13:
    raise ValueError('Too short for dts.')
  if header.startswith('\x1f\xff\xe8\x00') and 4 <= ord(header[4]) <= 7:
    header = ''.join(yield_convert_uint14s_to_bytes(yield_uint14s(buffer(header, 0, 18))))
  elif header.startswith('\xff\x1f\x00\xe8') and 4 <= ord(header[5]) <= 7:
    header = ''.join(yield_convert_uint14s_to_bytes(yield_uint14s(''.join(yield_swapped_bytes(buffer(header, 0, 18))))))
  elif header.startswith('\x7f\xfe\x80\x01'):
    pass
  elif header.startswith('\xfe\x7f\x01\x80'):
    header = ''.join(yield_swapped_bytes(buffer(header, 0, 15)))
  else:
    raise ValueError('dts signature not found.')
  cpf = (ord(header[4]) >> 1) & 1  # Has CRC-32?
  if len(header) < 13 + 2 * cpf:
    raise ValueError('EOF in dts header.')
  h, = struct.unpack('>H', header[7 : 9])
  amode, sfreq = (h >> 6) & 63, (h >> 2) & 15
  if sfreq < 16:  # >= 16 is user-defined.
    arate = (0, 8000, 16000, 32000, 0, 0, 11025, 22050, 44100, 0, 0, 12000, 24000, 48000, 96000, 192000)[sfreq]
    if not arate:
      raise ValueError('Invalid dts sfreq (arate).')
  anch = (1, 2, 2, 2, 2, 3, 3, 4, 4, 5, 6, 6, 6, 7, 8, 8)[amode]
  i = 11 + 2 * cpf
  h, = struct.unpack('>H', header[i : i + 2])
  pcmr = (h >> 6) & 3
  asbits = (16, 20, 24, 24)[pcmr >> 1]
  return {'type': 'audio', 'codec': 'dts', 'sample_size': asbits,
          'sample_rate': arate, 'channel_count': anch}


def analyze_dts(fread, info, fskip):
  header = fread(18)
  info['format'] = 'dts'
  info['tracks'] = [get_dts_track_info(header)]


class MpegAudioHeaderFinder(object):
  """Supports the mpeg-adts (mp1, mp2, mp3) and ac3 audio codecs."""

  __slots__ = ('_buf', '_header_ofs', '_expect_aac')

  def __init__(self, expect_aac):
    self._buf, self._header_ofs, self._expect_aac = '', 0, expect_aac

  def get_track_info(self):
    buf = self._buf
    if buf.startswith('\xff') and is_mpeg_adts(buf, self._expect_aac):
      import sys; sys.stdout.flush()
      track_info = get_mpeg_adts_track_info(buf)
    elif buf.startswith('\x0b\x77') and is_ac3(buf):
      track_info = get_ac3_track_info(buf)
    else:
      return None
    track_info['header_ofs'] = self._header_ofs
    return track_info

  def append(self, data):
    """Processes data until the first MPEG video sequence header is found."""
    if not isinstance(data, (str, buffer)):
      raise TypeError
    if not data:
      return
    buf = self._buf
    if ((buf.startswith('\xff') and is_mpeg_adts(buf, self._expect_aac)) or
        (buf.startswith('\x0b\x77') and is_ac3(buf))):
      return  # Found before.
    # We could do fewer copies with a 2-pass with data[:6] in pass 1 if data
    # is an str. We don't bother optimizing this, because data is a buffer
    # in production.
    buf = self._buf + data[:]
    limit = len(buf) - 6
    i = 0
    while i < limit:
      j1 = buf.find('\xff', i)
      if j1 < 0:
        j1 = limit
      j2 = buf.find('\x0b\x77', i)
      if j2 < 0:
        j2 = limit
      if j1 <= j2:
        if j1 < limit and is_mpeg_adts(buffer(buf, j1)):
          self._header_ofs += j1
          self._buf = buf[j1:]  # Found.
          return
        else:
          i = j1 + 1
      else:
        if j2 < limit and is_ac3(buffer(buf, j2)):
          self._header_ofs += j2
          self._buf = buf[j2:]  # Found.
          return
        else:
          i = j2 + 1
    if len(buf) > 6:
      self._header_ofs += len(buf) - 6
    self._buf = buf[-6:]  # Not found.


# --- Video streams in MPEG.


def parse_mpeg_video_header(header, expect_mpeg4=None):
  # The first 145 bytes contain the mpeg-1 and mpeg-2 headers. mpeg-4
  # headers are at most 48 bytes except if they contain user_data.
  #
  # TODO(pts): Some DVD VTS_01_3.VOB files start with
  # '\x00\x00\x01\xb5\x87W[\x98\x00\x00\x00\x01\x01\x1a7\xf0\xfd\xa3F\x8c0\xd1\xa3F\x8d\x18a\xa3',
  # causing us to detect mpeg-4 incorrectly (they are actually mpeg-2).
  is_mpeg4 = (
      header.startswith('\0\0\1\xb5') or
      (header.startswith('\0\0\1\xb0') and header[5 : 9] == '\0\0\1\xb5'))
  if expect_mpeg4 or (expect_mpeg4 is None and is_mpeg4):
    if not is_mpeg4:
      raise ValueError('mpeg-video mpeg-4 signature not found.')
    # https://en.wikipedia.org/wiki/MPEG-4_Part_2
    # Also known as: MPEG-4 Part 2, MPEG-4 Visual, MPEG ASP, extension of
    # H.263, DivX, mp42.
    track_info = {'type': 'video', 'codec': 'mpeg-4'}
    if header.startswith('\0\0\1\xb0'):
      # '\0\0\1\xb0' is the profile header (visual_object_sequence_start),
      # with a single-byte value.
      if header[4] == '\0':
        raise ValueError('Bad mpeg-video mpeg-4 profile_level 0.')
      track_info['profile_level'], i = ord(header[4]), 9
    else:
      track_info['profile_level'], i = 0, 4
    # Get width and height in get_mpeg_video_track_info instead of here.
  else:  # Returns full info if len(header) >= 145.
    # https://en.wikipedia.org/wiki/Elementary_stream
    # http://www.cs.columbia.edu/~delbert/docs/Dueck%20--%20MPEG-2%20Video%20Transcoding.pdf
    if len(header) < 9:
      raise ValueError('Too short for mpeg-video.')
    # MPEG video sequence header start code.
    if not header.startswith('\0\0\1\xb3'):
      raise ValueError('mpeg-video signature not found.')
    wdht, = struct.unpack('>L', header[3 : 7])
    track_info = {'type': 'video', 'codec': 'mpeg'}
    # TODO(pts): Verify that width and height are positive.
    track_info['width'] = (wdht >> 12) & 0xfff
    track_info['height'] = wdht & 0xfff
    if len(header) >= 16 and not ord(header[11]) & 3:
      i = 12
    elif len(header) >= 144 and ord(header[11]) & 2 and ord(header[75]) & 1:
      i = 140
    elif len(header) >= 80 and (
        (ord(header[11]) & 2 and not ord(header[75]) & 1) or
        (not ord(header[11]) & 2 and ord(header[11]) & 1)):
      i = 76
    else:
      i = None
    if i:
      start_data = header[i : i + 4]
      if start_data == '\0\0\0\1':
        i += 1
        start_data = header[i : i + 4]
      if start_data in ('\0\0\1\xb2', '\0\0\1\xb8'):  # \xb2: user data;  \xb8: (group of pictures).
        track_info['codec'] = 'mpeg-1'
      elif start_data in ('\0\0\1\xb5'):  # MPEG-2 sequence extension.
        # TODO(pts): Parse the sequence_extension, prepend 2+2 bits to width= and height=.
        # http://dvd.sourceforge.net/dvdinfo/mpeghdrs.html#ext
        track_info['codec'] = 'mpeg-2'
      elif not start_data.startswith('\0\0\1'):
        raise ValueError('mpeg-video start expected.')
      else:
        raise ValueError('Unexpected mpeg-video start code: 0x%02x' % ord(start_data[3]))
  return i, track_info


def find_mpeg_video_mpeg4_video_object_layer_start(header, visual_object_start_ofs):
  header = str(header)
  i = header.find('\0\0\1', visual_object_start_ofs)
  if i < 0 or i + 4 > len(header):
    raise ValueError('EOF in mpeg-video mpeg-4 visual_object_start.')
  while header[i + 3] == '\xb3':  # user_data.
    i = header.find('\0\0\1', i + 4)
    if i < 0 or i + 4 > len(header):
      raise ValueError('EOF in mpeg-video mpeg-4 user_data.')
  if header[i + 3] < '\x20':  # video_object_start.
    if i + 8 > len(header):
      raise ValueError('EOF in mpeg-video mpeg-4 video_object_start.')
    i += 4
    if header[i : i + 3] != '\0\0\1':
      raise ValueError('Bad non-empty mpeg-video mpeg-4 video_object_start.')
  if not '\x20' <= header[i + 3] <= '\x2f':
    raise ValueError('Expected mpeg-video mpeg-4 video_object_layer_start.')
  return i + 4


def parse_mpeg_video_mpeg4_video_object_layer_start(data, profile_level):
  # https://gitlab.bangl.de/crackling-dev/android_frameworks_base/blob/a979ad6739d573b3823b0fe7321f554ef5544753/media/libstagefright/rtsp/APacketSource.cpp#L268
  # https://github.com/MediaArea/MediaInfoLib/blob/3f4052e3ad4de45f68e715eb6f5746e2ca626ffe/Source/MediaInfo/Video/File_Mpeg4v.cpp#L1
  # https://github.com/boundary/wireshark/blob/master/epan/dissectors/packet-mp4ves.c
  # https://www.google.com/search?q="video_object_layer_verid"
  # Extension of: https://www.itu.int/rec/dologin_pub.asp?lang=e&id=T-REC-H.263-200501-I!!PDF-E&type=items
  #
  # 24 bytes of bitstream is enough for the rest.
  bitstream = get_bitstream(buffer(data, 0, 24))
  def read_1():
    return int(bitstream.next() == '1')
  def read_n(n):
    r = 0
    for _ in xrange(n):
      r = r << 1 | (bitstream.next() == '1')
    return r
  def expect_1():
    if not read_1():
      raise ValueError('Expected marker bit 1 in mpeg-video mpeg-4 video_object_layer_start.')
  def expect_shape():
    vob_layer_shape = read_n(2)  # video_object_layer_shape
    if vob_layer_shape:  # 0: Rectangular, 2: BinaryOnly, 3: GrayScale.
      raise ValueError('Expected mpeg-video mpeg-4 video_object_layer_shape rectangular, got: %d' % vob_layer_shape)
  try:
    read_1()  # random_accessible_vol.
    vob_type = read_n(8)  # video_object_type_indication.
    if vob_type == 0x21:  # Fine granularity scalable.
      raise ValueError('Unsupported mpeg-video mpeg-4 video_object_type_indication.')
    if 225 <= profile_level <= 232:  # Studio profile.
      read_n(4)  # visual_object_layer_verid.
      expect_shape()
      read_n(4)  # video_object_layer_shape_extension.
      read_n(1)  # progressive_sequence.
      read_n(1)  # rgb_compontents.
      read_n(2)  # chroma_format.
      read_n(4)  # bits_per_pixel.
    else:
      if read_1():  # is_object_layer_identifier
        read_n(4 + 3)  # video_object_layer_verid, video_object_layer_priority.
      if read_n(4) == 0xf:  # aspect_ratio_info.
        read_n(8 + 8)  # par_width, par_height.
      if read_1():  # vol_control_parameters.
        read_n(2 + 1)  # chrome_format, low_delay.
        if read_1():  # vbv_parameters
          read_n(15)  # first_half_bit_rate.
          expect_1()
          read_n(15)  # latter_half_bit_rate.
          expect_1()
          read_n(15)  # first_half_vbv_buffer_size.
          expect_1()
          read_n(3 + 11)  # latter_half_vbv_buffer_size, first_half_vbv_occupancy.
          expect_1()
          read_n(15)  # latter_half_vbv_occupancy.
          expect_1()
      expect_shape()
      expect_1()
      vop_time_increment_resolution = read_n(16)
      expect_1()
      if read_1():  # fixed_vop_rate.
        time_size = 0
        while time_size <= 16 and vop_time_increment_resolution >= (1 << time_size):
          time_size += 1
        read_n(time_size)  # fixed_vop_time_increment.
    expect_1()
    width = read_n(13)  # video_object_layer_width.
    expect_1()
    height = read_n(13)  # video_object_layer_height.
    expect_1()
    return width, height
  except StopIteration:
    raise ValueError('EOF in mpeg-video mpeg-4 video_object_layer_start.')


def get_mpeg_video_track_info(header, expect_mpeg4=None):
  i, track_info = parse_mpeg_video_header(header, expect_mpeg4)
  if track_info['codec'] == 'mpeg-4':
    i = find_mpeg_video_mpeg4_video_object_layer_start(header, i)
    width, height = parse_mpeg_video_mpeg4_video_object_layer_start(
        buffer(header, i), track_info['profile_level'])
    set_video_dimens(track_info, width, height)
  return track_info


class MpegVideoHeaderFinder(object):
  """Supports the mpeg video codec."""

  __slots__ = ('_buf', '_header_ofs', '_expect_mpeg4', '_ids')

  def __init__(self, expect_mpeg4=None):
    self._buf, self._header_ofs, self._expect_mpeg4 = '', 0, expect_mpeg4
    if self._expect_mpeg4 is False:
      self._ids = '\xb3'  # MPEG-1 or MPEG-2 video sequence.
    else:
      self._ids = '\xb0\xb3\xb5'  # Also includes MPEG-4.

  def get_track_info(self):
    buf = self._buf
    # MPEG video sequence header start code.
    if buf.startswith('\0\0\1') and buf[3 : 4] in self._ids:
      try:
        parse_mpeg_video_header(buf, self._expect_mpeg4)
      except ValueError:
        return None
      track_info = get_mpeg_video_track_info(buf)
      track_info['header_ofs'] = self._header_ofs
      return track_info
    return None

  def append(self, data):
    """Processes data until the first MPEG video sequence header is found."""
    if not isinstance(data, (str, buffer)):
      raise TypeError
    if data:
      buf, ids = self._buf, self._ids
      # MPEG video sequence header start code. We need 7 bytes of header.
      if buf.startswith('\0\0\1') and buf[3 : 4] in ids:  # Found before signature.
        if len(buf) < 145:
          self._buf = buf + data[:145 - len(buf)]
      elif buf.endswith('\0\0\1') and data[0] in ids:
        self._header_ofs += len(buf) - 3
        self._buf = buf[-3:] + data[:145 - 3]  # Found signature.
      elif buf.endswith('\0\1') and data[0] == '\1' and data[1] in ids:
        self._header_ofs += len(buf) - 2
        self._buf = buf[-2:] + data[:145 - 2]  # Found signature.
      elif buf.endswith('\0') and data[:2] == '\0\1' and data[2] in ids:
        self._header_ofs += len(buf) - 1
        self._buf = buf[-1] + data[:145 - 1]  # Found signature.
      else:
        self._header_ofs += len(buf)
        data = data[:]  # Convert buffer to str.
        i = i1 = data.find('\0\0\1\xb3')
        if len(ids) > 1:
          i2 = data.find('\0\0\1\xb0')
          i3 = data.find('\0\0\1\xb5')
        else:
          i2 = i3 = -1
        if i < 0 or (i2 >= 0 and i2 < i):
          i = i2
        if i < 0 or (i3 >= 0 and i3 < i):
          i = i3
        if i >= 0:
          self._header_ofs += i
          self._buf = data[i : i + 145]  # Found signature.
        elif len(data) >= 3:
          self._header_ofs += len(data) - 3
          self._buf = data[-3:]  # Not found.
        else:
          self._buf = buf[-3 + len(data):] + data  # Not found.


def analyze_mpeg_video(fread, info, fskip, format='mpeg-video', fclass='video',
                       spec=(0, '\0\0\1', 3, ('\xb3', '\xb0', '\xb5'), 9, lambda header: (header[3] != '\xb0' or header[5 : 9] == '\0\0\1\xb5', 1))):
  info['format'] = 'mpeg-video'
  # 145 bytes is enough unless the mpeg-4 headers contain long user_data.
  # TODO(pts): Get rid of the 145 limit here and above.
  header = fread(145)
  i, track_info = parse_mpeg_video_header(header)
  if track_info['codec'] == 'mpeg-4':
    i = find_mpeg_video_mpeg4_video_object_layer_start(header, i)
    width, height = parse_mpeg_video_mpeg4_video_object_layer_start(
        buffer(header, i), track_info['profile_level'])
    set_video_dimens(track_info, width, height)
  info['tracks'] = [track_info]


# --- Multiplexed MPEG.


def analyze_mpeg_ps(fread, info, fskip, format='mpeg-ps', fclass='media',
                    spec=(0, '\0\0\1\xba')):
  # Based on: https://en.wikipedia.org/wiki/MPEG_program_stream
  # Also based on: Use http://www.hampa.ch/mpegdemux/
  #   http://www.hampa.ch/mpegdemux/mpegdemux-0.1.4.tar.gz
  #   mpegdemux-0.1.4/src/mpeg_parse.c
  #   $ mpegdemux.static -d -s 0xe0 -b /tmp/m1dvideo.mpg m1.mpg
  #   $ mpegdemux.static -d -s 0xc0 -b /tmp/m1daudio.mpg m1.mpg
  #
  # MPEG-PES packet SID (http://dvd.sourceforge.net/dvdinfo/pes-hdr.html):
  #
  # * 0xbd; Private stream 1 (non MPEG audio, subpictures); has extension
  #         AC3 audio streams are typically bd[80], bd[81] etc.
  # * 0xbe; Padding stream; no extension, just ignore contents
  # * 0xbf; Private stream 2 (navigation data); mostly in DVD .vob; no extension
  # * 0xc0...0xdf; MPEG-1 or MPEG-2 audio stream; has extension
  # * 0xe0...0xef; MPEG-1 or MPEG-2 video stream; has extension
  # * Others: http://dvd.sourceforge.net/dvdinfo/mpeghdrs.html
  #
  # These are present, but not as MPEG-PES SID (stream ID) values:
  #
  # * 0xb9: MPEG-PS end
  # * 0xba: MPEG-PS pack header packet, file signature
  # * 0xbb: MPEG-PS system header packet
  # * 0xbc: program stream map
  # * 0xff: program stream directory
  #
  # TODO(pts): Can we get a list of SIDs without scanning through the file?
  # TODO(pts): Detect subformat=dvd-video even for VTS_??_2.VOB, which starts with MPEG-PS pack header, then it has the system header packet later.
  # TODO(pts): Count packet sizes for subformat=dvd-video, check for multiple of 2048.
  header = fread(12)
  if len(header) < 4:
    raise ValueError('Too short for mpeg-ps.')
  if not header.startswith('\0\0\1\xba'):
    raise ValueError('mpeg-ps signature not found.')
  info['format'] = format  # 'mpeg-ps'.
  if len(header) < 12:
    return
  maybe_dvd, never_dvd = 0, True
  def is_pack_dvd(data):
    # http://stnsoft.com/DVD/packhdr.html
    return data[:4] == '\0\0\1\xba' and ord(data[4]) >> 6 == 1 and data[13] == '\xf8' and (ord(data[4]) & 196) == 68 and ord(data[6]) & 4 and ord(data[8]) & 4 and ord(data[9]) & 1 and (ord(data[12]) & 3) == 3
  if ord(header[4]) >> 6 == 1:
    info['subformat'] = 'mpeg-2'  # MPEG-2 program stream.
    header += fread(2)
    if len(header) < 14:
      raise ValueError('Too short for mpeg-ps mpeg-2.')
    size = 14 + (ord(header[13]) & 7)
    if is_pack_dvd(header):
      maybe_dvd, never_dvd = 2, False
  elif ord(header[4]) >> 4 == 2:
    info['subformat'] = 'mpeg-1'  # MPEG-1 system stream.
    size = 12
  else:
    raise ValueError('Invalid mpeg-ps subformat 0x%02x.' % ord(header[4]))
  assert size >= len(header), 'mpeg-ps size too large.'
  if not fskip(size - len(header)):
    raise ValueError('EOF in mpeg-ps header.')

  # Scan for packets and packs.
  expect_system_header = True
  had_audio = had_video = False
  info['tracks'] = []
  skip_count = av_packet_count = packet_count = 0
  # Maps from SID to MpegVideoHeaderFinder or MpegAudioHeaderFinder. We use
  # finders to find the MPEG elementary stream header for video and audio
  # frames because the beginning of the frame may be truncated.
  finders = {}
  packet_limit, av_packet_limit = 1500, 1000
  while 1:
    data = fread(4)
    while len(data) == 4 and not data.startswith('\0\0\1'):
      maybe_dvd &= 1
      # TODO(pts): Don't skip or read too much in total.
      data = data[1 : 4] + fread(1)
      skip_count += 1
      if skip_count >= 100000:
        break
    if len(data) != 4:
      break
    sid = ord(data[3])
    if sid == 0xb9:  # MPEG end code.
      maybe_dvd &= 1
      break
    elif sid == 0xba:  # MPEG pack.
      maybe_dvd &= 1
      data = fread(8)
      if len(data) < 8:
        break  # raise ValueError('EOF in mpeg-ps pack.')
      if ord(data[0]) >> 6 == 1:  # MPEG-2.
        data += fread(2)
        if len(data) < 10:
          raise ValueError('Too short for mpeg-ps mpeg-2 pack.')
        size = 10 + (ord(data[9]) & 7)
        if size == 10:
          data += fread(10 - len(data))
          if len(data) < 10:
            break  # raise ValueError('EOF in mpeg-ps pack header.')
          if maybe_dvd == 0 and not never_dvd and is_pack_dvd('\0\0\1\xba' + data):
            maybe_dvd = 2
          size = len(data)
      elif ord(data[0]) >> 4 == 2:  # MPEG-1.
        size = 8
      else:
        raise ValueError('Invalid mpeg-ps pack subformat 0x%02x.' % ord(data[0]))
      assert size >= len(data), 'mpeg-ps pack size too large.'
      if not fskip(size - len(data)):
        break  # raise ValueError('EOF in mpeg-ps pack header.')
      never_dvd = never_dvd or not maybe_dvd
      expect_system_header = True
    elif sid == 0xbb:  # MPEG system header.
      if maybe_dvd != 2:
        maybe_dvd &= 1
      packet_count += 1
      if packet_count > packet_limit:  # This should be large enough for MPEG pack header in dvd-video VTS_??_2.VOB.
        break
      if not expect_system_header:
        raise ValueError('Unexpected mpeg-ps system header.')
      expect_system_header = False
      data = fread(2)
      if len(data) < 2:
        break  # raise ValueError('EOF in mpeg-ps system header size.')
      size, = struct.unpack('>H', data)
      if size != 18:
        maybe_dvd &= 1
      if maybe_dvd == 2:
        data = fread(size)
        if len(data) != size:
          break  # raise ValueError('EOF in mpeg-ps system header.')
        # System header: http://stnsoft.com/DVD/sys_hdr.html
        if (not (ord(data[0]) & 128) or (ord(data[3]) & 1) or not (ord(data[2]) & 1) or (ord(data[4]) & 63) != 33 or data[5] not in ('\xff', '\x7f') or
            data[6] != '\xb9' or (ord(data[7]) & 224) != 224 or data[9] != '\xb8' or (ord(data[10]) & 224) != 192 or data[12] != '\xbd' or
            (ord(data[13]) & 224) not in (224, 192) or data[15] != '\xbf' or data[16 : 18] != '\xe0\x02'):
          maybe_dvd = 0
          never_dvd = True
        else:
          maybe_dvd = 4
      elif not fskip(size):
        break  # raise ValueError('EOF in mpeg-ps system header.')
    elif 0xc0 <= sid < 0xf0 or sid in (0xbd, 0xbe, 0xbf, 0xbc, 0xff):  # PES packet.
      packet_count += 1
      if packet_count > packet_limit:
        break
      data = fread(2)
      if len(data) < 2:
        break  # raise ValueError('EOF in mpeg-ps packet size.')
      size, = struct.unpack('>H', data)
      if size == 0:
        # TODO(pts): Can we figure out the size?
        raise ValueError('Bad size 0 in PES packet.')
      data = fread(size)
      if len(data) < size:
        break  # raise ValueError('EOF in mpeg-ps packet.')
      if maybe_dvd == 4 and sid == 0xbf and size == 0x3d4 and data[0] == '\0':
        # http://stnsoft.com/DVD/pci_pkt.html
        maybe_dvd = 6
      elif maybe_dvd == 6 and sid == 0xbf and size == 0x3fa and data[0] == '\1':
        # http://stnsoft.com/DVD/dsi_pkt.html
        # These are the VIDEO_TS/*.VOB files on a DVD-video filesystem.
        info['subformat'] = 'dvd-video'  # Subset of subformat=mpeg-2.
        if had_audio and had_video:
          break
        maybe_dvd = 1  # Stop looking.
      else:
        maybe_dvd &= 1
      i = 0
      if 0xc0 <= sid < 0xf0 or sid == 0xbd:
        while i < len(data) and i <= 16 and data[i] == '\xff':
          i += 1
        if i >= len(data):
          break  # raise ValueError('EOF in mpeg-ps packet data.')
        if ord(data[i]) >> 6 == 2:
          if len(data) < i + 3:
            break  # raise ValueError('EOF in mpeg-ps packet type 2 data.')
          # The `is_aligned = bool(ord(data[i]) & 4)' is useless here, it's
          # False even at the beginning of the elementary stream.
          i += 3 + ord(data[i + 2])
        else:
          if ord(data[i]) >> 6 == 1:
            i += 2
            if i >= len(data):
              break  # raise ValueError('EOF in mpeg-ps packet type 1 data.')
          if (ord(data[i]) & 0xf0) == 0x20:
            i += 5
          elif (ord(data[i]) & 0xf0) == 0x30:
            i += 10
          elif ord(data[i]) == 0x0f:
            i += 1
        if sid == 0xbd:
          if i >= len(data):
            break  # raise ValueError('EOF in mpeg-ps packet SSID.')
          sid = 0x100 | ord(data[i])
          i += 1
          # For AC3 audio in DVD MPEGs (0x180 <= sid < 0x1a0), the first 3
          # bytes should be ignored: data[i : i + 3] == '\3\0\1'. No
          # problem, MpegAudioHeaderFinder takes care of this.
        #print 'mpeg-ps 0x%x data %s' % (sid, data[i : i + 20].encode('hex'))
        #if sid == 0xe0:
        #  open('videodump.mpg', 'ab').write(buffer(data, i))
        #if sid == 0xc0 or sid == 0x180:
        #  open('audiodump.mpg', 'ab').write(buffer(data, i))
        if 0xe0 <= sid < 0xf0:  # Video.
          av_packet_count += 1
          if not had_video:
             if sid not in finders:
               # Specifying expect_mpeg4=True wouldn't work here, e.g. for
               # subformat=dvd-video VTS_??_2.VOB, \0\0\1\xb5 (MPEG-2
               # extension header) may arrive earlier than \0\0\1\xb3 (MPEG
               # video sequence header), and expect_mpeg4=True would
               # interpret \0\0\1\xb5 as MPEG-4 visual_object_start, and
               # then it would fail to parse the subsequent non-empty MPEG-2
               # \0\0\1\1 slice as MPEG-4 video_object_start (which must be
               # empty).
               #
               # TODO(pts): Add parallel parsing of MPEG-2 and MPEG-4, and
               # when an non-empty MPEG-4 video_object_start is found,
               # continue scanning for MPEG-{1,2} headers.
               finders[sid] = MpegVideoHeaderFinder(expect_mpeg4=False)
             finders[sid].append(buffer(data, i))
             track_info = finders[sid].get_track_info()
             if track_info and track_info['codec'] != 'mpeg':  # Use first video stream with header.
               had_video = True
               info['tracks'].append(track_info)
               info['pes_video_at'] = track_info['header_ofs']
        elif 0xc0 <= sid < 0xe0 or 0x180 <= sid < 0x1a8:  # Audio.
          # 0xc0..0xdf: MPEG-ADTS MPEG-1 or MPEG-2 audio
          # 0x20..0x2f: DVD subtitle (subpicture)
          # 0x80..0x87: DVD AC3 audio
          # 0x88..0x8f: DVD DTS audio
          # 0xa0..0xa7: DVD LPCM (uncompressed) audio: TODO(pts): What headers does it have? Get abitrate from VTS_??_0.IFO audio parameters, see http://stnsoft.com/DVD/ifo.html
          av_packet_count += 1
          if not had_audio:
             if sid not in finders:
               # Specifying expect_aac=True wouldn't work here, it would
               # find a false AAC signature too early. And MPEG-PS files
               # can't have AAC audio anyway.
               finders[sid] = MpegAudioHeaderFinder(expect_aac=False)
             finders[sid].append(buffer(data, i))
             track_info = finders[sid].get_track_info()
             if track_info:  # Use first video stream with header.
               had_audio = True
               info['tracks'].append(track_info)
               info['pes_audio_at'] = track_info['header_ofs']
          if (had_audio and had_video and (never_dvd or maybe_dvd == 1)) or av_packet_count > av_packet_limit:
            break
    #else:  # Some broken MPEGs have useless SIDs, ignore those silently.
    #  raise ValueError('unexpected mpeg-ps sid=0x%02x' % sid)
  info['hdr_packet_count'] = packet_count
  info['hdr_av_packet_count'] = av_packet_count
  info['hdr_skip_count'] = skip_count


def analyze_mpeg_cdxa(fread, info, fskip, format='mpeg-cdxa', fclass='media',
                      spec=(0, 'RIFF', 8, 'CDXAfmt ', 17, '\0\0\0')):
  # Video CD (VCD).
  # https://github.com/Kurento/gst-plugins-bad/blob/master/gst/cdxaparse/gstcdxaparse.c
  # https://en.wikipedia.org/wiki/Video_CD
  data = fread(21)
  if len(data) < 16:
    raise ValueError('Too short for cdxa.')
  if not (data.startswith('RIFF') and data[8 : 16] == 'CDXAfmt ' and (len(data) < 20 or data[17 : 20] == '\0\0\0')):
    raise ValueError('cdxa signature not found.')
  info['format'] = 'mpeg-cdxa'
  if len(data) <= 20:
    return
  size, = struct.unpack('<L', data[16 : 20])
  if size > 1:
    if not fskip(size - 1):
      raise ValueError('EOF in cdxa fmt.')
  data = fread(8)
  if len(data) < 8:
    return
  if not data.startswith('data'):
    raise ValueError('Expected cdxa data.')

  def yield_sectors():
    do_strip0 = True
    while 1:
      data = fread(24)
      if len(data) < 24:
        break
      if not data.startswith('\0\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\0'):
        raise ValueError('Bad cdxa sector sync.')
      data = fread(2324)
      if not data:
        break
      is_short = len(data) < 2324
      if do_strip0:
        if data.lstrip('\0'):
          do_strip0 = False
          if not data.startswith('\0\0\1\xba'):
            raise ValueError('Expected mpeg-ps header in cdxa.')
        else:
          data = ''
      if data:
        yield data
      if is_short:
        break
      edc = fread(4)  # Checksum.
      if len(edc) < 4:
        break

  it = yield_sectors()
  try:
    buf = [0, it.next()]  # Reads first mpeg-ps header.
  except StopIteration:
    return  # raise ValueError('EOF before cdxa mpeg-ps header.')

  def mpeg_ps_fread(size):
    result = ''
    while size > 0:
      bufi, bufs = buf
      if not bufs:
        try:
          buf[1] = bufs = it.next()
        except StopIteration:
          break
      bufc = len(bufs)
      size -= bufc - bufi
      if size < 0:
        result += bufs[bufi : bufc + size]
        buf[0] = bufc + size
        return result
      result += bufs[bufi:]  # TODO(pts): Avoid copying.
      buf[0], buf[1] = 0, ''
    return result

  def mpeg_ps_fskip(size):
    return len(mpeg_ps_fread(size)) == size

  analyze_mpeg_ps(mpeg_ps_fread, info, mpeg_ps_fskip, format='mpeg-cdxa')


# --- mpeg-ts (MPEG TS).


def get_jpeg_dimensions(fread, header='', is_first_eof_ok=False):
  """Returns (width, height) of a JPEG file.

  Args:
    f: An object supporting the .read(size) method. Should be seeked to the
        beginning of the file.
    header: The first few bytes already read from fread.
  Returns:
    (width, height) pair of integers.
  Raises:
    ValueError: If not a JPEG file or there is a syntax error in the JPEG file.
    IOError: If raised by fread(size).
  """
  # Implementation based on pts-qiv
  #
  # A typical JPEG file has markers in these order:
  #   d8 e0_JFIF e1 e1 e2 db db fe fe c0 c4 c4 c4 c4 da d9.
  #   The first fe marker (COM, comment) was near offset 30000.
  # A typical JPEG file after filtering through jpegtran:
  #   d8 e0_JFIF fe fe db db c0 c4 c4 c4 c4 da d9.
  #   The first fe marker (COM, comment) was at offset 20.

  def read_all(size):
    data = fread(size)
    if len(data) != size:
      raise ValueError(
          'EOF in jpeg: wanted=%d got=%d' % (size, len(data)))
    return data

  data, header = header, None
  if len(data) < 4:
    data += fread(4 - len(data))
    if len(data) < 4:
      raise ValueError('Too short for jpeg.')
  if len(data) > 4:
    raise ValueError('Preread too long for jpeg.')
  if not data.startswith('\xff\xd8\xff'):
    raise ValueError('jpeg signature not found: %r.')
  m, is_first = ord(data[3]), is_first_eof_ok
  while 1:
    while m == 0xff:  # Padding.
      m = ord(read_all(1))
    if m in (0xd8, 0xd9, 0xda):
      # 0xd8: SOI unexpected.
      # 0xd9: EOI unexpected before SOF.
      # 0xda: SOS unexpected before SOF.
      raise ValueError('Unexpected marker: 0x%02x' % m)
    if is_first:
      data = fread(2)
      if not data:
        return ()
      if len(data) != 2:
        raise ValueError('EOF in jpeg first.')
      is_first = False
    else:
      data = read_all(2)
    ss, = struct.unpack('>H', data)
    if ss < 2:
      raise ValueError('Segment too short.')
    ss -= 2
    if 0xc0 <= m <= 0xcf and m not in (0xc4, 0xc8, 0xcc):  # SOF0 ... SOF15.
      if ss < 5:
        raise ValueError('SOF segment too short.')
      height, width = struct.unpack('>xHH', read_all(5))
      return width, height
    read_all(ss)
    # Some buggy JPEG encoders add ? or \0\0 after the 0xfe (COM)
    # marker. We will ignore those extra NUL bytes.
    is_nul_ok = m == 0xfe

    # Read next marker to m.
    m = read_all(2)
    if m[0] != '\xff':
      if is_nul_ok and m == '\0\0':
        m = read_all(2)
      elif is_nul_ok and m[1] == '\xff':
        m = m[1] + read_all(1)
      if m[0] != '\xff':
        raise ValueError('Marker expected.')
    m = ord(m[1])
  raise AssertionError('Internal JPEG parser error.')


def count_is_jpeg(header):
  if not header.startswith('\xff\xd8\xff'):
    return False
  i, lh = 2, len(header)
  c = 100 * i
  # Try to match more bytes (i.e. increasing c) of the most popular APP* markers.
  while i + 4 <= lh:
    marker = header[i + 1]
    if header[i] != '\xff' or marker not in '\xe0\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xeb\xec\xed\xee\xef':
      break
    c += 150  # 1 value for header[i], 16 values for marker.
    i += 2
    size, = struct.unpack('>H', header[i : i + 2])
    if size < 2 or i + size > lh:
      break
    # See statistics for leading most popular APP* segments below.
    j = i + 2
    es = i + size
    while j < es and header[j] != '\0':
      j += 1
    if j < es:
      c_name = 100 * (j + 1 - i) + (100 - 50)
      c += c_name
      name = marker + header[i + 2 : j]
      i = j + 1
      #print [name, header[i : es]]
      if name == '\xe0JFIF': # 8251073 https://www.w3.org/Graphics/JPEG/jfif3.pdf Example: '\x01\x02\x00\x00\x01\x00\x01\x00\x00'.
        if i + 9 <= es:
          if size == 16:
            c += 200
          if header[i : i + 2] in ('\1\0', '\1\1', '\1\2'):  # Version.
            c += 181
          if header[i + 3] in '\0\1\2':  # Units.
            c += 81
          if header[i + 3 : i + 5] == '\0\1':  # X density.
            c += 200
          if header[i + 5 : i + 7] == '\0\1':  # Y density.
            c += 200
          if header[i + 7] == '\0':  # Thumbnail width.
            c += 100
          if header[i + 8] == '\0':  # Thumbnail height.
            c += 100
      elif name == '\xe1Exif':  # 1244210 Example: '\x00II*\x00\x08\x00\x00\x00'.
        if i + 9 <= es and header[i] == '\0' and header[i + 1 : i + 5] in ('II*\0', 'MM\0*'):  # TIFF.
          c += 488
          if header[i + 4] == '\0' and header[i + 5 : i + 9] == '\x08\0\0\0':
            c += 400
      elif name == '\xeeAdobe': # 1003621 https://exiftool.org/TagNames/JPEG.html#Adobe Example: 'd\x08\x00\x00\x00\x01'.
        if i + 6 <= es:
          if i + 6 == es:
            c += 200
          if header[i] in '\x64\x65':
            c += 88
          if header[i + 1 : i + 3] in ('\x80\0', '\0\0'):
            c += 188
          if header[i + 3 : i + 5] == '\0\0':
            c += 200
          if header[i + 5] in '\0\1\2':
            c += 81
      elif name in ('\xe1http://ns.adobe.com/xap/1.0/', '\xe1http://ns.adobe.com/xap/1.0/ '): # 824414, 12330 https://wwwimages2.adobe.com/content/dam/acom/en/devnet/xmp/pdfs/XMP%20SDK%20Release%20cc-2016-08/XMPSpecificationPart3.pdf Example: '<?xpacket begin="'.
        if header[i : i + 16] == '<?xpacket begin=':  # TODO(pts): Also support UTF-16BE, UTF-16LE.
          c += 1600
        if '<x:xmpmeta ' in header[i : es]:
          c += 1100
      elif name == '\xedPhotoshop 3.0': # 805633 https://wwwimages2.adobe.com/content/dam/acom/en/devnet/xmp/pdfs/XMP%20SDK%20Release%20cc-2016-08/XMPSpecificationPart3.pdf Example: '8BIM\x04\x04\x00\x00\x00\x00??'.
        if i + 12 <= es and header[i : i + 4] == '8BIM':
          c += 400
          if header[i + 4 : i + 6] in ('\3\xf0', '\3\xfc', '\4\x04', '\4\x0a', '\4\x0b', '\4\x22', '\4\x24', '\4\x25'):  # Resource ID.
            c += 63
          if header[i + 6 : i + 8] == '\0\0':  # Resource name size.
            c += 200
            if header[i + 8 : i + 10] == '\0\0':  # High 2 bytes of size.
              c += 200
      elif name == '\xecDucky': # 570605 https://exiftool.org/TagNames/APP12.html#Ducky Example: '\x01\x00\x04\x00\x00\x00d\x00\x00'.
        if i + 9 <= es and header[i] == '\1':
          if i + 9 == es:
            c += 200
          c += 100
          if header[i + 1 : i + 3] == '\0\4':
            c += 200
            if header[i + 3 : i + 6] == '\0\0\0':  # Quality is between 1 and 100, we check 0..255.
              c += 300
            if header[i + 7 : i + 9] == '\0\0':  # End.
              c += 200
      elif name == '\xe2ICC_PROFILE': # 508030 Example: '\x01?\x00???'.
        if i + 3 <= es and header[i] == '\1':  # Chunk index.
          c += 100
          if header[i + 2] == '\0':  # High byte of profile size (4 bytes).
            c += 100
      elif name == '\xe2MPF': # 24363 http://fileformats.archiveteam.org/wiki/Multi-Picture_Format Example: 'II*\x00\x08\x00\x00\x00'.
        if i + 8 <= es and header[i : i + 4] in ('II*\0', 'MM\0*'):  # TIFF.
          c += 388
          if header[i + 3] == '\0' and header[i + 4 : i + 8] == '\x08\0\0\0':
            c += 400
      elif name == '\xe0JFXX': # 1409 https://www.w3.org/Graphics/JPEG/jfif3.pdf Example: '\x13'.
        if size >= 1 and header[i] in '\x10\x11\x13':
          c += 81
      else:
        c -= c_name
    i = es
  if i < lh and header[i] == '\xff':
    c += 100
    i += 1
    if i < lh and header[i] in ('\xc0', '\xc2', '\xdb', '\xfe'):
      c += 75
  return c


def analyze_jpeg(fread, info, fskip, format='jpeg', fclass='image',
                 spec=((0, '\xff\xd8\xff\xe0'),
                       (0, '\xff\xd8\xff\xe1'),  # Separate spec because of very different relative frequencies of header[3].
                       (0, '\xff\xd8\xff\xdb'),
                       (0, '\xff\xd8\xff', 3, ('\xe2', '\xc0', '\xee', '\xfe', '\xed')),
                       # 408 is arbitrary, but since cups-raster has it, we can also that much.
                       (0, '\xff\xd8\xff', 408, lambda header: adjust_confidence(300, count_is_jpeg(header))))):  # Most files will match this with highest confidence.
  # Statistics for header[3]: 8220887 e0, 560958 e1, 212585 db, 1964 e2, 1246 c0, 1215 ee, 873 fe, 473 ed.
  header = fread(4)
  if len(header) < 3:
    raise ValueError('Too short for jpeg.')
  if not header.startswith('\xff\xd8\xff'):
    raise ValueError('jpeg signature not found.')
  # TODO(pts): Which JPEG marker can be header[3]? Typically it's '\xe0'.
  info['format'] = info['codec'] = 'jpeg'
  if len(header) >= 4:
    dimensions = get_jpeg_dimensions(fread, header, is_first_eof_ok=True)
    if len(dimensions) == 2:
      info['width'], info['height'] = dimensions


def get_string_fread(header):
  i_ary = [0]

  def fread(n):
    result = header[i_ary[0] : i_ary[0] + n]
    i_ary[0] += len(result)
    return result

  return fread


def get_track_info_from_analyze_func(header, analyze_func, track_info=None):
  if not isinstance(header, (str, buffer)):
    raise TypeError
  info = {}

  if header:
    i_ary = [0]

    def fread(n):
      result = header[i_ary[0] : i_ary[0] + n]
      i_ary[0] += len(result)
      return result

    def fskip(n):
      return len(fread(n)) == n

    analyze_func(fread, info, fskip)

  track_info = dict(track_info or ())
  if isinstance(info.get('tracks'), (list, tuple)) and info['tracks']:
    track_info.update(info['tracks'][0])
  elif 'width' in info and 'height' in info and 'codec' in info:
    track_info = {'type': 'video'}
    for key in ('width', 'height', 'codec'):
      track_info[key] = info[key]
  if track_info.get('codec') in ('jpeg', 'jpeg2000'):
    track_info['codec'] = 'm' + track_info['codec']  # E.g. 'mjpeg'.
  return track_info


def get_mpeg_ts_es_track_info(header, stream_type):
  if not isinstance(header, str):
    raise TypeError
  # mpeg-ts elementary stream types:
  # https://en.wikipedia.org/wiki/Program-specific_information#Elementary_stream_types
  if stream_type in (0x01, 0x02):
    # Sometimes the wrong stream_type is used (e.g. 0x02 for mpeg-2).
    track_info = {'type': 'video', 'codec': 'mpeg-12'}
    if header:
      track_info.update(get_mpeg_video_track_info(header, expect_mpeg4=False))
  elif stream_type == 0x06:
    # stream_type=0x06 chosen by ffmpeg for mjpeg and mjpeg2000.
    # The standard says any ``privately defined MPEG-2 packetized data''.
    if not header:
      return {'type': 'video', 'codec': 'maybe-mjpeg'}
    elif header.startswith('\xff\xd8\xff'):
      track_info = {'type': 'video', 'codec': 'mjpeg'}
      track_info['width'], track_info['height'] = get_jpeg_dimensions(
          get_string_fread(header))
    elif is_jp2(header):
      track_info = get_track_info_from_analyze_func(
          buffer(header, 12), analyze_mov,
          {'type': 'video', 'codec': 'mjpeg2000'})
    elif is_jpc(header):
      track_info = get_track_info_from_analyze_func(
          buffer(header, 12), analyze_jpc,
          {'type': 'video', 'codec': 'mjpeg2000'})
    else:
      return {'type': 'video', 'codec': 'not-mjpeg'}
  elif stream_type == 0x10:
    track_info = {'type': 'video', 'codec': 'mpeg-4'}
    if header:
      track_info.update(get_mpeg_video_track_info(header, expect_mpeg4=True))
  elif stream_type == 0x1b:
    track_info = get_track_info_from_analyze_func(
        header, analyze_h264, {'type': 'video', 'codec': 'h264'})
  elif stream_type == 0x21:
    track_info = {'type': 'video', 'codec': 'mjpeg2000'}
    if is_jp2(header):
      track_info = get_track_info_from_analyze_func(
          buffer(header, 12), analyze_mov,
          {'type': 'video', 'codec': 'mjpeg2000'})
    elif header:
      raise ValueError('jp2 signature not found.')
  elif stream_type == 0x24:
    return get_track_info_from_analyze_func(
        header, analyze_h265, {'type': 'video', 'codec': 'h265'})
  elif stream_type == 0x52:
    return {'type': 'video', 'codec': 'chinese-video'}
  elif stream_type == 0xd1:
    return get_track_info_from_analyze_func(
        header, analyze_dirac, {'type': 'video', 'codec': 'dirac'})
  elif stream_type == 0xea:
    return {'type': 'video', 'codec': 'vc1'}
  elif stream_type in (0x03, 0x04):
    track_info = {'type': 'audio', 'codec': 'mp123'}
    if header:
      track_info.update(get_mpeg_adts_track_info(header, expect_aac=False))
  elif stream_type == 0x0f:
    track_info = {'type': 'audio', 'codec': 'aac'}
    if header:
      track_info.update(get_mpeg_adts_track_info(header, expect_aac=True))
  elif stream_type == 0x11:
    return {'type': 'audio', 'codec': 'loas'}
  elif stream_type == 0x1c:
    # TODO(pts): Is this LPCM (uncompressed) audio? If yes, get
    # audio paramaters.
    return {'type': 'audio', 'codec': 'pcm'}
  elif stream_type == 0x81:
    track_info = {'type': 'audio', 'codec': 'ac3'}
    if header:
      track_info.update(get_ac3_track_info(header))
  elif stream_type in (0x82, 0x85):
    if header and not is_dts(header):
      # Can be SCTE subtitle.
      return {'type': 'audio', 'codec': 'not-dts'}
    track_info = {'type': 'audio', 'codec': 'dts'}
    if header:
      track_info.update(get_dts_track_info(header))
  elif stream_type == 0x83:
    return {'type': 'audio', 'codec': 'truehd'}  # Dolby.
  elif stream_type == 0x84:
    return {'type': 'audio', 'codec': 'digital-plus'}  # Dolby.
  else:
    return None  # Unknown stream type.
  return track_info


def get_mpeg_ts_pes_track_info(header, stream_type):
  if not isinstance(header, str):
    raise TypeError
  if len(header) < 6:
    raise ValueError('EOF in mpeg-ts pes payload signature.')
  if not header.startswith('\0\0\1'):
    raise ValueError('Bad mpeg-ts pes payload signature.')
  sid = ord(header[3])
  if not (0xc0 <= sid < 0xf0 or sid == 0xbd or sid == 0xfd):
    # TODO(pts): Should we be more permissive and accept anything?
    raise ValueError('Bad mpeg-ts pes sid: 0x%02x' % sid)
  size, = struct.unpack('>H', header[4 : 6])
  j = 6
  if size:
    i = j + size
  else:
    i = len(header)
  while j < len(header) and j <= 16 and header[j] == '\xff':
    j += 1
  if j >= len(header):
    raise ValueError('EOF in mpeg-ts pes payload pes header.')
  if ord(header[j]) >> 6 == 2:
    if len(header) < j + 3:
      raise ValueError('EOF in mpeg-ps packet type 2 data.')
    j += 3 + ord(header[j + 2])
  else:
    if ord(header[j]) >> 6 == 1:
      j += 2
      if j >= len(header):
        raise ValueError('EOF in mpeg-ps packet type 1 header.')
    if (ord(header[j]) & 0xf0) == 0x20:
      j += 5
    elif (ord(header[j]) & 0xf0) == 0x30:
      j += 10
    elif ord(header[j]) == 0x0f:
      j += 1
  if j > i:
    raise ValueError('EOF in mpeg-ts pes payload sized pes header.')
  if j >= i or j >= len(header):
    # We need to check this, because get_mpeg_ts_es_track_info special-cases
    # an empty header.
    raise ValueError('EOF after mpeg-ts pes payload pes header: empty es packet.')
  if size and i <= len(header):
    # TODO(pts): Avoid copying, use buffer.
    return get_mpeg_ts_es_track_info(header[j : i], stream_type)
  try:
    return get_mpeg_ts_es_track_info(header[j : i], stream_type)
  except ValueError, e:
    if not str(e).startswith('Too short for '):
      raise
    raise ValueError('EOF in mpeg-ts pes es packet: %s' % e)


MPEG_TS_PSI_TABLES = {'pat': 0, 'cat': 1, 'pmt': 2}


def yield_mpeg_ts_psi_sections(data, table_name):
  """Parses mpeg-ts program-specific information."""
  # https://en.wikipedia.org/wiki/Program-specific_information#Table_Sections
  # https://en.wikipedia.org/wiki/Program-specific_information#PAT_(Program_association_specific_data)
  if not isinstance(data, (str, buffer)):
    raise TypeError
  tn, table_id = table_name, MPEG_TS_PSI_TABLES[table_name]
  i = 0
  if i >= len(data):
    raise ValueError('EOF in mpeg-ts %s pointer_field.' % tn)
  i += 1 + ord(data[i])
  if i > len(data):
    raise ValueError('EOF in mpeg-ts %s pointer_filler_bytes.' % tn)
  while i < len(data):
    if data[i] == '\xff':
      if data[i:].rstrip('\xff'):
        raise ValueError('Bad mpeg-ts %s suffix stuffing.' % tn)
      break
    if ord(data[i]) != table_id:
      raise ValueError('Bad mpeg-ts %s table_id: %d' % (tn, ord(data[i])))
    i += 1
    if i + 2 > len(data):
      raise ValueError('EOF in mpeg-ts %s section_size.' % tn)
    h, = struct.unpack('>H', data[i : i + 2])
    i += 2
    if not h & 0x8000:
      raise ValueError('Bad mpeg-ts %s section_syntax_indicator.' % tn)
    if h & 0x4000:
      raise ValueError('Bad mpeg-ts %s private_bit.' % tn)
    if (h & 0x3000) != 0x3000:
      raise ValueError('Bad mpeg-ts %s reserved1.' % tn)
    if h & 0xc00:
      raise ValueError('Bad mpeg-ts %s section_size_unused.' % tn)
    j = i
    i += h & 0x3ff
    if i - j > 1021:
      raise ValueError('mpeg-ts %s section too long.' % tn)
    if i > len(data):
      raise ValueError('EOF in mpeg-ts %s section.' % tn)
    i -= 4
    if i < j:
      raise ValueError('mpeg-ts %s section too short (no room for CRC32).' % tn)
    if j + 2 > i:
      raise ValueError('EOF in mpeg-ts %s section transport_stream_identifier.' % tn)
    identifier, = struct.unpack('>H', data[j : j + 2])
    j += 2
    if j >= i:
      raise ValueError('EOF in mpeg-ts %s section version byte.' % tn)
    h = ord(data[j])
    j += 1
    if (h & 0xc0) != 0xc0:
      raise ValueError('Bad mpeg-ts %s section reserved2.' % tn)
    version = (h >> 1) & 31
    if version not in (0, 1):
      raise ValueError('Bad mpeg-ts %s section version: %d' % version)
    if not h & 1:
      raise ValueError('Bad mpeg-ts %s section current_indicator.' % tn)
    if j >= i:
      raise ValueError('EOF in mpeg-ts %s section section_number.' % tn)
    section_number = ord(data[j])
    j += 1
    if j >= i:
      raise ValueError('EOF in mpeg-ts %s section last_section_number.' % tn)
    last_section_number = ord(data[j])
    j += 1
    yield (j, i, identifier, section_number, last_section_number)
    i += 4  # Skip CRC32.


def parse_mpeg_ts_pat(data):
  """Returns a list of (pmt_pid, program_num) pairs."""
  result = []
  for items in yield_mpeg_ts_psi_sections(data, 'pat'):
    j, i = items[:2]
    while j < i:
      if j + 2 > i:
        raise ValueError('EOF in mpeg-ts pat entry program_num.')
      program_num, = struct.unpack('>H', data[j : j + 2])
      j += 2
      if j + 2 > i:
        raise ValueError('EOF in mpeg-ts pat entry pmt_pid.')
      h, = struct.unpack('>H', data[j : j + 2])
      j += 2
      reserved3 = h >> 13
      if reserved3 not in (0, 7):
        # 7 is required, but we also accept 7, for some broken mpeg-ts files.
        raise ValueError('Bad mpeg-ts pat entry reserved3: %d' % reserved3)
      pmt_pid = h & 0x1fff
      if pmt_pid in (0, 0x1fff):
        raise ValueError('Bad mpeg-ts pat entry pmt_pid: 0x%x' % pmt_pid)
      if program_num != 0:  # NIT (table_name='nit') has program_num == 0.
        result.append((pmt_pid, program_num))
  if not result:
    raise ValueError('Empty mpeg-ts pat.')
  return result



def parse_mpeg_ts_pmt(data, expected_program_num):
  """Returns a list of (es_pid, stream_type) pairs."""
  result = []
  for items in yield_mpeg_ts_psi_sections(data, 'pmt'):
    j, i, identifier = items[:3]
    if identifier != expected_program_num:
      raise ValueError('Bad mpeg-ts pmt section program_num.')
    if j + 2 > i:
      raise ValueError('EOF in mpeg-ts pmt entry pcr_pid.')
    h, = struct.unpack('>H', data[j : j + 2])
    j += 2
    pcr_pid = h & 0x1fff
    if pcr_pid == 0:
      raise ValueError('Bad mpeg-ts pmt entry pcr_pid.')
    if j + 2 > i:
      raise ValueError('EOF in mpeg-ts pmt entry program_descriptor_size.')
    h, = struct.unpack('>H', data[j : j + 2])
    j += 2
    if (h & 0xf000) != 0xf000:
      raise ValueError('Bad mpeg-ts pmt entry reserved4.')
    if h & 0xc00:
      raise ValueError('Bad mpeg-ts pmt entry program_descriptor_size_unused.')
    j += h & 0x3ff
    if j > i:
      raise ValueError('EOF in mpeg-ts pmt entry program_descriptor.')
    if j >= i:
      raise ValueError('No streams in mpeg-ts pmt entry.')
    while j < i:
      if j >= i:
        raise ValueError('EOF in mpeg-ts pmt stream_info stream_type.')
      stream_type = ord(data[j])
      # https://en.wikipedia.org/wiki/Program-specific_information#Elementary_stream_types
      if stream_type in (0, 0x22, 0x23, 0x25):
        raise ValueError('Bad mpeg-ts pmt stream_info stream_type: 0x%x' % stream_type)
      j += 1
      if j + 2 > i:
        raise ValueError('EOF in mpeg-ts pmt stream_info es_pid.')
      h, = struct.unpack('>H', data[j : j + 2])
      j += 2
      if (h & 0xe000) != 0xe000:
        raise ValueError('Bad mpeg-ts pmt stream_info reserved5.')
      es_pid = h & 0x1fff
      if es_pid in (0, 0x1fff):
        raise ValueError('Bad mpeg-ts pmt stream_info es_pid: 0x%x' % es_pid)
      if j + 2 > i:
        raise ValueError('EOF in mpeg-ts pmt stream_info info_size.')
      h, = struct.unpack('>H', data[j : j + 2])
      j += 2
      if (h & 0xf000) != 0xf000:
        raise ValueError('Bad mpeg-ts pmt stream_info reserved6.')
      if h & 0xc00:
        raise ValueError('Bad mpeg-ts pmt stream_info es_descriptor_size_unused.')
      j += h & 0x3ff
      if j > i:
        raise ValueError('EOF in mpeg-ts pmt stream_info es_descriptor.')
      result.append((es_pid, stream_type))
  if not result:
    raise ValueError('Empty mpeg-ts pmt.')
  return result


def is_mpeg_ts(header):
  # https://en.wikipedia.org/wiki/MPEG_transport_stream
  # https://erg.abdn.ac.uk/future-net/digital-video/mpeg2-trans.html
  # TODO(pts): Use any of these to get more info.
  # https://github.com/topics/mpeg-ts
  # https://github.com/asticode/go-astits
  # https://github.com/drillbits/go-ts
  # https://github.com/small-teton/MpegTsAnalyzer
  # https://github.com/mzinin/ts_splitter
  is_bdav = header.startswith('\0')
  i = (0, 4)[is_bdav]
  if len(header) < i + 4:
    return False
  had_pat = had_pat_pusi = False
  cc_by_pid = {}
  #print '---ts'
  for pc in xrange(5):  # Number of packets to scan.
    if len(header) < i + 4:
      return pc > 0
    if header[i] != '\x47':
      return False
    b, = struct.unpack('>L', header[i : i + 4])
    tei, pusi, tp = (b >> 23) & 1, (b >> 22) & 1, (b >> 21) & 1
    pid = (b >> 8) & 0x1fff  # Packet id.
    tsc, afc, cc = (b >> 6) & 3, (b >> 4) & 3, b & 15
    #print 'afc=%d tei=%d pid=0x%x tsc=%d cc=%d' % (afc, tei, pid, tsc, cc)
    if not afc:  # Valid values are: 1, 2, 3.
      return False
    if tei:  # Error in transport.
      return False
    if pid == 0x1fff:  # Ignore null packet.
      continue
    if tsc:  # Scrambled packet.
      return False
    #print (pusi, cc, 'pid=0x%x' % pid, tei, tp, tsc, afc)
    if pid in cc_by_pid:
      if cc_by_pid[pid] != cc:  # Unexpected continuation cc.
        return False
    elif cc not in (0, 1):
      return False  # Unexpected followup cc.
    cc_by_pid[pid] = (cc + (afc & 1)) & 15
    if pid == 0:  # pat.
      if not (afc & 1):
        return False  # pat without payload.
      if pusi:
        had_pat_pusi = True
      elif not had_pat_pusi:
        return False
      had_pat = True
      # TODO(pts): Call parse_mpeg_ts_pat, ignore 'EOF '.
    elif 0x10 <= pid <= 0x20:
      # pid=0x11 is
      # https://en.wikipedia.org/wiki/Service_Description_Table
      pass  # DVB metadata.
    elif 0x20 <= pid < 0x1fff and had_pat:
      break
    else:
      return False
    i += (188, 192)[is_bdav]
  return True


def analyze_mpeg_ts(fread, info, fskip, format='mpeg-ts', fclass='media',
                    # is_mpeg_ts indeed needs 392 bytes.
                    spec=(0, ('\0', '\x47'), 392, lambda header: (is_mpeg_ts(header), 301))):
  prefix = fread(4)
  if len(prefix) < 4:
    raise ValueError('Too short for mpeg-ts.')
  ts_packet_count = ts_pusi_count = ts_payload_count = 0
  if prefix.startswith('\x47'):
    is_bdav = False
    info['subformat'] = 'ts'
  elif prefix.startswith('\0'):
    is_bdav = True
    info['subformat'] = 'bdav'
  else:
    raise ValueError('mpeg-ts signature not found.')
  ts_packet_first_limit = 5
  first_few_packets = []
  # Maps from pmt_pid to program_num. Empty if pat payload not found yet.
  programs = {}
  # Maps from es_pid to [stream_type, basic_track_info, track_info, buffered_data].
  es_streams = {}
  buffered_pat_data = []
  buffered_pmt_data_by_pid = {}
  es_streams_by_type = {'audio': 0, 'video': 0}
  es_payloads_by_type = {'audio': 0, 'video': 0}
  cc_by_pid = {}
  # info['format'] = 'mpeg-ts'  # Not yet, later.
  info['tracks'] = []
  eof_msg = ''
  ts_packet_count_limit = 6000
  expected_es_streams = 0
  while 1:
    if ts_packet_count >= ts_packet_count_limit:
      break
    if is_bdav:
      if len(prefix) != 4:
        prefix += fread(4 - len(prefix))
        if len(prefix) < 4:
          if prefix:
            eof_msg = 'EOF in mpeg-ts packet header.'
          else:
            eof_msg = 'EOF in mpeg-ts bdav stream.'
          break
      prefix = ''
    data = prefix + fread(188 - len(prefix))
    prefix = ''
    if data:
      ts_packet_count += 1
    if len(data) < 188:
      if data:
        eof_msg = 'EOF in mpeg-ts packet.'
      else:
        eof_msg = 'EOF in mpeg-ts stream.'
      break
    if data[0] != '\x47':
      raise ValueError('Bad sync byte in mpeg-ts packet: 0x%02x' % ord(data[0]))
    if first_few_packets is not None and ts_packet_count <= ts_packet_first_limit:
      first_few_packets.append(data)
      if not is_mpeg_ts(''.join(first_few_packets)):
        raise ValueError('Bad mpeg-ts header until packet %d.' % ts_packet_count)
      if ts_packet_count == ts_packet_first_limit:
        first_few_packets = None  # Save memory.
        info['format'] = 'mpeg-ts'
    h, = struct.unpack('>L', data[:4])
    tei, pusi, tp = (h >> 23) & 1, (h >> 22) & 1, (h >> 21) & 1
    pid = (h >> 8) & 0x1fff  # Packet id.
    tsc, afc, cc = (h >> 6) & 3, (h >> 4) & 3, h & 15
    #print (pusi, cc, 'pid=0x%x' % pid, tei, tp, tsc, afc)
    if tei:  # Ignore packet with errors.
      continue
    if pid == 0x1fff:  # Ignore null packet.
      continue
    if tsc:
      raise ValueError('Unexpected scrambled mpeg-ts packet.')
    if pid in cc_by_pid:
      if cc_by_pid[pid] != cc:
        raise ValueError('Bad mpeg-ts cc: pid=0x%x expected=%d got=%d' %
                         (pid, cc_by_pid[pid], cc))
    elif cc not in (0, 1):
      raise ValueError('Bad mpeg-ts first cc: pid=0x%x got=%d' % (pid, cc))
    cc_by_pid[pid] = (cc + (afc & 1)) & 15
    if pusi:  # New payload packet starts in this ts packet.
      ts_pusi_count += 1
    if afc == 3:
      # End of the adaptation field is stuffed with '\xff' just at the end
      # of the payload unit (PES packet).
      payload_ofs = 5 + ord(data[4])
    elif afc == 1:
      payload_ofs = 4
    elif afc == 2:
      continue  # No payload.
    else:
      raise ValueError('Invalid afc value 0.')
    if len(data) < payload_ofs:
      raise ValueError('mpeg-ts payload too short.')
    ts_payload_count += 1
    #print 'packet pusi=%d pid=0x%x size=%d' % (pusi, pid, len(data) - payload_ofs)
    if pid == 0:
      if not programs and (pusi or buffered_pat_data) and len(data) > payload_ofs:
        if pusi:
          del buffered_pat_data[:]
          payload = buffer(data, payload_ofs)
        else:
          buffered_pat_data.append(data[payload_ofs:])
          payload = ''.join(buffered_pat_data)
          if len(payload) > 1200:
            raise ValueError('mpeg-ts pat payload too long.')
        try:
          programs.update(parse_mpeg_ts_pat(payload))
        except ValueError, e:
          if not str(e).startswith('EOF '):
            raise
          if not buffered_pat_data:
            buffered_pat_data.append(payload[:])
        payload = None  # Save memory.
        if programs:
          for pmt_pid in programs:
            buffered_pmt_data_by_pid[pmt_pid] = []
    elif pid in programs:
      if programs[pid] > 0 and (pusi or buffered_pmt_data_by_pid[pid]) and len(data) > payload_ofs:
        buffered_data = buffered_pmt_data_by_pid[pid]
        if pusi:
          del buffered_data[:]
          payload = buffer(data, payload_ofs)
        else:
          buffered_data.append(data[payload_ofs:])
          payload = ''.join(buffered_data)
          if len(payload) > 1800:
            raise ValueError('mpeg-ts pmt payload too long.')
        try:
          parsed_pmt = parse_mpeg_ts_pmt(payload, programs[pid])
        except ValueError, e:
          if not str(e).startswith('EOF '):
            raise
          if not buffered_data:
            buffered_data.append(payload[:])
          parsed_pmt = None
        payload = None  # Save memory.
        if parsed_pmt:
          info['format'] = 'mpeg-ts'
          for es_pid, stream_type in parsed_pmt:
            if es_pid in es_streams:
              raise ValueError('Duplicate mpeg-ts pmt es_pid: 0x%x' % es_pid)
            if es_pid in programs:
              raise ValueError('mpeg-ts pmg es_pid is also a pmt_pid: 0x%x' % es_pid)
            track_info = get_mpeg_ts_es_track_info('', stream_type)
            if track_info is not None:  # Recognized audio or video es stream.
              es_streams_by_type[track_info['type']] += 1
              es_streams[es_pid] = [stream_type, track_info, None, []]
              ts_packet_count_limit += 1000
              expected_es_streams += 1
          programs[pid] = -1
          parsed_pmt = None  # Save memory.
    elif pid in es_streams:
      es_stream = es_streams[pid]
      if pusi:
        es_payloads_by_type[es_stream[1]['type']] += 1
      if es_stream[2] is None and (pusi or es_stream[3]) and len(data) > payload_ofs:
        buffered_data = es_stream[3]
        if pusi:
          del buffered_data[:]
          payload = buffer(data, payload_ofs)
        else:
          buffered_data.append(data[payload_ofs:])
          payload = ''.join(buffered_data)
        track_info = False
        try:
          track_info = get_mpeg_ts_pes_track_info(payload[:], es_stream[0])
        except ValueError, e:
          if str(e).startswith('EOF ') and len(payload) <= 1000:
            if not buffered_data:
              buffered_data.append(payload[:])
          else:
            track_info = e
        payload = None  # Save memory.
        assert track_info is not None, (
            'Unexpected unknown stream_type: 0x%02x' % stream_type)
        if track_info:
          es_stream[2] = track_info
          type_str = es_stream[1]['type']
          if isinstance(track_info, Exception):
            info['tracks'].append(es_stream[1])  # Fallback track_info.
          else:
            info['tracks'].append(track_info)
          expected_es_streams -= 1
          if not expected_es_streams:
            break  # Stop scanning when all es streams have been found.
    if ((not programs and ts_payload_count >= 3000) or
        (not es_streams and ts_payload_count >= 3500)):
      break
  if (first_few_packets is not None and
      not is_mpeg_ts(''.join(first_few_packets))):
    raise ValueError('Bad mpeg-ts header.')
  info['hdr_ts_packet_count'] = ts_packet_count
  info['hdr_ts_payload_count'] = ts_payload_count
  info['hdr_ts_pusi_count'] = ts_pusi_count
  info['hdr_vstreams'] = es_streams_by_type['video']
  info['hdr_astreams'] = es_streams_by_type['audio']
  info['hdr_vframes'] = es_payloads_by_type['video']
  info['hdr_aframes'] = es_payloads_by_type['audio']
  if not programs:
    info['format'] = 'mpeg-ts'
    raise ValueError('Missing mpeg-ts pat payload.')
  if not es_streams:
    info['format'] = 'mpeg-ts'
    raise ValueError('Missing mpeg-ts pmt with streams.')
  if expected_es_streams:
    raise ValueError('Missing some mpeg-ts pes payloads (tracks).')
  else:
    assert not eof_msg, 'mpeg-ts EOF reached after all pes payloads were detected.'
  errors = ['Error for stream_type=0x%02x fallback_track_info=%r: %s' % (es_stream[0], es_stream[1], es_stream[2])
            for es_stream in es_streams.itervalues() if isinstance(es_stream[2], Exception)]
  if errors:
    raise ValueError('Bad mpeg-ts pes payloads: ' + '; '.join(errors))
  if eof_msg:
    raise ValueError(eof_msg)


# ---


def detect_id3v2_audio_format(header):
  # 4 bytes are available in header.
  if header.startswith('fLaC'):
    return analyze_flac
  elif header.startswith('MAC '):
    return analyze_ape
  elif is_mpeg_adts(header):
    return analyze_mpeg_adts
  else:
    return None


def analyze_id3v2(fread, info, fskip, format='id3v2', fclass='audio',
                  spec=(0, 'ID3', 10, lambda header: (len(header) >= 10 and ord(header[3]) < 10 and (ord(header[5]) & 7) == 0 and ord(header[6]) >> 7 == 0 and ord(header[7]) >> 7 == 0 and ord(header[8]) >> 7 == 0 and ord(header[9]) >> 7 == 0, 100))):
  # Just reads the ID3v2 header with fread and fskip.
  # https://en.wikipedia.org/wiki/ID3
  # http://id3.org/id3v2.3.0
  # ID3v1 is at the end of the file, so we don't care.
  header = fread(10)
  while 1:
    if len(header) < 10:
      raise ValueError('Too short for id3v2.')
    if not header.startswith('ID3'):
      raise ValueError('id3v2 signature not found.')
    version = '2.%d.%d' % (ord(header[3]), ord(header[4]))
    if ord(header[3]) > 9:
      raise ValueError('id3v2 version too large: %d' % version)
    if ord(header[5]) & 7:
      raise ValueError('Unexpected id3v2 flags: 0x%x' % ord(header[5]))
    if ord(header[6]) >> 7 or ord(header[7]) >> 7 or ord(header[8]) >> 7 or ord(header[9]) >> 7:
      raise ValueError('Invalid id3v2 size bits.')
    size = ord(header[6]) << 21 | ord(header[7]) << 14 | ord(header[8]) << 7 | ord(header[9])
    info.setdefault('format', 'id3v2')
    info.setdefault('id3_version', version)
    if size >= 10:
      # Some files incorrectly have `size - 10' instead of size.
      if not fskip(size - 10):
        raise ValueError('EOF in id3v2 data, shorter than %d.' % (size - 10))
      header = fread(4)
      analyze_func = detect_id3v2_audio_format(header)
      if analyze_func:
        return analyze_func(fread, info, fskip, header)
      size = 10 - len(header)
    if not fskip(size):
      raise ValueError('EOF in id3v2 data, shorter than %d.' % size)
    header = fread(4)
    if not header.startswith('ID3'):
      break
    header += fread(10 - len(header))  # Another ID3 tag found.
  if len(header) == 4 and header.startswith('\xff\0\0\0'):
    header = header[1:] + fread(1)  # Skip \xff present in some broken MP3s.
  c = 0
  while 1:  # Skip some \0 bytes.
    if not header.startswith('\0') or len(header) != 4 or c >= 4096:
      break
    c += 1
    if header == '\0\0\0\0':
      header = ''
    elif header.startswith('\0\0\0'):
      header = header[3:]
    elif header.startswith('\0\0'):
      header = header[2:]
    elif header.startswith('\0'):
      header = header[1:]
    c += 4 - len(header)
    header += fread(4 - len(header))
  analyze_func = detect_id3v2_audio_format(header)
  if not analyze_func:
    raise ValueError('Unknown signature after id3v2 header.')
  return analyze_func(fread, info, fskip, header=header)


# --- Image file formats.


def is_animated_gif(fread, header='', do_read_entire_file=False):
  """Returns bool indicating whether f contains an animaged GIF.

  If it's a GIF, sometimes reads the entire file (or at least the 1st frame).

  Args:
    f: An object supporting the .read(size) method. Should be seeked to the
        beginning of the file.
    do_read_entire_file: If true, then read the entire file, even if we know
        that it's an animated GIF.
  Returns:
    bool indicating whether the GIF file f contains an animaged GIF.
  Raises:
    ValueError: If not a GIF file or there is a syntax error in the GIF file.
    IOError: If raised by fread(size).
  """

  def read_all(size):
    data = fread(size)
    if len(data) != size:
      raise ValueError(
          'Short read in GIF: wanted=%d got=%d' % (size, len(data)))
    return data

  if len(header) < 13:
    header += fread(13 - len(header))
  if len(header) < 10 or not (
      header.startswith('GIF87a') or header.startswith('GIF89a')):
    raise ValueError('Not a GIF file.')
  if len(header) < 13:
    return False
  pb = ord(header[10])
  if pb & 128:  # Global Color Table present.
    read_all(6 << (pb & 7))  # Skip the Global Color Table.
  frame_count = 0
  # These fields are related to animated GIFs:
  #
  # * The Netscape Looping Extension (b == 0xff, ext_id == 'NETSCAPE2.0',
  #   ext_data[0] == '\1') contains the number of repetitions (can be
  #   infinite).
  # * The AnimExts Looping Application Extension (b == 0xff, ext_id =
  #   'ANIMEXTS1.0', ext_data[0] == '\1') is identical to the Netscape
  #   Looping Extension, it also contains the number of repetitions.
  # * The Graphics Control Extension (b == 0xf9) contains the delay time
  #   between animation frames.
  #
  # However, we ignore these fields, because even if they specify values, the
  # GIF is still not animated unless it has more than 1 frame.
  while 1:
    b = ord(read_all(1))
    if b == 0x3b:  # End of file.
      break
    elif b == 0x21:  # Extension introducer.
      b = ord(read_all(1))
      if b == 0xff:  # Application extension.
        ext_id_size = ord(read_all(1))
        ext_id = read_all(ext_id_size)
        ext_data_size = ord(read_all(1))
        ext_data = read_all(ext_data_size)
        data_size = ord(read_all(1))
        while data_size:
          read_all(data_size)
          data_size = ord(read_all(1))
      else:
        # https://www.w3.org/Graphics/GIF/spec-gif89a.txt
        # 0x01: plain text extension
        # 0xf9: graphic control extension
        # 0xfe: comment extension
        # 0xff: application extension (handled above)
        if b not in (0x01, 0xf9, 0xfe):
          raise ValueError('Unknown GIF extension type: 0x%02x' % b)
        ext_data_size = ord(read_all(1))
        if b == 0xf9:  # Graphic Control extension.
          if ext_data_size != 4:
            raise ValueError(
                'Bad ext_data_size for GIF GCE: %d' % ext_data_size)
        ext_data = read_all(ext_data_size)
        data_size = ord(read_all(1))
        if b == 0xf9:
          if data_size != 0:
            raise ValueError('Bad data_size for GIF GCE: %d' % data_size)
        while data_size:
          read_all(data_size)
          data_size = ord(read_all(1))
    elif b == 0x2c:  # Image Descriptor.
      frame_count += 1
      if frame_count > 1 and not do_read_entire_file:
        return True
      read_all(8)
      pb = ord(read_all(1))
      if pb & 128:  # Local Color Table present.
        read_all(6 << (pb & 7))  # Skip the Local Color Table.
      read_all(1)  # Skip LZW minimum code size.
      data_size = ord(read_all(1))
      while data_size:
        read_all(data_size)
        data_size = ord(read_all(1))
    else:
      raise ValueError('Unknown GIF block type: 0x%02x' % b)
  if frame_count <= 0:
    raise ValueError('No frames in GIF file.')
  return frame_count > 1


def analyze_gif(fread, info, fskip, format='gif', extra_formats=('agif',), fclass='image',
                spec=(0, 'GIF8', 4, ('7a', '9a'))):
  # Still short enough for is_animated_gif.
  header = fread(10)
  if len(header) < 6:
    raise ValueError('Too short for gif.')
  if not header.startswith('GIF87a') and not header.startswith('GIF89a'):
    raise ValueError('gif signature not found.')
  info['format'] = 'gif'
  info['codec'] = 'lzw'
  if len(header) >= 10:
    info['width'], info['height'] = struct.unpack('<HH', header[6 : 10])
    if is_animated_gif(fread, header):  # This may read the entire input.
      info['format'] = 'agif'


def analyze_brunsli(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/JPEG_XL
  # Brunsli is lossless-reencoded JPEG, with an option to convert it back to
  # the original JPEG file.
  def read_all(size):
    data = fread(size)
    if len(data) != size:
      raise ValueError(
          'Short read in brunsli: wanted=%d got=%d' % (size, len(data)))
    return data

  def read_base128():
    shift, result, c = 0, 0, 0
    while 1:
      b = fread(1)
      if not b:
        raise ValueError('Short read in base128.')
      c += 1
      if shift > 57:
        raise ValueError('base128 value too large.')
      b = ord(b)
      result |= (b & 0x7f) << shift
      if not b & 0x80:
        return result, c
      shift += 7

  data = fread(7)
  if len(data) < 6:
    raise ValueError('Too short for brunsli.')
  if not data.startswith('\x0a\x04B\xd2\xd5N'):
    raise ValueError('brunsli signature not found.')
  info['format'], info['subformat'], info['codec'] = 'jpegxl-brunsli', 'brunsli', 'brunsli'
  if len(data) < 7 or data[6] != '\x12':
    return

  header_remaining, _ = read_base128()
  width = height = None
  while header_remaining:
    if header_remaining < 0:
      raise ValueError('brunsli header spilled over.')
    marker = ord(read_all(1))
    header_remaining -= 1
    if marker & 0x80 or marker & 0x5 or marker <= 2:
      raise ValueError('Invalid marker.')
    if marker == 0x8:
      if width is not None:
        raise ValueError('Multiple width.')
      width, c = read_base128()
      header_remaining -= c
    elif marker == 0x10:
      if height is not None:
        raise ValueError('Multiple height.')
      height, c = read_base128()
      header_remaining -= c
    else:
      val, c = read_base128()
      header_remaining -= c
      if (marker & 7) == 2:
        read_all(val)
        header_remaining -= val
  if width is not None and height is not None:
    info['width'], info['height'] = width, height
  else:
    raise ValueError('Dimensions not found in brunsli.')


def analyze_jpegxl(fread, info, fskip):
  # https://arxiv.org/pdf/1908.03565.pdf
  # cjpegxl.exe and djpegxl.exe:
  #   https://mega.nz/#!opJwGaaK!9PvdLVknqZPgVpMJ9LbEG5_POgEAaDZTtWnx2jYtsz8
  # web encoder: http://libwebpjs.appspot.com/jpegxl/

  header = fread(2)
  if len(header) < 2:
    raise ValueError('Too short for jpegxl.')
  if not header.startswith('\xff\x0a'):
    raise ValueError('jpegxl signature not found.')
  info['format'] = info['subformat'] = info['codec'] = 'jpegxl'
  bits = yield_bits_lsbfirst(fread)

  def read_1():
    for b in bits:
      return b
    raise ValueError('EOF in jpegxl.')

  def read_u(n):
    result = i = 0
    if n > 0:
      for b in bits:
        result |= b << i
        i += 1
        if i == n:
          break
      if i != n:
        raise ValueError('EOF in jpegxl.')
    return result

  def read_u32(bs):
    return read_u(bs[read_u(2)])

  is_small = read_1()  # Start of SizeHeader.
  if is_small:
    height = (read_u(5) + 1) << 3
  else:
    height = read_u32((9, 13, 18, 30)) + 1
  ratio = read_u(3)
  if ratio:
    width = height * (1, 1, 12, 4, 3, 16, 5, 2)[ratio] // (1, 1, 10, 3, 2, 9, 4, 1)[ratio]
  elif is_small:
    width = (read_u(5) + 1) << 3
  else:
    width = read_u32((9, 13, 18, 30)) + 1
  info['width'], info['height'] = width, height


def yield_early_eof(it):
  is_empty = 1  # True.
  for item in it:
    is_empty = 0
    yield item
  if is_empty:
    raise EOFError


def analyze_pik(fread, info, fskip):
  # subformat=pik1: http://libwebpjs.hohenlimburg.org/pik-in-javascript/
  # subformat=pik1: http://libwebpjs.hohenlimburg.org/pik-in-javascript/images/2.pik
  # subformat=pik1: https://github.com/google/pik/blob/52f2d45cc8e35e45278da54615bb8b11b5066f16/header.h#L62-L65
  # subformat=pik1: https://github.com/google/pik/blob/52f2d45cc8e35e45278da54615bb8b11b5066f16/header.cc#L232
  # subformat=pik2: https://github.com/google/pik/blob/b4866ff9332fe13b7f7f70e55de02459f5fbb3b3/pik/headers.h#L366-L372
  header = fread(4)
  if len(header) < 4:
    raise ValueError('Too short for pik.')
  if header == 'P\xccK\x0a':
    info['subformat'] = 'pik1'
    bits = yield_early_eof(yield_bits_msbfirst(fread))
    def read_u(n):
      result = i = 0
      if n > 0:
        for b in bits:
          result = result << 1 | b
          i += 1
          if i == n:
            break
        if i != n:
          raise ValueError('EOF in pik.')
      return result
    def read_dimen():
      return read_u((9, 11, 13, 32)[read_u(2)])
  elif header == '\xd7LM\x0a':
    info['subformat'] = 'pik2'
    bits = yield_early_eof(yield_bits_lsbfirst(fread))
    def read_u(n):
      result = i = 0
      if n > 0:
        for b in bits:
          result |= b << i
          i += 1
          if i == n:
            break
        if i != n:
          raise ValueError('EOF in pik.')
      return result
    def read_dimen():
      return read_u((9, 11, 13, 32)[read_u(2)]) + 1
  else:
    raise ValueError('pik signature not found.')
  info['format'] = info['codec'] = 'pik'
  try:
    width = read_dimen()
    height = read_dimen()
  except EOFError:
    return
  info['width'], info['height'] = width, height


def analyze_qtif(fread, info, fskip):
  # https://developer.apple.com/library/archive/documentation/QuickTime/QTFF/QTFFAppenA/QTFFAppenA.html
  # http://justsolve.archiveteam.org/wiki/QTIF
  data = fread(8)
  if len(data) < 8:
    raise ValueError('Too short for qtif atom.')
  size, xtype = struct.unpack('>L4s', data)
  if xtype not in ('idsc', 'iicc', 'idat'):
    raise ValueError('qtif signature not found.')
  if size >> (25, 8)[xtype == 'idsc']:
    raise ValueError('qtif atom too large.')
  info['format'] = 'qtif'
  had_xtypes = set()
  while xtype != 'idsc':
    if xtype in had_xtypes:
      raise ValueError('Duplicate qtif idsc atom: %s' % xtype)
    if size >> 25:
      raise ValueError('qtif %s atom too large.' % xtype)
    if size < 8:
      raise ValueError('qtif atom too small.')
    if not had_xtypes and size > 8:
      if not fread(1):
        return
      size -= 1
    if not fskip(size - 8):
      raise ValueError('EOF in qtif %s atom.' % xtype)
    data = fread(8)
    if not data and not had_xtypes:
      return
    if len(data) < 8:
      raise ValueError('Too short for qtif atom.')
    had_xtypes.add(xtype)
    size, xtype = struct.unpack('>L4s', data)
    if xtype not in ('idsc', 'iicc', 'idat'):
      raise ValueError('Bad qtif atom: %r' % xtype)
  if size >> 8:
    raise ValueError('qtif idsc atom too large.')
  if size < 36 + 8:
    raise ValueError('qtif idsc atom too small.')
  data = fread(36)
  if not data and not had_xtypes:
    return
  if len(data) < 36:
    raise ValueError('EOF in qtif idsc atom.')
  (size2, codec, r1, r2, version, vendor, tq, sq, width, height,
  ) = struct.unpack('>L4sLLL4sLLHH', data)
  if size2 != size - 8:
    raise ValueError('qtif idsc atom size mismatch.')
  codec = codec.strip().lower()
  info['codec'] = MP4_VIDEO_CODECS.get(codec, codec)
  info['width'], info['height'] = width, height
  if r1 or r2 or tq:
    raise ValueError('Bad qtif idsc reserved 0s.')
  # Typically: version in (0, 0x101).
  # Typically: vendor = 'appl'.
  # Typically: sq = 0x200.


PSP_CODECS = {
    0: 'uncompressed',
    1: 'rle',
    2: 'lz77',
    3: 'jpeg',  # Typically not allowed in the header (PSP_IMAGE_BLOCK).
}


def analyze_psp(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/PaintShop_Pro
  # ftp://ftp.corel.com/pub/documentation/PSP/PSP%20File%20Format%20Specification%207.pdf
  data = fread(69)
  if len(data) < 32:
    raise ValueError('Too short for psp.')
  if not data.startswith('Paint Shop Pro Image File\n\x1a\0\0\0\0\0'):
    raise ValueError('psp signature not found.')
  info['format'] = 'psp'
  if len(data) < 58:
    return
  major_version, minor_version, header_id, block_id, block_size1, block_size2, width, height = struct.unpack('<32xHHLHLLLL', data[:58])
  if header_id != 0x4b427e:
    raise ValueError('Bad psp header_id.')
  if block_id:
    raise ValueError('Bad psp block_id.')
  if block_size1 != block_size2:
    raise ValueError('psp block_size mismatch.')
  if block_size1 < 8:
    raise ValueError('psp block too short.')
  info['width'], info['height'] = width, height
  if not 1 <= major_version <= 8:
    raise ValueError('Bad psp major_version: %d' % major_version)
  if not 0 <= minor_version <= 20:  # Typically 0.
    raise ValueError('Bad psp minor_version: %d' % minor_version)
  if len(data) >= 69:
    codec, = struct.unpack('<H', data[67 : 69])
    info['codec'] = PSP_CODECS.get(codec, str(codec))


def analyze_ras(fread, info, fskip):
  # https://www.fileformat.info/format/sunraster/egff.htm
  # https://en.wikipedia.org/wiki/Sun_Raster
  # http://fileformats.archiveteam.org/wiki/Sun_Raster
  data = fread(24)
  if len(data) < 4:
    raise ValueError('Too short for ras.')
  if not data.startswith('\x59\xa6\x6a\x95'):
    raise ValueError('ras signature not found.')
  info['format'] = 'ras'
  if len(data) >= 24:
    info['width'], info['height'], itype = struct.unpack('>4xLL8xL', data)
    if itype < 3:
      info['codec'] = ('uncompressed', 'rle')[itype == 2]


GEM_NOSIG_HEADERS = (
    '\0\1\0\x08\0\1\0\2', '\0\1\0\x08\0\2\0\2', '\0\1\0\x08\0\4\0\2', '\0\1\0\x08\0\x08\0\2', '\0\1\0\x09\0\1\0\2', '\0\1\0\x09\0\2\0\2', '\0\1\0\x09\0\4\0\2', '\0\1\0\x09\0\x08\0\2',
    '\0\1\0\x0a\0\1\0\2',    # NOSIG, 2-color palette.
    '\0\1\0\x0c\0\2\0\2',    # NOSIG, 4-color palette.
    '\0\1\0\x18\0\4\0\2',    # NOSIG, 16-color palette.
    '\0\1\1\x08\0\x08\0\2',  # NOSIG, 256-color palette.
)

GEM_HYPERPAINT_HEADERS = (
    '\0\1\0\x0b\0\1\0\2',    # HYPERPAINT, 2-color palette.
    '\0\1\0\x0d\0\2\0\2',    # HYPERPAINT, 4-color palette.
    '\0\1\0\x19\0\4\0\2',    # HYPERPAINT, 16-color palette.
    '\0\1\1\x09\0\x08\0\2',  # HYPERPAINT, 256-color palette.
)

GEM_STTT_HEADERS = (
    '\0\1\0\x0d\0\1\0\1',    # STTT, 2-color palette.
    '\0\1\0\x0f\0\2\0\1',    # STTT, 4-color palette.
    '\0\1\0\x1b\0\4\0\1',    # STTT, 16-color palette.
    '\0\1\1\x0b\0\x08\0\1',  # STTT, 256-color palette.
)

GEM_XIMG_HEADERS = (
    '\0\2\0\x11\0\1\0\1',    # XIMG, 2-color palette.
    '\0\2\0\x17\0\2\0\1',    # XIMG, 4-color palette.
    '\0\2\0\x3b\0\4\0\1',    # XIMG, 16-color palette.
    '\0\2\3\x0b\0\x08\0\1',  # XIMG, 256-color palette.
)


def analyze_gem(fread, info, fskip):
  # https://www.seasip.info/Gem/ff_img.html
  # https://www.fileformat.info/format/gemraster/egff.htm
  # http://fileformats.archiveteam.org/wiki/GEM_Raster
  # http://www.fileformat.info/format/gemraster/spec/20e311cc16f844fda91beb539d62c46c/view.htm
  # http://www.atari-wiki.com/index.php/IMG_file
  data = fread(22)
  if len(data) < 8:
    raise ValueError('Too short for gem.')
  if data[:8] in GEM_NOSIG_HEADERS:
    info['subformat'] = 'nosig'
  elif data[:8] in GEM_HYPERPAINT_HEADERS and len(data) >= 18 and data[16 : 18] == '\0\x80':
    info['subformat'] = 'hyperpaint'
  elif data[:8] in GEM_STTT_HEADERS and len(data) >= 22 and data[16 : 22] == 'STTT\0\x10':
    info['subformat'] = 'sttt'
  elif data[:8] in GEM_XIMG_HEADERS and len(data) >= 22 and data[16 : 22] == 'XIMG\0\0':
    info['subformat'] = 'ximg'
  else:
    raise ValueError('gem signature not found.')
  info['format'], info['codec'] = 'gem', 'rle'
  if len(data) >= 16:
    info['width'], info['height'] = struct.unpack('>HH', data[12 : 16])


def analyze_pcpaint_pic(fread, info, fskip):
  # http://www.fileformat.info/format/pictor/egff.htm
  # http://netghost.narod.ru/gff/vendspec/pictor/pictor.txt
  # http://fileformats.archiveteam.org/wiki/PCPaint_PIC
  data = fread(17)
  if len(data) < 14:
    raise ValueError('Too short for pcpaint-pic.')
  if not (data.startswith('\x34\x12') and data[6 : 10] == '\0\0\0\0' and data[11] in '\xff123' and data[13] in '\0\1\2\3\4'):
    raise ValueError('pcpaint-pic signature not found.')
  info['format'], info['codec'] = 'pcpaint-pic', 'rle'
  info['width'], info['height'] = struct.unpack('<HH', data[2 : 6])
  if len(data) >= 17:
    esize, = struct.unpack('<H', data[15 : 17])
    if not fskip(esize):
      raise ValueError('EOF in pcpaint-pic palette.')
    data = fread(2)
    if len(data) < 2:
      raise ValueError('EOF if pcpaint-pic block count.')
    if data == '\0\0':
      info['codec'] = 'uncompressed'


def analyze_xwd(fread, info, fskip, format='xwd', fclass='image',
                spec=((0, '\0\0', 2, ('\0', '\1'), 4, '\0\0\0\6', 8, '\0\0\0', 11, tuple(chr(c) for c in xrange(17)), 12, '\0\0\0', 15, ('\1', '\2', '\3', '\4', '\5'), 16, '\0\0\0', 19, ('\0', '\1')),
                      (0, '\0\0', 2, ('\0', '\1'), 4, '\0\0\0\7', 8, '\0\0\0', 11, ('\0', '\1', '\2'), 12, '\0\0\0', 15, tuple(chr(c) for c in xrange(1, 33))),
                      (1, ('\0', '\1'), 2, '\0\0', 4, '\6\0\0\0', 8, tuple(chr(c) for c in xrange(17)), 9, '\0\0\0', 12, ('\1', '\2', '\3', '\4', '\5'), 13, '\0\0\0', 16, ('\0', '\1'), 17, '\0\0\0'),
                      (1, ('\0', '\1'), 2, '\0\0', 4, '\7\0\0\0', 8, ('\0', '\1', '\2'), 9, '\0\0\0', 12, tuple(chr(c) for c in xrange(1, 33)), 13, '\0\0\0'))):
  # https://www.fileformat.info/format/xwd/egff.htm
  # http://fileformats.archiveteam.org/wiki/XWD
  # https://en.wikipedia.org/wiki/Xwd
  header = fread(28)
  if len(header) < 16:
    raise ValueError('Too short for xwd.')
  fmt = '<>'[header[4 : 7] == '\0\0\0']  # Use file_version.
  header_size, file_version = struct.unpack(fmt + 'LL', header[:8])
  if not 28 <= header_size <= 512:
    raise ValueError('Bad xwd header size: %d' % header_size)
  if file_version == 6:
    info['format'], info['subformat'] = 'xwd', 'x10'
    if len(header) < 20:
      raise ValueError('Too short for xwd x10.')
    display_type, display_planes, pixmap_format = struct.unpack(fmt + '3L', header[8 : 20])
    if display_type > 16:
      raise ValueError('Bad xwd display type: %d' % display_type)
    if not 1 <= display_planes <= 5:  # Typically 1 or 3.
      raise ValueError('Bad xwd display planes: %d' % display_planes)
    if pixmap_format > 1:
      raise ValueError('Bad xwd pixmap format: %d' % pixmap_format)
    if len(header) < 28:
      return
    width, height = struct.unpack(fmt + 'LL', header[20 : 28])
  elif file_version == 7:
    info['format'], info['subformat'] = 'xwd', 'x11'
    pixmap_format, pixmap_depth = struct.unpack(fmt + '2L', header[8 : 16])
    if not 1 <= pixmap_depth <= 32:
      raise ValueError('Bad xwd pixmap depth: %d' % pixmap_depth)
    if pixmap_format > 2:
      raise ValueError('Bad xwd pixmap format: %d' % pixmap_format)
    if len(header) < 28:
      return
    width, height = struct.unpack(fmt + 'LL', header[16 : 24])
  else:
    raise ValueError('Bad xwd file version: %d' % file_version)
  info['width'], info['height'] = width, height


def count_is_sun_icon(header):
  if not header.startswith('/*') or header[2 : 3] not in ' \t\r\n':
    return False
  i = 3 + (header[2 : 4] == '\r\n')
  if header[i : i + 17] != 'Format_version=1,':
    return False
  return (i + 17) * 100


def analyze_sun_icon(fread, info, fskip, format='sun-icon', fclass='image',
                     spec=(0, '/*', 2, (' ', '\t', '\r', '\n'), 21, lambda header: adjust_confidence(300, count_is_sun_icon(header)))):  # '/* Format_version=1,'.
  # https://www.fileformat.info/format/sunicon/egff.htm
  data = fread(4)
  if data.startswith('/*') and data[2 : 3] in ' \t\r\n':
    if data == '/*\r\n':
      data = '/* '
    else:
      data = '/* ' + data[-1]
    data += fread(20 - len(data))
  if len(data) < 4:
    raise ValueError('Too short for sun-icon.')
  if data != '/* Format_version=1,':
    raise ValueError('sun-icon signature not found.')
  info['format'] = 'sun-icon'
  data = fread(256)
  i = data.find('*/')
  if i >= 0:
    items = data.split(',')
  else:
    data = data[:data.rfind(',')]
  dimens = {}
  for item in data.split(','):
    item = item.strip()
    if item.startswith('Width=') or item.startswith('Height='):
      key, value = item.split('=', 1)
      key = key.lower()
      try:
        dimens[key] = int(value)
      except ValueError:
        raise ValueError('Bad sun-icon %s value: %r' % (key, value))
  if 'width' in dimens and 'height' in dimens:
    info['width'], info['height'] = dimens['width'], dimens['height']


def analyze_wav(fread, info, fskip, format='wav', fclass='audio', ext='.wav',
                spec=(0, 'RIFF', 8, ('WAVE', 'RMP3'), 12, ('fmt ', 'bext', 'JUNK'), 20, lambda header: (len(header) < 20 or header[12 : 16] != 'fmt ' or (16 <= ord(header[16]) <= 80 and header[17 : 20] == '\0\0\0'), 315 * (header[12 : 16] == 'fmt ') or 1))):
  # 'RMP3' as .rmp extension, 'WAVE' has .wav extension. 'WAVE' can also have codec=mp3.
  header = fread(36)
  if len(header) < 16:
    raise ValueError('Too short for wav.')
  if not header.startswith('RIFF') or header[8 : 12] not in ('WAVE', 'RMP3'):
    raise ValueError('wav signature not found.')
  info['format'] = 'wav'
  info['tracks'] = []
  while header[12 : 16] in ('bext', 'JUNK'):  # Skip 'bext' and 'JUNK' chunk(s).
    chunk_size, = struct.unpack('<L', header[16 : 20])
    chunk_size += chunk_size & 1
    i = chunk_size - (len(header) - 20)
    if i < 0:
      header = header[:12] + header[20 + chunk_size:]
    else:
      header = header[:12]
      if not fskip(i):
        raise ValueError('EOF in wav bext chunk.')
    if len(header) < 36:
      header += fread(36 - len(header))
      if len(header) < 36:
        return  #raise ValueError('EOF after bext chunk.')
  if header[12 : 16] != 'fmt ':
    raise ValueError('wav fmt chunk missing.')
  fmt_size, wave_format, channel_count, sample_rate, _, _, sample_size = (
      struct.unpack('<LHHLLHH', header[16 : 36]))
  # Observation: 234 x fmt_size=16, 10 x fmt_size=18, 2 x fmt_size=50, 1 fmt_size=30.
  if not 16 <= fmt_size <= 80:
    raise ValueError('Bad wav fmt_size: %d' % fmt_size)
  info['tracks'].append({
      'type': 'audio',
      'codec': WINDOWS_AUDIO_FORMATS.get(
          wave_format, '0x%x' % wave_format),
      'channel_count': channel_count,
      'sample_rate': sample_rate,
      # With 'codec': 'mp3', sample_size is usually 0.
      'sample_size': sample_size or 16,
  })



PE_ARCHITECTURES = {
    0x14c: 'i386',
    0x8664: 'amd64',
    0x1c0: 'arm',
    0x1c4: 'arm-thumb2',
    0xaa64: 'arm64',
    0xebc: 'efi',
    0x200: 'ia64',  # Itanium.
}


def count_is_exe(header):
  if not header.startswith('MZ') or len(header) < 32:
    return 0
  magic, size_lo, size_hi, reloc_count, header_size16 = struct.unpack('<5H', header[:10])
  if size_lo > 512 or (size_hi == 0 and size_lo > 0):  # 512 is valid.
    return 0
  if header_size16 < 2 and not (size_hi == size_lo == header_size16 == 0):
    return 0
  size = (size_lo or 512) + (size_hi << 9) - 512
  pe_ofs = int(len(header) >= 64 and struct.unpack('<L', header[60 : 64])[0])
  if 64 <= pe_ofs <= 8166:  # Probably PE (Win32 etc.), NE (Win16), LE or LX.
    # TODO(pts): Add extra confidence score as below.
    is_lxle = header[pe_ofs : pe_ofs + 8] in ('LE\0\0\0\0\0\0', 'LX\0\0\0\0\0\0')
    is_pe = header[pe_ofs : pe_ofs + 4] == 'PE\0\0'
    is_ne = header[pe_ofs : pe_ofs + 2] == 'NE' and (header[pe_ofs + 2 : pe_ofs + 3] or 'x') in '\1\2\3\4\5\6\7\8'  # Typically linker major version is 5.
    # We only get the extra 400 points if header is long enough. Typically
    # pe_ofs is 64 or 96, so header is long enough.
    if len(header) < pe_ofs + 4 or is_lxle or is_pe or is_ne:
      return (438 + 88 + 400 * is_pe + 800 * is_lxle + 263 * is_ne +
              400 * ((size_lo == 0 and size_hi == 0) or size == pe_ofs))  # Typically `size > pe_ofs', but we give `==' a boost.
  if size_hi == 0:
    return 0
  reloc_ofs, = struct.unpack('<H', header[24 : 26])
  confidence = 201
  if reloc_count == 0:
    confidence += 200
  if reloc_count == 0 and header[24 : 32] == '>TIPPACH':  # wdosx.
    confidence += 800
  else:
    #if size_lo == 0 and size_hi == 0:
    #  confidence += 400
    if reloc_count == 0 and reloc_ofs == 0:
      confidence += 200
    elif 28 <= reloc_ofs < 64:
      confidence += 135
    elif 64 <= reloc_ofs < 512:
      confidence += 88
  return confidence


NE_OS_ARCHS = {
    1: ('os2', '80286'),  # OS/2 1.x.
    2: ('windows', '8086'),  # Windows 1.0--3.x.
    3: ('dos4', '8086'),  # MS-DOS 4.x.
    4: ('win32s', 'i386'),  # Windows for the 80386 (Win32s). 32-bit code. Windows NT 4.0 ... Windows 10 probably can't run them.
    5: ('boss', '8086'),  # Borland Operating System Service. Is it 8086?
}


def parse_lxle_objects(fread, data, ot_count, arch):
  """Parse each object table entry in LX or LE, infer archs."""
  archs = set()
  for _ in xrange(ot_count):
    if len(data) < 24:
      data += fread(24 - len(data))
      if len(data) < 24:
        raise ValueError('EOF in lxle object table entry.')
    vsize, relbase, flags, pm_idx, pm_count, name = struct.unpack('<5L4s', data[:24])
    if flags & 4 and vsize > 0:
      if arch == 'i386':
        # The function called in
        # https://github.com/darkstar/2ine/blob/c9706154479af13ee61b2bca2aa0f5cbc5cac7ba/lx_loader.c#L1841
        # indicates that these objects really contain 16-bit code.
        archs.add(('8086', 'i386')[(flags >> 13) & 1])
      else:
        archs.append(arch)
    data = data[24:]
  return sorted(archs)


LXLE_OSS = {
    1: 'os2',
    #2: 'windows',  # Not observed in the wild, indicates 16-bit Windows.
    #3: 'dos4',  # Not observed in the wild.
    4: 'windows',  # 32-bit Windows .vxd, may also contain some 16-bit code.
}

LXLE_CPU_ARCHS = {
    1: '80286',
    2: 'i386',
    3: 'i386',  # Actually 486.
    4: 'i386',  # Actually Pentium.
    0x20: 'i860',  # N10.
    0x21: 'i860',  # N11.
    0x40: 'mips',  # MIPS I.
    0x41: 'mips',  # MIPS II.
    0x42: 'mips',  # MIPS III.
}

LX_BINARY_TYPES = {
    0: 'executable',
    1: 'shlib',
    3: 'pmlib',  # Protected memory library.
    4: 'physical-driver',
    6: 'virtual-driver',
}


def parse_lxle(fread, info, fskip, pe_ofs, header):
  # Both LX and LE, with diffs: https://www.program-transformation.org/Transform/PcExeFormat
  # http://faydoc.tripod.com/formats/exe-LE.htm
  # http://www.textfiles.com/programming/FORMATS/lxexe.txt
  # https://svn.netlabs.org/repos/odin32/trunk/tools/common/LXexe.h
  if len(header) < pe_ofs + 96:
    header += fread(pe_ofs + 96 - len(header))
    if len(header) < pe_ofs + 20:
      raise ValueError('EOF in lxle header.')
  prefix = header[pe_ofs : pe_ofs + 20]
  # 'LX\1\1' would be big endian, we don't support that.
  if not (prefix.startswith('LE\0\0\0\0\0\0') or prefix.startswith('LX\0\0\0\0\0\0')):
    raise ValueError('lxle signature not found.')
  info['format'], info['endian'] = 'exe', 'little'
  info['subformat'] = ('le', 'lx')[prefix[1] == 'X']
  cpu, osx, module_version, module_flags = struct.unpack('<8xHHLL', prefix)
  if prefix[1] == 'X':
    module_type = (module_flags >> 15) & 7
    info['binary_type'] = LX_BINARY_TYPES.get(module_type, str(module_type))
  else:
    info['binary_type'] = ('executable', 'shlib')[(module_flags >> 15) & 1]
  info['os'] = LXLE_OSS.get(osx, str(osx))
  arch = LXLE_CPU_ARCHS.get(cpu, str(cpu))
  if len(header) >= pe_ofs + 72:
    ot_ofs, ot_count = struct.unpack('<LL', header[pe_ofs + 64 : pe_ofs + 72])
    ot_ofs += pe_ofs
    if ot_ofs > len(header):
      if not fskip(ot_ofs - len(header)):
        raise ValueError('EOF in le object table seek.')
      ot_ofs = len(header)
    info['arch'] = ','.join(parse_lxle_objects(fread, header[ot_ofs:], ot_count, arch)) or 'none'
  else:
    info['arch'] = arch
  if info['binary_type'] == 'shlib' and info['os'] == 'windows' and arch == 'i386' and prefix[1] != 'X':
    info['format'] = 'vxd'  # https://en.wikipedia.org/wiki/VxD
  elif info['binary_type'] in ('executable', 'shlib') and info['os'] == 'os2' and prefix[1] == 'X':
    info['format'] = ('os2exe', 'os2dll')[info['binary_type'] == 'shlib']  # OS/2 2.x.


def is_hxs(header):
  # http://www.russotto.net/chm/itolitlsformat.html
  return (len(header) >= 40 and
          header.startswith('ITOLITLS\1\0\0\0\x28\0\0\0') and
          header[24 : 40] == '\xc1\x07\x90\nv@\xd3\x11\x87\x89\x00\x00\xf8\x10WT')


def analyze_exe(fread, info, fskip, format='exe', fclass='code',
                # 408 (header_size_limit) is arbitrary, but since cups-raster has it, we can also that much.
                spec=((0, 'MZ', 408, lambda header: adjust_confidence(200, count_is_exe(header))),
                      # format='hxs' bare. Usually there is a PE header (analyze_exe) in front of this.
                      (0, 'ITOLITLS\1\0\0\0\x28\0\0\0', 24, '\xc1\x07\x90\nv@\xd3\x11\x87\x89\x00\x00\xf8\x10WT')),
                extra_formats=('dosexe', 'dosxexe', 'dotnetexe', 'dotnetdll', 'pe', 'pe-coff', 'pe-nonexec', 'winexe', 'windll', 'efiexe', 'efidll', 'vxd', 'os2exe', 'os2dll', 'hxs')):
  header = fread(64)
  if is_hxs(header):
    info['format'] = 'hxs'
    return
  if len(header) < 32:
    raise ValueError('Too short for exe.')
  if not header.startswith('MZ'):
    raise ValueError('exe signature not found.')
  pe_ofs = int(len(header) >= 64 and struct.unpack('<L', header[60 : 64])[0])
  # http://www.fysnet.net/exehdr.htm
  # http://www.delorie.com/djgpp/doc/exe/
  magic, size_lo, size_hi, reloc_count, header_size16 = struct.unpack('<5H', header[:10])
  reloc_ofs, = struct.unpack('<H', header[24 : 26])
  reloc_end_ofs = (reloc_count and reloc_ofs + (reloc_count << 2)) or 28
  header_size = header_size16 << 4
  if size_lo > 512 or (size_hi == 0 and size_lo > 0):  # 512 is valid.
    raise ValueError('Bad exe size.')
  if header_size16 < 2 and not (size_hi == size_lo == header_size16 == 0):
    raise ValueError('Bad exe header_size16.')
  size = (size_lo or 512) + (size_hi << 9) - 512
  # 8166 is mostly arbitrary. Typically pe_ofs is 64 or 96.
  # Some dual DOS + Windows programs (e.g. vmm32.vxd) are detected as DOS
  # only, because pe_ofs is too large for hem.
  if 64 <= pe_ofs < 8166 and len(header) < pe_ofs + 55:
    header += fread(pe_ofs + 55 - len(header))
  def is_hx_suffix(header, size):
    header = header[size - 48 : size]  # Matches dpmist32.bin in https://www.japheth.de/HX.html
    return size >= 48 and 'PATH=' in header and 'cannot find loader DPMILD32.EXE$' in header
  def is_hx():
    return reloc_count == 0 and reloc_ofs == 0x40 and header[26 : 32] == '\0\0\0\0\0\0' and size == 512 and is_hx_suffix(header, size)
  if (64 <= pe_ofs <= 8166 and len(header) >= pe_ofs + 40 and
      header[pe_ofs : pe_ofs + 2] == 'NE' and
      header[pe_ofs + 2 : pe_ofs + 3] in '\1\2\3\4\5\6\7\8'):
    # NE (New Executable), usually 16-bit Windows 1.0--3.x.
    # https://wiki.osdev.org/NE
    # https://www.fileformat.info/format/exe/corion-ne.htm
    # print [header[pe_ofs + 2 : pe_ofs + 4]]  # Linker version. Typically: 5.1; 5.60
    info['subformat'], info['endian'] = 'ne', 'little'
    osx = ord(header[pe_ofs + 54])
    flags, = struct.unpack('<H', header[pe_ofs + 12 : pe_ofs + 14])
    if osx in NE_OS_ARCHS:
      info['os'], info['arch'] = NE_OS_ARCHS[osx]
    else:
      info['os'] = str(osx)
    is_shlib = bool(flags & 0x8000)
    info['binary_type'] = ('executable', 'shlib')[is_shlib]
    if osx in (2, 4):
      info['format'] = 'win' + ('exe', 'dll')[is_shlib]
    elif osx == 1:  # OS/2 1.x.
      info['format'] = 'os2' + ('exe', 'dll')[is_shlib]
  elif header[pe_ofs : pe_ofs + 8] == 'LX\0\0\0\0\0\0' and size_hi > 0:
    parse_lxle(fread, info, fskip, pe_ofs, header)
  elif (64 <= pe_ofs <= 8166 and len(header) >= pe_ofs + 24 and
        header[pe_ofs : pe_ofs + 4] == 'PE\0\0'):
    # PE (Portable Executable), usually 32-bit or 64-bit Windows.
    # https://docs.microsoft.com/en-us/windows/win32/debug/pe-format
    info['format'], info['subformat'], info['endian'] = 'pe-coff', 'pe', 'little'
    (machine, section_count, date_time, symbol_table_ofs, symbol_count,
     opthd_size, characteristics,
    ) = struct.unpack('<HHLLLHH', header[pe_ofs + 4 : pe_ofs + 24])
    info['arch'] = PE_ARCHITECTURES.get(machine) or '0x%x' % machine
    if not 24 <= opthd_size <= 255:
      info['format'] = 'pe-coff'
      return
    if len(header) < pe_ofs + 26:
      raise ValueError('EOF in pe magic.')
    magic, = struct.unpack('<H', header[pe_ofs + 24 : pe_ofs + 26])
    info['format'] = 'pe'
    if magic == 0x10b:  # 32-bit.
      info['subformat'], opthd12_size = 'pe32', 96
    elif magic == 0x20b:  # 64-bit.
      info['subformat'], opthd12_size = 'pe32+', 112
    elif magic == 0x107:
      info['subformat'] = info['binary_type'] = 'rom-image'
      return
    else:
      info['binary_type'] = '0x%x' % magic
      return
    if len(header) < pe_ofs + 24 + opthd_size:
      header += fread(pe_ofs + 24 + opthd_size - len(header))
      if len(header) < pe_ofs + 24 + opthd_size:
        raise ValueError('EOF in pe optional header.')
    if characteristics & 2:  # Exectuable.
      if opthd_size < opthd12_size:
        raise ValueError('pe optional header too short.')
      suffix = ('exe', 'dll')[bool(characteristics & 0x2000)]
      info['binary_type'] = ('executable', 'shlib')[suffix == 'dll']
      rva_ofs = pe_ofs + 24 + (opthd12_size - 4)
      rva_count, = struct.unpack('<L', header[rva_ofs : rva_ofs + 4])
      if rva_count > ((opthd_size - opthd12_size) >> 2):
        raise ValueError('pe rva_count too large.')
      vaddr = vsize = 0
      if rva_count > 14:  # IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR.
        vaddr, vsize = struct.unpack('<LL', header[rva_ofs + 116 : rva_ofs + 124])
      # https://stackoverflow.com/q/36569710
      # https://reverseengineering.stackexchange.com/q/1614
      if vaddr > 0 and vsize > 0:  # Typically vaddr == 8292, vsize == 72.
        info['format'], info['os'] = 'dotnet' + suffix, 'dotnet'  # 'dotnetexe'  # .NET executable assembly.
      elif header[pe_ofs + 92 : pe_ofs + 94] in ('\x0a\0', '\x0b\0', '\x0c\0', '\x0d\0'):
        # Above: check the subsystem field for UEFI.
        info['format'], info['os'] = 'efi' + suffix, 'efi'  # 'efiexe'.
      else:
        info['format'], info['os'] = 'win' + suffix, 'windows'  # 'winexe'.
        if suffix == 'exe' and info['subformat'] == 'pe32' and is_hx():  # https://www.japheth.de/HX.html
          info['subformat'] += '-hx'  # subformat=pe32-hx.
    else:  # Not executable.
      info['format'] = 'pe-nonexec'  # TODO(pts): Windows (non-Wine) .vxd?
      data = header[pe_ofs + 24 + opthd_size:]
      its_ofs = None
      for _ in xrange(section_count):
        if len(data) < 40:
          data += fread(40 - len(data))
          if len(data) < 40:
            raise ValueError('EOF in pe section table.')
        name, virtual_size, virtual_address = struct.unpack('<8sLL', data[:16])
        name = name.rstrip('\0')
        data = data[40:]  # Usually empty by now.
        # http://www.russotto.net/chm/itolitlsformat.html
        if name == '.its':
          its_ofs = virtual_size + virtual_address
      ofs = pe_ofs + 24 + opthd_size + 40 * section_count
      if its_ofs is not None and its_ofs >= ofs:
        if len(data) >= its_ofs - ofs:
          data = data[its_ofs - ofs:]
        elif not fskip(its_ofs - ofs - len(data)):
          data = None
        if data is not None:
          if len(data) < 40:
            data += fread(40 - len(data))
          if is_hxs(data):
            info['format'] = 'hxs'
            info.pop('endian', None)
  elif size_hi == 0:
    raise ValueError('Empty exe image.')
  elif reloc_count and reloc_end_ofs > header_size:
    raise ValueError('exe relocation table too long.')
  else:  # MS-DOS EXE (MZ), no PE, LE, LX or NE.
    info['format'], info['subformat'], info['arch'], info['binary_type'], info['os'], info['endian'] = 'dosexe', 'dos', '8086', 'executable', 'dos', 'little'
    if reloc_count and not 28 <= reloc_ofs <= 512:
      info['subformat'] = 'dos-weird-reloc'
    if reloc_count == 0 and header[24 : 32] == '>TIPPACH':  # wdosx, embedded.
      # dosexe is exe with a DOS extender stub.
      # https://en.wikipedia.org/wiki/DOS_extender
      info['format'], info['subformat'], info['arch'] = 'dosxexe', 'wdosx', 'i386'
    elif reloc_ofs >= 80 and header[28 : 51] == 'PMODSTUB.EXE generated ':  # Embedded.
      # https://en.wikipedia.org/wiki/PMODE
      info['format'], info['subformat'], info['arch'] = 'dosxexe', 'pmodedj', 'i386'
    else:
      comment_ofs, is_comment64 = reloc_end_ofs, False
      is_comment64 = False
      if reloc_count == 0 and reloc_ofs == 0 and len(header) >= 64 and not header[22 : 64].rstrip('\0'):
        comment_ofs, is_comment64 = 64, True
      if comment_ofs <= 640 and len(header) < 640:
        header += fread(640 - len(header))
      def is_watcom_suffix(header, size):
        header = size >= 72 and header[size - 72 : size]
        return 'Can\'t run DOS/4G(W)' in header and 'DOS4GPATH' in header and 'DOS4GW.EXE\0' in header and 'DOS4G.EXE\0' in header
      if not is_comment64 and comment_ofs <= 200 and header[comment_ofs : comment_ofs + 14] == '\0\0\0\0\r\nCWSDPMI ':  # Embedded.
        info['format'], info['subformat'], info['arch'] = 'dosxexe', 'cwsdpmi', 'i386'
      elif is_comment64 and header[comment_ofs : comment_ofs + 24] == '\r\nstub.h generated from ':  # Not embedded.
        # Also at offset 512: 'go32stub, v 2.02'.
        info['format'], info['subformat'], info['arch'] = 'dosxexe', 'djgpp', 'i386'
      elif len(header) >= 624 and comment_ofs <= 512 and header[597 : 612] == '\0\0\0\0\0\0\0DOS/4G  ' and not header[comment_ofs : 512].rstrip('\0'):  # Embedded.
        info['format'], info['subformat'], info['arch'] = 'dosxexe', 'dos4gw', 'i386'
      elif comment_ofs == 28 and header[26 : 32] == '\0\0\0\0\0\0' and size in (0x200, 0x220, 0x280) and is_watcom_suffix(header, size):  # Not embedded.
        info['format'], info['subformat'], info['arch'] = 'dosxexe', 'watcom', 'i386'
      elif is_hx():
        info['format'], info['subformat'], info['arch'] = 'dosxexe', 'hx', 'i386'
      elif comment_ofs == 28 and header[26 : 32] == '\0\0\0\0\0\0' and header_size in (32, 64) and 'PMODE/W v1.' in header[header_size + 20 : header_size + 32]:
        info['format'], info['subformat'], info['arch'] = 'dosxexe', 'pmodew', 'i386'
      elif comment_ofs == 28 and header[26 : 32] == '\0\0\0\0\0\0' and header_size in (32, 64) and header[header_size : header_size + 16] == '\xfa\x16\x1f\x26\xa1\x02\x00\x83\xe8\x40\x8e\xd0\xfb\x06\x16\x07':
        # There is also 'CWC...CauseWay' at header[header_size + 0x490], but that's too much to read.
        info['format'], info['subformat'], info['arch'] = 'dosxexe', 'causeway', 'i386'
      elif 28 <= comment_ofs <= header_size and header_size == 48 and header[header_size : header_size + 64] == '\n\rFatal error, DPMI host does not support 32 bit applications$\n\r':
        # https://digitalmars.com/ctg/dos32.html
        # https://github.com/Olde-Skuul/KitchenSink/tree/master/sdks/dos/x32
        info['format'], info['subformat'], info['arch'] = 'dosxexe', 'x32vm', 'i386'
      elif 28 <= comment_ofs <= header_size and 32 <= header_size <= 128 and header[26 : 32] == '\0\0\0\0\0\0' and (
          (header[header_size : header_size + 28] == 'STUB/32A\0Copyright (C) 1996-') or  # Not embedded.
          (header[header_size : header_size + 4] == 'ID32' and header[header_size + 28 : header_size + 56] == 'STUB/32C\0Copyright (C) 1996-') or  # Not embedded.
          (header[header_size : header_size + 4] == 'ID32' and header[header_size + 28 : header_size + 55] == 'DOS/32A\0Copyright (C) 1996-') or  # Embedded.
          (header[header_size : header_size + 4] == 'ID32' and header[header_size + 28 : header_size + 38] == 'DOS/32A\0\0R')):  # Embedded.
        info['format'], info['subformat'], info['arch'] = 'dosxexe', 'dos32a', 'i386'
      elif header[pe_ofs : pe_ofs + 8] == 'LE\0\0\0\0\0\0':
        # First we checked for DOS extenders emitted by Watcom C compiler
        # first (which would be LE with os=os2 below, but it's really
        # os=dos).
        parse_lxle(fread, info, fskip, pe_ofs, header)


def parse_svg_dimen(data):
  whitespace = '\t\n\x0b\x0c\r '
  data = data.lower().strip(whitespace)
  # https://www.w3.org/TR/SVG11/coords.html
  if data.endswith('px'):
    multiplier, data = 1, data[:-2].rstrip(whitespace)
  elif data.endswith('pt'):
    multiplier, data = 1.25, data[:-2].rstrip(whitespace)
  elif data.endswith('pc'):
    multiplier, data = 15, data[:-2].rstrip(whitespace)
  elif data.endswith('mm'):
    multiplier, data = 3.543307, data[:-2].rstrip(whitespace)
  elif data.endswith('cm'):
    multiplier, data = 35.43307, data[:-2].rstrip(whitespace)
  elif data.endswith('in'):
    multiplier, data = 90, data[:-2].rstrip(whitespace)
  else:
    multiplier = 1
  if ('e' in data or '.' in data) and (data[0].isdigit() or data[0] == '.') and data[-1].isdigit():  # Floating point, e.g. 2e3.
    data = float(data) * multiplier
  elif data and data.isdigit():
    data = int(data) * multiplier
  else:
    # This also disallows negative.
    raise ValueError('Bad SVG dimension: %r' % data)
  if isinstance(data, float):
    data = int(data + .5)  # Round to neariest integer.
  return data


def count_is_xml(header):
  # XMLDecl in https://www.w3.org/TR/2006/REC-xml11-20060816/#sec-rmd
  if header.startswith('<?xml?>'):
    # XMLDecl needs version="...", but we are lenient here.
    return 700
  if not header.startswith('<?xml') and header[5 : 6].isspace():
    return False
  i = 6
  while i < len(header) and header[i].isspace():
    i += 1
  header = header[i : i + 13]
  if header.startswith('?>'):
    return (i + 2) * 100
  for decl in ('version=', 'encoding=', 'standalone='):
    i = len(decl)
    if header.startswith(decl) and len(header) > i and header[i] in '"\'':
      return (i + 1) * 100
  return False


def count_is_xml_comment(header):
  i = 0
  while i < len(header) and header[i].isspace():
    i += 1
  if header[i : i + 4] != '<!--':
    return False
  return (i + 4) * 100


UOF_FORMAT_BY_MIMETYPE = {
    'vnd.uof.presentation': 'uof-uop',
    'vnd.uof.spreadsheet': 'uof-uos',
    'vnd.uof.text': 'uof-uot',
}

ODF_FLATXML_FORMAT_BY_MIMETYPE = {
    'application/vnd.oasis.opendocument.graphics': 'odf-flatxml-fodg',
    'application/vnd.oasis.opendocument.presentation': 'odf-flatxml-fodp',
    'application/vnd.oasis.opendocument.spreadsheet': 'odf-flatxml-fods',
    'application/vnd.oasis.opendocument.text': 'odf-flatxml-fodt',
}


def analyze_xml(fread, info, fskip, format='xml', fclass='other',
                extra_formats=('xml-comment', 'xhtml', 'mathml', 'uof-xml', 'odf-flatxml') + tuple(UOF_FORMAT_BY_MIMETYPE.itervalues()) + tuple(ODF_FLATXML_FORMAT_BY_MIMETYPE.itervalues()),  # Also generates 'smil' etc.
                spec=((0, '<?xml', 5, WHITESPACE + ('?',), 256, lambda header: adjust_confidence(6, count_is_xml(header))),
                      # 408 is arbitrary, but since cups-raster has it, we can also that much.
                      (0, '<!--', 408, lambda header: adjust_confidence(400, count_is_xml_comment(header))),
                      (0, WHITESPACE, 408, lambda header: adjust_confidence(12, count_is_xml_comment(header))))):
  # https://www.w3.org/TR/2006/REC-xml11-20060816/#sec-rmd
  whitespace = '\t\n\x0b\x0c\r '
  whitespace_tagend = whitespace + '>'
  header = fread(1)
  while header and header in whitespace:
    header = fread(1)
  if header:
    header += fread(5)
  had_comment = False
  while header.startswith('<!--'):
    had_comment = True
    s = (header[5] == '-') + (header[4 : 6] == '--')
    while 1:  # Look for terminating '-->'.
      data = fread(1)
      if not data:
        raise ValueError('EOF in xml comment.')
      if data == '-':
        if s < 2:
          s += 1
      elif data == '>':
        if s == 2:
          break
      else:
        s = 0
    data = fread(1)
    while data and data in whitespace:
      data = fread(1)
    header = data + fread(5)

  if len(header) < 5:
    if had_comment:
      info['format'] = 'xml-comment'
      return
    raise ValueError('Too short for xml tag.')
  header_lo = header.lower()
  if header.startswith('<?xml') and len(header) > 5 and (header[5] in whitespace or header[5] == '?'):
    info['format'], data = 'xml', ''
  elif header.startswith('<svg:'):
    if len(header) < 9:
      header += fread(9 - len(header))
      if len(header) < 9:
        raise ValueError('Too short for svg.')
    if header.startswith('<svg:svg') and len(header) > 8 and header[8] in whitespace_tagend:
      info['format'], data = 'svg', '?><svg' + header[8:]
    else:
      raise ValueError('svg signature not found.')
  elif header.startswith('<svg') and len(header) > 4 and header[4] in whitespace_tagend:
    info['format'], data = 'svg', '?>' + header
  elif header.startswith('<smil') and len(header) > 5 and header[5] in whitespace_tagend:
    info['format'], data = 'smil', '?>' + header
  else:
    def is_ws_xhtml_tag(header, i):
      if i:
        i = header.find('>', i - 1)
        if i > 0:
          j = 0
          while j < i and header[j].isspace():
            j += 1
          if header[j : j + 5] == '<html':  # Lowercase.
            header = ' '.join(header[j : i].split()).replace("'", '"')
            if ' xmlns="' in header:
              return True
      return False
    if header_lo.startswith('<!doct'):
      header += fread(1024 - len(header))
      if count_is_html(header):
        info['format'] = 'html'
        if header.startswith('<!DOCTYPE'):  # Uppercase.
          i = header.find('>')
          if i > 0:
            header = header[i + 1:]
            while 1:
              header += fread(1024 - len(header))
              if not (header.startswith('<!--') or header[:1].isspace()):
                break
              j = 0
              while j < len(header) and header[j].isspace():
                j += 1
              header = header[j:]
              if header.startswith('<!--'):
                j = header.find('-->', 4)
                if j >= 0:
                  header = header[j + 3:]
                else:
                  header = '<!--' + header[-2:]
            if is_ws_xhtml_tag(header, count_is_html(header) // 100):
              # https://en.wikipedia.org/wiki/XHTML
              info['format'] = 'xhtml'
        return
    elif (header_lo.startswith('<html') or header_lo.startswith('<head') or header_lo.startswith('<body')) and header[5] in whitespace_tagend:
      header += fread(1024 - len(header))
      i = count_is_html(header) // 100
      if i:
        info['format'] = ('html', 'xhtml')[is_ws_xhtml_tag(header, i)]
        return
    if had_comment:
      info['format'] = 'xml-comment'
      return
    raise ValueError('xml signature not found.')

  def parse_attrs(data):
    attrs, i = {}, 0
    while i < len(data):
      c = data[i]
      if c in whitespace:
        i += 1
        continue
      if not c.isalpha():
        raise ValueError('Bad xml attr name start.')
      j = i
      while i < len(data) and (data[i].isalnum() or data[i] in '-:_'):
        i += 1
      if i == len(data):
        raise ValueError('EOF in attr name.')
      attr_name = data[j : i]
      while data[i : i + 1] in whitespace:
        i += 1
      if data[i : i + 1] != '=':
        raise ValueError('Expected attr eq: %r' % data[j : i + 1])
      i += 1
      while data[i : i + 1] in whitespace:
        i += 1
      cq = data[i : i + 1]
      if cq not in '"\'':
        raise ValueError('Expected attr quote start.')
      i += 1
      j = i
      cnq = '<>' + cq
      while i < len(data) and data[i] not in cnq:
        i += 1
      if data[i : i + 1] != cq:
        raise ValueError('Missing attr quote end.')
      # TODO(pts): Replace &lt; with <, &apos; etc. in attr_value.
      attr_value = data[j : i]
      i += 1
      attrs[attr_name] = attr_value
    return attrs

  def populate_svg_dimens(attrs, info):
    if ('width' in attrs and 'height' in attrs and
        not attrs['width'].endswith('%') and
        not attrs['height'].endswith('%')):
      info['width'] = parse_svg_dimen(attrs['width'])
      info['height'] = parse_svg_dimen(attrs['height'])
    elif 'viewBox' in attrs:
      # https://developer.mozilla.org/en-US/docs/Web/SVG/Attribute/viewBox
      items = attrs['viewBox'].strip(whitespace)
      for w in whitespace:
        items = items.replace(w, ' ')
      items = items.split(' ')
      if len(items) >= 4:
        info['width'] = parse_svg_dimen(items[2])
        info['height'] = parse_svg_dimen(items[3])

  def process(data):  # Reads and parses the first real XML tag.
    i = data.find('?>') + 2
    if i < 2:
      raise EOFError('End-of-xml-header not found.')
    had_doctype = False
    while 1:
      if len(data) <= i:
        raise EOFError
      if data[i] in whitespace:
        i += 1
      elif data[i] == '<':
        i = j = i + 1
        if i == len(data):
          raise EOFError
        if data[i] == '!':
          if i + 3 > len(data):
            raise EOFError
          if data[i + 1 : i + 3] == '--':  # XML comment.
            i = data.find('-->', i + 3) + 3
            if i < 3:
              raise EOFError
            continue
        elif not data[i].isalpha():
          raise ValueError('Bad xml tag name start.')
        i += 1
        while i < len(data) and (data[i].isalpha() or data[i] == '-' or data[i] == ':'):
          i += 1
        tag_name = data[j : i]
        j = i
        i = data.find('>', j) + 1
        if i <= 0:
          raise EOFError
        if i - 1 > j and data[i - 2] == '/':
          i -= 1
        if tag_name.startswith('!'):
          if tag_name == '!DOCTYPE':  # XML doctype is uppercase.
            if had_doctype:
              raise ValueError('Duplicate xml doctype.')
            had_doctype = True
            j0 = j
            j += data[j : i].find('[')
            if j >= j0:
              i = data.find(']>', j + 1) + 2
              if i < 2:
                raise EOFError
            continue
          raise ValueError('Unknown xml special tag: %s' % tag_name)
        elif tag_name in ('smil', 'smil:smil'):
          info['format'] = 'smil'
          # No width= and height= attributes in SMIL.
        elif tag_name in ('svg', 'svg:svg'):
          info['format'] = 'svg'
          # Typical: attrs['xmlns'] == 'http://www.w3.org/2000/svg'.
          attrs = parse_attrs(buffer(data, j, i - j - 1))
          populate_svg_dimens(attrs, info)
          if 'width' not in info:  # Look for a '<view ...>' tag.
            # TODO(pts): Also ignore XML comments here.
            while i < len(data) and data[i] in whitespace:
              i += 1
            if i == len(data):
              raise EOFError
            if data[i] == '<':
              j = i + 1
              i = data.find('>', j) + 1
              if i <= 0:
                raise EOFError
              if data[j : j + 4] == 'view' and data[j + 4 : j + 5] in whitespace:
                j += 5
                if data[i - 2] == '/':
                  i -= 1
                attrs = parse_attrs(buffer(data, j, i - j - 1))
                populate_svg_dimens(attrs, info)
        elif tag_name == 'html':
          # We don't check for xmlns="..." here, <?xml above was enough.
          info['format'] = 'xhtml'
        elif tag_name == 'TeXmacs':
          info['format'], info['subformat'] = 'texmacs', 'xml'
          attrs = parse_attrs(buffer(data, j, i - j - 1))
          if (attrs.get('version', '') + 'xx')[:2] not in ('1.', '2.', '3.'):
            raise ValueError('Bad texmacs version: %r' % attrs.get('version'))
        elif tag_name == 'math':
          attrs = parse_attrs(buffer(data, j, i - j - 1))
          if attrs.get('xmlns') == 'http://www.w3.org/1998/Math/MathML':
            info['format'] = 'mathml'
        elif tag_name == 'uof:UOF':
          # Replace xmlns:SOMENONEASCII= with xmlns:=
          attrs_str = ''.join((c for c in buffer(data, j, i - j - 1) if ord(c) < 128))
          attrs = parse_attrs(attrs_str)
          if attrs.get('xmlns:uof') == 'http://schemas.uof.org/cn/2003/uof':
            format = UOF_FORMAT_BY_MIMETYPE.get(attrs.get('uof:mimetype'))
            if format is not None:
              info['format'] = format
            else:
              info['format'] = 'uof-xml'
        elif tag_name == 'office:document':
          attrs = parse_attrs(buffer(data, j, i - j - 1))
          if attrs.get('xmlns:office') == 'urn:oasis:names:tc:opendocument:xmlns:office:1.0':
            format = ODF_FLATXML_FORMAT_BY_MIMETYPE.get(attrs.get('office:mimetype'))
            if format is not None:
              info['format'] = format
            else:
              info['format'] = 'odf-flatxml'
        break
      else:
        raise ValueError('xml tag expected.')

  data += fread(1024 - len(data))
  try:
    process(data)
  except EOFError:  # Read more, up to 32 KiB.
    while 1:
      size = len(data) + 1024
      data += fread(1024)
      try:
        process(data)
        break
      except EOFError:
        if len(data) >= 32768 or len(data) != size:
          break


def populate_bmp_info(info, data, format):
  # Should be preceded by: data = fread(34).
  if len(data) < 22:
    raise ValueError('Too short for %s bmp.' % format)
  if not data.startswith('BM'):
    raise ValueError('%s bmp signature not found.' % format)
  if data[6 : 10] != '\0\0\0\0':
    raise ValueError('Bad %s bmp data.'  % format)
  parse_dib_header(info, buffer(data, 14))
  info['format'] = format


def analyze_bmp(fread, info, fskip, format='bmp', fclass='image',
                spec=(0, 'BM', 6, '\0\0\0\0', 15, '\0\0\0', 22, lambda header: (len(header) >= 22 and 12 <= ord(header[14]) <= 127, 52))):
  # https://en.wikipedia.org/wiki/BMP_file_format
  # https://github.com/ImageMagick/ImageMagick/blob/1b04b8317378589d1c3a2fddecf30ef1f7cf2c80/coders/bmp.c#L618
  data = fread(34)
  if len(data) < 22:
    raise ValueError('Too short for bmp.')
  if not data.startswith('BM'):
    raise ValueError('bmp signature not found.' )
  populate_bmp_info(info, data, 'bmp')


DIB_BI_SIZES = (12, 40, 64, 108, 124)  # From Pillow-8.4.0.
DIB_BI_BITCNTS = (1, 2, 4, 8, 16, 24, 32)


def analyze_dib(fread, info, fskip, format='dib', fclass='image',
                spec=((0, '\x0c\0\0\0', 8, '\1\0', 10, ('\1', '\2', '\4', '\x08', '\x18'), 11, '\0'),
                      (0, tuple(chr(c) for c in DIB_BI_SIZES if c >= 20), 1, '\0\0\0', 12, '\1\0', 14, tuple(chr(c) for c in DIB_BI_BITCNTS), 15, '\0', 17, lambda header: (len(header) >= 17 and ord(header[16]) < 32, 38), 17, '\0\0\0'))):
  # BITMAPINFOHEADER struct (and its various versions), starting at offset 14
  # of format=bmp.
  data = fread(20)
  if len(data) < 12:
    raise ValueError('Too short for dib.')
  # Do some checks before calling the permissive parse_dib_header.
  bi_size, = struct.unpack('<L', data[:4])
  if bi_size not in DIB_BI_SIZES:
    raise ValueError('dib signature not found.')
  info['format'] = 'dib'
  if bi_size == 12:
    if data[8 : 10] != '\1\0':
      raise ValueError('Bad dib bc_planes.')
    bi_bitcnt, = struct.unpack('<H', data[10 : 12])
    if bi_bitcnt in (16, 32):
      raise ValueError('Bad dib bc_bitcnt.')
  else:
    if data[12 : 14] != '\1\0':
      raise ValueError('Bad dib bi_planes.')
    bi_bitcnt, = struct.unpack('<H', data[14 : 16])
    if ord(data[16]) >= 32:
      raise ValueError('Bad dib bi_compression.')
  if bi_bitcnt not in DIB_BI_BITCNTS:
    raise ValueError('Bad dib bi_bitcnt.')
  parse_dib_header(info, data)


def analyze_rdib(fread, info, fskip, format='rdib', fclass='image',
                 spec=((0, 'RIFF', 8, 'RDIBBM'),
                       (0, 'RIFF', 8, 'RDIBdata'))):
  # http://fileformats.archiveteam.org/wiki/RDIB
  # https://www.aelius.com/njh/wavemetatools/doc/riffmci.pdf
  # We don't support the ``extended RDIB'', because it has hard to find any
  # sample files.
  header = fread(20 + 34)
  if len(header) < 14:
    raise ValueError('Too short for rdib.')
  has_data = header[12 : 16] == 'data'
  if not (header.startswith('RIFF') and header[8 : 12] == 'RDIB' and (has_data or header[12 : 14] == 'BM')):
    raise ValueError('rdi signature not found.' )
  info['format'] = 'rdib'
  if has_data:
    # If there is a 4-byte chunk_size field after 'data', then header[26 :
    # 30] becomes '\0\0\0\0' (dib_data[6 : 10]). This is how we detect the
    # presence of chunk_size.
    header = header[20 - 4 * (len(header) >= 30 and header[16 : 18] == 'BM' and header[22 : 26] == '\0\0\0\0' and header[26 : 30] != '\0\0\0\0'):]
  else:
    header = header[12:]
  if len(header) >= 22:
    populate_bmp_info(info, header, 'rdib')


def analyze_flic(fread, info, fskip, format='flic', fclass='video',
                 spec=(4, ('\x12\xaf', '\x11\xaf'), 12, '\x08\0', 14, ('\3\0', '\0\0'))):
  # Autodesk Animator FLI or Autodesk Animator Pro flc.
  # http://www.drdobbs.com/windows/the-flic-file-format/184408954
  header = fread(16)
  if len(header) < 16:
    raise ValueError('Too short for flic.')
  cc = header[4 : 6]
  if cc == '\x12\xaf':
    subformat = 'flc'
  elif cc == '\x11\xaf':
    subformat = 'fli'
  else:
    raise ValueError('Bad flic subformat: %r' % cc)
  if header[12 : 14] != '\x08\0' or header[14 : 16] not in ('\3\0', '\0\0'):
    raise ValueError('Bad flic header.')
  info['format'] = 'flic'
  info['subformat'] = subformat
  width, height = struct.unpack('<HH', header[8 : 12])
  video_track_info = {'type': 'video', 'codec': 'rle'}
  info['tracks'] = [video_track_info]
  set_video_dimens(video_track_info, width, height)


def analyze_mng(fread, info, fskip, format='mng', fclass='image',
                spec=(0, '\x8aMNG\r\n\x1a\n')):
  # http://www.libpng.org/pub/mng/spec/
  header = fread(24)
  if len(header) < 24:
    raise ValueError('Too short for mng.')
  if not header.startswith('\x8aMNG\r\n\x1a\n\0\0\0'):
    raise ValueError('mng signature not found.')
  info['format'], info['tracks'] = 'mng', [{'codec': 'jpeg+png'}]
  if header[12 : 16] == 'MHDR':
    width, height = struct.unpack('>LL', header[16 : 24])
    set_video_dimens(info['tracks'][0], width, height)


def analyze_png(fread, info, fskip, format='png', extra_formats=('apng',), fclass='image',
                spec=((0, '\x89PNG\r\n\x1a\n\0\0\0', 12, 'IHDR'),
                      (0, '\x89PNG\r\n\x1a\n\0\0\0\x04CgBI\x50\0\x20', 24, '\0\0\0', 28, 'IHDR'))):
  # https://tools.ietf.org/html/rfc2083
  # https://wiki.mozilla.org/APNG_Specification
  header = fread(24)
  if len(header) < 24:
    raise ValueError('Too short for png.')
  if header.startswith('\x89PNG\r\n\x1a\n\0\0\0'):
    if header[12 : 16] == 'IHDR':
      pass
    elif header[12 : 19] == 'CgBI\x50\0\x20':
      # https://iphonedev.wiki/index.php/CgBI_file_format
      # https://stackoverflow.com/a/20670192/
      header += fread(16)
      if len(header) == 40 and header[24 : 27] == '\0\0\0' and header[28 : 32] == 'IHDR':
        info['subformat'] = 'apple'  # For iOS.
        header = header[16:]
      else:
        header = ''
  else:
    header = ''
  if not header:
    raise ValueError('png signature not found.')
  info['format'], info['codec'] = 'png', 'flate'
  info['width'], info['height'] = struct.unpack('>LL', header[16 : 24])
  chunk_size, = struct.unpack('>L', header[8 : 12])
  # Look for acTL chunk to detect format=apng.
  if chunk_size >= len(header) - 16 and fskip(chunk_size - (len(header) - 16) + 4):
    while 1:
      data = fread(8)
      if len(data) < 8:
        break
      chunk_size, chunk_type = struct.unpack('>L4s', data)
      if chunk_type == 'acTL':
        info['format'] = 'apng'
        break
      if chunk_type in ('IDAT', 'IEND') or not fskip(chunk_size + 4):
        break


def analyze_jng(fread, info, fskip, format='jng', fclass='image',
                spec=(0, '\x8bJNG\r\n\x1a\n\0\0\0')):
  # http://www.libpng.org/pub/mng/spec/jng.html
  header = fread(24)
  if len(header) < 24:
    raise ValueError('Too short for jng.')
  if not header.startswith('\x8bJNG\r\n\x1a\n\0\0\0'):
    raise ValueError('jng signature not found.')
  info['format'] = 'jng'
  info['codec'] = 'jpeg'
  if header[12 : 16] == 'JHDR':
    info['width'], info['height'] = struct.unpack('>LL', header[16 : 24])


def analyze_lepton(fread, info, fskip):
  # JPEG reencoded by Dropbox lepton. Getting width and height is complicated.
  # https://github.com/dropbox/lepton
  header = fread(4)
  if len(header) < 4:
    raise ValueError('Too short lepton.')
  if not (header.startswith('\xcf\x84') and header[2] in '\1\2' and header[3] in 'XYZ'):
    raise ValueError('lepton signature not found.')
  info['format'] = info['codec'] = 'lepton'


def analyze_lbm(fread, info, fskip, format='lbm', fclass='image',
                spec=(0, 'FORM', 8, ('ILBM', 'PBM ', 'RGB8', 'RGBN', 'ACBM', 'VDAT'), 12, 'BMHD\0\0\0\x14')):
  # https://en.wikipedia.org/wiki/ILBM
  # https://github.com/unwind/gimpilbm/blob/master/ilbm.c
  header = fread(24)
  if len(header) < 20:
    raise ValueError('Too short for lbm.')
  if not (header.startswith('FORM') and
          # Different 'DEEP', 'SHAM', 'DHAM', 'RGFX'.
          header[8 : 12] in ('ILBM', 'PBM ', 'RGB8', 'RGBN', 'ACBM', 'VDAT') and
          # Limitation: BMHD can appear later in the file.
          header[12 : 20] == 'BMHD\0\0\0\x14'):
    raise ValueError('lbm signature not found.')
  info['format'], info['subformat'] = 'lbm', header[8 : 12].strip().lower()
  info['codec'] = ('uncompressed', 'rle')[header[8] == 'I']
  if len(header) >= 24:
    info['width'], info['height'] = struct.unpack('>HH', header[20 : 24])


def analyze_deep(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/IFF-DEEP
  # https://wiki.amigaos.net/wiki/DEEP_IFF_Chunky_Pixel_Image
  header = fread(26)
  if len(header) < 20:
    raise ValueError('Too short for deep.')
  if not (header.startswith('FORM') and
          header[8 : 12] == 'DEEP' and
          # Limitation: BMHD can appear later in the file.
          header[12 : 20] == 'DGBL\0\0\0\x08'):
    raise ValueError('deep signature not found.')
  info['format'] = 'deep'
  if len(header) >= 24:
    info['width'], info['height'] = struct.unpack('>HH', header[20 : 24])
  if len(header) >= 26:
    codec, = struct.unpack('>H', header[24 : 26])
    codecs = ('uncompressed', 'rle', 'huffman', 'dynamic-huffman', 'jpeg', 'tvdc')
    if codec < len(codecs):
      info['codec'] = codecs[codec]
    else:
      info['codec'] = str(codec)


def analyze_pcx(fread, info, fskip, format='pcx', fclass='image',
                spec=(0, '\n', 1, ('\0', '\2', '\3', '\4', '\5'), 2, ('\0', '\1'), 3, ('\1', '\2', '\4', '\x08'))):
  # https://en.wikipedia.org/wiki/PCX
  header = fread(12)
  if len(header) < 12:
    raise ValueError('Too short for pcx.')
  signature, version, encoding, bpp, xmin, ymin, xmax, ymax = struct.unpack(
      '<BBBBHHHH', header)
  if not (signature == 10 and version in (0, 2, 3, 4, 5) and encoding in (0, 1) and bpp in (1, 2, 4, 8)):
    raise ValueError('pcx signature not found.')
  if xmax < xmin:
    raise ValueError('pcx xmax smaller than xmin.')
  if ymax < ymin:
    raise ValueError('pcx ymax smaller than ymin.')
  info['format'] = 'pcx'
  info['codec'] = ('uncompressed', 'rle')[encoding]
  info['width'], info['height'] = xmax - xmin + 1, ymax - ymin + 1


def is_f32_pos_nbit16(f):
  """Is f (an f32) a positive integer, smaller than (1 << 16)?"""
  return (f > 0 and 0 <= (f >> 23) - 127 < 16 and
          not (f & ((1 << (150 - (f >> 23))) - 1)))


def count_is_spider(header):
  if len(header) < 48:
    return False
  if header.startswith('\x3f\x80\0\0') and header[16 : 20] == '\x3f\x80\0\0':
    fmt = '>'
  elif header.startswith('\0\0\x80\x3f') and header[16 : 20] == '\0\0\x80\x3f':
    fmt = '<'
  else:
    return False
  height, width = struct.unpack(fmt + '4xL36xL', buffer(header, 0, 48))
  if not (is_f32_pos_nbit16(width) and is_f32_pos_nbit16(height)):
    return False
  # Confidence of is_f32_pos_nbit16 is 201.
  return (800 - 13) + 2 * 201


def analyze_spider(fread, info, fskip, format='spider', fclass='image',
                   spec=(0, ('\x3f\x80\0\0', '\0\0\x80\x3f'), 48, lambda header: adjust_confidence(800 - 13, count_is_spider(header)))):
  # https://github.com/python-pillow/Pillow/blob/862be7cbcda1a4fc566a4679ad38b0cd8bba22fe/src/PIL/SpiderImagePlugin.py#L234-L259
  # https://en.wikipedia.org/wiki/Single-precision_floating-point_format
  header = fread(48)
  if len(header) < 48:
    raise ValueError('Too short for spider.')
  if not (  # Check slice_count == 1.0 and iform == 1.0 (2D), both as f32.
     (header.startswith('\x3f\x80\0\0') and header[16 : 20] == '\x3f\x80\0\0') or
     (header.startswith('\0\0\x80\x3f') and header[16 : 20] == '\0\0\x80\x3f')):
    raise ValueError('spider signature not found.')

  def get_int_from_posint_f32(f):
    shift = 150 - (f >> 23)
    assert 0 <= shift <= 23
    return int((0x800000 | f & 0x7fffff) >> shift)

  fmt = '<>'[header[0] != '\0']  # Detect endianness.
  height, width = struct.unpack(fmt + '4xL36xL', buffer(header, 0, 48))
  # Valid iform (header[16 : 20]) values: 1 (2D), 3, -11, -12, -21, -22.
  if not is_f32_pos_nbit16(width):
    raise ValueError('Bad spider width.')
  if not is_f32_pos_nbit16(height):
    raise ValueError('Bad spider height.')
  info['format'], info['codec'] = 'spider', 'uncompressed'
  info['width'] = get_int_from_posint_f32(width)
  info['height'] = get_int_from_posint_f32(height)


def analyze_dcx(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/DCX
  # Sample: https://github.com/ImageMagick/ImageMagick6/blob/master/PerlMagick/t/input.dcx
  header = fread(8)
  if len(header) < 4:
    raise ValueError('Too short for dcx.')
  if not header.startswith('\xb1\x68\xde\x3a'):
    raise ValueError('dcx signature not found.')
  if len(header) >= 8:
    pcx_ofs, = struct.unpack('<L', header[4 : 8])
  else:
    pcx_ofs = 12
  if pcx_ofs < 12:
    raise ValueError('dcx pcx_ofs too small: %d' % pcx_ofs)
  info['format'], info['codec'] = 'dcx', 'rle'
  if len(header) >= 8:
    if not fskip(pcx_ofs - len(header)):
      raise ValueError('EOF in dcx before first pcx.')
    try:
      analyze_pcx(fread, info, fskip)
    finally:
      info['format'] = 'dcx'


def count_define_key(data, i=0):
  if not (data[i : i + 7] == '#define' and data[i + 7 : i + 8] in ' \t'):
    return 0, ''
  i += 8
  while i < len(data) and data[i] in ' \t':
    i += 1
  j = i
  while i < len(data) and (data[i].isalnum() or data[i] in '_.'):
    i += 1
  if not (i < len(data) and data[i] in ' \t'):
    return 0, ''
  key = data[j : i]
  j = i
  while i < len(data) and data[i] in ' \t':
    i += 1
  if j == i:
    return 0, ''
  return i, key


def parse_define_dimens(data, i, format):
  dimens = {}
  while 1:
    i, key = count_define_key(data, i)
    if not i:
      break
    if key.endswith('_width') or key.endswith('_height'):
      key = key[key.rfind('_') + 1:]
      j = i
      while i < len(data) and data[i].isalnum():
        i += 1
      value = data[j : i]
      try:
        dimens[key] = int(value)
      except ValueError:
        raise ValueError('Bad %s %s value: %r' % (format, key, value))
      if i >= len(data):
        break
      if data[i] not in '\r\n':
        raise ValueError('Bad %s %s value terminator.' % (format, key))
      if 'width' in dimens and 'height' in dimens:
        break
    else:  # Skip this item.
      while i < len(data) and data[i] not in '\r\n':
        i += 1
    i += 1
    while i < len(data) and data[i] in ' \t\r\n':
      i += 1
  return dimens


def count_is_xbm(header):
  i, key = count_define_key(header)
  if not i or not (key.endswith('_width') or key.endswith('_height')):
    return False
  if not (len(header) > i and header[i].isdigit()):
    return False
  return i * 100 + 12


def analyze_xbm(fread, info, fskip):
  # https://en.wikipedia.org/wiki/X_BitMap
  # https://www.fileformat.info/format/xbm/egff.htm
  data = fread(512)
  if len(data) < 8:
    raise ValueError('Too short for xbm.')
  if not count_is_xbm(data):
    raise ValueError('xbm signature not found.')
  info['format'], info['codec'] = 'xbm', 'uncompressed-ascii'
  dimens = parse_define_dimens(data, 0, 'xbm')
  if 'width' in dimens and 'height' in dimens:
    info['width'], info['height'] = dimens['width'], dimens['height']


def count_is_xpm1(header):
  i, key = count_define_key(header)
  if not i or not key.endswith('_format'):
    return False
  if not (len(header) >= i + 2 and header[i] == '1' and header[i + 1] in '\r\n'):
    return False
  return (i + 1) * 100 + 50


def analyze_xpm(fread, info, fskip):
  # https://en.wikipedia.org/wiki/X_PixMap
  # https://wiki.multimedia.cx/index.php/XPM
  data = fread(512)
  if len(data) < 7:
    raise ValueError('Too short for xpm.')
  i = count_is_xpm1(data) // 100
  if i:
    info['format'], info['subformat'], info['codec'] = 'xpm', 'xpm1', 'uncompressed-ascii'
    dimens = parse_define_dimens(data, i + 1, 'xbm')
    if 'width' in dimens and 'height' in dimens:
      info['width'], info['height'] = dimens['width'], dimens['height']
    return
  if data.startswith('! XPM2') and data[6 : 7] in '\r\n':
    info['format'], info['subformat'], info['codec'] = 'xpm', 'xpm2', 'uncompressed-ascii'
    i = 7
    while i < len(data) and data[i] in '\r\n\t ':
      i += 1
  elif data.startswith('/* XPM */') and data[9 : 10] in '\r\n':
    info['format'], info['subformat'], info['codec'] = 'xpm', 'xpm3', 'uncompressed-ascii'
    i = 10
    while i < len(data) and data[i] in '\r\n\t ':
      i += 1
    if i != len(data):
      i = data.find('"', 9) + 1
      if i <= 0:
        raise ValueError('Missing quote in xpm.')
  else:
    raise ValueError('xpm signature not found.')
  if i < len(data):
    j = i
    while i < len(data) and data[i].isdigit():
      i += 1
    try:
      width = int(data[j : i])
    except ValueError:
      raise ValueError('Bad xpm width: %r' % data[j  : i])
    if data[i] not in '\r\n\t ':
      raise ValueError('Bad xpm separator.')
    i += 1
    while i < len(data) and data[i] in '\r\n\t ':
      i += 1
    j = i
    while i < len(data) and data[i].isdigit():
      i += 1
    try:
      height = int(data[j : i])
    except ValueError:
      raise ValueError('Bad xpm height: %r' % data[j  : i])
    if data[i] not in '\r\n\t ':
      raise ValueError('Bad xpm separator.')
    info['width'], info['height'] = width, height


def analyze_xcf(fread, info, fskip):
  # https://gitlab.gnome.org/GNOME/gimp/blob/master/devel-docs/xcf.txt
  header = fread(22)
  if len(header) < 22:
    raise ValueError('Too short for xcf.')
  signature, version, zero, width, height = struct.unpack(
      '>9s4sBLL', header)
  if signature != 'gimp xcf ' or zero or version not in (
      'file', 'v001', 'v002', 'v003', 'v004', 'v005', 'v006', 'v007',
      'v008', 'v009'):
    raise ValueError('xcf signature not found.')
  info['format'] = 'xcf'
  info['width'], info['height'] = width, height


def analyze_psd(fread, info, fskip):
  # https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/
  header = fread(26)
  if len(header) < 26:
    raise ValueError('Too short for psd.')
  signature, version, zeros, channels, height, width, depth, color_mode = struct.unpack(
      '>4sH6sHLLHH', header)
  if not (signature == '8BPS' and version in (1, 2) and zeros == '\0\0\0\0\0\0'):
    raise ValueError('psd signature not found.')
  if not 1 <= channels <= 56:
    raise ValueError('Bad psd channels: %d' % channels)
  if depth not in (1, 8, 16, 32):
    raise ValueError('Bad psd depth: %d' % depth)
  if color_mode > 15:
    raise ValueError('Bad psd color_mode: %d' % depth)
  info['format'] = 'psd'
  info['width'], info['height'] = width, height


TARGA_CODECS = {
    1: 'uncompressed',
    2: 'uncompressed',
    3: 'uncompressed',
    9: 'rle',
    10: 'rle',
    11: 'rle',
    32: 'huffman-rle',
    33: 'huffman-rle-quadtree',
}


def analyze_tga(fread, info, fskip):
  # https://en.wikipedia.org/wiki/Truevision_TGA
  # http://www.paulbourke.net/dataformats/tga/
  header = fread(18)
  if len(header) < 18:
    raise ValueError('Too short for tga.')
  id_size, colormap_type, image_type, cm_first_idx, cm_size, cm_entry_size, origin_x, origin_y, width, height, bpp, image_descriptor = struct.unpack(
      '<BBBHHBHHHHBB', header)
  if not (id_size == 0 or 30 <= id_size <= 63):
    # TODO(pts): What non-zero values can we see in the wild?
    raise ValueError('Bad tga id_size: %d' % id_size)
  if colormap_type not in (0, 1):
    raise ValueError('Bad tga colormap_type: %d' % colormap_type)
  codec = TARGA_CODECS.get(image_type)
  if codec is None:
    raise ValueError('Bad tga image_type: %d' % image_type)
  if bpp not in (1, 2, 4, 8, 15, 16, 24, 32):  # Bits per pixel.
    raise ValueError('Bad tga bpp: %d' % bpp)
  if cm_entry_size not in (0, 16, 24, 32):
    raise ValueError('Bad tga colormap_entry_size: %d' % cm_entry_size)
  info['format'] = 'tga'
  info['codec'] = codec
  info['width'], info['height'] = width, height


# https://en.wikipedia.org/wiki/TIFF#Compression
TIFF_CODECS = {
    1: 'uncompressed',
    2: 'rle',  # Unused in sam2p.
    3: 'fax',
    4: 'fax',
    5: 'lzw',
    6: 'jpeg',  # Unused in sam2p.
    7: 'jpeg',
    8: 'zip',  # Unused in sam2p.
    9: 'jbig',  # Unused in sam2p.
    10: 'jbig',  # Unused in sam2p.
    0x8765: 'jbig',  # Unused in sam2p.
    0x879b: 'jbig2',  # Unused in sam2p.
    32771: 'rle',  # Unused in sam2p.
    32773: 'rle',  # Packbits.
    32946: 'flate',  # Deflate, zip.
    0x7ffe: 'rle',  # Unused in sam2p.
    0x8029: 'rle',  # Unused in sam2p.
    0x807f: 'rasterpadding',  # Unused in sam2p.
    0x8080: 'rle',  # Unused in sam2p.
    0x8081: 'rle',  # Unused in sam2p.
    0x8082: 'rle',  # Unused in sam2p.
    0x80b3: 'kodak-dcs',  # Unused in sam2p.
    0x8798: 'jpeg2000',  # Unused in sam2p.
    0x8799: 'nikon-nef',  # Unused in sam2p.
}


def analyze_tiff(fread, info, fskip, format='tiff', fclass='image', extra_formats=('tiff-preview',),
                 spec=(0, ('MM\x00\x2a', 'II\x2a\x00'))):
  # https://www.adobe.io/content/dam/udp/en/open/standards/tiff/TIFF6.pdf
  # https://en.wikipedia.org/wiki/TIFF
  # Also includes codec=nikon-nef has_preview=1 raw images: http://lclevy.free.fr/nef/
  header = fread(8)
  if len(header) < 8:
    raise ValueError('Too short for tiff.')
  if header.startswith('MM\x00\x2a'):  # Big endian.
    fmt = '>'
  elif header.startswith('II\x2a\x00'):  # Little endian.
    fmt = '<'
  else:
    raise ValueError('tiff signature not found.')
  info['format'] = 'tiff'
  ifd_ofs, = struct.unpack(fmt + '4xL', header)
  if ifd_ofs < 8:
    raise ValueError('Bad tiff ifd_ofs: %d' % ifd_ofs)
  #print 'ifd_ofs=%d' % ifd_ofs
  if not fskip(ifd_ofs - 8):
    raise ValueError('EOF before tiff ifd_ofs.')
  data = fread(2)
  if len(data) < 2:
    raise ValueError('EOF in tiff ifd_size.')
  ifd_count, = struct.unpack(fmt + 'H', data)
  if ifd_count < 10:  # Mandatory tags. SubIFD may have only 8 (no ImageWidth and ImageLength).
    raise ValueError('tiff ifd_count too small: %d' % ifd_count)
  ifd_data = fread(12 * ifd_count)
  if len(ifd_data) != 12 * ifd_count:
    raise ValueError('EOF in tiff ifd_data.')
  ifd_fmt, short_fmt = fmt + 'HHLL', fmt + 'H'
  is_uncompressed = is_reduced = False
  subifd_count = subifd_ofs = None
  for i in xrange(0, len(ifd_data), 12):
    # if ie_tag < 254: raise ValueError('...')
    ie_tag, ie_type, ie_count, ie_value = struct.unpack(
        ifd_fmt, buffer(ifd_data, i, 12))
    #print 'tag=%d=0x%x type=%d count=%d value=%d' % (ie_tag, ie_tag, ie_type, ie_count, ie_value)
    if ie_count == 1 and ie_type in (3, 4):  # (SHORT, LONG).
      if ie_type == 3:  # SHORT.
        ie_value, = struct.unpack(short_fmt, buffer(ifd_data, i + 8, 2))
      if ie_tag == 256:  # ImageWidth.
        info['width'] = ie_value
      elif ie_tag == 257:  # ImageLength.
        info['height'] = ie_value
      elif ie_tag == 259:  # Compression.
        if ie_value == 1:
          is_uncompressed = True
        if ie_value in TIFF_CODECS:
          info['codec'] = TIFF_CODECS[ie_value]
        else:
          info['codec'] = str(ie_value)
      elif ie_tag == 254 and ie_value == 1:  # SubfileType = reduced-resolution image.
        is_reduced = True
      elif ie_tag == 330:  # SubIFD.
        subifd_count, subifd_ofs = 1, ie_value
    elif ie_tag == 330 and ie_count > 1 and ie_type == 4:  # SubIFD, at least 2.
      subifd_count, subifd_ofs = ie_count, ie_value
  if is_uncompressed and is_reduced and subifd_count is not None:
    info['format'] = 'tiff-preview'
    read_ofs = (ifd_ofs + 2 + len(ifd_data))
    if subifd_count > 1:
      if subifd_ofs > read_ofs and fskip(subifd_ofs - read_ofs):
        data = fread(subifd_count << 2)
        if len(data) == (subifd_count << 2):
          read_ofs = subifd_ofs + len(data)
          subifd_ofs = struct.unpack(fmt + 'L' * subifd_count, data)  # tuple.
    else:
      subifd_ofs = (subifd_ofs,)
    if isinstance(subifd_ofs, tuple) and subifd_ofs:
      # Full-resolution image. http://lclevy.free.fr/nef/
      # In the wild, len(subifd_ofs) == 3 also appears, it also has the
      # full-resolution image at subifd_ofs[1].
      subifd_ofs = subifd_ofs[len(subifd_ofs) > 1]
      if subifd_ofs > read_ofs and fskip(subifd_ofs - read_ofs):
        data = fread(2)
        if len(data) < 2:
          raise ValueError('EOF in tiff subifd_size.')
        ifd_count, = struct.unpack(fmt + 'H', data)
        if ifd_count < 8:  # Mandatory tags. SubIFD may have only 8 (no ImageWidth and ImageLength).
          raise ValueError('tiff subifd_count too small: %d' % ifd_count)
        ifd_data = fread(12 * ifd_count)
        if len(ifd_data) != 12 * ifd_count:
          raise ValueError('EOF in tiff subifd_data.')
        info2 = {'format': 'tiff'}
        for i in xrange(0, len(ifd_data), 12):
          ie_tag, ie_type, ie_count, ie_value = struct.unpack(
              ifd_fmt, buffer(ifd_data, i, 12))
          #print 'subifd tag=%d=0x%x type=%d count=%d value=%d' % (ie_tag, ie_tag, ie_type, ie_count, ie_value)
          if ie_count == 1 and ie_type in (3, 4):  # (SHORT, LONG).
            if ie_type == 3:  # SHORT.
              ie_value, = struct.unpack(short_fmt, buffer(ifd_data, i + 8, 2))
            if ie_tag == 256:  # ImageWidth.
              info2['width'] = ie_value
            elif ie_tag == 257:  # ImageLength.
              info2['height'] = ie_value
            elif ie_tag == 259:  # Compression.
              if ie_value in TIFF_CODECS:
                info2['codec'] = TIFF_CODECS[ie_value]
              else:
                info2['codec'] = str(ie_value)
            elif ie_tag == 254 and ie_value == 0:  # SubfileType = full-resolution image.
              info2['has_preview'] = True
        if info2.get('has_preview'):
          # This can still be incorrect. For example, TIFF tags indicate
          # codec=nikon-nef width=6032 height=4032, but uctually ufraw-batch(1)
          # generates width=4039 height=6031 (correct).
          info.update(info2)


def analyze_pnm(fread, info, fskip):
  header = fread(3)
  if len(header) < 3:
    raise ValueError('Too short for pnm.')
  pnm_whitespace = ' \t\n\x0b\x0c\r'
  if (header[0] == 'P' and header[1] in '1234567' and
      (header[2] in pnm_whitespace or header[2] == '#')):
    if header[1] in '14':
      info['subformat'] = 'pbm'
    elif header[1] in '25':
      info['subformat'] = 'pgm'
    elif header[1] in '36':
      info['subformat'] = 'ppm'
    elif header[1] == '7':
      info['subformat'] = 'ppmx'
    if header[1] in '123':
      info['codec'] = 'uncompressed-ascii'
    else:
      info['codec'] = 'uncompressed'  # Raw.
  else:
    raise ValueError('pnm signature not found.')
  info['format'] = 'pnm'
  data, header = header[-1], header[:-1]
  state = 0
  dimensions = []
  memory_budget = 100
  while 1:
    if not data:
      break # raise ValueError('EOF in %s header.' % info['format'])
    if memory_budget < 0:
      raise ValueError('pnm header too long.')
    if header[1] == '7' and len(header) < 7:
      header += data
    if state == 0 and data.isdigit():
      state = 1
      memory_budget -= 1
      dimensions.append(int(data))
    elif state == 1 and data.isdigit():
      memory_budget -= 1
      dimensions[-1] = dimensions[-1] * 10 + int(data)
    elif data == '#':
      if len(dimensions) == 2:
        break
      while 1:
        data = fread(1)
        if data in '\r\n':
          break
      state = 0
    elif data in pnm_whitespace:
      if header == 'P7 332\n':
        # http://fileformats.archiveteam.org/wiki/XV_thumbnail
        # https://github.com/ingowald/updated-xv/blob/395756178dad44efb950e3ea6739fe60cc62d314/xvbrowse.c#L4034-L4059
        dimensions.pop()
        info['format'] = 'xv-thumbnail'
        info.pop('subformat', None)
        header += '.'
      if len(dimensions) == 2:
        break
      state = 0
    else:
      raise ValueError('Bad character in pnm header: %r' % data)
    data = fread(1)
  if len(dimensions) == 2:
    info['width'], info['height'] = dimensions


def count_is_pam(header):
  # http://netpbm.sourceforge.net/doc/pam.html
  if not header.startswith('P7\n'):
    return 0
  i, letters = 3, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
  while i < len(header):
    c, j = header[i], i
    i = header.find('\n', i) + 1
    if i <= 0:
      break  # EOF in header line.
    if c in letters:
      line = header[j : i - 1]
      if line == 'ENDHDR':
        return i * 100  # Found good header line.
      if line[-1].isspace():
        return 0  # Unexpected whitespace at end of line.
      line = line.split(None, 1)
      if len(line) != 2:
        return 0  # Missing argument.
      if line[0].rstrip(letters):
        return 0  # Non-letter found in key.
      if line[0] in ('WIDTH', 'HEIGHT', 'DEPTH', 'MAXVAL'):
        return i * 100  # Found first mandatory key.
    elif c in '\n#':
      pass
    else:
      return 0  # Unsupported character in comment.
  return 0  # EOF in header.


def analyze_pam(fread, info, fskip):
  # http://netpbm.sourceforge.net/doc/pam.html
  # https://en.wikipedia.org/wiki/Netpbm#PAM_graphics_format
  header = fread(4)
  if len(header) < 4:
    raise ValueError('Too short for pnm.')
  letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
  if not header.startswith('P7\n') or (header[3] not in '\n#' and header[3] not in letters):
    raise ValueError('pam signature not found.')
  info['format'], info['codec'] = 'pam', 'uncompressed'
  data = ''.join(('##\n', header[3], fread(508)))

  def process_lines(data, letters=letters):
    missing_keys = set(('WIDTH', 'HEIGHT', 'DEPTH', 'MAXVAL'))
    i, hdr = 3, {}
    while i < len(data):
      c, j = data[i], i
      i = data.find('\n', i) + 1
      if i <= 0:
        raise ValueError('EOF in pam header line.')
      if c in letters:
        line = data[j : i - 1]
        if line == 'ENDHDR':
          if missing_keys:
            raise ValueError('Missing pam header keys: %s' % ', '.join(sorted(missing_keys)))
          info['width'], info['height'] = hdr['width'], hdr['height']
          return
        if line[-1].isspace():
          raise ValueError('Whitespace at the end of pam header argument.')
        line = line.split(None, 1)
        if len(line) != 2:
          raise ValueError('Whitespace in pam header argument.')
        if line[0].rstrip(letters):
          raise ValueError('Non-letter in pam header key: %r' % line[0])
        missing_keys.discard(line[0])  # Allow arbitrary keys.
        if line[0] in ('WIDTH', 'HEIGHT'):
          key = line[0].lower()
          try:
            hdr[key] = int(line[1])
          except ValueError:
            raise ValueError('Bad pam %s: %r' % (line[0], line[1]))
      elif c in '\n#':
        pass
      else:
        return 0  # Unsupported character in comment.
    raise ValueError('EOF in pam header before ENDHDR.')

  while 1:
    try:
      process_lines(data)
      break
    except ValueError, e:
      if not str(e).startswith('EOF '):
        raise
      size = len(data)
      if size >= 8192 or size & (size - 1):  # Not a power of 2.
        raise
      data += fread(size)
      if size == len(data):
        raise


def analyze_ps(fread, info, fskip):
  # https://web.archive.org/web/20070204021414/http://partners.adobe.com/public/developer/en/ps/5002.EPSF_Spec.pdf
  header = fread(21)
  if len(header) < 15:
    raise ValueError('Too short for ps.')
  has_preview = False
  if header.startswith('\xc5\xd0\xd3\xc6') and ord(header[4]) >= 30 and header[5 : 8] == '\0\0\0':
    # EPS binary header, assuming that 32 <= eps_ofs <= 255.
    # Format: magic, eps_ofs, eps_size, wmf_ofs, wmf_size, tiff_ofs, tiff_size, checksum = struct.unpack('<46LH', header[:30])
    eps_ofs, = struct.unpack('<L', header[4 : 8])
    has_preview = True
    assert eps_ofs >= len(header)
    header = fskip(eps_ofs - len(header)) and fread(21)
    if not header:
      info['format'], info['subformat'], info['has_preview'] = 'ps', 'preview', True
      return
    if len(header) < 15:
      raise ValueError('EOF before eps section.')
  if not ((header.startswith('%!PS-Adobe-') and
           header[11] in '123' and header[12] == '.') or
          header.startswith('%!PS\r\n%%BoundingBox: ') or
          (header.startswith('%!PS') and header[4] in '\r\n' and
           header[5 : 20] == '%%BoundingBox: ')):
    raise ValueError('ps signature not found.')
  info['format'], info['has_preview'] = 'ps', has_preview
  i = 0
  data, header = header, ''
  for _ in xrange(8):
    # Slow copy, but doable 8 times.
    header += data.replace('\r\n', '\n').replace('\r', '\n').replace('\t', ' ')
    i = header.find('\n', i)
    while i >= 0:
      if header[i + 1 : i + 3] != '%%':
        i = -i
      else:
        i = header.find('\n', i + 3)
    if i < -1:
      header = header[:-i]
      break
    data = fread(256)
    if not data:
      break
  header = header.split('\n')
  if header[0] == '%!PS':
    info['subformat'] = 'mps'  # Old version: '%%Creator: MetaPost\n'.
  elif ' EPSF-' in header[0]:
    info['subformat'] = 'eps'
  else:
    info['subformat'] = 'ps'
  for line in header:
    if line == '%%EndComments':
      break
    if line.startswith('%%BoundingBox: ') and 'width' not in info:
      # We ignore HiResBoundingBox and ExactBoundingBox.
      try:
        bbox = map(float, line.split()[1:])
      except ValueError:
        bbox = ()
      if len(bbox) != 4:
        raise ValueError('Bad ps ' + line)
      def bbox_entry_to_int(value):
        if value < 0:
          return -int(.5 - value)
        else:
          return int(value + .5)
      wd_ht = (bbox[2] - bbox[0], bbox[3] - bbox[1])
      if wd_ht[0] < 0 or wd_ht[1] < 0:
        raise ValueError('Expected positive size for ps ' + line)
      wd_ht = map(bbox_entry_to_int, wd_ht)
      info['width'], info['height'] = (wd_ht[0] or 1, wd_ht[1] or 1)


def analyze_wmf(fread, info, fskip, format='wmf', fclass='vector',
                spec=((0, '\xd7\xcd\xc6\x9a\0\0'),
                      (0, ('\1\0\x09\0\0', '\2\0\x09\0\0'), 5, ('\1', '\3'), 16, '\0\0'))):
  # https://en.wikipedia.org/wiki/Windows_Metafile
  # https://www.fileformat.info/format/wmf/egff.htm
  # https://docs.microsoft.com/en-us/openspecs/windows_protocols/ms-wmf/4813e7fd-52d0-4f42-965f-228c8b7488d2
  # https://winprotocoldoc.blob.core.windows.net/productionwindowsarchives/MS-WMF/%5bMS-WMF%5d.pdf
  data = fread(6)
  if len(data) < 6:
    raise ValueError('Too short for wmf.')
  if data == '\xd7\xcd\xc6\x9a\0\0':  # META_PLACEABLE.
    info['format'] = 'wmf'
    data = fread(14)
    if len(data) == 14:
      left, top, right, bottom, inch, reserved = struct.unpack('<5HL', data)
      if reserved:
        raise ValueError('Bad wmf placeable Reserved.')
      if not inch:
        raise ValueError('Bad wmf placeable Inch.')
      width, height = abs(left - right), abs(top - bottom)  # Weird signs for width.
      width = (width * 72 + (inch >> 1)) // inch   # Convert to pt.
      height = (height * 72 + (inch >> 1)) // inch   # Convert to pt.
      info['width'], info['height'] = width, height
  elif data[0] in '\1\2' and data[1 : 5] == '\0\x09\0\0' and data[5] in '\1\3':  # META_HEADER.
    data = fread(12)
    if len(data) < 12:
      raise ValueError('EOF in wmf META_HEADER.')
    if data[10 : 12] != '\0\0':
      raise ValueError('Bad wmf NumberOfMembers.')
    info['format'] = 'wmf'
  else:
    raise ValueError('wmf signature not found.')


def analyze_emf(fread, info, fskip, format='emf', fclass='vector',
                spec=(0, '\1\0\0\0', 5, '\0\0\0', 40, ' EMF\0\0\1\0', 58, '\0\0')):
  "Analyzes an EMF (Enhanced Metafile) or EMF+ file."""
  # https://en.wikipedia.org/wiki/Windows_Metafile
  # https://docs.microsoft.com/en-us/openspecs/windows_protocols/ms-emf/91c257d7-c39d-4a36-9b1f-63e3f73d30ca
  # https://winprotocoldoc.blob.core.windows.net/productionwindowsarchives/MS-EMF/%5bMS-EMF%5d.pdf
  # https://docs.microsoft.com/en-us/openspecs/windows_protocols/ms-emfplus/5f92c789-64f2-46b5-9ed4-15a9bb0946c6
  # https://winprotocoldoc.blob.core.windows.net/productionwindowsarchives/MS-EMFPLUS/%5bMS-EMFPLUS%5d.pdf
  data = fread(60)
  if len(data) < 60:
    raise ValueError('Too short for emf.')
  if not (data.startswith('\1\0\0\0') and data[5 : 8] == '\0\0\0' and
          data[40: 48] == ' EMF\0\0\1\0' and data[58 : 60] == '\0\0'):
    raise ValueError('emf signature not found.')
  info['format'] = info['subformat'] = 'emf'
  size, left, top, right, bottom = struct.unpack('<4xL16xllll20x', data)
  if not 88 <= size < 256 or size & 3:
    raise ValueError('Bad emf header size: %d' % size)
  width, height = abs(left - right), abs(top - bottom)
  inch = 2540  # Unit of width and height: .01mm.
  width = (width * 72 + (inch >> 1)) // inch   # Convert to pt.
  height = (height * 72 + (inch >> 1)) // inch   # Convert to pt.
  info['width'], info['height'] = width, height
  if fskip(size - 60):
    data = fread(28)
    if len(data) == 28 and data.startswith('F\0\0\0') and data[12 : 18] == 'EMF+\1@':
      size, data_size, flags, size2, data_size2 = struct.unpack('<4xLL6xHLL', data)
      if flags & 1:
        info['subformat'] = 'dual'  # Both EMF (GDI) and EMF+ (GDI+).
      else:
        info['subformat'] = 'emfplus'
      if not (data_size2 > 0 and size2 >= 12 + ((data_size2 + 3) & ~3)):
        raise ValueError('Bad emf+ data_size2.')
      if not (data_size >= size2 + 4 and size >= 12 + ((data_size + 3) & ~3)):
        raise ValueError('Bad emf+ data_size.')
      if size < 32 or size & 3:
        raise ValueError('Bad emf+ size.')


# https://en.wikibooks.org/wiki/LaTeX/Lengths#Units
# 'ex' and 'em' are missing here, because they are font-specific.
TEX_DIMEN_MULTIPLIERS = {  # When converting to bp.
    'bp': 1,
    'pt': 72 / 72.27,
    'in': 72,
    'mm': 72 / 25.4,
    'cm': 72 / 2.54,
    'sp': 72 / (65536 * 72.27),
    'pc': 12 * 72 / 72.27,
    'dd': 1238 * 72 / (72.27 * 1157),
    'cc': 1238 * 12 * 72 / (72.27 * 1157),
    'nd': 685 * 72 / (72.27 * 642),
    'nc': 685 * 12 * 72 / (72.27 * 642),
}


def parse_tex_dimen(data):
  data = data.lower().strip()
  if len(data) < 2 or data[-2:] not in TEX_DIMEN_MULTIPLIERS:
    raise ValueError('Bad unit in TeX dimension: %r' % data)
  multiplier = TEX_DIMEN_MULTIPLIERS[data[-2:]]
  data = data[:-2].rstrip()
  if ('e' in data or '.' in data) and (data[0].isdigit() or data[0] == '.') and data[-1].isdigit():  # Floating point, e.g. 2e3.
    data = float(data) * multiplier
  elif data and data.isdigit():
    data = int(data) * multiplier
  else:
    # This also disallows negative.
    raise ValueError('Bad number in TeX dimension: %r' % data)
  if isinstance(data, float):
    data = int(data + .5)  # Round to neariest integer.
  return data


def analyze_dvi(fread, info, fskip, format='dvi', fclass='doc',
                # Bytes at offset 8 are numerator and denominator: struct.pack('>LL', 25400000, 473628672).
                spec=(0, '\367', 1, ('\002', '\003'), 2, '\001\203\222\300\034;\0\0')):
  # http://mirror.utexas.edu/ctan/dviware/driv-standard/level-0/dvistd0.pdf
  # http://www.pirbot.com/mirrors/ctan/dviware/driv-standard/level-0/dvistd0.pdf
  data = fread(10)
  if len(data) < 10:
    raise ValueError('Too short for dvi.')
  pre, version, num, den = struct.unpack('>BBLL', data)
  if pre != 247 or version not in (2, 3):
    raise ValueError('dvi signature not found.')
  if num != 25400000:
    raise ValueError('Bad num: (num, den)=(%d, %d)', (num, den))
  if den != 473628672:
    raise ValueError('Bad den: (num, den)=(%d, %d)', (num, den))
  info['format'] = 'dvi'
  data = fread(5)
  if len(data) < 5:
    return
  mag, comment_size = struct.unpack('>LB', data)
  if not fskip(comment_size):
    return
  while 1:
    c = fread(1)
    if not c:
      raise ValueError('EOF before dvi command.')
    b = ord(c)
    if b < 128 or b in (138, 140, 141, 142, 142, 147, 152, 161, 166) or 171 <= b <= 234:
      continue
    elif b in (128, 133, 143, 148, 153, 157, 162, 167, 235):
      n = 1
    elif b in (129, 134, 144, 149, 154, 158, 163, 168, 236):
      n = 2
    elif b in (130, 135, 145, 150, 155, 159, 164, 169, 237):
      n = 3
    elif b in (131, 136, 146, 151, 156, 160, 165, 170, 238):
      n = 4
    elif b in (132, 137):
      n = 8
    elif b == 139:
      n = 44
    elif b in (243, 244, 245, 246):  # Font definition.
      if not fskip(b - 230):
        break
      c = fread(2)
      if len(c) < 2 or not fskip(ord(c[0]) + ord(c[1])):
        break
      continue
    elif b in (248, 140):  # End of first page, stop parsing.
      return
    elif b in (239, 240, 241, 242):  # Special.
      c = '\0' * (242 - b) + fread(b - 238)
      if len(c) != 4:
        break
      n, = struct.unpack('>L', c)
      if n <= 2048:  # Not too long.
        c = fread(n)
        if len(c) < n:
          break
        if not c.startswith('papersize='):
          continue
        c = c[c.find('=') + 1:].split(',')
        if len(c) < 2:
          raise ValueError('Missing comma in papersize= special.')
        width = parse_tex_dimen(c[0])
        height = parse_tex_dimen(c[1])
        info['width'], info['height'] = width, height
        return
    else:
      raise ValueError('Bad dvi command: %d' % b)
    if not fskip(n):
      break  # EOF in dvi command argument.
  raise ValueError('EOF in dvi command.')


MAC_TYPE_MAP = {
    'jpeg': ('jpeg', 'jpeg'),
    'jfif': ('jpeg', 'jpeg'),
    'png':  ('png', 'flate'),
    'pngf': ('png', 'flate'),
    'pngr': ('png', 'flate'),
    'giff': ('gif', 'lzw'),
    'gif':  ('gif', 'lzw'),
    'bmpf': ('bmp', None),
    'bmpp': ('bmp', None),
    'bmp':  ('bmp', None),
    'bmap':  ('bmp', None),
    'epsf': ('ps', 'code'),
    'eps':  ('ps', 'code'),
    'pcx':  ('pcx', 'rle'),
    'pcxf':  ('pcx', 'rle'),
    'pcxx':  ('pcx', 'rle'),
    'pict': ('pict', 'code'),
    'pntg': ('macpaint', 'rle'),
    'targ': ('tga', None),
    'tga': ('tga', None),
    'tga1': ('tga', None),
    'tpic': ('tga', None),
    'iff': ('lbm', None),
    'ilbm': ('lbm', None),
    'tiff': ('tiff', None),
    'tif':  ('tiff', None),
    'qtif':  ('qtif', None),
    'kpcd': ('photocd', 'photocd'),
    'jp2': ('jpeg2000', None),
    'jp': ('jpeg2000', None),
    'sit!': ('stuffit', False),
    'sitd': ('stuffit', False),
    'sit2': ('stuffit', False),
    'sit5': ('stuffit', False),
    'pdf': ('pdf', False),
    '8bim': ('psd', False),
    #'appl': ('mac-executable', False),
    #'text': ('text', 'uncompressed'),
    #'mswd': ('microsoft-word', False),
    # TODO(pts): Add more, from types.lst.
}


def limit_fread_and_fskip(fread, fskip, data_size):
  fread_up, fskip_up, remaining_ary = fread, fskip, [int(data_size)]
  del data_size  # Save memory.

  def fread(size):
    data = fread_up(min(size, remaining_ary[0]))
    remaining_ary[0] -= len(data)
    return data

  def fskip(size):
    if size > remaining_ary[0]:
      return False
    remaining_ary[0] -= size
    return fskip_up(size)

  return fread, fskip


def get_string_fread_fskip(data):
  i_ary = [0]

  def fread(n):
    result = data[i_ary[0] : i_ary[0] + n]
    i_ary[0] += len(result)
    return result

  def fskip(n):
    return len(fread(n)) == n

  return fread, fskip


def analyze_by_format(fread, info, fskip, format, data_size):
  if format == 'bmp':  # TODO(pts): Add more, use autogenerated map.
    analyze_func = analyze_bmp
  elif format == 'tiff':
    analyze_func = analyze_tiff
  elif format == 'jpeg':
    analyze_func = analyze_jpeg
  elif format == 'png':
    analyze_func = analyze_png
  elif format == 'jpeg2000':
    analyze_func = noformat_analyze_jpeg2000
  elif format == 'photocd':
    analyze_func = analyze_photocd
  elif format == 'lbm':
    analyze_func = analyze_lbm
  elif format == 'tga':
    analyze_func = analyze_tga
  elif format == 'qtif':
    analyze_func = analyze_qtif  # TODO(pts): Isn't it analyze_tiff instead?
  elif format == 'jpegxl':
    analyze_func = analyze_jpegxl
  elif format == 'jpegxl-brunsli':
    analyze_func = analyze_brunsli
  elif format == 'jpegxr':
    analyze_func = analyze_jpegxl
  elif format == 'ico':
    analyze_func = analyze_ico
  elif format == 'cur':
    analyze_func = analyze_cur
  elif format == 'xbm':
    analyze_func = analyze_xbm
  elif format == 'pict':
    analyze_func = analyze_pict
  elif format == 'macpaint':
    analyze_func = analyze_macpaint
  elif format == 'psd':
    analyze_func = analyze_psd
  elif format == 'pdf':
    analyze_func = analyze_pdf
  else:
    info['format'] = format
    return
  if data_size is not None:
    fread, fskip = limit_fread_and_fskip(fread, fskip, data_size)
  analyze_func(fread, info, fskip)


def quick_detect_image_format(header):
  """Detect a few image formats with an easy magic, and which are usually
  embedded."""
  header = header[:8]  # Limit functionality to easy magic.
  # TODO(pts): Add more image file formats.
  if header.startswith('\0\0\0\x0cjP  ') or header.startswith('\xff\x4f\xff\x51\0'):
    return 'jpeg2000'
  elif header.startswith('\x89PNG\r\n\x1a\n'):
    return 'png'
  elif header.startswith('GIF87a') or header.startswith('GIF89a'):
    return 'gif'
  elif header.startswith('\xff\xd8\xff'):
    return 'jpeg'
  elif header.startswith('BM'):
    return 'bmp'
  elif header.startswith('MM\x00\x2a') or header.startswith('II\x2a\x00'):
    return 'tiff'
  elif header.startswith('\xff\xff\xff\xff\xff\xff\xff\xff'):
    return 'photocd'
  elif header.startswith('FORM'):  # Analyze 12 bytes, if available.
    return 'lbm'
  elif header.startswith('\xff\x0a'):
    return 'jpegxl'
  elif header.startswith('\x0a\x04B\xd2\xd5N'):
    return 'jpegxl-brunsli'
  elif header.startswith('WMPHOTO\0') or header.startswith('II\xbc\x01'):
    return 'jpegxr'
  elif header.startswith('\0\0\1\0'):
    return 'ico'
  elif header.startswith('#define'):
    return 'xbm'
  #elif (header.startswith('RIFF') and header[8 : 15] == 'WEBPVP8' and (header[15] or 'x') in ' LX'):  # Needs 12 bytes.
  #  return get_track_info_from_analyze_func(header, analyze_webp)
  #elif header.startswith('\0\0\0') and len(header) >= 12 and 8 <= ord(header[3]) <= 255 and header[4 : 12] == 'ftypmif1':  # Needs 12 bytes.
  #  return get_track_info_from_analyze_func(header, analyze_mov)  # HEIF or AVIF.
  else:
    return None



def count_is_pict_at_512(header):
  if header[10 : 15] == '\x11\1\1\0\x0a':
    return 500
  elif header[10 : 16] in ('\0\x11\2\xff\x0c\0', '\0\x11\2\xff\0\1'):
    return 600
  else:
    return 0


def analyze_pict(fread, info, fskip, header=''):
  # PICT: Apple QuickDraw vector graphics metadata (becore macOS with PDF).
  # https://developer.apple.com/library/archive/documentation/mac/pdf/Imaging_With_QuickDraw/Appendix_A.pdf
  # https://developer.apple.com/library/archive/documentation/mac/pdf/ImagingWithQuickDraw.pdf
  # http://mirrors.apple2.org.za/apple.cabi.net/Graphics/PICT.and_QT.INFO/PICT.file.format.TI.txt
  # https://www-jlc.kek.jp/subg/ir/study/latex/netpbm-10.18.14/converter/ppm/picttoppm.c
  # https://github.com/scummvm/scummvm/blob/master/image/pict.cpp
  # https://github.com/jsummers/deark/blob/master/modules/pict.c
  # http://mirror.informatimago.com/next/developer.apple.com/documentation/mac/QuickDraw/QuickDraw-461.html
  # https://woofle.net/impdf/QD-A-PictureOpcodes.pdf
  # https://github.com/ioquake/jedi-outcast/blob/master/utils/roq2/libim/impict.c
  # https://github.com/ewilded/upload-scanner/blob/master/bin/lib/Image/ExifTool/PICT.pm
  # http://fileformats.archiveteam.org/wiki/PackBits
  # https://developer.apple.com/library/archive/documentation/mac/pdf/Imaging_With_QuickDraw/Appendix_A.pdf
  # PixMap: http://mirror.informatimago.com/next/developer.apple.com/documentation/mac/QuickDraw/QuickDraw-202.html
  if len(header) > 23:
    raise ValueError('Initial header too long.')
  if len(header) < 17:  # 17 for the `len(header) <= 16' check below.
    header += fread(17 - len(header))
    if len(header) < 16:
      raise ValueError('Too short for pict.')
  # If it starts with '\0', then ignore the first 512 bytes.
  if not header[:16].rstrip('\0'):
    header += fread(32 - len(header))
    if len(header) == 32 and not header[16 : 32].rstrip('\0'):
      if fskip(512 - 32):
        header = fread(17)
        if len(header) < 15:
          raise ValueError('Too short for pict after 512 bytes.')
  if header[10 : 15] == '\x11\1\1\0\x0a':
    version, op, data = 1, 1, header[12:]
    data = header[13:]
  elif (header[10 : 14] in '\0\x11\2\xff' and
        header[14 : 16] in ('\x0c\0', '\0\1')):
    version, data = 2, header[16:]
    op, = struct.unpack('>H', header[14 : 16])
  else:
    raise ValueError('pict signature not found.')
  info['format'], info['subformat'] = 'pict', str(version)
  top, left, bottom, right = struct.unpack('>2x4H', header[:10])  # picFrame.
  if top > bottom or left > right:
    raise ValueError('Bad pict picFrame.')
  info['width'] = info['pt_width'] =  right - left
  info['height'] = info['pt_height'] = bottom - top
  if len(header) <= 16:
    return
  while 1:
    #print 'op=0x%x %r' % (op, data)
    if op == 0xff:  # OpEndPic.
      break
    elif op == 0xc00:  # HeaderOp.
      assert len(data) <= 24
      data += fread(24 - len(data))
      if len(data) < 24:
        raise ValueError('EOF in pict headerop.')
      if version == 2 and data.startswith('\xff\xfe'):
        info['subformat'] = '2ext'
    elif op == 1:  # Clip.
      if len(data) < 2:
        data += fread(2 - len(data))
        if len(data) < 2:
          raise ValueError('EOF in pict clip.')
      size, = struct.unpack('>H', data[:2])
      if size != 10:
        raise ValueError('Bad pict clip size.')
      assert len(data) <= size
      if len(data) < size:
        data += fread(size - len(data))
        if len(data) < size:
          raise ValueError('EOF in pict clip.')
    elif op == 0xa0:  # ShortComment.
      assert not data
      data = fread(2)
      if len(data) < 2:
        raise ValueError('EOF in pict shortcomment.')
    elif op == 0x1f:  # OpColor.
      assert not data
      data = fread(6)
      if len(data) < 6:
        raise ValueError('EOF in pict opcolor.')
    elif op == 0xa1:  # LongComment.
      assert not data
      data = fread(4)
      if len(data) < 4:
        raise ValueError('EOF in pict longcomment size.')
      size, = struct.unpack('>2xH', data)
      if not fskip(size):
        raise ValueError('EOF in pict longcomment.')
    elif op in (0, 0x1e):  # NOP, DefHilite.
      pass
    elif op in (0x90, 0x91, 0x98, 0x99, 0x9a, 0x9b):  # BitsRect, BitsRgn, PackBitsRect, PackBitsRgn, DirectBitsRect, DirectBitsRgn.
      assert not data
      data = fread(14)
      if len(data) < 14:
        raise ValueError('EOF in pict sampled op.')
      if op in (0x9a, 0x9b):
        if not data.startswith('\0\0\0\xff'):
          raise ValueError('Bad pict sampled baseaddr.')
        fmt = '>6xHHHH'
      else:
        fmt = '>2xHHHH4x'
      top, left, bottom, right = struct.unpack(fmt, data)  # bounds.
      if top > bottom or left > right:
        raise ValueError('Bad pict sampled bounds.')
      info['sampled_format'], info['codec'], info['width'], info['height'] = 'pict', 'rle', right - left, bottom - top
      break  # Found first sampled image, stop looking for more (for simplicity).
    elif op == 0x8200:  # CompressedQuicktime.
      assert not data
      data = fread(72)
      if len(data) < 72:
        raise ValueError('EOF in pict compressedquicktime.')
      size, matte_size, mask_size = struct.unpack('>L38xL22xL', data)
      if size < 86 + 68 + 4:
        raise ValueError('pict compressedquicktime size too small.')
      skip_size = (matte_size and 4) + matte_size + mask_size
      if not fskip(skip_size):
        raise ValueError('EOF in pict matte or mask.')
      data = fread(86)  # ImageDescription.
      if len(data) < 86:
        raise ValueError('EOF in pict imagedescription.')
      (id_size, codec_tag, res1, res2, data_ref_index, id_version, vendor,
       temporal_quality, quality, width, height, resolution_x, resolution_y,
       data_size, frame_count, format_desc, depth, clut_id,
      ) = struct.unpack('>L4sLHHL4sLLHHLLLH32sHH', data)
      if id_size < 86:
        raise ValueError('pict imagedescription too short.')
      data_size = size - 68 - id_size - skip_size
      if data_size < 0:
        raise ValueError('pict compressedquicktime too small for data.')
      info['width'], info['height'] = width, height
      if not fskip(id_size - 86):
        raise ValueError('EOF in pict imagedescription.')
      codec_tag = codec_tag.strip().strip('.').lower()
      if codec_tag in MAC_TYPE_MAP:
        format, codec = MAC_TYPE_MAP[codec_tag]
        if codec is False:
          pass
        elif codec:
          info['sampled_format'], info['codec'] = format, codec
        else:
          info['sampled_format'] = format
          subformat = info.pop('subformat')
          try:
            analyze_by_format(fread, info, fskip, format, data_size)
          finally:
            info['sampled_format'], info['format'] = info['format'], 'pict'
            if 'subformat' in info:
              info['sampled_subformat'] = info['subformat']
            info['subformat'] = subformat
      else:
        info['sampled_format'] = ('?', codec_tag)[codec_tag.isalnum()]
      break  # Found first sampled image, stop looking for more (for simplicity).
    else:  # Unsupported op.
      break
    data = fread(version)  # Read next op.
    if len(data) < version:
      raise ValueError('EOF in pict op.')
    op, = struct.unpack(('', '>B', '>H')[version], data)
    data = ''


add_format(format='?-zeros8', fclass='other', spec=(0, '\0' * 8))
add_format(format='?-zeros16', fclass='other', spec=(0, '\0' * 16))


def analyze_zeros32_64(fread, info, fskip, format='?-zeros32-64', extra_formats=('?-zeros32', '?-zeros64',),
                       spec=((0, '\0' * 32), (0, '\0' * 64))):
  # ``ISO 9660 CD-ROM filesystem data'' typically ends up in this format, because it starts with 40960 '\0' bytes (unless bootable).
  header = fread(32)
  if len(header) < 32:
    raise ValueError('Too short for zeros32.')
  if header.rstrip('\0'):
    raise ValueError('zeros32 signature not found.')
  header = fread(32)
  if len(header) == 32 and not header.rstrip('\0'):
    info['format'] = '?-zeros64'
  else:
    info['format'] = '?-zeros32'
  if len(header) == 32 and fskip(512 - 64):
    header = fread(16)  # At offset 512.
    if count_is_pict_at_512(header):
      analyze_pict(fread, info, fskip, header=header)


def is_vp8(header):
  if len(header) < 10 or header[3 : 6] != '\x9d\x01\x2a':
    return False
  size, width, height = struct.unpack('<L2xHH', header[:10])
  return ((size & 0xffffff) >> 5 and not size & 1 and ((size >> 1) & 7) <= 3 and
          size & 16 and width & 0x3fff and height & 0x3fff)


def get_vp8_track_info(header):
  # https://tools.ietf.org/html/rfc6386
  if len(header) < 10:
    raise ValueError('Too short for vp8.')
  size, signature, width, height = struct.unpack('<LHHH', header[:10])
  if size >> 24 != 157 or signature != 10753:  # \x9d\x01\x2a'.
    raise ValueError('vp8 signature not found.')
  size &= 0xffffff
  if not size >> 5:
    return ValueError('Bad vp8 frame size.')
  if size & 1:
    return ValueError('First vp8 frame must be keyframe.')
  if ((size >> 1) & 7) > 3:
    return ValueError('Bad vp8 frame version.')
  if not size & 16:
    return ValueError('Bad vp8 frame no-show.')
  size >>= 5
  width &= 0x3fff
  height &= 0x3fff
  if not (width and height):
    raise ValueError('Bad vp8 frame dimensions.')
  return {'type': 'video', 'codec': 'vp8', 'width': width, 'height': height}


def analyze_vp8(fread, info, fskip, format='vp8', fclass='video',
                spec=(3, '\x9d\x01\x2a', 10, lambda header: (is_vp8(header), 150))):
  header = fread(10)
  track_info = get_vp8_track_info(header)
  info['format'], info['tracks'] = 'vp8', [track_info]


def is_webp(header):
  if not (len(header) >= 26 and header.startswith('RIFF') and
          header[8 : 15] == 'WEBPVP8' and header[15] in ' LX'):
    return False
  if header[15] == 'X':  # https://developers.google.com/speed/webp/docs/riff_container#extended_file_format
    if len(header) < 30:
      return False
    size1, size2, flags = struct.unpack('<L8xLL', header[4 : 24])
    return size1 >= 18 and size2 == 10 and not (flags & ~0x3f)
  else:
    if header[15] == ' ' and header[23 : 26] != '\x9d\x01\x2a':
      return False
    if header[15] == 'L' and header[20] != '\x2f':
      return False
    size1, size2 = struct.unpack('<4xL8xL', header[:20])
    return size1 - size2 == 12 and size2 > 6


def analyze_webp(fread, info, fskip):
  header = fread(30)
  if len(header) < 26:
    raise ValueError('Too short for webp.')
  if not (header.startswith('RIFF') and
          header[8 : 15] == 'WEBPVP8' and header[15] in ' LX'):
    raise ValueError('webp signature not found.')
  info['format'] = 'webp'
  if header[15] == 'X':  # https://developers.google.com/speed/webp/docs/riff_container#extended_file_format
    info['subformat'] = 'extended'
    if len(header) < 30:
      raise ValueError('Too short for webp extended.')
    size1, size2, flags, wdl, wdh, htl, hth = struct.unpack('<L8xLLBHBH', header[4 : 30])
    if size1 < 18:
      return ValueError('webp extended too short.')
    if size2 != 10:
      return ValueError('Bad webp extended header size.')
    if flags & ~0x3f:
      return ValueError('Bad webp extended header flags: 0x%x' % flags)
    info['width'], info['height'] = (wdl | wdh << 8) + 1, (htl | hth << 8) + 1
    # We could parse more chunks including the 'VP8 ' or 'VP8L' chunk to get
    # info['codec'].
  else:
    size1, size2 = struct.unpack('<4xL8xL', header[:20])
    if size1 - size2 != 12:
      raise ValueError('Bad webp size difference.')
  if header[15] == ' ':
    # https://tools.ietf.org/html/rfc6386
    if header[23 : 26] != '\x9d\x01\x2a':
      raise ValueError('webp lossy signature not found.')
    if size2 < 10:
      raise ValueError('webp lossy too short.')
    header = header[20:]
    if len(header) < 10:
      header += fread(10 - len(header))
    track_info = get_vp8_track_info(header)
    for key in ('codec', 'width', 'height'):
      info[key] = track_info[key]
  elif header[15] == 'L':
    # https://developers.google.com/speed/webp/docs/webp_lossless_bitstream_specification
    if header[20] != '\x2f':
      raise ValueError('webp lossless signature not found.')
    if size2 < 6:
      raise ValueError('webp lossless too short.')
    v, = struct.unpack('<L', header[21 : 25])
    if (v >> 29) & 7:
      raise ValueError('Bad webp lossless version.')
    info['width'] = 1 + (v & 0x3fff)
    info['height'] = 1 + ((v >> 14) & 0x3fff)
    info['codec'] = 'webp-lossless'


def is_vp9(header):
  if len(header) < 10:
    return False
  b = ord(header[4])
  if header[1 : 4] == '\x49\x83\x42' and header[0] in '\x80\x81\x82\x83\xa0\xa1\xa2\xa3':
    profile = (ord(header[0]) >> 4) & 3  # profile=0,1,2
    # (0: uuu? or 111), (2: ?uuu? or ?111), (1: uuu???0 or 1110).
    return profile != 1 or (b & (2, 16)[((b >> 5) & 7) == 7]) == 0
  elif header[2 : 4] == '\xc1\xa1' and header[0] in '\xb0\xb1' and header[1] in '\x24\xa4':
    # profile = 3
    if ((b >> 3) & 7) == 7:  # CS_RGB.
      return (b & 132) == 0
    return ((b | ord(header[5])) & 128) == 0


def get_vp9_track_info(header):
  # https://storage.googleapis.com/downloads.webmproject.org/docs/vp9/vp9-bitstream-specification-v0.6-20160331-draft.pdf
  if len(header) < 10:
    raise ValueError('Too short for vp9.')
  # Now header contains the first 10 bytes of the first frame: a keyframe.
  b = ord(header[4])
  if header[1 : 4] == '\x49\x83\x42' and header[0] in '\x80\x81\x82\x83\xa0\xa1\xa2\xa3':
    profile = (ord(header[0]) >> 4) & 3  # profile=0,1,2
    if not (profile != 1 or (b & (2, 16)[((b >> 5) & 7) == 7]) == 0):
      raise ValueError('Bad bits for vp9 profile=%d' % profile)
    is_cs_rgb = ((b >> (5 - (profile == 2))) & 3) == 7
  elif header[2 : 4] == '\xc1\xa1' and header[0] in '\xb0\xb1' and header[1] in '\x24\xa4':
    profile = 3  # (3: 0?uuu???0 or 0?1110)
    is_cs_rgb = ((b >> 3) & 7) == 7
    if (((b | ord(header[5])) & 128), b & 132)[is_cs_rgb]:
      raise ValueError('Bad bits for vp9 profile=3')
  else:
    raise ValueError('vp9 signature not found.')
  d = (4, 7, 5, 9, 3, 4, 4, 6)[profile + (is_cs_rgb << 2)]
  width, height = [int((struct.unpack('>L', header[i : i + 4])[0] >> (16 - d)) & 0xffff) + 1 for i in (4, 6)]
  return {'type': 'video', 'codec': 'vp9', 'width': width, 'height': height}


def analyze_vp9(fread, info, fskip, format='vp9', fclass='video',
                spec=(0, ('\x80\x49\x83\x42', '\x81\x49\x83\x42', '\x82\x49\x83\x42', '\x83\x49\x83\x42', '\xa0\x49\x83\x42', '\xa1\x49\x83\x42', '\xa2\x49\x83\x42', '\xa3\x49\x83\x42', '\x90\x49\x83\x42', '\x91\x49\x83\x42', '\x92\x49\x83\x42', '\x93\x49\x83\x42', '\xb0\x24\xc1\xa1', '\xb0\xa4\xc1\xa1', '\xb1\x24\xc1\xa1', '\xb1\xa4\xc1\xa1'), 10, lambda header: (is_vp9(header), 20))):
  header = fread(10)
  track_info = get_vp9_track_info(header)
  info['format'], info['tracks'] = 'vp9', [track_info]


def get_av1_track_info(header):
  # https://aomediacodec.github.io/av1-spec/
  # https://aomediacodec.github.io/av1-spec/av1-spec.pdf
  #
  # https://aomediacodec.github.io/av1-spec/#ordering-of-obus states:
  #
  # * First few OBUs are: temporal delimiter, sequence header, metadata (0 or more), frame.
  # * The first frame (OBU_FRAME) header has frame_type equal to KEY_FRAME, show_frame equal to 1, show_existing_frame equal to 0, and temporal_id equal to 0.
  #
  # Limitations:
  #
  # * We don't support obu_extension_flag=1.
  # * Largest sequence header size we support is 127 because of leb128 parsing.
  if len(header) < 4:
    raise ValueError('Too short for av1.')
  seqhead_size = ord(header[3])
  if not header.startswith('\x12\0\x0a') or not 4 <= seqhead_size <= 127:
    raise ValueError('av1 signature not found.')
  # TODO(pts): Check that seqhead_size is long enough.
  bits = get_bitstream(buffer(header, 4))

  def read_1():
    for b in bits:
      return b == '1'
    raise ValueError('EOF in av1.')

  def read_u(n):
    result = i = 0
    if n > 0:
      for b in bits:
        result = result << 1 | (b == '1')
        i += 1
        if i == n:
          break
      if i != n:
        raise ValueError('EOF in av1.')
    return result

  def skip_uvlc():
    lzc = 0
    while not read_1():
      lzc += 1
    if lzc < 32:
      read_u(lcz)

  for b in bits:
    break
  else:
    return {'type': 'video', 'codec': 'av1'}  # Just 4 bytes of header.

  seq_profile = (b == '1') << 2 | read_u(2)
  still_picture = read_1()
  reduced_still_picture_header = read_1()
  if reduced_still_picture_header:
    read_u(5)  # seq_level_idx.
  else:
    if read_1():  # timing_info_present_flag.
      read_u(32)
      read_u(32)
      if read_1():
        skip_uvlc()
      decoder_model_info_present_flag = read_1()
      if decoder_model_info_present_flag:
        buffer_delay_length_minus_1 = read_u(5)
        read_u(32)
        read_u(5 + 5)
    else:
      decoder_model_info_present_flag = buffer_delay_length_minus_1 = 0
    initial_display_delay_present_flag = read_1()
    for _ in xrange(read_u(5) + 1):
      read_u(12)
      seq_level_idx = read_u(5)
      if seq_level_idx > 7:
        read_1()
      if decoder_model_info_present_flag:
        if read_1():
          read_u(3 + (buffer_delay_length_minus_1 << 1))
      if initial_display_delay_present_flag:
        if read_1():
          read_u(4)
  frame_width_bits_minus_1 = read_u(4)
  frame_height_bits_minus_1 = read_u(4)
  width = read_u(frame_width_bits_minus_1 + 1) + 1
  height = read_u(frame_height_bits_minus_1 + 1) + 1
  # Sequence header OBU continues here, but we stop parsing.
  return {'type': 'video', 'codec': 'av1', 'width': width, 'height': height}


def analyze_av1(fread, info, fskip, format='av1', fclass='video',
                spec=(0, '\x12\0\x0a', 3, tuple(chr(c) for c in xrange(4, 128)))):
  header = fread(131)
  track_info = get_av1_track_info(header)
  info['format'], info['tracks'] = 'av1', [track_info]
  info['tracks'] = [track_info]


def is_dirac(header):
  return (len(header) >= 14 and header.startswith( 'BBCD\0\0\0\0') and
          header[9 : 13] == '\0\0\0\0' and ord(header[8]) >= 14)


DIRAC_VIDEO_DIMENSIONS = (
    (640, 480),
    (176, 120),
    (176, 144),
    (352, 240),
    (352, 288),
    (704, 480),
    (704, 576),
    (720, 480),
    (720, 576),
    (1280, 720),
    (1280, 720),
    (1920, 1080),
    (1920, 1080),
    (1920, 1080),
    (1920, 1080),
    (2048, 1080),
    (4096, 2160),
)


def analyze_dirac(fread, info, fskip, format='dirac', fclass='video',
                  spec=(0, 'BBCD\0\0\0\0', 9, '\0\0\0\0', 14, lambda header: (is_dirac(header), 10))):
  # https://web.archive.org/web/20150503015104im_/http://diracvideo.org/download/specification/dirac-spec-latest.pdf
  # https://en.wikipedia.org/wiki/Dirac_(video_compression_format)
  header = fread(14)
  if len(header) < 14:
    raise ValueError('Too short for dirac.')
  signature, parse_code, next_parse_offset, previous_parse_offset = struct.unpack(
      '>4sBLLx', header)
  if signature != 'BBCD':
    raise ValueError('dirac signature not found.')
  if not 14 <= next_parse_offset <= 255:  # Maximum 140 bytes.
    raise ValueError('Bad dirac next_parse_offset: %d' % next_parse_offset)
  if previous_parse_offset:
    raise ValueError('Bad dirac previous_parse_offset.')
  if parse_code:
    raise ValueError('Bad dirac parse_code, expecting sequence_header: 0x%02x' % parse_code)
  info['format'] = 'dirac'
  info['tracks'] = [{'type': 'video', 'codec': 'dirac'}]
  header = header[13] + fread(next_parse_offset - 14)
  bitstream = get_bitstream(header)
  def read_1():
    return int(bitstream.next() == '1')
  def read_n(n):
    r = 0
    for _ in xrange(n):
      r = r << 1 | (bitstream.next() == '1')
    return r
  def read_varuint32():
    v, c = 1, 0
    while not read_1():
      if c >= 32:
        raise ValueError('dirac varuint32 too long.')
      c += 1
      v <<= 1
      if read_1():
        v += 1
    return v - 1
  try:
    version_major = read_varuint32()  # 2.
    version_minor  = read_varuint32()  # 2.
    profile = read_varuint32() # 8.
    level = read_varuint32()  # 0.
    base_video_format = read_varuint32()
    if read_1():  # custom_dimensions_flag.
      width = read_varuint32()
      height = read_varuint32()
    else:
      if base_video_format >= len(DIRAC_VIDEO_DIMENSIONS):
        raise ValueError('Bad base_video_format: %d' % base_video_format)
      width, height = DIRAC_VIDEO_DIMENSIONS[base_video_format]
  except StopIteration:
    raise ValueError('EOF in dirac sequence_header bitstream.')
  set_video_dimens(info['tracks'][0], width, height)


def analyze_theora(fread, info, fskip, format='theora', fclass='video',
                   spec=(0, '\x80theora', 7, ('\0', '\1', '\2', '\3', '\4', '\5', '\6', '\7'))):
  # https://theora.org/doc/Theora.pdf
  # https://web.archive.org/web/20040928224506/http://www.theora.org/doc/Theora_I_spec.pdf
  header = fread(20)
  if len(header) < 20:
    raise ValueError('Too short for theora.')
  signature, vmaj, vmin, vrev, fmbw, fmbh, picw_h, picw, pich_h, pich = struct.unpack(
      '>7sBBBHHBHBH', header)
  if signature != '\x80theora':
    raise ValueError('theora signature not found.')
  if vmaj > 7:  # Major version.
    raise ValueError('Bad theora vmaj: %d' % vmaj)
  info['format'] = 'theora'
  info['tracks'] = [{'type': 'video', 'codec': 'theora'}]
  set_video_dimens(info['tracks'][0], picw | picw_h << 16, pich | pich_h << 16)


def analyze_daala(fread, info, fskip, format='daala', fclass='video',
                  spec=(0, '\x80daala', 7, ('\0', '\1', '\2', '\3', '\4', '\5', '\6', '\7'))):
  # daala_decode_header_in in src/infodec.c in 	https://git.xiph.org/daala.git
  # https://en.wikipedia.org/wiki/Daala
  header = fread(17)
  if len(header) < 17:
    raise ValueError('Too short for daala.')
  signature, vmaj, vmin, vrev, width, height = struct.unpack(
      '>6sBBBLL', header)
  if signature != '\x80daala':
    raise ValueError('daala signature not found.')
  if vmaj > 7:  # Major version.
    raise ValueError('Bad daala vmaj: %d' % vmaj)
  if width > 0x7fffffff:
    raise ValueError('Bad daala width: %d' % width)
  if height > 0x7fffffff:
    raise ValueError('Bad daala height: %d' % width)
  info['format'] = 'daala'
  info['tracks'] = [{'type': 'video', 'codec': 'daala'}]
  set_video_dimens(info['tracks'][0], width, height)


def analyze_yuv4mpeg2(fread, info, fskip, format='yuv4mpeg2', fclass='video',
                      spec=(0, 'YUV4MPEG2 ')):
  # https://wiki.multimedia.cx/index.php/YUV4MPEG2
  # https://www.systutorials.com/docs/linux/man/5-yuv4mpeg/
  header = fread(10)
  if len(header) < 10:
    raise ValueError('Too short for yuv4mpeg2.')
  if header != 'YUV4MPEG2 ':
    raise ValueError('yuv4mpeg2 signature not found.')
  info['format'] = 'yuv4mpeg2'
  info['tracks'] = [{'type': 'video', 'codec': 'uncompressed', 'subformat': 'yuv4mpeg2'}]
  tags = {}
  header = ''
  while 1:
    data = fread(max(len(header), 32))
    if not data:
      raise ValueError('EOF in yuv4mpeg2 tags.')
    header += data
    del data  # Save memory.
    if '\n' in header:
      break
  header, data = header.split('\n', 1)
  if len(data) < 6:
    data += fread(6 - len(data))
  if not data.startswith('FRAME') and data[5] in ' \n':
    raise ValueError('Bad yuv4mpeg2 data frame.')
  if header.startswith(' ') or header.endswith(' ') or '  ' in header:
    raise ValueError('Bad yuv4mpeg2 header, contains too many spaces.')
  for item in header.split(' '):
    key, value = item[0], item[1:]
    if key not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
      raise ValueError('Bad yuv4mpeg2 tag key: %r' % key)
    if key in tags:
      raise ValueError('Duplicate yuv4mpeg2 tag key: %r' % key)
    if key in 'HW':
      try:
        value = int(value)
      except ValueError:
        value = -1
      if value < 0:
        raise ValueError('Bad yuv4mpeg2 tag %s value: %r' % (key, value))
    tags[key] = value
  if 'W' not in tags:
    raise ValueError('Missing yuv4mpeg2 tag W.')
  if 'H' not in tags:
    raise ValueError('Missing yuv4mpeg2 tag H.')
  info['tracks'][0]['colorspace'] = tags.get('C', '420jpeg')
  set_video_dimens(info['tracks'][0], tags['W'], tags['H'])


# https://en.wikipedia.org/wiki/RealVideo
REALVIDEO_CODECS = {
  'CLV1': 'clearvideo',
  'RV10': 'h263-rv10',
  'RV13': 'h263-rv13',
  'RV20': 'h263+-rv20',
  'RVTR': 'h263+-rvtr',
  'RV30': 'h264-rv30',
  'RVTR': 'h264-rvt2',
  'RV40': 'h264-rv40',
  'RV60': 'h265-rv60',
}


def get_realvideo_track_info(header):
  # https://en.wikipedia.org/wiki/RealVideo
  # https://github.com/MediaArea/MediaInfoLib/blob/4c8a5a6ef8070b3635003eade494dcb8c74e946f/Source/MediaInfo/Multiple/File_Rm.cpp#L414
  if header[:3] == '\0\0\0':
    header = buffer(header, 4)
  if len(header) < 12:
    raise ValueError('Too short for realvideo.')
  signature, codec, width, height = struct.unpack('>4s4sHH', buffer(header, 0, 12))
  if signature != 'VIDO':
    raise ValueError('realvideo signature not found.')
  if not ((codec.startswith('RV') and codec[2] in '123456789T' and codec[3].isalnum()) or codec == 'CLV1'):
    raise ValueError('Bad realvideo codec: %r' % codec)
  video_track_info = {'type': 'video', 'codec': REALVIDEO_CODECS.get(codec, codec.lower())}
  set_video_dimens(video_track_info, width, height)
  return video_track_info


def analyze_realvideo(fread, info, fskip, format='realvideo', fclass='video',
                      spec=((0, 'VIDO', 8, lambda header: ((header[4 : 6] == 'RV' and header[6] in '123456789T' and header[7].isalnum()) or header[4 : 8] == 'CLV1', 350)),
                            (0, '\0\0\0', 4, 'VIDO', 12, lambda header: (ord(header[3]) >= 32 and (header[8 : 10] == 'RV' and header[10] in '123456789T' and header[11].isalnum()) or header[8 : 12] == 'CLV1', 400)))):
  # https://en.wikipedia.org/wiki/RealVideo
  # https://github.com/MediaArea/MediaInfoLib/blob/4c8a5a6ef8070b3635003eade494dcb8c74e946f/Source/MediaInfo/Multiple/File_Rm.cpp#L414
  header = fread(4)
  if header.startswith('\0\0\0') and ord(header[3]) >= 32:
    header = fread(12)
  else:
    header += fread(8)
  if header.startswith('VIDO') and len(header) >= 12:
    info['format'] = 'realvideo'
  info['tracks'] = [get_realvideo_track_info(header)]


def count_is_jpegxr(header):
  if len(header) >= 8 and header.startswith('WMPHOTO\0'):
    return 800
  if len(header) >= 8 and header.startswith('II\xbc\x01') and not ord(header[4]) & 1:
    return 412


def analyze_jpegxr(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/JPEG_XR
  # Annex A of https://www.itu.int/rec/dologin_pub.asp?lang=e&id=T-REC-T.832-201906-I!!PDF-E&type=items
  # https://www.itu.int/rec/dologin_pub.asp?lang=e&id=T-REC-T.832-201906-I!!PDF-E&type=items
  header = fread(8)
  if len(header) < 8:
    raise ValueError('Too short for jpegxr.')
  if header.startswith('WMPHOTO\0'):
    info['format'] = info['codec'] = 'jpegxr'
    info['subformat'] = 'coded'
    header = fread(8)
    if len(header) < 8:
      raise ValueError('EOF in jpegxr coded header.')
    flags0, flags1, flags2, flags3, width, height = struct.unpack(
        '>BBBBHH', header)
    spatial_xfrm = (flags1 >> 3) & 7  # SPATIAL_XFRM_SUBORDINATE.
    if (flags0 | 8) != 0x19:
      raise ValueError('Bad jpegxr coded reserved0.')
    if not flags2 & 128:  # SHORT_HEADER_FLAG.
      header += fread(4)
      if len(header) < 12:
        raise ValueError('EOF in jpegxr coded long header.')
      width, height = struct.unpack('>4xLL')
    width += 1
    height += 1
    # TODO(pts): How to detect lossless JPEG-SR? by the quantization scaling
    # factor == 1? For lossless coding, the quantization scaling factor is
    # selected to be equal to 1. For lossy coding, the quantization scaling
    # factor is selected to be greater than 1.
  elif header.startswith('II\xbc\x01') and not ord(header[4]) & 1:
    info['format'] = info['codec'] = 'jpegxr'
    info['subformat'] = 'tagged'
    ifd_ofs, = struct.unpack('<4xL', header)
    if ifd_ofs < 8:
      raise ValueError('Bad jpegxr ifd_ofs: %d' % ifd_ofs)
    if not fskip(ifd_ofs - 8):
      raise ValueError('EOF before jpegxr ifd_ofs.')
    data = fread(2)
    if len(data) < 2:
      raise ValueError('EOF in jpegxr ifd_size.')
    ifd_count, = struct.unpack('<H', data)
    if ifd_count < 5:
      raise ValueError('jpegxr ifd_count too small: %d' % ifd_count)
    ifd_data = fread(12 * ifd_count)
    if len(ifd_data) != 12 * ifd_count:
      raise ValueError('EOF in jpegxr ifd_data.')
    width, height, spatial_xfrm = None, None, 0
    for i in xrange(0, len(ifd_data), 12):
      ie_tag, ie_type, ie_count, ie_value = struct.unpack(
          '<HHLL', buffer(ifd_data, i, 12))
      if ie_count == 1 and ie_type in (1, 2, 4):  # (UBYTE, USHORT, ULONG).
        if ie_type == 1:
          ie_value &= 0xff
        elif ie_type == 2:
          ie_value &= 0xffff
        #print ('0x%04x' % ie_tag, ie_type, ie_count, ie_value)
        if ie_tag == 0xbc02:  # SPATIAL_XFRM_PRIMARY.
          if ie_value > 7:
            raise ValueError('Bad jpegxr SPATIAL_XFRM_PRIMARY.')
          spatial_xfrm = ie_value
          # If SPATIAL_XFRM_PRIMARY is missing, we may want to check
          # SPATIAL_XFRM_SUBORDINATE in CODED_IMAGE.
        elif ie_tag == 0xbc80:  # IMAGE_WIDTH.
          width = ie_value
        elif ie_tag == 0xbc81:  # IMAGE_HEIGHT.
          height = ie_value
    if width is None:
      raise ValueError('Missing jpegxr width.')
    if height is None:
      raise ValueError('Missing jpegxr height.')
  else:
    raise ValueError('jpegxr signature not found.')
  if spatial_xfrm & 4:
    info['width'], info['height'] = height, width
  else:
    info['width'], info['height'] = width, height


def analyze_flif(fread, info, fskip):
  # https://flif.info/spec.html
  header = fread(6)
  if len(header) < 6:
    raise ValueError('Too short for flif.')
  signature, ia_nc, bpc = struct.unpack('>4sBB', header)
  ia = ia_nc >> 4
  component_count = ia_nc & 15
  bpc = (bpc - 48) * 8
  if signature != 'FLIF':
    raise ValueError('flif signature not found.')
  info['format'] = info['codec'] = 'flif'
  if ia not in (3, 4, 5, 6):
    raise ValueError('Bad flif interlacing or animation.')
  if component_count not in (1, 3, 4):
    raise ValueError('Bad flif component_count.')
  if bpc not in (0, 8, 16):
    raise ValueError('Bad flif bpc.')

  def read_varint(name):
    v, c, cc = 0, 128, 0
    while c & 128:
      if cc > 8:  # 63 bits maximum.
        raise ValueError('flif %s varint too long.' % name)
      c = fread(1)
      if not c:
        raise ValueError('EOF in flif %s.' % name)
      c = ord(c)
      v = v << 7 | c & 127
      cc += 1
    return v

  info['width'] = read_varint('width') + 1
  info['height'] = read_varint('height') + 1
  info['component_count'], info['bpc'] = component_count, bpc


def analyze_fuif(fread, info, fskip):
  # https://github.com/cloudinary/fuif/blob/3ed48249a9cbe68740aa4ea58098ab0cd4b87eaa/encoding/encoding.cpp#L456-L466
  header = fread(7)
  if len(header) < 6:
    raise ValueError('Too short for fuif.')
  signature, component_count, bpc = struct.unpack('>4sBB', header[:6])
  component_count -= 0x30
  bpc -= 0x26
  if signature not in ('FUIF', 'FUAF'):
    raise ValueError('fuif signature not found.')
  info['format'] = info['codec'] = 'fuif'
  info['subformat'] = ('fuif', 'fuaf')[signature == 'FUAF']
  if not 1 <= component_count <= 5:
    raise ValueError('Bad fuif component_count.')
  if not 1 <= bpc <= 16:
    raise ValueError('Bad fuif bpc.')
  if len(header) < 7:
    return

  def read_varint(name, data=''):
    v, c, cc = 0, 128, 0
    while c & 128:
      if cc > 8:  # 63 bits maximum.
        raise ValueError('fuif %s varint too long.' % name)
      if data:
        c, data = data, ''
      else:
        c = fread(1)
      if not c:
        raise ValueError('EOF in fuif %s.' % name)
      c = ord(c)
      v = v << 7 | c & 127
      cc += 1
    return v

  info['width'] = read_varint('width', header[6]) + 1
  info['height'] = read_varint('height') + 1
  info['component_count'], info['bpc'] = component_count, bpc


def is_bpg(header):
  if len(header) < 6 or not header.startswith('BPG\xfb'):
    return False
  signature, b1, b2 = struct.unpack('>4sBB', buffer(header, 0, 6))
  pixel_format, bit_depth_m8 = b1 >> 5, b1 & 15
  color_space = b2 >> 4
  return pixel_format <= 5 and bit_depth_m8 <= 6 and color_space <= 5


def analyze_bpg(fread, info, fskip):
  # https://bellard.org/bpg/bpg_spec.txt
  header = fread(6)
  if len(header) < 6:
    raise ValueError('Too short for bpg.')
  signature, b1, b2 = struct.unpack('>4sBB', header)
  pixel_format, alpha1_flag, bit_depth = b1 >> 5, (b1 >> 4) & 1, b1 & 15
  color_space = b2 >> 4
  bit_depth += 8
  if signature != 'BPG\xfb':
    raise ValueError('bpg signature not found.')
  info['format'] = 'bpg'
  info['codec'] = 'h265'
  if pixel_format > 5:
    raise ValueError('Bad bpg pixel_format: %d' % pixel_format)
  if not 8 <= bit_depth <= 14:
    raise ValueError('Bad bpg bit_depth: %d' % bit_depth)
  if color_space > 5:
    raise ValueError('Bad bpg color_space: %d' % color_space)

  def read_varint32(name):
    v, c, cc = 0, 128, 0
    while c & 128:
      if cc > 4:  # 35 bits maximum.
        raise ValueError('bpg %s varint32 too long.' % name)
      c = fread(1)
      if not c:
        raise ValueError('EOF in bpg %s.' % name)
      c = ord(c)
      if not cc and c == 128:
        raise ValueError('Bad bpg %s varint32.' % name)
      v = v << 7 | c & 127
      cc += 1
    if v >> 32:
      raise ValueError('bpg %s varint32 too large.' % name)
    return v

  info['width'] = read_varint32('width')
  info['height'] = read_varint32('height')


MIFF_CODEC_MAP = {
    'none': 'uncompressed',
    'bzip': 'bzip2',
    'zip': 'flate',
}


def analyze_miff(fread, info, fskip):
  # https://en.wikipedia.org/wiki/Magick_Image_File_Format
  # http://www.imagemagick.org/script/miff.php
  header = fread(14)
  if len(header) < 14:
    raise ValueError('Too short for miff.')
  if not header.startswith('id=ImageMagick'):
    raise ValueError('miff signature not found.')
  info['format'] = 'miff'
  buf = [header]
  while 1:
    buf.append(fread(128))
    if not buf[-1]:
      raise ValueError('EOF in miff header.')
    if buf[-2].endswith(':') and buf[-1].startswith('\x1a'):
      del buf[-1]
      buf[-1] = buf[-1][:-1]
      break
    i = buf[-1].find(':\x1a')
    if i >= 0:
      buf[-1] = buf[-1][:i]
      break
  # TODO(pts): Remove comments in {braces}.
  header = ''.join(buf).split()
  info['codec'] = 'uncompressed'
  for item in header:
    if '=' in item:
      key, value = item.split('=', 1)
      key = key.lower()
      if key == 'compression':
        value = value.lower()
        info['codec'] = MIFF_CODEC_MAP.get(value, value)
      elif key in ('columns', 'rows'):
        info_key = ('width', 'height')[key == 'rows']
        try:
          info[info_key] = int(value)
        except ValueError:
          raise ValueError('Bad miff %s syntax.' % info_key)
        if info[info_key] <= 0:
          raise ValueError('Bad miff %s.' % info_key)


def analyze_jbig2(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/JBIG2
  # https://www.itu.int/rec/dologin_pub.asp?lang=f&id=T-REC-T.88-200002-S!!PDF-E&type=items
  header = fread(9)
  if len(header) < 9:
    raise ValueError('Too short for jbig2.')
  if header == '\0\0\0\0\x30\0\1\0\0':
    # 0: 00000000: segment_number=0
    # 4: 30: dnr_flag=0 spa_size_flag=0 segment_type=48
    # 5: 00: count=0
    # 6: 01: page_number=1
    # 7: 00000013: data_size=19
    # 11: ????????: width
    # 15: ????????: height
    # 19: 00000000: x_res=0
    # 23: 00000000: y_res=0
    header = fread(18)
    if len(header) < 18:
      raise ValueError('Too short for jbig2-pdf.')
    data_size_suffix, width, height, x_res, y_res = struct.unpack(
        '>HLLLL', header)
    if data_size_suffix != 0x13 or x_res or y_res:
      raise ValueError('Bad jbig2-pdf header.')
    info['format'] = info['codec'] = 'jbig2'
    info['subformat'] = 'pdf'
  else:
    if not header.startswith('\x97JB2\r\n\x1a\n'):
      raise ValueError('jbig2 signature not found.')
    info['format'] = info['codec'] = 'jbig2'
    info['subformat'] = 'jbig2'
    b = ord(header[8])
    is_random_access = bool(b & 128)
    if not b & 64:
      data = fread(4)
      if len(data) != 4:
        raise ValueError('EOF in jbig2 page_count.')
      if data == '\0\0\0\0':
        raise ValueError('Bad jbig2 page_count.')
    page_info = None
    page_info_ofs = 0
    while 1:
      data = fread(6)
      if len(data) < 6:
        raise ValueError('EOF in jbig2 segment header.')
      segment_number, flags, count = struct.unpack('>LBB', data)
      segment_type = flags & 63
      spa_size = 1 + ((flags >> 6) & 1) * 3
      count_hi = count >> 4
      if count_hi <= 4:
        ref_size = 0
        ref_count = count_hi
      elif count_hi == 7:
        data = data[-1] + fread(3)
        if len(data) < 4:
          raise ValueError('Bad jbig2 segment long ref_count.')
        ref_count = struct.unpack('>L', data) & 0x1fffffff
        ref_size = (ref_count + 8) >> 3
      else:
        raise ValueError('Bad jbig2 segment count_hi.')
      if not fskip(ref_size):
        raise ValueError('EOF in jbig2 segment ref data.')
      data = fread(spa_size)  # Segment page association.
      if len(data) < spa_size:
        raise ValueError('EOF in jbig2 segment spa.')
      if spa_size == 1:
        page_number, = struct.unpack('>B', data)
      else:
        page_number, = struct.unpack('>L', data)
      data = fread(4)
      if len(data) < 4:
        raise ValueError('EOF in jbig2 segment data size.')
      data_size, = struct.unpack('>L', data)
      if data_size == 0xffffffff:
        raise ValueError('Unexpected implicit jbig2 segment data size.')
      #print (segment_number, segment_type, ref_count, page_number, data_size)
      if segment_type == 51:  # End of file.
        break
      if segment_type == 48:  # Page information.
        if data_size != 19:
          raise ValueError('Bad jbig2 page information data size: %d' % data_size)
        if is_random_access:
          page_info = True
        else:
          page_info = fread(data_size)
          if len(page_info) != data_size:
            raise ValueError('EOF in jbig2 page information.')
          break
      elif is_random_access:
        if not page_info:
          page_info_ofs += data_size
      else:
        if not fskip(data_size):
          raise ValueError('EOF in jbig2 segment.')
    if page_info is True:
      if not fskip(page_info_ofs):
        raise ValueError('EOF in jbig2 segment data before page information.')
      data_size = 19
      page_info = fread(data_size)
      if len(page_info) != data_size:
        raise ValueError('EOF in jbig2 random-access page information.')
    width, height, x_res, y_res, flags, striping_info = struct.unpack(
        '>LLLLBH', page_info)
  if width == 0xffffffff:
    raise ValueError('Bad jbig2 width.')
  info['width'] = width
  if height != 0xffffffff:  # Known already.
    info['height'] = height


def analyze_djvu(fread, info, fskip):
  # https://en.wikipedia.org/wiki/DjVu#File_structure
  header = fread(16)
  if len(header) < 16:
    raise ValueError('Too short for jdvu.')
  if not (header.startswith('AT&TFORM') and header[12 : 15] == 'DJV' and
          header[15] in 'UM'):
    raise ValueError('djvu signature not found.')
  info['format'] = 'djvu'
  if header[15] == 'U':
    info['subformat'] = 'djvu'
  else:
    info['subformat'] = 'djvm'
    djvm_size, = struct.unpack('>L', header[8 : 12])
    while 1:
      if djvm_size < 8:
        raise ValueError('djvu FORM:DJVM too short for member header.')
      data = fread(8)
      if len(data) < 8:
        raise ValueError('EOF in djvu djvm member header.')
      djvm_size -= 8
      tag, size = struct.unpack('>4sL', data)
      if djvm_size < size:
        raise ValueError('djvu FORM:DJVM too short for member %r data.' % tag)
      djvm_size -= size
      if tag == 'FORM':
        if size < 4:
          raise ValueError('Bad djvu djvm member FORM size.')
        tag += ':' + fread(4)
        if len(tag) != 9:
          raise ValueError('EOF in djvu djvm member FORM tag.')
        size -= 4
      #print (tag, size)
      if tag == 'FORM:DJVU':
        break
      # Typical tags: 'DIRM', 'NAVM', 'FORM:DJVI'.
      if not fskip(size):
        raise ValueError('EOF in djvm member %r.' % tag)
  data = fread(12)
  if len(data) < 12:
    raise ValueError('EOF in djvu INFO.')
  tag, size, width, height = struct.unpack('>4sLHH', data)
  if tag != 'INFO':
    raise ValueError('Bad djvu INFO tag.')
  if not 4 <= size < 256:
    raise ValueError('Bad djvu INFO size: %d' % size)
  info['width'], info['height'] = width, height


def analyze_art(fread, info, fskip, format='art', fclass='image',
                spec=(0, 'JG', 2, ('\3', '\4'), 3, '\x0e\0\0\0')):
  # By AOL browser.
  # https://en.wikipedia.org/wiki/ART_image_file_format
  # https://multimedia.cx/eggs/aol-art-format/
  # http://samples.mplayerhq.hu/image-samples/ART/
  # https://samples.ffmpeg.org/image-samples/ART/
  # https://bugzilla.mozilla.org/show_bug.cgi?id=153450
  # https://msfn.org/board/topic/125338-aol-art-compressed-image/
  #   2009, Internet Explorer 6, Windows registry FEATURE_IMAGING_USE_ART.
  # Proprietary and undocumented jgdw400.dll . There is also jgdw500.dll .
  #   There is also jgdwaol.dll .
  # ACDSee 5.01 has ART support. It works on Windows 10, but it doesn't work
  #   on Wine 1.6.
  header = fread(17)
  if len(header) < 7:
    raise ValueError('Too short for art.')
  if not (header.startswith('JG') and header[2] in '\3\4' and
          header[3 : 7] == '\x0e\0\0\0'):
    raise ValueError('art signature not found.')
  info['format'] = info['codec'] = 'art'
  # These are mostly an educated guess based on samples, the file format is
  # not documented. Not even XnView MP or IrfanView can open them.
  if header[2] == '\4' and header[7 : 13] in ('\0\7\0\x40\x15\3', '\0\7\0\x40\x15\x20'):
    info['width'], info['height'] = struct.unpack('<HH', header[13 : 17])
  elif ((header[2] == '\3' and header[7 : 12] == '\4\x8e\x02\x0a\0') or
        (header[2] == '\4' and header[7 : 12] == '\0\x8c\x16\0\0')):
    info['height'], info['width'] = struct.unpack('<HH', header[12 : 16])


def analyze_fuji_raf(fread, info, fskip):
  # https://libopenraw.freedesktop.org/wiki/Fuji_RAF/
  # https://libopenraw.freedesktop.org/formats/raf/
  # http://fileformats.archiveteam.org/wiki/Fujifilm_RAF
  # `memcmp (head,"FUJIFILM",8)' in https://www.dechifro.org/dcraw/dcraw.c
  # Look at the `Output size:' of the `dcraw -i -v FILENAME.RAF' output.
  # derived from dcraw.c: `memcmp (head,"FUJIFILM",8)' in dcraw.cc (part of ufraw-batch)
  #
  # Getting width= and height= is surprisingly complicated (as implemented
  # in dcraw.c), the used pixel_aspect value depends on the camera model,
  # and the entire calculation of fuji_width is hacky, brittle and prone
  # to errors, to the point that that it would be unmaintainable here.
  # Getting the dimensions of the JPEG thumbnail is easy though, but it's
  # not useful.
  header = fread(28)
  if len(header) < 28:
    raise ValueError('Too short for fuji-raf.')
  if not (header.startswith('FUJIFILMCCD-RAW 020') and header[19] in '01' and
          header[20 : 28] == 'FF383501'):
    raise ValueError('art signature not found.')
  info['format'], info['codec'] = 'fuji-raf', 'raw'


def parse_ico_or_cur(fread, info, fskip, format):
  # https://en.wikipedia.org/wiki/ICO_(file_format)#Outline
  header = fread(6)
  if len(header) < 6:
    raise ValueError('Too short for %s.' % format)
  if not header.startswith(('\0\0\2\0', '\0\0\1\0')[format == 'ico']):
    raise ValueError('%s signature not found.' % format)
  info['format'] = format
  image_count, = struct.unpack('<H', header[4 : 6])
  if not 1 <= image_count <= 64:
    raise ValueError('Bad %s image_count: %d' % (format, image_count))
  best = ()
  min_image_offset = 6 + 16 * image_count
  for _ in xrange(image_count):
    data = fread(16)
    if len(data) < 16:
      raise ValueError('EOF in %s image entry.' % format)
    width, height, color_count, reserved, color_plane_count, bits_per_pixel, image_size, image_offset = struct.unpack(
        '<BBBBHHLL', data)
    if reserved not in (0, 1, 255):
      raise ValueError('Bad %s reserved byte: %d' % (format, reserved))
    width += (width == 0) << 8
    height += (height == 0) << 8
    if format == 'ico':
      if color_plane_count > 4:
        raise ValueError('Bad %s color_plane_count: %d' % (format, color_plane_count))
      if bits_per_pixel not in (0, 1, 2, 4, 8, 16, 24, 32):
        raise ValueError('Bad %s bits_per_pixel: %d' % (format, bits_per_pixel))
    else:
      hotspot_x, hotspot_y = color_plane_count, bits_per_pixel
      if not 0 <= hotspot_x < width:
        raise ValueError('Bad cur hotspot_x: %d' % hotspot_x)
      if not 0 <= hotspot_y < height:
        raise ValueError('Bad cur hotspot_x: %d' % hotspot_y)
    if not image_size:
      raise ValueError('Bad %s image size.' % format)
    if image_offset < min_image_offset:
      raise ValueError('Bad %s image_offset.' % format)
    best = max(best, (width * height, width, height, image_offset))
  _, info['width'], info['height'], image_offset = best  # Largest icon.
  # Detect codec at image_offset.
  if format == 'ico' and fskip(image_offset - min_image_offset):
    data = fread(20)
    if len(data) == 20:
      # https://github.com/ImageMagick/ImageMagick/blob/2059f96eeae8c2d26e8683aa17fd65f78f42ad30/coders/icon.c#L276-L277
      # 'IHDR' conflicts with BITMAPINFOHEADER.biPlanes and .biBitCnt.
      if data.startswith('\x89PNG') and data[12 : 16] == 'IHDR':
        info['subformat'], info['codec'] = 'png', 'flate'
      else:
        dib_info = {}
        parse_dib_header(dib_info, data)
        if dib_info['width'] != width:
          raise ValueError('Bad %s dib width.')
        if dib_info['height'] != (height << 1):
          raise ValueError('Bad %s dib height.')
        info['subformat'] = 'bmp'
        if 'codec' in dib_info:
          info['codec'] = dib_info['codec']


def analyze_ico(fread, info, fskip, format='ico', fclass='image',
                spec=(0, '\0\0\1\0', 4, tuple(chr(c) for c in xrange(1, 65)), 5, '\0', 9, ('\0', '\1', '\xff'), 10, ('\0', '\1', '\2', '\3', '\4'), 11, '\0', 12, ('\0', '\1', '\2', '\4', '\x08', '\x10', '\x18', '\x20'), 13, '\0')):
  parse_ico_or_cur(fread, info, fskip, 'ico')


def analyze_cur(fread, info, fskip, format='cur', fclass='image',
                spec=(0, '\0\0\2\0', 4, tuple(chr(c) for c in xrange(1, 65)), 5, '\0', 9, ('\0', '\1', '\xff'), 11, '\0', 13, '\0')):
  parse_ico_or_cur(fread, info, fskip, 'cur')


def analyze_minolta_raw(fread, info, fskip):
  # http://www.dalibor.cz/software/minolta-raw-mrw-file-format
  # Old: http://www.dalibor.cz/minolta/raw_file_format.htm
  # Sample: http://www.rawsamples.ch/raws/minolta/a1/RAW_MINOLTA_A1.MRW
  # Example camera model: Minolta Dimage A1
  # Other Minolta cameras use a different raw file format.
  header = fread(16)
  if len(header) < 16:
    raise ValueError('Too short for minolta-raw.')
  if not (header.startswith('\0MRM') and header[8 : 16 ] == '\0PRD\0\0\0\x18'):
    raise ValueError('minolta-raw signature not found.')
  info['format'], info['codec'] = 'minolta-raw', 'raw'
  if header[5] not in '\0\1\2\3':
    raise ValueError('minolta-raw header too long.')
  header += fread(32 - len(header))
  if len(header) >= 32:
    info['height'], info['width'] = struct.unpack('>HH', header[28 : 32])


def analyze_dpx(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/DPX
  # http://www.simplesystems.org/users/bfriesen/dpx/S268M_Revised.pdf
  header = fread(12)
  if len(header) < 12:
    raise ValueError('Too short for dpx.')
  if not (header.startswith('SDPX\0\0') and header[8 : 11] in ('V1.', 'V2.') and header[11].isdigit()):
    raise ValueError('dpx signature not found.')
  info['format'] = 'dpx'
  if fskip(768 - 12):
    data = fread(40)
    if len(data) >= 12:
      info['width'], info['height'] = struct.unpack('>LL', data[4 : 12])
    if len(data) >= 40 and data[38 : 40] == '\0\0':
      info['codec'] = 'uncompressed'
    elif len(data) >= 40 and data[38 : 40] == '\0\1':
      info['codec'] = 'rle'


def analyze_cineon(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/Cineon
  # https://125px.com/docs/motionpicture/kodak/cineonfileformat4.5.pdf
  header = fread(8)
  if len(header) < 8:
    raise ValueError('Too short for cineon.')
  if header.startswith('\x80\x2a\x5f\xd7\0\0'):
    fmt = '>'
  elif header.startswith('\xd7\x5f\x2a\x80') and header[6 : 8] == '\0\0':
    fmt = '<'
  else:
    raise ValueError('cineon signature not found.')
  info['format'], info['codec'] = 'cineon', 'uncompressed'
  if fskip(200 - 8):
    data = fread(8)
    if len(data) == 8:
      info['width'], info['height'] = struct.unpack(fmt + 'LL', data)


def analyze_vicar(fread, info, fskip):
  # https://en.wikipedia.org/wiki/VICAR_file_format
  # https://www-mipl.jpl.nasa.gov/external/VICAR_file_fmt.pdf
  header = fread(64)
  if len(header) < 10:
    raise ValueError('Too short for vicar.')
  if not (header.startswith('LBLSIZE=') and header[8] in '123456789' and header[9].isdigit()):
    raise ValueError('vicar signature not found.')
  info['format'] = 'vicar'
  size = header[8:].split(None, 1)[0]
  try:
    size = int(size)
  except ValueError:
    raise ValueError('Bad vicar lblsize: %r' % size)
  assert size >= 10  # Follows from above.
  data = header[8 : size]
  if len(data) < size - 8:
    data += fread(size - 8 - len(data))
    if len(data) < size - 8:
      raise ValueError('EOF in vicar header.')
  i = data.find('\0')
  if i >= 0:
    data = data[:i]
  data = data.replace('=', ' = ').replace("'", " ' ").split()
  i = 1
  dimens = {}
  while i < len(data):
    key = data[i]
    i += 1
    if data[i] != '=':
      continue
    i += 1
    if i == len(data):
      break
    value = data[i]
    i += 1
    if value == "'":
      while i < len(data) and data[i] != "'":
        i += 1
      i += 1
    elif key in ('NS', 'NL'):
      dimens_key = ('height', 'width')[key == 'NS']
      try:
        value = int(value)
      except ValueError:
        raise ValueError('Bad vicar %s: %r' % (dimens_key, value))
      dimens[dimens_key] = value
  if 'width' in dimens and 'height' in dimens:
    info['width'], info['height'] = dimens['width'], dimens['height']


def analyze_pds(fread, info, fskip):
  # http://justsolve.archiveteam.org/wiki/PDS
  # https://pds.nasa.gov/datastandards/pds3/standards/sr/StdRef_20090227_v3.8.pdf
  # https://descanso.jpl.nasa.gov/DPSummary/DS1_Navigation_Primary.pdf
  # Sample: https://pdsimage2.wr.usgs.gov/Missions/Voyager/vg_0001/miranda/c2531144.imq
  data = fread(2)
  if len(data) == 2 and data[1] == '\0':
    size, = struct.unpack('<H', data)
    data = fread(size)
    if len(data) < size:
      raise ValueError('Too short for pds size.')
    nulb = fread(1)
    if nulb != '\0':
      raise ValueError('Missing NUL byte after pds header record.')
    def yield_records():
      yield data
      while 1:
        ydata = fread(2)
        if len(ydata) < 2:
          break
        ysize, = struct.unpack('<H', ydata)
        ydata = fread(ysize)
        if len(ydata) < ysize:
          break
        yield ydata
  else:
    def yield_records():
      ydata = (data + fread(1024 - len(data))).replace('\r', '\n').replace('\0', '\n')
      while 1:
        if '\n' in ydata:
          lines = ydata.split('\n')
          ydata = lines.pop()
          for line in lines:
            yield line
        ysize = len(ydata)
        ydata += fread(1024 - len(ydata)).replace('\r', '\n').replace('\0', '\n')
        if len(ydata) == ysize:  # EOF
          if ydata:
            yield ydata
          break
  need_header = True
  dimens = {}
  for record in yield_records():
    if need_header:
      if not (record.startswith('NJPL1I00PDS') or
              (record.startswith('PDS_VERSION_ID') and record[14 : 15].isspace()) or
              record.startswith('CCSD3ZF')):
        break
      need_header = False
      info['format'] = 'pds'
      continue
    record = record.strip()
    if record.startswith('IMAGE'):
      dimens['is_image'] = True
    elif record == 'END':
      break
    i = record.find('=')
    if i < 0:
      continue
    key, value = record[:i].rstrip(), record[i + 1:].lstrip()
    if key in ('LINES', 'LINE_SAMPLES', 'IMAGE_LINES'):
      dimens_key = ('height', 'width')[key == 'LINE_SAMPLES']
      try:
        value = int(value)
      except ValueError:
        raise ValueError('Bad pds %s: %r' % (dimens_key, value))
      dimens[dimens_key] = value
  if need_header:
    raise ValueError('pds signature not found.')
  if dimens.get('is_image') and 'width' in dimens and 'height' in dimens:
    info['width'], info['height'] = dimens['width'], dimens['height']


def analyze_ybm(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/YBM
  header = fread(6)
  if len(header) < 2:
    raise ValueError('Too short for ybm.')
  if not header.startswith('!!'):
    raise ValueError('ybm signature not found.')
  info['format'], info['codec'] = 'ybm', 'uncompressed'
  if len(header) >= 6:
    info['width'], info['height'] = struct.unpack('>HH', header[2 : 6])


def analyze_fbm(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/FBM_image
  header = fread(24)
  if len(header) < 8:
    raise ValueError('Too short for fbm.')
  if not header.startswith('%bitmap\0'):
    raise ValueError('fbm signature not found.')
  info['format'], info['codec'] = 'fbm', 'uncompressed'
  if len(header) >= 24:
    dimens = {}
    dimens['width'], dimens['height'] = struct.unpack('>8s8s', header[8 : 24])
    for key in ('width', 'height'):
      dimens[key] = dimens[key].split('\0', 1)[0]
      try:
        dimens[key] = int(dimens[key])
      except ValueError:
        raise ValueError('Bad fbm %s: %r' % (key, dimens[key]))
    info['width'], info['height'] = dimens['width'], dimens['height']


def analyze_cmuwm(fread, info, fskip):
  # Also called as ITC bitmap.
  # http://fileformats.archiveteam.org/wiki/CMU_Window_Manager_bitmap
  # http://inf.ufes.br/~thomas/vision/netpbm/pbm/cmuwmtopbm.c
  # http://inf.ufes.br/~thomas/vision/netpbm/pbm/cmuwm.h
  header = fread(12)
  if len(header) < 4:
    raise ValueError('Too short for cmuwm.')
  if not (header.startswith('\xf1\0\x40\xbb') or header.startswith('\xbb\x40\0\xf1')):
    raise ValueError('cmuwm signature not found.')
  fmt = '<>'[header[1] == '\0']
  info['format'], info['codec'] = 'cmuwm', 'uncompressed'
  if len(header) >= 12:
    info['width'], info['height'] = struct.unpack(fmt + 'LL', header[4 : 12])


def analyze_utah_rle(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/Utah_RLE
  # http://www.fileformat.info/format/utah/egff.htm
  # http://paulbourke.net/dataformats/urt/
  # Samples: ftp://ftp.uni-potsdam.de/pub/unix/graphics/imageprocessing/urt/urt-img.tar
  header = fread(15)
  if len(header) < 2:
    raise ValueError('Too short for utah-rle.')
  if not header.startswith('\x52\xcc'):
    raise ValueError('utal-rle signature not found.')
  info['format'], info['codec'] = 'utah-rle', 'rle'
  if len(header) >= 15:
    (xpos, ypos, xsize, ysize, flags, ncolors, pixelbits, ncmap, cmaplen,
    ) = struct.unpack('<4H5B', header[2 : 15])
    info['width'], info['height'] = xsize, ysize
    if flags > 15:
      raise ValueError('Bad utah-rle flags.')
    if not 1 <= ncolors <= 5:
      raise ValueError('Bad utah-rle ncolors.')
    if pixelbits != 8:
      raise ValueError('Bad utah-rle pixelbits.')
    if ncmap > 5:
      raise ValueError('Bad utah-rle ncmap.')
    if cmaplen > 8:
      raise ValueError('Bad utah-rle cmaplen.')


def analyze_ftc(fread, info, fskip, format='ftc', fclass='image',
                spec=(0, 'FTC\0\1\1\2\1')):
  # http://cd.textfiles.com/wthreepack/wthreepack-1/COMPRESS/FIFDEMO.ZIP
  # We don't know how to get width and height, the file format is not public.
  match_spec(spec, fread, info, format)
  info['codec'] = 'fractal'


def analyze_fif(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/Fractal_Image_Format
  header = fread(14)
  if len(header) < 4:
    raise ValueError('Too short for fif.')
  if not header.startswith('FIF\1'):
    raise ValueError('fif signature not found.')
  info['format'], info['codec'] = 'fif', 'fractal'
  if len(header) >= 14:
    info['width'], info['height'] = struct.unpack('<LL', header[6 : 14])


def is_spix(header):
  if len(header) < 24:
    return False
  header = header[:24]
  allowed_depths = (1, 2, 4, 8, 16, 24, 32, 40)
  for fmt in '<>':
    signature, width, height, depth, wpl, palette_color_count = struct.unpack(fmt + '4s5L', header)
    # Width and height limit imposed in spixio.c are 1000000
    if signature == 'spix' and not width >> 24 and not height >> 24 and depth in allowed_depths and wpl > 0 and palette_color_count <= 256:
      return True
  return False


def analyze_spix(fread, info, fskip):
  # https://github.com/DanBloomberg/leptonica/blob/cdef566863f2234114317e9a80710b7abba1760e/src/spixio.c#L446-L452
  header = fread(24)
  if len(header) < 24:
    raise ValueError('Too short for spix.')
  if not header.startswith('spix'):
    raise ValueError('spix signature not found.')
  if not is_spix(header):
    raise ValueError('Bad spix header.')
  info['format'], info['codec'] = 'spix', 'uncompressed'
  fmt = '<>'[header[12] == '\0']  # Big endian depth.
  info['width'], info['height'] = struct.unpack(fmt + 'LL', header[4 : 12])


def analyze_sgi_rgb(fread, info, fskip):
  # http://paulbourke.net/dataformats/sgirgb/sgiversion.html
  # https://www.fileformat.info/format/sgiimage/egff.htm
  # http://fileformats.archiveteam.org/wiki/SGI_(image_file_format)
  # http://reality.sgi.com/grafica/sgiimage.html
  # As indicated in sgiversion.html, only big endian is supported.
  # This format is also called as IRIX or IRIX RGB.
  header = fread(12)
  if len(header) < 12:
    raise ValueError('Too short for sgi-rgb.')
  (magic, storage, bpc, dimension, width, height, zsize,
  ) = struct.unpack('>HBBHHHH', header[:12])
  if magic != 474:
    raise ValueError('sgi-rgb signature not found.')
  if storage > 1:
    raise ValueError('Bad sgi-rgb storage.')
  if bpc not in (1, 2):
    raise ValueError('Bad sgi-rgb bpc.')
  if dimension not in (1, 2, 3):
    raise ValueError('Bad sgi-rgb dimension.')
  if dimension == 3 and zsize not in (1, 2, 3, 4, 5):
    raise ValueError('Bad sgi-rgb zsize.')
  info['format'] = 'sgi-rgb'
  info['codec'] = ('uncompressed', 'rle')[storage]
  info['width'], info['height'] = width, height


def analyze_xv_pm(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/PM_(XV_image)
  # Reader code: https://github.com/ingowald/updated-xv/blob/master/xvpm.c
  # Reader code: xv-3.10a/xvpm.c
  header = fread(24)
  if len(header) < 24:
    raise ValueError('Too short for xv-pm.')
  if header.startswith('VIEW\0\0\0') and header[7] != '\0':
    fmt = '>'
  elif header.startswith('WEIV') and header[4] != '\0' and header[5 : 8] == '\0\0\0':
    fmt = '<'
  else:
    raise ValueError('xv-pm signature not found.')
  info['format'], info['codec'] = 'xv-pm', 'uncompressed'
  (magic, component_count, height, width, band_count, pixel_format,
  ) = struct.unpack(fmt + '6L', header[:24])
  info['width'], info['height'] = width, height
  if component_count not in (1, 3, 4):
    raise ValueError('Bad xv-pm component_count: %d' % component_count)
  if band_count != 1:
    raise ValueError('Bad xv-pm band_count: %d' % band_count)
  if pixel_format not in (0x8001, 0x8004):
    raise ValueError('Bad xv-pm pixel_format: 0x%x' % pixel_format)
  if pixel_format == 0x8004 and component_count != 1:
    raise ValueError('Bad xv-pm indexed component_count: %d' % component_count)


def parse_imlib_argb_header(header):
  if len(header) < 11:  # Prerequisite: header = fread(32)
    raise ValueError('Too short for imlib-argb.')
  if not header.startswith('ARGB '):
    raise ValueError('imlib-argb signature not found.')
  header = header[:32].replace('\r', '\n')
  i = header.find('\n')
  if i < 0:
    raise ValueError('Newline missing in first %d bytes of imlib-argb header.' % len(header))
  header = header[:i]
  magic, width, height, alpha = header.split(' ')
  try:
    width = int(width)
  except ValueError:
    raise ValueError('Bad imlib-argb width: %r' % width)
  if width <= 0:
    raise ValueError('Bad imlib-argb width: %d: width')  # Consistent with FormatDb.
  try:
    height = int(height)
  except ValueError:
    raise ValueError('Bad imlib-argb height: %r' % height)
  if height <= 0:
    raise ValueError('Bad imlib-argb height: %d' % height)
  if alpha not in '01':
    raise ValueError('Bad imlib-argb alpha: %r' % alpha)
  return i + 1, width, height


def count_is_imlib_argb(header):
  try:
    return parse_imlib_argb_header(header)[0] * 100
  except ValueError:
    return 0


def analyze_imlib_argb(fread, info, fskip):
  # Reader code: https://downloads.sourceforge.net/enlightenment/imlib2-1.6.1.tar.bz2 loader_argb.c
  _, width, height = parse_imlib_argb_header(fread(32))
  info['format'], info['codec'] = 'imlib-argb', 'uncompressed'
  info['width'], info['height'] = width, height


def count_is_imlib_eim(header):
  if len(header) < 13:  # Prerequisite: header = fread(14)
    return 0
  d = header[5] == '\r'
  header = header.replace('\r\n', '\n')
  if not (header.startswith('EIM 1\nIMAGE ') and header[12 : 13] in '-0123456789'):
    return 0
  return (13 + d) * 100


def analyze_imlib_eim(fread, info, fskip):
  # Reader code: search for `fprintf(f, "IMAGE %i' in Imlib/load.c in https://ftp.gnome.org/pub/gnome/sources/imlib/1.9/imlib-1.9.15.tar.gz
  # Reader code: search for `fprintf(f, "IMAGE %i' in https://stuff.mit.edu/afs/athena/project/windowmgr/src/imlib-1.9.8/Imlib/load.c
  header = fread(14)
  if len(header) < 13:  # Sic 13, because of the repace below.
    raise ValueError('Too short for imlib-eim.')
  header = header.replace('\r\n', '\n')
  if not (header.startswith('EIM 1\nIMAGE ') and header[12 : 13] in '-0123456789'):
    raise ValueError('imlib-eim signature not found.')
  info['format'], info['codec'] = 'imlib-eim', 'uncompressed'
  header += fread(1024 - 14).replace('\r\n', '\n')
  # Allow any character but '\n' in the 2nd argument (``iden'') of IMAGE.
  i = header.find('\n', 6)
  if i < 0:
    header += fread(1536).replace('\r\n', '\n')
    i = header.find('\n', 6)
  if i >= 0:
    header = header[6 : i][::-1].split(' ', 9)
    if len(header) < 9:
      raise ValueError('Too few items in imlib-eim image line.')
    header = ' '.join(header[:9])[::-1].split(' ')
    try:
      header = map(int, header)
    except ValueError:
      raise ValueError('Bad number in imlib-eim image line.')
    if header[0] < 0:
      raise ValueError('Bad imlib-eim width: %d' % header[0])
    if header[1] < 0:
      raise ValueError('Bad imlib-eim height: %d' % header[1])
    info['width'], info['height'] = header[:2]


def analyze_farbfeld(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/Farbfeld
  header = fread(16)
  if len(header) < 8:
    raise ValueError('Too short for farbfeld.')
  if not header.startswith('farbfeld'):
    raise ValueError('farbfeld signature not found.')
  info['format'], info['codec'] = 'farbfeld', 'uncompressed'
  if len(header) >= 16:
    info['width'], info['height'] = struct.unpack('>LL', header[8 : 16])


def parse_count_wbmp_header(header):
  # For simplicity and lack of examples online, we don't support key=value
  # extension header, and we assume that all reserved bits are 0.
  if len(header) < 2:
    raise ValueError('Too short for wbmp.')
  if not (header[0] == '\0' and header[1] in '\0\x80'):
    raise ValueError('wbmp signature not found.')
  b, i, f = ord(header[1]), 2, 187  # f is confidence.
  while b & 0x80:  # Skip extension header.
    if i >= len(header):
      raise ValueError('EOF in wbmp extension header.')
    b = ord(header[i])
    i += 1
    f += 87
    if b not in (0, 0x80):
      raise ValueError('Bad wbmp extension header type.')
    while 1:
      if i >= len(header):
        raise ValueError('EOF in wbmp extension data.')
      i += 1  # Not increasing f, we don't have additional info.
      if ord(header[i - 1]) < 0x80:
        break
  i2 = i
  width = c = 0
  while 1:
    if i >= len(header):
      raise ValueError('EOF in wbmp width.')
    c += 7
    if c > 14:  # Heuristic guess based on WAP speeds and bandwidth costs.
      raise ValueError('wbmp width too long.')
    b = ord(header[i])
    i += 1
    f += 1  # Info stating that c isn't too much.
    width = width << 7 | (b & 0x7f)
    if b < 0x80:
      break
  height = c = 0
  while 1:
    if i >= len(header):
      raise ValueError('EOF in wbmp height.')
    c += 7
    if c > 14:  # Heuristic guess based on WAP speeds and bandwidth costs.
      raise ValueError('wbmp height too long.')
    b = ord(header[i])
    i += 1
    f += 1  # Info stating that c isn't too much.
    height = height << 7 | (b & 0x7f)
    if b < 0x80:
      break
  if not (width > 15 and height > 15):
    # Prevent '\0\0\1\1' from being recognized as
    # format=wbmp width=1 height=1. Most likely it's format=?.
    raise ValueError('wbmp dimensions too small.')
  return f, width, height


def count_is_wbmp(header):
  try:
    return parse_count_wbmp_header(header)[0]
  except ValueError:
    return 0


def analyze_wbmp(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/WBMP
  # https://fossies.org/linux/netpbm/converter/pbm/wbmptopbm.c
  # http://www.wapforum.org/what/technical/SPEC-WAESpec-19990524.pdf
  _, width, height = parse_count_wbmp_header(fread(32))
  info['format'], info['codec'] = 'wbmp', 'uncompressed'
  info['width'], info['height'] = width, height


def analyze_gd(fread, info, fskip):
  # gd_gd.c in libgd-2.2.5.tar.gz
  header = fread(7)
  if len(header) < 7:
    raise ValueError('Too short for gd.')
  magic, width, height, is_truecolor = struct.unpack('>HHHB', header[:7])
  if magic < 0xfffe:
    raise ValueError('gd signature not found.')
  if is_truecolor != (magic == 0xfffe):
    raise ValueError('Bad gd is_truecolor.')
  if not is_truecolor:
    data = fread(2)
    if len(data) == 2:
      color_count, = struct.unpack('>H', data)
      if not 1 <= color_count <= 256:
        raise ValueError('Bad gd palette color count: %d' % color_count)
  info['format'], info['codec'] = 'gd', 'uncompressed'
  if not width:
    raise ValueError('Bad gd width.')
  if not height:
    raise ValueError('Bad gd height.')
  info['width'], info['height'] = width, height


def analyze_gd2(fread, info, fskip):
  # https://github.com/libgd/libgd/blob/577dc4475dc58bb1f3da81f91be440353a16120b/src/gd_gd2.c#L30-L58
  header = fread(19)
  if len(header) < 19:
    raise ValueError('Too short for gd2.')
  (magic, version, width, height, chunk_size, format,
   x_chunk_count, y_chunk_count, is_truecolor,
  ) = struct.unpack('>4s7HB', header[:19])
  if magic != 'gd2\0':
    raise ValueError('gd2 signature not found.')
  if version not in (1, 2):
    raise ValueError('Bad gd2 version: %d' % version)
  if not chunk_size:
    raise ValueError('Bad gd2 chunk_size.')
  if not 1 <= format <= 4:
    raise ValueError('Bad gd2 format: %d' % format)
  if version > 1:
    if is_truecolor != (format > 2):
      raise ValueError('Bad gd2 is_truecolor.')
    if not is_truecolor:
      data = fread(2)
      if len(data) == 2:
        color_count, = struct.unpack('>H', data)
        if not 1 <= color_count <= 256:
          raise ValueError('Bad gd2 palette color count: %d' % color_count)
  info['format'] = 'gd2'
  info['codec'] = ('flate', 'uncompressed')[format & 1]
  if not width:
    raise ValueError('Bad gd2 width.')
  if not height:
    raise ValueError('Bad gd2 height.')
  info['width'], info['height'] = width, height


def parse_cups_raster_header(header):
  # http://fileformats.archiveteam.org/wiki/CUPS_Raster
  # https://www.cups.org/doc/spec-raster.html
  if len(header) < 408 and len(header) != 4:
    raise ValueError('Too short for cups-raster.')
  if header[:4] not in ('RaSt', 'tSaR', 'RaS2', '2SaR', 'RaS3', '3SaR'):
    raise ValueError('cups-raster signature not found.')
  if len(header) == 4:
    return 400, None, None, None, None
  fmt = '<>'[header[0] == 'R']
  (magic, media_class, media_color, media_type, output_type,
   advance_distance, advance_media, collate, cut_media, duplex,
   hw_resolution_x, hw_resolution_y, imaging_llx, imaging_lly, imaging_urx,
   imaging_ury, insert_sheet, jog, leading_edge, margin_left_origin,
   margin_bttom_origin, manual_feed, media_position, media_weight,
   mirror_print, negative_print, num_copies, orientation, output_face_up,
   pt_width, pt_height, separations, tray_switch, tumble, cups_width,
   cups_height, cups_media_type, cups_bits_per_color, cups_bits_per_pixel,
   cups_bytes_per_line, cups_color_order, cups_color_space,
  ) = struct.unpack(fmt + '4s64s64s64s64s7L4l26L', header[:408])
  dict_obj = locals()
  for name in (
      'hw_resolution_x', 'hw_resolution_y', 'pt_width', 'pt_height',
      'cups_width', 'cups_height', 'cups_bits_per_color',
      'cups_bits_per_pixel', 'cups_bytes_per_line'):
    if not dict_obj[name]:
       raise ValueError('Expected nonzero cups-raster %s.' % name)
  if imaging_urx < imaging_llx:
    raise ValueError('Bad cups-raster imaging x.')
  if imaging_ury < imaging_lly:
    raise ValueError('Bad cups-raster imaging y.')
  c = 400  # Because of magic. Our caller will subtract this.
  log2_sub = '\x00\x00\x0c\x13\x19\x1d #%\')+,./0234566789::;<<==>??@@AABBBCCDDEEEFFFGGGHHHIIIJJJKKKKLLLLMMMMNNNNOOOOOPPPPPQQQQQRRRRRSSSSSSTTTTTTUUUUUUVVVVVVVWWWWWWWXXXXXXXXYYYYYYYYZZZZZZZZ[[[[[[[[[\\\\\\\\\\\\\\\\\\]]]]]]]]]]^^^^^^^^^^^___________```````````aaaaaaaaaaaaabbbbbbbbbbbbbcccccccccccccd'
  for name, upper_bound in (
      ('advance_media', 5),
      ('collate', 2),
      ('cut_media', 5),
      ('duplex', 2),
      ('insert_sheet', 2),
      ('jog', 4),
      ('leading_edge', 4),
      ('manual_feed', 2),
      ('media_position', 256),
      ('mirror_print', 2),
      ('negative_print', 2),
      ('num_copies', 1024),
      ('orientation', 4),
      ('output_face_up', 2),
      ('separations', 2),
      ('tray_switch', 2),
      ('tumble', 2),
      ('cups_bits_per_color', 17),  # TOOD(pts): Only allow 1, 2, 4, 8 and 16.
      ('cups_bits_per_pixel', 240),  # TOOD(pts): Only allow 1...
      ('cups_color_order', 3),
      ('cups_color_space', 128),  # Maximum current value is 62.
  ):
    # TODO(pts): Accept larger (<256) values, but increment c less.
    if dict_obj[name] >= upper_bound:
      raise ValueError('Bad cups-raster %s, must be less than %d: %d' %
                       (name, dict_obj[name], upper_bound))
    # The smaller the upper bound, the larger c becomes, thus the more sure
    # we are that header is of cups-raster.
    if 257 <= upper_bound <= 1024:
      c -= ord(log2_sub[4])
      upper_bound >>= 2
    c += 400 - ord(log2_sub[upper_bound])  # TODO(pts): Precompute this.
  for data in (media_class, media_color, media_type, output_type):
    c += 100 * (64 - len(data.rstrip('\0')))
  def fix_asciiz(data):
    return data.split('\0', 1)[0]
  media_class = fix_asciiz(media_class)
  media_color = fix_asciiz(media_color)
  media_type = fix_asciiz(media_type)
  output_type = fix_asciiz(output_type)
  if media_class == 'PwgRaster':
    c += 100 * len(media_class)
  if output_type == 'Automatic':
    c += 100 * len(output_type)
  return c, pt_width, pt_height, cups_width, cups_height


def count_is_cups_raster(header):
  try:
    return parse_cups_raster_header(header)[0]
  except ValueError:
    return 0


def analyze_cups_raster(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/CUPS_Raster
  # https://www.cups.org/doc/spec-raster.html
  _, pt_width, pt_height, cups_width, cups_height = (
      parse_cups_raster_header(fread(408)))
  info['format'] = 'cups-raster'
  if pt_width is not None:
    (info['pt_width'], info['pt_height'], info['width'], info['height'],
    ) = pt_width, pt_height, cups_width, cups_height


def analyze_alias_pix(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/Alias_PIX
  # http://www.martinreddy.net/gfx/2d/PIX.txt
  # Used on IRIX. Software: Alias 3D, PowerAnimator, Wavefront.
  header = fread(10)
  if len(header) < 10:
    raise ValueError('Too short for alias-pix.')
  width, height, x_offset, y_offset, bpc = struct.unpack('>5H', header[:10])
  if x_offset or y_offset or bpc not in (8, 24):
    raise ValueError('alias-pix signature not found.')
  info['format'], info['codec'] = 'alias-pix', 'rle'
  info['width'], info['height'] = width, height


def analyze_photocd(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/Photo_CD
  # https://www.fileformat.info/format/photocd/egff.htm
  # https://github.com/OpenPrinting/cups-filters/blob/master/cupsfilters/image-photocd.c
  # https://mcampos-quinn.github.io/2018/12/20/pcd-normalization.html
  # http://tedfelix.com/PhotoCD/
  #
  # We could be much smarter about the dimensions, e.g. we could get the
  # dimensions of the highest-resolutin image (number 6, e.g. display
  # file.pcd'[6]') in the .pcd file). Maybe tedfelix.com can advise.
  header = fread(32)
  if len(header) < 32:
    raise ValueError('Too short for photocd.')
  if header[:36].rstrip('\xff'):
    raise ValueError('photcd signature not found.')
  info['format'] = info['codec'] = 'photocd'
  header += fread(41)
  if len(header) >= 72:
    width, height = 768, 512  # TODO(pts): Usage the largest resolution.
    if (ord(header[72]) & 63) != 8:
      width, height = height, width
    if fskip(2048 - len(header)):
      data = fread(7)
      if len(data) == 7 and data != 'PCD_IPI':
        raise ValueError('Bad photocd sector 1 signature.')
    info['width'], info['height'] = width, height


def analyze_fits(fread, info, fskip):
  # http://justsolve.archiveteam.org/wiki/Flexible_Image_Transport_System
  # https://en.wikipedia.org/wiki/FITS
  # https://fits.gsfc.nasa.gov/standard40/fits_standard40aa-le.pdf
  # http://www.stsci.edu/itt/review/dhb_2011/Intro/intro_ch23.html
  data = fread(80)
  if len(data) < 11:
    raise ValueError('Too short for fits.')
  if not data.startswith('SIMPLE  = '):
    raise ValueError('fits signature not found.')
  if data[10 : 80].split('/', 1)[0].strip(' ') != 'T':
    raise ValueError('Bad fits simple value.')
  info['format'] = 'fits'
  if len(data) < 80:
    return
  # To get info['codec'], we'd need to analyze "ZCMPTYPE= '...'" within
  # "XTENSION= 'BINTABLE'" after the primary data array.
  dimens = {}
  while 1:
    data = fread(80)
    if len(data) < 80:
      raise ValueError('EOF in fits card.')
    key = data[:8].rstrip(' ')
    if not (key.replace('-', 'A').replace('_', 'A').isalnum() and key.upper() == key and key[0].isalpha()):
      raise ValueError('Bad fits key: %r' % key)
    if data[8 : 10] == '= ':
      value = data[10 : 80].split('/', 1)[0].strip(' ')
      if key in ('NAXIS1', 'NAXIS2'):
        dimen_key = ('width', 'height')[key == 'NAXIS2']
        try:
          dimens[dimen_key] = int(value)
        except ValueError:
          raise ValueError('Bad fits %s value: %r' % (key, value))
    elif data[8 : 10].rstrip(' '):
      raise ValueError('Bad definition for fits key: %s' % key)
    elif key == 'END':
      break
  if 'width' in dimens and 'height' in dimens:
    info['width'], info['height'] = dimens['width'], dimens['height']


def analyze_xloadimage_niff(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/NIFF_(xloadimage)
  # niff.c in xloadimage_4.1.orig.tar.gz
  header = fread(16)
  if len(header) < 8:
    raise ValueError('Too short for xloadimage-niff.')
  if not header.startswith('NIFF\0\0\0\1'):
    raise ValueError('xloadimage-niff signature not found.')
  info['format'], info['codec'] = 'xloadimage-niff', 'uncompressed'
  if len(header) >= 16:
    (magic, version, info['width'], info['height'],
    ) = struct.unpack('>4sLLL', header)


def analyze_sun_taac(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/Sun_TAAC_image
  # Also known as VFF and Sun IFF.
  # libim/imiff.c in imtools_v3.0.tar.gz
  header = fread(512)
  if len(header) < 6:
    raise ValueError('Too short for sun-taac.')
  first_bytes = '\r\nabcdefghijklmnopqrstuvwxyz'
  if not (header.startswith('ncaa') and
          header[4] in first_bytes and header[5] in first_bytes):
    raise ValueError('sun-taac signature not found.')
  info['format'], info['codec'] = 'sun-taac', 'uncompressed'
  if len(header) <= 6:
    return
  header = header.replace('\r', '\n')
  while 1:
    i = header.find('\f\n', 4)
    if i >= 0:
      break
    if len(header) == 2048:
      raise ValueError('sun-taac header too long.')
    elif len(header) not in (512, 1024):
      raise ValueError('EOF in sun-taac header.')
    header += fread(len(header)).replace('\r', '\n')
  for line in header[4 : i].replace(';', '\n').split('\n'):
    line = line.strip()
    if '=' in line:
      key, value = line.split('=', 1)
      key, value = key.strip(), value.strip()
      if not (key.isalpha() and key.lower() == key):
        raise ValueError('Bad sun-taac key: %r' % key)
      if key == 'size':
        value = value.split()
        if len(value) != 2:
          raise ValueError('Bad sun-taac size item count.')
        try:
          info['width'], info['height'] = map(int, value)
        except ValueError:
          raise ValueError('Bad sun-taac size: %r' % value)
    elif line:
      raise ValueError('Bad sun-taac header line.')


FACESAVER_PREFIXES = ('FirstName:', 'LastName:', 'E-mail:', 'Telephone:', 'Company:', 'Address1:', 'Address2:', 'CityStateZip:', 'PicData:', 'Image:')


def count_is_facesaver(header):
  for prefix in FACESAVER_PREFIXES:
    if header.startswith(prefix):
      return 100 * len(prefix)
  return 0


def analyze_facesaver(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/FaceSaver
  # http://www.fileformat.info/format/face/egff.htm
  data = fread(16)
  if len(data) < 6:
    raise ValueError('Too short for facesaver.')
  for prefix in FACESAVER_PREFIXES:
    if data.startswith(prefix):
      break
  else:
    raise ValueError('facesaver signature not found.')
  info['format'], info['codec'] = 'facesaver', 'uncompressed'
  if len(data) == data.find(':') + 1:
    return
  data += fread(512 - len(data))
  while 1:
    i1, i2 = data.find('\n\n'), data.find('\n\r\n')
    if i1 >= 0 or i2 >= 0:
      break
    if len(header) == 2048:
      raise ValueError('facesaver header too long.')
    elif len(header) not in (512, 1024):
      raise ValueError('EOF in facesaver header.')
    header += fread(len(header))
  if i1 >= 0 and i2 >= 0 and i2 < i1:
    i1 = i2
  for line in data[:i1].replace('\r\n', '\n').split('\n'):
    if line.startswith('PicData:'):  # Contains actual pixels.
      items = line[line.find(':') + 1:].strip().split()
      if len(items) != 3:
        raise ValueError('Bad facesaver picdata item count.')
      try:
        info['width'], info['height'] = map(int, items[:2])
      except ValueError:
        raise ValueError('Bad facesaver picdata: %r' % items)


def count_is_mcidas_area(header):
  if len(header) < 20:
    return 0
  fmt = '<>'[header[7] != '\0']
  status, ftype, satid, ndate, ntime = struct.unpack(fmt + '5L', header[:20])
  return (status == 0 and ftype == 4 and satid < 0x400 and ndate <= 196366 and ntime <= 235959) and 1650


def analyze_mcidas_area(fread, info, fskip):
  # https://www.ssec.wisc.edu/mcidas/doc/prog_man/2015/formats-1.html
  # https://www.ssec.wisc.edu/mcidas/doc/misc_doc/area2.html
  header = fread(40)
  if len(header) < 20:
    raise ValueError('Too short for mcidas-area.')
  if not count_is_mcidas_area(header):
    raise ValueError('mcidas signature not found.')
  info['format'], info['codec'] = 'mcidas-area', 'uncompressed'
  if len(header) >= 40:
    fmt = '<>'[header[7] != '\0']
    info['height'], info['width'] = struct.unpack(fmt + 'LL', header[32 : 40])


def analyze_macpaint(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/MacPaint
  # http://www.idea2ic.com/File_Formats/macpaint.pdf
  # https://www.fileformat.info/format/macpaint/egff.htm
  if not (info.get('subformat') == 'macbinary' and info.get('format') == 'macpaint'):
    header = fread(12)
    if len(header) < 12:
      raise ValueError('Too short for macpaint.')
    if not ((header[:4] in ('\0\0\0\2', '\0\0\0\3') and
             header[4 : 12] in
             ('\0\0\0\0\0\0\0\0', '\xff\xff\xff\xff\xff\xff\xff\xff'))):
      raise ValueError('macpaint signature not found.')
  info['format'], info['codec'] = 'macpaint', 'rle'
  info['width'], info['height'] = 576, 720


def analyze_fit(fread, info, fskip):
  # Mentioned just here: https://github.com/file/file/blob/master/magic/Magdir/images
  header = fread(16)
  if len(header) < 16:
    raise ValueError('Too short for fit.')
  if header[:4] not in ('IT01', 'IT02'):
    raise ValueError('fit signature not found.')
  magic, width, height, depth = struct.unpack('>4sLLL', header[:16])
  if not 1 <= depth <= 32:  # Just a heuristic check.
    raise ValueError('Bad fit depth: %d' % depth)
  info['format'] = 'fit'
  info['width'], info['height'] = width, height


# Based on: https://en.wikipedia.org/wiki/Apple_Icon_Image_format
#
# It's unlikely that new entries will be added here, becase new icons tend
# to be compressed, and this dict contains only the uncompressed ones.
ICNS_FIXED_SIZE_FORMATS = {
    'icon': (128, 32, 32),
    'icn#': (256, 32, 32),
    'icm#': (48, 16, 12),
    'icm4': (96, 16, 12),
    'icm8': (192, 16, 12),
    'ics#': (64, 16, 16),
    'ics4': (128, 16, 16),
    'ics8': (256, 16, 16),
    'is32': (768, 16, 16),
    's8mk': (256, 16, 16),
    'icl4': (512, 32, 32),
    'icl8': (1024, 32, 32),
    'il32': (3072, 32, 32),
    'l8mk': (1024, 32, 32),
    'ich#': (288, 48, 48),
    'ich4': (1152, 48, 48),
    'ich8': (2304, 48, 48),
    'ih32': (6912, 48, 48),
    'h8mk': (2304, 48, 48),
    'it32': (49152, 128, 128),
    't8mk': (16384, 128, 128),
    'ic04': (0, 16, 16),
    'ic05': (0, 32, 32),
    'icsb': (0, 36, 36),
    'icsb': (0, 18, 18),
}


def analyze_icns(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/ICNS
  # https://en.wikipedia.org/wiki/Apple_Icon_Image_format
  # gdk-pixbuf/io-icns.c in  gdk-pixbuf-2.40.0.tar.xz
  header = fread(8)
  if len(header) < 8:
    raise ValueError('Too short for icns.')
  if not header.startswith('icns'):
    raise ValueError('icns signature not found.')
  size, = struct.unpack('>L', header[4 : 8])
  if size < 32:
    raise ValueError('Bad icns size: %d' % size)
  info['format'], info['icon_count'] = 'icns', 0
  remaining = size - 8
  best, is_first = (), True
  while remaining > 0:  # Find the largest icon. The earlier the better.
    if remaining < 16:
      raise ValueError('Too few bytes remaining in icns.')
    data = fread(16)
    if len(data) != 16:
      if not data and is_first:
        return
      raise ValueError('EOF in icns icon header.')
    is_first = False
    xtype, size, magic = struct.unpack('>4sL8s', data)
    if not 16 <= size <= remaining:
      raise ValueError('Bad icns icon size: %d')
    xtype = xtype.lower().strip()
    if ((xtype.startswith('icp') and xtype[3].isdigit()) or
        (xtype.startswith('ic') and xtype[3 : 4].isdigit() and xtype >= 'ic07')):
      width = height = codec = analyze_func = None
      # Observed: 'jpeg2000' jp2.
      # Documented: 'png', it Will be replaced with codec='flate'.
      codec = quick_detect_image_format(magic)
      if codec:
        magic += fread(min(1024, size - 8 - len(magic)))
        fread2, fskip2 = get_string_fread_fskip(magic)
        info2 = {'format': codec, 'codec': codec}
        analyze_by_format(fread2, info2, fskip2, codec, None)
        codec = info2['codec']
        if 'width' in info2 and 'height' in info2:
          width, height = info2['width'], info2['height']
      else:
        raise ValueError('Unknown icns icon magic: %r' % magic)
    elif xtype in ICNS_FIXED_SIZE_FORMATS:
      uc_size, width, height = ICNS_FIXED_SIZE_FORMATS[xtype]
      if size - 8 == uc_size:
        codec = 'uncompressed'
      else:
        codec = 'rle'
    elif not xtype.rstrip('#').isalnum():  # Corrupt file?
      raise ValueError('Bad icns icon xtype: %r' % xtype)
    else:
      codec = None
    if codec:
      #print (xtype, size - 8, codec, width, height)
      best = max(best, (width * height, remaining, width, height, codec, xtype))
      info['icon_count'] += 1
    if not fskip(size - 8 - len(magic)):
      raise ValueError('EOF in icns icon data.')
    remaining -= size
  if best:
    _, _, info['width'], info['height'], info['codec'], info['subformat'] = best


def analyze_dds(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/DirectDraw_Surface
  # https://en.wikipedia.org/wiki/S3_Texture_Compression#DXT4_and_DXT5
  # Samples in the data/DDS folder of: git clone --depth 1 https://github.com/timfel/tombexcavator
  header = fread(128)
  if len(header) < 88:
    raise ValueError('Too short for dds.')
  if not header.startswith('DDS '):
    raise ValueError('dds signature not found.')
  (size, flags, height, width, pols, depth, map_map_count,
   pf_size, pf_flags, codec,
  ) = struct.unpack('<7L44xLL4s', header[4 : 88])
  if size != 124:
    raise ValueError('Bad dds size: %d' % size)
  if pf_size != 32:
    raise ValueError('Bad dds pixelformat size: %d' % pf_size)
  info['format'], info['codec'] = 'dds', 'uncompressed'
  info['width'], info['height'] = width, height
  if pf_flags & 4 and not codec.endswith('\0\0\0'):
    codec = codec.lower().strip()
    if not codec.isalnum():
      raise ValueError('Bad dds codec: %r' % codec)
    # Typical values: 'dxt1', 'dxt2', 'dxt3', 'dxt4', 'dxt5', 'dx10', 'rgbg', 'grgb', 'yuy2', 'uyvy'.
    info['codec'] = codec


def analyze_olecf(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/Microsoft_Compound_File
  # http://forensicswiki.org/wiki/OLE_Compound_File
  header = fread(76)
  if len(header) < 8:
    raise ValueError('Too short for olecf.')
  if not (header.startswith('\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1') or
          header.startswith('\x0e\x11\xfc\x0d\xd0\xcf\x11\x0e')):
    raise ValueError('olecf signature not found.')
  info['format'] = 'olecf'
  if len(header) < 76:
    return
  (magic, clid, minor_version, dll_version, byte_order, sector_shift,
   mini_sector_shift, reserved0, reserved1, reserved2, csect_fat,
   sect_dir_start, signature, mini_sector_cutoff, sect_mini_fat_start,
   csect_mini_fat, sect_dif_start, sect_dif,
  ) = struct.unpack('<8s16sHHHHHHLLLLLLLLLL', header[:76])
  if byte_order != 0xfffe:
    raise ValueError('Bad olecf byte_order.')
  # http://fileformats.archiveteam.org/wiki/FlashPix
  # TODO(pts): Check dll_version and sector_shift based on olefile.
  if (magic[0] == '\xd0' and 9 <= sector_shift <= 18 and
      not reserved0 and not reserved1 and not reserved2 and
      clid == '\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0'):
    # https://github.com/decalage2/olefile/blob/7f15211f136146df0ccfc5b70be3961944a8be92/olefile/olefile.py#L1673-L1685
    root_dir_ofs = (sect_dir_start + 1) << sector_shift
    if fskip(root_dir_ofs - len(header)):
      data = fread(96)
      if len(data) == 96:
        (name_utf16, name_count, mse, bflags, sid_left_sib, sid_right_sib,
         sid_child, clsid,
        ) = struct.unpack('<64sHBBLLL16s', data)
        if (name_utf16.startswith('R\0') and 2 <= name_count <= 64 and
            mse == 5 and
            sid_left_sib == 0xffffffff and sid_right_sib == 0xffffffff):
          if clsid == '\x00\x67\x61\x56\x54\xc1\xce\x11\x85\x53\x00\xaa\x00\xa1\xf9\x5b':
            # http://fileformats.archiveteam.org/wiki/FlashPix
            # http://graphcomp.com/info/specs/livepicture/fpx.pdf
            # pfx.pdf also contains a nice description of olecf.
            info['format'] = 'fpx'  # Kodak FlashPix.
            # Finding the image with the largest resolution and returning
            # its name would be way too complicated: we'd have to navigate
            # the FAT chains and directory structures.
            # src/PIL/FpxImagePlugin.py in Pillow-7.0.0.tar.gz uses
            # `import olefile' to parse fpx.
            return


def analyze_binhex(fread, info, fskip, format='binhex', fclass='compress',
                   spec=((0, '(This file must be converted with BinHex 4.0)'),
                         (0, '(This file must be converted with BinHex.Hex)'),
                         (0, '(This file must be converted with BinHex'),
                         (0, '(This file '),
                         (0, '(Convert with'))):
  # http://fileformats.archiveteam.org/wiki/BinHex
  # https://tools.ietf.org/html/rfc1741
  # https://en.wikipedia.org/wiki/BinHex
  # macutils/hexbin/hexbin.c in http://archive.ubuntu.com/ubuntu/pool/universe/m/macutils/macutils_2.0b3.orig.tar.gz
  # Original software for hexbin.c: macutil-2.03b3, 1992-10-22.
  # binhex_2.0.bin on https://macintoshgarden.org/apps/binhex-20
  # https://www.iana.org/assignments/media-types/application/applefile
  header = fread(13)
  if len(header) < 13:
    raise ValueError('Too short for binhex.')
  if not (header.startswith('(This file ') or header.startswith('(Convert with')):
    raise ValueError('binhex signature not found.')
  header += fread(512 - len(header))
  header = header.replace('\r', '\n')
  i = header.find('\n')
  while 0 < i < len(header) and header[i] == '\n':
    i += 1
  if not (0 < i < len(header) and header[i] in ':#'):
    raise ValueError('binhex subformat signature not found.')
  if header[i] == ':':
    info['format'], info['subformat'], info['codec'] = 'binhex', 'hqx', 'rle'  # .hqx, BinHex 4.0
  else:
    i = header.find('\n', i) + 1
    if i <= 0:
      raise ValueError('EOF in binhex #TYPEAUTH line.')
    while i < len(header) and header[i] == '\n':
      i += 1
    if i + 13 < len(header):
      raise ValueError('EOF in binhex data.')
    if header[i : i + 13] == '***COMPRESSED':
      info['format'], info['subformat'], info['codec'] = 'binhex', 'hcx', 'uncompressed'  # .hcx, BinHex 2.0
    else:
      info['format'], info['subformat'], info['codec'] = 'binhex', 'hex', 'uncompressed'  # .hex, BinHex 1.0


def analyze_flate(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/Zlib
  # https://tools.ietf.org/html/rfc1950
  header = fread(2)
  if len(header) < 2:
    raise ValueError('Too short for flate.')
  if not (header[0] in '\x08\x18\x28\x38\x48\x58\x68\x78' and
          header[1] in '\x01\x5e\x9c\xda'):
    raise ValueError('flate signature not found.')
  info['format'] = info['codec'] = 'flate'


def analyze_gz(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/Gzip
  # https://wiki.alpinelinux.org/wiki/Alpine_package_format
  # Also .tar.gz and Alpine apk.
  header = fread(3)
  if len(header) < 3:
    raise ValueError('Too short for gz.')
  if not header.startswith('\x1f\x8b\x08'):
    raise ValueError('gz signature not found.')
  info['format'], info['codec'] = 'gz', 'flate'


def analyze_xz(fread, info, fskip, format='xz', fclass='compress',
               spec=(0, '\xfd7zXZ\0')):
  # http://fileformats.archiveteam.org/wiki/XZ
  header = fread(6)
  if len(header) < 6:
    raise ValueError('Too short for xz.')
  if not header.startswith('\xfd7zXZ\0'):
    raise ValueError('xz signature not found.')
  info['format'], info['codec'] = 'xz', 'lzma'


def analyze_lzma(fread, info, fskip):
  # http://fileformats.archiveteam.org/wiki/LZMA_Alone
  header = fread(13)
  if len(header) < 13:
    raise ValueError('Too short for lzma.')
  if not (header.startswith('\x5d\0\0') and header[12] in '\0\xff'):
    raise ValueError('lzma signature not found.')
  info['format'] = info['codec'] = 'lzma'


MACBINARY_TYPES = ('PICT', 'PNTG', 'SIT!', 'SITD', 'SIT2', 'SIT5')


def is_macbinary(header):
  return (len(header) >= 128 and header[0] == '\0' and
          1 <= ord(header[1]) <= 63 and
          header[74] == header[82] == '\0' and
          header[65 : 69] in MACBINARY_TYPES)


def analyze_macbinary(fread, info, fskip, format='macbinary', fclass='other',
                      spec=(0, '\0', 128, lambda header: (is_macbinary(header), 800))):
  # http://fileformats.archiveteam.org/wiki/MacBinary
  # https://github.com/mietek/theunarchiver/wiki/MacBinarySpecs
  # https://www.iana.org/assignments/media-types/application/applefile
  # TODO(pts): Check checksum for MacBinary II and MacBinary III,
  header = fread(128)
  if len(header) < 128:
    raise ValueError('Too short for macbinary.')
  if not is_macbinary(header):
    raise ValueError('macbinary signature not found or unknown type.')
  codec_tag = header[65 : 69].strip().strip('.').lower()
  assert codec_tag in MAC_TYPE_MAP
  info['format'] = format = MAC_TYPE_MAP[codec_tag][0]
  info['subformat'] = 'macbinary'
  if 'format' == 'stuffit':
    return
  try:
    analyze_by_format(fread, info, fskip, format, None)
  except ValueError, e:
    if not str(e).startswith('Too short for '):  # TODO(pts): Only ignore if file size is exactly 128 bytes.
      raise


def parse_opentype_header(header):
  if len(header) < 12:
    raise ValueError('Too short for opentype.')
  if not (header.startswith('\0\1\0\0') or header.startswith('OTTO')):
    raise ValueError('opentype signature not found.')
  table_count, sr, es, rs = struct.unpack('>HHHH', header[4 : 12])
  # TODO(pts): What is the minimum number of tables? More than 1.
  if not 1 <= table_count <= 64:  # Maximum 32 in the wild.
    raise ValueError('Bad opentype table_count: %d' % table_count)
  e = 1
  while table_count >> e:
    e += 1
  e -= 1
  if sr != (16 << e):
    raise ValueError('Bad opentype search_range: %d' % sr)
  if es != e:
    raise ValueError('Bad opentype entry_selector: %d' % es)
  if rs != (table_count << 4) - sr:
    raise ValueError('Bad opentype range_shift: %d' % rs)
  is_truetype = header.startswith('\0')
  return 388 + 125 + 600, table_count, is_truetype


def count_is_opentype(header):
  try:
    return parse_opentype_header(header)[0]
  except ValueError:  # TODO(pts): Generalize this pattern.
    return 0


# Exclude LTSH and VDMX tables from here, they are part of Windows 95 *.ttf.
OPENTYPE_ONLY_TABLES = ('BASE', 'CBDT', 'CBLC', 'CFF ', 'CFF2', 'COLR', 'CPAL', 'DSIG', 'EBDT', 'EBLC', 'GDEF', 'GPOS', 'GSUB', 'HVAR', 'JSTF', 'MATH', 'MERG', 'MVAR', 'PCLT', 'STAT', 'SVG ', 'VORG', 'VVAR')


def analyze_opentype(fread, info, fksip, format='opentype', ext=('.otf', '.ttf'), extra_formats=('truetype',),
                     spec=(0, ('\0\1\0\0', 'OTTO'), 12, lambda header: adjust_confidence(388, count_is_opentype(header)))):
  # OpenType, tables: https://docs.microsoft.com/en-us/typography/opentype/spec/otff
  # TrueType, tables: https://developer.apple.com/fonts/TrueType-Reference-Manual/
  header = fread(12)
  _, table_count, is_truetype = parse_opentype_header(header)
  info['format'] = 'opentype'
  oots = set(OPENTYPE_ONLY_TABLES)
  glyph_format = 0
  for i in xrange(table_count):
    data = fread(16)
    if len(data) < 16:
      if not (data or i):
        break
      raise ValueError('EOF in opentype table.')
    name = data[:4]
    if name == 'glyf':
      glyph_format |= 1
    elif name == 'CFF ':
      glyph_format |= 2
    if name in oots:
      is_truetype = False
  if glyph_format == 2:
    info['glyph_format'] = 'cff'  # Type 2. (Or Type 1?)
  elif glyph_format == 1:
    info['glyph_format'] = 'truetype'  # Type 42.
  if glyph_format == 1 and is_truetype:
    info['format'] = 'truetype'


MACHO_BINARY_TYPES = {
    1: 'object',
    2: 'executable',
    3: 'fixedvm-shlib',
    4: 'core',
    5: 'preload',
    6: 'shlib',
    7: 'dld',
    8: 'bundle',
    9: 'shlib-stub',
    10: 'dsym-cf',
    11: 'kext',
}

MACHO_ARCHS = {
    1: 'vax',
    2: 'romp',
    4: 'ns32032',
    5: 'ns32332',
    6: 'm68k',
    7: 'i386',
    8: 'mips',
    9: 'ns32532',
    10: 'mc98000',
    11: 'hhpa',
    12: 'arm',
    13: 'm88k',
    14: 'sparc',
    15: 'i860g',
    16: 'alpha',
    17: 'rs6000',
    18: 'powerpc',
    107: 'amd64',
    108: 'mips64',
    112: 'arm64',
    114: 'sparc',
    118: 'powerpc64',
}


def analyze_macho(fread, info, fskip, format='macho', fclass='code',
                  spec=((0, ('\xce\xfa\xed\xfe', '\xcf\xfa\xed\xfe'), 4, tuple(chr(c) for c in xrange(1, 23)), 5, '\0\0', 7, ('\0', '\1'), 12, tuple(chr(c) for c in xrange(1, 16)), 13, '\0\0\0'),
                        (0, ('\xfe\xed\xfa\xce', '\xfe\xed\xfa\xcf'), 4, ('\0', '\1'), 5, '\0\0', 7, tuple(chr(c) for c in xrange(1, 23)), 12, '\0\0\0', 15, tuple(chr(c) for c in xrange(1, 16))),
                        (0, '\xbe\xba\xfe\xca', 4, tuple(chr(c) for c in xrange(1, 31)), 5, '\0\0\0'),
                        (0, '\xca\xfe\xba\xbe\0\0\0', 7, tuple(chr(c) for c in xrange(1, 31))))):
  # http://fileformats.archiveteam.org/wiki/Mach-O
  # https://github.com/x64dbg/btparser/blob/d5034cf6d647e98cb01e9e1fc4efa5086f8fc6a5/btparser/tests/MachOTemplate.bt
  header = fread(16)
  if len(header) < 16:
    raise ValueError('Too short for macho.')
  fmt = '<>'[header.startswith('\xfe') or header.startswith('\xca')]
  magic, archx, subarch, binary_type = struct.unpack(fmt + 'LLLL', header[:16])
  if magic == 0xcafebabe and 1 <= archx <= 30:  # 30 to distinguish it from format=java-class.
    # https://en.wikipedia.org/wiki/Universal_binary
    # https://www.symbolcrash.com/2019/02/26/mach-o-universal-fat-binaries/
    info['format'], info['subformat'], info['binary_type'] = 'macho', 'universal', 'executable'  # Fat binary.
    info['endian'] = ('little', 'big')[fmt == '>']
    arch_count, archs, data = archx, [], header[8:]
    for _ in xrange(arch_count):
      if len(data) != 20:
        assert len(data) <= 20
        data += fread(20 - len(data))
        if len(data) < 20:
          raise ValueError('EOF in macho universal fat record.')
      archx, = struct.unpack(fmt + 'L', data[:4])
      data = ''
      archis64, arch = archx >> 24, archx & 0xffffff
      if archis64 not in (0, 1):
        raise ValueError('Bad macho archis64: %d' % archis64)
      if not 1 <= arch < 23:
        raise ValueError('Bad macho arch: %d' % arch)
      arch = arch + 100 * archis64
      archs.append(MACHO_ARCHS.get(arch, str(arch)))
    info['arch'] = ','.join(archs)
    return
  if (magic & ~1) != 0xfeedface:
    raise ValueError('macho signature not found.')
  archis64, arch = archx >> 24, archx & 0xffffff
  if archis64 not in (0, 1):
    raise ValueError('Bad macho archis64: %d' % archis64)
  if not 1 <= arch < 23:
    raise ValueError('Bad macho arch: %d' % arch)
  if not 1 <= binary_type < 16:
    raise ValueError('Bad macho binary_type: %d' % binary_type)
  info['format'] = 'macho'
  info['subformat'] = ('32bit', '64bit')[(magic & 1)]
  info['binary_type'] = MACHO_BINARY_TYPES.get(binary_type, str(binary_type))
  info['endian'] = ('little', 'big')[fmt == '>']
  arch = arch + 100 * archis64
  info['arch'] = MACHO_ARCHS.get(arch, str(arch))


def analyze_pef(fread, info, fskip, format='pef', fclass='code',
                spec=(0, 'Joy!peff', 8, ('pwpc', 'm68k'), 12, '\0\0\0\1', 32, '\0', 33, tuple(chr(c) for c in xrange(1, 33)), 34, '\0', 35, tuple(chr(c) for c in xrange(1, 33)))):
  # https://en.wikipedia.org/wiki/Preferred_Executable_Format
  # https://developer.apple.com/library/archive/documentation/mac/pdf/MacOS_RT_Architectures.pdf
  # The PEF is usually in the data fork, and usually it's powerpc.
  header = fread(36)
  if len(header) < 36:
    raise ValueError('Too short for pef.')
  (magic, arch, version, section_count, inst_section_count,
  ) = struct.unpack('>8s4sL16xHH', header[:36])
  if magic != 'Joy!peff':
    raise ValueError('pef signature not found.')
  if arch not in ('pwpc', 'm64k'):
    raise ValueError('Bad pef arch: %r' % arch)
  if version != 1:
    raise ValueError('Bad pef version: %d' % version)
  if not 1 <= section_count < 33:
    raise ValueError('Bad pef section_count: %d' % section_count)
  if not 1 <= inst_section_count < 33:
    raise ValueError('Bad pef inst_section_count: %d' % inst_section_count)
  info['format'], info['endian'], info['binary_type'] = 'pef', 'big', 'executable'
  info['arch'] = ('m68k', 'powerpc')[arch == 'pwpc']  # m68k here is CMF-86K.


ELF_OSABIS = {
    0: 'generic-sysv',
    1: 'hpux',
    2: 'netbsd',
    3: 'linux',
    4: 'hurd',
    6: 'solaris',
    7: 'aix',
    8: 'irix',
    9: 'freebsd',
    10: 'tru64',
    11: 'modesto',
    12: 'openbsd',
    13: 'openvms',
    14: 'nonstop-kernel',
    15: 'aros',
    16: 'fenixos',
    17: 'cloudabi',
    18: 'openvos',
}

# Names are consistent which MACHO_BINARY_TYPES.
ELF_BINARY_TYPES = {
    1: 'object',  # Relocatable.
    2: 'executable',
    3: 'shlib',
    4: 'core',
}

# Names are consistent which MACHO_ARCHS.
# Obsolete and obscure architectures are left out.
ELF_ARCHS = {
    1: 'we32100',
    2: 'sparc',
    3: 'i386',
    4: 'm68k',
    5: 'm88k',
    6: 'i386',  # Non-canonical i386.
    7: 'i386',  # Canonical i386.
    8: 'mips',  # Canonical mips.
    9: 'amdahl',
    10: 'mips',  # Non-canonical mips.
    11: 'rs6000',
    15: 'parisc',
    16: 'ncube',
    17: 'vpp500',
    18: 'sparc32plus',
    20: 'powerpc',
    21: 'powerpc64',
    22: 's390',
    40: 'arm',
    41: 'alpha',
    42: 'superh',
    43: 'sparcv9',
    50: 'ia64',  # Itanium.
    62: 'amd64',
    75: 'vax',
    80: 'mmix',
    92: 'openrisc',
    183: 'arm64',  # AArch64.
    243: 'riscv',
}


def analyze_elf(fread, info, fskip, format='elf', fclass='code',
                spec=((0, '\x7fELF', 4, ('\1', '\2'), 5, '\1', 6, '\1', 7, tuple(chr(c) for c in xrange(32)), 19, '\0', 20, '\1\0\0\0'),
                      (0, '\x7fELF', 4, ('\1', '\2'), 5, '\2', 6, '\1', 7, tuple(chr(c) for c in xrange(32)), 18, '\0', 20, '\0\0\0\1'))):
  # https://en.wikipedia.org/wiki/Executable_and_Linkable_Format
  header = fread(24)
  if len(header) < 24:
    raise ValueError('Too short for elf.')
  if not header.startswith('\x7fELF'):
    raise ValueError('elf signature not found.')
  fmt = '<>'[header[5] == '\2']
  (magic, classx, endian, version, osabi, abiversion, pad, binary_type, arch, version2,
  ) = struct.unpack(fmt + '4sBBBBB7sHHL', header)
  if classx not in (1, 2):
    raise ValueError('Bad elf class: %d' % classx)
  if endian not in (1, 2):
    raise ValueError('Bad elf endian: %d' % endian)
  if version != 1:
    raise ValueError('Bad elf version: %d' % version)
  if version2 != 1:
    raise ValueError('Bad elf version2: %d' % version2)
  if osabi >= 32:
    raise ValueError('Bad elf osabi: %d' % osabi)
  if arch > 255:
    raise ValueError('Bad elf arch: %d' % arch)
  info['format'] = 'elf'
  info['subformat'] = (0, '32bit', '64bit')[classx]
  info['endian'] = (0, 'little', 'big')[endian]
  info['os'] = ELF_OSABIS.get(osabi, str(osabi))
  # Don't match spec on this, there can be os-specific values.
  info['binary_type'] = ELF_BINARY_TYPES.get(binary_type, str(binary_type))
  # Don't match spec on this, there can be high values.
  info['arch'] = ELF_ARCHS.get(arch, str(arch))
  if not (1 <= binary_type  <= 4) or (0xfe00 <= binary_type):
    raise ValueError('Bad elf binary_type: %d' % binary_type)
  if not arch:
    raise ValueError('Bad elf arch, must not be 0.')


def analyze_wasm(fread, info, fskip, format='wasm', fclass='code',
                 spec=((0, '\0asm\1\0\0\0'),
                       (0, '(module', 7, WHITESPACE))):
  header = fread(8)
  if len(header) < 8:
    raise ValueError('Too short for wasm.')
  if header.startswith('\0asm\1\0\0\0'):
    # https://webassembly.github.io/spec/core/bikeshed/index.html#modules%E2%91%A0%E2%93%AA
    info['format'], info['subformat'] = 'wasm', 'binary'
  elif header.startswith('(module') and header[7].isspace():
    # https://webassembly.github.io/spec/core/bikeshed/index.html#modules%E2%91%A0%E2%93%AA
    info['format'], info['subformat'] = 'wasm', 'ascii'
  else:
    raise ValueError('wasm signature not found.')


def count_is_rtf(header):
  # http://fileformats.archiveteam.org/wiki/RTF
  # RTF specification 1.9.1. https://interoperability.blob.core.windows.net/files/Archive_References/[MSFT-RTF].pdf
  if not header.startswith('{\\rtf1'):
    return 0
  i = 6
  if header[i : i + 1] == ' ':
    i += 1
  # Try to make the match longer (stronger) by matching common control words.
  for suffix in ('{\\info', '\\fbidis', '\\ansi', '\\mac', '\\pc', '\\pca', '\\ansicpg'):
    j = i + len(suffix)
    if header[i : j] == suffix and not header[j : j + 1].isalpha():
      if header[j : j + 1] == ' ':
        j += 1
      return j * 100
  return i * 100


PYC_VERSION_MAGICS = dict((m, v) for v, ms in (
    ('1.5', (20121,)),
    ('1.6', (50428,)),
    ('2.0', (50823, 50824)),
    ('2.1', (60202, 60203)),
    ('2.2', (60717, 60718)),
    ('2.3', (62011, 62012, 62021, 62022)),
    ('2.4', (62051, 62052, 62061, 62062)),
    ('2.5', (62071, 62072, 62081, 62082, 62091, 62092, 62101, 62102, 62111, 62112, 62121, 62122, 62131, 62132)),
    ('2.6', (62151, 62152, 62161, 62162)),
    ('2.7', (62171, 62172, 62181, 62182, 62191, 62192, 62201, 62202, 62211, 62212)),
    ('3.0', (3000, 3001, 3010, 3011, 3020, 3021, 3030, 3031, 3040, 3041, 3050, 3051, 3060, 3061, 3071, 3081, 3091, 3101, 3103, 3111, 3131)),
    ('3.1', (3141, 3151)),
    ('3.2', (3160, 3170, 3180)),
    ('3.3', (3190, 3200, 3210, 3220, 3230)),
    ('3.4', (3250, 3260, 3270, 3280, 3290, 3300, 3310)),
    ('3.5', (3320, 3330, 3340, 3350, 3351)),
    ('3.6', (3360, 3361, 3370, 3371, 3372, 3373, 3375, 3376, 3377, 3378, 3379)),
    ('3.7', (3390, 3391, 3392, 3393, 3394)),
    ('3.8', (3401, 3410, 3411, 3412, 3413)),
    ) for m in ms)


def analyze_python_pyc(fread, info, fskip, format='python-pyc', fclass='code',
                       spec=((0, ('\x99N', '\xfc\xc4', '\x87\xc6', '\x88\xc6', '*\xeb', '+\xeb', '-\xed', '.\xed'), 2, '\r\n', 8, 'c\0\0\0\0'),
                             (0, (';\xf2', '<\xf2', 'E\xf2', 'F\xf2', 'c\xf2', 'd\xf2', 'm\xf2', 'n\xf2', 'w\xf2', 'x\xf2', '\x81\xf2', '\x82\xf2', '\x8b\xf2', '\x8c\xf2', '\x95\xf2', '\x96\xf2', '\x9f\xf2', '\xa0\xf2', '\xa9\xf2', '\xaa\xf2', '\xb3\xf2', '\xb4\xf2', '\xc7\xf2', '\xc8\xf2', '\xd1\xf2', '\xd2\xf2', '\xdb\xf2', '\xdc\xf2', '\xe5\xf2', '\xe6\xf2', '\xef\xf2', '\xf0\xf2', '\xf9\xf2', '\xfa\xf2', '\x03\xf3', '\x04\xf3'), 2, '\r\n', 8, 'c\0\0\0\0\0\0\0\0'),
                             (0, ('\xb8\x0b', '\xb9\x0b', '\xc2\x0b', '\xc3\x0b', '\xcc\x0b', '\xcd\x0b', '\xd6\x0b', '\xd7\x0b', '\xe0\x0b', '\xe1\x0b', '\xea\x0b', '\xeb\x0b', '\xf4\x0b', '\xf5\x0b', '\xff\x0b', '\t\x0c', '\x13\x0c', '\x1d\x0c', '\x1f\x0c', "'\x0c", ';\x0c', 'E\x0c', 'O\x0c', 'X\x0c', 'b\x0c', 'l\x0c'), 2, '\r\n', 8, 'c\0\0\0\0\0\0\0\0'),
                             (0, ('v\x0c', '\x80\x0c', '\x8a\x0c', '\x94\x0c', '\x9e\x0c'), 2, '\r\n', 12, 'c\0\0\0\0\0\0\0\0'),
                             (0, ('\xb2\x0c', '\xbc\x0c', '\xc6\x0c', '\xd0\x0c', '\xda\x0c', '\xe4\x0c', '\xee\x0c', '\xf8\x0c', '\x02\r', '\x0c\r', '\x16\r', '\x17\r', ' \r', '!\r', '*\r', '+\r', ',\r', '-\r', '/\r', '0\r', '1\r', '2\r', '3\r'), 2, '\r\n', 12, ('c', '\xe3'), 13, '\0\0\0\0\0\0\0\0'),
                             (0, ('>\r', '?\r', '@\r', 'A\r', 'B\r', 'I\r', 'R\r', 'S\r', 'T\r', 'U\r'), 2, '\r\n', 4, ('\0', '\1', '\3'), 5, '\0\0\0', 16, ('c', '\xe3'), 17, '\0\0\0\0\0\0\0\0'),
                             (1, ('\x0d', '\x0e', '\x0f', '\x10'), 2, lambda header: (len(header) >= 2 and 3414 <= struct.unpack('<H', header[:2])[0] <= 4181, 3), 2, '\r\n', 4, ('\0', '\1', '\3'), 5, '\0\0\0', 16, ('c', '\xe3'), 17, '\0\0\0\0\0\0\0\0'))):
  header = fread(25)
  if len(header) < 25:
    raise ValueError('Too short for python-pyc.')
  magic, magic2 = struct.unpack('<H2s', header[:4])
  if 3414 <= magic <= 4181:  # 4181 is arbirary, looking 2 * 256 into the future.
    version = '3.8+'
  else:
    version = PYC_VERSION_MAGICS.get(magic)
  if version is None or magic2 != '\r\n':
    raise ValueError('python-pyc magic no found.')
  if ((version < '2.3' and header[8 : 13] != 'c\0\0\0\0') or   # header[4 : 8] is mtime.
      ('2.3' <= version < '3.3' and header[8 : 17] != 'c\0\0\0\0\0\0\0\0') or  # header[4 : 8] is mtime.
      (version == '3.3' and header[12 : 21] != 'c\0\0\0\0\0\0\0\0') or  # header[4 : 8] is mtime, header[8 : 12] is source_size.
      ('3.4' <= version < '3.7' and not (header[12] in 'c\xe3' and header[13 : 21] == '\0\0\0\0\0\0\0\0')) or  # header[4 : 8] is mtime, header[8 : 12] is source_size.
      ('3.7' <= version and not (header[4] in '\0\1\3' and header[5 : 8] == '\0\0\0' and header[16] in 'c\xe3' and header[17 : 25] == '\0\0\0\0\0\0\0\0'))):
    raise ValueError('Bad python-pyc code for version %s.' % version)
  info['format'], info['subformat'] = 'python-pyc', version


add_format(format='ocaml-bytecode', fclass='code',
           spec=((0, '\x54\0\0\0', 6, '\0\0'),
                 (0, '\0\0\0\x54\0\0')))
  # Bytecode file format explained here: https://github.com/ocaml/ocaml/blob/b1fdc44547dc20d891bd260b55740f37c57b4961/runtime/caml/exec.h#L23-L38
  # Bytecode file ends with 'Caml1999X027', no header.
  # Usually the file starts with section "CODE", which contains 32-bit
  # opcodes in either byte order:
  # https://github.com/ocaml/ocaml/blob/b1fdc44547dc20d891bd260b55740f37c57b4961/runtime/interp.c#L214
  # Description of opcodes: http://cadmium.x9c.fr/distrib/caml-instructions.pdf
  # Below we opportunistically match a BRANCH opcode with a 16-bit offset
  # (typically 0x2df), at the beginning of the CODE section.


def analyze_lua_luac(fread, info, fskip, format='lua-luac', fclass='code', ext='.luac',
                     spec=((0, '\x1bLua', 4, ('\x24', '\x25'), 5, '\2\4', 7, ('\4', '\x08'), 8, ('\x12\x34', '\x34\x12')),
                           (0, '\x1bLua', 4, ('\x31',), 5, ('l', 'f', 'd', '?'), 6, ('\4', '\x08')),
                           (0, '\x1bLua', 4, ('\x32',), 5, ('\0', '\4', '\x08')),
                           (0, '\x1bLua', 4, ('\x40',), 5, ('\0', '\1'), 6, ('\4', '\x08'), 7, ('\4', '\x08'), 8, ('\4', '\x08'), 9, ' \6\x09'),
                           (0, '\x1bLua', 4, ('\x50',), 5, ('\0', '\1'), 6, ('\4', '\x08'), 7, ('\4', '\x08'), 8, ('\4', '\x08'), 9, '\6\x08\x09\x09', 13, ('\4', '\x08')),
                           (0, '\x1bLua', 4, ('\x51',), 5, '\0', 6, ('\0', '\1'), 7, ('\4', '\x08'), 8, ('\4', '\x08'), 9, ('\4', '\x08'), 10, ('\4', '\x08'), 11, ('\0', '\1')),
                           (0, '\x1bLua', 4, ('\x52',), 5, '\0', 6, ('\0', '\1'), 7, ('\4', '\x08'), 8, ('\4', '\x08'), 9, ('\4', '\x08'), 10, ('\4', '\x08'), 11, ('\0', '\1'), 12, '\x19\x93\r\n\x1a\n'),
                           (0, '\x1bLua', 4, ('\x53',), 5, '\0', 6, '\x19\x93\r\n\x1a\n', 12, ('\4', '\x08'), 13, ('\4', '\x08'), 14, ('\4', '\x08'), 15, ('\4', '\x08'), 16, ('\4', '\x08'), 17, ('\0\0\x56\x78', '\x78\x56\0\0', '\0\0\0\0')),
                           (0, '\x1bLua', 4, ('\x54', '\x55', '\x56', '\x57', '\x58', '\x59'), 5, '\0'))):  # Prediction of future Lua bytecode versions.
  # http://files.catwell.info/misc/mirror/lua-5.2-bytecode-vm-dirk-laurie/lua52vm.html
  # Also in Lua sources: src/lundump.h and src/lundump.c in https://www.lua.org/ftp/
  header = match_spec(spec, fread, info, format)
  info['subformat'] = '%d.%d' % (ord(header[4]) >> 4, ord(header[4]) & 15)


def analyze_signify(fread, info, fskip, format='signify', fclass='crypto',
                    extra_formats=('signify-signature', 'signify-public-key', 'signify-private-key'),
                    spec=(0, 'untrusted comment: ')):
  # https://github.com/aperezdc/signify
  # minisign: https://jedisct1.github.io/minisign/
  signature = 'untrusted comment: '
  header = fread(len(signature))
  if len(header) < len(signature):
    raise ValueError('Too short for signify.')
  if not header.startswith(signature):
    raise ValueError('signify signature not found.')
  info['format'] = 'signify'
  data = fread(256 - len(header))
  while 1:
    i = data.find('\n')
    if i >= 0:
      break
    if len(data) >= 8192:
      raise ValueError('signify untrusted comment too long.')
    size = len(data)
    data += fread(len(data))
    if len(data) == size:
      raise ValueError('EOF in signify comment.')
  comment = data[:i]
  if comment.startswith('minisign '):
    info['subformat'] = 'minisign'
  if comment.startswith('signature from minisign '):
    info['format'], info['subformat'] = 'signify-signature', 'minisign'
  elif comment.startswith('minisign public key '):
    info['format'], info['subformat'] = 'signify-public-key', 'minisign'
  elif comment.endswith(' public key'):
    info['format'] = 'signify-public-key'
  elif comment.endswith(' secret key'):
    info['format'] = 'signify-private-key'
  elif comment.startswith('verify with '):
    info['format'] = 'signify-signature'
  elif comment.startswith('signature from '):
    info['format'] = 'signify-signature'


ODF_FORMAT_BY_MIMETYPE = {
    'application/vnd.oasis.opendocument.base': 'odf-odb',
    'application/vnd.oasis.opendocument.formula': 'odf-odf',
    'application/vnd.oasis.opendocument.graphics': 'odf-odg',
    'application/vnd.oasis.opendocument.presentation': 'odf-odp',
    'application/vnd.oasis.opendocument.spreadsheet': 'odf-ods',
    'application/vnd.oasis.opendocument.text': 'odf-odt',
    'application/vnd.oasis.opendocument.graphics-template': 'odf-otg',
    'application/vnd.oasis.opendocument.presentation-template': 'odf-otp',
    'application/vnd.oasis.opendocument.spreadsheet-template': 'odf-ots',
    'application/vnd.oasis.opendocument.text-template': 'odf-ott',
}


def analyze_zip(fread, info, fskip, format='zip', fclass='archive',
                extra_formats=('msoffice-zip', 'msoffice-docx', 'msoffice-xlsx', 'msoffice-pptx', 'odf-zip') + tuple(ODF_FORMAT_BY_MIMETYPE.itervalues()),
                spec=((0, 'PK', 2, ('\1\2', '\3\4', '\5\6', '\7\x08', '\6\6')),
                      (0, 'PK00PK', 6, ('\1\2', '\3\4', '\5\6', '\7\x08', '\6\6')))):
  # Also Java jar, Android apk, Python .zip, .docx, .xlsx, .pptx,  ODT, ODS, ODP.
  header = fread(4)
  if header == 'PK00':
    header = fread(4)
  if len(header) < 4:
    raise ValueError('Too short for zip.')
  # 'PK\6\6' is ZIP64.
  if header in ('PK\1\2', 'PK\5\6', 'PK\7\x08', 'PK\6\6'):
    info['format'] = 'zip'
    return
  elif header != 'PK\3\4':
    raise ValueError('zip signature not found.')
  info['format'] = 'zip'
  data = fread(26)  # Local file header.
  if len(data) < 26:
    return
  # crc32 is of the uncompressed, decrypted file. We ignore it.
  (version, flags, method, mtime_time, mtime_date, ignored_crc32, compressed_size,
   uncompressed_size, filename_size, extra_field_size,
  ) = struct.unpack('<HHHHHlLLHH', data)
  if method not in (0, 8):  # 0=uncompressed, 8=flate.
    return
  assert method in (0, 8), method  # See meanings in METHODS.
  if flags & 1:  # Encrypted file.
    return
  if flags & 8:  # Data descriptor comes after file contents.
    if method == 8:
      compressed_size = uncompressed_size = None
    elif method == 0:
      if uncompressed_size == 0:
        uncompressed_size = compressed_size
  # 8-bit name of the first archive member.
  filename = fread(filename_size)
  if len(filename) != filename_size or not fskip(extra_field_size):
    return
  if filename == '[Content_Types].xml':
    info['format'], max_size = 'msoffice-zip', 65536
  elif filename == 'mimetype':
    info['format'], max_size = 'odf-zip', 256  # OpenDocument Format.
  else:
    return

  if method:  # Usually compressed for msoffice-zip.
    try:
      import zlib
    except ImportError:
      return
    zd = zlib.decompressobj(-15)
    if compressed_size is None:
      data = fread(max_size)
    else:
      zd = zlib.decompressobj(-15)
      data = fread(min(compressed_size, max_size))
    try:
      data = zd.decompress(data)[:max_size]  # TODO(pts): Decompress in 256-byte chunks to prevent size blowup.
    except zlib.error:
      return
  else:  # Usuually uncompressed for odf-zip.
    data = fread(min(uncompressed_size, max_size))
  if info['format'] == 'msoffice-zip' and data.startswith('<?xml '):
    is_docx = ' PartName="/word/' in data
    is_xlsx = ' PartName="/xl/' in data
    is_pptx = ' PartName="/ppt/' in data
    if is_docx + is_xlsx + is_pptx == 1:
      if is_docx:
        info['format'] = 'msoffice-docx'
      elif is_xlsx:
        info['format'] = 'msoffice-xlsx'
      elif is_pptx:
        info['format'] = 'msoffice-pptx'
  elif info['format'] == 'odf-zip':
    format = ODF_FORMAT_BY_MIMETYPE.get(data)
    if format is not None:
      info['format'] = format


def count_is_troff(header):
  i = 0
  if header.startswith('.\\" ') or header.startswith('.\\"*'):
    i = header.find('\n') + 1
    if i <= 0:
      return 400
  cmd = header[i : i + 4]
  if cmd in ('.TH ', '.SH ', '.de ') and header[i + 4 : i + 5].isalpha():
    return (i + 4) * 100 + 24
  if cmd == '.EF ' and header[i + 4 : i + 5] == "'":
    return (i + 5) * 100
  if cmd in ('.\\" ', '.\\"*'):
    return (i + 4) * 100 - 13
  return 0


def count_is_info(header):
  # https://www.gnu.org/software/texinfo/manual/texinfo/html_node/Info-Format-Specification.html
  # https://www.gnu.org/software/texinfo/manual/texinfo/html_node/Info-Format-Preamble.html
  if not header.startswith('This is '):
    return 0
  i = header.find('\n')
  if not 0 <= i < 170:  # The number 170 is abitrary.
    return 0
  header = header[:i]
  # Even Texinfo generates this.
  i = header.find(', produced by ')
  if i < 0:
    return 0
  i += 14
  if i >= len(header):
    return 0
  if header[i : i + 17] == 'makeinfo version ' and header[i + 17 : i + 18].isdigit():
    return (i + 19) * 100 + 55
  else:
    return (i + 1) * 100  # +1: '\n'


def count_is_html(header):
  i = 0
  while i < len(header) and header[i].isspace():
    i += 1
  if header[i : i + 1] != '<':
    return False
  i += 1
  j = i
  while i < len(header) and not (header[i].isspace() or header[i] in '<>"\''):
    i += 1
  tag = header[j : i].lower()
  if not (i < len(header) and (header[i].isspace() or header[i] == '>')):
    return False
  while i < len(header) and header[i].isspace():
    i += 1
  if tag == '!doctype':
    j = i
    while i < len(header) and not (header[i].isspace() or header[i] in '<>"\''):
      i += 1
    arg = header[j : i].lower()
    if not (i < len(header) and (header[i].isspace() or header[i] == '>')):
      return False
    while i < len(header) and header[i].isspace():
      i += 1
    if arg == 'html':
      return i * 100
  elif tag in ('html', 'head', 'body'):
    return i * 100
  return False


def count_is_msoffice_owner(header):
  # File names starting with ~$ , they are called ``owner files'' in the Microsoft Office documentation.
  # https://support.microsoft.com/en-us/topic/description-of-how-word-creates-temporary-files-66b112fb-d2c0-8f40-a0be-70a367cc4c85
  # File format prefix is an educated guess based on samples.
  if len(header) < 54:
    return False
  name_size = ord(header[0])
  if not 1 <= name_size <= 53:
    return False
  c = 29  # Confidence.
  for i in xrange(1, name_size + 1):  # Username in 8-bit encoding.
    if ord(header[i]) < 32:
      return False
    c += 38
  b2 = ''
  for i in xrange(name_size + 1, 54):
    if b2:
      if header[i] != b2:
        return False
      c += 100
    else:
      b2 = header[i]
      if b2 not in ' \0':
        return False
      c += 78
  if len(header) >= 56:
    name_size2, = struct.unpack('<H', header[54 : 56])
    if name_size2 != name_size:
      if len(header) >= 57 and b2 == ' ' and header[54] == b2:
        name_size2, = struct.unpack('<H', header[55 : 57])
        if name_size2 != name_size:
          return False
        c += 100
      else:
        return False
    c += 200
  elif len(header) == 55:
    if ord(header[54]) != name_size:
      return False
    c += 100
  return c


def count_is_rds_ascii(header):
  if not (header.startswith('A\n2\n') or header.startswith('A\n3\n')):
    return False
  i, j, m, c = 4, 5, min(len(header) - 1, 14), 387 + 61 + 100
  if m < 4 or not header[4].isdigit() or header[4] == '0':
    return False
  while j < m and header[j].isdigit():
    j += 1
  if header[j] != '\n':
    return False
  r_version = int(header[i : j])
  if r_version >> 24:
    return False
  v1, v2, v3 = (r_version >> 16) & 255, (r_version >> 8) & 255, r_version & 255
  if not 1 <= v1 <= 6:  # Major R version (4 in 2021).
    return False
  if not (v2 <= 20 and v3 <= 20):
    return False
  return c


def count_is_hsqldb_log(header):
  if not header.startswith('/*'):
    return False
  if len(header) < 4 or header[3] == '0':
    return False
  i, c = 3, 300
  while i < len(header) and header[i].isdigit():
    i += 1
    c += 55
  # Usually: "*/SET SCHEMA PUBLIC\n" or "*/SET SCHEMA SYSTEM_LOBS\n".
  expected = '*/SET SCHEMA '
  if header[i : i + len(expected)] != expected:
    return False
  return c + 100 * len(expected)


def count_is_torrent(header):
  # https://en.wikipedia.org/wiki/Torrent_file
  # https://fileformats.fandom.com/wiki/Torrent_file
  if len(header) < 3 or header[0] != 'd' or header[1] not in '123456789':
    return False
  c = 161
  if header[2] == ':':
    c += 100
    i, size = 3, int(header[1])
  elif header[2].isdigit() and header[3 : 4] == ':':
    c += 159
    i, size = 4, int(header[1 : 3])
  if len(header) < i + size:
    return False
  # The most common (>=99.84%) key is 'announce'.
  if header[i : i + size] not in ('announce', 'created by', 'announce-list', 'comment', 'comment.utf-8', 'info', 'creation date', 'nodes', 'httpseeds'):
    return False
  return c + 100 * size


# ---


# TODO(pts): Move everything from here to def analyze_...(..., format=..., spec=...) or add_format(...).
# TODO(pts): Static analysis: autodetect conflicts and subsumes in string-only matchers.
# TODO(pts): Optimization: create prefix dict of 8 bytes as well.
FORMAT_ITEMS.extend((
    # (n, f, ...) means: read at most n bytes from the beginning of the file
    # to header, call f(header).
    ('empty', (1, lambda header: (len(header) == 0, MAX_CONFIDENCE))),
    ('short1', (2, lambda header: (len(header) == 1, MAX_CONFIDENCE))),
    ('short2', (3, lambda header: (len(header) == 2, MAX_CONFIDENCE))),
    ('short3', (4, lambda header: (len(header) == 3, MAX_CONFIDENCE))),

    # fclass='media': Media container (with audio and/or video).

    # .ifo and .bup files on a video DVD.
    # http://stnsoft.com/DVD/ifo.html
    ('dvd-video-video-ts-ifo', (0, 'DVDVIDEO-VMG\0')),
    ('dvd-video-vts-ifo', (0, 'DVDVIDEO-VTS\0')),
    # http://fileformats.archiveteam.org/wiki/RIFX
    # Big endian RIFF. Not in mainstream use, not analyzing further.
    ('rifx', (0, ('RIFX', 'XFIR'), 12, lambda header: (len(header) >= 12 and header[8 : 12].lower().strip().isalnum(), 100))),

    # fclass='video': Video (single elementary stream, no audio).
    #
    # TODO(pts): Add 'mpeg-pes', it starts with: '\0\0\1' + [\xc0-\xef\xbd]. mpeg-pes in mpeg-ts has more sids (e.g. 0xfd for AC3 audio).

    # fclass='image': Image. Can be animated.
    #
    # TODO(pts): Add detection and analyzing of OpenEXR, DNG, CR2.
    # XnView MP supports even more: https://www.xnview.com/en/xnviewmp/#formats
    # IrfanView also supports a lot: https://www.irfanview.com/main_formats.htm

    ('lepton', (0, '\xcf\x84', 2, ('\1', '\2'), 3, ('X', 'Y', 'Z'))),
    ('pnm', (0, 'P', 1, ('1', '2', '3', '4', '5', '6', '7'), 2, ('\t', '\n', '\x0b', '\x0c', '\r', ' ', '#'), 4, lambda header: (len(header) >= 3 and header[2] == '#' or header[3].isdigit(), 1))),
    # Detected as 'pnm'.
    ('xv-thumbnail',),
    # 408 is arbitrary, but since cups-raster has it, we can also that much.
    ('pam', (0, 'P7\n', 3, tuple('#\nABCDEFGHIJKLMNOPQRSTUVWXYZ'), 408, lambda header: adjust_confidence(400, count_is_pam(header)))),
    ('xbm', (0, '#define', 7, (' ', '\t'), 256, lambda header: adjust_confidence(800, count_is_xbm(header)))),  # '#define test_width 42'.
    ('xpm', (0, '#define', 7, (' ', '\t'), 256, lambda header: adjust_confidence(800, count_is_xpm1(header)))),  # '#define test_format 1'. XPM1.
    ('xpm', (0, '! XPM2', 6, ('\r', '\n'))),  # XPM2.
    ('xpm', (0, '/* XPM */', 9, ('\r', '\n'))),  # XPM3.
    ('deep', (0, 'FORM', 8, 'DEEPDGBL\0\0\0\x08')),
    ('djvu', (0, 'AT&TFORM', 12, 'DJV', 15, ('U', 'M'))),
    ('jbig2', (0, '\x97JB2\r\n\x1a\n')),
    # PDF-ready output of `jbig2 -p'.
    ('jbig2', (0, '\0\0\0\0\x30\0\1\0\0\0\x13', 19, '\0\0\0\0\0\0\0\0')),
    ('webp', (0, 'RIFF', 8, 'WEBPVP8', 15, (' ', 'L', 'X'), 30, lambda header: (is_webp(header), 400))),
    # Both the tagged (TIFF-based) and the coded (codestream, elementary
    # stream, bitstream) format are detected.
    ('jpegxr', (0, ('II\xbc\x01', 'WMPH'), 8, lambda header: adjust_confidence(400, count_is_jpegxr(header)))),
    ('flif', (0, 'FLIF', 4, ('\x31', '\x33', '\x34', '\x41', '\x43', '\x44', '\x51', '\x53', '\x54', '\x61', '\x63', '\x64'), 5, ('0', '1', '2'))),
    ('fuif', (0, ('FUIF', 'FUAF'), 4, ('\x31', '\x32', '\x33', '\x34', '\x35'), 5, tuple(chr(c) for c in xrange(0x26 + 1, 0x26 + 16)))),
    ('bpg', (0, 'BPG\xfb', 6, lambda header: (is_bpg(header), 30))),
    # By ImageMagick.
    ('miff', (0, 'id=ImageMagick')),
    # By GIMP.
    ('xcf', (0, 'gimp xcf ', 9, ('file', 'v001', 'v002', 'v003', 'v004', 'v005', 'v006', 'v007', 'v008', 'v009'))),
    # By Photoshop.
    ('psd', (0, '8BPS', 4, ('\0\1', '\0\2'), 6, '\0\0\0\0\0\0')),
    # By Paint Shop Pro.
    ('psp', (0, 'Paint Shop Pro Image File\n\x1a\0\0\0\0\0')),
    # Sun Raster.
    ('ras', (0, '\x59\xa6\x6a\x95', 24, lambda header: (len(header) < 24 or header[20 : 23] == '\0\0\0' and header[23] in ('\0', '\1', '\2', '\3', '\4', '\5'), 363 * (len(header) >= 24) or 1))),
    ('gem', (0, GEM_NOSIG_HEADERS)),
    ('gem', (0, GEM_HYPERPAINT_HEADERS, 16, '\0\x80')),
    ('gem', (0, GEM_STTT_HEADERS, 16, 'STTT\0\x10')),
    ('gem', (0, GEM_XIMG_HEADERS, 16, 'XIMG\0\0')),
    # By PCPaint >=2.0 and Pictor.
    ('pcpaint-pic', (0, '\x34\x12', 6, '\0\0\0\0', 11, tuple('\xff123'), 13, tuple('\0\1\2\3\4'))),
    ('fuji-raf', (0, 'FUJIFILMCCD-RAW 020', 19, ('0', '1'), 20, 'FF383501')),
    ('minolta-raw', (0, '\0MRM\0', 6, ('\0', '\1', '\2', '\3'), 8, '\0PRD\0\0\0\x18')),
    ('dpx', (0, 'SDPX\0\0', 8, 'V', 9, ('1', '2'), 10, '.', 11, tuple('0123456789'))),
    ('cineon', (0, '\x80\x2a\x5f\xd7\0\0')),  # .cin
    ('cineon', (0, '\xd7\x5f\x2a\x80', 6, '\0\0')),
    ('vicar', (0, 'LBLSIZE=', 8, tuple('123456789'), 9, tuple('0123456789'))),
    ('pds', (0, 'NJPL1I00PDS')),
    ('pds', (0, 'PDS_VERSION_ID', 14, WHITESPACE)),
    ('pds', (0, 'CCSD3ZF')),
    ('pds', (1, '\0NJPL1I00PDS')),
    ('pds', (1, '\0PDS_VERSION_ID', 16, WHITESPACE)),
    ('pds', (1, '\0CCSD3ZF')),
    # This is a very short header, it most probably conflicts with many others.
    ('ybm', (0, '!!')),
    ('fbm', (0, '%bitmap\0')),
    ('cmuwm', (0, ('\xf1\0\x40\xbb', '\xbb\x40\0\xf1'))),
    ('utah-rle', (0, '\x52\xcc',         10, tuple(chr(c) for c in xrange(16)), 11, tuple(chr(c) for c in xrange(1, 6)), 12, '\x08', 13, tuple(chr(c) for c in xrange(6)), 14, tuple(chr(c) for c in xrange(9)))),
    # Adding this with xpos=0 and ypos=0 for better header matching of the most common case.
    ('utah-rle', (0, '\x52\xcc\0\0\0\0', 10, tuple(chr(c) for c in xrange(16)), 11, tuple(chr(c) for c in xrange(1, 6)), 12, '\x08', 13, tuple(chr(c) for c in xrange(6)), 14, tuple(chr(c) for c in xrange(9)))),
    ('fif', (0, 'FIF\1')),
    ('spix', (0, 'spix', 24, lambda header: (is_spix(header), 812))),
    ('sgi-rgb', (0, '\x01\xda', 2, ('\0', '\1'), 3, ('\1', '\2'), 4, ('\0\1', '\0\2', '\0\3'), 12, lambda header: (len(header) >= 12 and (header[5] != '\3' or (header[10] == '\0' and 1 <= ord(header[11]) <= 5)), 10))),
    ('xv-pm', (0, 'VIEW\0\0\0', 7, ('\1', '\3', '\4'), 16, '\0\0\0\1\0\0\x80', 23, ('\1', '\4'))),
    ('xv-pm', (0, 'WEIV', 4, ('\1', '\3', '\4'), 5, '\0\0\0', 16, '\1\0\0\0', 20, ('\1', '\4'), 21, '\x80\0\0')),
    ('imlib-argb', (0, 'ARGB ', 5, tuple('123456789'), 32, lambda header: adjust_confidence(600, count_is_imlib_argb(header)))),
    ('imlib-eim', (0, 'EIM 1', 14, lambda header: adjust_confidence(500, count_is_imlib_eim(header)))),
    ('farbfeld', (0, 'farbfeld')),
    ('fpx',),  # From 'olecf'.
    # 408 is arbitrary, but since cups-raster has it, we can also that much.
    ('wbmp', (0, '\0', 1, ('\0', '\x80'), 408, lambda header: adjust_confidence(300, count_is_wbmp(header)))),
    ('gd', (0, '\xff', 1, ('\xfe', '\xff'), 7, lambda header: (len(header) >= 7 and header[2 : 4] != '\0\0' and header[4 : 6] != '\0\0' and ord(header[6]) == (header[1] == '\xfe'), 102))),
    ('gd2', (0, 'gd2\0\0', 5, ('\1', '\2'), 10, '\0', 11, ('\1', '\2', '\3', '\4'), 19, lambda header: (len(header) >= 19 and header[4 : 6] != '\0\0' and header[6 : 8] != '\0\0' and header[8 : 10] != '\0\0' and (header[5] == '\1' or ord(header[18]) == (header[13] in '\3\4')), 104))),
    ('cups-raster', (0, ('RaSt', 'tSaR', 'RaS2', '2SaR', 'RaS3', '3SaR'), 408, lambda header: adjust_confidence(400, count_is_cups_raster(header)))),
    # This is a very weak header without magic number, and the first 4 \s at
    # offset 4 isn't for sure either -- but we don't have anything better to
    # match on.
    ('alias-pix', (4, '\0\0\0\0\0', 9, ('\x08', '\x18'))),
    # http://fileformats.archiveteam.org/wiki/BRender_PIX
    ('brender-pix', (0, '\0\0\0\x12\0\0\0\x08\0\0\0\2\0\0\0\2')),
    ('photocd', (0, '\xff' * 32)),
    ('fits', (0, 'SIMPLE  = ', 80, lambda header: (len(header) >= 11 and header[10 : 80].split('/', 1)[0].strip(' ') == 'T', 180))),
    ('xloadimage-niff', (0, 'NIFF\0\0\0\1')),
    ('sun-taac', (0, 'ncaa', 4, tuple('\r\nabcdefghijklmnopqrstuvwxyz'), 5, tuple('\r\nabcdefghijklmnopqrstuvwxyz'))),
    ('facesaver', (0, tuple(sorted(set(prefix[:6] for prefix in FACESAVER_PREFIXES))), 6, lambda header: adjust_confidence(600, count_is_facesaver(header)))),
    ('mcidas-area', (0, ('\0\0\0\0\0\0\0\4', '\0\0\0\0\4\0\0\0'), 32, lambda header: adjust_confidence(800, count_is_mcidas_area(header)))),
    # Not all macpaint files match this, some of them start with '\0' * 512,
    # and they don't have any other header either, so no image data.
    ('macpaint', (0, '\0\0\0', 3, ('\2', '\3'), 4, ('\0\0\0\0\0\0\0\0', '\xff\xff\xff\xff\xff\xff\xff\xff'))),  # .mac. Also from 'macbinary'.
    ('fit', (0, 'IT0', 3, ('1', '2'), 12, '\0\0\0', 15, tuple(chr(c) for c in xrange(1, 33)))),
    ('icns', (0, 'icns', 8, lambda header: (len(header) >= 8 and (header[4 : 7] != '\0\0\0' or ord(header[7]) >= 32), 2))),
    ('dds', (0, 'DDS \x7c\0\0\0', 76, ' \0\0\0')),
    ('jpegxl', (0, ('\xff\x0a'))),
    ('jpegxl-brunsli', (0, '\x0a\x04B\xd2\xd5N')),
    ('pik', (0, ('P\xccK\x0a', '\xd7LM\x0a'))),
    ('qtif', (0, ('\0', '\1'), 4, ('idat', 'iicc'))),
    ('qtif', (0, '\0\0\0', 4, 'idsc')),
    # .mov preview image.
    ('pnot', (0, '\0\0\0\x14pnot', 12, '\0\0')),
    ('dcx', (0, '\xb1\x68\xde\x3a', 8, lambda header: (len(header) < 8 or header[5 : 8] != '\0\0\0' or ord(header[4]) >= 12, 2))),
    # Not all tga (targa) files have 'TRUEVISION-XFILE.\0' footer.
    ('tga', (0, ('\0',) + tuple(chr(c) for c in xrange(30, 64)), 1, ('\0', '\1'), 2, ('\1', '\2', '\3', '\x09', '\x0a', '\x0b', '\x20', '\x21'), 7, ('\0', '\x10', '\x18', '\x20'), 16, ('\1', '\2', '\4', '\x08', '\x0f', '\x10', '\x18', '\x20'))),
    # Corel Binary Material Format. Used by cliparts in Corel Gallery. The
    # file format is not public, no way to get width and height.
    # https://file-extension.net/seeker/seeker.py?filetype_AND=binary
    # http://review-tech.appspot.com/bmf-file.html
    # https://github.com/digipres/digipres.github.io/blob/master/_sources/registries/trid/triddefs_xml/bmf-corel.trid.xml
    ('corel-bmf', (0, '@CorelBMF\n\rCorel Corporation\n\r')),
    # http://fileformats.archiveteam.org/wiki/BMF_%28Dmitry_Shkarin%29
    # https://github.com/digipres/digipres.github.io/blob/master/_sources/registries/trid/triddefs_xml/bitmap-bmf-1x.trid.xml
    ('shkarin-bmf', (0, '\x81\x8a', 2, ('\x31', '\x32'), 10, '\0\0\0\0', 18, '\0\0')),
    ('g3-digifax', (1, 'PC Research, Inc')),
    # https://plan9.io/sources/plan9/sys/src/cmd/postscript/g3p9bit/g3p9bit.c
    ('g3-dumbpc', (0, 'II*')),

    # * It's not feasible to detect
    #   http://justsolve.archiveteam.org/wiki/DEGAS_image , the signature is
    #   too short (2 bytes).
    # * It's not possible to detect CCITT Fax Group 3 (G3), it doesn't have a
    #   header. http://fileformats.archiveteam.org/wiki/CCITT_Group_3
    # * It's not possible to detect CCITT Fax Group 4 (G4), it doesn't have a
    #   header. http://fileformats.archiveteam.org/wiki/CCITT_Group_4

    # fclass='audio'. Audio.

    ('aac', (0, 'ADIF')),
    ('flac', (0, 'fLaC')),
    ('ac3', (0, '\x0b\x77', 7, lambda header: (is_ac3(header), 20))),
    ('dts', (0, ('\x7f\xfe\x80\x01', '\xfe\x7f\x01\x80', '\x1f\xff\xe8\x00', '\xff\x1f\x00\xe8'), 6, lambda header: (is_dts(header), 1))),
    ('ape', (0, 'MAC ')),
    ('vorbis', (0, '\x01vorbis\0\0\0\0', 11, tuple(chr(c) for c in xrange(1, 16)))),
    ('oggpcm', (0, 'PCM     \0\0\0')),
    ('opus', (0, 'OpusHead', 8, tuple(chr(c) for c in xrange(1, 16)))),
    ('speex', (0, 'Speex   1.')),
    ('realaudio', (0, '.ra\xfd')),
    ('ralf', (0, 'LSD:', 4, ('\1', '\2', '\3'))),
    # http://midi.teragonaudio.com/tech/midifile/mthd.htm
    ('midi', (0, 'MThd\0\0\0\6\0\0\0\1')),  # This assumes that for Format=0, it is always Tracks=2. But there are some counterexamples.
    ('midi', (0, 'MThd\0\0\0\6\0', 9, ('\0', '\1', '\2'), 10, ('\0', '\1', '\2', '\3'))),
    # http://web.archive.org/web/20110610135604/http://www.midi.org/about-midi/rp29spec(rmid).pdf
    ('midi-rmid', (0, 'RIFF', 8, 'RMIDdata', 20, 'MThd\0\0\0\6\0', 29, ('\0', '\1', '\2'))),  # .rmi
    ('aiff', (0, 'FORM', 8, 'AIFFCOMM\0\0\0\x12')),
    ('aifc', (0, 'FORM', 8, 'AIFC', 12, ('FVER', 'COMM'), 16, '\0\0\0')),
    # https://github.com/schismtracker/schismtracker/wiki/ITTECH.TXT
    # .mod and .s3m don't have a magic number (they start with an arbitrary song name >= 16 bytes).
    ('impulsetracker', (0, 'IMPM')),  # .it
    ('au', (0, '.snd\0\0\0', 12, '\0\0\0', 15, tuple(chr(c) for c in AU_CODECS), 20, '\0\0\0', 23, tuple(chr(c) for c in xrange(1, 16)))),

    # fclass='doc': Document media and vector graphics.

    ('pdf', (0, '%PDF-1.')),
    ('ps', (0, '%!PS-Adobe-', 11, ('1', '2', '3'), 12, '.')),
    ('ps', (0, '%!PS', 4, ('\n', '\r'), 5, '%%BoundingBox: ')),
    ('ps', (0, '%!PS\r\n%%BoundingBox: ')),
    ('ps', (0, '\xc5\xd0\xd3\xc6', 5, '\0\0\0', 8, lambda header: (ord(header[4]) >= 30, 2))),
    ('pict', (2, '\0\0\0\0', 16, lambda header: adjust_confidence(0, count_is_pict_at_512(header)))),  # Also from 'macbinary'. Also from '?-zeros32' and '?-zeros64' if it has the 512-byte to be ignored at the beginning.
    ('pict', (16, lambda header: adjust_confidence(0, count_is_pict_at_512(header)))),  # Much less confidence.
    # http://fileformats.archiveteam.org/wiki/CGM
    # https://books.google.ch/books?id=O0KeBQAAQBAJ
    # TODO(pts): Page 161, Chapter 10. The Character Encoding ``This chapter develops the techical details of CGM Part 2, the Character Encoding.''
    # Software: http://www.agocg.ac.uk/train/cgm/ralcgm.htm
    # Sample with character encoding: https://github.com/CliffsDover/graphicsmagick/blob/master/ralcgm/examples/ca.cgm
    # Sample with character encoding: https://github.com/CliffsDover/graphicsmagick/blob/master/ralcgm/examples/cells.cgm
    ('cgm', (0, ('B', 'b'), 1, ('E', 'e'), 2, ('G', 'g'), 3, ('M', 'm'), 4, ('F', 'f'), 5, (' ', '\"', "'", '\n', '\r'))),  # Clear-text encoding of 'BEGMF '.
    ('cgm', (0, '\0\x3f\0')),  # Binary encoding with parameter length >= 31. Doesn't detect shorter lengths.
    ('cgm', (0, '0 ~>~')),  # Character encoding.
    ('cgm', (0, '0 \x1b\x5c\1b')),  # Character encoding with some binary.
    ('svg', (0, '<svg', 4, XML_WHITESPACE_TAGEND)),
    ('svg', (0, '<svg:svg', 8, XML_WHITESPACE_TAGEND)),
    ('smil', (0, '<smil', 5, XML_WHITESPACE_TAGEND)),
    # https://fossies.org/linux/xfig/doc/FORMAT3.2
    # TODO(pts): For width= and height=, get paper size from line 5 in version 3.2 only.
    ('fig', (0, '#FIG ', 5, ('1', '2', '3'), 6, '.')),
    # http://fileformats.archiveteam.org/wiki/Xar_(vector_graphics)
    # http://site.xara.com/support/docs/webformat/spec/XARFormatDocument.pdf
    ('xara', (0, 'XARA\xa3\xa3\r\n\2\0\0\0', 13, ('\0', '\1', '\2', '\3'), 14, '\0\0', 16, ('CXW', 'CXN'), 23, '\0\0\0\0')),
    # http://fileformats.archiveteam.org/wiki/CorelDRAW
    # https://github.com/LibreOffice/libcdr/blob/04b3c20882653adf4727a4dcf18fa1b577c0f20e/src/lib/CDRParser.cpp#L228
    ('cdr-old', (0, 'WLm\0')),
    # http://fileformats.archiveteam.org/wiki/CorelDRAW
    # https://www.ntfs.com/corel-draw-format.htm
    ('cdr', (0, 'RIFF', 8, ('CDR', 'cdr'), 11, tuple('456789ABCD'), 12, 'vrsn', 17, '\0\0\0')),
    # http://fileformats.archiveteam.org/wiki/SHW_(Corel)
    ('corelshow', (0, 'RIFF', 8, 'shv4LIST')),
    ('rtf', (0, '{\\rtf1', 32, lambda header: adjust_confidence(600, count_is_rtf(header)))),
    # http://fileformats.archiveteam.org/wiki/Microsoft_Write
    # https://web.archive.org/web/20130831064118/http://msxnet.org/word2rtf/formats/write.txt
    ('wri', (0, ('\x31\xbe\0\0', '\x32\xbe\0\0'), 4, '\0\xab\0\0\0\0\0\0\0')),
    # https://perldoc.perl.org/perlpod.html
    ('perl-pod', (0, '=pod', 4, (' ', '\n'))),
    ('perl-pod', (0, ('=head1 ', '=begin '))),
    # 408 is arbitrary, but since cups-raster has it, we can also that much.
    ('troff', (0, ('.TH ', '.SH ' , '.\\\" ', '.\\\"*', '.de ', '.EF '), 408, lambda header: adjust_confidence(400, count_is_troff(header)))),
    # TODO(pts): Also match whitespace and (short) comments in the beginning. Most .tex documents have it.
    ('latex', (0, '\\documentclass', 14, lambda header: (len(header) <= 14 or not header[14].isalpha(), 6))),
    # Older than 'latex', now obsolete.
    ('latex-209', (0, '\\documentstyle', 14, lambda header: (len(header) <= 14 or not header[14].isalpha(), 6))),
    # http://fileformats.archiveteam.org/wiki/Texinfo
    # https://www.gnu.org/software/texinfo/
    # TODO(pts): Add @node and section with args.
    # TODO(pts): Ignore a few \n in the beginning.
    ('texinfo', (0, '\\input texinfo', 14, ('\r', '\n', ' ', '\t'))),
    ('texinfo', (0, '@ignore', 7, ('\r', '\n', ' ', '\t'))),
    ('texinfo', (0, '@comment', 8, ('\r', '\n', ' ', '\t'))),
    ('texinfo', (0, '@ifnottex', 9, ('\r', '\n', ' ', '\t'))),
    # https://www.texmacs.org/tmweb/manual/webman-format.en.html
    # https://www.texmacs.org/Download/ftp/tmftp/source/TeXmacs-1.99.12-src.tar.gz
    # Old versions also have the 'edit' prefix, but we don't match on it, it's too generic.
    ('texmacs', (0, '<TeXmacs|', 9, ('1', '2', '3'), 10, '0')),
    ('texmacs', (0, '(document (TeXmacs')),
    ('texmacs', (0, 'TeXmacs')),
    ('texmacs', (0, '\\(\\)(TeXmacs')),
    # https://wiki.tcl-lang.org/page/tbcload
    # https://github.com/corbamico/tbcload/blob/master/parser.go
    # https://github.com/ActiveState/teapot/blob/master/lib/tbcload/tests/tbc10/catch.tbc
    ('tclpro-bytecode', (0, 'TclPro ByteCode ')),
    # https://wiki.tcl-lang.org/page/getbytecode
    # https://github.com/SAOImageDS9/SAOImageDS9/blob/39579a905d2396471f23b49d6a6b8f110df7e290/tcl8.6/generic/tclDisassemble.c#L1229
    ('tcl-bytecode', (0, 'literals {')),
    # https://ftp.lip6.fr/pub/lyx/stable/2.3.x/lyx-2.3.4.3.tar.xz
    # 408 is arbitrary, but since cups-raster has it, we can also that much.
    ('lyx', (0, '#LyX ', 408, lambda header: (header[header.find('\n') + 1:].startswith('\\lyxformat '), 1100))),
    ('info', (0, 'This is ', 170, lambda header: adjust_confidence(800, count_is_info(header)))),
    # http://fileformats.archiveteam.org/wiki/HLP_(WinHelp)
    # http://www.oocities.org/mwinterhoff/helpfile.htm
    ('winhelp', (0, '\x3f\x5f\3\0', 6, '\0\0', 12, lambda header: (True, 400 * (len(header) >= 12 and header[8 : 12] == '\xff\xff\xff\xff') or 1))),
    # http://fileformats.archiveteam.org/wiki/CHM
    # http://www.russotto.net/chm/itolitlsformat.html
    ('chm', (0, 'ITSF\3\0\0\0', 9, '\0\0\0\1\0\0\0', 22, '\0\0\x10\xfd\x01\x7c\xaa\x7b\xd0\x11\x9e\x0c\x00\xa0\xc9\x22\xe6\xec\x11\xfd\x01\x7c\xaa\x7b\xd0\x11\x9e\x0c\x00\xa0\xc9\x22\xe6\xec')),
    # http://fileformats.archiveteam.org/wiki/Microsoft_Help_2
    # http://www.russotto.net/chm/itolitlsformat.html
    # TODO(pts): Also add .mshc (.zip-based). https://fileinfo.com/extension/mshc
    # ---
    # https://www.opendesign.com/files/guestdownloads/OpenDesign_Specification_for_.dwg_files.pdf
    ('autodesk-dwg', (0, 'AC10', 4, ('12', '14', '15', '18', '21', '24', '27', '32'), 6, '\0\0\0\0\0', 12, '\1')),

    # fclass='archive': Compressed archive.

    ('rar', (0, 'Rar!')),
    ('zpaq', (0, ('7kS', 'zPQ'), 4, lambda header: (header.startswith('7kSt') or (header.startswith('zPQ') and 1 <= ord(header[3]) <= 127), 52))),
    ('7z', (0, '7z\xbc\xaf\x27\x1c')),
    # http://fileformats.archiveteam.org/wiki/Zoo
    # https://www.fileformat.info/format/zoo/corion.htm
    ('zoo', (0, 'ZOO ', 4, ('1', '2'), 5, '.', 6, tuple('0123456789'), 7, tuple('0123456789'), 8, ' Archive.\x1a\0\0\xdc\xa7\xc4\xfd')),
    # http://fileformats.archiveteam.org/wiki/UltraCompressor_II
    ('uc2', (0, 'UC2\x1a')),
    # http://fileformats.archiveteam.org/wiki/ARJ
    # https://github.com/tripsin/unarj/blob/master/TECHNOTE.TXT
    # https://github.com/joncampbell123/arj/blob/master/defines.h
    ('arj', (0, '\x60\xea', 5, tuple(chr(c) for c in xrange(1, 16)), 6, tuple(chr(c) for c in xrange(1, 16)), 7, tuple(chr(c) for c in xrange(16)), 9, ('\0', '\1', '\2', '\3', '\4'), 10, ('\0', '\1', '\2', '\3', '\4'))),
    # http://fileformats.archiveteam.org/wiki/LHA
    # https://web.archive.org/web/20021005080911/http://www.osirusoft.com/joejared/lzhformat.html
    ('lha', (2, ('-lh0-', '-lzs-', '-lh1-', '-lh2-', '-lh3-', '-lh4-', '-lh5-', '-lh6-', '-lh7-', '-lh8-', '-lh9-', '-lhd-', '-lha-', '-lhb-', '-lhc-', '-lhe-', '-lhx-', '-pc1-', '-pm0-', '-pm1-', '-pm2-', '-pms-', '-lz2-', '-lz3-', '-lz4-', '-lz5-', '-lz7-', '-lz8-'), 20, ('\0', '\1', '\2'))),
    # https://github.com/NeighTools/ARCX/wiki/ARCX-format
    ('arcx', (0, 'ARCX')),
    # http://fileformats.archiveteam.org/wiki/ACE
    # https://raw.githubusercontent.com/droe/acefile/master/acefile.py
    ('ace', (4, '\0', 7, '**ACE**')),
    # http://fileformats.archiveteam.org/wiki/Deb
    # Also udeb.
    ('deb', (0, '!<arch>\ndebian-binary ')),
    # http://fileformats.archiveteam.org/wiki/RPM
    ('rpm', (0, '\xed\xab\xee\xdb')),
    # http://fileformats.archiveteam.org/wiki/AR
    # Also used for Linux .a files (containing ELF .o files) and archives
    # containing Go object files.
    ('ar', (0, '!<arch>\n')),
    # http://fileformats.archiveteam.org/wiki/Cpio
    # https://www.systutorials.com/docs/linux/man/5-cpio/
    ('cpio', (0, ('070707', '070701', '070702'))),
    ('cpio', (0, ('\x71\xc7', '\xc7\x71'))),
    # http://fileformats.archiveteam.org/wiki/Cabinet
    ('cab', (0, 'MSCF\0\0\0\0')),
    # https://doomwiki.org/wiki/WAD#Compression
    ('wad', (0, ('IWAD', 'PWAD'))),
    # http://fileformats.archiveteam.org/wiki/AIN
    # JUP.DAT in JUP at https://weynans.lima-city.de/tools-en.htm
    ('ain', (0, '!', 1, ('\x11', '\x12'), 2, '\0\0\0\0\0\0')),
    # http://fileformats.archiveteam.org/wiki/StuffIt
    # `apt-get install unar' can extract it ('SIT!') on Linux.
    # format=macbinary can also detect it.
    ('stuffit', (0, 'SIT!', 10, 'rLau')),
    ('stuffit', (0, 'StuffIt (c)1997')),
    # http://fileformats.archiveteam.org/wiki/StuffIt_X#Identification
    ('stuffitx', (0, 'StuffIt', 7, ('!', '?'))),

    # fclass='compress': Compressed single file.

    ('gz', (0, '\x1f\x8b\x08')),  # .gz
    # http://fileformats.archiveteam.org/wiki/MSZIP
    ('mszip', (0, 'CK')),
    # http://fileformats.archiveteam.org/wiki/Bzip
    ('bzip', (0, 'BZ0')),
    ('bz2', (0, 'BZh')),  # .bz2; bzip2
    # http://fileformats.archiveteam.org/wiki/Lzip
    # Uses LZMA.
    ('lzip', (0, 'LZIP')),
    # http://fileformats.archiveteam.org/wiki/Rzip
    ('rzip', (0, 'RZIP')),
    # http://fileformats.archiveteam.org/wiki/Lrzip
    ('lrzip', (0, 'LRZI')),
    # http://fileformats.archiveteam.org/wiki/LZX
    ('lzx', (0, 'LZX')),
    # http://fileformats.archiveteam.org/wiki/Lzop
    ('lzop', (0, '\x89LZO\0\r\n\x1a\x0a')),
    ('lzma', (0, '\x5d\0\0', 12, ('\0', '\xff'))),
    ('flate', (0, '\x78', 1, ('\x01', '\x5e', '\x9c', '\xda'))),
    ('flate', (0, ('\x08', '\x18', '\x28', '\x38', '\x48', '\x58', '\x68'), 1, ('\x01', '\x5e', '\x9c', '\xda'))),  # Flate width small window.
    # http://fileformats.archiveteam.org/wiki/Compress_(Unix)
    ('compress', (0, '\x1f\x9d')),  # .Z
    # http://fileformats.archiveteam.org/wiki/Compact_(Unix)
    ('compact', (0, ('\x1f\xff', '\xff\x1f'))),  # .C
    # http://fileformats.archiveteam.org/wiki/Pack_(Unix)
    ('pack', (0, '\x1f\x1e')),  # .z
    # http://fileformats.archiveteam.org/wiki/Freeze/Melt
    ('freeze', (0, ('\x1f\x9e', '\x1f\x9f'))),  # .F
    # http://fileformats.archiveteam.org/wiki/Crunch
    ('crunch', (0, '\x76\xfe')),
    # http://fileformats.archiveteam.org/wiki/Squeeze
    ('squeeze', (0, '\x76\xff')),
    # http://fileformats.archiveteam.org/wiki/CrLZH
    ('crlzh', (0, '\x76\xfd')),
    # http://fileformats.archiveteam.org/wiki/SCO_compress_LZH
    ('sco-lzh', (0, '\x1f\xa0')),
    # http://fileformats.archiveteam.org/wiki/Zstandard
    ('zstd', (0, ('\x25\xb5\x2f\xfd', '\x28\xb5\x2f\xfd'))),
    # http://fileformats.archiveteam.org/wiki/Zstandard_dictionary
    ('zstd-dict', (0, '\x37\xa4\x30\xec')),
    # http://fileformats.archiveteam.org/wiki/LZ4
    ('lz4', (0, '\x04\x22\x4d\x18')),
    ('lz4-legacy', (0, '\x04\x22\x4d\x18')),
    # http://fileformats.archiveteam.org/wiki/Mozilla_LZ4
    ('mozlz4', (0, 'mozLz40\0')),
    # https://github.com/google/brotli/issues/298
    # https://github.com/madler/brotli/blob/master/br-format-v3.txt
    ('brotli', (0, '\xce\xb2\xcf\x81')),  # .br
    # http://fileformats.archiveteam.org/wiki/MS-DOS_installation_compression
    ('msdos-compress-szdd-qbasic', (0, 'SZ \x88\xF0\x27\x33\xd1')),
    ('msdos-compress-szdd', (0, 'SZDD\x88\xF0\x27\x33')),
    ('msdos-compress-kwaj', (0, 'KWAJ\x88\xF0\x27\xD1')),
    # http://fileformats.archiveteam.org/wiki/Squash_(RISC_OS)
    ('squash', (0, 'SQSH')),
    # http://fileformats.archiveteam.org/wiki/DIET_(compression)
    ('diet', (0, '\xb4\x4c\xcd\x21\x9d\x89\x64\x6c\x7a')),
    # https://github.com/pts/upxbc/blob/0c5c63aef8c5c3336945a92a3829078d64dfdee2/upxbc#L1239
    ('upxz', (0, 'UPXZ')),

    # fclass='code': Code: source code, machine code or bytecode.

    # .o object files created by Go.
    # See printObjHeader in go/src/cmd/compile/internal/gc/obj.go
    # TODO(pts): Read XCOFF in go/src/cmd/link/internal/ld/lib.go
    # NOTE: There are *three* independent implementations of this object file format in the Go source tree:
    #       cmd/internal/goobj/read.go (used by cmd/addr2line, cmd/nm, cmd/objdump, cmd/pprof)
    #       cmd/internal/obj/objfile.go (used by cmd/asm and cmd/compile)
    #       cmd/link/internal/objfile.go (used by cmd/link)
    # The Plan 9 version of the assembler
    # (https://github.com/0intro/plan9/blob/master/sys/src/cmd/8a/lex.c)
    # doesn't seem to print any specific header in the assemble(...)
    # function. The corresponding lex.c in Go prints "go object ".
    ('go-object', (0, 'go object ')),
    # This header seems to come right after 'go object ...\n!\n', so it
    # isn't at the beginning of the file.
    # .o object files created by newer (1.14) Go.
    # See Magic in in go/src/cmd/internal/goobj/objfile.go
    # See Magic in in go/src/cmd/internal/goobj2/objfile.go
    # See WriteObjFile in go/src/cmd/internal/obj/objfile.go
    # See startmagic in go/src/cmd/link/internal/objfile/objfile.go
    # In Go 1.10 go/src/cmd/internal/obj/read.go also has it.
    # ('go-object', (0, ('\x00\x00go13ld', '\x00\x00go17ld', '\x00\x00go19ld', '\x00go112ld', '\x00go114ld', '\x00go114LD'))),
    # Doing the major_version >= 30 check to distinguish from format=macho subformat=universal.
    ('java-class', (0, '\xca\xfe\xba\xbe', 6, '\0', 8, lambda header: (len(header) >= 8 and ord(header[7]) >= 30, 1))),
    # http://fileformats.archiveteam.org/wiki/BEAM
    ('erlang-beam', (0, 'FOR1', 8, 'BEAM')),
    ('erlang-beam', (0, '\x7fBEAM!')),
    # http://docs.parrot.org/parrot/devel/html/docs/parrotbyte.pod.html
    ('parrot-pbc', (0, '\xfePBC\r\n\x1a\n')),
    # https://ruby-doc.org/core-2.6/RubyVM/InstructionSequence.html
    ('ruby-yarv', (0, 'YARB', 4, ('\1', '\2', '\3', '\4'), 5, '\0\0\0')),  # RubyVM::InstructionSequence.compile('p 6 * 7').to_binary[0, 100]; '\2' is the Ruby major version number (2.x).
    ('ruby-yarv', (0, '["YARVInstructionSequence/SimpleDataFormat", ', 45, ('1', '2', '3', '4'))),  # RubyVM::InstructionSequence.compile('p 6 * 7').to_a.inspect
    ('ruby-yarv', (0, '"\4\x08[\x13\"-YARVInstructionSequence/SimpleDataFormati', 48, ('\6', '\7', '\x08', '\x09'))),  # Marshal::dump(RubyVM::InstructionSequence.compile('p 6 * 7').to_a)
    # https://github.com/micropython/micropython/blob/5716c5cf65e9b2cb46c2906f40302401bdd27517/tools/mpy-tool.py
    ('micropython-mpy', (0, 'M', 1, ('\0', '\1', '\2', '\3'), 2, ('\0', '\1', '\2', '\3'), 3, ('\x1e', '\x1f', '\x2f', '\x3e', '\x3f'))),
    ('micropython-mpy', (0, 'M', 1, tuple(chr(c) for c in xrange(4, 30)), 2, tuple(chr(c) for c in xrange(128)), 3, ('\x1e', '\x1f', '\x2f', '\x3e', '\x3f'), 4, ' ')),
    # This covers Emacs >=19.34b (1996-09-06) and XEmacs >= 21.1.6 (1999-05-12).
    ('emacs-elc', (0, ';ELC', 4, ('\x12', '\x13', '\x14', '\x17'), 5, '\0\0\0\n')),
    # https://lwn.net/Articles/707619/
    # https://dancol.org/pdumperpres.pdf
    # https://github.com/emacs-mirror/emacs/blob/188bd80a903d34ef6a85b09e99890433e7adceb7/src/pdumper.c#L136-L140
    # FYI The `(dump-emacs ...)' call crates a native executable, no magic number to detect.
    ('emacs-pdump', (0, 'DUMPEDGNUEMACS\0\0')),
    # https://github.com/file/file/blob/79f3070d4ea165196fa072281f6a2c2c3d19f756/magic/Magdir/lisp#L64-L65
    ('clisp-bytecode', (0, '(SYSTEM::VERSION ')),
    ('clisp-bytecode', (0, '(|SYSTEM|::|VERSION| ')),
    # https://source.android.com/devices/tech/dalvik/dex-format
    # Version 039 is used in Android 9--11.
    ('dalvik-dex', (0, 'dex\n0', 5, ('45', '44', '43', '42', '41', '40', '39', '38', '37', '35', '13', '09'), 7, '\0')),  # classes.dex.
    # Opportunistic, there can be comments etc., not everything is a
    # function.
    ('common-lisp', (0, '(defun ')),
    # Opportunistic, there can be comments etc., not everything is a
    # function. Also matches PreScheme (bytecode?) by Scheme 48.
    ('scheme', (0, '(define (')),
    # http://pascal.hansotten.com/ucsd-p-system/ucsd-files/
    # The UCSD Pascal P-code codefile file format is hard to detect, so we
    # don't do it. header[64 : 72] == ' ' can be useful, see pcode_*.cod for
    # examples. See also ucsd-psystem-xc-0.13/lib/codefile/file/i_5.{h,cc}
    # for the description of the segment header in the first 512 bytes
    # (block0).
    ('ucsd-pcode',),
    # https://github.com/graphitemaster/gmqcc/blob/94c2936bfad224529cf326d539a5cdac0a286183/code.cpp#L309-L313
    ('quakec-lnof', (0, 'LNOF\1\0\0\0')),
    # Ethereum EVM bytecode doesn't contain a header.
    # https://ethervm.io/
    # https://patrickventuzelo.com/wp-content/uploads/2018/11/devcon4_reversing_ethereum_smart_contract_full.pdf
    ('ethereum-evm', (0, '\x60\x80\x60\x40\x52\x34\x80\x15\x61')),  # Loader bytecode compiled by Solidity.
    ('ethereum-evm', (0, '\x60\x80\x60\x40\x52\x60\x04\x36\x10\x60', 11, '\x57\x60\x00\x35')),  # Runtime bytecode compiled by Solidity, PUSH1 before JUMPI.
    ('ethereum-evm', (0, '\x60\x80\x60\x40\x52\x60\x04\x36\x10\x61', 12, '\x57\x60\x00\x35')),  # Runtime bytecode compiled by Solidity.
    ('ethereum-evm', (0, '\x60\x80\x60\x40\x52\x60\x04\x36\x10\x62', 13, '\x57\x60\x00\x35')),  # Runtime bytecode compiled by Solidity, PUSH3 before JUMPI.
    ('ethereum-evm', (0, '\x60\x04\x36\x10\x15\x60\x0c\x57\x60', 10, '\x56\x5b\x60\x00\x35')),  # Runtime bytecode compiled by Vyper (also contains regular bytecode compiled by Viper), PUSH1 before JUMPI.
    ('ethereum-evm', (0, '\x60\x04\x36\x10\x15\x61\x00\x0d\x57\x61', 12, '\x56\x5b\x60\x00\x35')),  # Runtime bytecode compiled by Vyper (also contains regular bytecode compiled by Viper).
    ('ethereum-evm', (0, '\x60\x04\x36\x10\x15\x61\x00\x0d\x57\x62', 13, '\x56\x5b\x60\x00\x35')),  # Runtime bytecode compiled by Vyper (also contains regular bytecode compiled by Viper), PUSH2 before JUMPI, then PUSH3.
    ('ethereum-evm', (0, '\x60\x04\x36\x10\x15\x62\x00\x00\x0d\x57\x62', 14, '\x56\x5b\x60\x00\x35')),  # Runtime bytecode compiled by Vyper (also contains regular bytecode compiled by Viper), PUSH3 before JUMPI.
    ('ethereum-bzzhash', (0, '\x62\x7a\x7a\x72\x30\x58\x20')), # bzzhash (Swarm Hash) compiled by Solidity.
    # https://en.wikipedia.org/wiki/Solidity
    # TODO(pts): Add comments etc.
    ('solidity', (0, 'pragma solidity ')),
    ('solidity', (0, 'contract ')),
    # https://nekovm.org/
    # https://github.com/HaxeFoundation/neko/blob/1df580cb95e6f93d71d553391a92eda2fab283dd/src/neko/Bytecode.nml#L275
    # Languages which target this bytecode: Neko, NekoML, Haxe.
    ('nekovm-bytecode', (0, 'NEKO', 7, '\0', 11, '\0')),
    # https://en.wikipedia.org/wiki/SCUMM
    # https://github.com/AlbanBedel/scummc/wiki/Scumm-6-data-format
    # http://www.jestarjokin.net/apps/scummbler/
    # XOR encryption with 0, 0x69 or 0xff.
    ('scumm-bytecode', (0, 'LECF', 8, 'LOFF')),
    ('scumm-bytecode', (0, '%,*/', 8, '%&//')),  # Based on Day of the Tentacle (xor 0x69).
    ('scumm-bytecode', (0, '\xb3\xba\xbc\xb9', 8, '\xb3\xb0\xb9\xb9')),
    ('scumm-index', (0, 'RNAM\0\0\0\x09\x00MAXS')),
    ('scumm-index', (0, ';\'($iii`i$(1:')),  # Based on Day of the Tentacle (xor 0x69). Maybe size of RNAM is not always the same (9).
    ('scumm-index', (0, '\xad\xb1\xbe\xb2\xff\xff\xff\xf6\xff\xb2\xbe\xa7\xac')),
    # https://en.wikipedia.org/wiki/Scratch_(programming_language)#File_formats
    ('scratch', (0, ('ScratchV01', 'ScratchV02'))),
    ('unixscript', (0, '#!', 4, lambda header: (header.startswith('#!/') or header.startswith('#! /'), 110))),
    # Windows .cmd or DOS .bat file. Not all such file have a signature though.
    ('windows-cmd', (0, '@', 1, ('e', 'E'), 11, lambda header: (header[:11].lower() == '@echo off\r\n', 900))),
    # https://wiki.syslinux.org/wiki/index.php?title=Doc/comboot#COM32R_file_format
    ('com32r', (0, '\xb8\xfeL\xcd!')),  # .c32
    # https://github.com/pts/pts-xcom
    ('xcom', (0, "&XPZ,2P_0E[0E_,pP[,Eu\r\nR^!5+1+1CC+1)5GGHu#PWtl6~!ugH\"!rE\"!~~0B(m\"!4r!!Y~!)E~\"0~~Cump!!|d\r\n~E)!~~0B(m\"!pq!\"G0!!oD!\"B~\"v_Q\"! PSW\r\n")),
    # http://nozdr.ru/marinais/
    # Krasilnikov 1993.
    ('com4mail', (0, 'BEGIN===tfud#of_Com4Mail_file#\r\n')),
    # https://llvm.org/docs/BitCodeFormat.html#bitstream-format
    # TODO(pts): For the ASCII (.ll) format: https://subscription.packtpub.com/book/application_development/9781785285981/1/ch01lvl1sec13/converting-ir-to-llvm-bitcode
    ('llvm-bitcode', (0, '\xde\xc0\x17\x0b\0\0\0\0')),
    ('llvm-bitcode', (0, 'BC\xc0\xde')),  # Usually continues with '\x21\0c\00' -- is it a function?
    # https://en.wikipedia.org/wiki/Netwide_Assembler#RDOFF
    ('rdoff', (0, 'RDOFF', 5, ('1', '2'))),

    # fclass='other': Non-code, non-compressed, non-media.

    ('appledouble', (0, '\0\5\x16\7\0', 6, lambda header: (header[5] <= '\3', 25))),
    ('dsstore', (0, '\0\0\0\1Bud1\0')),  # https://en.wikipedia.org/wiki/.DS_Store
    ('php', (0, '<?', 2, ('p', 'P'), 6, WHITESPACE, 7, lambda header: (header[:5].lower() == '<?php', 200))),
    # We could be more strict here, e.g. rejecting non-HTML docypes.
    # 408 is arbitrary, but since cups-raster has it, we can also that much.
    ('html', (0, '<', 408, lambda header: adjust_confidence(100, count_is_html(header)))),
    ('html', (0, WHITESPACE, 408, lambda header: adjust_confidence(12, count_is_html(header)))),
    # Some yamls files omit this header (e.g. Google App Engine app.yaml),
    # they can't be detected.
    ('yaml', (0, ('---\n', '---\r', '--- '))),
    # https://toml.io/en/v1.0.0
    # No signature.
    ('toml',),
    # Contains thumbnails of multiple images files.
    # http://fileformats.archiveteam.org/wiki/PaintShop_Pro_Browser_Cache
    # pspbrwse.jbf
    # https://github.com/0x09/jbfinspect/blob/master/jbfinspect.c
    ('jbf', (0, 'JASC BROWS FILE\0')),
    # `nasm -f rdf' output.
    # OLE compound file == composite document file, including Thumbs.db and
    # Microsoft Office 97--2003 documents (.doc, .xls, .ppt).
    ('olecf', (0, ('\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1', '\x0e\x11\xfc\x0d\xd0\xcf\x11\x0e'))),
    ('avidemux-mpeg-index', (0, 'ADMY')),
    ('avidemux-project', (0, '//AD')),
    # *** These modified files were found in JOE when it aborted on ...
    # *** JOE was aborted by UNIX signal ...
    # *** Modified files in JOE when it aborted on
    ('deadjoe', (0, '\n*** ', 5, ('These modified', 'JOE was aborte', 'Modified files'))),
    # Filename extension: .mfo
    # Example: output of pymediafileinfo and media_scan.py.
    ('mediafileinfo', (0, 'format=')),
    ('cue', (0, 'REM GENRE ')),
    ('cue', (0, 'REM DATE ')),
    ('cue', (0, 'REM DISCID ')),
    ('cue', (0, 'REM COMMENT ')),
    ('cue', (0, 'PERFORMER ')),
    ('cue', (0, 'TITLE ')),
    ('cue', (0, 'FILE ')),
    ('cue', (0, '\xef\xbb\xbfREM GENRE ')),
    ('cue', (0, '\xef\xbb\xbfREM DATE ')),
    ('cue', (0, '\xef\xbb\xbfREM DISCID ')),
    ('cue', (0, '\xef\xbb\xbfREM COMMENT ')),
    ('cue', (0, '\xef\xbb\xbfPERFORMER ')),
    ('cue', (0, '\xef\xbb\xbfTITLE ')),
    ('cue', (0, '\xef\xbb\xbfFILE ')),
    ('utf8', (0, '\xef\xbb\xbf')),  # BOM.
    ('utf16', (0, ('\xff\xfe', '\xfe\xff'))),  # BOM.
    # http://fileformats.archiveteam.org/wiki/PostScript_Printer_Description
    ('ppd', (0, '*PPD-Adobe: "')),  # Normal recommended header.
    ('ppd', (0, '*PPD-Adobe:  "')),  # Windows 95 has some with double spaces.
    ('ppd', (0, '*Product: "')),  # Windows 95 installer has many of these.
    # http://justsolve.archiveteam.org/wiki/ICC_profile
    # http://www.color.org/specification/ICC.2-2019.pdf
    # http://www.color.org/registry/signature/TagRegistry-2019-10.pdf
    ('icm', (
        0, '\0', 1, tuple(chr(c) for c in xrange(32)),  #  At most 2 MiB.
        # CMM type. Superset of CMM signatures in: http://www.color.org/registry/signature/TagRegistry-2019-10.pdf
        # Plus extra observed in the wild: ('\0\0\0\0', 'Lino', 'MSFT', 'SCRS', 'scrs').
        4, ('\0\0\0\0', 'Lino', 'MSFT', 'SCRS', 'scrs', 'ADBE', 'ACMS', 'appl', 'CCMS', 'UCCM', 'UCMS', 'EFI ', 'FF  ', 'EXAC', 'HCMM', 'argl', 'LgoS', 'HDM ', 'lcms', 'RIMX', 'KCMS', 'MCML', 'WCS ', 'SIGN', 'ONYX', 'RGMS', 'SICC', 'TCMM', '32BT', 'vivo', 'WTG ', 'zc00'),
        8, ('\1', '\2', '\3', '\4', '\5', '\6', '\7'),  # Profile version.
        12, ('scnr', 'mntr', 'prtr', 'link', 'spac', 'abst', 'nmcl', 'cenc', 'mid ', 'mlnk', 'mvis'),
        16, ('\0\0\0\0', 'XYZ ', 'Lab ', 'Luv ', 'YCbr', 'Yxy ', 'LMS ', 'RGB ', 'GRAY', 'HSV ', 'HLS ', 'CMYK', 'CMY ', '2CLR', '3CLR', '4CLR', '5CLR', '6CLR', '7CLR', '8CLR', '9CLR', 'ACLR', 'BCLR', 'CCLR', 'DCLR', 'ECLR', 'FCLR'),
        20, ('\0\0\0\0', 'XYZ ', 'Lab '),
        36, 'acsp',
        40, ('\0\0\0\0', 'APPL', 'MSFT', 'SGI ', 'SUNW', '*nix'),
        # 270 possible manufacturer values: http://www.color.org/signatureRegistry/index.xalter
        #48, ('\0\0\0\0', 'ADBE', 'CANO', 'EPSO', 'HP  ', 'IBM ', 'IEC ', 'KODA', 'QMS ', 'TEKT', 'argl', 'none'),
    )),
    # https://specifications.freedesktop.org/desktop-entry-spec/desktop-entry-spec-latest.html
    ('desktop', (0, '[Desktop Entry]', 15, ('\r', '\n'))),
    ('desktop', (0, '[KDE Desktop Entry]', 19, ('\r', '\n'))),
    # Microsoft Windows shortcut.
    # https://ithreats.files.wordpress.com/2009/05/lnk_the_windows_shortcut_file_format.pdf
    # file-5.30/magic/Magdir/windows
    ('lnk', (0, '\114\0\0\0\001\024\002\0\0\0\0\0\300\0\0\0\0\0\0\106')),
    # Microsoft Windows program information file.
    # https://smsoft.ru/en/pifdoc.htm
    # file-5.30/magic/Magdir/msdos
    ('pif', (0, '\0', 30, '  ', 0x171, 'MICROSOFT PIFEX\0\x87\1\0\0')),
    # Microsoft Windows internet shortcut.
    # http://www.lyberty.com/encyc/articles/tech/dot_url_format_-_an_unofficial_guide.html
    # https://stackoverflow.com/q/13088263
    ('url', (0, '[InternetShortcut]', 18, ('\r', '\n'))),
    ('msoffice-owner', (0, tuple(chr(c) for c in xrange(1, 54)), 57, lambda header: adjust_confidence(29, count_is_msoffice_owner(header)))),
    # https://hwiegman.home.xs4all.nl/desktopini.html
    ('desktopini', (0, '[.ShellClassInfo]', 17, ('\r', '\n'))),
    ('desktopini', (0, '[LocalizedFileNames]', 20, ('\r', '\n'))),
    ('desktopini', (0, '[ViewState]', 11, ('\r', '\n'))),
    ('desktopini', (0, '\r\n[.ShellClassInfo]', 19, ('\r', '\n'))),
    ('desktopini', (0, '\r\n[LocalizedFileNames]', 22, ('\r', '\n'))),
    ('desktopini', (0, '\xff\xfe\x0d\0\x0a\0[\0.\0S\0h\0e\0l\0l\0C\0l\0a\0s\0s\0I\0n\0f\0o\0]\0', 40, ('\r', '\n'))),
    ('desktopini', (0, '\xff\xfe\x0d\0\x0a\0[\0L\0o\0c\0a\0l\0i\0z\0e\0d\0F\0i\0l\0e\0N\0a\0m\0e\0s\0]\0', 46, ('\r', '\n'))),
    ('vcalendar-ics', (0, 'BEGIN:VCALENDAR', 15, ('\r', '\n'))),
    ('vcard-vcf', (0, 'BEGIN:VCARD', 11, ('\r', '\n'))),
    ('m3u-extended', (0, '#EXTM3U', 7, ('\r', '\n'))),
    ('torrent', (0, 'd', 1, ('1', '2', '3', '4', '5', '6', '7', '8', '9'), 22, lambda header: adjust_confidence(161, count_is_torrent(header)))),
    ('vobsub-idx', (0, '# VobSub index file, v')),
    # TODO(pts): Allow a leading '\n' or '\r\n'. Detect more files.
    # TODO(pts): Allow UTF-8 and UTF-16LE and UTF-16BE BOM.
    ('srt', (0, ('0', '1'), 1, '\r\n00:', 6, tuple('0123456789'), 7, tuple('0123456789'), 8, ':')),  # Subtitle.
    ('srt', (0, ('0', '1'), 1, '\n00:', 5, tuple('0123456789'), 6, tuple('0123456789'), 7, ':')),  # Subtitle.

    # fclass='database': Database.

    # https://stackoverflow.com/a/69722897
    ('sqlite2', (0, '** This file contains an SQLite 2.', 34, ('0', '1'), 35, ' database **\0', 48, ('\xda\xe3\x75\x28', '\x28\x75\xe3\xda'))),
    # https://www.sqlite.org/fileformat.html#the_database_header
    # https://stackoverflow.com/a/69722897
    ('sqlite3', (0, 'SQLite format 3\0', 16, ('\0\1', '\2\0', '\4\0', '\x08\0', '\x10\0', '\x20\0', '\x40\0', '\x80\0'), 18, ('\1', '\2', '\3', '\4'), 19, ('\1', '\2', '\3', '\4'))),
    # DBNAME-journal file.
    # https://www.sqlite.org/fileformat.html#the_rollback_journal
    # Many times the header (first 8 bytes) is overwritten with \0s.
    ('sqlite3-journal', (0, '\xd9\xd5\x05\xf9\x20\xa1\x63\xd7')),
    # https://www.sqlite.org/fileformat.html#the_write_ahead_log
    ('sqlite3-wal', (0, '\x37\x7f\x06', 3, ('\x82', '\x83'), 4, '\x00\x2d\xe2\x18', 8, ('\0\0\2\0', '\0\0\4\0', '\0\0\x08\0', '\0\0\x10\0', '\0\0\x20\0', '\0\0\x40\0', '\0\0\x80\0', '\0\1\0\0'))),
    # https://www.sqlite.org/walformat.html#walidxfmt
    ('sqlite3-shm', (0, '\x00\x2d\xe2\x18\0\0\0\0', 12, '\0\0\0\1')),  # Big endian.
    ('sqlite3-shm', (0, '\x18\xe2\x2d\x00\0\0\0\0', 12, '\1\0\0\0')),  # Little endian.
    # Microsoft Access database file before Access 2007.
    # http://jabakobob.net/mdb/first-page.html
    ('msoffice-mdb', (0, '\0\1\0\x00Standard Jet DB\0', 22, '\0\0')),
    # Microsoft Access database file since Access 2007.
    # http://jabakobob.net/mdb/first-page.html
    ('msoffice-accdb', (0, '\0\1\0\x00Standard ACE DB\0', 22, '\0\0')),
    # CDB database files don't have any header.
    # https://cr.yp.to/cdb/cdb.txt
    ('djb-cdb',),
    # https://github.com/LMDB/lmdb/blob/4b6154340c27d03592b8824646a3bc4eb7ab61f5/libraries/liblmdb/mdb.c#L634
    # https://blog.separateconcerns.com/2016-04-03-lmdb-format.html
    ('lmdb-data', (0, ('\0\0\0\0\0\0\0\x08\0\0\0\0\xbe\xef\xc0\xde\0\0\0\1', '\0\0\0\0\0\0\x08\0\0\0\0\0\xde\xc0\xef\xbe\1\0\0\0'))),
    ('lmdb-lock', (0, ('\xbe\xef\xc0\xde', '\xde\xc0\xef\xbe'), 8, lambda header: (len(header) >= 8 and ((header[0] == '\xbe' and header[7] in '\1\2\3\4') or (header[0] == '\xde' and header[4] in '\1\2\3\4')), 75))),
    # https://github.com/erthink/libmdbx
    ('mdbx-data', (0, '\0\0\0\0\0\0\0\0\0\0' '\x08\0' '\0\0\0\0\0\0\0\0', 20, ('\1', '\2', '\3', '\4', '\5', '\6'), 21, '\x11\x4c\xef\xbd\x9d\x65\x59')),  # Little endian.
    ('mdbx-data', (0, '\0\0\0\0\0\0\0\0\0\0' '\0\x08' '\0\0\0\0\0\0\0\0' '\x59\x65\x9d\xbd\xef\x4c\x11', 27, ('\1', '\2', '\3', '\4', '\5', '\6'))),  # Big endian.
    ('mdbx-lock', (0, ('\1', '\2', '\3', '\4', '\5', '\6'), 1, '\x11\x4c\xef\xbd\x9d\x65\x59')),  # The lock file is empty if not in use.
    ('mdbx-lock', (0,'\x59\x65\x9d\xbd\xef\x4c\x11', 7, ('\1', '\2', '\3', '\4', '\5', '\6'))),
    # DuckDB also supports it, but may not be its native format: https://duckdb.org/docs/data/parquet
    # https://github.com/apache/parquet-format
    # https://github.com/apache/parquet-format/blob/master/src/main/thrift/parquet.thrift
    # TODO(pts): Parse the first few fields in Thrift format, just to understand.
    # TODO(pts): Add detection of the Apache Arrow file format.
    ('parquet', (0, 'PAR1')),
    # https://www.loc.gov/preservation/digital/formats/fdd/fdd000470.shtml
    # https://github.com/vnmabus/rdata/tree/develop/rdata/tests/data
    # http://yetanothermathprogrammingconsultant.blogspot.com/2016/02/r-rdata-file-format.html
    # This can read only binary: https://github.com/vnmabus/rdata
    # TODO(pts): Also detect format=rdata if it's gzip-compressed, sometimes bzip2- or xz-compressed.
    ('rdata', (0, ('RDX2\nX\n', 'RDX3\nX\n', 'RDA2\nA\n', 'RDA2\nB\n', 'RDX2\nB\n'))),
    # R languge, writeRDS.
    # Sample file: https://www.dropbox.com/s/e1tb76d57oqc79g/data_corpus_foreignaffairscommittee.rds?dl=1&v=1
    # Sample file: https://www.dropbox.com/s/7mu92jzodpq11zc/data_corpus_guardian.rds?dl=1&v=1
    # TODO(pts): Also detect format=rds if it's gzip-compressed, sometimes bzip2- or xz-compressed.
    ('rds', (0, 'X\n\0\0\0', 5, ('\2', '\3'), 6, '\0', 7, ('\1', '\2', '\3', '\4', '\5', '\6'))),
    ('rds', (0, 'A\n', 2, ('2', '3'), 3, '\n', 14, lambda header: adjust_confidence(387, count_is_rds_ascii(header)))),
    # https://support.hdfgroup.org/release4/doc/DS.pdf
    ('hdf4', (0, '\x0e\x03\x13\x01', 10, '\0\x1e\0\1')),
    ('hdf4', (0, '\x0e\x03\x13\x01')),
    # https://support.hdfgroup.org/HDF5/doc/H5.format.html#Superblock
    ('hdf5', (0, '\x89HDF\r\n\x1a\n', 8, ('\0', '\1', '2'))),
    # There is no signature in SDBM pag and dir files.
    # See ext/SDBM_File/sdbm/sdbm.{c,h} in perl-5.10.1.tar.gz
    ('sdbm-pag',),
    ('sdbm-dir',),
    # Probably there is no signature in DBM files (by Ken Thompson in 1978 and 1979).
    # Source code and documentation are not available.
    ('dbm',),
    # http://fileformats.archiveteam.org/wiki/TDB_(Samba)
    # struct tdb_header in common/tdb_private.h in https://www.samba.org/ftp/tdb/tdb-1.4.5.tar.gz
    # The version (header[32 : 36]) is (0x26011967 + 6) between tdb-1.1.3 and tdb-1.4.5.
    ('samba-tdb', (0, 'TDB file\n\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0', 36, lambda header: (len(header) >= 36 and (header[32 : 35] == '\x26\x01\x19' or header[33 : 36] == '\x19\x01\x26'), 300))),
    # samba-ntdb is not in active use by Samba, it was a proposal in 2013.
    # struct ntdb_header in struct ntdb_header in https://www.samba.org/ftp/tdb/ntdb-1.0.tar.gz
    # The version (header[64 : 72]) is (0x26011967 + 7) in ntdb-1.0.
    ('samba-ntdb', (0, 'NTDB file\n\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0', 72, lambda header: (len(header) >= 72 and (header[64 : 71] == '\0\0\0\0\x26\x01\x19' or header[65 : 72] == '\x19\x01\x26\0\0\0\0'), 300))),
    # https://fallabs.com/qdbm/
    # Search for magic in: https://fallabs.com/qdbm/spex.html
    # https://fallabs.com/qdbm/qdbm-1.8.78.tar.gz
    # Library version (header[12: 14]) is 14 in qdbm-1.8.78.
    ('qdbm', (0, ('[DEPOT]\n\f\0\0\0', '[depot]\n\f\0\0\0'), 12, ('1\0\0\0', '2\0\0\0', '3\0\0\0', '4\0\0\0', '5\0\0\0', '6\0\0\0', '7\0\0\0', '8\0\0\0', '9\0\0\0', '10\0\0', '11\0\0', '12\0\0', '13\0\0', '14\0\0'))),
    # Same as Apache Arrow Feather V1.
    # https://github.com/wesm/feather/blob/master/doc/FORMAT.md
    ('arrow-feather', (0, 'FEA1')),
    # Same as Apache Arrow Feather V2.
    # https://arrow.apache.org/docs/format/Columnar.html#ipc-file-format
    ('arrow-ipc', (0, 'ARROW1\0\0')),
    # ndbm and GDBM use the same format.
    ('ndbm', (0, ('\x13\x57\x9a\xcd', '\x13\x57\x9a\xce', '\x13\x57\x9a\xcf', '\xcd\x9a\x57\x13', '\xce\x9a\x57\x13', '\xcf\x9a\x57\x13'))),
    # https://www.gnu.org.ua/software/gdbm/manual/Numsync.html
    ('gdbm-numsync', (0, ('\x13\x57\x9a\xd0', '\x13\x57\x9a\xd1', '\xd0\x9a\x57\x13', '\xd1\x9a\x57\x13'))),
    # Created by `gdbm_dump --format=ascii'.
    ('gdbm-export-ascii', (0, '# GDBM dump file created by ')),
    # Created by `gdbm_dump --format=binary'.
    ('gdbm-export-binary', (0, '!\r\n! GDBM FLAT FILE DUMP -- THIS IS NOT A TEXT FILE\r\n! ')),
    # docs/programmer_reference/magic.txt in https://github.com/berkeleydb/libdb/releases/download/v5.3.28/db-5.3.28.tar.gz
    ('berkeleydb', (0, ('\x00\x06\x15\x61', '\x61\x15\x06\x00'), 4, '\0\0\0', 7, ('\1', '\2', '\3', '\4', '\5', '\6', '\7', '\x08', '\x09'), 8, ('\0\0\x10\xe1', '\0\0\x04\xd2'))),
    ('berkeleydb', (0, ('\x00\x05\x31\x62', '\x62\x31\x05\x00'), 4, ('\0\0\0\1', '\0\0\0\2', '\0\0\0\3', '\0\0\0\4', '\0\0\0\5', '\0\0\0\6', '\0\0\0\7', '\0\0\0\x08', '\0\0\0\x09', '\1\0\0\0', '\2\0\0\0', '\3\0\0\0', '\4\0\0\0', '\5\0\0\0', '\6\0\0\0', '\7\0\0\0', '\x08\0\0\0', '\x09\0\0\0'))),
    # TODO(pts): Maybe values other than 0 and 1 are also valid in the first 12 bytes if Berkeley DB >=2.
    ('berkeleydb', (0, '\0\0\0\0\0\0\0\0\0\0\0\1', 12, ('\x00\x04\x09\x88', '\x00\x05\x31\x62', '\x00\x06\x15\x61', '\x00\x07\x45\x82', '\x00\x04\x22\x53'), 16, '\0\0\0')),
    ('berkeleydb', (0, '\0\0\0\0\1\0\0\0\0\0\0\0', 12, ('\x88\x09\x04\x00', '\x62\x31\x05\x00', '\x61\x15\x06\x00', '\x82\x45\x07\x00', '\x53\x22\x04\x00'), 17, '\0\0\0')),
    # Created by `db_dump'.
    # https://github.com/berkeleydb/libdb/releases/download/v5.3.28/db-5.3.28.tar.gz
    ('berkeleydb-export', (0, 'VERSION=', 8, ('2', '3', '4', '5'), 9, '\n')),
    ('berkeleydb-export', (0, 'format=print\n')),  # Version 1.
    ('berkeleydb-export', (0, 'format=bytevalue\n')),  # Version 1.
    # http://fallabs.com/tokyocabinet/spex-en.html
    ('tokyocabinet', (0, 'ToKyO CaBiNeT\n', 24, '\0\0\0\0\0\0\0\0', 32, ('\0', '\1', '\2', '\3'))),
    # https://dbmx.net/kyotocabinet/spex.html
    # kchashdb.h in https://dbmx.net/kyotocabinet/pkg/kyotocabinet-1.2.79.tar.gz
    # Record count (offset 32) file size (offset 40) are 64-bit big endian.
    ('kyotocabinet', (0, 'KC\n\0', 4, tuple(chr(c) for c in xrange(1, 20)), 5, tuple(chr(c) for c in xrange(1, 20)), 6, tuple(chr(c) for c in xrange(1, 10)), 8, ('\x30', '\x31', '\x40', '\x41'), 32, '\0\0', 40, '\0\0')),
    # https://github.com/wiredtiger/wiredtiger
    ('wiredtiger-block', (0, '\x41\xd8\x01\x00\1\0', 7, '\0', 12, '\0\0\0\0')),
    ('wiredtiger-log', (0, '\x64\x10\x10\x00', 5, '\0\0\0', 14, '\0\0')),
    # https://dbmx.net/tkrzw/
    # https://dbmx.net/tkrzw/pkg/tkrzw-1.0.18.tar.gz
    ('tkrzw-tree', (0, 'TDB\0', 4, ('\0', '\1', '\2', '\3'), 34, ('\0', '\1'), 40, ('\0', '\1'))),
    ('tkrzw-hash', (0, 'TkrzwHDB\n', 10, ('\1', '\2', '\3', '\4'), 16, '\0\0\0', 24, '\0\0', 32, '\0\0', 40, '\0\0')),
    ('tkrzw-skip', (0, 'TkrzwSDB\n', 10, ('\1', '\2', '\3', '\4'), 24, '\0\0', 32, '\0\0', 40, '\0\0')),
    ('tkrzw-queue', (0, 'TkrzwMQX\n')),
    # http://hsqldb.org/download/hsqldb_251_jdk6/
    # http://hsqldb.org/download/hsqldb_251_jdk6/hsqldb-2.3.8-jdk6-sources.jar
    # http://hsqldb.org/download/hsqldb_251_jdk6/hsqldb-2.3.8-jdk6.jar
    # http://hsqldb.org/download/hsqldb_251_jdk6/sqltool-2.3.8-jdk6.jar
    # *.lck file.
    ('hsqldb-lck', (0, 'HSQLLOCK')),
    # *.script file.
    # getPropertiesSQL in org/hsqldb/persist/Logger.java
    # TODO(pts): Sometimes it's gzip-compressed (.gz) text file.
    # There also used to be a a binary format, but not anymore in hsqldb-2.3.8.
    ('hsqldb-script', (0, 'SET DATABASE UNIQUE NAME ')),
    # *.properties file.
    ('hsqldb-properties', (0, '#HSQL Database Engine ')),
    # *.data file containing the cache after a `SHUTDOWN;' statement. It
    # It doesn't have a signature, typically it starts with ~16 \0 bytes.
    ('hsqldb-data',),
    # *.log file.
    # Sometimes the file is empty.
    ('hsqldb-log', (0, '/*C', 64, lambda header: adjust_confidence(300, count_is_hsqldb_log(header)))),
    # It doesn't have a signature. Sumetimes it's gzip-compressed (.gz).
    ('hsqldb-backup',),
    # It doesn't have a signature.
    ('hsqldb-lobs',),

    # fclass='crypto': Cryptography: encrypted files, keys, keychains.

    # https://tools.ietf.org/html/draft-ietf-openpgp-rfc4880bis-09#section-5.3
    # (0,' \x8c') is generated by gpg(1).
    # (1, ...) includes no session key, and session key with keytable size any of 16, 24 and 32.
    ('gpg-symmetric-encrypted', (0, ('\x8c', '\xc3'), 1, ('\x04', '\x15', '\x1d', '\x25'), 2, '\x04', 3, GPG_CIPHER_ALGOS, 4, '\0', 5, GPG_DIGEST_ALGOS)),
    ('gpg-symmetric-encrypted', (0, ('\x8c', '\xc3'), 1, ('\x0c', '\x1d', '\x25', '\x2d'), 2, '\x04', 3, GPG_CIPHER_ALGOS, 4, '\1', 5, GPG_DIGEST_ALGOS)),
    ('gpg-symmetric-encrypted', (0, ('\x8c', '\xc3'), 1, ('\x0d', '\x1e', '\x26', '\x2e'), 2, '\x04', 3, GPG_CIPHER_ALGOS, 4, '\3', 5, GPG_DIGEST_ALGOS)),
    ('gpg-symmetric-encrypted', (0, ('\x8c', '\xc3'), 2, '\5', 3, ('\1', '\2', '\3', '\4', '\7', '\x08', '\x09', '\x0a'), 4, ('\1', '\2'), 5, ('\0', '\1', '\3'))),
    ('gpg-pubkey-encrypted', (0, '\x85', 3, '\3', 12, GPG_PUBKEY_ENCRYPTED_ALGOS)),
    ('gpg-pubkey-encrypted', (0, '\x84', 2, '\3', 11, GPG_PUBKEY_ENCRYPTED_ALGOS)),
    ('gpg-pubkey-encrypted', (0, '\xc1', 2, lambda header: (len(header) >= 2 and ord(header[1]) < 192, 1), 2, '\3', 11, GPG_PUBKEY_ENCRYPTED_ALGOS)),
    ('gpg-pubkey-encrypted', (0, '\xc1', 2, lambda header: (len(header) >= 2 and 192 <= ord(header[1]) < 224, 1), 3, '\3', 12, GPG_PUBKEY_ENCRYPTED_ALGOS)),
    # https://tools.ietf.org/html/draft-ietf-openpgp-rfc4880bis-09#section-5.4
    ('gpg-signed', (0, ('\x90', '\xc4'), 1, '\x0d\3', 3, ('\0', '\1'), 4, GPG_DIGEST_ALGOS, 5, GPG_PUBKEY_SIGNED_ALGOS)),  # gpg --sign --compress-algo none  # TODO(pts); codec=uncompressed
    # Typically it is also signed, but the outer layer is compressed, so that's what we detect.
    ('gpg-compressed', (0, '\xa3\1', 3, lambda header: (len(header) >= 3 and (ord(header[2]) & 6) != 6, 5))),  # gpg --sign --compress-algo zip  # TODO(pts): codec=flate
    ('gpg-compressed', (0, '\xa3\2\x78', 3, ('\x01', '\x5e', '\x9c', '\xda'))),  # gpg --sign --compress-algo zlib  # TODO(pts): codec=flate
    ('gpg-compressed', (0, '\xa3\x03BZh')),  # gpg --sign --compress-algo bzip2  # TODO(pts): codec=bz2
    ('gpg-ascii', (0, '-----BEGIN PGP MESSAGE-----', 27, ('\r', '\n'))),  # Can be gpg-symmetric-encrypted, gpgp-pubkey-encrypted, gpg-signed, gpg-compressed.
    # Multiple keys: e.g. output of `gpg --export-secret-keys'.
    # Also multiple keys (GPG 1.x): ~/.gnupg/secring.gpg
    ('gpg-private-keys', (0, '\x94', 2, '\3', 9, GPG_PUBKEY_KEY_ALGOS)),
    ('gpg-private-keys', (0, '\x94', 2, ('\4', '\5'), 7, GPG_PUBKEY_KEY_ALGOS)),
    ('gpg-private-keys', (0, '\x95', 1, GPG_KEY_BYTE_SHR8_SIZES, 3, '\3', 10, GPG_PUBKEY_KEY_ALGOS)),
    ('gpg-private-keys', (0, '\x95', 1, GPG_KEY_BYTE_SHR8_SIZES, 3, ('\4', '\5'), 8, GPG_PUBKEY_KEY_ALGOS)),
    ('gpg-private-keys', (0, '-----BEGIN PGP PRIVATE KEY BLOCK-----', 37, ('\r', '\n'))),
    # Multiple keys: e.g. output of `gpg --export'.
    # Also multiple keys (GPG 1.x and 2.x): ~/.gnupg/pubring.gpg
    ('gpg-public-keys', (0, '\x98', 2, '\3', 9, GPG_PUBKEY_KEY_ALGOS)),
    ('gpg-public-keys', (0, '\x98', 2, ('\4', '\5'), 7, GPG_PUBKEY_KEY_ALGOS)),
    ('gpg-public-keys', (0, '\x99', 1, GPG_KEY_BYTE_SHR8_SIZES, 3, '\3', 10, GPG_PUBKEY_KEY_ALGOS)),
    ('gpg-public-keys', (0, '\x99', 1, GPG_KEY_BYTE_SHR8_SIZES, 3, ('\4', '\5'), 8, GPG_PUBKEY_KEY_ALGOS)),
    ('gpg-public-keys', (0, '-----BEGIN PGP PUBLIC KEY BLOCK-----', 36, ('\r', '\n'))),
    # https://wiki.openssl.org/index.php/Enc
    # This detects `openssl enc -... -salt' and `openssl enc -... -pbkdf2',
    # but it doesn't detect `openssl enc -... -nosalt', because that one
    # doesn't have a signature.
    ('openssl-symmetric-encrypted', (0, 'Salted__')),
    # https://age-encryption.org/v1
    # https://github.com/FiloSottile/age
    # https://github.com/FiloSottile/age/blob/f0f8092d60bb96737fa096c29ec6d8adb5810390/internal/format/format.go#L46
    # Private key signature: 'AGE-SECRET-KEY-', but it may contain comment
    # lines starting with '#' first.
    ('age-encrypted', (0, 'age-encryption.org/v1\n')),
    # https://saltpack.org/
    ('saltpack-binary', (0, '\xc4', 2, tuple('\x94\x95\x96\x97\x98\x99'), 3, '\xa8saltpack\x92', 13, ('\1', '\2', '\3', '\4'), 14, tuple('\0\1\2\3\4\5\6\7'))),
    ('saltpack-binary', (0, '\xc5', 3, tuple('\x94\x95\x96\x97\x98\x99'), 4, '\xa8saltpack\x92', 14, ('\1', '\2', '\3', '\4'), 16, tuple('\0\1\2\3\4\5\6\7'))),
    ('saltpack-binary', (0, '\xc7', 5, tuple('\x94\x95\x96\x97\x98\x99'), 6, '\xa8saltpack\x92', 16, ('\1', '\2', '\3', '\4'), 18, tuple('\0\1\2\3\4\5\6\7'))),
    ('saltpack-ascii', (0, 'BEGIN KEYBASE SALTPACK MESSAGE.')),
    ('saltpack-ascii', (0, 'BEGIN KEYBASE SALTPACK ENCRYPTED MESSAGE.')),
    ('saltpack-ascii', (0, 'BEGIN KEYBASE SALTPACK DETACHED SIGNATURE.')),
    ('saltpack-ascii', (0, 'BEGIN KEYBASE SALTPACK SIGNED MESSAGE.')),
    ('saltpack-ascii', (0, 'BEGIN SALTPACK MESSAGE.')),
    ('saltpack-ascii', (0, 'BEGIN SALTPACK ENCRYPTED MESSAGE.')),
    ('saltpack-ascii', (0, 'BEGIN SALTPACK DETACHED SIGNATURE.')),
    ('saltpack-ascii', (0, 'BEGIN SALTPACK SIGNED MESSAGE.')),
    # Example: ~/.ssh/id_*.pub , ~/.ssh/authorized_keys
    ('ssh-public-keys', (0, 'ssh-rsa ')),
    ('ssh-public-keys', (0, 'ssh-dss ')),
    ('ssh-public-keys', (0, 'ssh-ed25519 ')),
    ('ssh-public-keys', (0, 'ecdsa-sha2-nistp256 ')),
    ('ssh-public-keys', (0, 'ecdsa-sha2-nistp384 ')),
    ('ssh-public-keys', (0, 'ecdsa-sha2-nistp521 ')),
    ('ssh-public-keys', (0, 'sk-ssh-ed25519@openssh.com ')),
    ('ssh-public-keys', (0, 'sk-ecdsa-sha2-nistp256@openssh.com ')),
    ('ssh-public-keys', (0, 'sk-ecdsa-sha2-nistp384@openssh.com ')),
    ('ssh-public-keys', (0, 'sk-ecdsa-sha2-nistp521@openssh.com ')),
    # smime.p7s file attachments.
    ('pkcs7-signature', (0, '\x30\x80\x06\x09\x2a\x86\x48\x86\xf7\x0d\x01\x07\x02')),

    # fclass='font'.

    # PostScript Type 1 font, ASCII.
    # http://fileformats.archiveteam.org/wiki/Adobe_Type_1
    ('pfa', (0, '%!PS-AdobeFont-1.', 17, ('0', '1'), 18, ': ')),  # .pfa
    # PostScript Type 1 font, binary (Printer Font Binary).
    # http://fileformats.archiveteam.org/wiki/Adobe_Type_1
    # '\x80\x01' is followed by little-endian 32-bit size of ASCII block.
    ('pfb', (0, '\x80\x01', 3, tuple(chr(c) for c in xrange(64)), 4, '\0\0' '%!PS-AdobeFont-1.', 23, ('0', '1'), 24, ': ')),  # .pfb
    # Adobe Font Metrics. Version 4.1 is current.
    # http://fileformats.archiveteam.org/wiki/Adobe_Type_1
    # https://www.adobe.com/content/dam/acom/en/devnet/font/pdfs/5004.AFM_Spec.pdf
    ('afm', (0, 'StartFontMetrics ', 17, ('1', '2', '3', '4'), 18, '.')),  # .afm
    # https://en.wikipedia.org/wiki/Glyph_Bitmap_Distribution_Format
    ('bdf', (0, 'STARTFONT 2.', 12, ('1', '2'))),  # .bdf
    # https://fontforge.org/docs/techref/pcf-format.html
    ('pcf', (0, '\x01fcp', 4, tuple('\1\2\3\4\5\6\7\x08\x09'), 5, '\0\0\0', 8, ('\1\0', '\2\0', '\4\0', '\x08\0', '\x10\0', '\x20\0', '\x40\0', '\x80\0', '\0\1'), 10, '\0\0')),  # .pcf
    # Server Normal Format font for X11. Big endian.
    # https://en.wikipedia.org/wiki/Server_Normal_Format
    # https://github.com/TurboVNC/tightvnc/blob/master/vnc_unixsrc/Xvnc/lib/font/bitmap/snfstr.h
    # http://www.tug.org/tetex/html/fontfaq/cf_94.html
    # https://stuff.mit.edu/afs/athena.mit.edu/system/x11r4/rtlib/X11/fonts/misc/
    # https://github.com/shattered/dmd-730Xhost/blob/master/Xmtg/src/mtg/fonts/bdftosnf/showsnf.c
    ('snf', (0, '\0\0\0\4', 4, '\0\0\0', 7, ('\0', '\1'), 8, '\0\0\0', 11, ('\0', '\1'), 12, '\0\0\0', 15, ('\0', '\1'), 16, '\0\0\0', 19, ('\0', '\1'), 20, '\0\0\0', 23, ('\0', '\1'), 28, '\0\0\0', 32, '\0\0\0', 36, '\0\0\0', 40, '\0\0\0', 44, '\0\0\0')),  # .snf
))


# TODO(pts): Move everything from here to analyze(..., format=...).
ANALYZE_FUNCS_BY_FORMAT = {
    'deep': analyze_deep,
    'dcx': analyze_dcx,
    'xbm': analyze_xbm,
    'xpm': analyze_xpm,
    'xcf': analyze_xcf,
    'psd': analyze_psd,
    'tga': analyze_tga,
    'pnm': analyze_pnm,
    'xv-thumbnail': analyze_pnm,
    'pam': analyze_pam,
    'ps': analyze_ps,
    'miff': analyze_miff,
    'jbig2': analyze_jbig2,
    'djvu': analyze_djvu,
    'webp': analyze_webp,
    'jpegxr': analyze_jpegxr,
    'flif': analyze_flif,
    'fuif': analyze_fuif,
    'bpg': analyze_bpg,
    'flac': analyze_flac,
    'ape': analyze_ape,
    'vorbis': analyze_vorbis,
    'oggpcm': analyze_oggpcm,
    'opus': analyze_opus,
    'speex': analyze_speex,
    'realaudio': analyze_realaudio,
    'ralf': analyze_ralf,
    'aiff': analyze_aiff,
    'aifc': analyze_aifc,
    'au': analyze_au,
    'lepton': analyze_lepton,
    'fuji-raf': analyze_fuji_raf,
    'minolta-raw': analyze_minolta_raw,
    'dpx': analyze_dpx,
    'cineon': analyze_cineon,
    'vicar': analyze_vicar,
    'pds': analyze_pds,
    'ybm': analyze_ybm,
    'fbm': analyze_fbm,
    'cmuwm': analyze_cmuwm,
    'utah-rle': analyze_utah_rle,
    'fif': analyze_fif,
    'spix': analyze_spix,
    'sgi-rgb': analyze_sgi_rgb,
    'xv-pm': analyze_xv_pm,
    'imlib-argb': analyze_imlib_argb,
    'imlib-eim': analyze_imlib_eim,
    'farbfeld': analyze_farbfeld,
    'wbmp': analyze_wbmp,
    'gd': analyze_gd,
    'gd2': analyze_gd2,
    'cups-raster': analyze_cups_raster,
    'alias-pix': analyze_alias_pix,
    'photocd': analyze_photocd,
    'fits': analyze_fits,
    'xloadimage-niff': analyze_xloadimage_niff,
    'sun-taac': analyze_sun_taac,
    'facesaver': analyze_facesaver,
    'mcidas-area': analyze_mcidas_area,
    'macpaint': analyze_macpaint,
    'fit': analyze_fit,
    'icns': analyze_icns,
    'dds': analyze_dds,
    'flate': analyze_flate,
    'gz': analyze_gz,
    'lzma': analyze_lzma,
    'olecf': analyze_olecf,
    'pnot': analyze_pnot,
    'ac3': analyze_ac3,
    'dts': analyze_dts,
    'mng': analyze_mng,
    'html': analyze_xml,
    'svg': analyze_xml,
    'smil': analyze_xml,
    'jpegxl-brunsli': analyze_brunsli,
    'jpegxl': analyze_jpegxl,
    'pik': analyze_pik,
    'qtif': analyze_qtif,
    'psp': analyze_psp,
    'ras': analyze_ras,
    'gem': analyze_gem,
    'pcpaint-pic': analyze_pcpaint_pic,
    'pict': analyze_pict,
}
