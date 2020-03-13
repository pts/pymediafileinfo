# by pts@fazekas.hu at Sun Sep 10 00:26:18 CEST 2017

import struct

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


def analyze_flv(fread, info, fskip):
  # by pts@fazekas.hu at Sun Sep 10 00:26:18 CEST 2017
  #
  # Documented here (starting on page 68, Annex E):
  # http://download.macromedia.com/f4v/video_file_format_spec_v10_1.pdf
  #

  data = fread(13)
  if len(data) < 13:
    raise ValueError('Too short for flv.')

  if not data.startswith('FLV'):
    raise ValueError('flv signature not found.')
  info['format'] = 'flv'
  if data[3] != '\1':
    # Not found any files with other versions.
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
    'A_AC3': 'ac3',
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
}


def analyze_mkv(fread, info, fskip):
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

  def read_id():
    c = read_n(1)
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

  def read_size():
    c = read_n(1)
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

  def read_id_skip_void():
    while 1:
      xid = read_id()
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
  size = read_size()
  if size >= 256:
    raise ValueError('mkv header unreasonably large: %d' % size)
  header_end = ofs_list[0] + size
  info['format'] = 'mkv'
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
  xid = read_id_skip_void()
  if xid != '\x18\x53\x80\x67':  # Segment.
    raise ValueError('Expected Segment element, got: %s' % xid.encode('hex'))
  size = read_size()
  segment_end = ofs_list[0] + size
  info['tracks'] = []
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
          info['tracks'].append(track_info)
      break  #  in Segment, don't read anything beyond Tracks, they are large.
    else:
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
    'hev1': 'h265',
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
}

# See all on: http://mp4ra.org/codecs.html
# All keys are converted to lowercase, and whitespace-trimmed.
MP4_AUDIO_CODECS = {
    'raw':  'pcm',
    'sowt': 'pcm',
    'twos': 'pcm',
    'in24': 'pcm',
    'in32': 'pcm',
    'fl32': 'pcm',
    'fl64': 'pcm',
    'alaw': 'alaw',   # Logarithmic PCM wih A-Law
    'ulaw': 'mulaw',  # Logarithmic PCM wih mu-Law.
    '.mp3': 'mp3',
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
}

JP2_CODECS = {
    0: 'raw',
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


def analyze_mp4(fread, info, fskip):
  # Documented here: http://xhelmboyx.tripod.com/formats/mp4-layout.txt
  # Also apple.com has some .mov docs.

  info['format'] = 'mov'
  info['brands'] = []
  info['tracks'] = []
  info['has_early_mdat'] = False

  # Empty or contains the type of the last hdlr.
  last_hdlr_type_list = []

  infe_count_ary = []
  item_infos = {}
  primary_item_id_ary = []
  ipco_boxes = []
  ipma_values = []

  def process_box(size):
    """Dumps the box, and must read it (size bytes)."""
    xtype = xtype_path[-1]
    xytype = '/'.join(xtype_path[-2:])
    # Only the composites we care about.
    is_composite = xytype in (
        '/moov', '/jp2h', 'moov/trak', 'trak/mdia', 'mdia/minf', 'minf/stbl',
        '/meta', 'meta/iprp', 'iprp/ipco', 'meta/iinf')
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
        if ofs_limit < 8:
          raise ValueError('EOF in mp4 composite box size.')
        size2, xtype2 = struct.unpack('>L4s', fread(8))
        if not (8 <= size2 <= ofs_limit):
          raise ValueError(
              'EOF in mp4 composite box, size=%d ofs_limit=%d' %
              (size2, ofs_limit))
        ofs_limit -= size2
        xtype_path.append(xtype2)
        process_box(size2 - 8)
        xtype_path.pop()
    else:
      if size > 16383 or xtype in ('free', 'skip', 'wide'):
        if not fskip(size):
          raise ValueError('EOF while skipping mp4 box, xtype=%r' % xtype)
      else:
        data = fread(size)
        if len(data) != size:
          raise ValueError('EOF in mp4 box, xtype=%r' % xtype)
        if xytype == '/ftyp':
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
            info['format'] = 'jp2'
          elif major_brand == 'mif1':
            # Contains items in /meta.
            info['format'] = 'isobmff-image'
          else:
            info['format'] = 'mp4'
          info['subformat'] = major_brand.strip()
          brands = set(data[i : i + 4] for i in xrange(8, len(data), 4))
          brands.discard('\0\0\0\0')
          brands.add(major_brand)
          brands = sorted(brands)
          info['brands'] = brands  # Example: ['isom', 'mp42'].
        elif xytype == 'jp2h/ihdr':
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
    data = fread(8)
    if len(data) != 8:
      # Sometimes this happens, there is a few bytes of garbage, but we
      # don't reach it, because we break after 'moov' earlier below.
      toplevel_xtypes.discard('free')
      toplevel_xtypes.discard('skip')
      toplevel_xtypes.discard('wide')
      if 'mdat' in toplevel_xtypes and len(toplevel_xtypes) == 1:
        # This happens. The mdat can be any video, we could process
        # recursively. (But it's too late to seek back.)
        # TODO(pts): Convert this to bad_file_mdat_only error.
        # TODO(pts): Allow mpeg file (from mac).
        raise ValueError('mov file with only an mdat box.')
      if 'moov' in toplevel_xtypes:  # Can't happen, see break below.
        raise AssertionError('moov forgotten.')
      raise ValueError('mp4 moov box not found.')
    size, xtype = struct.unpack('>L4s', data)
    if size == 1:  # Read 64-bit size.
      data = fread(8)
      if len(data) < 8:
        raise ValueError('EOF in top-level 64-bit mp4 box size.')
      size, = struct.unpack('>Q', data)
      if size < 16:
        raise ValueError('64-bit mp4 box size too small.')
      size -= 16
    elif size >= 8:
      size -= 8
    else:
      # We don't allow size == 0 (meaning until EOF), because we want to
      # finish the small track parameter boxes first (before EOF).
      raise ValueError('mp4 box size too small for xtype %r: %d' % (xtype, size))
    toplevel_xtypes.add(xtype)
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
    if codec is not None:
      # Typically codec is 'hvc1' for .heic and 'av01' or .avif.
      info['codec'] = MP4_VIDEO_CODECS.get(codec, codec)
      subformat = ISOBMFF_IMAGE_SUBFORMATS.get(codec)
      if subformat:
        info['subformat'] = subformat


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
  analyze_mp4(fread, info, fskip)


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


def analyze_swf(fread, info, fskip):
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
  elif signature == 'CWS' and version >= 8:
    info['codec'] = codec = 'flate'
    read_size += 256  # Educated guess.
  elif signature == 'ZWS' and version >= 13:
    info['codec'] = codec = 'lzma'
    read_size += 256  # Educated guess.
  else:
    raise ValueError('Bad swf version %d for codec: %s' % (version, codec))
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
    return get_track_info_from_analyze_func(buffer(header, 12), analyze_mp4)
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


def analyze_ogg(fread, info, fskip):
  # https://xiph.org/ogg/
  # https://xiph.org/ogg/doc/oggstream.html
  # https://en.wikipedia.org/wiki/Ogg#File_format
  packets = {}
  page_sequences = {}
  # It seems that all the elementary stream headers are in the beginning of
  # the ogg file, with flag == 2.
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


def analyze_realmedia(fread, info, fskip):
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


def analyze_ivf(fread, info, fskip):
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


# --- Windows

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
    'xvid': 'divx',
    'mjpg': 'mjpeg',
    'msvc': 'msvc',
    'cram': 'msvc',
    'x265': 'h264',
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
    # TODO(pts): Add these.
    # 13 ffds: Not a specific codec, but anything ffdshow (ffmpeg) supports.
    #  7 uldx
    #  6 pim1
    #  4 divf
    #  2 1cva
}


def get_windows_video_codec(codec):
  codec = codec.strip().lower()  # Canonicalize FourCC.
  if codec == '\0\0\0\0':
    codec = 'uncompressed'
  elif codec in ('\1\0\0\x10', '\2\0\0\x10'):
    codec = 'mpeg'
  elif codec == '\2\0\0\x10':
    codec = 'mpeg'
  elif codec in ('\1\0\0\0', '\2\0\0\0'):
    codec = 'rle'
  elif '\0' in codec:
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


def analyze_avi(fread, info, fskip):
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
    while ofs_limit is None or ofs_limit > 0 and not do_stop_ary:
      if ofs_limit is not None and ofs_limit < 8:
        raise ValueError('No room for avi %s chunk.' % what)
      data = fread(8)
      if len(data) < 8:
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
          # BITMAPINFO starts with BITMAPINFOHEADER.
          # https://msdn.microsoft.com/en-us/library/windows/desktop/dd183376(v=vs.85).aspx
          width, height = struct.unpack('<LL', strf_data[4 : 12])
          if strh_data[4 : 8] == '\0\0\0\0':
            video_codec = strf_data[16 : 20]
          else:
            video_codec = strh_data[4 : 8]
          video_codec = get_windows_video_codec(video_codec)
          track_info = {'type': 'video', 'codec': video_codec}
          set_video_dimens(track_info, width, height)
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


# --- asf

ASF_Header_Object = guid('75b22630-668e-11cf-a6d9-00aa0062ce6c')
ASF_Stream_Properties_Object = guid('b7dc0791-a9b7-11cf-8ee6-00c00c205365')
ASF_Audio_Media = guid('f8699e40-5b4d-11cf-a8fd-00805f5c442b')
ASF_Video_Media = guid('bc19efc0-5b4d-11cf-a8fd-00805f5c442b')


