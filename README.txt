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

FAQ
~~~
Q1. Can mediafileinfo.py extract image authoring metadata (e.g. camera model
    and other EXIF tags), audio metadata (e.g. artist and album and other ID3
    MP3 tags) or video metadata (such as software created)?

A1. No, and it probably won't be able to. The main goal of mediafileinfo.py
    is to extract dimensions (width, height), codecs and other parameters
    (e.g. audio sample rate).

TODO
~~~~

* TODO(pts): Compare it with medid for all (not only h264).
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
