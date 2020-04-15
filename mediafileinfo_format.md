# The mediafileinfo file format #

A mediafileinfo file is a list of entries concatenated after each other. Each entry contains a filename, a file format identifier and a list of key-value pairs describing file metadata (e.g. size, last modification time, checksum) and media parameters (e.g. width, height, codec, audio bitrate). Encoding of all text is UTF-8, line terminator is LF (code 10, `b'\n'`). The format of an entry (with Python syntax) is:

```python
entry = b'format=' + format_value + encoded_info + b' f=' + filename + b'\n'
```

Magic number (file signature) is ASCII `format=`, hex *66 6f 72 6d 61 74 3d*.

Recommended filename extension is `.mfo`.

Example entry:

```
format=mp3 acodec=mp3 anch=2 arate=44100 asbits=16 asubformat=mpeg-1 hdr_done_at=440 id3_version=2.3.0 mtime=1586944973 sha256=76e40de23ec3abd2d692c3735575fd9fa1343dc1eadee36b5af8afb523ab23ef size=4123456 f=mysong.mp3
```

The filename is encoded as UTF-8 or as the native encoding of the operating system (e.g. arbitrary bytes on Unix). The filename must not contain a NUL (code 0, `b'\0'`) or an LF (code 10, `b'\n'`) byte, all other byte values are allowed. The slash (code `b'/'`) must be used as pathname component separator. Please note that the filename isn't percent-encoded.

The format of encoded_info is:

```python
encoded_info = b''.join(b' ' + key + b'=' + format_value(value)
                        for key, value in sorted(info.items()))
```

Sorting in `encoded_info` can be arbitrary, but it should be ASCII lexicographically ascending on the key.

The format of each value (`format_value`) is:

* Integers are encoded in ASCII decimal, without leading zeros.
* Real numbers having an integer value are encoded as their integer value.
* Real numbers having a non-integer value are encoded as ASCII decimal, i.e. anything C `scanf("%f", ...)` can parse. It typically looks like: `b'-' + integer_digits + b'.' + fractional_digits + b'e' +  b'-' + exponent`, with some parts maybe omitted.
* Booleans are encoded as ASCII bits: `b'0'` means false, `b'1'` means true.
* Strings are first encoded as UTF-8, then some bytes (including but not limited to `b'%'`, `b'\0'`, `b'\n'`, `b' '`) are percent-encoded, i.e. replaced with `b'%' + b'0123456789ABCDEF'[v >> 4] + b'0123456789ABCDEF'[v & 15]`. This is similar to the veriant of URL encoding which replaces space with `b'%20'` (rather than `b'+'`). Encoders should replace only the 4 byte values explicitly mentioned below, decoders must replace back all occurrences of `%??`.
* Encoding of other types is not supported.

The format_value is a nonempty string which may contain `b'?'`, `b'-'` and ASCII alphanumeric bytes. An unknown (unrecognized) file format is indicated by a single `b'?'`.

The key is a nonempty string which may contain `b'_'` and ASCII alphanumeric bytes.

How to parse an entry:

* If it doesn't start with `b'format='`, report an error.
* Find the first `b'\n'`, and ignore it and everything after it (they are part of subsequent entries). If there is no `b'\n'`, then report an error.
* Find the first `b' f='`, and treat everything after it as the filename. Ignore it and everything after it.
* Split the remaining string on `b' '`, and parse each item as an info item. Treat the value corresponding to the key `format=` as format_value.

How to parse an info item:

* Find the first `b'='`, and treat everything before it as the key. Ignore `b'='` and everything before it.
* Parse everything after it as a value. The type of the value depends on the key.

All info keys are optional. `b'format='` and `b' f='` are mandatory.

Typical keys, types and values:

* `size` (integer): File size in bytes.
* `mtime` (integer): Last modification time encoded as a Unix timestamp (number of seconds elapsed since the beginning of 1970).
* `sha256` (string): Lowercase hexadecimal encoding of the SHA-256 checksum (message digest) of the file contents. 64 ASCII bytes.
* `codec` (string): Short lowercase string describing the compression method, image codec or video codec used. Examples: `flate` (for deflate = zlib = ZIP), `jpeg`, `lzma`, `uncompressed`.
* `width` (integer): Width (horizontal size) of the largest image or video.
* `height` (integer): Height (vertical size) of the largest image or video.
* `acodec` (string): Short lowercase string describing the audio codec used. Example: `raw`, `mp3`, `aac`, `alaw`, `mulaw`.
* `anch` (integer): Number of audio channels.
* `arate` (integer): Audio rate (in Hz) after decompression.
* `asbits` (integer): Number of bits per audio sample.
* `subformat` (string): Format-dependent short lowercase description of the subformat.
* `asubformat` (string): Format-dependent short lowercase description of the subformat of the audio stream.

If the media file contains multiple audio streams or multiple video streams, one or none of them will be included in the info.

File format design considerations:

* It should be text-based (no binary, no offsets).
* It should be very easy to generate in any programming language (especially if string values don't contain bytes which need percent-encoding).
* It should be easy to parse with regular expressions and line oriented tools such as `awk` (if the filename doesn't contain spaces) and `perl -n`.
* It should be more compact than XML or JSON.

Software which can generate files of the mediafileinfo file format:

* The `quick_scan.py` command-line tool in https://github.com/pts/pymediafileinfo . It reports `mtime` and `size` only, it always reports `format=?`.
* The `mediafileinfo.py` command-line tool in https://github.com/pts/pymediafileinfo . It reports `mtime`, `size`, it recognizes many formats, and it also reports media parameters (`codec`, `width` etc.) for most formats it can detect.
* The `media_scan.py` command-line tool in https://github.com/pts/pymediafileinfo . Just like `mediafileinfo.py`, but it also reports `sha256`, and it can skip over files already mentioned in the previous version of the output file.
* The `mediafileinfo.pl` command-line tool in https://github.com/pts/plmediafileinfo . Just like `mediafileinfo.py`, but it supports only a few (5) file formats.

Software which can parse the mediafileinfo file format:

* Python code: https://github.com/pts/pymediafileinfo/blob/33f0aa221fb9e9c4f48914e49f2ac97d773ba7ad/media_scan_main.py#L919-L947 ; Run incrementally as `mediafileinfo.py --old=files.mfo .`
