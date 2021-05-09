import asyncio
import atexit
import getpass
import fbchat
import os
import json
import toml
import logging
import httpx
import re
import base64
from aiohttp import ClientSession
import secrets

if os.name == "nt":
    asyncio.DefaultEventLoopPolicy = asyncio.WindowsSelectorEventLoopPolicy

threads = dict()
users = dict()

# Reverse lookup
reverse_threads = dict()

remote_nick_format = ""

stream_api_url = ''
message_api_url = ''

api_client = httpx.AsyncClient()
fb_listener_global = None

run_infinite_timer = True
timeout_listen = 3600


# Send message to matterbridge
async def send_msg_to_api(gateway, text, username=''):
    if text is not None:
        headers = {'content-type': 'application/json'}
        payload = {"text": text, "username": username, "gateway": gateway}
        async with httpx.AsyncClient() as client:
            await client.post(message_api_url, data=json.dumps(payload), headers=headers)


def load_cookies(filename):
    try:
        # Load cookies from file
        with open(filename) as f:
            return json.load(f)
    except FileNotFoundError as e:
        logging.error(e)
        return  # No cookies yet


def save_cookies(filename, cookies):
    with open(filename, "w") as f:
        json.dump(cookies, f)


async def load_session(cookies, cookie_domain):
    if not cookies:
        return

    try:
        return await fbchat.Session.from_cookies(cookies, domain=cookie_domain)
    except fbchat.FacebookError as e:
        logging.error(e)
        return  # Failed loading from cookies


async def find_file_type(search_text, search_link=True, url_protocol="http"):
    types = {"image": ["jpg", "png", "jpeg", "gif", "webp"], "video": ["webm"]}

    found_type = None
    found_url = None
    found_cat = None

    for tp in types:
        for find_tp in types[tp]:
            try:
                if search_link is True:
                    find_img_url = re.search(url_protocol + r".+\.(" + find_tp + ")", search_text)
                else:
                    find_img_url = re.search(r".+\.(" + find_tp + ')$', search_text)
            except TypeError as e:
                logging.info(f"searching for file returned: {e}")
                break
            else:
                if find_img_url:
                    found_url = find_img_url.group(0)
                    found_type = find_img_url.group(1)
                    found_cat = tp
                    logging.info(f"found_url: {found_url} ; found_type: {found_type} ; found_cat: {found_cat}")
                    break

    if found_type == "jpg":
        found_type = "jpeg"

    if found_type == "webp":
        found_type = "png"

    return found_type, found_url, found_cat


