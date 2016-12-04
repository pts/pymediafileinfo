#! /bin/sh
# by pts@fazekas.hu at Wed Aug 24 12:35:51 CEST 2016

""":" #media_scan: Computes file checksum, detects format and image dimensions.

type python2.7 >/dev/null 2>&1 && exec python2.7 -- "$0" ${1+"$@"}
type python2.6 >/dev/null 2>&1 && exec python2.6 -- "$0" ${1+"$@"}
type python2.5 >/dev/null 2>&1 && exec python2.5 -- "$0" ${1+"$@"}
type python2.4 >/dev/null 2>&1 && exec python2.4 -- "$0" ${1+"$@"}
exec python -- ${1+"$@"}; exit 1

This script need Python 2.5, 2.6 or 2.7. Python 3.x won't work. Python 2.4
typically won't work (unless the hashlib module is installed from PyPi).

Typical usage: media_scan.py --old=mscan.out .
"""

import cStringIO
import re
import struct
import os
import os.path
import stat
import sys

try:
  from hashlib import sha256  # Needs Python 2.5 or later.
except ImportError:
  if sys.version_info < (2, 5):
    sys.exit('fatal: Install hashlib from PyPI or use Python >=2.5.')

# --- Image fingerprinting for similarity with findimagedupes.
#
# Clients should call fingerprint_image.
#

def fix_gm_filename(filename):
  """Prevent GraphicsMagick from treating files like logo: specially."""
  if not os.path.isabs(filename) and (
     filename.startswith('-') or filename.startswith('+') or
     ':' in filename):
    return os.path.join('.', filename)
  else:
    return filename


# by pts@fazekas.hu at Thu Dec  1 21:07:48 CET 2016
# Bit-by-bit identical output to the findimagedupes Perl script's.
def fingerprint_image_with_pgmagick(filename, _half_threshold_ary=[]):
  # Dependency: sudo apt-get install python-pgmagick
  # Dependency (alt): pip install pgmagick
  import pgmagick
  if not _half_threshold_ary:
    _half_threshold_ary.append((1 << (pgmagick.Image().depth() - 1)) - 1)  # 127
  try:
    # Ignores and hides warnings. Usage ing.read(filename) to convert a
    # warning to a RuntimeError. For a ``Premature end of JPEG file'', this
    # will still read the JPEG (partyially) to img.
    img = pgmagick.Image(filename)
    # Not doing this: img.verbose(True)
    img.sample('160x160!')
    img.modulate(100.0, -100.0, 100.0)  # saturation=-100.
    img.blur(3, 99)  # radius=3, sigma=99.
    img.normalize()
    img.equalize()
    img.sample('16x16')
    img.threshold(_half_threshold_ary[0])
    img.magick('mono')
    blob = pgmagick.Blob()
    img.write(blob)
    # Just for comaptibility check.
    #try:
    #  assert blob.base64() == fingerprint_image_with_perl(filename)
    #except IOError:
    #  pass
    # 32 bytes encoded as 44 bytes base64, ending by '=='.
    return blob.base64()
  except (RuntimeError, IOError), e:
    # Typically RuntimeError raised by pgmagick methods.
    raise IOError(str(e))


