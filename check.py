import sys
import re
import json
import time
import argparse
from datetime import datetime
from urllib import request
from requests import ConnectionError

def get_metadata(video_id, api_key, connection_timeout):
    data = json.dumps({
        'videoId': video_id,
        'context': {
            'client': {
                'utcOffsetMinutes': 540,
                'clientName': 'WEB',
                'clientVersion': '2.20211009.11.00',
                'hl': 'en',
                'gl':'JP',
                'timeZone':'Asia/Tokyo',
            },
        },
    }).encode('utf8')

    req = request.Request('https://www.youtube.com/youtubei/v1/updated_metadata?key={}'.format(api_key), data=data)
    req.add_header('Content-Type', 'application/json')
    res = request.urlopen(req)
    result = None

    start_time = time.time()
    while True:
        try:
            result = json.loads(res.read().decode('utf8'))
            break
        except ConnectionError:
            if time.time() > start_time + connection_timeout:
                raise Exception('Unable to get updates after {} seconds of ConnectionErrors'.format(connection_timeout))
            else:
                time.sleep(10)

    return result

def is_stream_online(url, connection_timeout, quiet=False, wait=False, verbose=False):
    # Fetch video page
    if not quiet:
        print('Fetching YouTube page...')
    youtube_page = request.urlopen(url).read().decode('utf8')
    regex_canonical = r"<link rel=\"canonical\" href=\"https://www\.youtube\.com/watch\?v=(.{11})\">"
    regex_api_key = r"\"innertubeApiKey\":\"([^\"]+)\""

    # Get details
    try:
        video_id = re.findall(regex_canonical, youtube_page, re.MULTILINE)[0]
        api_key = re.findall(regex_api_key, youtube_page, re.MULTILINE)[0]
    except IndexError:
        if not wait:
            return False
        if '/live' in url:
            time.sleep(60)
            return is_stream_online(url, connection_timeout, quiet, wait, verbose)

    if verbose:
        print('Video ID:', video_id)
        print('Found API Key', api_key)

    # Send heartbeat
    if not quiet:
        print('Checking for stream status')

    while True:
        heartbeat = get_metadata(video_id, api_key, connection_timeout)
        if verbose:
            print(json.dumps(heartbeat, indent=2))

        reason = None
        for action in heartbeat['actions']:
            if 'updateDateTextAction' in action:
                reason = action['updateDateTextAction']['dateText']['simpleText']

        is_online = 'streaming' in reason or 'in progress' in reason

        if not quiet:
            print(reason)

        if not wait or is_online:
            return is_online

        time.sleep(5)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    group = parser.add_mutually_exclusive_group()
    group.add_argument('-q', '--quiet', help='Do not output anything to stdout', action='store_true')
    group.add_argument('--verbose', help='Print heartbeat to stdout for debugging', action='store_true')

    parser.add_argument('-w', '--wait', help='Keep polling until the stream starts, then exit', action='store_true')
    parser.add_argument('--timeout', help='How long to wait in case network fails (in seconds). 5 minutes by default', type=int, nargs='?', const=300, default=300)
    parser.add_argument('url', help='YouTube url', type=str)

    args = parser.parse_args()

    if args.verbose:
        print(args)

    if is_stream_online(args.url, args.timeout, quiet=args.quiet, wait=args.wait, verbose=args.verbose):
        sys.exit(0)
    sys.exit(2)
