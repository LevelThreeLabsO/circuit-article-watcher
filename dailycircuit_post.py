#!/usr/bin/env python3
"""
The Daily Circuit -> WhatsApp post, delivered to Sruli's Slack DM.

Started weekday mornings by poll.yml (see dailycircuit.yml). Waits for
today's Daily Circuit to be published on circuit.news, then builds:

    Today's The Daily Circuit: <headline, verbatim from the site>
    <plain circuit.news link>

Env:
  DM_SLACK_WEBHOOK   incoming webhook to Sruli's DM (unset = just print)
  DEADLINE_HOUR_ET   hour (ET) to give up waiting; default 12
"""

import datetime
import html
import json
import os
import re
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

API = "https://circuit.news/wp-json/wp/v2/posts"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
ET = ZoneInfo("America/New_York")
WAIT_SECONDS = 300

WEBHOOK = os.environ.get("DM_SLACK_WEBHOOK", "").strip()
DEADLINE_HOUR_ET = int(os.environ.get("DEADLINE_HOUR_ET", "12"))


def get_json(url):
    url = f"{url}&_cb={int(time.time())}"  # dodge the edge cache
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def verbatim(fragment):
    text = html.unescape(re.sub(r"<[^>]+>", "", fragment))
    return re.sub(r"\s+", " ", text).strip()


def todays_edition():
    # The site's own clock is Gulf time, so compare dates in ET via date_gmt.
    today = datetime.datetime.now(ET).date()
    posts = get_json(f"{API}?search=daily%20circuit&orderby=date&per_page=10"
                     "&_fields=date_gmt,link,title")
    for p in posts:
        slug = p["link"].rstrip("/").rsplit("/", 1)[-1]
        published = (datetime.datetime.fromisoformat(p["date_gmt"])
                     .replace(tzinfo=datetime.timezone.utc).astimezone(ET).date())
        if slug.startswith("the-daily-circuit-") and published == today:
            return p
    return None


def build():
    edition = None
    while True:
        try:
            edition = todays_edition()
        except Exception as e:  # transient site hiccup: keep waiting
            print(f"lookup failed: {e}", file=sys.stderr)
        if edition:
            break
        if datetime.datetime.now(ET).hour >= DEADLINE_HOUR_ET:
            raise RuntimeError("today's Daily Circuit never showed up on the site "
                               "(holiday, or it's very late)")
        print("Daily Circuit not up yet, waiting...", file=sys.stderr)
        time.sleep(WAIT_SECONDS)

    title = verbatim(edition["title"]["rendered"])
    title = re.sub(r"^The Daily Circuit:\s*", "", title)
    return f"Today's The Daily Circuit: {title}\n{edition['link']}"


def slack(text):
    if not WEBHOOK:
        print(text)
        return
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps({"text": text, "unfurl_links": False,
                         "unfurl_media": False}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=30).read()


def main():
    try:
        post = build()
    except Exception as e:
        slack(f":warning: Couldn't build today's Daily Circuit WhatsApp post: {e}")
        raise
    if datetime.datetime.now(ET).hour >= 13:
        post = (":warning: Late: the morning trigger didn't fire, so this came from "
                "the backup schedule. Check the Circuit watcher's cron-job.org pinger.\n\n"
                + post)
    slack(post)


if __name__ == "__main__":
    main()
