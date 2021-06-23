from httpx import AsyncClient, Timeout, RemoteProtocolError, ConnectError
from base64 import standard_b64decode
from json import loads
from asyncio import sleep, create_task
from fbchat import Group, User, FacebookError, MessageEvent, MessageReplyEvent, PleaseRefresh
import logging

from fbridge_send import send_file, send_text, send_msg_to_api
from fbridge_check import find_file_type, check_if_same_authors, check_event_match
from fbridge_handle_extra import format_text_quote, handle_reply
from needed_values import NeededVars
import websockets


async def stop_infinite_timer():
    if NeededVars.timed_out is False:
        NeededVars.run_infinite_timer = False
        NeededVars.timeout_listen = 0
        logging.warning("Stopping infinite timer loop.")
    else:
        NeededVars.timed_out = False


async def disconnect_fb():
    NeededVars.fb_listener_global.disconnect()


async def setup_api():
    NeededVars.api_client = AsyncClient()
    timeout = Timeout(10.0, read=None)
    return timeout


async def out_of_api():
    logging.warning(f"out of api_client stream")
    await NeededVars.api_client.aclose()
    await disconnect_fb()


async def set_timeout(value):
    if NeededVars.run_infinite_timer is True:
        NeededVars.timed_out = value


async def handle_interrupt():
    await set_timeout(False)
    await stop_infinite_timer()
    if NeededVars.listen_api_mode != "websocket":
        await out_of_api()
    else:
        await disconnect_fb()


async def handle_got_message(msg, session, fbchat_client):
    logging.info(f"API Message: {msg}")
    if type(msg) == str:
        resp_json = loads(msg)
    else:
        resp_json = msg
    got_gateway = resp_json.get("gateway")
    if bool(got_gateway) is True:
        got_username = resp_json.get("username")
        file_data = None
        try:
            file_data = resp_json["Extra"]["file"][0]["Data"]
            file_data = standard_b64decode(file_data)
            search_link = False
            got_text = resp_json["Extra"]["file"][0]["Name"]
        except (KeyError, TypeError):
            logging.info(f"From API received json: {resp_json}")
            search_link = True
            got_text = resp_json.get("text")

        img_type_result, filename, cat = await find_file_type(search_text=got_text, search_link=search_link)

        if filename == got_text and search_link is False:
            got_text = f"sent {img_type_result} file"

        fb_thread = NeededVars.reverse_threads[got_gateway]

        thread = Group(session=session, id=fb_thread)
        if fb_thread in NeededVars.users:
            thread = User(session=session, id=fb_thread)

        await send_file(f"{got_username}", thread, fbchat_client, file_data,
                        cat, img_type_result, filename, search_link)

        got_text = await format_text_quote(got_text)

        logging.info(f"From api sending message: username: {got_username} | text: {got_text}")

        await send_text(f"{got_username}{got_text}", thread)

        logging.info(f"Sent message: username: {got_username} | text: {got_text}")


async def listen_api_stream(session, fbchat_client):
    if NeededVars.run_infinite_timer is False:
        return
    timeout = await setup_api()
    logging.info("Starting api_client stream")
    logging.info(f"Using API URL for receiving: {NeededVars.stream_api_url}")
    logging.info(f"Using API URL for sending: {NeededVars.message_api_url}")
    try:
        async with NeededVars.api_client.stream(method="GET", url=NeededVars.stream_api_url, timeout=timeout) as r:
            logging.info(f"API: {r}")
            async for msg in r.aiter_lines():
                await handle_got_message(msg, session, fbchat_client)
    except (RemoteProtocolError, ConnectError) as e:
        logging.error(f"API Exception: {e}")
        await handle_interrupt()


async def listen_api_messages(session, fbchat_client):
    if NeededVars.run_infinite_timer is False:
        return
    timeout = await setup_api()
    logging.info("Starting api_client stream (using messages mode)")
    logging.info(f"Using API URL for receiving: {NeededVars.messages_api_url}")
    logging.info(f"Using API URL for sending: {NeededVars.message_api_url}")
    try:
        while NeededVars.run_infinite_timer is True:
            r = await NeededVars.api_client.get(url=NeededVars.messages_api_url, timeout=timeout)
            resp_json = r.json()
            if len(resp_json) != 0:
                logging.info(f"API: {r}")
                await handle_got_message(resp_json[0], session, fbchat_client)
            else:
                await sleep(0.2)
    except (RemoteProtocolError, ConnectError) as e:
        logging.error(f"API Exception: {e}")
        await handle_interrupt()


