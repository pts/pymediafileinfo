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
            ('reserved0', 'reserved1', 'h263', 'screen', 'vp6',
             'vp6alpha', 'screen2', 'h264', 'u8', 'u9', 'u10',
             'u11', 'u12', 'u13', 'u14', 'u15')[video_codec_id])
        if video_codec_id ==  2:  # 'h263'.
          # 736 of 1531 .flv files have this codec.
          # See H263VIDEOPACKET in swf-file-format-spec.pdf, v19.
          # http://www.adobe.com/content/dam/Adobe/en/devnet/swf/pdf/swf-file-format-spec.pdf
          if len(data) < 9:
            raise ValueError('h263 video tag too short.')
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
              raise ValueError('h263 video tag too short.')
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
    'A_REAL/14_4': 'ra1',
    'A_REAL/28_8': 'ra2',
    'A_REAL/COOK': 'cook',
    'A_REAL/SIPR': 'sipro',
    'A_REAL/RALF': 'ra-lossless',
    'A_REAL/ATRC': 'altrac3',
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


def analyze_mp4(fread, info, fskip):
  # Documented here: http://xhelmboyx.tripod.com/formats/mp4-layout.txt
  # Also apple.com has some .mov docs.

  info['format'] = 'mov'
  info['brands'] = []
  info['tracks'] = []
  info['has_early_mdat'] = False

  # Empty or contains the type of the last hdlr.
  last_hdlr_type_list = []

  def process_box(size):
    """Dumps the box, and must read it (size bytes)."""
    xtype = xtype_path[-1]
    xytype = '/'.join(xtype_path[-2:])
    # Only the composites we care about.
    is_composite = xytype in (
        '/moov', '/jp2h', 'moov/trak', 'trak/mdia', 'mdia/minf', 'minf/stbl')
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
    if is_composite:
      if xytype == 'trak/mdia':
        if last_hdlr_type_list and 'd' not in last_hdlr_type_list:
          # stsd not found, still report the track.
          if last_hdlr_type_list[0] == 'vide':
            info['tracks'].append({'type': 'video'})
          elif last_hdlr_type_list[0] == 'soun':
            info['tracks'].append({'type': 'audio'})
        del last_hdlr_type_list[:]
      ofs_limit = size
      while ofs_limit > 0:  # Dump sequences of boxes inside.
        if ofs_limit < 8:
          raise ValueError('EOF in mp4 composite box size')
        size2, xtype2 = struct.unpack('>L4s', fread(8))
        if not (8 <= size2 <= ofs_limit):
          raise ValueError(
              'EOF in mp4 cmposite box, size=%d ofs_limit=%d' %
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
    if xtype == 'moov':  # All track parameters already found, stop looking.
      break
    if xtype == 'jp2h':  # All JP2 track parameters already found, stop looking.
      break


# --- Windows

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
    # TODO(pts): Add these.
    # 26 flv1
    # 13 ffds
    #  7 uldx
    #  6 pim1
    #  4 divf
    #  2 1cva
}


def get_windows_video_codec(codec):
  codec = codec.strip().lower()
  if codec == '\0\0\0\0':
    codec = 'raw'
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


# --- flac


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


def parse_h264_sps(
    data, expected_sps_id=0,
    _hextable='0123456789abcdef',
    _hex_to_bits='0000 0001 0010 0011 0100 0101 0110 0111 1000 1001 1010 1011 1100 1101 1110 1111'.split(),
    ):
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
  data = iter(''.join(  # Convert to binary.
      _hex_to_bits[_hextable.find(c)]
      for c in str(buffer(data, 3)).encode('hex')))
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


def parse_h265_sps(
    data,
    _hextable='0123456789abcdef',
    _hex_to_bits='0000 0001 0010 0011 0100 0101 0110 0111 1000 1001 1010 1011 1100 1101 1110 1111'.split()):
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
  bitstream = iter(''.join(  # Convert to binary.
      _hex_to_bits[_hextable.find(c)]
      for c in data[:165].encode('hex')))
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
  elif header[:4] == '\xff\x1f\x00\xe8' and 4 <= ord(header[5]) <= 7:
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


