# fbridge-asyncio

This repo is a fork of [fbridge](https://github.com/VictorNine/fbridge).

If you log in to your facebook account from a browser, after you do, it's a good idea to restart
fbridge-asyncio, since facebook might disconnect you.

Example service file for fbridge:
```
[Unit]
Description=fbridge-asyncio
After=matterbridge.service

[Service]
WorkingDirectory=/home/user/fbridge-asyncio
ExecStart=/usr/bin/python3 /home/user/fbridge-asyncio/fbridge-asyncio.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Example service file for matterbridge:
```
[Unit]
Description=matterbridge

[Service]
ExecStart=/home/user/matterbridge/matterbridge-1.20.0-linux-armv6 -conf /home/user/matterbridge/matterbridge.toml
Restart=always

[Install]
WantedBy=multi-user.target
```

Warning if `User=` is not specified, these services will run everything as root, which you might not want.

Example config for fbridge:
```toml
# You have to set a RemoteNickFormat in "matterbridge.toml", otherwise the bot won't work properly.
# This is used so that messages written in the api, don't echo back.
# Also this approach allows you to write through the user which is the bot in Facebook.
# It has to be the same format you set in "matterbridge.toml" for the api.
# This has to be a regular expression, if you don't know how, just use the default here, but you have to
# set the RemoteNickFormat for the bridges you'll be receiveing from into the api in matterbridge.toml
# as "[{PROTOCOL}] <{NICK}>"
RemoteNickFormat = '''\[(\w+)\]\s<.+>'''

# These links are hosted by the matterbridge api after configuring it.
stream_api_url = "http://localhost:4242/api/stream"
message_api_url = "http://localhost:4242/api/message"

# The domain from which you got the cookie.
cookie_domain = "messenger.com"

# How fast to restart the script in case facebook randomly stops sending.
timeout_listen = 3600

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

This will install modules globally.

If you don't wish to add bloat to your setup, checkout the
[venv docs](https://docs.python.org/3/library/venv.html).

Read around in the repo for [fbchat-asyncio](https://github.com/tulir/fbchat-asyncio) to get familiar with it, otherwise
you'll have a hard time logging in. This is the module that's used for communicating with the Facebook chat.

## Handle duplicate usernames

If in other services (example: discord) there is a way to set any username, someone can impersonate another
user by accident or not. That's why if you're bridging small groups and using other bots it's a good idea to handle
the duplicates with a "tengo" script in matterbridge. Some services like mumble (registration) and irc (nickserv) have
mechanisms to reserve usernames, but if it's not configured you can still use the script.

You can create a file called "userids.tengo" in the directory where your matterbridge config is with the following code:

```tengo
userids := {"123456789123456789": "some_username",
            "otheruser@some-hostanme.new": "otheruser"}

for key, res in userids {
	if key == msgUserID {
		result=res
		break
	} else {
		/*
		Ignoring the facebook bridge, set "fb" to your bridge name.
		This is done for fbridge-asyncio since it already uses the user id.
		*/
		if bridge != "fb" && protocol != "api" {
			result=nick + " | not static"
		} else {
			result=nick
		}
	}
}
```

Then add this to your matterbridge config file:

```
[tengo]
RemoteNickFormat="userids.tengo"
```

If you're running matterbridge as a service, set the full path for "userids.tengo" in the config.

and replace all `{NICK}` with `{TENGO}`.

## Encryption

You should consider encrypting your config files especially the `session.json` file.

Anyone who can plug in a USB drive with a live OS running on it to your computer even without a
password can get access to the data on the device unless you encrypt the whole drive or data.
With a Raspberry Pi all they need is the SD card and a reader.

This script may need your actual session which would allow anyone else to use it as well,
so if you have a session file stored, it's highly recommended looking at the following.

### Windows options

On Windows, for whole drive encryption you can use the "BitLocker" tool.

There is also the file encryption which you can do by opening "Properties" of any
file, then "Advanced...", finally "Encrypt contents to secure data".

You can also look at open source options for encryption on Windows, such as:

* 7-Zip (https://www.7-zip.org/), for encrypting archives.
  
* Gpg4win (https://www.gpg4win.org/), for an OpenPGP implementation for Windows.

For GPG checkout info bellow.

### Linux options

On Linux, for whole drive encryption you can use dm-crypt (https://wiki.archlinux.org/title/Dm-crypt).

One possible solution for Linux if whole drive encryption
isn't really an option (for example on Raspberry Pi),
or you just don't want to encrypt the whole drive:

Install GPG: https://gnupg.org/

Make sure /tmp is mounted as tmpfs: https://wiki.archlinux.org/title/Tmpfs#Examples

After installing GPG, create a key: https://wiki.archlinux.org/title/GnuPG#Create_a_key_pair

Keep in mind, not using a strong password is a bad idea since brute forcing the password of
a private key is very possible and only thing protecting it is the password itself.
If anyone can get to the drive and is able to brute force they have the private key
in plain sight since it's just a simple file with gibberish in it.

Run: `gpg --list-keys`

Then copy the fingerprint of your key (example: 9D2FAD842D83E3CB13313334190C37B0F8665DA8).

Encrypt the files using this command:

```
gpg -r FINGERPRINT_HERE -o session.json.gpg -e session.json &&
gpg -r FINGERPRINT_HERE -o fbridge-config.toml.gpg -e fbridge-config.toml
```

Then you can create a script like this
(make sure to replace the paths and usernames with yours):

```
#!/bin/bash

gpg -o /tmp/fbridge-config.toml -d /path/to/YOUR/fbridge-config.toml.gpg &&
gpg -o /tmp/session.json -d /path/to/YOUR/session.json.gpg &&
sudo chown YOURusername:YOURusername /tmp/fbridge-config.toml &&
sudo chown YOURusername:YOURusername /tmp/session.json &&
sudo chmod 600 /tmp/fbridge-config.toml &&
sudo chmod 600 /tmp/session.json
```

Then when you run this script and type your password the decrypted files will
be in the `/tmp` directory which is only in RAM and will be cleared on shutting down.
The permissions are set so that only your user can read/write the files when the machine is on.

Create `session.toml` where the script is and place in it:

`path = "/tmp/session.json"`

Now you can delete the old "session.json" if you have one
where the script is.

Then clean `fbridge-asyncio.toml` and only type in it:

`path = "/tmp/fbridge-config.toml"`

This will tell the script where to look for the files.

Don't forget to run the decryption script on every boot.
