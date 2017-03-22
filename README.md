# [DTOP] Automated Google Calendar to Twitter bot

Can dump to a raw hex file, or to a human-readable text file.

Roughly, this does the following:
1. Reads iCal file from our Google Events calendar.
2. Finds any events in the next 4 or 24 hours, including recurring events.
3. Sorts and formats announcements with UTC and ET start time for each event.
4. Post announcement(s) on Twitter if instructed to do so.

You can specify a fake "now" time for the script (for testing, primarily).

```
Usage:
  dtop-twitter-poster
  dtop-twitter-poster [-h | --help]
  dtop-twitter-poster [--go] [--settings=settings.json]
  dtop-twitter-poster [<timestamp>]
  dtop-twitter-poster [<timestamp>] [--go] [--settings=settings.json]
  dtop-twitter-poster --version

Options:
  -h --help                 Show this screen.
  --version                 Show version information.
  --settings=settings.json  Specify alterate settings file.
  --go                      Tweet the results, do not print to stdout

Examples:
  dtop-twitter-poster --go
  dtop-twitter-poster 2017-03-19T11:00:00-04:00
  dtop-twitter-poster --settings=tests/settings.json 2017-03-19T11:00:00-04:00
```