def parse_mpeg_video_mpeg4_video_object_layer_start(
    data, profile_level,
    _hextable='0123456789abcdef',
    _hex_to_bits='0000 0001 0010 0011 0100 0101 0110 0111 1000 1001 1010 1011 1100 1101 1110 1111'.split()):
  # https://gitlab.bangl.de/crackling-dev/android_frameworks_base/blob/a979ad6739d573b3823b0fe7321f554ef5544753/media/libstagefright/rtsp/APacketSource.cpp#L268
  # https://github.com/MediaArea/MediaInfoLib/blob/3f4052e3ad4de45f68e715eb6f5746e2ca626ffe/Source/MediaInfo/Video/File_Mpeg4v.cpp#L1
  # https://github.com/boundary/wireshark/blob/master/epan/dissectors/packet-mp4ves.c
  # https://www.google.com/search?q="video_object_layer_verid"
  # Extension of: https://www.itu.int/rec/dologin_pub.asp?lang=e&id=T-REC-H.263-200501-I!!PDF-E&type=items
  #
  # 24 bytes of bitstream is enough for the rest.
  bitstream = iter(''.join(  # Convert to binary.
      _hex_to_bits[_hextable.find(c)]
      for c in data[:24].encode('hex')))
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
    elif (header.startswith('\0\0\0\x0cjP  \r\n\x87\n\0\0\0') and
          header[16 : 24] == 'ftypjp2 '):
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
    if (header.startswith('\0\0\0\x0cjP  \r\n\x87\n\0\0\0') and
          header[16 : 24] == 'ftypjp2 '):
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
    return {'type': 'video', 'codec': 'bbc-dirac'}
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


def get_brn_dimensions(fread):
  """Returns (width, height) of a BRN file.

  Args:
    f: An object supporting the .read(size) method. Should be seeked to the
        beginning of the file.
    header: The first few bytes already read from fread.
  Returns:
    (width, height) pair of integers.
  Raises:
    ValueError: If not a BRN file or there is a syntax error in the BRN file.
    IOError: If raised by fread(size).
  """
  def read_all(size):
    data = fread(size)
    if len(data) != size:
      raise ValueError(
          'Short read in BRN: wanted=%d got=%d' % (size, len(data)))
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
  if len(data) < 7 or not data.startswith('\x0a\x04B\xd2\xd5N\x12'):
    raise ValueError('Not a BRN file.')

  header_remaining, _ = read_base128()
  width = height = None
  while header_remaining:
    if header_remaining < 0:
      raise ValueError('BRN header spilled over.')
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
    return width, height
  else:
    raise ValueError('Dimensions not found in BRN.')


def analyze_wav(fread, info, fskip):
  # This function doesn't do any file format detection.
  header = fread(36)
  if len(header) < 36:
    raise ValueError('Too short for wav.')
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
  # This function doesn't do any file format detection.
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


def analyze_bmp(fread, info, fskip):
  # This function doesn't do any file format detection.
  header = fread(26)
  if len(header) < 26:
    raise ValueError('Too short for bmp.')
  if not header.startswith('BM'):
    raise ValueError('bmp signature not found.')
  info['format'] = 'bmp'
  # TODO(pts): Detect codec other than 'uncompressed'.
  b = ord(header[14])
  if b in (12, 26) and len(header) >= 22:
    info['width'], info['height'] = struct.unpack(
        '<HH', header[18 : 22])
  elif b in (40, 124) and len(header) >= 26:
    info['width'], info['height'] = struct.unpack(
        '<LL', header[18 : 26])


def analyze_flic(fread, info, fskip):
  # This function doesn't do any file format detection.
  header = fread(16)
  if len(header) < 16:
    raise ValueError('Too short for flic.')
  info['format'] = 'flic'
  if header[4] == '\x12':
    info['subformat'] = 'flc'
  else:
    info['subformat'] = 'fli'
  width, height = struct.unpack('<HH', header[8 : 12])
  video_track_info = {'type': 'video', 'codec': 'rle'}
  info['tracks'] = [video_track_info]
  set_video_dimens(video_track_info, width, height)


def analyze_png(fread, info, fskip):
  # This function doesn't do any file format detection.
  header = fread(24)
  if len(header) < 24:
    raise ValueError('Too short for png.')
  info['format'] = 'png'
  info['codec'] = 'flate'
  if header[12 : 16] == 'IHDR':
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


