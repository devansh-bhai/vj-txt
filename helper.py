import logging
import subprocess
import datetime
import asyncio
import os
import requests
import time
from p_bar import progress_bar
from config import LOG
import aiohttp
import tgcrypto
import aiofiles
from pyrogram.types import Message
from pyrogram import Client, filters
import re

def duration(filename):
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
        "default=noprint_wrappers=1:nokey=1", filename
    ],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    return float(result.stdout)


async def download(url, name):
    ka = f'{name}.pdf'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(ka, mode='wb')
                await f.write(await resp.read())
                await f.close()
    return ka



async def run(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()

    print(f'[{cmd!r} exited with {proc.returncode}]')
    if proc.returncode == 1:
        return False
    if stdout:
        return f'[stdout]\n{stdout.decode()}'
    if stderr:
        return f'[stderr]\n{stderr.decode()}'


def old_download(url, file_name, chunk_size=1024 * 10):
    if os.path.exists(file_name):
        os.remove(file_name)
    r = requests.get(url, allow_redirects=True, stream=True)
    with open(file_name, 'wb') as fd:
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:
                fd.write(chunk)
    return file_name


def human_readable_size(size, decimal_places=2):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if size < 1024.0 or unit == 'PB':
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"


def time_name():
    date = datetime.date.today()
    now = datetime.datetime.now()
    current_time = now.strftime("%H%M%S")
    return f"{date} {current_time}.mp4"


async def vimo_url(url):
    # Extract videocode and videohash using regular expressions
    videocode = re.search(r'videocode=([0-9]+)', url).group(1)
    videohash = re.search(r'videohash=([a-f0-9]+)', url).group(1)
    
    # URL to get the JWT
    jwt_url = "https://vimeo.com/_next/jwt"
    video_url = f"https://api.vimeo.com/videos/{videocode}:{videohash}?transcript=1&title=0&portrait=0&byline=0&share=0&like=0&watch_later=0&transparent=0&ask_ai=0&fields=embed_player_config_url,width,height"
    

    # Headers for the first request to get JWT
    headers = {
        'Newrelic': 'eyJ2IjpbMCwxXSwiZCI6eyJ0eSI6IkJyb3dzZXIiLCJhYyI6IjM5Mjg0IiwiYXAiOiI3NDQ3NDY4IiwiaWQiOiJjNmExZTY2OTY0Yjc2NTQ3IiwidHIiOiIyZWY5MDRmZTZmODU0MDdiZjBmMzE2NjA4Nzk5NDE1MCIsInRpIjoxNzIwODA4MjA4NzI1fX0=',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'X-Requested-With': 'XMLHttpRequest'
    }

    # Send GET request to get JWT
    response = requests.get(jwt_url, headers=headers)

    # Parse the JSON response and extract the token
    jwt_token = response.json().get('token')

    # Headers for the second request with Authorization header
    headers2 = {
        'Authorization': f'jwt {jwt_token}',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'X-Requested-With': 'XMLHttpRequest'
    }

    # Send GET request to the second URL with Authorization header
    response2 = requests.get(video_url, headers=headers2)

    # Parse the response from the second request
    embed_player_config_url = response2.json()

    # Extract the embed player config URL
    embed_url = embed_player_config_url.get('embed_player_config_url')

    # Print the embed player config URL

    # Extract avc_url from the embed_url response
    response3 = requests.get(embed_url)
    dl_url = response3.json()
    avc_url = dl_url['request']['files']['hls']['cdns']['akfire_interconnect_quic']['avc_url']
    
    return avc_url


async def download_video(url, cmd, name):
    #download_cmd = f'{cmd} --user-agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36"'
    #time.sleep(2)
    download_cmd = f'{cmd} -R infinite --fragment-retries 25 --socket-timeout 50 --external-downloader aria2c --downloader-args "aria2c: -x 16 -j 32"'
    global failed_counter
    print(download_cmd)
    logging.info(download_cmd)
    k = subprocess.run(download_cmd, shell=True)
    if "visionias" in cmd and k.returncode != 0 and failed_counter <= 10:
        failed_counter += 1
        await asyncio.sleep(5)
        await download_video(url, cmd, name)
    failed_counter = 0
    try:
        if os.path.isfile(name):
            return name
        elif os.path.isfile(f"{name}.webm"):
            return f"{name}.webm"
        name = name.split(".")[0]
        if os.path.isfile(f"{name}.mkv"):
            return f"{name}.mkv"
        elif os.path.isfile(f"{name}.mp4"):
            return f"{name}.mp4"
        elif os.path.isfile(f"{name}.mp4.webm"):
            return f"{name}.mp4.webm"

        return name
    except FileNotFoundError as exc:
        return os.path.isfile.splitext[0] + "." + "mp4"



async def send_vid(bot: Client, m: Message, cc, filename, thumb, name,thumb2):
    reply = await m.reply_text(f"**⚡️ Starting Uploading ...** - `{name}`")
    try:
        if thumb != "no":
            subprocess.run(['wget', thumb2, '-O', 'thumb1.jpg'], check=True)  # Fixing this line
            thumbnail = "thumb1.jpg"
        else:
            subprocess.run(f'ffmpeg -i "{filename}" -ss 00:00:12 -vframes 1 "thumb1.jpg"', shell=True)
            thumbnail = "thumb1.jpg"
            
    except Exception as e:
        await m.reply_text(str(e))

    dur = int(duration(filename))

    start_time = time.time()

    try:
        await m.reply_video(filename, caption=cc, supports_streaming=True, height=720, width=1280, thumb=thumbnail, duration=dur, progress=progress_bar, progress_args=(reply, start_time))
    except Exception:
        await m.reply_document(filename, caption=cc, thumb=thumbnail, progress=progress_bar, progress_args=(reply, start_time))

    os.remove(filename)
    os.remove(thumbnail)
    await reply.delete(True)
