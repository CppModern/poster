import csv
import os
import tempfile
import telegram
from telegram import InlineKeyboardMarkup
from telegram import InlineKeyboardButton
from telegram.chatmember import ChatMemberAdministrator
import worker2
from pathlib import Path
import _signals
import utils

MARKDOWN = telegram.parsemode.ParseMode.MARKDOWN
CancelSignal = _signals.CancelSignal
StopSignal = _signals.StopSignal


def group_menu(worker: "worker2.Worker", selection: telegram.CallbackQuery = None):
    data = {
        "add": worker.loc.get("group_add"),
        "del": worker.loc.get("group_delete"),
        "view": worker.loc.get("group_view")
    }
    add, delete, view = "add", "del", "view"
    buttons = utils.buildmenubutton(data)
    if selection:
        selection.edit_message_text(
            worker.loc.get("group_menu_clicked"),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=telegram.ParseMode.MARKDOWN
        )
    else:
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("group_menu_clicked"),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
    if selection.data == "cmd_cancel":
        return worker.admin_menu(selection=selection)
    if selection.data == add:
        selection.edit_message_text(
            worker.loc.get("group_username"),
            reply_markup=worker.cancel_marked,
            parse_mode=telegram.ParseMode.MARKDOWN
        )
        selection = worker.wait_for_regex("(.+)", cancellable=True)
        if isinstance(selection, telegram.Update):
            return worker.admin_group_menu(selection=selection.callback_query)
        try:
            admins = worker.bot.getChatAdministrators(selection)
        except telegram.error.BadRequest as e:
            if "not found" in e.message:
                worker.bot.send_message(
                    worker.chat.id,
                    worker.loc.get("group_not_found")
                )
                return group_menu(worker)
        can_manage = False
        for admin in admins:
            admin: ChatMemberAdministrator
            if admin.user == worker.bot.bot:
                if admin.can_manage_chat:
                    can_manage = True
        if not can_manage:
            # inform the admin to add the  bot to the group
            worker.bot.send_message(
                worker.chat.id,
                worker.loc.get("group_admin_error")
            )
            return group_menu(worker)
        info = worker.bot.getChat(selection)
        group_id, group_title = info["id"], info["title"]
        print(f"ID {group_id}")
        data = {"group_id": group_id, "group_title": group_title}
        worker.add_group(data)

        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("group_add_ok").format(group_title)
        )
        return group_menu(worker)
    elif selection.data == view:
        groups = worker.get_groups()
        if not groups:
            selection.edit_message_text(
                worker.loc.get("group_not_available"),
                parse_mode=telegram.ParseMode.MARKDOWN
            )
            return group_menu(worker)
        msg = worker.loc.get("groups_intro")
        found = False
        for group in groups:
            if group["group_id"] in [1234, 5678]:
                continue
            try:
                group_json = worker.bot.getChat(group["group_id"])
                print(group_json)
            except Exception:
                worker.delete_group(group["group_id"])
                continue
            found = True
            username = group_json["username"]
            title = group_json["title"]
            info = f"[{title}](https://t.me/{username}) \n\n"
            msg = msg + info
        if not found:
            selection.edit_message_text(
                worker.loc.get("group_not_available"),
                parse_mode=telegram.ParseMode.MARKDOWN
            )
            return group_menu(worker)
        selection.edit_message_text(
            msg,
            parse_mode=telegram.ParseMode.MARKDOWN
        )
        return group_menu(worker)
    elif selection.data == delete:
        groups = worker.get_groups()
        if not groups:
            selection.edit_message_text(
                worker.loc.get("group_not_available"),
                parse_mode=telegram.ParseMode.MARKDOWN
            )
            return group_menu(worker)

        gdata = {}
        for group in groups:
            gdata[group["group_id"]] = group["group_title"]
        buttons = utils.buildmenubutton(gdata)
        selection.edit_message_text(
            worker.loc.get("group_delete_info"),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=telegram.ParseMode.MARKDOWN
        )
        selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            return group_menu(worker, selection=selection)
        worker.delete_group(selection.data)
        selection.edit_message_text(
            worker.loc.get("group_deleted")
        )
        return group_menu(worker)


