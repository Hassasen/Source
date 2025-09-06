from telethon import TelegramClient, events
import asyncio
import random
import os
import json
from urllib.parse import urlparse
import re

# ====== إعداداتك ======
api_id = 21473023
api_hash = "f539471b07734d6872f25403010afa1d"
session_name = "auto_join_userbot"
ADMIN_GROUP_ID = -1002761489692

DATA_FILE = "last_forwarded.json"

client = TelegramClient(session_name, api_id, api_hash)


def load_last_forwarded():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_last_forwarded(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def random_delay():
    await asyncio.sleep(random.randint(5, 10))


async def is_admin(dialog):
    try:
        participant = await client.get_permissions(dialog.id, 'me')
        return getattr(participant, 'is_admin', False) or getattr(participant, 'is_creator', False)
    except Exception:
        return False


def get_dialog_link_from_entity(entity_id, username=None):
    if username:
        return f"https://t.me/{username}"
    else:
        return f"https://t.me/c/{str(entity_id).replace('-100', '')}"


def get_dialog_link(dialog):
    if hasattr(dialog.entity, 'username') and dialog.entity.username:
        return f"https://t.me/{dialog.entity.username}"
    else:
        return f"https://t.me/c/{str(dialog.id).replace('-100', '')}"


def extract_forwarded_id(result):
    try:
        if isinstance(result, list):
            if len(result) > 0 and hasattr(result[0], "id"):
                return result[0].id
        elif hasattr(result, "id"):
            return result.id
        else:
            return None
    except Exception:
        return None


last_forwarded = load_last_forwarded()


@client.on(events.NewMessage(chats=ADMIN_GROUP_ID, pattern=r'^\.انشر (https?://t\.me/\S+/\d+)$'))
async def on_publish(event):
    global last_forwarded
    post_link = event.pattern_match.group(1)
    await event.respond('جاري تحديث قائمة القنوات والمجموعات المشرف فيها...')

    dialogs = []
    async for dialog in client.iter_dialogs():
        if dialog.is_channel or dialog.is_group:
            if await is_admin(dialog):
                dialogs.append(dialog)

    if not dialogs:
        await event.respond('❌ لا توجد قنوات أو مجموعات مشرف فيها لنشر المنشور.')
        return

    last_forwarded = {}
    save_last_forwarded(last_forwarded)

    try:
        url_path = urlparse(post_link).path
        match = re.match(r'^/(\S+)/(\d+)$', url_path)
        if not match:
            await event.respond('❌ الرابط غير صحيح.')
            return

        username = match.group(1)
        src_msg_id = int(match.group(2))
        src_entity = await client.get_entity(username)
    except Exception as e:
        await event.respond(f'❌ خطأ بجلب المنشور: {e}')
        return

    success = 0
    failed_channels = []

    for d in dialogs:
        try:
            res = await client.forward_messages(d.id, src_msg_id, from_peer=src_entity)
            fwd_id = extract_forwarded_id(res)
            if fwd_id:
                last_forwarded[str(d.id)] = {
                    "message_id": fwd_id,
                    "name": d.name or str(d.id),
                    "link": get_dialog_link(d)
                }
                save_last_forwarded(last_forwarded)
                success += 1
            else:
                failed_channels.append({"name": d.name or str(d.id), "link": get_dialog_link(d)})
        except Exception:
            failed_channels.append({"name": d.name or str(d.id), "link": get_dialog_link(d)})
        await random_delay()

    await event.respond(f'✅ تم تحويل المنشور إلى {success} قناة/غروب.\n⚠️ فشل في {len(failed_channels)} جهة.')

    if failed_channels:
        text = "⚠️ فشل النشر في:\n"
        text += "\n".join(f"{i+1}) {c['name']} - {c['link']}" for i, c in enumerate(failed_channels))
        await client.send_message(ADMIN_GROUP_ID, text)


@client.on(events.NewMessage(chats=ADMIN_GROUP_ID, pattern=r'^\.احذف$'))
async def on_delete(event):
    global last_forwarded
    await event.respond('جاري حذف الرسائل التي نشرها الحساب (المخزّنة)...')

    if not last_forwarded:
        await event.respond("❌ ما في منشورات محفوظة للحذف.")
        return

    deleted = 0
    failed = []

    items = list(last_forwarded.items())

    for chat_id_str, info in items:
        chat_id = int(chat_id_str)
        msg_id = info.get("message_id")
        name = info.get("name", str(chat_id))
        link = info.get("link", get_dialog_link_from_entity(chat_id))

        try:
            # 1) نتأكد أولاً إذا الرسالة موجودة فعلاً
            existing = await client.get_messages(chat_id, ids=msg_id)
            if not existing:
                # الرسالة غير موجودة => فشل
                failed.append({"name": name, "link": link})
                await random_delay()
                continue

            # 2) نحاول نحذف الرسالة اللي احنا حفظناها
            try:
                await client.delete_messages(chat_id, msg_id)
                deleted += 1
                # حذف من القاموس لأن الحذف نجح
                if chat_id_str in last_forwarded:
                    del last_forwarded[chat_id_str]
                    save_last_forwarded(last_forwarded)
            except Exception:
                # أي خطأ أثناء الحذف => فشل
                failed.append({"name": name, "link": link})
        except Exception:
            # أي خطأ أثناء جلب الرسالة نعتبر فشل
            failed.append({"name": name, "link": link})

        await random_delay()

    await event.respond(f'🗑️ تم حذف {deleted} رسالة.\n⚠️ فشل حذف {len(failed)} جهة.')

    if failed:
        text = "⚠️ فشل الحذف في:\n"
        text += "\n".join(f"{i+1}) {c['name']} - {c['link']}" for i, c in enumerate(failed))
        await client.send_message(ADMIN_GROUP_ID, text)

    if not last_forwarded:
        save_last_forwarded(last_forwarded)


if __name__ == "__main__":
    print('✅ جاري التشغيل...')
    client.start()
    client.run_until_disconnected()