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


def analyze_flv(f, info, header=''):
  # by pts@fazekas.hu at Sun Sep 10 00:26:18 CEST 2017
  #
  # Documented here (starting on page 68, Annex E):
  # http://download.macromedia.com/f4v/video_file_format_spec_v10_1.pdf
  #

  def parse_h264_sps(
      data, expected, expected_sps_id,
      _hextable='0123456789abcdef',
      # TODO(pts): Precompute this, don't run it each time analyze_flv runs.
      _hex_to_bits='0000 0001 0010 0011 0100 0101 0110 0111 1000 1001 1010 1011 1100 1101 1110 1111'.split(),
      ):
    # Based on function read_seq_parameter_set_rbsp in
    # https://github.com/aizvorski/h264bitstream/blob/29489957c016c95b495f1cce6579e35040c8c8b0/h264_stream.c#L356
    # , except for the very first byte.
    #
    # The formula for width and height is based on:
    # https://stackoverflow.com/a/31986720/97248
    if len(data) < 5:
      raise ValueError('flv h264 avcc sps too short.')
    if data[0] != '\x67':  # nalu_type=7 nalu_reftype=3.
      raise ValueError('Bad flv h264 avcc sps type.')
    if not data[1 : 4].startswith(expected):
      raise ValueError('Unexpected start of sps.')
    if len(data) > 255:  # Typically just 22 bytes.
      raise ValueError('flv h264 avcc sps too long.')
    io = {}
    io['chroma_format'] = 1
    io['profile'] = ord(data[1])
    io['compatibility'] = ord(data[2])
    io['level'] = ord(data[3])
    io['residual_color_transform_flag'] = 0
    # TODO(pts): Maybe bit shifting is faster.
    data = iter(''.join(  # Convert to binary.
        _hex_to_bits[_hextable.find(c)]
        for c in str(buffer(data, 4)).encode('hex')))
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
      if io['sps_id'] != expected_sps_id:
        raise ValueError('Unexpected flv h264 avcc sps id: expected=%d, got=%d' %
                         (expecteD_sps_id, io['sps_id']))
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
        raise ValueError('Unknown flv h264 avcc sps pic_order_cnt_type: %d' %
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
        raise ValueError('Unknown flv h264 sps chroma_format: %d' % io['chroma_format'])
      io['height_in_mbs'] = (2 - io['frame_mbs_only_flag']) * io['height_in_map_units']
      io['width'] =  (io['width_in_mbs']  << 4) - io['sub_width_c']  * (io['crop_left'] + io['crop_right'])
      io['height'] = (io['height_in_mbs'] << 4) - io['sub_height_c'] * (2 - io['frame_mbs_only_flag']) * (io['crop_top'] + io['crop_bottom'])
      return io  # h264_sps_info.
    except StopIteration:
      raise ValueError('EOF in flv h264 avcc sps.')

  data = header
  if len(data) < 13:
    data += f.read(13 - len(data))
    if len(data) < 13:
      raise ValueError('Too short for flv.')
  elif len(data) != 13:
    raise AssertionError('Header too long for flv: %d' % len(data))

  if not data.startswith('FLV'):
    raise ValueError('flv signature not found.')
  info['type'] = 'flv'
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
    data = f.read(11)
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
      data = f.read(size)
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
      data = f.read(size)  # TODO(pts): Skip over most of the tag, save memory.
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
          if len(data) < 13:
            raise ValueError('EOF in flv h264 avcc sps size.')
          sps_size, = struct.unpack('>H', data[11 : 13])
          if 13 + sps_size > len(data):
            raise ValueError('EOF in flv h264 avcc sps.')
          h264_sps_info = parse_h264_sps(
              buffer(data, 13, sps_size), expected, 0)
          set_video_dimens(video_track_info,
                           h264_sps_info['width'], h264_sps_info['height'])
    elif xtype in (15, 18):
      # The script tag for YouTube .flv doesn't contain width and height.
      # There are width and height fields defined, they are just not filled
      # in many .flv files, so instead of using this data, we do codec-specific
      # video frame parsing above.
      # TODO(pts): Get more metadata from script.
      if size > 65535:  # TODO(pts): Estimate better.
        raise ValueError('Script tag unreasonably large: %d' % size)
      # The ScriptTagBody contains SCRIPTDATA encoded in the Action Message
      # Format (AMF), which is a compact binary format used to serialize
      # ActionScript object graphs. The specification for AMF0 is available
      # at:
      # http://opensource.adobe.com/wiki/display/blazeds/Developer+Documentation
      script_format = ('amf0', 'amf3')[xtype == 15]
      data = f.read(size)
      if len(data) != size:
        raise ValueError('EOF in tag data.')
    data = f.read(4)
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
    'V_UNCOMPRESSED': 'raw',
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


def analyze_mkv(f, info, fskip, header=''):
  # https://matroska.org/technical/specs/index.html

  # list so that inner functions can modify it.
  #
  # Invariant: ofs_list[0] == f.tell().
  #
  # We use ofs_list so that we don't have to call f.tell(). This is useful
  # for unseekable files.
  ofs_list = [len(header)]

  def read_n(n):
    data = f.read(n)
    ofs_list[0] += len(data)
    return data

  def read_id(f):
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

  def read_size(f):
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
      if not len(data) != 2:
        raise ValueError('EOF in mkv element size 9')
      return (b & 31) << 16 | struct.unpack('>H', data)[0]
    if b > 15:
      data = read_n(3)
      if not len(data) != 3:
        raise ValueError('EOF in mkv element size 10')
      return (b & 15) << 24 | struct.unpack('>L', '\0' + data)[0]
    if b > 7:
      data = read_n(4)
      if not len(data) != 4:
        raise ValueError('EOF in mkv element size 11')
      return (b & 7) << 32 | struct.unpack('>L', data)[0]
    if b > 3:
      data = read_n(5)
      if not len(data) != 5:
        raise ValueError('EOF in mkv element size 12')
      return (b & 3) << 40 | struct.unpack('>Q', '\0\0\0' + data)[0]
    if b > 1:
      data = read_n(6)
      if not len(data) != 6:
        raise ValueError('EOF in mkv element size 13')
      return (b & 1) << 48 | struct.unpack('>Q', '\0\0' + data)[0]
    raise ValueError('Invalid ID prefix: %d' % b)

  def read_id_skip_void(f):
    while 1:
      xid = read_id(f)
      if xid != '\xec':  # Void.
        return xid
      size = read_size(f)
      if not fskip(size):
        raise ValueError('EOF in Void element.')
      ofs_list[0] += size

  if len(header) > 4:
    # We can increase it by input buffering.
    raise AssertionError('Header too long for mkv: %d' % len(header))
  header += read_n(4 - len(header))
  if len(header) != 4:
    raise ValueError('Too short for mkv.')

  xid = header[:4]  # xid = read_id(f)
  if xid != '\x1a\x45\xdf\xa3':
    raise ValueError('mkv signature not found.')
  size = read_size(f)
  if size >= 256:
    raise ValueError('mkv header unreasonably large: %d' % size)
  header_end = ofs_list[0] + size
  info['format'] = 'mkv'
  while ofs_list[0] < header_end:
    xid = read_id_skip_void(f)
    size = read_size(f)
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
  xid = read_id_skip_void(f)
  if xid != '\x18\x53\x80\x67':  # Segment.
    raise ValueError('Expected Segment element, got: %s' % xid.encode('hex'))
  size = read_size(f)
  segment_end = ofs_list[0] + size
  info['tracks'] = []
  while ofs_list[0] < segment_end:
    xid = read_id_skip_void(f)
    size = read_size(f)
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
        xid = read_id_skip_void(f)
        size = read_size(f)
        if ofs_list[0] + size > tracks_end:
          raise ValueError('Size of in-Tracks element too large.')
        if xid != '\xae':  # Track.
          raise ValueError('Expected Track element, got: %s' % xid.encode('hex'))
        track_end = ofs_list[0] + size
        track_info = {}
        while ofs_list[0] < track_end:
          xid = read_id_skip_void(f)
          size = read_size(f)
          if ofs_list[0] + size > track_end:
            raise ValueError('Size of in-Track element too large.')
          if xid == '\xe0':  # Video.
            track_info['type'] = 'video'
            video_end = ofs_list[0] + size
            width = height = None
            while ofs_list[0] < video_end:
              xid = read_id_skip_void(f)
              size = read_size(f)
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
              xid = read_id_skip_void(f)
              size = read_size(f)
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


def analyze_mp4(f, info, fskip, header=''):
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
          raise ValueError('MP4E2')
        size2, xtype2 = struct.unpack('>L4s', f.read(8))
        if not (8 <= size2 <= ofs_limit):
          raise ValueError('MP4E3 size=%d ofs_limit=%d' % (size2, ofs_limit))
        ofs_limit -= size2
        xtype_path.append(xtype2)
        process_box(size2 - 8)
        xtype_path.pop()
    else:
      if size > 16383 or xtype in ('free', 'skip', 'wide'):
        if not fskip(size):
          raise ValueError('EOF while skipping mp4 box, xtype=%r' % xtype)
      else:
        data = f.read(size)
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
            raise ValueError('Found stsd without a hdlr first.')
          if len(data) < 8:
            raise ValueError('MP4E11')
          version_and_flags, count = struct.unpack('>LL', data[:8])
          if version_and_flags:
            raise ValueError('Bad mp4 stsd bad_version_and_flags=%d' % version_and_flags)
          i = 8
          while i < len(data):
            if len(data) - i < 8:
              raise ValueError('MP4E12')
            if not count:
              raise ValueError('MP4E13')
            # codec usually indicates the codec, e.g. 'avc1' for video and 'mp4a' for audio.
            ysize, codec = struct.unpack('>L4s', data[i : i + 8])
            codec = codec.strip().lower()  # Remove whitespace, e.g. 'raw'.
            if ysize < 8 or i + ysize > len(data):
              raise ValueError('MP4E14')
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
            raise ValueError('MP4E15')

  xtype_path = ['']
  toplevel_xtypes = set()
  while 1:
    if header:
      if len(header) > 8:
        raise AssertionError('Header too long for mp4: %d' % len(header))
      data = str(header)
      data += f.read(8 - len(data))
      header = ''
    else:
      data = f.read(8)
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
      data = f.read(8)
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
# !! TODO(pts): Fill this.
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
# !! TODO(pts): Find more.
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


def analyze_avi(f, info, fskip, header=''):
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
      data = f.read(8)
      if len(data) < 8:
        raise ValueError('EOF in avi %s chunk header.' % what)
      chunk_id, size = struct.unpack('<4sL', data)
      size += size & 1
      if ofs_limit is not None:
        ofs_limit -= 8 + size
      if (size >= 4 and (ofs_limit is None or ofs_limit + size >= 4) and
          chunk_id == 'LIST'):
        chunk_id = f.read(4) + '+'
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
        data = f.read(size)
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

  data = header
  if len(data) < 12:
    data += f.read(12 - len(data))
    if len(data) < 12:
      raise ValueError('Too short for avi.')
  elif len(data) != 12:
    raise AssertionError('Header too long for avi: %d' % len(data))
  riff_id, ofs_limit, avi_id = struct.unpack('<4sL4s', header)
  if riff_id != 'RIFF' or avi_id != 'AVI ':
    raise ValueError('avi signature not found.')
  info['type'] = 'avi'
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


def analyze_asf(f, info, fskip, header):
  if len(header) < 30:
    header += f.read(30 - len(header))
    if len(header) < 30:
      raise ValueError('Too short for asf.')
  if len(header) > 30:
    raise AssertionError('Header too long for asf: %d' % len(header))
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
    data = f.read(24)
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
      data = f.read(size)
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


def analyze_flac(f, info, header):
  if len(header) < 5:
    header += f.read(5 - len(header))
    if len(header) < 5:
      raise ValueError('Too short for flac.')
  if not header.startswith('fLaC'):
    raise ValueError('flac signature not found.')
  info['format'] = 'flac'
  if len(header) > 5:
    raise AssertionError('Header too long for flac: %d' % len(header))
  if header[4] not in '\0\x80':
    raise AssertionError('STREAMINFO metadata block expected in flac.')
  size = f.read(3)
  if len(size) != 3:
    raise ValueError('EOF in flac STREAMINFO metadata block size.')
  size, = struct.unpack('>L', '\0' + size)
  if not 34 <= size <= 255:
    raise ValueError(
        'Unreasonable size of flac STREAMINFO metadata block: %d' % size)
  data = f.read(18)
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


# --- Image file formats.


def is_animated_gif(f, header='', do_read_entire_file=False):
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
    IOError: If raised by f.read(size).
  """

  def read_all(f, size):
    data = f.read(size)
    if len(data) != size:
      raise ValueError(
          'Short read in GIF: wanted=%d got=%d' % (size, len(data)))
    return data

  if len(header) < 13:
    header += f.read(13 - len(header))
  elif len(header) > 13:
    raise AssertionError('Header too long for GIF: %d' % len(header))
  if len(header) < 13 or not (
      header.startswith('GIF87a') or header.startswith('GIF89a')):
    raise ValueError('Not a GIF file.')
  pb = ord(header[10])
  if pb & 128:  # Global Color Table present.
    read_all(f, 6 << (pb & 7))  # Skip the Global Color Table.
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
    b = ord(read_all(f, 1))
    if b == 0x3B:  # End of file.
      break
    elif b == 0x21:  # Extension introducer.
      b = ord(read_all(f, 1))
      if b == 0xff:  # Application extension.
        ext_id_size = ord(read_all(f, 1))
        ext_id = read_all(f, ext_id_size)
        ext_data_size = ord(read_all(f, 1))
        ext_data = read_all(f, ext_data_size)
        data_size = ord(read_all(f, 1))
        while data_size:
          read_all(f, data_size)
          data_size = ord(read_all(f, 1))
      else:
        # TODO(pts): AssertionError: Unknown extension: 0x01; in badgif1.gif
        if b not in (0xf9, 0xfe):
          raise ValueError('Unknown GIF extension type: 0x%02x' % b)
        ext_data_size = ord(read_all(f, 1))
        if b == 0xf9:  # Graphic Control extension.
          if ext_data_size != 4:
            raise ValueError(
                'Bad ext_data_size for GIF GCE: %d' % ext_data_size)
        ext_data = read_all(f, ext_data_size)
        data_size = ord(read_all(f, 1))
        if b == 0xf9:
          if data_size != 0:
            raise ValueError('Bad data_size for GIF GCE: %d' % data_size)
        while data_size:
          read_all(f, data_size)
          data_size = ord(read_all(f, 1))
    elif b == 0x2C:  # Image Descriptor.
      frame_count += 1
      if frame_count > 1 and not do_read_entire_file:
        return True
      read_all(f, 8)
      pb = ord(read_all(f, 1))
      if pb & 128:  # Local Color Table present.
        read_all(f, 6 << (pb & 7))  # Skip the Local Color Table.
      read_all(f, 1)  # Skip LZW minimum code size.
      data_size = ord(read_all(f, 1))
      while data_size:
        read_all(f, data_size)
        data_size = ord(read_all(f, 1))
    else:
      raise ValueError('Unknown GIF block type: 0x%02x' % b)
  if frame_count <= 0:
    raise ValueError('No frames in GIF file.')
  return frame_count > 1


def get_jpeg_dimensions(f, header=''):
  """Returns (width, height) of a JPEG file.

  Args:
    f: An object supporting the .read(size) method. Should be seeked to the
        beginning of the file.
    header: The first few bytes already read from f.
  Returns:
    (width, height) pair of integers.
  Raises:
    ValueError: If not a JPEG file or there is a syntax error in the JPEG file.
    IOError: If raised by f.read(size).
  """
  # Implementation based on pts-qiv
  #
  # A typical JPEG file has markers in these order:
  #   d8 e0_JFIF e1 e1 e2 db db fe fe c0 c4 c4 c4 c4 da d9.
  #   The first fe marker (COM, comment) was near offset 30000.
  # A typical JPEG file after filtering through jpegtran:
  #   d8 e0_JFIF fe fe db db c0 c4 c4 c4 c4 da d9.
  #   The first fe marker (COM, comment) was at offset 20.

  def read_all(f, size):
    data = f.read(size)
    if len(data) != size:
      raise ValueError(
          'Short read in JPEG: wanted=%d got=%d' % (size, len(data)))
    return data

  data = header
  if len(data) < 4:
    data += f.read(4 - len(data))
  elif len(data) > 4:
    raise AssertionError('Header too long for JPEG: %d' % len(data))
  if len(data) < 4 or not data.startswith('\xff\xd8\xff'):
    raise ValueError('Not a JPEG file.')
  m = ord(data[3])
  while 1:
    while m == 0xff:  # Padding.
      m = ord(read_all(f, 1))
    if m in (0xd8, 0xd9, 0xda):
      # 0xd8: SOI unexpected.
      # 0xd9: EOI unexpected before SOF.
      # 0xda: SOS unexpected before SOF.
      raise ValueError('Unexpected marker: 0x%02x' % m)
    ss, = struct.unpack('>H', read_all(f, 2))
    if ss < 2:
      raise ValueError('Segment too short.')
    ss -= 2
    if 0xc0 <= m <= 0xcf and m not in (0xc4, 0xc8, 0xcc):  # SOF0 ... SOF15.
      if ss < 5:
        raise ValueError('SOF segment too short.')
      height, width = struct.unpack('>xHH', read_all(f, 5))
      return width, height
    read_all(f, ss)

    # Read next marker to m.
    m = read_all(f, 2)
    if m[0] != '\xff':
      raise ValueError('Marker expected.')
    m = ord(m[1])
  raise AssertionError('Internal JPEG parser error.')


def get_brn_dimensions(f, header=''):
  """Returns (width, height) of a BRN file.

  Args:
    f: An object supporting the .read(size) method. Should be seeked to the
        beginning of the file.
    header: The first few bytes already read from f.
  Returns:
    (width, height) pair of integers.
  Raises:
    ValueError: If not a BRN file or there is a syntax error in the BRN file.
    IOError: If raised by f.read(size).
  """
  def read_all(f, size):
    data = f.read(size)
    if len(data) != size:
      raise ValueError(
          'Short read in BRN: wanted=%d got=%d' % (size, len(data)))
    return data

  def read_base128(f):
    shift, result, c = 0, 0, 0
    while 1:
      b = f.read(1)
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

  data = header
  if len(data) < 7:
    data += f.read(7 - len(data))
  elif len(data) > 7:
    raise AssertionError('Header too long for BRN: %d' % len(data))
  if len(data) < 7 or not data.startswith('\x0a\x04B\xd2\xd5N\x12'):
    raise ValueError('Not a BRN file.')

  header_remaining, _ = read_base128(f)
  width = height = None
  while header_remaining:
    if header_remaining < 0:
      raise ValueError('BRN header spilled over.')
    marker = ord(read_all(f, 1))
    header_remaining -= 1
    if marker & 0x80 or marker & 0x5 or marker <= 2:
      raise ValueError('Invalid marker.')
    if marker == 0x8:
      if width is not None:
        raise ValueError('Multiple width.')
      width, c = read_base128(f)
      header_remaining -= c
    elif marker == 0x10:
      if height is not None:
        raise ValueError('Multiple height.')
      height, c = read_base128(f)
      header_remaining -= c
    else:
      val, c = read_base128(f)
      header_remaining -= c
      if (marker & 7) == 2:
        read_all(f, val)
        header_remaining -= val
  if width is not None and height is not None:
    return width, height
  else:
    raise ValueError('Dimensions not found in BRN.')


def is_html(data):
  data = data[:256].lstrip().lower()
  return (data.startswith('<!--') or
          data.startswith('<html>') or
          data.startswith('<head>') or
          data.startswith('<body>') or
          data.startswith('<!doctype html ') or
          data.startswith('<!doctype html>'))


# ---

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
      elif key == 'type':
        if value == 'audio':
          continue
        key = 'atype'
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


# --- File format detection for many file formats and getting media
# parameters for some.


def detect(f, info=None, is_seek_ok=False):
  """Detects file format, and gets media parameters in file f.

  For videos, info['tracks'] is a list with an item for each video or audio
  track (info['tracks'][...]['type'] in ('video', 'audio'). Presence and
  parameters of subtitle tracks are not reported.

  Args:
    f: File-like object with a .read(n) method and an optional .seek(n) method,
        should do buffering for speed, and must return exactly n bytes unless
        at EOF. Seeking will be avoided if possible.
    info: A dict to update with the info found, or None.
    is_seek_ok: Boolean indicating whether seeking in f is OK. Even if true,
      but the f doesn't support seeking, detect still works fine. Seeking is
      only used for skipping ahead a large number of bytes.
  Returns:
    The info dict.
  """
  if info is None:
    info = {}
  if 'f' not in info and getattr(f, 'name', None):
    info['f'] = f.name.replace('\n', '{\\n}')
  file_size_for_seek = None
  if is_seek_ok:
    try:
      f.seek(0, 2)
      info['size'] = file_size_for_seek = int(f.tell())
    except (IOError, OSError, AttributeError):
      pass
    if info.get('size'):
      f.seek(0)  # Can raise IOError, which we propagate.
  if file_size_for_seek is None:
    def fskip(size):
      """Returns bool indicating whther f was long enough."""
      while size >= 32768:
        if len(f.read(32768)) != 32768:
          return False
        size -= 32768
      return size == 0 or len(f.read(size)) == size
  else:
    def fskip(size, file_size=file_size_for_seek):
      """Returns bool indicating whther f was long enough."""
      if size < 32768:
        data = f.read(size)
        return len(data) == size
      else:
        f.seek(size, 1)
        return f.tell() <= file_size

  # Set it early, in case of an exception.
  info.setdefault('format', '?')
  # We can't read more than 4 bytes here, analyze_mkv would fail.
  header = f.read(4)
  if not header:
    info['format'] = 'empty'
  elif len(header) < 4:
    info['format'] = 'short%d' % len(header)

  # Video.

  elif header.startswith('FLV\1'):
    # \1 is the version number, but there is no version later than 1 in 2017.
    info['format'] = 'flv'
    analyze_flv(f, info, header)
  elif header.startswith('\x1a\x45\xdf\xa3'):
    info['format'] = 'mkv'  # Can also be .webm as a subformat.
    analyze_mkv(f, info, fskip, header)
  elif header.startswith('OggS'):
    info['format'] = 'ogg'  # TODO(pts): Get media parameters.
    # https://en.wikipedia.org/wiki/Ogg#File_format
    # https://xiph.org/ogg/doc/oggstream.html
    # Vorbis: identification header in https://xiph.org/vorbis/doc/Vorbis_I_spec.html
    # Theora: identification header in https://web.archive.org/web/20040928224506/http://www.theora.org/doc/Theora_I_spec.pdf
    # Can contain other codecs as well, each with codec-specific identification header.
    # ... e.g. Dirac https://en.wikipedia.org/wiki/Dirac_(video_compression_format)
  elif header.startswith('\x30\x26\xb2\x75'):
    if len(header) < 16:
      header += f.read(16 - len(header))
    if header.startswith('0&\xb2u\x8ef\xcf\x11\xa6\xd9\x00\xaa\x00b\xcel'):
      info['format'] = 'asf'  # Also 'wmv'.
      analyze_asf(f, info, fskip, header)
  elif header.startswith('RIFF'):
    if len(header) < 12:
      header += f.read(12 - len(header))
    if header[8 : 12] == 'AVI ':
      info['format'] = 'avi'
      analyze_avi(f, info, fskip, header)
    elif header[8 : 12] == 'WAVE':
      info['format'] = 'wav'
      if len(header) < 36:
        header += f.read(36 - len(header))
        if len(header) < 36:
          raise ValueError('wav too short.')
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
    elif header[8 : 12] == 'CDXA':
      info['format'] = 'mpeg-cdxa'  # Video CD (VCD).
  elif header.startswith('\0\0\1') and header[3] in (
      '\xba\xbb\x07\x27\x47\x67\x87\xa7\xc7\xe7\xb0\xb5\xb3'):
    info['format'] = 'mpeg'  # Video.
    # https://github.com/tpn/winsdk-10/blob/38ad81285f0adf5f390e5465967302dd84913ed2/Include/10.0.10240.0/shared/ksmedia.h#L2909
    # lists MPEG audio packet types here: STATIC_KSDATAFORMAT_TYPE_STANDARD_ELEMENTARY_STREAM
  elif header.startswith('\212MNG'):
    if len(header) < 8:
      header += f.read(8 - len(header))
    if header.startswith('\212MNG\r\n\032\n'):
      info['format'] = 'mng'
  elif header.startswith('FWS') or header.startswith('CWS'):
    info['format'] = 'swf'
  elif header.startswith('.RMF'):
    if len(header) < 7:
      header += f.read(7 - len(header))
    if header.startswith('.RMF\0\0\0'):
      info['format'] = 'rm'
  elif header.startswith('DVDV'):
    if len(header) < 12:
      header += f.read(12 - len(header))
    if (header.startswith('DVDVIDEO-VTS') or
        header.startswith('DVDVIDEO-VMG')):
      info['format'] = 'dvd-bup'  # .bup and .ifo files on DVD.
  elif header.startswith('\x1f\x07\x00'):
    info['format'] = 'dv'  # DIF DV (digital video).

  # --- Images.

  elif header.startswith('GIF8'):
    if len(header) < 6:
      header += f.read(6 - len(header))
    if header.startswith('GIF87a') or header.startswith('GIF89a'):
      info['format'], info['codec'] = 'gif', 'lzw'
      if len(header) < 10:
        # Still short enough for is_animated_gif.
        header += f.read(10 - len(header))
        if len(header) < 10:
          raise ValueError('EOF in GIF header.')
      info['width'], info['height'] = struct.unpack('<HH', header[6 : 10])
      if is_animated_gif(f, header):  # This may read the entire input.
        info['format'] = 'agif'
  elif header.startswith('\xff\xd8\xff'):
    # TODO(pts): Which JPEG marker can be header[3]?
    info['format'], info['codec'] = 'jpeg', 'jpeg'
    info['width'], info['height'] = get_jpeg_dimensions(f, header)
  elif header.startswith('\211PNG'):
    if len(header) < 11:
      header += f.read(11 - len(header))
    if header.startswith('\211PNG\r\n\032\n\0\0\0'):
      info['format'], info['codec'] = 'png', 'flate'
      if len(header) < 24:
        header += f.read(24 - len(header))
        if len(header) < 24:
          raise ValueError('EOF in PNG header.')
      if header[12 : 16] == 'IHDR':
        info['width'], info['height'] = struct.unpack('>LL', header[16 : 24])
  elif (header.startswith('\xcf\x84') and
        header[2] in '\1\2' and header[3] in 'XYZ'):
    # JPEG reencoded by Dropbox lepton.
    info['format'], info['codec'] = 'lepton', 'lepton'
  elif (header.startswith('MM\x00\x2a') or
        header.startswith('II\x2a\x00')):
    # Also includes 'nikon-nef' raw images.
    info['format'] = 'tiff'
  elif header.startswith('P1 '):
    # TODO(pts): Get dimensions for all ppm.
    info['format'], info['codec'] = 'pbm', 'rawascii'
  elif header.startswith('P4'):
    info['format'], info['codec'] = 'pbm', 'raw'
  elif header.startswith('P2 '):
    info['format'], info['codec'] = 'pgm', 'rawascii'
  elif header.startswith('P5'):
    info['format'], info['codec'] = 'pgm', 'raw'
  elif header.startswith('P3 '):
    info['format'], info['codec'] = 'ppm', 'rawascii'
  elif header.startswith('P6'):
    info['format'], info['codec'] = 'ppm', 'raw'
  elif header.startswith('/* X'):
    if len(header) < 9:
      header += f.read(9 - len(header))
    if header.startswith('/* XPM */'):
      info['format'] = 'xpm'  # sam2p can read it.
  elif header.startswith('FORM'):
    if len(header) < 16:
      header += f.read(16 - len(header))
    if header.startswith('FORM') and header[8 : 16] == 'ILBMBMHD':
      info['format'] = 'lbm'  # sam2p can read it.
  elif header.startswith('AT&T'):
    if len(header) < 12:
      header += f.read(12 - len(header))
    if (header.startswith('AT&TFORM') and header[12 : 15] == 'DJV' and
        header[15 : 16] in 'UIM'):
      info['format'] = 'djvu'
  elif header.startswith('\x97\x4A\x42\x32'):
    # http://fileformats.archiveteam.org/wiki/JBIG2
    if len(header) < 12:
      header += f.read(12 - len(header))
    if header.startswith('\x97\x4A\x42\x32\x0D\x0A\x1A\x0A'):
      info['format'] = 'jbig2'
  elif header.startswith('id=I'):
    if len(header) < 14:
      header += f.read(14 - len(header))
    if header.startswith('id=ImageMagick'):
      info['format'] = 'miff'  # By ImageMagick.
  elif header.startswith('gimp'):
    if len(header) < 9:
      header += f.read(9 - len(header))
    if header.startswith('gimp xcf '):
      info['format'] = 'xcf'  # By GIMP.
  elif header.startswith('8BPS'):
    info['format'] = 'psd'  # By Photoshop.
  elif header.startswith('\0\0\1\0'):
    if len(header) < 6:
      header += f.read(6 - len(header))
    if len(header) >= 6 and 1 <= ord(header[4]) <= 40 and header[5] == '\0':
      info['format'] = 'ico'
  elif header.startswith('JG\4\016'):
    if len(header) < 8:
      header += f.read(8 - len(header))
    if header.startswith('JG\4\016\0\0\0\0'):
      info['format'] = 'art'  # By AOL browser.
  elif header.startswith('FUJI'):
    if len(header) < 28:
      header += f.read(28 - len(header))
    if (header.startswith('FUJIFILMCCD-RAW 0200FF383501') or
        header.startswith('FUJIFILMCCD-RAW 0201FF383501')):
      # https://libopenraw.freedesktop.org/wiki/Fuji_RAF/
      # Dimensions are not easy to get, maybe from the CFA IDs.
      # Please note that codec=raw also applies to uncompressed RGB 8-bit.
      info['format'], info['codec'] = 'fuji-raf', 'raw'

  # --- Audio.

  elif header.startswith('ID3'):
    info['format'] = 'mp3'
  elif header.startswith('ADIF'):
    info['format'] = 'aac'
  elif header.startswith('fLaC'):
    info['format'] = 'flac'
    analyze_flac(f, info, header)

  # --- Non-media data.

  elif header[:4].lower().startswith('@ech'):
    if len(header) < 9:
      header += f.read(9 - len(header))
    if header[:9].lower().startswith('@echo off'):
      info['format'] = 'windows-cmd'  # Or DOS .bat file.
  elif header.startswith('<?xm'):
    if len(header) < 5:
      header += f.read(5 - len(header))
    if header.startswith('<?xml'):
      info['format'] = 'xml'
  elif header[:4].lower().startswith('<?ph'):
    if len(header) < 5:
      header += f.read(5 - len(header))
    if header[:5].lower().startswith('<?php'):
      info['format'] = 'php'
  elif (header.startswith('<!--') or
        header[:4].lower() in ('<htm', '<hea', '<bod', '<!do')):
    # We could be more strict here, e.g. rejecting non-HTML docypes.
    # TODO(pts): Ignore whitespace in the beginning above.
    if len(header) < 256:
      header += f.read(256 - len(header))
    if is_html(header):
      info['format'] = 'html'
  elif header.startswith('\x0a\x04B\xd2'):
    if len(header) < 7:
      header += f.read(7 - len(header))
    if header.startswith('\x0a\x04B\xd2\xd5N\x12'):
      info['format'], inf['codec'] = 'brn', 'brn'
      info['width'], info['height'] = get_brn_dimensions(f, header)
  elif header.startswith('JASC'):
    info['format'] = 'jbf'
  elif header.startswith('\xca\xfe\xba\xbe'):
    info['format'] = 'java-class'
  elif (header.startswith('\xd0\xcf\x11\xe0') or
        header.startswith('\x0e\x11\xfc\x0d')):
    if len(header) < 8:
      header += f.read(8 - len(header))
    if (header.startswith('\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1') or
        header.startswith('\x0e\x11\xfc\x0d\xd0\xcf\x11\x0e')):
      # OLE compound file, including Thumbs.db
      # http://forensicswiki.org/wiki/OLE_Compound_File
      info['format'] = 'olecf'
  elif header.startswith('ADMY'):
    info['format'] = 'avidemux-mpeg-index'
  elif header.startswith('//AD'):
    info['format'] = 'avidemux-project'

  # --- Compressed.

  elif (header.startswith('PK\1\2') or header.startswith('PK\3\4') or
        header.startswith('PK\5\6') or header.startswith('PK\7\x08') or
        header.startswith('PK\6\6')):  # ZIP64.
    info['format'], info['codec'] = 'zip', 'flate'
  elif header.startswith('Rar!'):
    info['format'] = 'rar'
  elif (header.startswith('7kSt') or
        header.startswith('zPQ') and 1 <= ord(header[3]) <= 127):
    info['format'] = 'zpaq'
  elif header.startswith('\037\213\010'):
    info['format'], info['codec'] = 'gz', 'flate'
  elif header.startswith('BZh'):
    info['format'] = 'bz2'
  elif header.startswith('LZIP'):
    info['format'] = 'lzip'
  elif header.startswith('\x89LZO'):
    if len(header) < 7:
      header += f.read(7 - len(header))
    if header.startswith('\x89LZO\0\r\n'):
      info['format'] = 'lzop'
  elif header.startswith('7z\xbc\xaf'):
    if len(header) < 6:
      header += f.read(6 - len(header))
    if header.startswith('7z\xbc\xaf\x27\x1c'):
      info['format'] = '7z'
  elif header.startswith('\xfd7zX'):
    if len(header) < 6:
      header += f.read(6 - len(header))
    if header.startswith('\xfd7zXZ\0'):
      info['format'] = 'xz'
  elif header.startswith('\x5d\0\0'):
    if len(header) < 13:
      header += f.read(3 - len(header))
    if header[12] in '\0\xff':
      info['format'] = 'lzma'
  elif header.startswith('%PDF'):
    info['format'] = 'pdf'
  elif header.startswith('%!PS'):
    info['format'] = 'ps'
  elif header.startswith('\x7fELF'):
    if len(header) < 7:
      header += f.read(7 - len(header))
    if (len(header) >= 7 and header[4] in '\1\2' and header[5] in '\1\2' and
        header[6] == '\1'):
      info['format'] = 'elf'
  elif header.startswith('form'):
    if len(header) < 7:
      header += f.read(7 - len(header))
    if header.startswith('format='):
      # Filename extension: .mfo
      # Example: output of pymediafileinfo.
      info['format'] = 'fileinfo'
  elif header.startswith('#!/') or header.startswith('#! /'):
    info['format'] = 'unixscript'  # Unix script with shebang.
  elif header.startswith('\367\002'):  # Move this down (short prefix).
    info['format'] = 'dvi'
    # TODO(pts): 10 byte prefix? "\367\002\001\203\222\300\34;\0\0"
  elif (header.startswith('\x78\x01') or header.startswith('\x78\x5e') or
        header.startswith('\x78\x9c') or header.startswith('\x78\xda')):
    # Compressed in ZLIB format (/FlateEncode).
    info['format'], info['codec'] = 'flate', 'flate'

  # --- Anything with very short header. Has to come last.

  else:  # Last few matchers, with very short header.
    # TODO(pts): Make it compatible with 'winexe', in any order.
    info['format'] = '?'
    if info['format'] == '?' and len(header) < 8:
      # Mustn't be more than 8 bytes, for analyze_mp4.
      header += f.read(8 - len(header))
    if (info['format'] == '?' and
        header.startswith('\0\0\0') and len(header) >= 4 and
        ord(header[3]) >= 16 and (ord(header[3]) & 3) == 0 and
        header[4 : 8] == 'ftyp'):
      info['format'] = 'mp4'  # Can also be (new) .mov, .f4v etc. as a subformat.
      analyze_mp4(f, info, fskip, header)
    if (info['format'] == '?' and
        header.startswith('\0\0\0\x0cjP  ')):
      if len(header) < 12:
        header += f.read(12 - len(header))
      if header.startswith('\0\0\0\x0cjP  \r\n\x87\n'):
        info['format'] = 'jp2'  # JPEG2000 container format.
        analyze_mp4(f, info, fskip, header[12:])
    if (info['format'] == '?' and
        header[4 : 8] == 'mdat'):  # TODO(pts): Make it compatible with 'winexe'.
      info['format'] = 'mov'
      analyze_mp4(f, info, fskip, header)
    if (info['format'] == '?' and
          header.startswith('\0\0') and
          header[4 : 8] in ('wide', 'free', 'skip')):
      # Immediately followed by a 4-byte size, then 'mdat'.
      info['format'] = 'mov'
      analyze_mp4(f, info, fskip, header)
    if (info['format'] == '?' and
        header[0] == '\0' and header[1] in '\0\1\2\3\4\5\6\7\x08' and
        header[4 : 8] == 'moov'):
      info['format'] = 'mov'
      analyze_mp4(f, info, fskip, header)
    if (info['format'] == '?' and
          header.startswith('\0\0\0') and
          header[4 : 8] == 'pnot'):
      info['format'] = 'pnot'  # Seems to contain an image.
    if (info['format'] == '?' and
        header.startswith('BM')):
      if len(header) < 10:  # Don't read too much, for other formats later.
        header += f.read(10 - len(header))
      if header[6 : 10] == '\0\0\0\0':
        if len(header) < 18:
          header += f.read(18 - len(header))
        if header[15 : 18] == '\0\0\0' and 12 <= ord(header[14]) <= 127:
          if len(header) < 26:
            header += f.read(26 - len(header))
          info['format'] = 'bmp'
          b = ord(header[14])
          if b in (12, 64) and len(header) >= 22:
            info['width'], info['height'] = struct.unpack(
                '<HH', header[18 : 22])
          elif b in (40, 124) and len(header) >= 26:
            info['width'], info['height'] = struct.unpack(
                '<LL', header[18 : 26])

    if (info['format'] == '?' and header[4 : 6] in ('\x12\xaf', '\x11\xaf')):
      if len(header) < 16:
        header += f.read(16 - len(header))
      if header[12 : 14] == '\x08\0' and header[14 : 16] in ('\3\0', '\0\0'):
        # Autodesk Animator FLI or Autodesk Animator Pro flc.
        # http://www.drdobbs.com/windows/the-flic-file-format/184408954
        info['format'] = 'flic'
        if header[4] == '\x12':
          info['subformat'] = 'flc'
        else:
          info['subformat'] = 'fli'
        width, height = struct.unpack('<HH', header[8 : 12])
        video_track_info = {'type': 'video', 'codec': 'rle'}
        info['tracks'] = [video_track_info]
        set_video_dimens(video_track_info, width, height)
    if (info['format'] == '?' and
        (header[0] == '\x47' or header.startswith('\0\0\0\0\x47'))):
      # https://en.wikipedia.org/wiki/MPEG_transport_stream
      i = header.find('\x47')
      if len(header) >= i + 4:
        b, = struct.unpack('>L', header[i : i + 4])
        tei = (b >> 23) & 1
        pusi = (b >> 22) & 1
        tp = (b >> 21) & 1
        packet_id = (b >> 8) & 0x1fff  # 13-bit.
        tsc = (b >> 6) & 3
        afc = (b >> 4) & 3
        cc = b & 15
        # TODO(pts): If packet_id == 8191, then it's the null packet, and find
        # the next packet.
        if tei == 0 and cc == 0 and tsc == 0 and packet_id in (0, 0x11, 8191):
          # Also applies to .m2ts.
          info['format'] = 'mpegts'
          # packet_id=0 is Program Association Table (PAT)
          # packet_id=0x11 is
          # https://en.wikipedia.org/wiki/Service_Description_Table
        elif (header[0] == '\x47' and
              header[2] == '\0' and (ord(header[1]) & 0x5f) == 0x40 and
              (ord(header[3]) & 0x10) == 0x10):
          info['format'] = 'mpegts'  # Old getting of parameters.
    if (info['format'] == '?' and
        header[0] == '\n' and header[2] == '\1' and ord(header[1]) <= 5 and
        header[3] in '\1\2\4\x08'):  # Move this down.
      format = 'pcx'  # sam2p can read it.
    if (info['format'] == '?' and
        30 <= ord(header[0]) <= 63 and ord(header[1]) <= 11):
      if len(header) < 17:
        header += f.read(17 - len(header))
      if ord(header[16]) <= 8 or ord(header[16]) == 24:
        # Unfortunately not all tga (targa) files have 'TRUEVISION-XFILE.\0'.
        format = 'tga'  # sam2p can read it.
    if (info['format'] == '?' and
        (header.startswith('\xff\xfa') or header.startswith('\xff\xfb')) and
         ord(header[2]) >> 4 not in (0, 15) and ord(header[2]) & 0xc != 12):
      # The technically more correct term is MPEG ADTS.
      info['format'] = 'mp3'
    if (info['format'] == '?' and header.startswith('MZ')):
      # Windows .exe file (PE, Portable Executable).
      if len(header) < 64:
        header += f.read(64 - len(header))
      pe_ofs, = struct.unpack('<L', header[60: 64])
      if pe_ofs < 8180 and len(header) < pe_ofs + 300:
        header += f.read(pe_ofs + 300 - len(header))
      if (len(header) >= pe_ofs + 6 and
          header.startswith('MZ') and
          header[pe_ofs : pe_ofs + 4] == 'PE\0\0' and
          header[pe_ofs + 24 : pe_ofs + 26] in ('\x0b\1', '\x0b\2') and
          # Only i386 and amd64 are recognized.
          header[pe_ofs + 4 : pe_ofs + 6] in ('\x4c\01', '\x64\x86')):
        info['format'] = 'winexe'
        # 108 bytes instead of 92 bytes for PE32+.
        rva_ofs = pe_ofs + 24 + 92 + 16 * (
            header[pe_ofs + 24 : pe_ofs + 26] == '\x0b\2')
        rva_count, = struct.unpack('<L', header[rva_ofs : rva_ofs + 4])
        if rva_count > 14:  # IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR.
          vaddr, size = struct.unpack('<LL', header[rva_ofs + 116 : rva_ofs + 124])
          if vaddr > 0 and size > 0:  # Typically vaddr == 8292, size == 72.
            info['format'] = 'dotnetexe'  # .NET executable assembly.

  if not info.get('format'):
    info['format'] = '?'
  if info.get('tracks'):
    copy_info_from_tracks(info)
  return info