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

import mediafileinfo_detect
import mediafileinfo_formatdb

import cStringIO
import re
import struct
import os
import os.path
import stat
import sys
import time

try:
  from hashlib import sha256  # Needs Python 2.5 or later.
except ImportError:
  if sys.version_info < (2, 5):
    sys.exit('fatal: Install hashlib from PyPI or use Python >=2.5.')

ANALYZE = mediafileinfo_formatdb.FormatDb(mediafileinfo_detect.FORMAT_ITEMS).analyze
ANALYZE_FUNCS_BY_FORMAT = mediafileinfo_detect.ANALYZE_FUNCS_BY_FORMAT

# --- Image fingerprinting for similarity with findimagedupes.pl.
#
# The output is bit-by-bit identical to findimagedupes.pl by Rob Kudla
# (checked with 2.18-4build3 in Debian). (Please note that the Go program
# called findimagedupes is incompatible.)
#
# The relevant function is in `sub getfingerrpint' in
# http://www.ostertag.name/HowTo/findimagedupes.pl
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
# Bit-by-bit identical output to findimagedupes.pl.
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
  # Example: Exception 450: Unsupported marker type 0x6a
  #     With this on Ubuntu 10.04, there will be ``not enough image data''.
  #     But Unbutu 14.04 pgmagick is able to load the image.
  # Example: Exception 350: Extra compression data
  # Example: Exception 350: Incorrect sBIT chunk length
  if ($err and $err !~ /^(?:Warning (?:315|330)|Exception (?:325|350|450)):/) {
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
      die("not enough image data: $file\n");
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

# --- Extended attributes (xattr).
#
# by pts@fazekas.hu at Sun Jan 22 09:48:10 CET 2017
# based on xattr_compat.py by pts@fazekas.hu at Sat Apr  9 14:20:09 CEST 2011
#
# Tested on Linux >=2.6 only.
#

XATTR_KEYS = ('getxattr', 'fgetxattr', 'listxattr', 'flistxattr')

XATTR_DOCS = {
    'getxattr': """Get an extended attribute of a file.

Args:
  filename: Name of the file or directory.
  xattr_name: Name of the extended attribute.
  do_not_follow_symlinks: Bool prohibiting to follow symlinks, False by
    default.
Returns:
  str containing the value of the extended attribute, or None if the file
  exists, but doesn't have the specified extended attribute.
Raises:
  OSError: If the file does not exists or the extended attribute cannot be
    read.
""",
    'listxattr': """List the extended attributes of a file.

Args:
  filename: Name of the file or directory.
  do_not_follow_symlinks: Bool prohibiting to follow symlinks, False by
    default.
Returns:
  (New) list of str containing the extended attribute names.
Raises:
  OSError: If the file does not exists or the extended attributes cannot be
    read.
""",
}


def _xattr_doc(name, function):
  function.__doc__ = XATTR_DOCS[name]
  return name, function


def xattr_impl_xattr():
  import errno

  # sudo apt-get install python-xattr
  # pip install xattr
  #
  # Please note that there is python-pyxattr, it's different.
  import xattr

  XATTR_ENOATTR = getattr(errno, 'ENOATTR', getattr(errno, 'ENODATA', -1))
  del errno  # Save memory.

  def getxattr(filename, attr_name, do_not_follow_symlinks=False):
    try:
      # This does 2 lgetattxattr(2) syscalls, the first to determine size.
      return xattr._xattr.getxattr(
          filename, attr_name, 0, 0, do_not_follow_symlinks)
    except IOError, e:
      if e[0] != XATTR_ENOATTR:
        # We convert the IOError raised by the _xattr module to OSError
        # expected from us.
        raise OSError(e[0], e[1])
      return None

  def listxattr(filename, do_not_follow_symlinks=False):
    # Please note that xattr.listxattr returns a tuple of unicode objects,
    # so we have to call xattr._xattr.listxattr to get the str objects.
    try:
      data = xattr._xattr.listxattr(filename, do_not_follow_symlinks)
    except IOError, e:
      raise OSError(e[0], e[1])
    if data:
      assert data[-1] == '\0'
      data = data.split('\0')
      data.pop()  # Drop last empty string because of the trailing '\0'.
      return data
    else:
      return []

  return dict(_xattr_doc(k, v) for k, v in locals().iteritems()
              if k in XATTR_KEYS)


def xattr_impl_dl():
  import dl  # Only i386, in Python >= 2.4.
  import errno
  import os
  import struct

  LIBC_DL = dl.open(None)
  XATTR_ENOATTR = getattr(errno, 'ENOATTR', getattr(errno, 'ENODATA', -1))
  XATTR_ERANGE = errno.ERANGE
  del errno  # Save memory.
  assert struct.calcsize('l') == 4  # 8 on amd64.

  def getxattr(filename, attr_name, do_not_follow_symlinks=False):
    getxattr_name = ('getxattr', 'lgetxattr')[bool(do_not_follow_symlinks)]
    # TODO(pts): Do we need to protect errno in multithreaded code?
    errno_loc = LIBC_DL.call('__errno_location')
    err_str = 'X' * 4
    value = 'x' * 256
    got = LIBC_DL.call(getxattr_name, filename, attr_name, value, len(value))
    if got < 0:
      LIBC_DL.call('memcpy', err_str, errno_loc, 4)
      err = struct.unpack('i', err_str)[0]
      if err == XATTR_ENOATTR:
        # The file exists, but doesn't have the specified xattr.
        return None
      elif err != XATTR_ERANGE:
        raise OSError(err, '%s: %r' % (os.strerror(err), filename))
      got = LIBC_DL.call(getxattr_name, filename, attr_name, None, 0)
      if got < 0:
        LIBC_DL.call('memcpy', err_str, errno_loc, 4)
        err = struct.unpack('i', err_str)[0]
        raise OSError(err, '%s: %r' % (os.strerror(err), filename))
      assert got > len(value)
      value = 'x' * got
      # We have a race condition here, someone might have changed the xattr
      # by now.
      got = LIBC_DL.call(getxattr_name, filename, attr_name, value, got)
      if got < 0:
        LIBC_DL.call('memcpy', err_str, errno_loc, 4)
        err = struct.unpack('i', err_str)[0]
        raise OSError(err, '%s: %r' % (os.strerror(err), filename))
      return value
    assert got <= len(value)
    return value[:got]

  def listxattr(filename, do_not_follow_symlinks=False):
    listxattr_name = ('listxattr', 'llistxattr')[bool(do_not_follow_symlinks)]
    errno_loc = LIBC_DL.call('__errno_location')
    err_str = 'X' * 4
    value = 'x' * 256
    got = LIBC_DL.call(listxattr_name, filename, value, len(value))
    if got < 0:
      LIBC_DL.call('memcpy', err_str, errno_loc, 4)
      err = struct.unpack('i', err_str)[0]
      if err != XATTR_ERANGE:
        raise OSError(err, '%s: %r' % (os.strerror(err), filename))
      got = LIBC_DL.call(listxattr_name, filename, None, 0)
      if got < 0:
        LIBC_DL.call('memcpy', err_str, errno_loc, 4)
        err = struct.unpack('i', err_str)[0]
        raise OSError(err, '%s: %r' % (os.strerror(err), filename))
      assert got > len(value)
      value = 'x' * got
      # We have a race condition here, someone might have changed the xattr
      # by now.
      got = LIBC_DL.call(listxattr_name, filename, value, got)
      if got < 0:
        LIBC_DL.call('memcpy', err_str, errno_loc, 4)
        err = struct.unpack('i', err_str)[0]
        raise OSError(err, '%s: %r' % (os.strerror(err), filename))
    if got:
      assert got <= len(value)
      assert value[got - 1] == '\0'
      return value[:got - 1].split('\0')
    else:
      return []

  return dict(_xattr_doc(k, v) for k, v in locals().iteritems()
              if k in XATTR_KEYS)


def xattr_impl_ctypes():
  import ctypes  # Python >= 2.6. Tested with both i386 and amd64.
  import errno
  import os

  LIBC_CTYPES = ctypes.CDLL(None, use_errno=True)  # Also: 'libc.so.6'.
  functions = dict((k, getattr(LIBC_CTYPES, k)) for k in (
      'lgetxattr', 'getxattr', 'llistxattr', 'listxattr'))
  LIBC_CTYPES = None  # Save memory.
  XATTR_ENOATTR = getattr(errno, 'ENOATTR', getattr(errno, 'ENODATA', -1))
  XATTR_ERANGE = errno.ERANGE
  del errno  # Save memory.

  def getxattr(filename, attr_name, do_not_follow_symlinks=False):
    getxattr_function = functions[
        ('getxattr', 'lgetxattr')[bool(do_not_follow_symlinks)]]
    value = 'x' * 256
    got = getxattr_function(filename, attr_name, value, len(value))
    if got < 0:
      err = ctypes.get_errno()
      if err == XATTR_ENOATTR:
        # The file exists, but doesn't have the specified xattr.
        return None
      elif err != XATTR_ERANGE:
        raise OSError(err, '%s: %r' % (os.strerror(err), filename))
      got = getxattr_function(filename, attr_name, None, 0)
      if got < 0:
        err = ctypes.get_errno()
        raise OSError(err, '%s: %r' % (os.strerror(err), filename))
      assert got > len(value)
      value = 'x' * got
      # We have a race condition here, someone might have changed the xattr
      # by now.
      got = getxattr_function(filename, attr_name, value, got)
      if got < 0:
        err = ctypes.get_errno()
        raise OSError(err, '%s: %r' % (os.strerror(err), filename))
      return value
    assert got <= len(value)
    return value[:got]

  def listxattr(filename, do_not_follow_symlinks=False):
    listxattr_function = functions[
        ('listxattr', 'llistxattr')[bool(do_not_follow_symlinks)]]
    value = 'x' * 256
    got = listxattr_function(filename, value, len(value))
    if got < 0:
      err = ctypes.get_errno()
      if err != XATTR_ERANGE:
        raise OSError(err, '%s: %r' % (os.strerror(err), filename))
      got = listxattr_function(filename, None, 0)
      if got < 0:
        err = ctypes.get_errno()
        raise OSError(err, '%s: %r' % (os.strerror(err), filename))
      assert got > len(value)
      value = 'x' * got
      # We have a race condition here, someone might have changed the xattr
      # by now.
      got = listxattr_function(filename, value, got)
      if got < 0:
        err = ctypes.get_errno()
        raise OSError(err, '%s: %r' % (os.strerror(err), filename))
    if got:
      assert got <= len(value)
      assert value[got - 1] == '\0'
      return value[:got - 1].split('\0')
    else:
      return []

  return dict(_xattr_doc(k, v) for k, v in locals().iteritems()
              if k in XATTR_KEYS)


def xattr_detect():
  try:
    import ctypes
    import errno
    try:
      LIBC_CTYPES = ctypes.CDLL(None, use_errno=True)  # Also: 'libc.so.6'.
    except OSError:
      LIBC_CTYPES = None
    if (LIBC_CTYPES and getattr(LIBC_CTYPES, 'lgetxattr', None) and
        getattr(errno, 'ENOATTR', getattr(errno, 'ENODATA', 0))):
      return xattr_impl_ctypes
  except ImportError:
    pass

  try:
    import struct
    import dl
    import errno
    try:
      LIBC_DL = dl.open(None)  # Also: dl.open('libc.so.6')
    except dl.error:
      LIBC_DL = None
    if (LIBC_DL and LIBC_DL.sym('memcpy') and LIBC_DL.sym('__errno_location')
        and LIBC_DL.sym('lgetxattr') and
        getattr(errno, 'ENOATTR', getattr(errno, 'ENODATA', 0))):
     return xattr_impl_dl
  except ImportError:
    pass

  # We try this last, because it does 2 syscalls by default.
  try:
    import xattr
    # Earlier versions are buggy.
    if getattr(xattr, '__version__', '') >= '0.2.2':
      return xattr_impl_xattr
  except ImportError:
    pass

  raise NotImplementedError(
      'xattr implementation not found. Please install python-xattr or ctypes.')


# All image file formats supported by GraphicsMagick.
# TODO(pts): Try and support 'agif'.
# TODO(pts): Does it support other image formats mediafileinfo_detect supports?
FINGERPRINTABLE_FORMATS = ('gif', 'jpeg', 'png', 'bmp', 'pbm', 'pgm', 'ppm')


class FileWithHash(object):
  """A readable file which computes a hash as being read."""

  __slots__ = ('f', 'name', 'hash', 'ofs')

  def __init__(self, f, hash, ofs=0):
    self.f, self.name, self.hash, self.ofs = f, f.name, hash, ofs

  def read(self, size):
    data = self.f.read(size)
    self.ofs += len(data)
    self.hash.update(data)
    return data

  def tell(self):
    return self.ofs

  def seek(self, ofs, whence=0):
    if whence == 0:
      ofs -= self.ofs
    elif whence != 1:
      raise ValueError('Unsupported whence: %d' % whence)
    if ofs < 0:
      raise ValueError('Backward seek: %d' % -ofs)
    ofs += self.ofs
    while ofs - self.ofs > 65536:
      if not self.read(65536):
        return
    if ofs > self.ofs:
      self.read(ofs - self.ofs)


def detect_file(filename, filesize, do_fp, do_sha256, filemtime):
  had_error = False
  f, info = None, {}
  try:
    try:
      f = open(filename, 'rb')
    except IOError, e:
      had_error = True
      print >>sys.stderr, 'error: missing file %r: %s' % (filename, e)
      info['error'] = 'bad_open'
    if 'error' not in info:
      if do_sha256:
        fh = FileWithHash(f, sha256())
      else:
        fh = f
      had_error_here, info = True, {'f': filename}
      try:
        info = ANALYZE(
            fh, info, file_size_for_seek=filesize or None,
            analyze_funcs_by_format=ANALYZE_FUNCS_BY_FORMAT)
        had_error_here = False
      except ValueError, e:
        info['error'] = 'bad_data'
        if e.__class__ == ValueError:
          print >>sys.stderr, 'error: bad data in file %r: %s' % (filename, e)
        else:
          print >>sys.stderr, 'error: bad data in file %r: %s.%s: %s' % (
              filename, e.__class__.__module__, e.__class__.__name__, e)
      except IOError, e:
        info['error'] = 'bad_read'
        print >>sys.stderr, 'error: error reading from file %r: %s.%s: %s' % (
            filename, e.__class__.__module__, e.__class__.__name__, e)
      except AssertionError, e:
        info['error'] = 'assert'
        print >>sys.stderr, 'error: error detecting in %r: %s.%s: %s' % (
            filename, e.__class__.__module__, e.__class__.__name__, e)
      except (KeyboardInterrupt, SystemExit):
        raise
      except Exception, e:
        #raise
        info['error'] = 'error'
        print >>sys.stderr, 'error: error detecting in %r: %s.%s: %s' % (
            filename, e.__class__.__module__, e.__class__.__name__, e)
      if not info.get('format'):
        info['format'] = '?'
      try:
        # header_end_offset, hdr_done_at: Offset we reached after parsing
        # headers.
        info['hdr_done_at'] = int(f.tell())
      except (IOError, OSError, AttributeError):
        pass
      if had_error_here:
        had_error = True
      elif info['format'] == '?':
        print >>sys.stderr, 'warning: unknown file format: %r' % filename
        had_error = True

    if info.get('error') in (None, 'bad_data'):
      try:
        if do_sha256:
          bufsize = 65536
          s = fh.hash
          size = fh.ofs
          while 1:
            data = f.read(bufsize)
            if not data:
              info['sha256'] = s.hexdigest()
              info['size'] = size
              break
            size += len(data)
            s.update(data)
        else:
          try:
            f.seek(0, 2)
            info['size'] = int(f.tell())
          except (IOError, OSError):
            info['size'] = 0
      except IOError, e:
        print >>sys.stderr, 'error: error reading from file %r: %s.%s: %s' % (
            filename, e.__class__.__module__, e.__class__.__name__, e)
        info.setdefault('error', 'bad_read_sha256')
  finally:
    if f is not None:
      f.close()

  if filesize is not None:
    if info.get('size') is None:
      info['size'] = filesize
    elif info['size'] != filesize:
      print >>sys.stderr, (
          'warning: file size mismatch for %r: '
          'from_fileobj=%d from_stat=%d' %
          (filename, info['size'], filesize))
      had_error = True
  if filemtime is not None:
    info.setdefault('mtime', int(filemtime))

  if (info.get('error') in (None, 'bad_data') and do_fp and
      info['format'] in FINGERPRINTABLE_FORMATS):
      try:
        info['xfidfp'] = fingerprint_image(filename)
      except IOError, e:
        e = str(e)
        for suffix in (': ' + filename, ' (%s)' % filename):
          if e.endswith(suffix):
            e = e[:-len(suffix)]
        print >>sys.stderr, 'warning: fingerprint_image %s: %s' % (filename, e)
        had_error = True
        info['xfidfp'] = 'err'

  if info.get('error'):
    had_error = True
  return info, had_error


def scan(path_iter, old_files, do_th, do_fp, do_sha256, do_mtime, tags_impl, skip_recent_sec):
  dir_paths = []
  file_items = []  # List of (path, st, tags, symlink, is_symlink).
  symlink = None
  if callable(getattr(os, 'lstat', None)):
    stat_func = os.lstat
    for path in path_iter:
      try:
        st = os.lstat(path)
      except OSError, e:
        if do_th or not (path.endswith('.th.jpg') or path.endswith('.th.jpg.tmp')):
          print >>sys.stderr, 'warning: lstat %s: %s' % (path, e)
        st = None
      if not st:
        pass
      # TODO(pts): Indicate block device, character device, pipe and socket
      # nodes as well. Currently they are just omitted from the output.
      elif stat.S_ISREG(st.st_mode):
        tags = None  # Don't emit tags= with --tags=false.
        if tags_impl:
          # We could save ctime= to old_files, then compare it to st_ctime,
          # and if it's equal, omit the (slow, disk-seeking) call to tags_impl
          # below, because the tags haven't changed.
          try:
            tags = ','.join(tags_impl(path).strip().split())
          except OSError, e:
            print >>sys.stderr, 'warning: tags %s: %s' % (path, e)
        file_items.append((path, st, tags, None, False))
      elif stat.S_ISLNK(st.st_mode):
        try:
          symlink = os.readlink(path)
        except OSError, e:
          # This shouldn't happen. It means that the symlink has vanished
          # between the lstat and the readlink.
          print >>sys.stderr, 'warning: symlink %s: %s' % (path, e)
          symlink = '%'
        try:
          st2 = os.stat(path)  # There is a race condition between lstat and stat.
        except OSError, e:  # Typically: dangling symlink.
          if do_th or not (path.endswith('.th.jpg') or path.endswith('.th.jpg.tmp')):
            print >>sys.stderr, 'warning: stat %s: %s' % (path, e)
          st2 = None
        # Don't do anything special with symlinks to directories.
        if st2 and stat.S_ISREG(st2.st_mode):
          tags = None  # Don't emit tags= with --tags=false.
          if tags_impl:
            # We use os.path.realpath to avoid EPERM on lgetattr on symlink.
            try:
              tags = ','.join(tags_impl(os.path.realpath(path)).strip().split())
            except OSError, e:
              print >>sys.stderr, 'warning: symlink tags %s: %s' % (path, e)
          file_items.append((path, st2, tags, symlink, False))
        else:
          # No tags for symlinks. This is to avoid EPERM on lgetattr.
          tags = None
          if tags_impl:
            tags = ''
          file_items.append((path, st, tags, symlink, True))
        # We don't follow symlinks pointing to directories.
      elif stat.S_ISDIR(st.st_mode):
        dir_paths.append(path)
  else:  # Running on a system which doesn't support symlinks.
    stat_func = os.stat
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
        file_items.append((path, st, None, False))
      elif stat.S_ISDIR(st.st_mode):
        dir_paths.append(path)

  dir_paths.sort()
  dir_paths.reverse()
  file_items.sort()
  file_items.reverse()
  while file_items:
    path, st, tags, symlink, is_symlink = file_items.pop()
    if skip_recent_sec is not None:
      try:
        st = stat_func(path)
      except OSError, e:
        print >>sys.stderr, 'warning: restat %r: %s' % (path, e)
        continue
      if st.st_mtime + skip_recent_sec >= time.time():
        continue
    old_item = old_files.get(path)
    #assert path != 'blah.pl', [old_item, (st.st_size, int(st.st_mtime), tags, symlink, is_symlink)]
    if (not old_item or old_item[0] != st.st_size or
        (do_mtime and old_item[1] != int(st.st_mtime)) or
        old_item[3] != symlink or
        old_item[4] != is_symlink or
        # If old_item[2] is None (we don't know the tags) and tags == '',
        # this doesn't match. Good.
        (tags_impl and tags != old_item[2])):
      #print >>sys.stderr, 'info: Scanning: %s' % path
      if do_th or not (path.endswith('.th.jpg') or path.endswith('.th.jpg.tmp')):
        if is_symlink:
          info = {'format': 'symlink', 'f': path, 'symlink': symlink,
                  'size': len(symlink)}
        else:
          info, _ = detect_file(path, int(st.st_size), do_fp, do_sha256, None)
          if tags is not None:
            info['tags'] = tags  # Save '', don't save None.
          if symlink is not None:
            info['symlink'] = symlink
        if do_mtime:
          info['mtime'] = int(st.st_mtime)
        if info.get('error') in (None, 'bad_data', 'bad_read_sha256'):
          yield info
  while dir_paths:
    path = dir_paths.pop()
    try:
      subpaths = os.listdir(path)
    except OSError, e:
      print >>sys.stderr, 'error: listdir %r: %s' % (path, e)
      subpaths = []
    if path != '.':
      for i in xrange(len(subpaths)):
        subpaths[i] = os.path.join(path, subpaths[i])
    for info in scan(subpaths, old_files, do_th, do_fp, do_sha256, do_mtime, tags_impl, skip_recent_sec):
      yield info


PERCENT_HEX_RE = re.compile(r'%([0-9a-fA-F]{2})')


def add_old_files(line_source, old_files):
  _percent_hex_re = PERCENT_HEX_RE
  for line in line_source:
    line = line.rstrip('\r\n')
    i = line.find(' f=')
    if i < 0:
      raise ValueError('f= not found: %d' % line_source.tell())
    info = {'f': line[line.find('=', i) + 1:]}
    for item in line[:i].split(' '):
      kv = item.split('=', 1)
      if len(kv) != 2:
        raise ValueError('Expected key=value, got: %s in line %r' % (kv, line))
      if kv[0] in info:
        raise ValueError('Duplicate key %r in info line %r' % (kv[0], line))
      info[kv[0]] = _percent_hex_re.sub(
          lambda match: chr(int(match.group(1), 16)), kv[1])
    #print info
    is_symlink = info['format'] == 'symlink'
    if is_symlink:
      dtags = ''
    else:
      dtags = None
    if info.get('mtime'):
      mtime = int(info['mtime'])
    else:
      mtime = None
    try:
      old_files[info['f']] = (int(info['size']), mtime,
                              info.get('tags', dtags), info.get('symlink'),
                              is_symlink)
    except (KeyError, ValueError):
      pass


def format_info(info):
  def format_value(v):
    if isinstance(v, bool):
      return int(v)
    if isinstance(v, float):
      if abs(v) < 1e15 and int(v) == v:  # Remove the trailing '.0'.
        return int(v)
      return repr(v)
    if isinstance(v, (int, long)):
      return str(v)
    if isinstance(v, str):
      # Faster than a regexp if there are no matches.
      return (v.replace('%', '%25').replace('\0', '%00').replace('\n', '%0A')
              .replace(' ', '%20'))
    raise TypeError(type(v))
  output = ['format=%s' % format_value(info.get('format') or '?')]
  # TODO(pts): Display brands list.
  output.extend(
      ' %s=%s' % (k, format_value(v))
      for k, v in sorted(info.iteritems())
      if k != 'f' and k != 'format' and
      not isinstance(v, (tuple, list, dict, set)))
  filename = info.get('f')
  if filename is not None:
    if '\n' in filename or '\0' in filename:
      raise ValueError('Invalid byte in filename: %r' % filename)
    output.append(' f=%s' % filename)  # Emit ` f=' last.
  output.append('\n')
  return ''.join(output)


def get_file_info(filename, stat_obj):
  do_fp = do_sha256 = False
  return detect_file(filename, stat_obj.st_size, do_fp, do_sha256,
                     stat_obj.st_mtime)


# --- From quick_scan.py .


def get_quick_info(filename, stat_obj):
  return {'mtime': int(stat_obj.st_mtime), 'size': stat_obj.st_size,
          'f': filename}, False


def get_symlink_info(filename, stat_obj):
  info = {'format': 'symlink', 'mtime': int(stat_obj.st_mtime), 'f': filename}
  try:
    info['symlink'] = os.readlink(filename)
    info['size'] = len(info['symlink'])
  except OSError, e:
    print >>sys.stderr, 'error: readlink: %s' % (filename, e)
    return info, True
  return info, False


def info_scan(dirname, outf, get_file_info_func, skip_recent_sec):
  """Prints results sorted by filename."""
  had_error = False
  try:
    entries = os.listdir(dirname)
  except OSError, e:
    print >>sys.stderr, 'error: listdir %r: %s' % (dirname, e)
    had_error = True
    entries = ()
  files, subdirs = [], []
  for entry in entries:
    if dirname == '.':
      filename = entry
    else:
      filename = os.path.join(dirname, entry)
    try:
      stat_obj = os.lstat(filename)
    except OSError, e:
      print >>sys.stderr, 'error: lstat %r: %s' % (filename, e)
      stat_obj = None
    if stat_obj is None:
      had_error = True
    elif stat.S_ISDIR(stat_obj.st_mode):
      subdirs.append(filename)
    elif (stat.S_ISREG(stat_obj.st_mode) or
          stat.S_ISLNK(stat_obj.st_mode)):
      files.append((filename, stat_obj))
  for filename, stat_obj in sorted(files):
    if stat.S_ISLNK(stat_obj.st_mode):
      info, had_error_here = get_symlink_info(filename, stat_obj)
    else:
      if skip_recent_sec is not None:
        try:
          stat_obj = os.lstat(filename)
        except OSError, e:
          print >>sys.stderr, 'error: lstat %r: %s' % (filename, e)
          had_error = True
          continue
        if stat_obj.st_mtime + skip_recent_sec >= time.time():
          continue
      info, had_error_here = get_file_info_func(filename, stat_obj)
    if had_error_here:
      had_error = True
    elif info.get('format') == '?':
      print >>sys.stderr, 'warning: unknown file format: %r' % filename
      had_error = True
    outf.write(format_info(info))
    outf.flush()
  for filename in sorted(subdirs):
    had_error |= info_scan(filename, outf, get_file_info_func, skip_recent_sec)
  return had_error


def process(filename, outf, get_file_info_func, skip_recent_sec):
  """Prints results sorted by filename."""
  try:
    stat_obj = os.lstat(filename)
  except OSError, e:
    print >>sys.stderr, 'error: missing file %r: %s' % (filename, e)
    return True
  if stat.S_ISDIR(stat_obj.st_mode):
    return info_scan(filename, outf, get_file_info_func, skip_recent_sec)
  elif stat.S_ISREG(stat_obj.st_mode):
    if (skip_recent_sec is not None and
        stat_obj.st_mtime + skip_recent_sec >= time.time()):
      return True
    info, had_error = get_file_info_func(filename, stat_obj)
    outf.write(format_info(info))
    outf.flush()
    if not had_error and info.get('format') == '?':
      print >>sys.stderr, 'warning: unknown file format: %r' % filename
      had_error = True
    return had_error
  elif stat.S_ISLNK(stat_obj.st_mode):
    info, had_error = get_symlink_info(filename, stat_obj)
    outf.write(format_info(info))
    outf.flush()
    return had_error
  else:
    return False


# ---


def main(argv):
  outf = None
  old_files = {}  # Maps paths to (size, mtime) pairs.
  i = 1
  do_th = True
  do_fp = False
  do_tags = False
  do_sha256 = True
  do_mtime = True
  mode = 'scan'
  # If not None, skip scanning files whose mtime is more recent than the
  # specified amount in seconds (relative to now).
  skip_recent_sec = None
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
    elif arg in ('--scan', '--mode=scan'):
      mode = 'scan'
    elif arg in ('--info', '--mode=info'):
      mode = 'info'
    elif arg in ('--quick', '--mode=quick'):
      mode = 'quick'
    elif arg.startswith('--mode='):
      sys.exit('Invalid flag value: %s' % arg)
    elif arg.startswith('--th='):
      value = arg[arg.find('=') + 1:].lower()
      do_th = value in ('1', 'yes', 'true', 'on')
    elif arg.startswith('--tags='):
      value = arg[arg.find('=') + 1:].lower()
      do_tags = value in ('1', 'yes', 'true', 'on')
    elif arg.startswith('--sha256=') or arg.startswith('--hash='):
      value = arg[arg.find('=') + 1:].lower()
      do_sha256 = value in ('1', 'yes', 'true', 'on')
    elif arg.startswith('--mtime='):
      value = arg[arg.find('=') + 1:].lower()
      do_mtime = value in ('1', 'yes', 'true', 'on')
    elif arg.startswith('--fp=') or arg.startswith('--xfidfp='):
      value = arg[arg.find('=') + 1:].lower()
      do_fp = value in ('1', 'yes', 'true', 'on')
    elif arg.startswith('--skip-recent-sec='):
      skip_recent_sec = int(arg[arg.find('=') + 1:].lower())
    elif arg == '--list-formats':
      sys.stdout.write('%s\n' % ' '.join(sorted(
          mediafileinfo_detect.FORMAT_DB.formats)))
      return
    else:
      sys.exit('Unknown flag: %s' % arg)
  if outf is None:
    # For unbuffered appending.
    outf = os.fdopen(os.dup(sys.stdout.fileno()), 'a', 0)
  tags_impl = None
  if do_tags:
    tags_impl = lambda filename, getxattr=xattr_detect()()['getxattr']: (
        getxattr(filename, 'user.mmfs.tags', True) or '')
  had_error = False
  if mode == 'scan':
    # Files are yielded in deterministic (sorted) order, not in original argv
    # order. This is for *.jpg.
    for info in scan(argv[i:], old_files, do_th, do_fp, do_sha256, do_mtime, tags_impl, skip_recent_sec):
      outf.write(format_info(info))  # Files with some errors are skipped.
      outf.flush()
    # TODO(pts): Detect had_error in scan.
  elif mode in ('quick', 'info'):
    prefix = '.' + os.sep
    get_file_info_func = (get_file_info, get_quick_info)[mode == 'quick']
    # Keep the original argv order, don't sort.
    for filename in argv[i:]:
      if filename.startswith(prefix):
        filename = filename[len(prefix):]
      had_error |= process(filename, outf, get_file_info_func, skip_recent_sec)
  else:
    raise AssertionError('Unknown mode: %s' % mode)
  if had_error:
    sys.exit(2)


if __name__ == '__main__':
  sys.exit(main(sys.argv))
