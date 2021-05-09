from secrets import token_hex
from fbchat import ShareAttachment, VideoAttachment, AudioAttachment, ImageAttachment
import logging


async def get_attachments(attachments, send_text, client):
    url = ''
    if isinstance(attachments[0], ShareAttachment) or \
            isinstance(attachments[0], VideoAttachment) or \
            isinstance(attachments[0], AudioAttachment):  # TODO: Finish me
        return send_text  # you need to find a way to extract the attachments

    if isinstance(attachments[0], ImageAttachment):
        url = await client.fetch_image_url(attachments[0].id)

    logging.info(f"Got URL: {url}")

    if send_text is not None:
        send_text = f"{url} {send_text}"
    else:
        send_text = f"{url}"

    return send_text


async def handle_reply(event, reply, send_text, client, users):
    random_token = token_hex(nbytes=2)

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

    return format_whole_reply_msg


async def format_text_quote(got_text):
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
    return got_text