def analyze_xpm(fread, info, fskip):
  header = fread(140)
  if len(header) < 9:
    raise ValueError('Too short for xpm.')
  if not header.startswith('/* XPM */'):
    raise ValueError('xpm signature not found.')
  info['format'] = 'xpm'
  info['codec'] = 'uncompressed'
  i = header.find('"', 9) + 1
  if i <= 0:
    raise ValueError('Missing quote in xpm.')
  j = i
  while i < len(header) and header[i].isdigit():
    i += 1
  if i == j or i == len(header):
    raise ValueError('Bad xpm width.')
  width = int(header[j : i])
  if not header[i].isspace():
    raise ValueError('Bad xpm separator.')
  i += 1
  j = i
  while i < len(header) and header[i].isdigit():
    i += 1
  if i == j or i == len(header):
    raise ValueError('Bad xpm height.')
  height = int(header[j : i])
  if not header[i].isspace():
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
      info['format'] = 'pbm'
    elif header[1] in '25':
      info['format'] = 'pgm'
    else:
      info['format'] = 'ppm'
    if header[1] in '123':
      info['codec'] = 'rawascii'
    else:
      info['codec'] = 'raw'
  else:
    raise ValueError('pnm signature not found.')
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


def analyze_gif(fread, info, fskip):
  # This function doesn't do any file format detection.
  # Still short enough for is_animated_gif.
  header = fread(10)
  if len(header) < 10:
    raise ValueError('Too short for gif.')
  info['format'] = 'gif'
  info['codec'] = 'lzw'
  info['width'], info['height'] = struct.unpack('<HH', header[6 : 10])
  if is_animated_gif(fread, header):  # This may read the entire input.
    info['format'] = 'agif'


# --- File format detection for many file formats and getting media
# parameters for some.


def adjust_confidence(base_confidence, confidence):
  return (confidence, max(1, confidence - base_confidence))


MAX_CONFIDENCE = 100000