def fingerprint_image_with_gm_convert(filename):
  # Dependency: sudo apt-get install graphicsmagick

  import base64
  import subprocess
  # ImageMagick `convert' tool doesn't work, it implements `-sample' in an
  # incompatible way, the outputs don't match.
  #
  # The per-file overhead of calling a separate `gm convert' process is 0.02s
  # in real time and 0.00255s in user time. This is how much faster
  # fingerprint_image_with_gm_convert is.
  gm_convert_cmd = (
      'gm', 'convert', filename, '-sample', '160x160!',
      '-modulate', '100,-100,100', '-blur', '3x99', '-normalize',
      '-equalize', '-sample', '16x16', '-threshold', '50%', 'mono:-')
  p = subprocess.Popen(gm_convert_cmd, stdin=subprocess.PIPE,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  try:
    data, stderr_data = p.communicate('')
  finally:
    exit_code = p.wait()
  if exit_code:
    raise IOError('gm convert failed: exit_code=%d stderr=%r' %
                  (exit_code, stderr_data))
  # Don't print stderr_data here, example line:
  # 'gm convert: Corrupt JPEG data: premature end of data segment (t.jpg).\n'.
  if len(data) != 32:
    raise IOError(
        'gm convert returned bad data size: got=%d expected=32' % len(data))
  return base64.b64encode(data)


# by pts@fazekas.hu at Thu Dec  1 08:06:10 CET 2016
FINGERPRINT_IMAGE_PERL_CODE = r'''
use integer;
use strict;
use Graphics::Magick;

my $inFP = 0;
$SIG{SEGV} = sub { die $inFP ? "caught segfault in fingerprinting\n" : ()};

sub try {
  my ($err) = @_;
  # Example: Exception 325: Corrupt JPEG data: premature end of data segment
  # TODO(pts): Handle: GraphicMagick problem: Exception 450: Unsupported marker type 0x31
  if ($err and $err !~ /^(?:Warning (?:315|330)|Exception 325):/) {
    die("GraphicMagick problem: $err\n");
  }
}

# Similar to Mime::Base64::encode_base64, compatible with Python
# base64.decodestrig and base64.standard_b64decode.
sub base64_encode($) {
  return undef if !defined($_[0]);
  my $s = pack("u", $_[0]);  # We base base64 encoding on on uuencode.
  $s =~ y{`!\"#\$\%&\x27()*+,\-./0-9:;<=>?\@A-Z[\\]^_`}{A-Za-z0-9+/};
  $s =~ s@^(?:[ADGJMPSVYbehknqtwz258](\S+)\n|[BEHKNQTWZcfilorux0369]
      (\S+)AA\n|[CFILORUXadgjmpsvy147](\S+)A\n|(.+))@
      defined$1 ? $1 : defined$2 ? $2."==" : defined$3 ?
      $3."=" : die("bad uu:$4\n") @msgex;
  return $s;
}

# Code based on `findimagedupes` 2.18-4build3.
sub fingerprint_image($) {
  my $file = $_[0];
  # GraphicMagick doesn't always catch output from the programs
  # it spawns, so we have to clean up for it...
  open(SAVED_OUT, ">&", \*STDOUT) or die("open(/dev/null): $!\n");
  open(SAVED_ERR, ">&", \*STDERR) or die("open(/dev/null): $!\n");
  open(STDOUT, ">/dev/null");
  open(STDERR, ">/dev/null");
  $inFP = 1;
  my $result = eval {
    my $image = Graphics::Magick->new;
    die "file not found: $file\n" if !-f($file);
    if (!$image->Ping($file)) {
      die("unknown-type file: $file\n");
    }
    try $image->Read($file);
    if ($#$image<0) {
      die("fingerprint: not enough image data for $file\n");
    }
    else {
      $#$image = 0;
    }
    try $image->Sample("160x160!");
    try $image->Modulate(saturation=>-100);
    try $image->Blur(radius=>3,sigma=>99);
    try $image->Normalize();
    try $image->Equalize();
    try $image->Sample("16x16");
    try $image->Threshold();
    try $image->Set(magick=>'mono');
    my $blob = $image->ImageToBlob();
    if (!defined($blob)) {
      die("This can't happen! undefined blob for: $file\n");
    }
    $blob;
  };
  $inFP = 0;
  #@$image = ();  # TODO(pts): Do we need this for cleanup? It doesn't speed up.
  open(STDOUT, ">&", \*SAVED_OUT) or die("open(/dev/null): $!\n");
  open(STDERR, ">&", \*SAVED_ERR) or die("open(/dev/null): $!\n");
  close(SAVED_OUT);
  close(SAVED_ERR);
  if (!defined($result)) {
    my $msg = $@; chomp $msg; $msg =~ s@[\n\r]+@  @g; return "! $msg";
  }
  base64_encode($result);
}

print "! fingerprint_image ready\n";
select((select(STDOUT), $| = 1)[0]);  # Flush.
while (<STDIN>) {
  chomp;
  print fingerprint_image($_) . "\n";
  select((select(STDOUT), $| = 1)[0]);  # Flush.
}
'''

fingerprint_pipe_ary = []

def init_fingerprint_pipe():
  # This function is not thread-safe.

  if not fingerprint_pipe_ary:
    import subprocess
    env = dict(os.environ)
    env['PERL__CODE'] = FINGERPRINT_IMAGE_PERL_CODE
    # Line-buffering seems to work with fast flushes in Perl and Python.
    # TODO(pts): Catch OSError.
    p = subprocess.Popen(('perl', '-we', '#fingerprint_image\neval $ENV{PERL__CODE}; die $@ if $@'), stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
    fingerprint_pipe_ary.append(p)
    line = p.stdout.readline()
    if line != '! fingerprint_image ready\n':
      # TODO(pts): Call p.wait if line is empty etc.
      # TODO(pts): Don't init again if first one failed.
      raise IOError('fingerprint_image init failed.')
  return fingerprint_pipe_ary[0]


def fingerprint_image_with_perl(filename):
  # This function is not thread-safe.
  #
  # Dependency: sudo apt-get install libgraphics-magick-perl
  p = init_fingerprint_pipe()
  filename = str(filename)
  if '\0' in filename or '\n' in filename:
    raise ValueError('Unsupported filename: %r' % filename)
  p.stdin.write('%s\n' % filename)
  p.stdin.flush()  # Automatic, just to make sure.
  fp = p.stdout.readline()
  if not fp:
    raise IOError('Unexpected EOF from fingerprint_image pipe: %s' % filename)
  fp = fp.rstrip('\n')
  if not fp:
    raise IOError('Unexpected empty line from fingerprint_image pipe.' % filename)
  if fp.startswith('! '):
    # Filename is usually included.
    raise IOError('Graphics::Magick error: %s' % fp[2:])
  if not (len(fp) == 44 and fp[-1] == '='):
    raise IOError('Invalid fingerprint syntax for: %s' % filename)
  return fp


def fingerprint_image(filename, _use_impl_ary=[]):
  """Computes and returns a find visual image fingerprint.

  This function is not thread-safe. Don't call it from multiple threads at
  the same time.

  Don't call this on non-images (e.g. videos or animated gifs), it may be
  slow.

  The output of this function seems to be bit-by-bit identical across
  platforms and implementations:

  * _with_pgmagick, _with_perl, _with_gm_convert
  * i386, amd64
  * Ubuntu 10.04, Ubuntu 14.04
  * GraphicsMagick 1.3.5, GraphicsMagick 1.3.18
  * findimagedupes -v fp -n, media_scan.py

  This function silently ignores image processing warnings such as
  ``Premature end of JPEG file'' and ``premature end of data segment''.

  Args:
    filename: The name of the file containing an image. Must be in a format
      supported by GraphicsMagick. Don't pass non-images (e.g. videos or
      animated gifs), it may be slow.
    _use_impl_ary: Implementation detail, don't specify it. Contain an empty
      list or a 1-element list of the implementation function to use. If empty,
      the best available implementation will be autodetected and appended.
  Returns:
    A 256-bit string encoded as base64 in 44 bytes, ending with '='. It is
    the same as the output of `findimagedupes -v fp -n'. The 256-bit string
    contains an uncompressed 16x16 1-bit-per-pixel image. Based on the
    fingerprints it's possible to assess how similar two uncropped images
    are visually. findimagedupes calculates the number of 1-bits in the xor
    of the 256-bit fingerprints, and it considers the two images are
    identical iff the xor has at most 25 1-bits. See also:
    https://github.com/pts/pyfindimagedupes .
  Raises:
    IOError: If fingerprinting has failed.
    NotImplementedError: If no working implementation has been detected.
  """

  if not _use_impl_ary:
    try:
      import pgmagick
      _use_impl_ary.append(fingerprint_image_with_pgmagick)  # Fastest.
    except ImportError:
      pass
    if not _use_impl_ary:
      import subprocess
      try:
        exit_code = subprocess.call(
          ('perl', '-mGraphics::Magick', '-e0'), stderr=subprocess.PIPE)
      except OSError:
        exit_code = -1
      if not exit_code:
        _use_impl_ary.append(fingerprint_image_with_perl)  # Medium speed.
    if not _use_impl_ary:
      import subprocess
      try:
        p = subprocess.Popen(
            ('gm', 'convert', 'xc:#000', '-sample', '1x1!', 'mono:-'),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
      except OSError:
        p, exit_code = None, -1
      if p:
        try:
          data, _ = p.communicate('')
        finally:
          exit_code = p.wait()
      if not exit_code and data == '\0':
        _use_impl_ary.append(fingerprint_image_with_gm_convert)  # Slowest.
    if not _use_impl_ary:
      raise NotImplementedError(
          'No fingerpint_image backend found, '
          'install pgmagick or graphicsmagick.')

  return _use_impl_ary[0](fix_gm_filename(filename))


# ---


def is_animated_gif(f, do_read_entire_file=False):
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

  header = f.read(13)
  if len(header) < 13 or not (
      header.startswith('GIF87a') or header.startswith('GIF89a')):
    raise ValueError('Not a GIF file.')
  pb = ord(header[10])
  if pb & 128:  # Global Color Table present.
    read_all(f, 6 << (pb & 7))  # Skip the Global Color Table.
  has_repeat = False
  has_delay = False
  frame_count = 0
  while 1:
    b = ord(read_all(f, 1))
    if b == 0x3B:  # End of file.
      break
    elif b == 0x21:  # Extension introducer.
      b = ord(read_all(f, 1))
      if b == 0xff:  # Application extension.
        ext_id_size = ord(read_all(f, 1))
        ext_id = read_all(f, ext_id_size)
        if ext_id == 'NETSCAPE2.0':  # For the number of repetitions.
          if not do_read_entire_file:
            return True
          has_repeat = True
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
        # Graphic Control extension, delay for animation.
        if b == 0xf9 and ext_data[1 : 3] != '\0\0':
          if not do_read_entire_file:
            return True
          has_delay = True
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
  return bool(frame_count > 1 or has_repeat or has_delay)


def is_animated_gif_cached(f, data):
  # data is the first few bytes of f.

  if len(data) >= 16:
    try:
      return is_animated_gif(cStringIO.StringIO(data))
    except ValueError, e:
      se = str(e)
      if not se.startswith('Short read '):
        return False
  old_ofs = f.tell()
  f.seek(0)
  try:
    try:
      return is_animated_gif(f)
    except ValueError, e:
      return False
  finally:
    f.seek(old_ofs)


def get_jpeg_dimensions(f):
  """Returns (width, height) of a JPEG file.

  Args:
    f: An object supporting the .read(size) method. Should be seeked to the
        beginning of the file.
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

  data = f.read(4)
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
  assert 0, 'Internal JPEG parser error.'


def get_jpeg_dimensions_cached(f, data):
  # data is the first few bytes of f.

  if len(data) >= 4:
    try:
      return get_jpeg_dimensions(cStringIO.StringIO(data))
    except ValueError, e:
      se = str(e)
      if not se.startswith('Short read '):
        return None, None
  old_ofs = f.tell()
  f.seek(0)
  try:
    try:
      return get_jpeg_dimensions(f)
    except ValueError, e:
      return None, None
  finally:
    f.seek(old_ofs)


def get_brn_dimensions(f):
  """Returns (width, height) of a BRN file.

  Args:
    f: An object supporting the .read(size) method. Should be seeked to the
        beginning of the file.
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

  data = f.read(7)
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
    return None, None


def get_brn_dimensions_cached(f, data):
  # data is the first few bytes of f.

  if len(data) >= 8:
    try:
      return get_brn_dimensions(cStringIO.StringIO(data))
    except ValueError, e:
      se = str(e)
      if not se.startswith('Short read '):
        return None, None
  old_ofs = f.tell()
  f.seek(0)
  try:
    try:
      return get_brn_dimensions(f)
    except ValueError, e:
      return None, None
  finally:
    f.seek(old_ofs)


BMP_HEADER_RE = re.compile(r'(?s)BM....\0\0\0\0....([\014-\177])\0\0\0')

LEPTON_HEADER_RE = re.compile(r'\xcf\x84[\1\2][XYZ]')

# All image file formats supported by GraphicsMagick.
# TODO(pts): Try and support 'agif'.
FINGERPRINTABLE_FORMATS = ('gif', 'jpeg', 'png', 'bmp')


def scanfile(path, st, do_th, do_fp):
  if do_th or not (path.endswith('.th.jpg') or path.endswith('.th.jpg.tmp')):
    bufsize = 1 << 20
    width = height = None
    format = '?'
    try:
      f = open(path, 'rb', bufsize)
      try:
        data = f.read(max(bufsize, 4096))
        if not data:
          format = 'empty'
        elif data.startswith('GIF87a') or data.startswith('GIF89a'):
          if is_animated_gif_cached(f, data):
            format = 'agif'  # Animated GIF.
          else:
            format = 'gif'
          if len(data) >= 10:
            width, height = struct.unpack('<HH', data[6 : 10])
        elif data.startswith('\xff\xd8\xff'):
          format = 'jpeg'
          width, height = get_jpeg_dimensions_cached(f, data)
        elif data.startswith('\x0a\x04B\xd2\xd5N\x12'):
          format = 'brn'
          width, height = get_brn_dimensions_cached(f, data)
        elif data.startswith('\211PNG\r\n\032\n'):
          format = 'png'
          if (data[8 : 11] == '\0\0\0' and
              data[12 : 16] == 'IHDR' and len(data) >= 24):
            width, height = struct.unpack('>II', data[16 : 24])
        elif data.startswith('\xcf\x84') and LEPTON_HEADER_RE.match(data):
          format = 'lepton'  # JPEG reencoded by Dropbox lepton.
          # Width and height are not easily available: they need
          # decompression.
        elif data.startswith('BM') and BMP_HEADER_RE.match(data):
          format = 'bmp'
          match = BMP_HEADER_RE.match(data)
          b = ord(match.group(1))
          if b in (12, 64) and len(data) >= 22:
            width, height = struct.unpack('<HH', data[18 : 22])
          elif b in (40, 124) and len(data) >= 26:
            width, height = struct.unpack('<II', data[18 : 26])
        elif (data.startswith('PK\1\2') or data.startswith('PK\3\4') or
              data.startswith('PK\5\6') or data.startswith('PK\7\x08')):
          format = 'zip'
        elif data.startswith('JASC BROWS FILE\0'):
          format = 'jbf'
        else:
          pass  # format = '?'
        s = sha256(data)
        while 1:
          data = f.read(bufsize)
          if not data:
            break
          s.update(data)
      finally:
        f.close()
      info = {'format': format, 'f': path, 'sha256': s.hexdigest(),
              'mtime': int(st.st_mtime), 'size': int(st.st_size)}
      if do_fp and format in FINGERPRINTABLE_FORMATS:
        # xfidfp: extra findimagedupes fingerprint.
        try:
          info['xfidfp'] = fingerprint_image(path)
        except IOError, e:
          e = str(e)
          for suffix in (': ' + path, ' (%s)' % path):
            if e.endswith(suffix):
              e = e[:-len(suffix)]
          print >>sys.stderr, 'warning: fingerprint_image %s: %s' % (path, e)
          info['xfidfp'] = 'err'
      if width is not None and height is not None and width >= 0 and height >= 0:
        info['width'], info['height'] = width, height
      yield info
    except IOError, e:
      print >>sys.stderr, 'error: Reading file %s: %s' % (path, e)


def scan(path_iter, old_files, do_th, do_fp):
  dir_paths = []
  file_items = []
  if getattr(os, 'lstat', None):
    for path in path_iter:
      try:
        st = os.lstat(path)
      except OSError, e:
        if do_th or not (path.endswith('.th.jpg') or path.endswith('.th.jpg.tmp')):
          print >>sys.stderr, 'warning: lstat %s: %s' % (path, e)
        st = None
      if not st:
        pass
      elif stat.S_ISREG(st.st_mode):
        file_items.append((path, st))
      elif stat.S_ISLNK(st.st_mode):
        try:
          st2 = os.stat(path)  # There is a race condition between lstat and stat.
        except OSError, e:  # Typically: dangling symlink.
          if do_th or not (path.endswith('.th.jpg') or path.endswith('.th.jpg.tmp')):
            print >>sys.stderr, 'warning: stat %s: %s' % (path, e)
          st2 = None
        if st2 and stat.S_ISREG(st2.st_mode):
          file_items.append((path, st2))
        # We don't follow symlinks pointing to directories.
      elif stat.S_ISDIR(st.st_mode):
        dir_paths.append(path)
  else:  # Running on a system which doesn't support symlinks.
    for path in path_iter:
      try:
        st = os.stat(path)
      except OSError, e:
        if do_th or not (path.endswith('.th.jpg') or path.endswith('.th.jpg.tmp')):
          print >>sys.stderr, 'warning: stat %s: %s' % (path, e)
        st = None
      if not st:
        pass
      elif stat.S_ISREG(st.st_mode):
        file_items.append((path, st))
      elif stat.S_ISDIR(st.st_mode):
        dir_paths.append(path)

  dir_paths.sort()
  dir_paths.reverse()
  file_items.sort()
  file_items.reverse()
  while file_items:
    path, st = file_items.pop()
    old_item = old_files.get(path)
    if (not old_item or old_item[0] != st.st_size or
        old_item[1] != int(st.st_mtime)):
      #print >>sys.stderr, 'info: Scanning: %s' % path
      for info in scanfile(path, st, do_th, do_fp):
        yield info
  while dir_paths:
    path = dir_paths.pop()
    subpaths = os.listdir(path)
    if path != '.':
      for i in xrange(len(subpaths)):
        subpaths[i] = os.path.join(path, subpaths[i])
    for info in scan(subpaths, old_files, do_th, do_fp):
      yield info


def add_old_files(line_source, old_files):
  for line in line_source:
    line = line.rstrip('\r\n')
    i = line.find(' f=')
    if i < 0:
      raise ValueError('f= not found.')
    info = {'f': line[line.find('=', i) + 1:]}
    for item in line[:i].split(' '):
      kv = item.split('=', 1)
      if len(kv) != 2:
        raise ValueError('Expected key=value, got: %s' % kv)
      info[kv[0]] = kv[1]
    #print info
    try:
      old_files[info['f']] = (int(info['size']), int(info['mtime']))
    except (KeyError, ValueError):
      pass


def format_info(info):
  output = [' %s=%s' % k_v for k_v in sorted(info.iteritems()) if k_v[0] != 'f']
  path = info.get('f')
  if path is not None:
    output.append(' f=%s' % path)  # Emit ` f=' last.
  if output:
    output[0] = output[0][1:]  # Remove leading space.
  output.append('\n')
  return ''.join(output)


def main(argv):
  outf = None
  old_files = {}  # Maps paths to (size, mtime) pairs.
  i = 1
  do_th = True
  do_fp = False
  while i < len(argv):
    arg = argv[i]
    i += 1
    if arg == '--':
      break
    if arg == '-' or not arg.startswith('-'):
      i -= 1
      break
    if arg.startswith('--old='):
      old_filename = arg.split('=', 1)[1]
      f = open(old_filename)
      try:
        add_old_files(f, old_files)
      finally:
        f.close()
      # TODO(pts): Explicit close.
      outf = open(old_filename, 'a', 0)
    elif arg.startswith('--th='):
      value = arg[arg.find('=') + 1:].lower()
      do_th = value in ('1', 'yes', 'true', 'on')
    elif arg.startswith('--fp=') or arg.startswith('--xfidfp='):
      value = arg[arg.find('=') + 1:].lower()
      do_fp = value in ('1', 'yes', 'true', 'on')
    else:
      sys.exit('Unknown flag: %s' % arg)
  if outf is None:
    # For unbuffered appending.
    outf = os.fdopen(sys.stdout.fileno(), 'a', 0)
  for info in scan(argv[i:], old_files, do_th, do_fp):  # Not in original order.
    outf.write(format_info(info))
    outf.flush()


if __name__ == '__main__':
  sys.exit(main(sys.argv))
