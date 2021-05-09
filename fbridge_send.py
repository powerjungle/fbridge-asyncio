from aiohttp import ClientSession
from httpx import AsyncClient
from json import dumps
from fbchat import FacebookError, ExternalError
import logging


async def send_text(text, thread, files=None):
    try:
        await thread.send_text(text=text, files=files)
    except FacebookError as e:
        logging.error(e)


async def send_file(text, thread, fbchat_client, filedata, cat,
                    img_type_result=None, filename=None, search_link=None):
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
            await send_text(text, thread, files)
        except ExternalError as e:
            logging.error(e)


# Send message to matterbridge
async def send_msg_to_api(gateway, text, message_api_url, username=''):
    if text is not None:
        headers = {'content-type': 'application/json'}
        payload = {"text": text, "username": username, "gateway": gateway}
        async with AsyncClient() as client:
            await client.post(message_api_url, data=dumps(payload), headers=headers)
