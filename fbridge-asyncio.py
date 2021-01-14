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
from aiohttp import ClientSession

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


async def listen_api(session, fbchat_client):
    timeout = httpx.Timeout(10.0, read=None)
    async with api_client.stream(method="GET", url=stream_api_url, timeout=timeout) as r:
        logging.info(f"response: {r}")
        try:
            async for msg in r.aiter_lines():
                resp_json = json.loads(msg)
                logging.info(resp_json)
                if resp_json:
                    logging.info(f"From api received json: {resp_json}")

                    got_gateway = resp_json.get("gateway")
                    got_text = resp_json.get("text")
                    got_username = resp_json.get("username")

                    found_img_url = None
                    found_img_type = None

                    img_types = ["jpg", "png", "jpeg", "gif", "webp"]

                    for imgt in img_types:
                        try:
                            find_img_url = re.search(r"http.+\.(" + imgt + ')', got_text)
                        except TypeError:
                            logging.info("TypeError")
                        else:
                            if find_img_url:
                                found_img_url = find_img_url.group(0)
                                found_img_type = find_img_url.group(1)

                        if found_img_type == "jpg":
                            found_img_type = "jpeg"

                        if found_img_type == "webp":
                            found_img_type = "png"

                    if got_gateway:
                        fb_thread = reverse_threads[got_gateway]

                        if fb_thread in users:
                            thread = fbchat.User(session=session, id=fb_thread)
                        else:
                            thread = fbchat.Group(session=session, id=fb_thread)

                        if found_img_url is not None:
                            async with ClientSession() as sess, sess.get(found_img_url) as resp:
                                image_data = await resp.read()

                            try:
                                files = await fbchat_client.upload(
                                    [("image_name.png", image_data, "image/" + found_img_type)]
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
            try:
                fb_listener_global.disconnect()
            except fbchat.FacebookError as e:
                logging.error(e)
    logging.error(f"out of client.stream")


async def get_attachments(attachments, send_text, client):
    url = ''
    if isinstance(attachments[0], fbchat.ShareAttachment) or \
            isinstance(attachments[0], fbchat.VideoAttachment) or \
            isinstance(attachments[0], fbchat.AudioAttachment):  # TODO: Finish me
        return send_text  # you need to find a way to extract the attachments

    if isinstance(attachments[0], fbchat.ImageAttachment):
        url = await client.fetch_image_url(attachments[0].id)

    logging.info(f"got url: {url}")

    if send_text is not None:
        send_text = f"{url} {send_text}"
    else:
        send_text = f"{url}"

    return send_text


async def listen_fb(fb_listener, session, client):
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
                        reply = event.replied_to
                        logging.info(
                            f"From fb sending to api (reply): "
                            f"username: {username} | "
                            f"gateway: {gateway} | "
                            f"message: {event.message.text} | "
                            f"reply author: {reply.author}")
                        event_msg = send_text
                        if reply.author != '':
                            author_nick = users.get(reply.author)
                            if author_nick == username:
                                event_msg = "replied to self: " + event_msg
                            else:
                                event_msg = f"replied to {author_nick}: " + event_msg

                        if event.replied_to.attachments:
                            event_msg = await get_attachments(event.replied_to.attachments, event_msg, client)

                        format_only_reply_msg = ''
                        if reply.text is not None:
                            for line in reply.text.splitlines(keepends=True):
                                format_only_reply_msg += "> " + line

                        format_whole_reply_msg = \
                            f"\n{format_only_reply_msg}\n" \
                            f"{event_msg}"
                        await send_msg_to_api(gateway, format_whole_reply_msg, username)
                        logging.info(f"Sent message to api: event_msg: {event_msg}")
    except fbchat.FacebookError as e:
        logging.error(e)
        await api_client.aclose()
        return


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

        await listen_api(session, client)

        await listen_fb_task
    else:
        logging.error("No session was loaded, you either need the cookies or a proper login.")


asyncio.run(main())
