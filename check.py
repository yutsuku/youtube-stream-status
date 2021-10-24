import sys
import re
import json
import time
import argparse
from datetime import datetime
from urllib import request
from requests import ConnectionError
from socket import gethostbyname, gaierror

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

    try:
        result = json.loads(res.read().decode('utf8'))
    except:
        pass

    return result

def get_keys(url, quiet=False):
    if not quiet:
        print('Fetching YouTube page...')

    regex_canonical = r"<link rel=\"canonical\" href=\"https://www\.youtube\.com/watch\?v=(.{11})\">"
    regex_api_key = r"\"innertubeApiKey\":\"([^\"]+)\""

    try:
        youtube_page = request.urlopen(url).read().decode('utf8')
    except:
        pass

    video_id = re.findall(regex_canonical, youtube_page, re.MULTILINE)
    api_key = re.findall(regex_api_key, youtube_page, re.MULTILINE)

    if len(video_id) == 0:
        video_id = None
    else:
        video_id = video_id[0]

    if len(api_key) == 0:
        api_key = None
    else:
        api_key = api_key[0]

    return video_id, api_key

def is_stream_online(url, connection_timeout, quiet=False, wait=False, verbose=False):
    video_id = None
    api_key = None
    start_time = time.time()
    attempts = 0

    while True:
        attempts += 1
        video_id, api_key = get_keys(url, quiet)
                
        if video_id and api_key:
            break
        else:
            if time.time() > start_time + connection_timeout:
                raise Exception('Unable to fetch base info after {} seconds and {} attempts'.format(connection_timeout, attempts))
            time.sleep(60 + (60 * attempts / 2))

    if verbose:
        print('Video ID:', video_id)
        print('Found API Key', api_key)

    # Send heartbeat
    if not quiet:
        print('Checking for stream status')

    attempts = 0

    while True:
        heartbeat = get_metadata(video_id, api_key, connection_timeout)

        if heartbeat is None:
            if attempts > 10:
                if not quiet:
                    print('Giving up. Is the network unstable?')
                return False

            attempts += 1
            time.sleep(60)
            continue
        else:
            attempts = 0

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

    try:
        if is_stream_online(args.url, args.timeout, quiet=args.quiet, wait=args.wait, verbose=args.verbose):
            sys.exit(0)
    except Exception as e:
        if not args.quiet:
            if hasattr(e, 'message'):
                print(e.message)
            else:
                print(e)
        pass
    sys.exit(2)
