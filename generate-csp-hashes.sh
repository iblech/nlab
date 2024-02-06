#!/usr/bin/env bash
# This script computes the required hashes for the Content-Security-Policy
# header, to be added to /etc/nginx/conf.d/nlab.conf or similar.

{
  find app -type f -print0 | xargs -0 perl -MDigest::SHA=sha256 -MMIME::Base64 -nwe "
    print \"'sha256-\" . encode_base64(sha256(\$2), '') . \"'\\n\"
      while /\\bon(?:click|blur|submit|mouse|change|key)'?\\s*=>?\\s*(['\"])(.*?)\\1/g
  "

  find app -type f -print0 | xargs -0 perl -MDigest::SHA=sha256 -MMIME::Base64 -nwe "
    BEGIN { \$/ = undef }

    print \"'sha256-\" . encode_base64(sha256(\$1 . \$2 . \$3), '') . \"'\\n\"
      while m#<script[^>]*>(\\s*)(?:<!--//--><!\\[CDATA\\[)?(.*?)(?:\\]\\]>)?(\\s*)<\\/script>#gs;
  "
} | sort | uniq