def analyze_asf(fread, info, fskip):
  header = fread(30)
  if len(header) < 30:
    raise ValueError('Too short for asf.')
  guid, size, count, reserved12 = struct.unpack('<16sQLH', header)
  if guid != ASF_Header_Object:
    raise ValueError('asf signature not found.')
  if reserved12 != 0x201:
    raise ValueError('Unexpected asf reserved12 value: 0x%x' % reserved12)
  if size < 54:
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
  if len(data) > 255:  # Typically just 22 bytes.
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
    # Untested, based on h264_scale.c.
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
      # Untested.
      io['chroma_format'] = read_ue()
      if io['chroma_format'] == 3:
        io['residual_colour_transform_flag'] = read_1()
      io['bit_depth_luma_minus8'] = read_ue()
      io['bit_depth_chroma_minus8'] = read_ue()
      io['qpprime_y_zero_transform_bypass_flag'] = read_1()
      io['seq_scaling_matrix_present_flag'] = read_1()
      if io['seq_scaling_matrix_present_flag']:
        for si in xrange(8):
          if read_1():
            read_scaling_list((64, 16)[i < 6])
    io['log2_max_frame_num'] = 4 + read_ue()
    io['pic_order_cnt_type'] = read_ue()
    if io['pic_order_cnt_type'] == 0:
      io['log2_max_pic_order_cnt'] = 4 + read_ue()
    elif io['pic_order_cnt_type'] == 1:
      io['log2_max_pic_order_cnt'] = 0
      io['delta_pic_order_always_zero_flag'] = read_1()
      io['offset_for_non_ref_pic'] = read_se()
      io['offset_for_top_to_bottom_field'] = read_se()
      for _ in read_ue():
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


def analyze_h264(fread, info, fskip):
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
  header = header[i:]
  info['tracks'] = [{'type': 'video', 'codec': 'h264'}]
  if len(header) < 40:  # Maybe 32 bytes are also enough.
    header += fread(40 - len(header))
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


def analyze_h265(fread, info, fskip):
  # H.265 is also known as MPEG-4 HEVC.
  #
  # https://www.itu.int/rec/dologin.asp?lang=e&id=T-REC-H.265-201504-S!!PDF-E&type=items
  # https://www.codeproject.com/Tips/896030/The-Structure-of-HEVC-Video
  header = fread(15)
  i = count_is_h265(header) // 100
  if not i:
    raise ValueError('h265 signature not found.')
  assert i <= len(header), 'h265 preread header too short.'
  info['tracks'] = [{'type': 'video', 'codec': 'h265'}]
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


def is_mpeg_adts(header):
  # Works with: isinstance(header, (str, buffer)).
  return (len(header) >= 4 and header[0] == '\xff' and
          ((header[1] in '\xe2\xe3' '\xf2\xf3\xf4\xf5\xf6\xf7\xfa\xfb\xfc\xfd\xfe\xff' '\xf0\xf1\xf8\xf9' and
           ord(header[2]) >> 4 not in (0, 15) and ord(header[2]) & 0xc != 12) or
           (header[1] in '\xf0\xf1\xf8\xf9' and not ord(header[2]) >> 6 and ((ord(header[2]) >> 2) & 15) < 13)))


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
    if ord(header[2]) >> 6:
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