async def listen_websocket_messages(session, fbchat_client):
    if NeededVars.run_infinite_timer is False:
        return
    logging.info("Starting api_client stream (using messages mode)")
    logging.info(f"Using API URL for receiving: {NeededVars.websocket_api_url}")
    logging.info(f"Using API URL for sending: {NeededVars.message_api_url}")
    try:
        websocket = await websockets.connect(NeededVars.websocket_api_url)
        while NeededVars.run_infinite_timer is True:
            r = await websocket.recv()
            logging.info(f"r: {r}")
            if len(r) != 0:
                logging.info(f"API: {r}")
                await handle_got_message(r, session, fbchat_client)
    except (RemoteProtocolError, ConnectError) as e:
        logging.error(f"API Exception: {e}")
        await handle_interrupt()


async def timeout_listen_fb():
    logging.info(f"Facebook listener timeout restarted: {NeededVars.timeout_listen} sec")
    await set_timeout(False)
    await sleep(NeededVars.timeout_listen)
    await set_timeout(True)
    await disconnect_fb()
    logging.info("Executed listener disconnect")


async def listen_fb(client, remote_nick_format, session):
    if NeededVars.run_infinite_timer is False:
        return
    logging.info("Listening for Facebook events")
    try:
        async for event in NeededVars.fb_listener_global.listen():
            if isinstance(event, MessageEvent) is True or isinstance(event, MessageReplyEvent) is True:
                # Don't echo back messages to api that are received from the api
                if await check_if_same_authors(event.author.id, session.user.id,
                                               remote_nick_format, event.message.text) is False:
                    logging.info(f"From Facebook event: {event}")
                    logging.info(
                        f"From Facebook received: "
                        f"message: {event.message.text} | "
                        f"from user: {event.author.id} | "
                        f"in thread: {event.thread.id}")

                    got_event_check_result = await check_event_match(event, client,
                                                                     NeededVars.threads, NeededVars.users)
                    gateway = got_event_check_result[0]
                    username = got_event_check_result[1]
                    send_text_txt = got_event_check_result[2]

                    if isinstance(event, MessageEvent):
                        logging.info(
                            f"From Facebook sending to api: "
                            f"username: {username} | "
                            f"gateway: {gateway} | "
                            f"message: {event.message.text}")
                        await send_msg_to_api(gateway, send_text_txt, username)
                        logging.info(f"Sent message to api: event.message.text: {event.message.text}")
                    elif isinstance(event, MessageReplyEvent):
                        reply = event.replied_to
                        logging.info(
                            f"From Facebook sending to api (reply): "
                            f"username: {username} | "
                            f"gateway: {gateway} | "
                            f"message: {event.message.text} | "
                            f"reply author: {reply.author}")
                        format_whole_reply_msg = await handle_reply(event, reply, send_text_txt,
                                                                    client, NeededVars.users)
                        await send_msg_to_api(gateway, format_whole_reply_msg, username)
                        logging.info(f"Sent message to API: send_text_txt: {send_text_txt}")
        logging.warning("Out of Facebook listener loop.")
    except PleaseRefresh as e:
        logging.error(f"Facebook Exception: {e}")
        await handle_interrupt()
    except FacebookError as e:
        logging.error(f"Facebook Exception: {e}")
        await set_timeout(False)
        await disconnect_fb()


async def loop_listeners(listen_fb_task, client, remote_nick_format, session):
    if NeededVars.listen_api_mode == "stream":
        create_task(listen_api_stream(session, client))
    elif NeededVars.listen_api_mode == "messages":
        create_task(listen_api_messages(session, client))
    elif NeededVars.listen_api_mode == "websocket":
        create_task(listen_websocket_messages(session, client))
    create_task(timeout_listen_fb())
    while NeededVars.run_infinite_timer is True:
        if NeededVars.timed_out is True:
            create_task(timeout_listen_fb())
        await listen_fb_task
        listen_fb_task = create_task(listen_fb(client, remote_nick_format, session))
