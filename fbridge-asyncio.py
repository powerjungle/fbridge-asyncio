from atexit import register
from getpass import getuser, getpass
from fbchat import Session, FacebookError, Listener, Client
from os import path, name
from json import load, dump
import logging
import toml
import asyncio

from fbridge_listen import listen_fb, listen_api, loop_listeners


if not path.exists("fbridge-config.toml"):
    logging.error("Config file fbridge-config.toml doesn't exist")
    exit()

if name == "nt":
    asyncio.DefaultEventLoopPolicy = asyncio.WindowsSelectorEventLoopPolicy

threads = dict()
users = dict()

# Reverse lookup
reverse_threads = dict()


def load_cookies(filename):
    try:
        # Load cookies from file
        with open(filename) as f:
            return load(f)
    except FileNotFoundError as e:
        logging.error(e)
        return  # No cookies yet


parsed_toml = toml.load("fbridge-config.toml")
if parsed_toml.get("path"):
    parsed_toml = toml.load(parsed_toml["path"])
stream_api_url = parsed_toml["stream_api_url"]
message_api_url = parsed_toml["message_api_url"]
cookie_domain_global = parsed_toml["cookie_domain"]
th = parsed_toml["threads"]
us = parsed_toml["users"]

for key, value in th.items():
    threads[key] = value["gateway"]
for key, value in us.items():
    users[key] = value["username"]

reverse_threads = {v: k for k, v in threads.items()}

remote_nick_format = parsed_toml["RemoteNickFormat"]

session_toml = "session.toml"
if path.exists(session_toml):
    parsed_cookie_toml = toml.load(session_toml)
    got_session_path = parsed_cookie_toml["path"]
    cookies_global = load_cookies(got_session_path)
else:
    cookies_global = load_cookies("session.json")


async def load_session(cookies, cookie_domain):
    if not cookies:
        return

    try:
        return await Session.from_cookies(cookies, domain=cookie_domain)
    except FacebookError as e:
        logging.error(e)
        return  # Failed loading from cookies


def save_cookies(filename, cookies):
    with open(filename, "w") as f:
        dump(cookies, f)


async def main():
    logging.basicConfig(level=logging.INFO)  # You cen set the level to DEBUG for more info
    logging.info("Logging started")
    session_global = await load_session(cookies_global, cookie_domain_global)
    fb_listener_global = Listener(session=session_global, chat_on=True, foreground=False)
    if not session_global:
        logging.error("Session could not be loaded, login instead!")
        session_global = await Session.login(getuser(), getpass())
        # Save session cookies to file when the program exits
        register(lambda: save_cookies("session.json", session_global.get_cookies()))
    if session_global:
        client = Client(session=session_global)

        listen_fb_task = asyncio.create_task(listen_fb(fb_listener_global, client,
                                                       remote_nick_format, threads, users,
                                                       message_api_url, session_global))
        client.sequence_id_callback = fb_listener_global.set_sequence_id
        await client.fetch_threads(limit=1).__anext__()
        asyncio.create_task(listen_api(session_global, client, stream_api_url,
                                       reverse_threads, users, fb_listener_global))
        await loop_listeners(listen_fb_task, fb_listener_global, client,
                             remote_nick_format, threads, users, message_api_url, session_global)
    else:
        logging.error("No session was loaded, you either need the cookies or a proper login.")


asyncio.run(main())
