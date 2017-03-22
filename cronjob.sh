#!/bin/bash
source /home/joant/bin/dtop-twitter-poster/venv/bin/activate
export TZ=":US/Eastern"
if [ "$(date +%z)" == "$1" ]; then
  shift
  exec $@
fi

