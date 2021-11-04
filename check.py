import sys
import re
import json
import time
import argparse
import random
import traceback
from datetime import datetime
from urllib import request
from requests import ConnectionError
from socket import gethostbyname, gaierror

def custom_sleep(start_time, attempts, timeout_max_sleep):
    wasted_time = int(time.time() - start_time)
    sleep_time = 60 + (60 * attempts / 2)

    if timeout_max_sleep > 0 and sleep_time > timeout_max_sleep:
        sleep_time = timeout_max_sleep

    jitter = int(sleep_time * 0.1)
    jitter = random.randrange(0, jitter)

    if random.randrange(0, 1) == 1:
        sleep_time = sleep_time + jitter
    else:
        sleep_time = sleep_time - jitter
        if sleep_time < 0:
            if timeout_max_sleep > 0:
                sleep_time = timeout_max_sleep
            else:
                sleep_time = 60
    return sleep_time, wasted_time

def get_stream_status(video_id, api_key):
    data = json.dumps({
        "videoId": video_id,
        "context": {
            "client": {
                "hl": "en",
                "gl": "JP",
                "clientName": "WEB",
                "clientVersion": "2.20211102.01.00",
                "timeZone": "UTC"
            }
        },
        "heartbeatRequestParams": {
            "heartbeatChecks": ["HEARTBEAT_CHECK_TYPE_LIVE_STREAM_STATUS"]
        }
    }).encode('utf8')

    req = request.Request('https://www.youtube.com/youtubei/v1/player/heartbeat?alt=json&key={}'.format(api_key), data=data)
    req.add_header('Content-Type', 'application/json')

    result = None
    status = None # LIVE_STREAM_OFFLINE | OK
    startTime = None

    try:
        res = request.urlopen(req)
        result = json.loads(res.read().decode('utf8'))
    except:
        pass

    if result is None:
        return result, startTime

    try:
        status = result['playabilityStatus']['status']
    except:
        pass

    try:
        status = result['playabilityStatus']['status']
    except:
        pass

    try:
        startTime = int(result['playabilityStatus']['liveStreamability']['liveStreamabilityRenderer']['offlineSlate']['liveStreamOfflineSlateRenderer']['scheduledStartTime'])
    except:
        pass

    return status, startTime



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
    result = None

    try:
        res = request.urlopen(req)
        result = json.loads(res.read().decode('utf8'))
    except:
        pass

    return result

def get_keys(url, quiet=False):
    if not quiet:
        print('Fetching YouTube page...')

    regex_canonical = r"<link rel=\"canonical\" href=\"https://www\.youtube\.com/watch\?v=(.{11})\">"
    regex_api_key = r"\"innertubeApiKey\":\"([^\"]+)\""
    youtube_page = None
    video_id = None
    api_key = None

    try:
        youtube_page = request.urlopen(url).read().decode('utf8')
    except:
        return video_id, api_key
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

def is_stream_online(url, connection_timeout, quiet=False, wait=False, verbose=False, timeout_max_sleep=0):
    video_id = None
    api_key = None
    start_time = time.time()
    attempts = 0

    while True:
        attempts += 1
        if verbose:
            print('[{}] Attempting to fetch basic information. Attempt {}'.format(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()), attempts))
        video_id, api_key = get_keys(url, quiet)

        if video_id and api_key:
            break
        else:
            sleep_time, wasted_time = custom_sleep(start_time, attempts, timeout_max_sleep)

            if not wait:
                raise Exception('Unable to fetch base info after {} seconds and {} attempts'.format(wasted_time, attempts))
            if time.time() > start_time + connection_timeout:
                raise Exception('Unable to fetch base info after {} seconds and {} attempts'.format(wasted_time, attempts))
            time.sleep(sleep_time)

    if verbose:
        print('Video ID:', video_id)
        print('Found API Key', api_key)

    # Send heartbeat
    if not quiet:
        print('Checking for stream status')

    attempts = 0

    while True:
        heartbeat = get_metadata(video_id, api_key, connection_timeout)
        status, startTime = get_stream_status(video_id, api_key)

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

        if startTime:
            now = int(time.time())
            startsIn = startTime - now - 1
            if startsIn > 0:
                if not quiet:
                    print('Waiting {} seconds for stream...'.format(startsIn))
                time.sleep(startsIn)
            else:
                time.sleep(1)
        else:
            time.sleep(5)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    group = parser.add_mutually_exclusive_group()
    group.add_argument('-q', '--quiet', help='Do not output anything to stdout', action='store_true')
    group.add_argument('--verbose', help='Print heartbeat to stdout for debugging', action='store_true')

    parser.add_argument('-w', '--wait', help='Keep polling until the stream starts, then exit', action='store_true')
    parser.add_argument('--timeout', help='How long to wait in case network fails (in seconds). 5 minutes by default', type=int, nargs='?', const=300, default=300)
    parser.add_argument('--timeout-max-sleep', help='Maximum allowed idle time (in seconds) between failed network requests. Infinite by default', type=int, nargs='?', const=0, default=0)
    parser.add_argument('url', help='YouTube url', type=str)

    args = parser.parse_args()

    if args.verbose:
        print(args)

    try:
        if is_stream_online(args.url, args.timeout, quiet=args.quiet, wait=args.wait, verbose=args.verbose, timeout_max_sleep=args.timeout_max_sleep):
            sys.exit(0)
    except Exception as e:
        if not args.quiet:
            print('Terminating')
            if hasattr(e, 'message'):
                print(e.message)
            else:
                print(e)
            traceback.print_exception(type(e), e, e.__traceback__)
        pass
    sys.exit(2)
