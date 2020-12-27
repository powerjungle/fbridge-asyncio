# fbridge-asyncio

This repo is a fork of [fbridge](https://github.com/VictorNine/fbridge).

If you're having problems with matterbridge not detecting messages, try restarting both it and the fbridge script.

Example service file for fbridge that restarts every hour:
```
[Unit]
Description=fbridge-asyncio
Requires=matterbridge.service

[Service]
WorkingDirectory=/home/pi/fbridge-asyncio
ExecStart=/usr/bin/python3 /home/pi/fbridge-asyncio/fbridge-asyncio.py
User=pi
Restart=always
RuntimeMaxSec=3600

[Install]
WantedBy=multi-user.target
```
Change `RuntimeMaxSec` to something else if you don't want it to restart so fast.

Example service file for matterbridge:
```
[Unit]
Description=matterbridge
Requires=fbridge-asyncio.service

[Service]
ExecStart=/home/pi/matterbridge/matterbridge-1.20.0-linux-armv6 -conf /home/pi/matterbridge/matterbridge.toml
User=pi
Restart=always

[Install]
WantedBy=multi-user.target
```

Example config for fbridge:
```toml
# You have to set a RemoteNickFormat in "matterbridge.toml", otherwise the bot won't work properly.
# This is used so that messages written in the api, don't echo back.
# Also this approach allows you to write through the user which is the bot in fb.
# It has to be the same format you set in "matterbridge.toml" for the api.
# This has to be a regular expression, if you don't know how, just use the default here, but you have to
# set the RemoteNickFormat for the bridges you'll be receiveing from into the api in matterbridge.toml
# as "[{PROTOCOL}] <{NICK}>"
RemoteNickFormat = '''\[(\w+)\]\s<.+>'''

stream_api_url = "http://localhost:4242/api/stream"
message_api_url = "http://localhost:4242/api/message"

# This section is used so that the script knows which thread to relay to which gateway in matterbridge.
[threads]
    [threads.1567891234567891] # Here you put the thread id you got from the url in messenger.com
    gateway = "gateway1" # This is the gateway you've configured in matterbridge for the api.

# This section is used so that the script knows what name to be set, to each user id, otherwise in the RemoteNickFormat
# it will just echo the user ids.
[users]
    [users.100012345678912] # Here you put the user id you got from the url in messenger.com
    username = "First Last"

    [users.100012345678913]
    username = "John Johnson"

    [users.100012345678914]
    username = "Perry Platapus"
```
This config needs to be called `fbridge-config.toml`! Without this file the script won't run.

### Requirements

* [matterbridge](https://github.com/42wim/matterbridge)
* [Python 3](https://www.python.org/downloads/) (preferably 3.9+)
* [pip](https://pypi.org/project/pip/)

To install the required modules, run in the directory that `requirements.txt` is present for fbridge-asyncio:

`python -m pip install -r requirements.txt`

If just `python` doesn't work, try running `python3`, the same goes for `pip` and `pip3`.

If you don't wish to add bloat to your setup, install `pipenv` and checkout the [pipenv docs](https://pypi.org/project/pipenv/).

Read around in the repo for [fbchat-asyncio](https://github.com/tulir/fbchat-asyncio) to get familiar with it, otherwise you'll have a hard time logging in. This is the module that's used for communicating with the Facebook chat.