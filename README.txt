mediafileinfo.py: Get parameters and dimension of media files.
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
mediafileinfo.py is a self-contained Python 2.x script which detects file
format, media parameters (e.g. codec, dimensions (width and height), number
of audio channels) of media files (image, audio, video). It needs just
Python 2.4, 2.5, 2.6 or 2.7, no module installation. mediafileinfo.py can
read the input in a streaming way (without seeking), and it stops reading
after the media parameters have been found.

mediafileinfo.py can detect >130 file formats, among those it can display
dimensions and codec of media formats mp4, mkv, mpeg-ts, mpeg-ps, wmv, avi,
webm, flv, asf, wma, etc., it can display dimensions of image formats JPEG,
PNG, GIF, BMP, PNM, TIFF etc., and it can display codec and audio parameters
of audio formats mp3, flac, wav etc.

Status: production ready for images, beta software for video. Please report
bugs on https://github.com/pts/pymediafileinfo/issues , your feedback is
very much appreciated.

System compatibility: Unix, Windows and any operating system supported by
Python.

Advantages of mediafileinfo.py:

* It's fast (see FAQ entry Q4) even though it's written in Python, and some of
  the alternatives are written in C or C++.
* It has only a few dependencies: stock Python 2.4, 2.5, 2.6 or 2.7; no
  package installation needed. It doesn't work with Python 3, but see Q14
  for interacting with it from Python 3 code.
* It isn't not fooled by incorrect media metadata: it gets media parameters
  directly from the media data (e.g. width sometimes from the video
  bitstream).

Disadvantages of mediafileinfo.py:

* It doesn't support many media formats for width and height.
* It isn't able to get metadata (such as author and EXIF tags).

