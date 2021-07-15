#! /usr/bin/perl -w
#
# client.pl: sample client for mediafileinfo.py --pipe in Perl
# by pts@fazekas.hu at Thu Jul 15 01:24:54 CEST 2021
#

use integer;
use strict;
use IPC::Run qw(start finish);  # sudo apt-get install libipc-run-perl
use Data::Dumper qw(Dumper);

$| = 1;  # Autoflush stdout.
my($in, $out) = ("", "");
# TODO(pts): How to set up binmode on Windows?
my $h = start(["./mediafileinfo.py", "--pipe"], \$in, \$out) or die("start");
for my $filename (@ARGV) {  # Treat each command-line argument as a filename.
  $in = "$filename\n";
  while (length($in)) { pump $h or die("pump in"); }  # Send request.
  # Wait for and receive response.
  while ($out !~ /\n/) { pump $h or die("pump out"); }
  die if $out !~ s/^([^\n]+)\n\Z(?!\n)//;
  my $response = $1;
  $response =~ /^format=/ or die("response prefix: $response\n");
  $response =~ s/ f=\Q$filename\E$// or die("response suffix: $response\n");
  my $h = {map { split(/=/, $_, 2) } split(/ /, $response)};  # Parse response.
  $h->{f} = $filename;
  print Dumper($h);  # Pretty-print parsed response to an STDOUT line.
}
finish $h or die("finish");