# TODO(pts): Static analysis: fail on duplicate format name.
# TODO(pts): Static analysis: autodetect collisions in string-only matchers.
# TODO(pts): Optimization: create prefix dicts (for 4 bytes and 8 bytes).
# TODO(pts): On multiple matches, use the one with largest confidence.
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
    # Can also be (new) .mov, .f4v etc. as a subformat.
    ('mp4', (0, '\0\0\0', 4, 'ftyp', 4, lambda header: (len(header) >= 4 and ord(header[3]) >= 16 and (ord(header[3]) & 3) == 0, 26))),
    # TODO(pts): Get media parameters.
    # https://en.wikipedia.org/wiki/Ogg#File_format
    # https://xiph.org/ogg/doc/oggstream.html
    # Vorbis: identification header in https://xiph.org/vorbis/doc/Vorbis_I_spec.html
    # Theora: identification header in https://web.archive.org/web/20040928224506/http://www.theora.org/doc/Theora_I_spec.pdf
    # Can contain other codecs as well, each with codec-specific identification header.
    # ... e.g. Dirac https://en.wikipedia.org/wiki/Dirac_(video_compression_format)
    ('ogg', (0, 'OggS')),
    # Also 'wma' and 'wmv'.
    ('asf', (0, '0&\xb2u\x8ef\xcf\x11\xa6\xd9\x00\xaa\x00b\xcel')),
    ('avi', (0, 'RIFF', 8, 'AVI ')),
    # \1 is the version number, but there is no version later than 1 in 2017.
    ('flv', (0, 'FLV\1', 5, '\0\0\0\x09')),
    # Video CD (VCD).
    ('mpeg-cdxa', (0, 'RIFF', 8, 'CDXA')),
    ('mpeg-ps', (0, '\0\0\1\xba')),
    ('mpeg-ts', (0, ('\0', '\x47'), 392, lambda header: (is_mpeg_ts(header), 301))),
    ('rm', (0, '.RMF\0\0\0')),
    # .bup and .ifo files on a video DVD.
    ('dvd-bup', (0, 'DVDVIDEO-V', 10, ('TS', 'MG'))),
    # DIF DV (digital video).
    ('dv', (0, '\x1f\x07\x00')),
    ('mov-mdat', (4, 'mdat')),  # TODO(pts): Analyze mpeg inside.
    # This box ('wide', 'free' or 'skip'), after it's data, is immediately
    # followed by an 'mdat' box (typically 4-byte size, then 'mdat'), but we
    # can't detect 'mdat' here, it's too far for us.
    ('mov-skip', (0, '\0\0', 4, ('wide', 'free', 'skip'))),
    ('mov-moov', (0, '\0', 1, ('\0', '\1', '\2', '\3', '\4', '\5', '\6', '\7', '\x08'), 4, ('moov',))),
    ('swf', (0, ('FWS', 'CWS'))),

    # Video (single elementary stream, no audio).

    ('mpeg-video', (0, '\0\0\1', 3, ('\xb3', '\xb0', '\xb5'), 9, lambda header: (header[3] != '\xb0' or header[5 : 9] == '\0\0\1\xb5', 0))),
    # TODO(pts): Add 'mpeg-pes', it starts with: '\0\0\1' + [\xc0-\xef\xbd]. mpeg-pes in mpeg-ts has more sids (e.g. 0xfd for AC3 audio).
    ('h264', (0, ('\0\0\0\1', '\0\0\1\x09', '\0\0\1\x27', '\0\0\1\x47', '\0\0\1\x67'), 128, lambda header: adjust_confidence(4, count_is_h264(header)))),
    ('h265', (0, ('\0\0\0\1\x46', '\0\0\0\1\x40', '\0\0\0\1\x42', '\0\0\1\x46\1', '\0\0\1\x40\1', '\0\0\1\x42\1'), 128, lambda header: adjust_confidence(5, count_is_h265(header)))),
    ('mng', (0, '\212MNG\r\n\032\n')),
    # Autodesk Animator FLI or Autodesk Animator Pro flc.
    # http://www.drdobbs.com/windows/the-flic-file-format/184408954
    ('flic', (4, ('\x12\xaf', '\x11\xaf'), 12, '\x08\0', 14, ('\3\0', '\0\0'))),

    # Image.

    ('gif', (0, 'GIF8', 4, ('7a', '9a'))),
    # TODO(pts): Which JPEG marker can be header[3]? Typically it's '\xe0'.
    ('jpeg', (0, '\xff\xd8\xff')),
    ('png', (0, '\211PNG\r\n\032\n\0\0\0')),
    # JPEG reencoded by Dropbox lepton.
    ('lepton', (0, '\xcf\x84', 2, ('\1', '\2'), 3, ('X', 'Y', 'Z'))),
    # Also includes 'nikon-nef' raw images.
    ('tiff', (0, ('MM\x00\x2a', 'II\x2a\x00'))),
    ('pbm', (0, 'P', 1, ('1', '4'), 2, ('\t', '\n', '\x0b', '\x0c', '\r', ' ', '#'))),
    ('pgm', (0, 'P', 1, ('2', '5'), 2, ('\t', '\n', '\x0b', '\x0c', '\r', ' ', '#'))),
    ('ppm', (0, 'P', 1, ('3', '6'), 2, ('\t', '\n', '\x0b', '\x0c', '\r', ' ', '#'))),
    # sam2p can read it.
    ('xpm', (0, '/* XPM */')),
    # sam2p can read it.
    ('lbm', (0, 'FORM', 8, ('ILBM', 'PBM '), 12, 'BMHD\0\0\0\x14')),
    ('djvu', (0, 'AT&TFORM', 12, 'DJV', 15, ('U', 'I', 'M'))),
    # http://fileformats.archiveteam.org/wiki/JBIG2
    ('jbig2', (0, '\x97\x4A\x42\x32\x0D\x0A\x1A\x0A')),
    # By ImageMagick.
    ('miff', (0, 'id=ImageMagick')),
    # By GIMP.
    ('xcf', (0, 'gimp xcf ', 9, ('file', 'v001', 'v002', 'v003', 'v004', 'v005', 'v006', 'v007', 'v008', 'v009'))),
    # By Photoshop.
    ('psd', (0, '8BPS', 4, ('\0\1', '\0\2'), 6, '\0\0\0\0\0\0')),
    ('ico', (0, '\0\0\1\0', 5, '\0', 6, lambda header: (len(header) >= 6 and 1 <= ord(header[4]) <= 40, 240))),
    # By AOL browser.
    ('art', (0, 'JG\4\016\0\0\0\0')),
    # https://libopenraw.freedesktop.org/wiki/Fuji_RAF/
    ('fuji-raf', (0, 'FUJIFILMCCD-RAW 020', 19, ('0', '1'), 20, 'FF383501')),
    ('brn', (0, '\x0a\x04B\xd2\xd5N\x12')),
    # JPEG2000 container format.
    ('jp2', (0, '\0\0\0\x0cjP  \r\n\x87\n')),
    # Seems to contain an image.
    ('pnot', (0, '\0\0\0', 4, 'pnot')),
    ('bmp', (0, 'BM', 6, '\0\0\0\0', 15, '\0\0\0', 26, lambda header: (len(header) >= 26 and 12 <= ord(header[14]) <= 127, 52))),
    ('pcx', (0, '\n', 1, ('\0', '\1', '\2', '\3', '\4', '\5'), 2, '\1', 3, ('\1', '\2', '\4', '\x08'))),
    # Unfortunately not all tga (targa) files have 'TRUEVISION-XFILE.\0'.
    ('tga', (0, tuple(chr(c) for c in xrange(30, 64)), 1, tuple(chr(c) for c in xrange(12)), 16, ('\0', '\1', '\2', '\3', '\4', '\5', '\6', '\7', '\x08', '\x30'))),

    # Audio.

    ('wav', (0, 'RIFF', 8, 'WAVE')),
    # https://en.wikipedia.org/wiki/ID3
    # http://id3.org/id3v2.3.0
    # ID3v1 is at the end of the file, so we don't care.
    # ID3v2 is at the start of the file, before the mpeg-adts frames.
    ('mp3-id3v2', (0, 'ID3', 10, lambda header: (len(header) >= 10 and ord(header[3]) < 10 and (ord(header[5]) & 7) == 0 and ord(header[6]) >> 7 == 0 and ord(header[7]) >> 7 == 0 and ord(header[8]) >> 7 == 0 and ord(header[9]) >> 7 == 0, 100))),
    # Also MPEG audio elementary stream. https://en.wikipedia.org/wiki/Elementary_stream
    ('mpeg-adts', (0, '\xff', 1, ('\xe2', '\xe3', '\xf2', '\xf3', '\xf4', '\xf5', '\xf6', '\xf7', '\xfa', '\xfb', '\xfc', '\xfd', '\xfe', '\xff', '\xf0', '\xf1', '\xf8', '\xf9'), 3, lambda header: (is_mpeg_adts(header), 30))),
    ('aac', (0, 'ADIF')),
    ('flac', (0, 'fLaC')),
    ('ac3', (0, '\x0b\x77', 7, lambda header: (is_ac3(header), 20))),
    ('dts', (0, ('\x7f\xfe\x80\x01', '\xfe\x7f\x01\x80', '\x1f\xff\xe8\x00', '\xff\x1f\x00\xe8'), 6, lambda header: (is_dts(header), 1))),
    ('ape', (0, 'MAC ')),

    # Document media.

    ('pdf', (0, '%PDF')),
    # TODO(pts): Get papar size (image dimensions) from %%BoundingBox.
    ('ps', (0, '%!PS-Adobe-', 11, ('1', '2', '3'), 12, '.')),
    # TODO(pts): 10 byte prefix? '\367\002\001\203\222\300\34;\0\0'.
    ('dvi', (0, '\367\002')),

    # Compressed file or archive.

    # '\6\6' is ZIP64.
    ('zip', (0, 'PK', 2, ('\1\2', '\3\4', '\5\6', '\7\x08', '\6\6'))),
    ('rar', (0, 'Rar!')),
    ('zpaq', (0, ('7kS', 'zPQ'), 4, lambda header: (header.startswith('7kSt') or (header.startswith('zPQ') and 1 <= ord(header[3]) <= 127), 52))),
    ('gz', (0, '\037\213\010')),
    ('bz2', (0, 'BZh')),
    ('lzip', (0, 'LZIP')),
    ('lzop', (0, '\x89LZO\0\r\n')),
    ('7z', (0, '7z\xbc\xaf\x27\x1c')),
    ('xz', (0, '\xfd7zXZ\0')),
    ('lzma', (0, '\x5d\0\0', 12, ('\0', '\xff'))),
    ('flate', (0, '\x78', 1, ('\x01', '\x5e', '\x9c', '\xda'))),

    # Non-compressed, non-media.

    ('appledouble', (0, '\0\5\x16\7\0', 6, lambda header: (header[5] <= '\3', 25))),
    ('dsstore', (0, '\0\0\0\1Bud1\0')),  # https://en.wikipedia.org/wiki/.DS_Store
    # Or DOS .bat file.
    ('windows-cmd', (0, '@', 1, ('e', 'E'), 9, lambda header: (header[:9].lower() == '@echo off', 700))),
    ('xml', (0, '<?xml', 4, ('\t', '\n', '\x0b', '\x0c', '\r', ' '))),
    ('php', (0, '<?', 2, ('p', 'P'), 6, ('\t', '\n', '\x0b', '\x0c', '\r', ' '), 5, lambda header: (header[:5].lower() == '<?php', 200))),
    # We could be more strict here, e.g. rejecting non-HTML docypes.
    # TODO(pts): Ignore whitespace in the beginning above.
    ('html', (0, '<', 15, lambda header: (header.startswith('<!--') or header[:15].lower() in ('<!doctype html>', '<!doctype html ') or header[:6].lower() in ('<html>', '<head>', '<body>'), 500))),
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
    ('exe', (0, 'MZ', 64, lambda header: (len(header) >= 64, 1))),
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
  __slots__ = ('formats_by_prefix', 'header_preread_size')

  def __init__(self, format_items):
    # It's OK to have duplicate, e.g. 'cue'.
    #if len(dict(format_items)) != len(format_items):
    #  raise ValueError('Duplicate key in format_items.')
    hps = 0
    fbp = [{} for i in xrange(5)]
    for format_spec in format_items:
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
    self.header_preread_size = hps  # Typically 64.
    assert hps <= HEADER_SIZE_LIMIT, 'Header too long.'
    self.formats_by_prefix = fbp


