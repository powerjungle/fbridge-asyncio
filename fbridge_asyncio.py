from atexit import register
from getpass import getuser, getpass
from fbchat import Session, FacebookError, Listener, Client
from os import path, name
from json import load, dump
import logging
import toml
import asyncio

from fbridge_listen import listen_fb, listen_api, loop_listeners
from needed_values import NeededVars

if not path.exists("fbridge-config.toml"):
    logging.error("Config file fbridge-config.toml doesn't exist")
    exit()

if name == "nt":
    asyncio.DefaultEventLoopPolicy = asyncio.WindowsSelectorEventLoopPolicy

parsed_toml = toml.load("fbridge-config.toml")
if parsed_toml.get("path"):
    parsed_toml = toml.load(parsed_toml["path"])
message_api_url = parsed_toml["message_api_url"]
cookie_domain_global = parsed_toml["cookie_domain"]
th = parsed_toml["threads"]
us = parsed_toml["users"]
stream_api_url = parsed_toml["stream_api_url"]
timeout_listen = parsed_toml["timeout_listen"]
NeededVars.stream_api_url = stream_api_url
NeededVars.timeout_listen = timeout_listen


def load_cookies(filename):
    try:
        # Load cookies from file
        with open(filename) as f:
            return load(f)
    except FileNotFoundError as e:
        logging.error(e)
        return  # No cookies yet


for key, value in th.items():
    NeededVars.threads[key] = value["gateway"]
for key, value in us.items():
    NeededVars.users[key] = value["username"]

NeededVars.reverse_threads = {v: k for k, v in NeededVars.threads.items()}

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
    NeededVars.fb_listener_global = Listener(session=session_global, chat_on=True, foreground=False)
    if not session_global:
        logging.error("Session could not be loaded, login instead!")
        session_global = await Session.login(getuser(), getpass())
        # Save session cookies to file when the program exits
        register(lambda: save_cookies("session.json", session_global.get_cookies()))
    if session_global:
        client = Client(session=session_global)
        listen_fb_task = asyncio.create_task(listen_fb(client, remote_nick_format,
                                                       message_api_url, session_global))
        client.sequence_id_callback = NeededVars.fb_listener_global.set_sequence_id
        await client.fetch_threads(limit=1).__anext__()
        await loop_listeners(listen_fb_task, client,
                             remote_nick_format, message_api_url, session_global)
    else:
        logging.error("No session was loaded, you either need the cookies or a proper login.")


asyncio.run(main())
