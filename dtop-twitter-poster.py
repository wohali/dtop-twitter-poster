#!/usr/bin/env python
"""[DTOP] Automated twitter bot
Can dump to a raw hex file, or to a human-readable text file.

Roughly, this does the following:
 1. Reads iCal file from our Google Events calendar.
 2. Finds any events in the next 4 or 24 hours, including recurring events.
 3. Sorts and formats announcements with UTC and ET start time for each event.
 4. Post announcement(s) on Twitter if instructed to do so.

You can specify a fake "now" time for the script (for testing, primarily).

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
"""

import arrow
import datetime
import dateutil
import docopt
import emoji
import json
import os
import random
import requests
import sys
from twitter import Twitter, OAuth
import vobject


def toeastern(etime):
    # Formats time in US/Eastern for printing/tweeting.
    return etime.to('US/Eastern').format('h:mm A')

def relreset(tt):
    # Calculates offset from arrow to the next reset (00:00 UTC)
    # as minutes before/after reset.
    now = arrow.utcnow()
    reset = now.replace(hour=0, minute=0, second=0, microsecond=0, days=+1)
    if tt > reset:
        delta = tt - reset
        return "{} minutes after reset".format(delta.seconds // 60)
    elif tt < reset:
        delta = reset - tt
        return "{} minutes before reset".format(delta.seconds // 60)
    else:
        return "at reset"

def deltatime(tt, now=arrow.utcnow()):
    # Calculates time between now and event start and returns it
    # in a human readable form.
    deltamins = (tt - now).seconds // 60
    if deltamins == 0:
        return "RIGHT NOW"
    elif deltamins <= 90:
        ms = "" if deltamins == 1 else "s"
        return "in just {} minute{}".format(deltamins, ms)
    else:
        deltahrs = deltamins // 60
        hs = "" if deltahrs == 1 else "s"
        deltamins = deltamins % 60
        if deltamins == 0:
            return "in just {} hour{}".format(deltahrs, hs)
        ms = "" if deltamins == 1 else "s"
        return "in just {} hour{} {} minute{}".format(
            deltahrs, hs, deltamins, ms)
    
def readgcalevents(ical_url):
    # Reads iCal file from Google Events calendar (or static file).
    if "http" in ical_url:
        ical = requests.get(ical_url).text
    else:
        with open(ical_url) as f:
            ical = f.read()
    vobs = list(vobject.readComponents(ical))
    allevents = []
    for vob in vobs:
        allevents.extend(vob.vevent_list)
    return allevents

def findevents(allevents, offset=arrow.utcnow(), window=60*24):
    # Finds any events in allevents starting at offset and going until
    # offset+window, where window is specified in minutes.
    # Defaults to events in the next 24 hours.
    endtime = offset.replace(minutes=+window)

    events = []
    for event in allevents:
        # TODO: Handle RDATE, EXDATE and EXRULE
        # Check if recurring event
        if type(event.rruleset) == dateutil.rrule.rruleset:
            if event.summary.value == "Meta Map":
                # waaaaat broken event in calendar
                continue
            between = event.rruleset.between(offset, endtime, inc=True)
            between = [(event.summary.value, arrow.get(x)) for x in between]
            events.extend(between)
        else:
            if type(event.dtstart.value) == datetime.date:
                etime = arrow.get(event.dtstart.value.isoformat())
            elif type(event.dtstart.value) == datetime.datetime:
                etime = arrow.get(event.dtstart.value)
            else:
                raise Exception("wtf, unknown dtstart value type {}".format(
                    event.dtstart.value))
            if offset < etime < endtime:
                events.append((event.summary.value, etime))

    # Mel request: never tweets about raids
    events = [x for x in events if "Raid" not in x[0]]
    events.sort(key=lambda x: x[1])
    return events

def getimage(ename, imgpath):
    # Looks for an image for the event ename. Searches in imgpath/ename
    # (where ename's spaces and punctuation have all been removed)
    # Returns full path to image if one found, otherwise None.
    imglist = None
    ipath = imgpath + os.sep + ename.replace(" ", "").replace("'", "").lower()
    if os.path.exists(ipath) and os.path.isdir(ipath):
        imglist = [x for x in os.listdir(ipath) 
            if os.path.isfile(os.path.join(ipath, x))]
    if imglist:
        img = random.choice(imglist)
        return os.path.join(ipath, img)
    else:
        return None

def dailyreminder(ename, etime, templates):
    # Picks a random daily reminder, populates it and returns it.
    if "Core Tyria" in ename:
        daily = random.choice(templates['coretyriadailys'])
    else:
        daily = random.choice(templates['dailys'])
    delta = relreset(etime)
    return daily.format(ename, delta, toeastern(etime))

def nightlyreminder(ename, etime, templates, now=arrow.utcnow()):
    # Picks a random hourly reminder, populates it and returns it.
    if "Core Tyria" in ename:
        nightly = random.choice(templates['coretyrianightlys'])
    elif "Guild Missions" in ename:
        nightly = random.choice(templates['guildmissionnightlys'])
    else:
        nightly = random.choice(templates['nightlys'])
    delta = deltatime(etime, now)
    return nightly.format(ename, delta, toeastern(etime))

def mondayreminder(e1, e2, templates):
    # Picks a random Monday reminder, populates it and returns it.
    monday = random.choice(templates['mondays'])
    return monday.format(e1, e2)

def thursdayreminder(e1, e2, templates):
    # Picks a random Thursday reminder, populates it and returns it.
    thursday = random.choice(templates['thursdays'])
    return thursday.format(e1, e2)

def tweetorprint(tweets, settings, doit=False):
    # Posts announcement(s) on Twitter, or print for debug purposes.
    if doit:
        tauth = OAuth(
            settings['config']['token'],
            settings['config']['token_secret'],
            settings['config']['consumer_key'],
            settings['config']['consumer_secret']
        )
        t = Twitter(auth=tauth)
    for tweet, timg in tweets:
        # convert emojis
        tweet = emoji.emojize(tweet, use_aliases=True)
        if doit:
            if timg:
                with open(timg, "rb") as imagefile:
                    imagedata = imagefile.read()
                t_upload = Twitter(domain='upload.twitter.com', auth=tauth)
                id_img = t_upload.media.upload(
                    media=imagedata)["media_id_string"]
                t.statuses.update(status=tweet, media_ids=id_img)
            else:
                t.statuses.update(status=tweet)
        else:
            print (tweet)
            if timg:
                print ("  Image: " + timg)


def main(args):
    doit = args['--go']
    if '<timestamp>' in args:
        #now = arrow.get('2017-03-25T10:00:00.934551-04:00')
        now = arrow.get(args['<timestamp>'])
    else:
        now = arrow.utcnow()

    # read config data
    mydir = os.path.dirname(os.path.abspath(__file__))
    if '--settings' in args:
        fpath = os.path.abspath(args['--settings'])
    else:
        fpath = os.path.join(mydir, "settings.json")
    with open(fpath) as f:
        settings = json.load(f)

    # default search window
    window = 60*24
    day = now.format('dddd')
    evening = (now.to('US/Eastern').hour >= 17)

    # Special case: on Thursday, expand window to include Fri and Sat
    if day == "Thursday":
        sat = now.replace(days=+2, hour=23, minute=59)
        delta = sat - now
        window = delta.days*60*24 + delta.seconds // 60

    # Special case: on Monday, use Thursday's window
    if day == "Monday":
        now = now.replace(days=+3)
        sat = now.replace(days=+2, hour=23, minute=59)
        delta = sat - now
        window = delta.days*60*24 + delta.seconds // 60

    # Special case: for all evening runs, use short window
    if evening:
        window = 60*4

    allevents = readgcalevents(settings['config']['ical_url'])
    events = findevents(allevents, offset=now, window=window)
    if not events:
        exit(0)
    if not doit:
        # debug, print events
        print ( events )

    tweets = []
    templates = settings['templates']
    if settings["config"]["images"][0] == '/':
        imgpath = settings["config"]["images"]
    else:
        imgpath = os.path.join(mydir, settings["config"]["images"])
    if evening:
        # Only tweet immediate next event at night
        ename, etime = events[0]
        img = getimage(ename, imgpath)
        tweets.append( ( nightlyreminder(ename, etime, templates, now), img ) )
    elif day == "Monday":
        events = [x for x in events if x[0] != "Guild Missions"]
        tweets.append( ( mondayreminder(events[0][0], events[1][0], templates), None ) )
    elif day == "Thursday":
        events = [x for x in events if x[0] != "Guild Missions"]
        tweets.append( ( thursdayreminder(events[0][0], events[1][0], templates), None ) )
    elif day == "Saturday":  # (and not evening)
        # TODO Fix Guild Mission rendering
        ename, etime = events[0]
        img = getimage(ename, imgpath)
        tweets.append( ( nightlyreminder(ename, etime, templates, now), img) )
        ename, etime = events[1]
        img = getimage(ename, imgpath)
        tweets.append( ( dailyreminder(ename, etime, templates), img ) )
    else:
        ename, etime = events[0]
        img = getimage(ename, imgpath)
        tweets.append( ( dailyreminder(ename, etime, templates), img ) )

    tweetorprint(tweets, settings, doit) 

if __name__ == "__main__":
    args = docopt.docopt(__doc__, version="1.0")
    main(args)