FORMAT_DB = FormatDb(FORMAT_ITEMS)

# import math; print ["\0"+"".join(chr(int(100. / 8 * math.log(i) / math.log(2))) for i in xrange(1, 1084))]'
LOG2_SUB = '\0\0\x0c\x13\x19\x1d #%\')+,./0234566789::;<<==>??@@AABBBCCDDEEEFFFGGGHHHIIIJJJKKKKLLLLMMMMNNNNOOOOOPPPPPQQQQQRRRRRSSSSSSTTTTTTUUUUUUVVVVVVVWWWWWWWXXXXXXXXYYYYYYYYZZZZZZZZ[[[[[[[[[\\\\\\\\\\\\\\\\\\]]]]]]]]]]^^^^^^^^^^^___________```````````aaaaaaaaaaaaabbbbbbbbbbbbbcccccccccccccdddddddddddddddeeeeeeeeeeeeeeeeffffffffffffffffggggggggggggggggghhhhhhhhhhhhhhhhhhiiiiiiiiiiiiiiiiiiiijjjjjjjjjjjjjjjjjjjjkkkkkkkkkkkkkkkkkkkkklllllllllllllllllllllllmmmmmmmmmmmmmmmmmmmmmmmmnnnnnnnnnnnnnnnnnnnnnnnnnnoooooooooooooooooooooooooopppppppppppppppppppppppppppppqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrsssssssssssssssssssssssssssssssssttttttttttttttttttttttttttttttttttttuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{|||||||||||||||||||||||||||||||||||||||||||||||||||||||}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}~'
assert len(LOG2_SUB) == 1084, 'Unexpected LOG2_SUB size.'