async def listen_api(session, fbchat_client):
    timeout = httpx.Timeout(10.0, read=None)
    logging.info("Starting api_client stream")
    async with api_client.stream(method="GET", url=stream_api_url, timeout=timeout) as r:
        logging.info(f"response: {r}")
        try:
            async for msg in r.aiter_lines():
                resp_json = json.loads(msg)

                if resp_json:
                    got_gateway = resp_json.get("gateway")
                    got_text = resp_json.get("text")
                    got_username = resp_json.get("username")

                    search_link = True

                    try:
                        filedata = resp_json["Extra"]["file"][0]["Data"]
                    except (KeyError, TypeError):
                        logging.info(f"From api received json: {resp_json}")
                    else:
                        search_link = False
                        filedata = base64.standard_b64decode(filedata)
                        got_text = resp_json["Extra"]["file"][0]["Name"]

                    img_type_result, filename, cat = await find_file_type(search_text=got_text, search_link=search_link)

                    if filename == got_text and search_link is False:
                        got_text = f"sent {img_type_result} file"

                    if got_gateway:
                        fb_thread = reverse_threads[got_gateway]

                        if fb_thread in users:
                            thread = fbchat.User(session=session, id=fb_thread)
                        else:
                            thread = fbchat.Group(session=session, id=fb_thread)

                        if img_type_result is not None:
                            if search_link is True:
                                async with ClientSession() as sess, sess.get(filename) as resp:
                                    image_data = await resp.read()
                            else:
                                image_data = filedata

                            try:
                                files = await fbchat_client.upload(
                                    [(filename, image_data, cat + "/" + img_type_result)]
                                )
                                try:
                                    await thread.send_text(text=f"{got_username}", files=files)
                                except fbchat.FacebookError as e:
                                    logging.error(e)

                            except fbchat.ExternalError as e:
                                logging.error(e)

                        if len(got_text.splitlines()) > 1 and got_text.startswith('>'):
                            split_lines = got_text.splitlines()
                            got_text = ''
                            count = 0
                            for line in split_lines:
                                if not line.startswith('>'):
                                    break
                                count += 1

                            try:
                                split_lines[count] = '\n' + split_lines[count]
                            except IndexError:
                                pass

                            for line in split_lines:
                                got_text += '\n' + line
                        elif got_text.startswith('>'):
                            got_text = '\n' + got_text

                        logging.info(f"From api sending message: username: {got_username} | text: {got_text}")

                        try:
                            await thread.send_text(f"{got_username}{got_text}")
                        except fbchat.FacebookError as e:
                            logging.error(e)

                        logging.info(f"Sent message: username: {got_username} | text: {got_text}")
        except httpx.RemoteProtocolError as e:
            logging.error(e)

    logging.error(f"out of api_client stream")
    try:
        fb_listener_global.disconnect()
    except fbchat.FacebookError as e:
        logging.error(e)
    global run_infinite_timer
    run_infinite_timer = False
    global timeout_listen
    timeout_listen = 1
    logging.info("Stopping infinite timer loop.")


async def get_attachments(attachments, send_text, client):
    url = ''
    if isinstance(attachments[0], fbchat.ShareAttachment) or \
            isinstance(attachments[0], fbchat.VideoAttachment) or \
            isinstance(attachments[0], fbchat.AudioAttachment):  # TODO: Finish me
        return send_text  # you need to find a way to extract the attachments

    if isinstance(attachments[0], fbchat.ImageAttachment):
        url = await client.fetch_image_url(attachments[0].id)

    logging.info(f"Got URL: {url}")

    if send_text is not None:
        send_text = f"{url} {send_text}"
    else:
        send_text = f"{url}"

    return send_text


async def listen_fb(fb_listener, session, client):
    logging.info("Listening for fb events")
    try:
        async for event in fb_listener.listen():
            if isinstance(event, fbchat.MessageEvent) or isinstance(event, fbchat.MessageReplyEvent):
                run_rest = True
                # Don't echo back messages to api that are received from the api
                if event.author.id == session.user.id:
                    try:
                        # Find the configured pattern to ignore
                        regex = re.search(r'' + remote_nick_format, event.message.text)
                    except TypeError:
                        pass  # Just go on error, so that the script doesn't stop
                    else:
                        if regex:
                            run_rest = False

                if run_rest is True:
                    logging.info(f"From fb event: {event}")
                    logging.info(
                        f"From fb received: "
                        f"message: {event.message.text} | "
                        f"from user: {event.author.id} | "
                        f"in thread: {event.thread.id}")

                    gateway = ""
                    username = ""

                    if event.thread.id in threads:
                        gateway = threads[event.thread.id]

                    if event.author.id in users:
                        username = users[event.author.id]

                    send_text = event.message.text

                    if event.message.attachments:
                        send_text = await get_attachments(event.message.attachments, send_text, client)

                    if isinstance(event, fbchat.MessageEvent):
                        logging.info(
                            f"From fb sending to api: "
                            f"username: {username} | "
                            f"gateway: {gateway} | "
                            f"message: {event.message.text}")
                        await send_msg_to_api(gateway, send_text, username)
                        logging.info(f"Sent message to api: event.message.text: {event.message.text}")
                    elif isinstance(event, fbchat.MessageReplyEvent):
                        random_token = secrets.token_hex(nbytes=2)

                        reply = event.replied_to

                        logging.info(
                            f"From fb sending to api (reply): "
                            f"username: {username} | "
                            f"gateway: {gateway} | "
                            f"message: {event.message.text} | "
                            f"reply author: {reply.author}")
                        event_msg = send_text

                        author_nick = None
                        if reply.author != '':
                            author_nick = users.get(reply.author)

                        format_event_msg = ''
                        for line in event_msg.splitlines(keepends=True):
                            format_event_msg += f"({random_token}) {line}"

                        event_msg = f"[Reply]: \n" + format_event_msg

                        if event.replied_to.attachments:
                            event_msg = await get_attachments(event.replied_to.attachments, event_msg, client)
                            event_msg += f"\n({random_token}) [Attachment from]: {author_nick}"

                        format_only_reply_msg = ''
                        if reply.text is not None:
                            format_only_reply_msg += f"[Quote from]: {author_nick}:\n"
                            for line in reply.text.splitlines(keepends=True):
                                format_only_reply_msg += f"({random_token}) {line}"

                        format_whole_reply_msg = \
                            f"({random_token}) {format_only_reply_msg}\n" \
                            f"({random_token}) {event_msg}"
                        await send_msg_to_api(gateway, format_whole_reply_msg, username)
                        logging.info(f"Sent message to api: event_msg: {event_msg}")
        logging.warning("Out of fb listener loop.")
    except fbchat.FacebookError as e:
        logging.error(e)
        await api_client.aclose()
        return