def analyze_mpeg_adts(fread, info, fskip, header=''):
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

  __slots__ = ('_buf', '_header_ofs')

  def __init__(self):
    self._buf, self._header_ofs = '', 0

  def get_track_info(self):
    buf = self._buf
    if buf.startswith('\xff') and is_mpeg_adts(buf):
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
    if ((buf.startswith('\xff') and is_mpeg_adts(buf)) or
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
    track_info = {'type': 'video', 'codec': 'mpeg-4', }
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
      if start_data in ('\0\0\1\xb2', '\0\0\1\xb8'):
        track_info['codec'] = 'mpeg-1'
      elif start_data in ('\0\0\1\xb5'):  # MPEG-2 sequence extension.
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

  __slots__ = ('_buf', '_header_ofs')

  def __init__(self):
    self._buf, self._header_ofs = '', 0

  def get_track_info(self):
    buf = self._buf
    # MPEG video sequence header start code.
    if buf.startswith('\0\0\1') and buf[3 : 4] in '\xb3\xb5\xb0':
      try:
        parse_mpeg_video_header(buf)
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
      buf = self._buf
      # MPEG video sequence header start code. We need 7 bytes of header.
      if buf.startswith('\0\0\1') and buf[3 : 4] in '\xb3\xb0\xb5':  # Found before signature.
        if len(buf) < 145:
          self._buf = buf + data[:145 - len(buf)]
      elif buf.endswith('\0\0\1') and data[0] in '\xb3\xb0\xb5':
        self._header_ofs += len(buf) - 3
        self._buf = buf[-3:] + data[:16]  # Found signature.
      elif buf.endswith('\0\1') and data[:2] in ('\1\xb3', '\1\xb0', '\1\xb5'):
        self._header_ofs += len(buf) - 2
        self._buf = buf[-2:] + data[:16]  # Found signature.
      elif buf.endswith('\0') and data[:3] == ('\0\1\xb3', '\0\1\xb0', '\0\1\xb5'):
        self._header_ofs += len(buf) - 1
        self._buf = buf[-1] + data[:16]  # Found signature.
      else:
        self._header_ofs += len(buf)
        data = data[:]  # Convert buffer to str.
        i = i1 = data.find('\0\0\1\xb3')
        i2 = data.find('\0\0\1\xb0')
        i3 = data.find('\0\0\1\xb5')
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


def analyze_mpeg_video(fread, info, fskip):
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


def analyze_mpeg_ps(fread, info, fskip):
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
  #         Audio streams are typically bd[80], bd[81] etc.
  # * 0xbe; Padding stream; no extension, just ignore contents
  # * 0xbf; Private stream 2 (navigation data); mostly in DVD .vob; no extension
  # * 0xc0...0xdf; MPEG-1 or MPEG-2 audio stream; has extension
  # * 0xe0...0xef; MPEG-1 or MPEG-2 video stream; has extension
  # * Others: http://dvd.sourceforge.net/dvdinfo/mpeghdrs.html
  #
  # These are present, but not as MPEG-PES SID (stream ID) values:
  #
  # * 0xb9: MPEG-PS end
  # * 0xba: MPEG-PS header (file signature)
  # * 0xbb: MPEG-PS system header packet
  # * 0xbc: program stream map
  # * 0xff: program stream directory
  #
  # TODO(pts): Can we get a list of SIDs without scanning through the file?
  header = fread(12)
  if len(header) < 12:
    raise ValueError('Too short for mpeg-ps.')
  if not header.startswith('\0\0\1\xba'):
    raise ValueError('mpeg-ps signature not found.')
  info['format'] = 'mpeg-ps'
  if ord(header[4]) >> 6 == 1:
    info['subformat'] = 'mpeg-2'  # MPEG-2 program stream.
    header += fread(2)
    if len(header) < 14:
      raise ValueError('Too short for mpeg-ps mpeg-2.')
    size = 14 + (ord(header[13]) & 7)
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
  while 1:
    data = fread(4)
    while len(data) == 4 and not data.startswith('\0\0\1'):
      # TODO(pts): Don't skip or read too much in total.
      data = data[1 : 4] + fread(1)
      skip_count += 1
      if skip_count >= 100000:
        break
    if len(data) != 4:
      break
    sid = ord(data[3])
    if sid == 0xb9:  # MPEG end code.
      break
    elif sid == 0xba:  # MPEG pack.
      data = fread(8)
      if len(data) < 8:
        break  # raise ValueError('EOF in mpeg-ps pack.')
      if ord(data[0]) >> 6 == 1:  # MPEG-2.
        data += fread(2)
        if len(data) < 10:
          raise ValueError('Too short for mpeg-ps mpeg-2 pack.')
        size = 10 + (ord(data[9]) & 7)
      elif ord(data[0]) >> 4 == 2:  # MPEG-1.
        size = 8
      else:
        raise ValueError('Invalid mpeg-ps pack subformat 0x%02x.' % ord(data[0]))
      assert size >= len(data), 'mpeg-ps pack size too large.'
      if not fskip(size - len(data)):
        break  # raise ValueError('EOF in mpeg-ps pack header.')
      expect_system_header = True
    elif sid == 0xbb:  # MPEG system header.
      packet_count += 1
      if packet_count > 1500:
        break
      if not expect_system_header:
        raise ValueError('Unexpected mpeg-ps system header.')
      expect_system_header = False
      data = fread(2)
      if len(data) < 2:
        break  # raise ValueError('EOF in mpeg-ps system header size.')
      size, = struct.unpack('>H', data)
      if not fskip(size):
        break  # raise ValueError('EOF in mpeg-ps system header.')
    elif 0xc0 <= sid < 0xf0 or sid in (0xbd, 0xbe, 0xbf, 0xbc, 0xff):  # PES packet.
      packet_count += 1
      if packet_count > 1500:
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
               finders[sid] = MpegVideoHeaderFinder()
             finders[sid].append(buffer(data, i))
             track_info = finders[sid].get_track_info()
             if track_info and track_info['codec'] != 'mpeg':  # Use first video stream with header.
               had_video = True
               info['tracks'].append(track_info)
               info['pes_video_at'] = track_info['header_ofs']
        elif 0xc0 <= sid < 0xe0 or 0x180 <= sid < 0x1a0:  # Audio.
          av_packet_count += 1
          if not had_audio:
             if sid not in finders:
               finders[sid] = MpegAudioHeaderFinder()
             finders[sid].append(buffer(data, i))
             track_info = finders[sid].get_track_info()
             if track_info:  # Use first video stream with header.
               had_audio = True
               info['tracks'].append(track_info)
               info['pes_audio_at'] = track_info['header_ofs']
          if (had_audio and had_video) or av_packet_count > 1000:
            break
    #else:  # Some broken MPEGs have useless SIDs, ignore those silently.
    #  raise ValueError('unexpected mpeg-ps sid=0x%02x' % sid)
  info['hdr_packet_count'] = packet_count
  info['hdr_av_packet_count'] = av_packet_count
  info['hdr_skip_count'] = skip_count


# --- mpeg-ts (MPEG TS).


def get_jpeg_dimensions(fread):
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

  data = fread(4)
  if len(data) < 4:
    raise ValueError('Too short for jpeg.')
  if not data.startswith('\xff\xd8\xff'):
    raise ValueError('jpeg signature not found.')
  m = ord(data[3])
  while 1:
    while m == 0xff:  # Padding.
      m = ord(read_all(1))
    if m in (0xd8, 0xd9, 0xda):
      # 0xd8: SOI unexpected.
      # 0xd9: EOI unexpected before SOF.
      # 0xda: SOS unexpected before SOF.
      raise ValueError('Unexpected marker: 0x%02x' % m)
    ss, = struct.unpack('>H', read_all(2))
    if ss < 2:
      raise ValueError('Segment too short.')
    ss -= 2
    if 0xc0 <= m <= 0xcf and m not in (0xc4, 0xc8, 0xcc):  # SOF0 ... SOF15.
      if ss < 5:
        raise ValueError('SOF segment too short.')
      height, width = struct.unpack('>xHH', read_all(5))
      return width, height
    read_all(ss)

    # Read next marker to m.
    m = read_all(2)
    if m[0] != '\xff':
      raise ValueError('Marker expected.')
    m = ord(m[1])
  raise AssertionError('Internal JPEG parser error.')


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


def is_jp2(header):
  return (len(header) >= 28 and
          header.startswith('\0\0\0\x0cjP  \r\n\x87\n\0\0\0') and
          header[16 : 20] == 'ftyp' and
          header[20 : 24] in ('jp2 ', 'jpm ', 'jpx '))


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
          buffer(header, 12), analyze_mp4,
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
          buffer(header, 12), analyze_mp4,
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
      if (h & 0xe000) != 0xe000:
        raise ValueError('Bad mpeg-ts pat entry reserved3.')
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
  is_bdav = header.startswith('\0\0')
  i = (0, 4)[is_bdav]
  if len(header) < i + 4:
    return False
  had_pat = had_pat_pusi = False
  cc_by_pid = {}
  #print '---ts'
  for pc in xrange(5):  # Number of packets to scan.
    if len(header) < i + 4:
      return True
    if header[i] != '\x47':
      return False
    b, = struct.unpack('>L', header[i : i + 4])
    tei, pusi, tp = (b >> 23) & 1, (b >> 22) & 1, (b >> 21) & 1
    pid = (b >> 8) & 0x1fff  # Packet id.
    tsc, afc, cc = (b >> 6) & 3, (b >> 4) & 3, b & 15
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


def analyze_mpeg_ts(fread, info, fskip):
  prefix = fread(4)
  if len(prefix) < 4:
    raise ValueError('Too short for mpeg-ts.')
  ts_packet_count = ts_pusi_count = ts_payload_count = 0
  if prefix.startswith('\x47'):
    is_bdav = False
    info['subformat'] = 'ts'
  elif prefix.startswith('\0\0'):
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
    ts_packet_count += 1
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
        raise ValueError('Bad mpeg-ps header until packet %d.' % ts_packet_count)
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
    raise ValueError('Bad mpeg-ps header.')
  info['hdr_ts_packet_count'] = ts_packet_count
  info['hdr_ts_payload_count'] = ts_payload_count
  info['hdr_ts_pusi_count'] = ts_pusi_count
  info['hdr_vstreams'] = es_streams_by_type['video']
  info['hdr_astreams'] = es_streams_by_type['audio']
  info['hdr_vframes'] = es_payloads_by_type['video']
  info['hdr_aframes'] = es_payloads_by_type['audio']
  if not programs:
    raise ValueError('Missing mpeg-ts pat payload.')
  if not es_streams:
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


def analyze_id3v2(fread, info, fskip):
  # Just reads the ID3v2 header with fread and fskip.
  # http://id3.org/id3v2.3.0
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
  c = 0
  while 1:  # Skip some \0 bytes.
    if not header.startswith('\0') or len(header) != 4 or c >= 4096:
      break
    c += 1
    if header.startswith('\0\0\0'):
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
  return analyze_func(fread, info, fskip, header)


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
  if len(header) < 13 or not (
      header.startswith('GIF87a') or header.startswith('GIF89a')):
    raise ValueError('Not a GIF file.')
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
    if b == 0x3B:  # End of file.
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
        # TODO(pts): AssertionError: Unknown extension: 0x01; in badgif1.gif
        if b not in (0xf9, 0xfe):
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
    elif b == 0x2C:  # Image Descriptor.
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
    bits = yield_bits_msbfirst(fread)
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
    bits = yield_bits_lsbfirst(fread)
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
  width = read_dimen()
  height = read_dimen()
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
    had_xtypes.add(xtype)
    if size >> 25:
      raise ValueError('qtif %s atom too large.' % xtype)
    if size < 8:
      raise ValueError('qtif atom too small.')
    if not fskip(size - 8):
      raise ValueError('EOF in qtif %s atom.' % xtype)
    data = fread(8)
    if len(data) < 8:
      raise ValueError('Too short for qtif atom.')
    size, xtype = struct.unpack('>L4s', data)
    if xtype not in ('idsc', 'iicc', 'idat'):
      raise ValueError('Bad qtif atom: %r' % xtype)
  if size >> 8:
    raise ValueError('qtif idsc atom too large.')
  if size < 36 + 8:
    raise ValueError('qtif idsc atom too small.')
  data = fread(36)
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
  if len(data) < 58:
    raise ValueError('EOF in psp image header.')
  info['format'] = 'psp'
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
  data = fread(4)
  if len(data) < 4:
    raise ValueError('Too short for ras.')
  if not data.startswith('\x59\xa6\x6a\x95'):
    raise ValueError('ras signature not found.')
  info['format'] = 'ras'
  data = fread(8)
  if len(data) < 4:
    raise ValueError('EOF in ras header.')
  info['width'], info['height'] = struct.unpack('>LL', data)


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


def analyze_xwd(fread, info, fskip):
  # https://www.fileformat.info/format/xwd/egff.htm
  # http://fileformats.archiveteam.org/wiki/XWD
  # https://en.wikipedia.org/wiki/Xwd
  data = fread(28)
  if len(data) < 28:
    raise ValueError('Too short for xwd.')
  header_size, file_version = struct.unpack('>LL', data[:8])
  if not 28 <= header_size <= 512:
    raise ValueError('Bad xwd header size: %d' % header_size)
  if file_version == 6:
    info['format'], info['subformat'] = 'xwd', 'x10'
    display_type, display_planes, pixmap_format, width, height = struct.unpack('>8x5L', data)
    if display_type > 16:
      raise ValueError('Bad xwd display type: %d' % display_type)
    if not 1 <= display_planes <= 5:  # Typically 1 or 3.
      raise ValueError('Bad xwd display planes: %d' % display_planes)
    if pixmap_format > 1:
      raise ValueError('Bad xwd pixmap format: %d' % pixmap_format)
  elif file_version == 7:
    info['format'], info['subformat'] = 'xwd', 'x11'
    pixmap_format, pixmap_depth, width, height = struct.unpack('>8x4L4x', data)
    if not 1 <= pixmap_depth <= 32:
      raise ValueError('Bad xwd pixmap depth: %d' % pixmap_depth)
    if pixmap_format > 2:
      raise ValueError('Bad xwd pixmap format: %d' % pixmap_format)
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


def analyze_sun_icon(fread, info, fskip):
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


def analyze_wav(fread, info, fskip):
  header = fread(36)
  if len(header) < 36:
    raise ValueError('Too short for wav.')
  if not header.startswith('RIFF') or header[8 : 12] != 'WAVE':
    raise ValueError('wav signature not found.')
  info['format'] = 'wav'
  if header[12 : 16] != 'fmt ':
    raise ValueError('wav fmt chunk missing.')
  wave_format, channel_count, sample_rate, _, _, sample_size = (
      struct.unpack('<HHLLHH', header[20 : 36]))
  info['tracks'] = []
  info['tracks'].append({
      'type': 'audio',
      'codec': WINDOWS_AUDIO_FORMATS.get(
          wave_format, '0x%x' % wave_format),
      'channel_count': channel_count,
      'sample_rate': sample_rate,
      # With 'codec': 'mp3', sample_size is usually 0.
      'sample_size': sample_size or 16,
  })


def analyze_exe(fread, info, fskip):
  header = fread(64)
  if len(header) < 64:
    raise ValueError('Too short for exe.')
  if not header.startswith('MZ'):
    raise ValueError('exe signature not found.')
  info['format'] = 'exe'
  pe_ofs, = struct.unpack('<L', header[60 : 64])
  if pe_ofs < 8180 and len(header) < pe_ofs + 300:
    header += fread(pe_ofs + 300 - len(header))
  if (len(header) >= pe_ofs + 6 and
      header.startswith('MZ') and
      header[pe_ofs : pe_ofs + 4] == 'PE\0\0' and
      header[pe_ofs + 24 : pe_ofs + 26] in ('\x0b\1', '\x0b\2') and
      # Only i386 and amd64 are recognized.
      header[pe_ofs + 4 : pe_ofs + 6] in ('\x4c\01', '\x64\x86')):
    # Windows .exe file (PE, Portable Executable).
    info['format'] = 'winexe'
    # 108 bytes instead of 92 bytes for PE32+.
    rva_ofs = pe_ofs + 24 + 92 + 16 * (
        header[pe_ofs + 24 : pe_ofs + 26] == '\x0b\2')
    rva_count, = struct.unpack('<L', header[rva_ofs : rva_ofs + 4])
    if rva_count > 14:  # IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR.
      vaddr, size = struct.unpack('<LL', header[rva_ofs + 116 : rva_ofs + 124])
      if vaddr > 0 and size > 0:  # Typically vaddr == 8292, size == 72.
        info['format'] = 'dotnetexe'  # .NET executable assembly.


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


def analyze_xml(fread, info, fskip):
  header = fread(6)
  if len(header) < 6:
    raise ValueError('Too short for xml.')
  whitespace = '\t\n\x0b\x0c\r '
  whitespace_tagend = whitespace + '>'
  if header.startswith('<?xml') and header[5] in whitespace:
    info['format'], data = 'xml', ''
  elif header.startswith('<svg:'):
    if len(header) < 9:
      header += fread(9 - len(header))
      if len(header) < 9:
        raise ValueError('Too short for svg.')
    if header.startswith('<svg:svg') and header[8] in whitespace_tagend:
      info['format'], data = 'svg', ''
      data = '?><svg' + header[8:]
    else:
      raise ValueError('svg signature not found.')
  elif header.startswith('<svg') and header[4] in whitespace_tagend:
    info['format'], data = 'svg', ''
    data = '?>' + header
  elif header.startswith('<smil') and header[5] in whitespace_tagend:
    info['format'], data = 'smil', ''
    data = '?>' + header
  else:
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
      while i < len(data) and (data[i].isalpha() or data[i] in '-:_'):
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
        while i < len(data) and (data[i].isalpha() or data[i] == '-'):
          i += 1
        tag_name = data[j : i]
        j = i
        i = data.find('>', j) + 1
        if i <= 0:
          raise EOFError
        if tag_name.startswith('!'):
          if tag_name == '!DOCTYPE':
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
        elif tag_name == 'smil':
          info['format'] = 'smil'
          # No width= and height= attributes in SMIL.
        elif tag_name == 'svg':
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


def analyze_bmp(fread, info, fskip):
  # https://en.wikipedia.org/wiki/BMP_file_format
  header = fread(26)
  if len(header) < 26:
    raise ValueError('Too short for bmp.')
  if not header.startswith('BM'):
    raise ValueError('bmp signature not found.')
  if header[6 : 10] != '\0\0\0\0' or header[15 : 18] != '\0\0\0':
    raise ValueError('Bad bmp header.')
  b = ord(header[14])
  if not 12 <= b <= 127:
    raise ValueError('Bad bmp info size: %d' % b)
  info['format'] = 'bmp'
  # TODO(pts): Detect codec other than 'uncompressed'.
  if b < 40 and len(header) >= 22:
    info['width'], info['height'] = struct.unpack(
        '<HH', header[18 : 22])
  elif b >= 40 and len(header) >= 26:
    info['width'], info['height'] = struct.unpack(
        '<LL', header[18 : 26])


def analyze_flic(fread, info, fskip):
  header = fread(16)
  if len(header) < 16:
    raise ValueError('Too short for flic.')
  cc = header[4 : 6]
  if cc == '\x12\zaf':
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


def analyze_mng(fread, info, fskip):
  # http://www.libpng.org/pub/mng/spec/
  header = fread(24)
  if len(header) < 24:
    raise ValueError('Too short for mng.')
  if not header.startswith('\212MNG\r\n\032\n\0\0\0'):
    raise ValueError('mng signature not found.')
  info['format'] = 'mng'
  info['tracks'] = [{'codec': 'jpeg+png'}]
  if header[12 : 16] == 'MHDR':
    width, height = struct.unpack('>LL', header[16 : 24])
    set_video_dimens(info['tracks'][0], width, height)


def analyze_png(fread, info, fskip):
  # https://tools.ietf.org/html/rfc2083
  header = fread(24)
  if len(header) < 24:
    raise ValueError('Too short for png.')
  if not header.startswith('\211PNG\r\n\032\n\0\0\0'):
    raise ValueError('png signature not found.')
  info['format'] = 'png'
  info['codec'] = 'flate'
  if header[12 : 16] == 'IHDR':
    info['width'], info['height'] = struct.unpack('>LL', header[16 : 24])


def analyze_jng(fread, info, fskip):
  # http://www.libpng.org/pub/mng/spec/jng.html
  header = fread(24)
  if len(header) < 24:
    raise ValueError('Too short for jng.')
  if not header.startswith('\213JNG\r\n\032\n\0\0\0'):
    raise ValueError('jng signature not found.')
  info['format'] = 'jng'
  info['codec'] = 'jpeg'
  if header[12 : 16] == 'JHDR':
    info['width'], info['height'] = struct.unpack('>LL', header[16 : 24])


def analyze_lbm(fread, info, fskip):
  # https://en.wikipedia.org/wiki/ILBM
  header = fread(24)
  if len(header) < 24:
    raise ValueError('Too short for lbm.')
  if not (header.startswith('FORM') and
          header[8 : 12] in ('ILBM', 'PBM ') and
          header[12 : 20] == 'BMHD\0\0\0\x14'):
    raise ValueError('lbm signature not found.')
  info['format'] = 'lbm'
  if header[8] == 'I':
    info['codec'] = 'rle'
  else:
    info['codec'] = 'uncompressed'
  info['width'], info['height'] = struct.unpack('>HH', header[20 : 24])


def analyze_pcx(fread, info, fskip):
  # https://en.wikipedia.org/wiki/PCX
  header = fread(12)
  if len(header) < 12:
    raise ValueError('Too short for pcx.')
  signature, version, encoding, bpp, xmin, ymin, xmax, ymax = struct.unpack(
      '<BBBBHHHH', header)
  if signature != 10 or version > 5 or encoding != 1 or bpp not in (1, 2, 4, 8):
    raise ValueError('pcx signature not found.')
  if xmax < xmin:
    raise ValueError('pcx xmax smaller than xmin.')
  if ymax < ymin:
    raise ValueError('pcx ymax smaller than ymin.')
  info['format'] = 'pcx'
  info['codec'] = 'rle'
  info['width'], info['height'] = xmax - xmin + 1, ymax - ymin + 1


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
  if bpp not in (1, 2, 4, 8, 16, 24, 32):  # Bits per pixel.
    raise ValueError('Bad tga bpp: %d' % bpp)
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


def analyze_tiff(fread, info, fskip):
  # https://www.adobe.io/content/dam/udp/en/open/standards/tiff/TIFF6.pdf
  # https://en.wikipedia.org/wiki/TIFF
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
  if not fskip(ifd_ofs - 8):
    raise ValueError('EOF before tiff ifd_ofs.')
  data = fread(2)
  if len(data) < 2:
    raise ValueError('EOF in tiff ifd_size.')
  ifd_count, = struct.unpack(fmt + 'H', data)
  if ifd_count < 10:
    raise ValueError('tiff ifd_count too small: %d' % ifd_count)
  ifd_data = fread(12 * ifd_count)
  if len(ifd_data) != 12 * ifd_count:
    raise ValueError('EOF in tiff ifd_data.')
  ifd_fmt, short_fmt = fmt + 'HHLL', fmt + 'H'
  for i in xrange(0, len(ifd_data), 12):
    # if ie_tag < 254: raise ValueError('...')
    ie_tag, ie_type, ie_count, ie_value = struct.unpack(
        ifd_fmt, buffer(ifd_data, i, 12))
    if ie_count == 1 and ie_type in (3, 4):  # (SHORT, LONG).
      if ie_type == 3:  # SHORT.
        ie_value, = struct.unpack(short_fmt, buffer(ifd_data, i + 8, 2))
      if ie_tag == 256:  # ImageWidth.
        info['width'] = ie_value
      elif ie_tag == 257:  # ImageLength.
        info['height'] = ie_value
      elif ie_tag == 259:  # Compression.
        if ie_value in TIFF_CODECS:
          info['codec'] = TIFF_CODECS[ie_value]
        else:
          info['codec'] = str(ie_value)


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
    if header[1] in '123':
      info['codec'] = 'uncompressed-ascii'
    else:
      info['codec'] = 'uncompressed'  # Raw.
  else:
    raise ValueError('pnm signature not found.')
  if header[1] == '7':
    # http://fileformats.archiveteam.org/wiki/XV_thumbnail
    # https://github.com/ingowald/updated-xv/blob/395756178dad44efb950e3ea6739fe60cc62d314/xvbrowse.c#L4034-L4059
    header += fread(4)
    if header != 'P7 332\n':
      raise ValueError('xv-thumbnail signature not found.')
    info['format'] = 'xv-thumbnail'
  else:
    info['format'] = 'pnm'
  data = header[-1]
  state = 0
  dimensions = []
  memory_budget = 100
  while 1:
    if not data:
      raise ValueError('EOF in %s header.' % info['format'])
    if memory_budget < 0:
      raise ValueError('pnm header too long.')
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
      if len(dimensions) == 2:
        break
      state = 0
    else:
      raise ValueError('Bad character in pnm header: %r' % data)
    data = fread(1)
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
        raise EOFError('EOF in pam header line.')
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
    raise EOFError('EOF in pam header before ENDHDR.')

  while 1:
    try:
      process_lines(data)
      break
    except EOFError:
      size = len(data)
      if size >= 8192 or size & (size - 1):  # Not a power of 2.
        raise
      data += fread(size)
      if size == len(data):
        raise


def analyze_ps(fread, info, fskip):
  header = fread(15)
  if len(header) < 15:
    raise ValueError('Too short for ps.')
  if not (header.startswith('%!PS-Adobe-') and
          header[11] in '123' and header[12] == '.'):
    raise ValueError('ps signature not found.')
  info['format'] = 'ps'
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
  if ' EPSF-' in header[0]:
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


def analyze_wmf(fread, info, fskip):
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
    info['format'] = 'wmf'
    data = fread(12)
    if len(data) == 12 and data[10 : 12] != '\0\0':
      raise ValueError('Bad wmf NumberOfMembers.')
  else:
    raise ValueError('wmf signature not found.')


def analyze_emf(fread, info, fskip):
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


def analyze_dvi(fread, info, fskip):
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


def analyze_vp8(fread, info, fskip):
  header = fread(10)
  track_info = get_vp8_track_info(header)
  info['format'] = 'vp8'
  info['tracks'] = [track_info]


def is_webp(header):
  if not (len(header) >= 26 and header.startswith('RIFF') and
          header[8 : 15] == 'WEBPVP8' and header[15] in ' L'):
    return False
  if header[15] == ' ' and header[23 : 26] != '\x9d\x01\x2a':
    return False
  if header[15] == 'L' and header[20] != '\x2f':
    return False
  size1, size2 = struct.unpack('<4xL8xL', header[:20])
  return size1 - size2 == 12 and size2 > 6


def analyze_webp(fread, info, fskip):
  header = fread(26)
  if len(header) < 26:
    raise ValueError('Too short for webp.')
  if not (header.startswith('RIFF') and
          header[8 : 15] == 'WEBPVP8' and header[15] in ' L'):
    raise ValueError('webp signature not found.')
  info['format'] = 'webp'
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


def analyze_vp9(fread, info, fskip):
  header = fread(10)
  track_info = get_vp9_track_info(header)
  info['format'] = 'vp9'
  info['tracks'] = [track_info]


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


def analyze_av1(fread, info, fskip):
  header = fread(131)
  track_info = get_av1_track_info(header)
  info['format'] = 'av1'
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


def analyze_dirac(fread, info, fskip):
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


def analyze_theora(fread, info, fskip):
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


def analyze_daala(fread, info, fskip):
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


def analyze_yuv4mpeg2(fread, info, fskip):
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


def analyze_realvideo(fread, info, fskip):
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
  header = fread(6)
  if len(header) < 6:
    raise ValueError('Too short for fuif.')
  signature, component_count, bpc = struct.unpack('>4sBB', header)
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

  def read_varint(name):
    v, c, cc = 0, 128, 0
    while c & 128:
      if cc > 8:  # 63 bits maximum.
        raise ValueError('fuif %s varint too long.' % name)
      c = fread(1)
      if not c:
        raise ValueError('EOF in fuif %s.' % name)
      c = ord(c)
      v = v << 7 | c & 127
      cc += 1
    return v

  info['width'] = read_varint('width') + 1
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


def analyze_art(fread, info, fskip):
  # https://en.wikipedia.org/wiki/ART_image_file_format
  # https://multimedia.cx/eggs/aol-art-format/
  # http://samples.mplayerhq.hu/image-samples/ART/
  header = fread(17)
  if len(header) < 17:
    raise ValueError('Too short for art.')
  if not (header.startswith('JG') and header[2] in '\3\4' and
          header[3 : 8] == '\016\0\0\0\0'):
    raise ValueError('art signature not found.')
  # Usually header[8 : 13] == '\7\0\x40\x15\x03'.
  info['format'] = info['codec'] = 'art'
  # This is mostly an educated guess based on samples, the file format is
  # not documented. Not even XnView MP or IrfanView can open them.
  if header[8 : 13] == '\7\0\x40\x15\3':
    info['width'], info['height'] = struct.unpack('<HH', header[13 : 17])
  else:
    pass  # Example: P50374Bc.art has header[8 : 13] == '\x8c\x16\0\0\x7d'.


def analyze_ico(fread, info, fskip):
  # https://en.wikipedia.org/wiki/ICO_(file_format)#Outline
  header = fread(6)
  if len(header) < 6:
    raise ValueError('Too short for ico.')
  signature, image_count = struct.unpack('<4sH', header)
  if not (signature == '\0\0\1\0' and 1 <= image_count <= 12):
    raise ValueError('ico signature not found.')
  info['format'] = 'ico'
  best = (0,)
  min_image_offset = 6 + 16 * image_count
  for _ in xrange(image_count):
    data = fread(16)
    if len(data) < 16:
      raise ValueError('EOF in ico image entry.')
    width, height, color_count, reserved, color_plane_count, bits_per_pixel, image_size, image_offset = struct.unpack(
        '<BBBBHHLL', data)
    if reserved not in (0, 1):
      raise ValueError('Bad ico reserved byte: %d' % reserved)
    if color_plane_count > 4:
      raise ValueError('Bad ico color_plane_count: %d' % color_plane_count)
    if bits_per_pixel not in (0, 1, 2, 4, 8, 16, 24, 32):
      raise ValueError('Bad ico bits_per_pixel: %d' % bits_per_pixel)
    if not image_size:
      raise ValueError('Bad ico image size.')
    if image_offset < min_image_offset:
      raise ValueError('Bad ico image_offset.')
    width += (width == 0) << 8
    height += (height == 0) << 8
    best = max(best, (width * height, width, height))
    # TODO(pts): Detect .png compression at image_offset.
  assert best[0], 'Best width * height not found.'
  _, info['width'], info['height'] = best  # Largest icon.


def analyze_gif(fread, info, fskip):
  # Still short enough for is_animated_gif.
  header = fread(10)
  if len(header) < 10:
    raise ValueError('Too short for gif.')
  if not header.startswith('GIF87a') and not header.startswith('GIF89a'):
    raise ValueError('gif signature not found.')
  info['format'] = 'gif'
  info['codec'] = 'lzw'
  info['width'], info['height'] = struct.unpack('<HH', header[6 : 10])
  if is_animated_gif(fread, header):  # This may read the entire input.
    info['format'] = 'agif'


# --- File format detection for many file formats and getting media
# parameters for some.


def adjust_confidence(base_confidence, confidence):
  return (confidence, max(1, confidence - base_confidence))


XML_WHITESPACE_TAGEND = ('\t', '\n', '\x0b', '\x0c', '\r', ' ', '>')

MAX_CONFIDENCE = 100000

# TODO(pts): Static analysis: fail on duplicate format name. (Do we want this?)
# TODO(pts): Static analysis: autodetect conflicts and subsumes in string-only matchers.
# TODO(pts): Optimization: create prefix dicts (for 4 bytes and 8 bytes).
FORMAT_ITEMS = (
    # (n, f, ...) means: read at most n bytes from the beginning of the file
    # to header, call f(header).
    ('empty', (1, lambda header: (len(header) == 0, MAX_CONFIDENCE))),
    ('short1', (2, lambda header: (len(header) == 1, MAX_CONFIDENCE))),
    ('short2', (3, lambda header: (len(header) == 2, MAX_CONFIDENCE))),
    ('short3', (4, lambda header: (len(header) == 3, MAX_CONFIDENCE))),

    # Media container (with audio and/or video).

    # Can also be .webm as a subformat.
    ('mkv', (0, '\x1a\x45\xdf\xa3')),
    # TODO(pts): Add support for ftyp=mis1 (image sequence) or ftyp=hevc, ftyp=hevx.
    ('mp4-wellknown-brand', (0, '\0\0\0', 4, 'ftyp', 8, ('qt  ', 'f4v ', 'isom', 'mp41', 'mp42', 'jp2 ', 'jpm ', 'jpx ', 'mif1'), 4, lambda header: (is_mp4(header), 26))),
    ('mp4', (0, '\0\0\0', 4, 'ftyp', 4, lambda header: (is_mp4(header), 26))),
    ('f4v',),  # From 'mp4'.
    ('webm',),  # From 'mp4'.
    ('mov',),  # From 'mp4'.
    ('isobmff-image',),  # From 'mp4'.
    ('mov-mdat', (4, 'mdat')),  # TODO(pts): Analyze mpeg inside.
    # This box ('wide', 'free' or 'skip'), after it's data, is immediately
    # followed by an 'mdat' box (typically 4-byte size, then 'mdat'), but we
    # can't detect 'mdat' here, it's too far for us.
    ('mov-skip', (0, '\0\0', 4, ('wide', 'free', 'skip'))),
    ('mov-moov', (0, '\0', 1, ('\0', '\1', '\2', '\3', '\4', '\5', '\6', '\7', '\x08'), 4, ('moov',))),
    ('ogg', (0, 'OggS\0')),
    ('asf', (0, '0&\xb2u\x8ef\xcf\x11\xa6\xd9\x00\xaa\x00b\xcel')),
    ('wmv',),  # From 'asf'.
    ('wma',),  # From 'asf'.
    ('avi', (0, 'RIFF', 8, 'AVI ')),
    # \1 is the version number, but there is no version later than 1 in 2017.
    ('flv', (0, 'FLV\1', 5, '\0\0\0\x09')),
    # Video CD (VCD).
    ('mpeg-cdxa', (0, 'RIFF', 8, 'CDXA')),
    ('mpeg-ps', (0, '\0\0\1\xba')),
    ('mpeg-ts', (0, ('\0', '\x47'), 392, lambda header: (is_mpeg_ts(header), 301))),
    ('realmedia', (0, '.RMF\0\0\0')),
    # .bup and .ifo files on a video DVD.
    ('dvd-bup', (0, 'DVDVIDEO-V', 10, ('TS', 'MG'))),
    # DIF DV (digital video).
    ('dv', (0, '\x1f\x07\x00')),
    ('swf', (0, ('FWS', 'CWS', 'ZWS'), 3, tuple(chr(c) for c in xrange(1, 40)))),
    ('ivf', (0, 'DKIF\0\0 \0')),

    # Video (single elementary stream, no audio).

    ('mpeg-video', (0, '\0\0\1', 3, ('\xb3', '\xb0', '\xb5'), 9, lambda header: (header[3] != '\xb0' or header[5 : 9] == '\0\0\1\xb5', 0))),
    # TODO(pts): Add 'mpeg-pes', it starts with: '\0\0\1' + [\xc0-\xef\xbd]. mpeg-pes in mpeg-ts has more sids (e.g. 0xfd for AC3 audio).
    ('h264', (0, ('\0\0\0\1', '\0\0\1\x09', '\0\0\1\x27', '\0\0\1\x47', '\0\0\1\x67'), 128, lambda header: adjust_confidence(400, count_is_h264(header)))),
    ('h265', (0, ('\0\0\0\1\x46', '\0\0\0\1\x40', '\0\0\0\1\x42', '\0\0\1\x46\1', '\0\0\1\x40\1', '\0\0\1\x42\1'), 128, lambda header: adjust_confidence(500, count_is_h265(header)))),
    ('vp8', (3, '\x9d\x01\x2a', 10, lambda header: (is_vp8(header), 150))),
    ('vp9', (0, ('\x80\x49\x83\x42', '\x81\x49\x83\x42', '\x82\x49\x83\x42', '\x83\x49\x83\x42', '\xa0\x49\x83\x42', '\xa1\x49\x83\x42', '\xa2\x49\x83\x42', '\xa3\x49\x83\x42', '\x90\x49\x83\x42', '\x91\x49\x83\x42', '\x92\x49\x83\x42', '\x93\x49\x83\x42', '\xb0\x24\xc1\xa1', '\xb0\xa4\xc1\xa1', '\xb1\x24\xc1\xa1', '\xb1\xa4\xc1\xa1'), 10, lambda header: (is_vp9(header), 20))),
    ('av1', (0, '\x12\0\x0a', 3, tuple(chr(c) for c in xrange(4, 128)))),
    ('dirac', (0, 'BBCD\0\0\0\0', 9, '\0\0\0\0', 14, lambda header: (is_dirac(header), 10))),
    ('theora', (0, '\x80theora', 7, ('\0', '\1', '\2', '\3', '\4', '\5', '\6', '\7'))),
    ('daala', (0, '\x80daala', 7, ('\0', '\1', '\2', '\3', '\4', '\5', '\6', '\7'))),
    ('yuv4mpeg2', (0, 'YUV4MPEG2 ')),
    ('realvideo', (0, 'VIDO', 8, lambda header: ((header[4 : 6] == 'RV' and header[6] in '123456789T' and header[7].isalnum()) or header[4 : 8] == 'CLV1', 350))),
    ('realvideo-size', (0, '\0\0\0', 4, 'VIDO', 12, lambda header: (ord(header[3]) >= 32 and (header[8 : 10] == 'RV' and header[10] in '123456789T' and header[11].isalnum()) or header[8 : 12] == 'CLV1', 400))),
    ('mng', (0, '\212MNG\r\n\032\n')),
    # Autodesk Animator FLI or Autodesk Animator Pro flc.
    # http://www.drdobbs.com/windows/the-flic-file-format/184408954
    ('flic', (4, ('\x12\xaf', '\x11\xaf'), 12, '\x08\0', 14, ('\3\0', '\0\0'))),

    # Image.
    #
    # TODO(pts): Add detection and analyzing of OpenEXR, DNG, CR2.
    # XnView MP supports even more: https://www.xnview.com/en/xnviewmp/#formats
    # IrfanView also supports a lot: https://www.irfanview.com/main_formats.htm

    ('gif', (0, 'GIF8', 4, ('7a', '9a'))),
    ('agif',),  # From 'gif'.
    # TODO(pts): Which JPEG marker can be header[3]? Typically it's '\xe0'.
    ('jpeg', (0, '\xff\xd8\xff')),
    ('png', (0, '\211PNG\r\n\032\n\0\0\0')),
    ('jng', (0, '\213JNG\r\n\032\n\0\0\0')),
    # JPEG reencoded by Dropbox lepton. Getting width and height is complicated.
    ('lepton', (0, '\xcf\x84', 2, ('\1', '\2'), 3, ('X', 'Y', 'Z'))),
    # Also includes 'nikon-nef' raw images.
    ('tiff', (0, ('MM\x00\x2a', 'II\x2a\x00'))),
    ('pnm', (0, 'P', 1, ('1', '4'), 2, ('\t', '\n', '\x0b', '\x0c', '\r', ' ', '#'))),
    ('pnm', (0, 'P', 1, ('2', '5'), 2, ('\t', '\n', '\x0b', '\x0c', '\r', ' ', '#'))),
    ('pnm', (0, 'P', 1, ('3', '6'), 2, ('\t', '\n', '\x0b', '\x0c', '\r', ' ', '#'))),
    ('xv-thumbnail', (0, 'P7 332\n')),
    # 392 is arbitrary, but since mpeg-ts has it, we can also that much.
    ('pam', (0, 'P7\n', 3, tuple('#\nABCDEFGHIJKLMNOPQRSTUVWXYZ'), 392, lambda header: adjust_confidence(400, count_is_pam(header)))),
    ('xbm', (0, '#define', 7, (' ', '\t'), 256, lambda header: adjust_confidence(800, count_is_xbm(header)))),  # '#define test_width 42'.
    ('xpm', (0, '#define', 7, (' ', '\t'), 256, lambda header: adjust_confidence(800, count_is_xpm1(header)))),  # '#define test_format 1'. XPM1.
    ('xpm', (0, '! XPM2', 6, ('\r', '\n'))),  # XPM2.
    ('xpm', (0, '/* XPM */', 9, ('\r', '\n'))),  # XPM3.
    ('lbm', (0, 'FORM', 8, ('ILBM', 'PBM '), 12, 'BMHD\0\0\0\x14')),
    ('djvu', (0, 'AT&TFORM', 12, 'DJV', 15, ('U', 'M'))),
    ('jbig2', (0, '\x97JB2\r\n\x1a\n')),
    # PDF-ready output of `jbig2 -p'.
    ('jbig2-pdf', (0, '\0\0\0\0\x30\0\1\0\0\0\x13', 19, '\0\0\0\0\0\0\0\0')),
    ('webp', (0, 'RIFF', 8, 'WEBPVP8', 15, (' ', 'L'), 26, lambda header: (is_webp(header), 400))),
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
    ('ras', (0, '\x59\xa6\x6a\x95')),
    ('gem', (0, GEM_NOSIG_HEADERS)),
    ('gem', (0, GEM_HYPERPAINT_HEADERS, 16, '\0\x80')),
    ('gem', (0, GEM_STTT_HEADERS, 16, 'STTT\0\x10')),
    ('gem', (0, GEM_XIMG_HEADERS, 16, 'XIMG\0\0')),
    # By PCPaint >=2.0 and Pictor.
    ('pcpaint-pic', (0, '\x34\x12', 6, '\0\0\0\0', 11, tuple('\xff123'), 13, tuple('\0\1\2\3\4'))),
    ('ico', (0, '\0\0\1\0', 4, tuple(chr(c) for c in xrange(1, 13)), 5, '\0', 10, ('\0', '\1', '\2', '\3', '\4'), 11, '\0', 12, ('\0', '\1', '\2', '\4', '\x08', '\x10', '\x18', '\x20'), 13, '\0')),
    # By AOL browser.
    ('art', (0, 'JG', 2, ('\3', '\4'), 3, '\016\0\0\0\0')),
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
    ('fuji-raf', (0, 'FUJIFILMCCD-RAW 020', 19, ('0', '1'), 20, 'FF383501')),
    ('jpegxl', (0, ('\xff\x0a'))),
    ('jpegxl-brunsli', (0, '\x0a\x04B\xd2\xd5N')),
    ('pik', (0, ('P\xccK\x0a', '\xd7LM\x0a'))),
    ('qtif', (0, ('\0', '\1'), 4, ('idat', 'iicc'))),
    ('qtif', (0, '\0\0\0', 4, 'idsc')),
    # JPEG2000 container format.
    ('jp2', (0, '\0\0\0\x0cjP  \r\n\x87\n\0\0\0', 28, lambda header: (is_jp2(header), 750))),
    # .mov preview image.
    ('pnot', (0, '\0\0\0\x14pnot', 12, '\0\0')),
    ('bmp', (0, 'BM', 6, '\0\0\0\0', 15, '\0\0\0', 26, lambda header: (len(header) >= 26 and 12 <= ord(header[14]) <= 127, 52))),
    ('pcx', (0, '\n', 1, ('\0', '\1', '\2', '\3', '\4', '\5'), 2, '\1', 3, ('\1', '\2', '\4', '\x08'))),
    # Not all tga (targa) files have 'TRUEVISION-XFILE.\0' footer.
    ('tga', (0, ('\0',) + tuple(chr(c) for c in xrange(30, 64)), 1, ('\0', '\1'), 2, ('\1', '\2', '\3', '\x09', '\x0a', '\x0b', '\x20', '\x21'), 16, ('\1', '\2', '\4', '\x08', '\x10', '\x18', '\x20'))),
    ('xwd', (0, '\0\0', 2, ('\0', '\1'), 4, '\0\0\0\6', 8, '\0\0\0', 11, tuple(chr(c) for c in xrange(17)), 12, '\0\0\0', 15, ('\1', '\2', '\3', '\4', '\5'), 16, '\0\0\0', 19, ('\0', '\1'))),
    ('xwd', (0, '\0\0', 2, ('\0', '\1'), 4, '\0\0\0\7', 8, '\0\0\0', 11, ('\0', '\1', '\2'), 12, '\0\0\0', 15, tuple(chr(c) for c in xrange(1, 33)))),
    ('sun-icon', (0, '/*', 2, (' ', '\t', '\r', '\n'), 21, lambda header: adjust_confidence(300, count_is_sun_icon(header)))),  # '/* Format_version=1,'.

    # * It's not feasible to detect
    #   http://justsolve.archiveteam.org/wiki/DEGAS_image , the signature is
    #   too short (2 bytes).
    # * It's not possible to detect CCITT Fax Group 3 (G3), it doesn't have a
    #   header. http://fileformats.archiveteam.org/wiki/CCITT_Group_3
    # * It's not possible to detect CCITT Fax Group 4 (G4), it doesn't have a
    #   header. http://fileformats.archiveteam.org/wiki/CCITT_Group_4

    # Audio.

    ('wav', (0, 'RIFF', 8, 'WAVE')),
    # https://en.wikipedia.org/wiki/ID3
    # http://id3.org/id3v2.3.0
    # ID3v1 is at the end of the file, so we don't care.
    # ID3v2 is at the start of the file, before the mpeg-adts frames.
    ('mp3-id3v2', (0, 'ID3', 10, lambda header: (len(header) >= 10 and ord(header[3]) < 10 and (ord(header[5]) & 7) == 0 and ord(header[6]) >> 7 == 0 and ord(header[7]) >> 7 == 0 and ord(header[8]) >> 7 == 0 and ord(header[9]) >> 7 == 0, 100))),
    # Also MPEG audio elementary stream. https://en.wikipedia.org/wiki/Elementary_stream
    ('mpeg-adts', (0, '\xff', 1, ('\xe2', '\xe3', '\xf2', '\xf3', '\xf4', '\xf5', '\xf6', '\xf7', '\xfa', '\xfb', '\xfc', '\xfd', '\xfe', '\xff', '\xf0', '\xf1', '\xf8', '\xf9'), 3, lambda header: (is_mpeg_adts(header), 30))),
    ('mp3',),  # From 'mpeg-adts'.
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

    # Document media and vector graphics.

    ('pdf', (0, '%PDF')),
    ('ps', (0, '%!PS-Adobe-', 11, ('1', '2', '3'), 12, '.')),
    # Bytes at offset 8 are numerator and denominator: struct.pack('>LL', 25400000, 473628672).
    ('dvi', (0, '\367', 1, ('\002', '\003'), 2, '\001\203\222\300\034;\0\0')),
    ('wmf', (0, '\xd7\xcd\xc6\x9a\0\0')),
    ('wmf', (0, ('\1\0\x09\0\0', '\2\0\x09\0\0'), 5, ('\1', '\3'), 16, '\0\0')),
    ('emf', (0, '\1\0\0\0', 5, '\0\0\0', 40, ' EMF\0\0\1\0', 58, '\0\0')),
    # TODO(pts): Detect <!--....--><svg ...> as format=svg (rather than format=html).
    ('svg', (0, '<svg', 4, XML_WHITESPACE_TAGEND)),
    ('svg', (0, '<svg:svg', 8, XML_WHITESPACE_TAGEND)),
    ('smil', (0, '<smil', 5, XML_WHITESPACE_TAGEND)),
    # https://fossies.org/linux/xfig/doc/FORMAT3.2
    # TODO(pts): For width= and height=, get paper size from line 5 in version 3.2 only.
    ('fig', (0, '#FIG ', 5, ('1', '2', '3'), 6, '.')),

    # Compressed archive.

    # '\6\6' is ZIP64.
    # Also Java jar and Android apk.
    ('zip', (0, 'PK', 2, ('\1\2', '\3\4', '\5\6', '\7\x08', '\6\6'))),
    ('zip', (0, 'PK00PK', 6, ('\1\2', '\3\4', '\5\6', '\7\x08', '\6\6'))),
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
    ('ar', (0, '!<arch>\n')),

    # Compressed single file.

    # http://fileformats.archiveteam.org/wiki/Gzip
    # https://wiki.alpinelinux.org/wiki/Alpine_package_format
    # Also .tar.gz and Alpine apk.
    ('gz', (0, '\037\213\010')),
    # http://fileformats.archiveteam.org/wiki/MSZIP
    ('mszip', (0, 'CK')),
    # http://fileformats.archiveteam.org/wiki/Bzip
    ('bzip', (0, 'BZ0')),
    ('bz2', (0, 'BZh')),
    # http://fileformats.archiveteam.org/wiki/Lzip
    # Uses LZMA.
    ('lzip', (0, 'LZIP')),
    # http://fileformats.archiveteam.org/wiki/Lzop
    ('lzop', (0, '\x89LZO\0\r\n\x1a\x0a')),
    ('xz', (0, '\xfd7zXZ\0')),
    # http://fileformats.archiveteam.org/wiki/LZMA_Alone
    ('lzma', (0, '\x5d\0\0', 12, ('\0', '\xff'))),
    # http://fileformats.archiveteam.org/wiki/Zlib
    # https://tools.ietf.org/html/rfc1950
    ('flate', (0, '\x78', 1, ('\x01', '\x5e', '\x9c', '\xda'))),
    ('flate-small-window', (0, ('\x08', '\x18', '\x28', '\x38', '\x48', '\x58', '\x68'), 1, ('\x01', '\x5e', '\x9c', '\xda'))),
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
    # https://github.com/google/brotli/issues/298
    # https://github.com/madler/brotli/blob/master/br-format-v3.txt
    ('brotli', (0, '\xce\xb2\xcf\x81')),  # .br

    # Non-compressed, non-media.

    ('appledouble', (0, '\0\5\x16\7\0', 6, lambda header: (header[5] <= '\3', 25))),
    ('dsstore', (0, '\0\0\0\1Bud1\0')),  # https://en.wikipedia.org/wiki/.DS_Store
    ('xml', (0, '<?xml', 5, ('\t', '\n', '\x0b', '\x0c', '\r', ' '))),
    ('php', (0, '<?', 2, ('p', 'P'), 6, ('\t', '\n', '\x0b', '\x0c', '\r', ' '), 5, lambda header: (header[:5].lower() == '<?php', 200))),
    # We could be more strict here, e.g. rejecting non-HTML docypes.
    # TODO(pts): Ignore whitespace in the beginning above.
    ('html', (0, '<', 15, lambda header: (header.startswith('<!--') or header[:15].lower() in ('<!doctype html>', '<!doctype html ') or header[:6].lower() in ('<html>', '<head>', '<body>'), 500))),
    # Contains thumbnails of multiple images files.
    # http://fileformats.archiveteam.org/wiki/PaintShop_Pro_Browser_Cache
    # pspbrwse.jbf
    # https://github.com/0x09/jbfinspect/blob/master/jbfinspect.c
    ('jbf', (0, 'JASC BROWS FILE\0')),
    ('java-class', (0, '\xca\xfe\xba\xbe')),
    # OLE compound file, including Thumbs.db
    # http://forensicswiki.org/wiki/OLE_Compound_File
    ('olecf', (0, ('\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1', '\x0e\x11\xfc\x0d\xd0\xcf\x11\x0e'))),
    ('avidemux-mpeg-index', (0, 'ADMY')),
    ('avidemux-project', (0, '//AD')),
    # *** These modified files were found in JOE when it aborted on ...
    # *** JOE was aborted by UNIX signal ...
    ('deadjoe', (0, '\n*** ', 5, ('Thes', 'JOE '))),
    ('elf', (0, '\x7fELF', 4, ('\1', '\2'), 5, ('\1', '\2'), 6, '\1')),
    # Filename extension: .mfo
    # Example: output of pymediafileinfo and media_scan.py.
    ('fileinfo', (0, 'format=')),
    ('unixscript', (4, lambda header: (header.startswith('#!/') or header.startswith('#! /'), 350))),
    # Windows .cmd or DOS .bat file. Not all such file have a signature though.
    ('windows-cmd', (0, '@', 1, ('e', 'E'), 11, lambda header: (header[:11].lower() == '@echo off\r\n', 900))),
    ('exe', (0, 'MZ', 64, lambda header: (len(header) >= 64, 1))),
    ('dotnetexe',),  # From 'exe'.
    ('winexe',),  # From 'exe'.
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
    ('?-zeros8', (0, '\0' * 8)),
    ('?-zeros16', (0, '\0' * 16)),
    ('?-zeros32', (0, '\0' * 32)),
    ('?-zeros64', (0, '\0' * 64)),  # ``ISO 9660 CD-ROM filesystem data'' typically ends up in this format, because it starts with 40960 '\0' bytes (unless bootable).
)

HEADER_SIZE_LIMIT = 512


class FormatDb(object):
  __slots__ = ('formats_by_prefix', 'header_preread_size', 'formats')

  def __init__(self, format_items):
    # It's OK to have duplicate, e.g. 'cue'.
    #if len(dict(format_items)) != len(format_items):
    #  raise ValueError('Duplicate key in format_items.')
    hps = 0
    fbp = [{} for i in xrange(5)]
    for format_spec in format_items:
      if len(format_spec) == 1:
        continue  # Indicates that analyze_* can generate this format.
      format, spec = format_spec
      size, pattern = spec[0], spec[1]
      prefixes = ('',)
      # TODO(pts): Check that size==0 is first.
      # TODO(pts): Do smarter prefix selection.
      if isinstance(pattern, str):
        if size == 0:
          prefixes = (pattern,)
      elif isinstance(pattern, tuple):
        if size == 0:
          prefixes = pattern
      for prefix in prefixes:
        i = min(4, len(prefix))
        prefix2 = prefix[:i]
        fbp2 = fbp[i]
        if prefix2 in fbp2:
          fbp2[prefix2].append(format_spec)
        else:
          fbp2[prefix2] = [format_spec]
      for i in xrange(0, len(spec), 2):
        size, pattern = spec[i], spec[i + 1]
        if isinstance(pattern, str):
          hps = max(hps, size + len(pattern))
        elif isinstance(pattern, tuple):
          assert pattern, 'Empty pattern tuple.'
          assert len(set(len(s) for s in pattern)) == 1, (
              'Non-uniform pattern choice sizes for %s: %r' %
              (format, pattern))
          hps = max(hps, size + len(pattern[0]))
        else:
          hps = max(hps, size)
    self.header_preread_size = hps  # Typically 64, we have 392.
    assert hps <= HEADER_SIZE_LIMIT, 'Header too long.'
    self.formats_by_prefix = fbp
    self.formats = frozenset(item[0] for item in FORMAT_ITEMS)


FORMAT_DB = FormatDb(FORMAT_ITEMS)

# import math; print ["\0"+"".join(chr(int(100. / 8 * math.log(i) / math.log(2))) for i in xrange(1, 1084))]'
LOG2_SUB = '\0\0\x0c\x13\x19\x1d #%\')+,./0234566789::;<<==>??@@AABBBCCDDEEEFFFGGGHHHIIIJJJKKKKLLLLMMMMNNNNOOOOOPPPPPQQQQQRRRRRSSSSSSTTTTTTUUUUUUVVVVVVVWWWWWWWXXXXXXXXYYYYYYYYZZZZZZZZ[[[[[[[[[\\\\\\\\\\\\\\\\\\]]]]]]]]]]^^^^^^^^^^^___________```````````aaaaaaaaaaaaabbbbbbbbbbbbbcccccccccccccdddddddddddddddeeeeeeeeeeeeeeeeffffffffffffffffggggggggggggggggghhhhhhhhhhhhhhhhhhiiiiiiiiiiiiiiiiiiiijjjjjjjjjjjjjjjjjjjjkkkkkkkkkkkkkkkkkkkkklllllllllllllllllllllllmmmmmmmmmmmmmmmmmmmmmmmmnnnnnnnnnnnnnnnnnnnnnnnnnnoooooooooooooooooooooooooopppppppppppppppppppppppppppppqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrsssssssssssssssssssssssssssssssssttttttttttttttttttttttttttttttttttttuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{|||||||||||||||||||||||||||||||||||||||||||||||||||||||}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}~'
assert len(LOG2_SUB) == 1084, 'Unexpected LOG2_SUB size.'


def detect_format(f):
  """Detects the file format.

  Args:
    f: A .read(...) method of a file-like object, a file-like object, or
        an str.
  Returns:
    (format, header), where format is a non-empty string (can be '?'),
    header is a string containing the prefix of f, and exactly this many
    bytes were read from f.
  """
  format_db, log2_sub, lmi = FORMAT_DB, LOG2_SUB, len(LOG2_SUB) - 1
  size = format_db.header_preread_size
  if isinstance(f, (str, buffer)):
    header = f[:size]
  elif callable(getattr(f, 'read', None)):
    header = f.read(size)
  else:
    header = f(size)
  if not isinstance(header, str):
    raise TypeError
  matches = []
  fbp = format_db.formats_by_prefix
  for j in xrange(min(len(header), 4), -1, -1):
    for format, spec in fbp[j].get(header[:j], ()):
      assert isinstance(spec, tuple), 'spec must be tuple.'
      confidence = 0
      i = 0
      prev_ofs = 0
      while i < len(spec):
        ofs = spec[i]
        assert isinstance(ofs, int), 'ofs must be int.'
        pattern = spec[i + 1]
        if isinstance(pattern, str):
          assert ofs + len(pattern) <= HEADER_SIZE_LIMIT, 'Header too long.'
          if header[ofs : ofs + len(pattern)] != pattern:
            break
          confidence += 100 * len(pattern) - 10 * min(ofs - prev_ofs, 10)
          prev_ofs = ofs + len(pattern)
        elif isinstance(pattern, tuple):
          # TODO(pts): Check that each str in pattern has the same len.
          header_sub = header[ofs : ofs + len(pattern[0])]
          assert ofs + len(pattern[0]) <= HEADER_SIZE_LIMIT, 'Header too long.'
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
          assert ofs <= HEADER_SIZE_LIMIT, 'Header too long.'
          is_matching, cadd = pattern(header)
          if not is_matching:
            break
          confidence += cadd
        else:
          raise AssertionError(type(pattern))
        i += 2
      if i == len(spec):  # The spec has matched.
        matches.append((confidence, format))
  if matches:
    matches.sort()  # By (confidence, format) ascending.
    format = matches[-1][1]
  else:
    format = '?'
  return format, header


def copy_info_from_tracks(info):
  """Copies fields from info['tracks'] to top-level in info."""

  # Copy audio fields.
  audio_track_infos = [track for track in info['tracks']
                       if track['type'] == 'audio']
  if len(audio_track_infos) == 1:
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


def _analyze_detected_format(f, info, header, file_size_for_seek):
  prebuf = [0, header]
  header = ''

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

  format = info['format']
  if format == 'flv':
    analyze_flv(fread, info, fskip)
  elif format == 'mkv':
    analyze_mkv(fread, info, fskip)
  elif format == 'asf':
    analyze_asf(fread, info, fskip)
  elif format == 'avi':
    analyze_avi(fread, info, fskip)
  elif format == 'mpeg-ps':
    analyze_mpeg_ps(fread, info, fskip)
  elif format == 'mpeg-ts':
    analyze_mpeg_ts(fread, info, fskip)
  elif format == 'mpeg-video':
    analyze_mpeg_video(fread, info, fskip)
  elif format == 'mpeg-adts':
    # Can change info['format'] = 'mp3'.
    analyze_mpeg_adts(fread, info, fskip)
  elif format == 'mp3-id3v2':
    analyze_id3v2(fread, info, fskip)
  elif format == 'h264':
    analyze_h264(fread, info, fskip)
  elif format == 'h265':
    analyze_h265(fread, info, fskip)
  elif format == 'vp8':
    analyze_vp8(fread, info, fskip)
  elif format == 'vp9':
    analyze_vp9(fread, info, fskip)
  elif format == 'av1':
    analyze_av1(fread, info, fskip)
  elif format == 'dirac':
    analyze_dirac(fread, info, fskip)
  elif format == 'theora':
    analyze_theora(fread, info, fskip)
  elif format == 'daala':
    analyze_daala(fread, info, fskip)
  elif format == 'yuv4mpeg2':
    analyze_yuv4mpeg2(fread, info, fskip)
  elif format in ('realvideo', 'realvideo-size'):
    analyze_realvideo(fread, info, fskip)
  elif format == 'wav':
    analyze_wav(fread, info, fskip)
  elif format == 'gif':
    analyze_gif(fread, info, fskip)
  elif format == 'jpeg':
    info['codec'] = 'jpeg'
    info['width'], info['height'] = get_jpeg_dimensions(fread)
  elif format == 'png':
    analyze_png(fread, info, fskip)
  elif format == 'jng':
    analyze_jng(fread, info, fskip)
  elif format == 'lbm':
    analyze_lbm(fread, info, fskip)
  elif format == 'pcx':
    analyze_pcx(fread, info, fskip)
  elif format == 'xbm':
    analyze_xbm(fread, info, fskip)
  elif format == 'xpm':
    analyze_xpm(fread, info, fskip)
  elif format == 'xcf':
    analyze_xcf(fread, info, fskip)
  elif format == 'psd':
    analyze_psd(fread, info, fskip)
  elif format == 'tga':
    analyze_tga(fread, info, fskip)
  elif format == 'tiff':
    analyze_tiff(fread, info, fskip)
  elif format in ('pnm', 'xv-thumbnail'):
    analyze_pnm(fread, info, fskip)
  elif format == 'pam':
    analyze_pam(fread, info, fskip)
  elif format == 'ps':
    analyze_ps(fread, info, fskip)
  elif format == 'miff':
    analyze_miff(fread, info, fskip)
  elif format in ('jbig2', 'jbig2-pdf'):
    analyze_jbig2(fread, info, fskip)
  elif format == 'djvu':
    analyze_djvu(fread, info, fskip)
  elif format == 'art':
    analyze_art(fread, info, fskip)
  elif format == 'ico':
    analyze_ico(fread, info, fskip)
  elif format == 'webp':
    analyze_webp(fread, info, fskip)
  elif format == 'jpegxr':
    analyze_jpegxr(fread, info, fskip)
  elif format == 'flif':
    analyze_flif(fread, info, fskip)
  elif format == 'fuif':
    analyze_fuif(fread, info, fskip)
  elif format == 'bpg':
    analyze_bpg(fread, info, fskip)
  elif format == 'flac':
    analyze_flac(fread, info, fskip)
  elif format == 'ape':
    analyze_ape(fread, info, fskip)
  elif format == 'vorbis':
    analyze_vorbis(fread, info, fskip)
  elif format == 'oggpcm':
    analyze_oggpcm(fread, info, fskip)
  elif format == 'opus':
    analyze_opus(fread, info, fskip)
  elif format == 'speex':
    analyze_speex(fread, info, fskip)
  elif format == 'realaudio':
    analyze_realaudio(fread, info, fskip)
  elif format == 'ralf':
    analyze_ralf(fread, info, fskip)
  elif format == 'lepton':
    info['codec'] = 'lepton'
  elif format == 'fuji-raf':
    info['codec'] = 'raw'
  elif format in ('flate', 'gz', 'zip'):
    info['codec'] = 'flate'
  elif format in ('xz', 'lzma'):
    info['codec'] = 'lzma'
  elif format in ('mp4', 'mp4-wellknown-brand', 'mov', 'mov-mdat', 'mov-small', 'mov-moov'):
    analyze_mp4(fread, info, fskip)
  elif format == 'swf':
    analyze_swf(fread, info, fskip)
  elif format == 'ogg':
    analyze_ogg(fread, info, fskip)
  elif format == 'realmedia':
    analyze_realmedia(fread, info, fskip)
  elif format == 'pnot':
    analyze_pnot(fread, info, fskip)
  elif format == 'ac3':
    analyze_ac3(fread, info, fskip)
  elif format == 'dts':
    analyze_dts(fread, info, fskip)
  elif format == 'jp2':
    if len(fread(12)) != 12:
      raise ValueError('Too short for jp2 header.')
    analyze_mp4(fread, info, fskip)
  elif format == 'bmp':
    analyze_bmp(fread, info, fskip)
  elif format == 'flic':
    analyze_flic(fread, info, fskip)
  elif format == 'mng':
    analyze_mng(fread, info, fskip)
  elif format == 'exe':
    analyze_exe(fread, info, fskip)
  elif format in ('xml', 'svg'):
    analyze_xml(fread, info, fskip)  # Also generates format=svg and =smil.
  elif format == 'jpegxl-brunsli':
    analyze_brunsli(fread, info, fskip)
  elif format == 'jpegxl':
    analyze_jpegxl(fread, info, fskip)
  elif format == 'pik':
    analyze_pik(fread, info, fskip)
  elif format == 'qtif':
    analyze_qtif(fread, info, fskip)
  elif format == 'psp':
    analyze_psp(fread, info, fskip)
  elif format == 'ras':
    analyze_ras(fread, info, fskip)
  elif format == 'gem':
    analyze_gem(fread, info, fskip)
  elif format == 'pcpaint-pic':
    analyze_pcpaint_pic(fread, info, fskip)
  elif format == 'ivf':
    analyze_ivf(fread, info, fskip)
  elif format == 'wmf':
    analyze_wmf(fread, info, fskip)
  elif format == 'dvi':
    analyze_dvi(fread, info, fskip)
  elif format == 'emf':
    analyze_emf(fread, info, fskip)
  elif format == 'xwd':
    analyze_xwd(fread, info, fskip)
  elif format == 'sun-icon':
    analyze_sun_icon(fread, info, fskip)


def analyze(f, info=None, file_size_for_seek=None):
  """Detects file format, and gets media parameters in file f.

  For videos, info['tracks'] is a list with an item for each video or audio
  track (info['tracks'][...]['type'] in ('video', 'audio'). Presence and
  parameters of subtitle tracks are not reported.

  Args:
    f: File-like object with a .read(n) method and an optional .seek(n) method,
        should do buffering for speed, and must return exactly n bytes unless
        at EOF. Seeking will be avoided if possible.
    info: A dict to update with the info found, or None to create a new one.
    file_size_for_seek: None or an integer specifying the file size up to which
        it is OK to seek forward (fskip).
  Returns:
    The info dict.
  """
  if info is None:
    info = {}
  # Set it early, in case of an exception.
  info.setdefault('format', '?')
  format, header = detect_format(f)
  info['format'] = format
  try:
    _analyze_detected_format(f, info, header, file_size_for_seek)
  finally:
    if info.get('tracks'):
      copy_info_from_tracks(info)
  return info