def detect_format(f):
  """Detects the file format.

  Returns:
    (format, header), where format is a non-empty string (can be '?'),
    header is a string containing the prefix of f, and exactly this many
    bytes were read from f.
  """
  format_db, log2_sub, lmi = FORMAT_DB, LOG2_SUB, len(LOG2_SUB) - 1
  header = f.read(format_db.header_preread_size)
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
  elif format == 'wav':
    analyze_wav(fread, info, fskip)
  elif format == 'gif':
    analyze_gif(fread, info, fskip)
  elif format == 'jpeg':
    info['codec'] = 'jpeg'
    info['width'], info['height'] = get_jpeg_dimensions(fread)
  elif format == 'png':
    analyze_png(fread, info, fskip)
  elif format == 'lbm':
    analyze_lbm(fread, info, fskip)
  elif format == 'pcx':
    analyze_pcx(fread, info, fskip)
  elif format == 'xpm':
    analyze_xpm(fread, info, fskip)
  elif format == 'xcf':
    analyze_xcf(fread, info, fskip)
  elif format == 'psd':
    analyze_psd(fread, info, fskip)
  elif format == 'tiff':
    analyze_tiff(fread, info, fskip)
  elif format in ('pbm', 'pgm', 'ppm'):
    analyze_pnm(fread, info, fskip)
  elif format == 'flac':
    analyze_flac(fread, info, fskip)
  elif format == 'ape':
    analyze_ape(fread, info, fskip)
  elif format == 'brn':
    info['codec'] = 'brn'
    info['width'], info['height'] = get_brn_dimensions(fread)
  elif format == 'lepton':
    info['codec'] = 'lepton'
  elif format == 'fuji-raf':
    info['codec'] = 'raw'
  elif format in ('flate', 'gz', 'zip'):
    info['codec'] = 'flate'
  elif format in ('xz', 'lzma'):
    info['codec'] = 'lzma'
  elif format in ('mp4', 'mov', 'mov-mdat', 'mov-small', 'mov-moov'):
    analyze_mp4(fread, info, fskip)
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
  elif format == 'exe':
    analyze_exe(fread, info, fskip)


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