async def timeout_listen_fb():
    logging.info(f"Fb listener timeout restarted: {timeout_listen} sec")
    await asyncio.sleep(timeout_listen)
    try:
        fb_listener_global.disconnect()
    except fbchat.FacebookError as e:
        logging.error(e)
        exit()
    logging.info("Executed listener disconnect")


async def main():
    logging.basicConfig(level=logging.INFO)  # You cen set the level to DEBUG for more info

    logging.info("Logging started")

    global threads
    global users
    global reverse_threads
    global remote_nick_format

    global stream_api_url
    global message_api_url

    if not os.path.exists("fbridge-config.toml"):
        logging.error("Config file fbridge-config.toml doesn't exist")
        return

    parsed_toml = toml.load("fbridge-config.toml")

    if parsed_toml.get("path"):
        parsed_toml = toml.load(parsed_toml["path"])

    stream_api_url = parsed_toml["stream_api_url"]
    message_api_url = parsed_toml["message_api_url"]

    cookie_domain = parsed_toml["cookie_domain"]

    th = parsed_toml["threads"]
    us = parsed_toml["users"]

    for key, value in th.items():
        threads[key] = value["gateway"]
    for key, value in us.items():
        users[key] = value["username"]

    reverse_threads = {v: k for k, v in threads.items()}

    remote_nick_format = parsed_toml["RemoteNickFormat"]

    session_toml = "session.toml"

    if os.path.exists(session_toml):
        parsed_cookie_toml = toml.load(session_toml)
        got_session_path = parsed_cookie_toml["path"]
        cookies = load_cookies(got_session_path)
    else:
        cookies = load_cookies("session.json")

    session = await load_session(cookies, cookie_domain)
    if not session:
        logging.error("Session could not be loaded, login instead!")
        session = await fbchat.Session.login(getpass.getuser(), getpass.getpass())
        # Save session cookies to file when the program exits
        atexit.register(lambda: save_cookies("session.json", session.get_cookies()))

    if session:
        client = fbchat.Client(session=session)
        global fb_listener_global
        fb_listener_global = fbchat.Listener(session=session, chat_on=True, foreground=False)
        fb_listener = fb_listener_global

        listen_fb_task = asyncio.create_task(listen_fb(fb_listener, session, client))

        client.sequence_id_callback = fb_listener.set_sequence_id
        await client.fetch_threads(limit=1).__anext__()

        asyncio.create_task(listen_api(session, client))

        while run_infinite_timer is True:
            asyncio.create_task(timeout_listen_fb())
            await listen_fb_task
            listen_fb_task = asyncio.create_task(listen_fb(fb_listener, session, client))

    else:
        logging.error("No session was loaded, you either need the cookies or a proper login.")


asyncio.run(main())
