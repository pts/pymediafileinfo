#! /usr/bin/python
# by pts@fazekas.hu at Sun Sep 10 00:26:18 CEST 2017

import struct
import sys


def set_video_dimens(video_track_info, width, height):
  if width is not None and height is not None:
    # We don't check `(height & 7) == 0', because sometimes height == 262.
    if not (16 <= width <= 16383):
      raise ValueError('Unreasonable width: %d' % width)
    if not (16 <= height <= 16383):
      raise ValueError('Unreasonable height: %d' % height)
    video_track_info['width'] = width
    video_track_info['height'] = height


# --- flv


def detect_flv(f, info, header=''):
  # by pts@fazekas.hu at Sun Sep 10 00:26:18 CEST 2017
  #
  # Documented here (starting on page 68, Annex E):
  # http://download.macromedia.com/f4v/video_file_format_spec_v10_1.pdf
  #
  # !!! Compare it with medid for all (not only h264).

  def parse_h264_sps(
      data, expected, expected_sps_id,
      _hextable='0123456789abcdef',
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
  if (flags & ~5) != 0:
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
      if size > 8191:  # !! Estimate better.
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
      if size >= (1 << 22):  # !! Estimate better.
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
          # We extract the dimensions from the SPS in the AVCC.
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
          if (lsm | 3) != 255 or (sps_count | 31) != 255:
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
      if size > 65535:  # !! Estimate better.
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
    if prev_size not in (0, size + 11):
      raise ValueError(
          'Unexpected PreviousTagSize: expected=%d got=%d' %
          (size + 11, prev_size))

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
    'V_MPEG4/ISO/ASP': 'divxasp',
    'V_MPEG4/MS/V3': 'divx3',
    'V_MPEG1': 'mpeg1',
    'V_MPEG2': 'mpeg2',	
    'V_REAL/RV10': 'rv5',
    'V_REAL/RV20': 'rvg2',
    'V_REAL/RV30': 'rv8',
    'V_REAL/RV30': 'rv9',
    'V_QUICKTIME': 'qt',  # Sorenson or Cinepak, more info in CodecPrivate.
    'V_THEORA': 'theora',
    'V_PRORES': 'prores',
    'V_VP8': 'vp8',

    'A_MPEG/L3': 'mp3',
    'A_MPEG/L2': 'mp2',
    'A_MPEG/L1': 'mp1',
    'A_PCM/INT/BIG': 'pcm',
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


def detect_mkv(f, info, header=''):
  # https://matroska.org/technical/specs/index.html

  # !!! merge and refactor mp4 from dump_mp4.py
  # !!! convert assert to ValueError in detect_mp4
  # !!! make everything work for nonseekable
  # !!! don't use f.tell()
  # !!! diagnos all errors, e.g. lots of Unexpected PreviousTagSize: 
  def read_id(f):
    c = f.read(1)
    if not c:
      raise ValueError('MKVE1')
    b = ord(c)
    if b > 127:
      return c
    if b > 63:
      data = f.read(1)
      if not data:
        raise ValueError('MKVE2')
      return c + data
    if b > 31:
      data = f.read(2)
      if len(data) != 2:
        raise ValueError('MKVE3')
      return c + data
    if b > 15:
      data = f.read(3)
      if len(data) != 3:
        raise ValueError('MKVE4')
      return c + data
    raise ValueError('Invalid ID prefix: %d' % b)

  def read_size(f):
    c = f.read(1)
    if not c:
      raise ValueError('MKVE5')
    if c == '\1':
      data = f.read(7)
      if len(data) != 7:
        raise ValueError('MKVE6')
      if data == '\xff\xff\xff\xff\xff\xff\xff':  # Streaming size.
        raise ValueError('MKVE7')
      return struct.unpack('>Q', '\0' + data)[0]
    b = ord(c)
    if b > 127:
      return b & 127
    if b > 63:
      data = f.read(1)
      if not data:
        raise ValueError('MKVE8')
      return (b & 63) << 8 | ord(data)
    if b > 31:
      data = f.read(2)
      if not len(data) != 2:
        raise ValueError('MKVE9')
      return (b & 31) << 16 | struct.unpack('>H', data)[0]
    if b > 15:
      data = f.read(3)
      if not len(data) != 3:
        raise ValueError('MKVE10')
      return (b & 15) << 24 | struct.unpack('>L', '\0' + data)[0]
    if b > 7:
      data = f.read(4)
      if not len(data) != 4:
        raise ValueError('MKVE11')
      return (b & 7) << 32 | struct.unpack('>L', data)[0]
    if b > 3:
      data = f.read(5)
      if not len(data) != 5:
        raise ValueError('MKVE11')
      return (b & 3) << 40 | struct.unpack('>Q', '\0\0\0' + data)[0]
    if b > 1:
      data = f.read(6)
      if not len(data) != 6:
        raise ValueError('MKVE11')
      return (b & 1) << 48 | struct.unpack('>Q', '\0\0' + data)[0]
    raise ValueError('Invalid ID prefix: %d' % b)

  def read_id_skip_void(f):
    while 1:
      xid = read_id(f)
      if xid != '\xec':  # Void.
        return xid
      size = read_size(f)
      data = f.read(size)  # !! Don't read too much to memory.
      if len(data) != size:
        raise ValueError('EOF in Void element.')

  if len(header) > 4:
    # We can increase it by input buffering.
    raise AssertionError('Header too long for mkv: %d' % len(header))
  header += f.read(4 - len(header))
  if len(header) != 4:
    raise ValueError('Too short for MKV.')

  xid = header[:4]  # xid = read_id(f)
  if xid != '\x1a\x45\xdf\xa3':
    raise ValueError('MKV signature not found.')
  size = read_size(f)
  if size >= 256:
    raise ValueError('MKV header unreasonably large: %d' % size)
  header_end = f.tell() + size
  info['format'] = 'mkv'
  while f.tell() < header_end:
    xid = read_id_skip_void(f)
    size = read_size(f)  # !! Don't read too much. Limit it.
    if f.tell() + size > header_end:
      raise ValueError('Size of in-header element too large.')
    data = f.read(size)
    if len(data) != size:
      raise ValueError('EOF in header element.')
    if xid == '\x42\x82':  # DocType.
      # 'matroska' for .mkv, 'webm' for .webm.
      if data not in ('matroska', 'webm'):
        raise ValueError('Unknown MKV DocType: %r' % data)
      info['subformat'] = MKV_DOCTYPES[data]
      if info['subformat'] == 'webm':
        info['brands'] = ['mkv', 'webm']
        info['format'] = 'webm'
      else:
        info['brands'] = ['mkv']
  if 'subformat' not in info:
    raise('MKV DocType not found.')
  xid = read_id_skip_void(f)
  if xid != '\x18\x53\x80\x67':  # Segment.
    raise ValueError('Expected Segment element, got: %s' % xid.encode('hex'))
  size = read_size(f)
  segment_end = f.tell() + size
  info['tracks'] = []
  while f.tell() < segment_end:
    xid = read_id_skip_void(f)
    size = read_size(f)
    if f.tell() + size > segment_end:
      raise ValueError('Size of in-Segment element too large.')
    if (xid == '\x11\x4d\x9b\x74' or  # SeekHead.
        xid == '\x15\x49\xa9\x66'):  # Info.
      data = f.read(size)
      if len(data) != size:
        raise ValueError('EOF in SeekHead or Info element.')
    elif xid == '\x16\x54\xae\x6b':  # Tracks.
      tracks_end = f.tell() + size
      while f.tell() < tracks_end:
        xid = read_id_skip_void(f)
        size = read_size(f)
        if f.tell() + size > tracks_end:
          raise ValueError('Size of in-Tracks element too large.')
        if xid != '\xae':  # Track.
          raise ValueError('Expected Track element, got: %s' % xid.encode('hex'))
        track_end = f.tell() + size
        track_info = {}
        while f.tell() < track_end:
          xid = read_id_skip_void(f)
          size = read_size(f)
          if f.tell() + size > track_end:
            raise ValueError('Size of in-Track element too large.')
          if xid == '\xe0':  # Video.
            track_info['type'] = 'video'
            video_end = f.tell() + size
            width = height = None
            while f.tell() < video_end:
              xid = read_id_skip_void(f)
              size = read_size(f)
              if f.tell() + size > video_end:
                raise ValueError('Size of in-Video element too large.')
              data = f.read(size)
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
            audio_end = f.tell() + size
            width = height = None
            while f.tell() < audio_end:
              xid = read_id_skip_void(f)
              size = read_size(f)
              if f.tell() + size > audio_end:
                raise ValueError('Size of in-Audio element too large.')
              data = f.read(size)
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
          elif xid == '\x86':  # Codec ID.
            data = f.read(size)
            if len(data) != size:
              raise ValueError('EOF in Track element.')
            track_info['codec'] = MKV_CODEC_IDS.get(data, data)
          elif xid == '\x25\x86\x88':  # Codec Name.
            data = f.read(size)
            if len(data) != size:
              raise ValueError('EOF in Track element.')
            track_info['codec_name'] = data  # Usually not set in .webm.
          else:
            data = f.read(size)
            if len(data) != size:
              raise ValueError('EOF in Track element.')
        if 'type' in track_info:
          info['tracks'].append(track_info)
      break  #  in Segment, don't read anything beyond Tracks, they are large.
    else:
      raise ValueError('Unexpected ID in Segment: %s' % xid.encode('hex'))
  return info


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


# --- mp4


def detect_mp4(f, info, header=''):
  # Documentation: http://xhelmboyx.tripod.com/formats/mp4-layout.txt
  info['type'] = 'mov'
  info['minor_version'] = 0
  info['brands'] = []
  info['tracks'] = []
  info['has_early_mdat'] = False

  def skip(size, xtype):
    if size < 65536:
      data = f.read(size)
      if len(data) != size:
        raise ValueError('EOF while skipping mp4 box, xtype=%r' % xtype)
    else:
      # !! TODO(pts): What if not seekable?
      f.seek(size, 1)  # We assume that the file is long enough.

  # Empty or contains the type of the last hdlr.
  last_hdlr_type_list = []

  def process_box(size):
    """Dumps the box, and must read it (size bytes)."""
    xtype = xtype_path[-1]
    xytype = '/'.join(xtype_path[-2:])
    # Only the composites we care about.
    is_composite = xytype in (
        '/moov', 'moov/trak', 'trak/mdia', 'mdia/minf', 'minf/stbl')
    if xtype == 'mdat':
      info['has_early_mdat'] = False
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
      if size > 16383 or xtype == 'free':
        skip(size, xtype)
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
          info['minor_version'] = int(info['minor_version'])
          if major_brand == 'qt  ':
            info['type'] = 'mov'
          elif major_brand == 'f4v ':
            info['type'] = 'f4v'
          else:
            info['type'] = 'mp4'
          info['subtype'] = major_brand
          brands = set(data[i : i + 4] for i in xrange(8, len(data), 4))
          brands.discard('\0\0\0\0')
          brands.add(major_brand)
          brands = sorted(brands)
          info['brands'] = brands  # Example: ['isom', 'mp42'].
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
          last_hdlr_type_list.append(data[8 :12])
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
            # !! allow ysize==0 and nothing else.
            if len(data) - i < 8:
              raise ValueError('MP4E12')
            if not count:
              raise ValueError('MP4E13')
            # codec usually indicates the codec, e.g. 'avc1' for video and 'mp4a' for audio.
            ysize, codec = struct.unpack('>L4s', data[i : i + 8])
            codec = ''.join(codec.split())  # Remove whitespace, e.g. 'raw'.
            if ysize < 8 or i + ysize > len(data):
              raise ValueError('MP4E14')
            yitem = data[i + 8 : i + ysize]
            last_hdlr_type_list.append('d')  # Signal above.
            if last_hdlr_type_list[0] == 'vide':
              # Video docs: https://developer.apple.com/library/content/documentation/QuickTime/QTFF/QTFFChap3/qtff3.html#//apple_ref/doc/uid/TP40000939-CH205-BBCGICBJ
              if ysize < 28:
                raise ValueError('Video stsd too short.')
              # !! TODO(pts): Many of these for .mov files: Unreasonable height: 2
              # !!            .mov dimen detection is not reliable yet.
              reserved1, data_reference_index, version, revision_level, vendor, temporal_quality, spatial_quality, width, height = struct.unpack('>6sHHH4sLLHH', yitem[:28])
              video_track_info = {'type': 'video', 'codec': codec}
              set_video_dimens(video_track_info, width, height)
              info['tracks'].append(video_track_info)
            elif last_hdlr_type_list[0] == 'soun':
              # Audio: https://developer.apple.com/library/content/documentation/QuickTime/QTFF/QTFFChap3/qtff3.html#//apple_ref/doc/uid/TP40000939-CH205-BBCGGHJH
              # Version can be 0 or 1.
              # Audio version 1 adds 4 new 4-byte fields (samples_per_packet, bytes_per_packet, bytes_per_frame, bytes_per_sample)
              if ysize < 28:
                raise ValueError('Audio stsd too short.')
              reserved1, data_reference_index, version, revision_level, vendor, channel_count, sample_size_bits, compression_id, packet_size, sample_rate_hi, sample_rate_lo = struct.unpack('>6sHHHLHHHHHH', yitem[:28])
              info['tracks'].append({
                  'type': 'audio',
                  'codec': codec,
                  'channel_count': channel_count,
                  'sample_size': sample_size_bits,
                  'sample_rate': sample_rate_hi + (sample_rate_lo / 65536.0),
              })
            i += ysize
            count -= 1
          if count:
            raise ValueError('MP4E15')

  xtype_path = ['']
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
      raise ValueError('EOF in top-level mp4 box header.')
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
      # finish the metadata boxes first (before EOF).
      raise ValueError('mp4 box size too small: %d' % size)
    xtype_path.append(xtype)
    process_box(size)
    xtype_path.pop()
    if xtype == 'moov':  # Found all metadata.
      break


def detect(f, info=None):
  """Detect file format, codecs and image dimensions in file f.

  For videos, info['tracks'] is a list with an item for each video or audio
  track (info['tracks'][...]['type'] in ('video', 'audio'). Subtitle tracks
  are not detected.

  Args:
    f: File-like object with a .read(n) method and an optional .seek(n) method.
        Seeking will be avoided if possible.
    info: A dict to update with the detected info, or None.
  Returns:
    The info dict.
  """
  if info is None:
    info = {}
  if 'f' not in info and getattr(f, 'name', None):
    info['f'] = f.name.replace('\n', '{\\n}')
  # Set it early, in case of an exception.
  info.setdefault('format', '?')
  header = f.read(4)
  if not header:
    info['format'] = 'empty'
  elif len(header) < 4:
    info['format'] = 'short%d' % len(header)
  elif header.startswith('FLV\1'):
    # \1 is the version number, but there is no version later than 1 in 2017.
    info['format'] = 'flv'
    detect_flv(f, info, header)
  elif header.startswith('\x1a\x45\xdf\xa3'):
    info['format'] = 'mkv'  # Can also be .webm as a subformat.
    detect_mkv(f, info, header)
  elif (header.startswith('\0\0\0') and len(header) >= 4 and
        ord(header[3]) >= 16 and (ord(header[3]) & 3) == 0):
    if len(header) < 8:
      header += f.read(8 - len(header))
    if header[4 : 8] == 'ftyp':
      info['format'] = 'mp4'  # Can also be (new) .mov, .f4v etc. as a subformat.
      detect_mp4(f, info, header)
  elif header.startswith('GIF8'):
    if len(header) < 6:
      header += f.read(6 - len(header))
    if header.startswith('GIF87a') or header.startswith('GIF89a'):
      info['format'] = 'gif'  # TODO(pts): Distinguish 'agif' (animated GIF).
  elif header.startswith('\xff\xd8\xff'):
    # TODO(pts): Which JPEG marker can be header[3]?
    info['format'] = 'jpeg'
    # !! TODO(pts): Copy much code for image formats media_scan.py.
    #    No need for seeking.
    #    is_animated_gif
    #    dimensions for: jpeg, gif, brn, png, bmp, html
  elif header.startswith('<?xm'):
    info['format'] = 'xml'
  elif (header.startswith('<!--') or
        header[:4].lower() in ('<htm', '<hea', '<bod', '<!do')):
    # We could be more strict here, e.g. non-HTML docypes.
    # TODO(pts): Check: '<html>', '<head>', '<body>', '<!doctype html'.
    info['format'] = 'html'
  elif header.startswith('\x0a\x04B\xd2'):
    if len(header) < 7:
      header += f.read(7 - len(header))
    if header.startswith('\x0a\x04B\xd2\xd5N\x12'):
      info['format'] = 'brn'
  elif header.startswith('\211PNG'):
    if len(header) < 8:
      header += f.read(8 - len(header))
    if header.startswith('\211PNG\r\n\032\n'):
      info['format'] = 'png'
  elif header.startswith('\xcf\x84'):
    # TODO(pts): Be more strict.
    info['format'] = 'lepton'  # JPEG reencoded by Dropbox lepton.
  elif (header.startswith('MM\x00\x2a') or
        header.startswith('II\x2a\x00')):
    # Also includes 'nikon-nef' raw images.
    info['format'] = 'tiff'
  elif header.startswith('P1 ') or header.startswith('P4'):
    info['format'] = 'pbm'
  elif header.startswith('P2 ') or header.startswith('P5'):
    info['format'] = 'pgm'
  elif header.startswith('P3 ') or header.startswith('P6'):
    info['format'] = 'ppm'
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
      # Dimensions are not easy to extract, maybe from the CFA IDs.
      info['format'] = 'fuji-raf'
  elif (header.startswith('PK\1\2') or header.startswith('PK\3\4') or
        header.startswith('PK\5\6') or header.startswith('PK\7\x08') or
        header.startswith('PK\6\6')):  # ZIP64.
    info['format'] = 'zip'
  elif header.startswith('JASC'):
    info['format'] = 'jbf'
  elif header.startswith('Rar!'):
    info['format'] = 'rar'
  elif (header.startswith('7kSt') or
        header.startswith('zPQ') and 1 <= ord(header[3]) <= 127):
    info['format'] = 'zpaq'
  elif header.startswith('\037\213\010'):
    info['format'] = 'gz'
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
  elif (header.startswith('\xd0\xcf\x11\xe0') or
        header.startswith('\x0e\x11\xfc\x0d')):
    if len(header) < 8:
      header += f.read(8 - len(header))
    if (header.startswith('\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1') or
        header.startswith('\x0e\x11\xfc\x0d\xd0\xcf\x11\x0e')):
      # OLE compound file, including Thumbs.db
      # http://forensicswiki.org/wiki/OLE_Compound_File
      info['format'] = 'olecf'
  elif header.startswith('\x30\x26\xb2\x75'):
    info['format'] = 'asf'  # Also 'wmv'.
  elif header.startswith('RIFF'):
    if len(header) < 12:
      header += f.read(12 - len(header))
    if header[8 : 12] == 'AVI ':
      info['format'] = 'avi'
      # TODO(pts): Add detection of width and height.
    elif header[8 : 12] == 'WAVE':
      info['format'] = 'wav'
  elif header.startswith('\0\0\1') and header[3] in (
      '\xba\xbb\x07\x27\x47\x67\x87\xa7\xc7\xe7\xb0\xb5\xb3'):
    info['format'] = 'mpeg'
  elif (header[0] == '\x47' and header[2] == '\0' and
        (ord(header[1]) & 0x5f) == 0x40 and (ord(header[3]) & 0x10) == 0x10):
    info['format'] = 'mpegts'  # .ts, MPEG transport stream.
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
  elif header.startswith('#!/') or header.startswith('#! /'):
    info['format'] = 'unixscript'  # Unix script with shebang.
  elif header.startswith('\367\002'):  # Move this down (short prefix).
    info['format'] = 'dvi'
    # TODO(pts): 10 byte prefix? "\367\002\001\203\222\300\34;\0\0"
  elif header.startswith('MZ'):  # Move this down (short prefix).
    # Windows .exe file (PE, Portable Executable).
    if len(header) < 64:
      header += f.read(64 - len(header))
    pe_ofs, = struct.unpack('<L', header[60: 64])
    if pe_ofs < 8180 and len(header) < pe_ofs + 6:
      header += f.read(pe_ofs + 6 - len(header))
    if (len(header) >= pe_ofs + 6 and
        header.startswith('MZ') and
        header[pe_ofs : pe_ofs + 4] == 'PE\0\0' and
        # Only i386 and amd64 detected.
        header[pe_ofs + 4 : pe_ofs + 6] in ('\x4c\01', '\x64\x86')):
      info['format'] = 'winexe'
  elif (header.startswith('\x78\x01') or header.startswith('\x78\x5e') or
        header.startswith('\x78\x9c') or header.startswith('\x78\xda')):
    info['format'] = 'flate'  # Compressed in ZLIB format (/FlateEncode).
  else:  # Last few matchers, with very short header.
    # TODO(pts): Make it compatible with 'winexe', in any order.

    info['format'] = '?'
    if info['format'] == '?' and len(header) < 8:
      # Mustn't be more than 8 bytes, for detect_mp4.
      header += f.read(8 - len(header))
    if (info['format'] == '?' and
        header[4 : 8] == 'mdat'):  # TODO(pts): Make it compatible with 'winexe'.
      info['format'] = 'mov'
      detect_mp4(f, info, header)
    elif (info['format'] == '?' and
          header.startswith('\0\0') and header[4 : 8] == 'wide'):
      # Immediately followed by a 4-byte size, then 'mdat'.
      info['format'] = 'mov'
      detect_mp4(f, info, header)
    elif (info['format'] == '?' and
          header.startswith('\0\0') and header[4 : 8] == 'moov'):
      info['format'] = 'mov'
      detect_mp4(f, info, header)
    if (info['format'] == '?' and
        header.startswith('BM')):
      if len(header) < 10:
        header += f.read(10 - len(header))
      if header[6 : 10] == '\0\0\0\0':
        info['format'] = 'bmp'
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

  if not info.get('format'):
    info['format'] = '?'
  if info.get('tracks'):
    copy_info_from_tracks(info)
  return info


def format_info(info):
  def format_value(v):
    if isinstance(v, bool):
      return int(v)
    if isinstance(v, float):
      if abs(v) < 1e15 and int(v) == v:  # Remove the trailing '.0'.
        return int(v)
      return repr(v)
    return v
  output = ['format=%s' % (info.get('format') or '?')]
  output.extend(
      ' %s=%s' % (k, '___'.join(str(format_value(v)).split()))
      for k, v in sorted(info.iteritems())
      if k != 'f' and k != 'format' and
      not isinstance(v, (tuple, list, dict, set)))
  path = info.get('f')
  if path is not None:
    output.append(' f=%s' % path)  # Emit ` f=' last.
  output.append('\n')
  return ''.join(output)


def main(argv):
  had_error = False
  for filename in argv[1:]:
    f = open(filename, 'rb')
    try:
      had_error_here, info = True, {}
      try:
        info = detect(f, info)
        had_error_here = False
      except KeyboardInterrupt:
        raise
      except (IOError, ValueError), e:
        info['error'] = 'bad_file'
        if e.__class__ == ValueError:
          print >>sys.stderr, 'error: bad file %r: %s' % (filename, e)
        else:
          print >>sys.stderr, 'error: bad file %r: %s.%s: %s' % (
              filename, e.__class__.__module__, e.__class__.__name__, e)
      except Exception, e:
        info['error'] = 'error'
        print >>sys.stderr, 'error: error detecting in %r: %s.%s: %s' % (
            filename, e.__class__.__module__, e.__class__.__name__, e)
      if had_error_here:
        had_error = True
      if not info.get('format'):
        info['format'] = '?'
      try:
        info['header_end_offset'] = int(f.tell())
        f.seek(0, 2)
        info['size'] = f.tell()
      except (IOError, OSError, AttributeError):
        pass
      sys.stdout.write(format_info(info))
      sys.stdout.flush()
      if not had_error_here and info['format'] == '?':
        print >>sys.stderr, 'warning: unknown file format: %r' % filename
        had_error = True
    finally:
      f.close()
  if had_error:
    sys.exit(2)


if __name__ == '__main__':
  sys.exit(main(sys.argv))
