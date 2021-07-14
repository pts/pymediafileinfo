#! /usr/bin/ruby
#
# client.rb: sample client for mediafileinfo.py --pipe in Ruby
# by pts@fazekas.hu at Thu Jul 15 01:09:54 CEST 2021
#

IO.popen ["./mediafileinfo.py", "--pipe"], "rb+" do |io|
  ARGV.each do |filename|  # Treat each command-line argument as a filename.
    io.puts(filename)  # Send request.
    response = io.gets  # Wait for and receive response.
    suffix = " f=#{filename.dup.force_encoding("ASCII-8BIT")}\n"
    raise "bad prefix: #{response.inspect}" if !response.start_with?("format=")
    raise "bad suffix: #{response.inspect}" if !response.end_with?(suffix)
    h = Hash[response[0 ... -suffix.size].split(" ").map {
       |p| p.split("=", 2) }]  # Parse response.
    h["f"] = filename
    p h  # Pretty-print parsed response to an STDOUT line.
    STDOUT.flush
  end
end