def postmenu(worker: "worker2.Worker", selection: telegram.CallbackQuery = None):
    data = {
        "new": worker.loc.get("newPost"),
        "hist": worker.loc.get("myPost")
    }
    buttons = utils.buildmenubutton(data)
    selection.edit_message_text(
        worker.loc.get("post_menu_clicked"),
        parse_mode=MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
    if selection.data == "cmd_cancel":
        return worker.admin_menu(selection=selection)
    if selection.data == "new":
        """userinfo = worker.get_user(worker.telegram_user.id)
        if not userinfo["balance"] or not userinfo["slots"]:
            if selection:
                selection.edit_message_text(
                    worker.loc.get("post_insufficient_balance_or_slots")
                )
                return postmenu(worker)
            worker.bot.send_message(
                worker.chat.id,
                worker.loc.get("post_insufficient_balance_or_slots")
            )
            return postmenu(worker)"""
        groups = worker.get_groups()

        if not groups:
            if selection:
                selection.edit_message_text(
                    worker.loc.get("group_not_available")
                )
                return postmenu(worker)
            worker.bot.send_message(
                worker.chat.id,
                worker.loc.get("group_not_available")
            )
            return postmenu(worker)
        selection.edit_message_text(
            worker.loc.get("post_text"),
            reply_markup=worker.cancel_marked,
            parse_mode=MARKDOWN
        )
        selection = worker.wait_for_regex("(.*)", cancellable=True, mark=True)
        if isinstance(selection, telegram.Update):
            return postmenu(worker, selection.callback_query)
        text = selection
        gdata = {}
        for group in groups:
            gdata[group["group_id"]] = group["group_title"]
        buttons = utils.buildmenubutton(gdata)
        buttons.append([InlineKeyboardButton(worker.loc.get("menu_done"), callback_data="cmd_done")])
        buttons_copy = list(buttons)
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("post_groups"),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        selected = 0
        while True:
            selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
            if selection.data == "cmd_cancel":
                return worker.admin_post_menu(selection=selection)
            elif selection.data == "cmd_done":
                # check at least one user selected for the pm
                if not selected:
                    continue
                else:
                    break
            for kb in buttons_copy:
                for k in kb:
                    if k.callback_data == selection.data:
                        if "✅" in k.text:
                            k.text = k.text.replace("✅", "")
                            selected -= 1
                        else:
                            k.text = k.text + " ✅"
                            selected += 1
            selection.edit_message_text(
                worker.loc.get("post_groups"),
                reply_markup=InlineKeyboardMarkup(buttons_copy)
            )
        ids = []
        for kb in buttons_copy:
            for k in kb:
                if "✅" in k.text and (k.callback_data != "cmd_done"):
                    ids.append(k.callback_data)
        groups = " ".join(ids)
        groups = groups.strip()
        buttons = utils.buildmenubutton({}, skip=True)
        selection.edit_message_text(
            worker.loc.get("post_media"),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        selection = worker.wait_for_photo(cancellable=True)
        data = selection
        has_media = False
        if isinstance(data, telegram.Update):
            if data.callback_query.data == "cmd_cancel":
                return postmenu(worker, selection.callback_query)
        else:
            has_media = True
            if isinstance(data, list):
                first: telegram.PhotoSize = data[0]
                media = first.file_id
                media_type = 0
            elif isinstance(data, telegram.Video):
                media = data.file_id
                media_type = 1
            elif isinstance(data, telegram.Animation):
                media = data.file_id
                media_type = 2

        skip = utils.buildmenubutton({}, skip=True)
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("post_buttons"),
            reply_markup=InlineKeyboardMarkup(skip)
        )
        hasbutt = False
        while True:
            selection = worker.wait_for_regex("(.+)", cancellable=True)
            if isinstance(selection, telegram.Update):
                if selection.callback_query.data == "cmd_cancel":
                    return postmenu(worker, selection.callback_query)
                break
            raw = selection.split("\n")
            if not all([len(i.split("|")) == 2 for i in raw]):
                worker.bot.send_message(
                    worker.chat.id,
                    worker.loc.get("post_buttons"),
                    reply_markup=InlineKeyboardMarkup(skip)
                )
                continue
            hasbutt = True
            break
        if hasbutt:
            pbutt = ""
            blist = []
            for line in raw:
                line = line.split("|")
                disp = line[0].strip()
                link = line[1].strip()
                if not link.startswith("https") or not link.startswith("http"):
                    continue
                blist.append(
                    [InlineKeyboardButton(disp, url=link)]
                )

                line = f"{disp}|{link}"
                pbutt += line + "<>"
            pbutt = pbutt.rsplit("<>", 1)[0]
            pbutt = pbutt.strip()
        # Post duration
        data = {
            "fivemin": worker.loc.get("fivemin"),
            "tenmin": worker.loc.get("tenmin"),
            "thirtymin": worker.loc.get("thirtymin"),
            "onehour": worker.loc.get("onehour")
        }
        durbuttons = utils.buildmenubutton(data)
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("duration"),
            reply_markup=InlineKeyboardMarkup(durbuttons)
        )
        selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            return postmenu(worker, selection)

        #  Post confirmation
        duration = selection.data
        log = selection.edit_message_text(
            worker.loc.get("confirm_info")
        )
        try:
            if not has_media:
                if not hasbutt:
                    msg = worker.bot.send_message(
                            worker.chat.id,
                            text
                    )
                else:
                    msg = worker.bot.send_message(
                        worker.chat.id,
                        text,
                        reply_markup=InlineKeyboardMarkup(blist)
                    )
            else:
                if hasbutt:
                    if media_type == 0:
                        msg = worker.bot.send_photo(
                            worker.chat.id,
                            photo=media,
                            caption=text,
                            reply_markup=InlineKeyboardMarkup(blist),
                            parse_mode=MARKDOWN
                        )
                    elif media_type == 1:
                        msg = worker.bot.send_video(
                            worker.chat.id,
                            video=media,
                            caption=text,
                            reply_markup=InlineKeyboardMarkup(blist),
                            parse_mode=MARKDOWN
                        )
                    elif media_type == 2:
                        msg = worker.bot.send_animation(
                            worker.chat.id,
                            animation=media,
                            caption=text,
                            reply_markup=InlineKeyboardMarkup(blist),
                            parse_mode=MARKDOWN
                        )
                else:
                    if media_type == 0:
                        msg = worker.bot.send_photo(
                            worker.chat.id,
                            photo=media,
                            caption=text,
                            parse_mode=MARKDOWN
                        )
                    elif media_type == 1:
                        msg = worker.bot.send_video(
                            worker.chat.id,
                            video=media,
                            caption=text,
                            parse_mode=MARKDOWN
                        )
                    elif media_type == 2:
                        msg = worker.bot.send_animation(
                            worker.chat.id,
                            animation=media,
                            caption=text,
                            parse_mode=MARKDOWN
                        )
        except Exception as e:
            print(e)
            worker.bot.send_message(
                worker.chat.id,
                worker.loc.get("critical")
            )
            return postmenu(worker)
        confirm = {"confirm": worker.loc.get("confirm")}
        confirmbut = utils.buildmenubutton(confirm)
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("confirm_prompt"),
            reply_markup=InlineKeyboardMarkup(confirmbut)
        )
        selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            log.delete()
            msg.delete()
            return postmenu(worker, selection)
        data = {"content": text, "user_id": worker.telegram_user.id, "duration": duration, "groups": groups}
        if has_media:
            data["media"] = media
            data["media_type"] = media_type
        if hasbutt:
            data["button"] = pbutt
        log.delete()
        msg.delete()
        worker.add_post(data)
        selection.edit_message_text(
            worker.loc.get("post_add_ok"),
        )
        return worker.admin_menu()
    elif selection.data == "hist":
        posts = worker.get_user_posts()
        if not posts:
            selection.edit_message_text(
                worker.loc.get("no_posts")
            )
            return worker.admin_menu()
        selection.edit_message_text(
            worker.loc.get("posts_hist_info")
        )
        for post in posts:
            media = post["media"]
            text = post["content"]
            pk = post["pk"]
            butt = utils.buildmenubutton(
                {f"delete_{pk}": worker.loc.get("delete_post")},
                cancellable=False
            )
            if not media:
                worker.bot.send_message(
                    worker.chat.id,
                    text,
                    reply_markup=InlineKeyboardMarkup(butt)
                )
            else:
                media_type = post["media_type"]
                if media_type == 0:
                    worker.bot.send_photo(
                        worker.chat.id,
                        photo=media,
                        caption=text,
                        reply_markup=InlineKeyboardMarkup(butt),
                        parse_mode=MARKDOWN
                    )
                elif media_type == 1:
                    worker.bot.send_video(
                        worker.chat.id,
                        video=media,
                        caption=text,
                        reply_markup=InlineKeyboardMarkup(butt),
                        parse_mode=MARKDOWN
                    )
                elif media_type == 2:
                    worker.bot.send_animation(
                        worker.chat.id,
                        animation=media,
                        caption=text,
                        reply_markup=InlineKeyboardMarkup(butt),
                        parse_mode=MARKDOWN
                    )
        return worker.admin_menu()


def add_admin(worker: "worker2.Worker", selection: telegram.CallbackQuery = None):
    data = {
        "add": worker.loc.get("admin_add"),
        "del": worker.loc.get("admin_del")
    }
    buttons = utils.buildmenubutton(data)
    selection.edit_message_text(
        worker.loc.get("admin_promote_clicked"),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
    if selection.data == "cmd_cancel":
        return worker.admin_menu(selection=selection)
    action = selection.data
    selection.edit_message_text(
        worker.loc.get("admin_id_promt")
    )
    selection = worker.wait_for_regex("(.*)", cancellable=True)
    if isinstance(selection, telegram.Update):
        return worker.admin_menu(selection.callback_query)
    if not selection.isnumeric():
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("admin_id_invalid")
        )
        return worker.admin_menu()
    if action == "add":
        worker.promoteuser(selection)
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("admin_added")
        )
        return worker.admin_menu()
    res = worker.ban(selection)
    if "error" in res:
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("admin_invalid")
        )
    else:
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("admin_deleted")
        )
    return worker.admin_menu()