Usage on Unix (don't type the leading $):

  $ curl -L -o mediafileinfo.py https://github.com/pts/pymediafileinfo/raw/master/mediafileinfo.py
  $ chmod 755 mediafileinfo.py
  $ ./mediafileinfo.py *.mp4
  (prints one line per file)

FAQ
~~~
Q0. Which file formats does mediafileinfo.py support?

A0. Get a full list of file formats that can be detected (by their
    signature) by running `mediafileinfo.py --list-formats'. This will
    include >130 file formats.

    Please note that media parameters (e.g. width, height and codec) cannot
    be found in all file formats, e.g. format=zip doesn't have width, and
    format=pdf would be too complicated to process (i.e. /MediaBox can be
    in a compressed object).

    See also Q11 for more details of image formats.

Q1. Can mediafileinfo.py get image authoring metadata (e.g. camera model
    and other EXIF tags), audio metadata (e.g. artist and album and other ID3
    MP3 tags) or video metadata (such as software created)?

A1. No, and it probably won't be able to. The main goal of mediafileinfo.py
    is to get dimensions (width, height), codecs and other media parameters
    (e.g. audio sample rate).

Q2. I need many more file formats to be supported in mediafileinfo.py.

A2. For only a few new formats, please open an issue or send a patch.

    If you need many more, see FAQ entry Q3.

Q3. What are the alternatives of mediafileinfo.py?

A3. Some alternatives are:

    * mediafileinfo.pl (http://github.com/pts/plmediafileinfo) is a Perl
      script similar to mediafileinfo.py: it has the same output format, it
      has similarly few dependencies (only Perl 5 with built-in packages).
      It supports only a few (about 5) media formats though.

    * MediaInfo (https://mediaarea.net/en/MediaInfo) is a library in C++
      with the command-line tool mediainfo(1) and also some GUI tools. It
      supports about 100 media formats and codecs, it's actively
      maintained (as of 2017-09-11), and it's included in many Linux distributions.
      The library doesn't have too many dependencies.

    * pymediainfo (https://pypi.python.org/pypi/pymediainfo/) is a Python
      library which uses the MediaInfo C++ library as a backend, thus it
      supports about 100 media formats.

    * midentify.sh
      (https://github.com/larsmagne/mplayer/blob/master/TOOLS/midentify.sh)
      is a tiny shell script which calls mplayer with the following flags:
      mplayer -noconfig all -cache-min 0 -vo null -ao null -frames 0 -identify
      . It supports whatever audio and video formats mplayer supports (thus
      no JPEG). Thus it supports more than 100 media formats.

    * https://github.com/linkinpark342/midentify-py/blob/master/midentify.py
      contains a small Python class calling midentify.sh.

    * mpv_identify.sh
      (https://github.com/mpv-player/mpv/blob/master/TOOLS/mpv_identify.sh)
      is a bit longer shell script similar to midentify.sh, but uses mpv
      (a fork of mplayer) instead of mplayer as a backend.

    * ffprobe (docs: https://trac.ffmpeg.org/wiki/FFprobeTips and
      https://ffmpeg.org/ffprobe.html) is a program written in C for getting
      media parameters. It's part of the ffmpeg package. It has lots of
      dependencies (ldd prints more than 80 libraries it depends on), as
      many as ffmpeg has. It supports more than 100 media formats (including
      JPEG and PNG).

      Example command:
      `ffprobe -v error -show_format -show_streams -- file.mp4'.

    * avprobe (docs: https://libav.org/documentation/avprobe.html)
      is similar to ffprobe, but it uses libav (part of the avconv package,
      a fork of ffmpeg) instead of ffmpeg.

      Example command:
      `avprobe -v error -show_format -show_streams -- file.mp4'.

    * flvlib (https://pypi.python.org/pypi/flvlib) is a Python library for
      parsing flv files. It's not able to get width and height.

    * mp4file (https://pypi.python.org/pypi/mp4file) is a Python library for
      parsing mp4 files. It's not able to get width and height.

    * h264bitstream (https://github.com/aizvorski/h264bitstream) is a C++
      library for parsing the output of the H.264 codec. It has code to
      parse the SPS, but no code to compute the width and height from it.

    * php-flvinfo
      (https://github.com/zeldein/php-flvinfo/blob/master/flvinfo.php)
      is a PHP library for parsing flv files. It's able to get width and
      height only for 3 codecs, and 2 of them (vp6 and vp6alpha) are buggy.

    * php-mp4info (https://github.com/chrisdeeming/php-mp4info)
      is a PHP library for parsing mp4 files. It's able to get width and
      height from the metadata (which many mp4 files don't have) or the tkhd
      box (which has incorrect width and height in many mp4 files).

Q4. How fast is mediafileinfo.py?

    It's pretty fast, actually faster than many alternatives for the file
    formats it supports.

    Here is a benchmark on 42 random video files of about 60 MiB each.
    Times are total runtime for all 42 files. Results:

                    mediafileinfo.py  avprobe  midentify.sh  mediainfo
    ------------------------------------------------------------------
    real time                 2.048s   4.965s        8.805s    13.188s
    user time                 1.412s   3.804s        6.584s     8.856s
    sys  time                 0.444s   0.912s        1.844s     2.836s
    prog. language  Python .........  C .....  C (+sh) ....  C++ .....

    All tools were run with their default settings.

    All tools were run twice, and the 2nd run was measured, so that we're not
    measuring disk read speed.

    mediainfo is especially slow because it reads the entire file, not only
    the first few kilobytes.

Q5. Is mediafileinfo.py able to get duration info (e.g. number of
    seconds, number of frames, number of keyframes)?

A5. No, it isn't. Probably this feature won't be added, because it's
    complicated to implement reliably for most video formats.

Q6. Is mediafileinfo.py able to get media parameters, duration info or
    metadata of subtitles and other, non-audio, non-video tracks?

A6. No, it isn't. This feature is not of high priority, but feel free to
    send a patch if you have an implementation.

Q7. Does mediafileinfo.py support MPEG?

A7. mediafileinfo.py can detect MP3 and MPEG files (mpeg-video (elementary
    stream), mpeg-adts (audio elementary stream), mpeg-ps, mpeg-ts) and get
    media parameters (e.g. codec, dimensions), with the following restrictions:

    * If there is junk in front of the MPEG header in the file, the file is
      not detected as MPEG.
    * Raw MPEG audio streams without MPEG-ADTS frame wrapping are not detected.
      (Does this even exist? Aren't just junk in the beginning of the
      mpeg-adts file?)
    * Media parameters are not found from some MPEG-TS files, especially
      if the PAT frame is not near the beginning of the file.

Q8. What scanning tools are available in addition to mediafileinfo.py?

A8. quick_scan.py is a small Python script which detects size=, mtime= and
    symlink= only. Its functionality is also avaiable as `mediafileinfo.py
    --quick' and `media_scan.py --quick'. It is very quick, because it
    doesn't even open the files.

    mediafilefileinfo.py detects size=, mtime=, symlink=, format= and
    media parameters (e.g. width= and height=). Its functionality is also
    available as `media_scan.py --info'. It is quick, because it reads only
    the first few kilobytes of each file.

    media_scan.py detects size=, mtime=, symlink=, format=, media parameters
    (e.g. width= and height=), sha256= and xfidfp= (visual fingerprint of
    images using the findimagedupes.pl algorithm, specify --fp=yes to
    enable). Its the default `media_scan.py --scan'.

Q9. mediafileinfo.py doesn't support my favorite file format, can you add
    support?

A9. Please add an issue on https://github.com/pts/pymediafileinfo/issues .

Q10. mediafileinfo.py doesn't detect or analyze (media parameters) my
     favorite file format, can you fix it?

A10. Please report a bug on https://github.com/pts/pymediafileinfo/issues ,
     and attach the offending file.

Q11. How many image formats does mediafileinfo.py support?

A11. Dozens, and it can get width and height from most of them.

     As of 2020-03-25, all web image formats (JPEG, JPEG 2000, JPEG XR, WebP,
     WebP lossless, GIF, PNG, APNG, MNG, TIFF, SVG, PDF, XBM, BMP, ICO, HEIF)
     are supported. Except for PDF, getting width and height is supported for
     these web image formats.

     Web image formats include:

     * https://en.wikipedia.org/wiki/Comparison_of_web_browsers#Image_format_support (15 formats)
     * https://en.wikipedia.org/wiki/Comparison_of_browser_engines_(graphics_support) (10 formats)
     * https://developer.mozilla.org/en-US/docs/Web/Media/Formats/Image_types (9 formats)
     * https://developer.akamai.com/legacy/learn/Images/common-image-formats.html (6 formats)

     mediafileinfo.py also supports all image formats supported by these
     libraries and tools:

     * gdk-pixbuf-2.40.0, GNOME Image Viewer == Eye of GNOME, GQview
       (16 formats)
     * qtimage and qtimageformats-5.14.1, KDE Gwenview (16 formats)
     * imlib-1.9.15 (8 formats)
     * imlib2-1.6.1, qiv (13 formats)
     * libgd-2.2.5 (12 formats)
     * cups-filters-1.27.2, imagetoraster, cupsfilters/image.c (11 formats)
     * xv-3.10a (19 formats)
     * xloadimage-4.1 (19 formats)
     * leptonica-1.79.0 (11 formats)
     * sam2p-0.49.4 (13 formats)

     mediafileinfo.py supports some (but far from all) image formats
     supported by these libraries and tools:

     * Pillow-7.0.0, PIL, Python Imaging Library (45 formats)
     * netpbm-10.73.30 (69 formats)
     * Image Alchemy 1.11
       (http://fileformats.archiveteam.org/wiki/Image_Alchemy) (95 formats)
     * ImageMagick-6.9.10, convert, display, identify (218 formats)

     mediafileinfo.py also supports old Mac (Apple) image formats PICT,
     MacPaint, QTIF and PNOT.

Q12. If multiple magic numbers match, which one does mediafileinfo.py report?

A12. mediafileinfo.py sorts matching file formats by (approximate)
     number of bits matched, and picks the top one. For example, if a format
     starts with '\0\0\0', and the mp4 format has header[4 : 8] == 'ftyp',
     and the file starts with '\0\0\0\x18ftyp', then mediafileinfo.py will
     detect the file as mp4, because that has matched 4 bytes ('ftyp'), and
     the other format only matched 3 bytes (at the beginning). This strategy
     leads to the most likely match even if detection of new file formats
     with short matches get added in the future.

     For the matching, mediafileinfo.py doesn't only look at magic numbers,
     but it also does consistency checks on the first few header fields
     (especially in the first 16 bytes of the file). For example, the XWD
     file format doesn't have any magic number, but it starts with
     header_size (32-bit integer) and file_version (32-bit integer), both of
     which have only a few valid values, and mediafileinfo.py matches XWD
     only if these header values are valid.

Q13. What is the output file format of mediafileinfo.py?

A13. This file format is called ``mediafileinfo'', it's documented here:
     https://github.com/pts/pymediafileinfo/blob/master/mediafileinfo_format.md

     You can detect it by checking the magic number (signature), i.e.
     whether the file startsw with the ASCII string 'format=' without
     quotes.

     Of course, mediafileinfo.py and related tools can detect this file format.

* (end)

__END__


TODO
~~~~

* TODO(pts): Compare it with medid, ffprobe, MediaInfo etc. for all.
* TODO(pts): Diagnose all errors, e.g. lots of Unexpected PreviousTagSize: ...
* TODO(pts): Diagnose all width= and height= missing.
* TODO(pts): Estimate better size limits.
* TODO(pts): Add type=video, type=audio, type=image etc.
* TODO(pts): Add memory limits against large reads everywhere.
* TODO(pts): Add dimension detection (from img_bbox.pl: sub calc and
             my @formats) for more image formats: BioRad,
             FIT, G3, + all from @formats.
             Still, img_bbox.pl has better PostScript and PDF
             analyzing.

__END__
