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
        logging.info(e)
        return  # No cookies yet


def save_cookies(filename, cookies):
    with open(filename, "w") as f:
        json.dump(cookies, f)


async def load_session(cookies):
    if not cookies:
        return

    try:
        # Set the domain to the one you took the cookie data from
        return await fbchat.Session.from_cookies(cookies, domain="facebook.com")
    except fbchat.FacebookError as e:
        logging.info(e)
        return  # Failed loading from cookies


async def listen_api(session, fbchat_client):
    client = httpx.AsyncClient()
    timeout = httpx.Timeout(10.0, read=None)
    async with client.stream(method="GET", url=stream_api_url, timeout=timeout) as r:
        logging.info(f"response: {r}")
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
                        pass
                    else:
                        if find_img_url:
                            found_img_url = find_img_url.group(0)
                            found_img_type = find_img_url.group(1)

                    if found_img_type == "jpg":
                        found_img_type = "jpeg"

                    if found_img_type == "webp":
                        found_img_type = "png"

                # logging.info(f"found img: {found_img_url}")
                # logging.info(f"found img type: {found_img_type}")
                # logging.info(got_username)
                # logging.info(got_text)
                # logging.info(got_gateway)

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
                                [("image_name.png", image_data, "image/" + found_img_type)])
                            await thread.send_files(files)  # Alternative to .send_text
                        except fbchat.ExternalError as e:
                            logging.error(e)

                    logging.info(f"From api sending message: username: {got_username} | text: {got_text}")

                    await thread.send_text(f"{got_username}{got_text}")

                    logging.info(f"Sent message: username: {got_username} | text: {got_text}")
        logging.warning("listen_api: out of loop")
    logging.error(f"out of client.stream")


async def get_attachments(attachments, send_text):
    proper_elements = dict()
    count = 0
    got_attachments = []

    if isinstance(attachments[0], fbchat.ShareAttachment) or \
            isinstance(attachments[0], fbchat.VideoAttachment) or \
            isinstance(attachments[0], fbchat.AudioAttachment):  # TODO: Finish me
        ''' you need to find a way to exctract the original img url from
        the attachment and the video, from the video attachment
        
        orig_img_url = attachments[0].image.original_image_url

        if send_text is not None:
            send_text = f"{orig_img_url} {send_text}"
        else:
            send_text = f"{orig_img_url}"
        
        '''

        return send_text

    for img_pr in attachments[0].previews:
        got_attachments.append(img_pr.url)
        if img_pr.width is not None:
            proper_elements[count] = img_pr.width * img_pr.height
        count += 1

    # print(proper_elements)

    if len(proper_elements) > 1:
        proper_elements = sorted(proper_elements, key=proper_elements.get)

    # print(proper_elements)

    last_element = 0
    for x in proper_elements:
        last_element = x

    # print(last_element)

    if send_text is not None:
        send_text = f"{got_attachments[last_element]} {send_text}"
    else:
        send_text = f"{got_attachments[last_element]}"

    return send_text


async def listen_fb(listener, session):
    async for event in listener.listen():
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

                # This is temporary until a solution that allows the bot to post images without echo is found.
                if event.message.text is None:
                    logging.info("Ignoring attachments from bot acc in fb to prevent echo.")
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
                    send_text = await get_attachments(event.message.attachments, send_text)

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
                        event_msg = await get_attachments(event.replied_to.attachments, event_msg)

                    format_only_reply_msg = ''
                    if reply.text is not None:
                        for line in reply.text.splitlines(keepends=True):
                            format_only_reply_msg += "> " + line

                    format_whole_reply_msg = \
                        f"\n{format_only_reply_msg}\n" \
                        f"{event_msg}"
                    await send_msg_to_api(gateway, format_whole_reply_msg, username)
                    logging.info(f"Sent message to api: event_msg: {event_msg}")
    logging.warning("listen_fb: out of loop")


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
        logging.info("Config file fbridge-config.toml doesn't exist")
        return

    parsed_toml = toml.load("fbridge-config.toml")

    stream_api_url = parsed_toml["stream_api_url"]
    message_api_url = parsed_toml["message_api_url"]

    th = parsed_toml["threads"]
    us = parsed_toml["users"]

    for key, value in th.items():
        threads[key] = value["gateway"]
    for key, value in us.items():
        users[key] = value["username"]

    reverse_threads = {v: k for k, v in threads.items()}

    remote_nick_format = parsed_toml["RemoteNickFormat"]

    cookies = load_cookies("session.json")
    session = await load_session(cookies)
    if not session:
        logging.error("Session could not be loaded, login instead!")
        session = await fbchat.Session.login(getpass.getuser(), getpass.getpass())
        # Save session cookies to file when the program exits
        atexit.register(lambda: save_cookies("session.json", session.get_cookies()))

    if session:
        client = fbchat.Client(session=session)
        listener = fbchat.Listener(session=session, chat_on=True, foreground=False)

        asyncio.create_task(listen_fb(listener, session))

        client.sequence_id_callback = listener.set_sequence_id
        await client.fetch_threads(limit=1).__anext__()

        # api_task = asyncio.create_task(listen_api(session, client))
        # await api_task

        await listen_api(session, client)
    else:
        logging.error("No session was loaded, you either need the cookies or a proper login.")


asyncio.run(main())
