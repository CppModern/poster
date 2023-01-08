import sys
import logging
import queue as queuem
import threading
import traceback
import json
import requests
import nuconfig
import telegram
import _signals
import localisation
import adminmenu as menu

from utils import (
    wait_for_photo, wait_for_regex,
    wait_for_inlinekeyboard_callback,
    receive_next_update, wait_for_specific_message,
    graceful_stop, buildmenubutton
)

log = logging.getLogger(__name__)
CancelSignal = _signals.CancelSignal
StopSignal = _signals.StopSignal
MARKDOWN = telegram.parsemode.ParseMode.MARKDOWN


class Worker(threading.Thread):
    CancelSignal = _signals.CancelSignal
    StopSignal = _signals.StopSignal
    wait_for_specific_message = wait_for_specific_message
    wait_for_inlinekeyboard_callback = wait_for_inlinekeyboard_callback
    receive_next_update = receive_next_update
    wait_for_photo = wait_for_photo
    wait_for_regex = wait_for_regex
    graceful_stop = graceful_stop

    admin_group_menu = menu.group_menu
    admin_post_menu = menu.postmenu
    admin_promote_menu = menu.add_admin

    def __init__(
        self,
        bot,
        chat: telegram.Chat,
        telegram_user: telegram.User,
        cfg: nuconfig.NuConfig,
        *args,
        **kwargs,
    ):
        # Initialize the thread
        super().__init__(name=f"Worker {chat.id}", *args, **kwargs)
        # Store the bot, chat info and config inside the class
        self.bot: telegram.Bot = bot
        self.chat: telegram.Chat = chat
        self.todelete = []
        self.telegram_user: telegram.User = telegram_user
        self.cfg = cfg
        self.special = False
        self.admin = False
        # The sending pipe is stored in the Worker class,
        # allowing the forwarding of messages to the chat process
        self.queue = queuem.Queue()
        # The current active invoice payload; reject all invoices
        # with a different payload
        self.invoice_payload = None
        self.loc: localisation.Localisation = None
        self.__create_localization()
        self.cancel_marked = telegram.InlineKeyboardMarkup(
            [[telegram.InlineKeyboardButton(self.loc.get("menu_cancel"), callback_data="cmd_cancel")]])
        self.cancel_list = [telegram.InlineKeyboardButton(self.loc.get("menu_cancel"), callback_data="cmd_cancel")]
        # The price class of this worker.

    def __repr__(self):
        return f"<{self.__class__.__qualname__} {self.chat.id}>"

    def run(self):
        """The conversation code."""
        self.create_user()
        log.debug("Starting conversation")
        # Capture exceptions that occour during the conversation
        # noinspection PyBroadException
        user = self.get_user(self.telegram_user.id)
        try:
            """# Welcome the user to the bot
            if self.cfg["Appearance"]["display_welcome_message"] == "yes":
                self.bot.send_message(
                    self.chat.id, self.loc.get("welcome")
                )
                self.cfg["Appearance"]["display_welcome_message"] = "no"""
            self.special = user["special"]
            self.admin = user["admin"]
            if self.special or self.admin:
                self.admin_menu()

        except Exception as e:
            # Try to notify the user of the exception
            # noinspection PyBroadException
            try:
                self.bot.send_message(
                    self.chat.id, self.loc.get("fatal_conversation_exception")
                )
            except Exception as ne:
                log.error(
                    f"Failed to notify the user of a conversation exception: {ne}"
                )
            log.error(f"Exception in {self}: {e}")
            traceback.print_exception(*sys.exc_info())

    def is_ready(self):
        # Change this if more parameters are added!
        return self.loc is not None

    def stop(self, reason: str = ""):
        """Gracefully stop the worker process"""
        # Send a stop message to the thread
        self.queue.put(StopSignal(reason))
        # Wait for the thread to stop
        self.join()

    """def update_user(self):
        user_data = json.loads(
            requests.get(self.cfg["API"]["base"].format(f"payment/user/{self.user.id}")).json()["user"]
        )
        self.user = User(user_data[0], user=self.telegram_user)
        return self.user"""

    def __create_localization(self):
        self.loc = localisation.Localisation("en")

    def admin_menu(self, selection: telegram.CallbackQuery = None):
        if self.admin:
            data = {
                "group": self.loc.get("group_button"),
                "post": self.loc.get("post_button"),
                "promote": self.loc.get("admin_button"),
                "lang": self.loc.get("language_button")
            }
        elif self.special:
            data = {
                "group": self.loc.get("group_button"),
                "post": self.loc.get("post_button"),
                "lang": self.loc.get("language_button")
            }
        buttons = buildmenubutton(data, cancellable=False)
        if not selection:
            self.bot.send_message(
                self.chat.id,
                text=self.loc.get("welcome").format(self.telegram_user.first_name),
                reply_markup=telegram.InlineKeyboardMarkup(
                    buttons
                ),
            )
        else:
            selection.edit_message_text(
                self.loc.get("welcome").format(self.telegram_user.first_name),
                reply_markup=telegram.InlineKeyboardMarkup(
                    buttons
                ),
                parse_mode=MARKDOWN
            )
        selection = self.wait_for_inlinekeyboard_callback()
        if selection.data == "post":
            self.admin_post_menu(selection=selection)
        elif selection.data == "group":
            self.admin_group_menu(selection=selection)
        elif selection.data == "promote":
            self.admin_promote_menu(selection=selection)
        elif selection.data == "lang":
            self.switch_context(selection=selection)

    def switch_context(self, selection: telegram.CallbackQuery = None):
        if self.loc.code != "en":
            data = {
                "en": "English 🇱🇷"
            }
        else:
            data = {
                "heb": "Hebrew 🇮🇱"
            }
        button = buildmenubutton(data)

        selection.edit_message_text(
            self.loc.get("langPrompt"),
            reply_markup=telegram.InlineKeyboardMarkup(button)
        )
        selection = self.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            return self.admin_menu(selection)
        self.loc = localisation.Localisation(selection.data)
        return self.admin_menu(selection)

    def get_orders(self):
        url = self.cfg["API"]["base"].format(f"payment/orders/{self.telegram_user.id}/")
        orders = requests.get(url).json()["orders"]
        return orders

    def list_products(self):
        url = self.cfg["API"]["base"].format("payment/products/")
        prods = requests.get(url).json()["products"]
        return prods

    def get_users(self):
        url = self.cfg["API"]["base"].format("payment/users/")
        users = requests.get(url).json()["users"]
        return users

    def addorder(self, details):
        url = self.cfg["API"]["base"].format("payment/addorder/")
        requests.post(url, details)

    def getorders(self, user_id):
        url = self.cfg["API"]["base"].format(f"payment/orders/{user_id}")
        res = requests.get(url).json()
        return res["orders"]

    def user_dump(self):
        url = self.cfg["API"]["base"].format("payment/usersdump/")
        res = requests.get(url).json()["users"]
        return res

    def create_or_update_product(self, data, update=False):
        if update:
            url = self.cfg["API"]["base"].format("payment/updateproduct/")
        else:
            url = self.cfg["API"]["base"].format("payment/createproduct/")
        res = requests.post(url, data=data).json()
        return res

    def delete_product(self, product):
        url = self.cfg["API"]["base"].format("payment/deleteproduct/")
        res = requests.post(url, data={"product_id": product})
        return res.json()

    def get_banned_users(self):
        url = self.cfg["API"]["base"].format("payment/users/banned/")
        users = json.loads(requests.get(url).json()["users"])
        data = []
        for user in users:
            data.append(user["fields"])
        return data

    def create_user(self):
        url = self.cfg["API"]["base"].format("payment/createuser/")
        data = {
            "user_id": self.telegram_user.id,
            "fname": self.telegram_user.first_name,
            "username": self.telegram_user.username or ""
        }
        requests.post(url, data=data)

    def ban(self, user):
        user = str(user)
        data = {"user_id": user, "loc": self.telegram_user.language_code}
        url = self.cfg["API"]["base"].format(f"payment/ban/")
        res = requests.post(url, data=data).json()
        return res

    def unban(self, user):
        user = str(user)
        data = {"user_id": user, "loc": self.telegram_user.language_code}
        url = self.cfg["API"]["base"].format(f"payment/unban/")
        res = requests.post(url, data=data).json()
        return res

    def update_balace(self, user, amout, charge=False):
        user = str(user)
        if charge:
            data = {"user_id": user, "amount": amout, "charge": True}
        else:
            data = {"user_id": user, "amount": amout}
        url = self.cfg["API"]["base"].format(f"payment/balance/")
        res = requests.post(url, data=data).json()
        return res

    def get_user(self, user_id):
        url = self.cfg["API"]["base"].format(f"payment/user/{user_id}/")
        user = requests.get(url).json()["user"]
        return user

    def create_order(self, user, product_id, qty, coupon=None):
        data = {"user": user, "product_id": product_id, "qty": qty, "coupon": coupon}
        url = self.cfg["API"]["base"].format(f"payment/createorder/")
        res = requests.post(url, data=data).json()
        return res

    def pending_user_orders(self, user):
        url = self.cfg["API"]["base"].format(f"payment/pendingorders/{user}")
        res = requests.get(url)
        return res.json()["orders"]

    def settled_user_orders(self, user):
        url = self.cfg["API"]["base"].format(f"payment/settledorders/{user}")
        res = requests.get(url)
        return res.json()["orders"]

    def create_payment(self, user, amount):
        data = {"user_id": user, "amount": amount}
        url = self.cfg["API"]["base"].format(f"payment/create/")
        res = requests.post(url, data=data).json()
        return res

    def get_user_groups(self):
        url = self.cfg["API"]["base"].format(f"payment/groups/{self.telegram_user.id}")
        res = requests.get(url).json()
        return res["groups"]

    def get_groups(self):
        url = self.cfg["API"]["base"].format(f"payment/groups/")
        res = requests.get(url).json()
        return res["groups"]

    def add_group(self, data):
        url = self.cfg["API"]["base"].format(f"payment/addgroup/")
        res = requests.post(url, data=data).json()
        return res

    def delete_group(self, group_id):
        url = self.cfg["API"]["base"].format(f"payment/deletegroup/")
        data = {"group_id": group_id}
        res = requests.post(url, data=data)
        return res.json()

    def permit_group(self, group_id, user_id):
        data = {"group_id": group_id, "user_id": user_id}
        url = self.cfg["API"]["base"].format(f"payment/permit/")
        res = requests.post(url, data=data).json()
        return res

    def add_post(self, data):
        url = self.cfg["API"]["base"].format(f"payment/post/")
        res = requests.post(url, data=data).json()
        return res

    def get_user_posts(self):
        url = self.cfg["API"]["base"].format(f"payment/userposts/{self.telegram_user.id}")
        res = requests.get(url).json()
        return res["posts"]

    def delete_post(self, pk):
        url = self.cfg["API"]["base"].format("payment/deletepost/")
        data = {"post_id": pk}
        res = requests.post(url, data=data)
        return res

    def promoteuser(self, user_id):
        url = self.cfg["API"]["base"].format("payment/promote/")
        data = {"user_id": user_id}
        res = requests.post(url, data=data)
        return res

    def track_payment(self, order_id):
        url = self.cfg["API"]["base"].format(f"payment/invoice/{order_id}")
        res = requests.get(url).json()
        return res["data"]

    def transaction_times(self, day="today"):
        url = self.cfg["API"]["base"].format(f"payment/transaction{day}/")
        res = requests.get(url).json()
        return res["transactions"]
