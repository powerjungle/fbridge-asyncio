from re import search
import logging

from fbridge_handle_extra import get_attachments


async def find_ignore_path(regex_format, text):
    try:
        # Find the configured pattern to ignore
        regex = search(r'' + regex_format, text)
    except TypeError:
        pass  # Just go on error, so that the script doesn't stop
    else:
        if regex:
            return True
    return False


async def check_if_same_authors(event, session, regex_format, text):
    if event == session:
        return await find_ignore_path(regex_format, text)
    return False


async def check_event_match(event, client, threads, users):
    gateway = ''
    if event.thread.id in threads:
        gateway = threads[event.thread.id]

    username = ''
    if event.author.id in users:
        username = users[event.author.id]

    send_text = event.message.text
    if event.message.attachments:
        send_text = await get_attachments(event.message.attachments, send_text,
                                                               client)

    return [gateway, username, send_text]


async def find_file_type(search_text, search_link=True, url_protocol="https"):
    types = {"image": ["jpg", "png", "jpeg", "gif", "webp"], "video": ["webm"]}

    found_type = None
    found_url = None
    found_cat = None

    for tp in types:
        for find_tp in types[tp]:
            try:
                if search_link is True:
                    find_img_url = search(url_protocol + r".+\.(" + find_tp + ")", search_text)
                else:
                    find_img_url = search(r".+\.(" + find_tp + ')$', search_text)
            except TypeError as e:
                logging.info(f"searching for file returned: {e}")
                break

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
