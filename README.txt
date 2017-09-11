mediafileinfo.py: Get parameters and dimension of media files.
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
mediafileinfo.py is a self-contained Python 2.x script which detects file
format, codec and dimensions (width and height) of media files (image,
audio, video). It needs just Python 2.4, 2.5, 2.6 or 2.7, no module
installation. mediafileinfo.py can read the input in a streaming way
(without seeking), and it stops reading after the parameters have been found.

Supported video formats for dimension detection include mp4, mkv, webm, flv.

Supported image formats for dimension detection include JPEG, PNG, GIF,
BMP.

Status: production ready for images beta software for video. Please report
bugs on https://github.com/pts/pymediafileinfo/issues , your feedback is
very much appreciated.

System compatibility: Unix, Windows and any operating system supported by
Python.

Advantages of mediafileinfo.py:

* Fast (see FAQ entry Q4) even though it's written in Python, and some of
  the alternatives are written in C or C++.
* Has only a few dependencies: stock Python 2.4, 2.5, 2.6 or 2.7; no
  external package installation needed.
* Isn't fooled by incorrect media metadata: it gets dimensions and
  parameters right from the media data (e.g. width sometimes from the video
  frames themselves).

Disadvantages of mediafileinfo.py:

* Doesn't support many media formats for width and height.
* Doesn't do metadata extraction.

FAQ
~~~
Q1. Can mediafileinfo.py get image authoring metadata (e.g. camera model
    and other EXIF tags), audio metadata (e.g. artist and album and other ID3
    MP3 tags) or video metadata (such as software created)?

A1. No, and it probably won't be able to. The main goal of mediafileinfo.py
    is to get dimensions (width, height), codecs and other parameters
    (e.g. audio sample rate).

Q2. I need many more file formats to be supported in mediafileinfo.py.

A2. For only a couple of new formats, please open a an issue or send a patch.

    If you need many more, see FAQ entry Q3.

Q3. What are the alternative of mediafileinfo.py?

A3.

    * MediaInfo (https://mediaarea.net/en/MediaInfo) is a library in C++
      with the command-line tool mediainfo(1) and also some GUI tools. It
      supports about 100 media formats and codecs, it's actively
      maintained, and it's included in many Linux distributions. It's
      actively maintained (as of 2017-09-11). The library
      doesn't have too many dependencies.

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
      has a small Python class around midentify.sh.

    * mpv_identify.sh
      (https://github.com/mpv-player/mpv/blob/master/TOOLS/mpv_identify.sh)
      is a bit longer shell script similar to midentify.sh, but uses mpv
      (a fork of mplayer) instead of mplayer as a backend.

    * ffprobe (docs: https://trac.ffmpeg.org/wiki/FFprobeTips and
      https://ffmpeg.org/ffprobe.html) is a program written in C for getting
      media file parameters. It's part of the ffmpeg package. It has lots of
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

    Here is a benchmark on 42 random video files of of about 60 MiB each.
    Times are total runtime for all 42 files. Results:

                    mediafileinfo.py  avprobe  midentify.sh  mediainfo
    ------------------------------------------------------------------
    real time                 2.048s   4.965s        8.805s    13.188s
    user time                 1.412s   3.804s        6.584s     8.856s
    sys  time                 0.444s   0.912s        1.844s     2.836s
    prog. language  Python .........  C .....  C (+sh) ....        C++

    All tools were run with their default settings.

    All tools were run twice, and the 2nd run was measured, so that we're not
    measuring disk read speed.

TODO
~~~~

* TODO(pts): Compare it with medid, ffprobe, MediaInfo etc. for all.
* TODO(pts): Diagnose all errors, e.g. lots of Unexpected PreviousTagSize: ...
* TODO(pts): Diagnose all width= and height= missing.
* TODO(pts): Estimate better size limits.
* TODO(pts): Better format=html detection, longer strings etc.
* TODO(pts): Add some audio formats (e.g. MP3, FLAC).
* TODO(pts): Add type=video, type=audio, type=image.
* TODO(pts): Add JPEG-2000 (JPX).
* TODO(pts): Extend media_scan.py with code from here.
* TODO(pts): Add memory limits against large reads everywhere.
* TODO(pts): Add dimension detection (from img_bbox.pl) for more image formats.

__END__