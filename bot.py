import datetime
import json
import os
import time
import uuid

import requests
from aiogram import Bot, Dispatcher, executor
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, \
    InlineKeyboardButton, CallbackQuery
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from settings import base_link, debug
import pandas as pd

bot = Bot(os.environ.get("TG_TOKEN"))
dp = Dispatcher(bot)
scheduler = AsyncIOScheduler()

page_size = 5

hoover_state = {
    "status": "free",
    "floor": 2,
    "location": "в ванной коворкинга",
    "chat_id": "",
    "rent_time": ""
}

complains_pages = {}
users_pages = {}

response = {
    "floor": 0,
    "location": ""
}

priv = ["user", "duty", "admin", "owner"]

stop_rent_user = ""

default_markup = ReplyKeyboardMarkup(resize_keyboard=True)
default_markup.add("Где пылесос?")
default_markup.add("Список команд")


def get_user(chat_id) -> bool | dict:
    link = base_link + f"/api/user/{chat_id}?api_key={os.environ.get('LOCAL_API_TOKEN')}"
    resp = requests.get(link).json()
    if resp["status"] > 0:
        return resp["user"]
    else:
        return False


def get_possibilities(role):
    return priv[:priv.index(role) + 1]


def is_admin(chat_id) -> bool:
    user = get_user(chat_id)
    if user:
        role = user["role"]
        if "admin" in get_possibilities(role):
            return True
    return False


def get_all_users():
    link = base_link + f"/api/get_users?api_key={os.environ.get('LOCAL_API_TOKEN')}"
    resp = requests.get(link).json()
    return resp


def get_requests():
    with open("items.json") as file:
        content = json.loads(file.read())
    return content


def get_complains():
    with open("complains.json") as file:
        content = json.loads(file.read())
    return content


def get_users_list():
    users = get_all_users()
    users_list = []
    for room, users_in_room in users.items():
        for user in users_in_room:
            user.append(room)
            users_list.append(user)

    return users_list


async def add_complain(chat_id, name, complain_text):
    with open("cooldown.json") as file:
        cooldowns = json.loads(file.read())
    chat_id = str(chat_id)
    if cooldowns.get(chat_id) and round(time.time()) - cooldowns[chat_id] < 600:
        return await bot.send_message(chat_id,
                                      f"Вы уже отправляли жалобу недавно. "
                                      f"Подождите ещё {10 - (round(time.time()) - cooldowns[chat_id]) // 60} минут")
    data = get_complains()
    data[uuid.uuid4().hex] = {"from_user": chat_id,
                              "name": name,
                              "text": complain_text,
                              "time": datetime.datetime.now().strftime('%d-%m-%Y-%H-%M-%S')
                              }
    with open("complains.json", "w") as file:
        file.write(json.dumps(data))

    cooldowns[chat_id] = round(time.time())

    with open("cooldown.json", "w") as file:
        file.write(json.dumps(cooldowns))
    return await bot.send_message(chat_id, "Жалоба отправлена.")


def create_request(chat_id, item):
    _requests = get_requests()
    _requests[item] = chat_id
    with open("items.json", "w") as file:
        file.write(json.dumps(_requests))


def delete_request(item):
    _requests = get_requests()
    del _requests[item]
    with open("items.json", "w") as file:
        file.write(json.dumps(_requests))


async def notify(bot: Bot):
    file = pd.ExcelFile("data/data.xlsx")
    df: pd.DataFrame = file.parse(file.sheet_names[0])
    tim: dict = df.to_dict()
    for room, date in tim.items():
        date: dict
        date: pd.Timestamp = date[0]
        if date.strftime('%d-%m-%Y') == datetime.datetime.now().strftime(
                '%d-%m-%Y') and datetime.datetime.now().hour.real == 12 and datetime.datetime.now().minute.real == 30:
            link = base_link + f"/api/room/{room}?api_key={os.environ.get('LOCAL_API_TOKEN')}"
            resp = requests.get(link).json()

            if resp["status"] > 0:
                for resident in resp["room"]["residents"]:
                    await bot.send_message(resident["chat_id"], "Поздравляю! Сегодня день вашего дежурства!")
    file.close()


def config_message(callback_query):
    message = callback_query.message

    complains = get_complains()
    complains = list(complains.values())
    if not (message.chat.id in list(complains_pages)):
        complains_pages[message.chat.id] = 0

    complain_user = get_user(complains[complains_pages[message.chat.id]]["from_user"])

    if complain_user:
        mes = f"Жалоба №{complains_pages[message.chat.id] + 1} от {complain_user.get('name') or 'Неизвестно'} из комнаты {complain_user.get('room') or 'Неизвестно'}.\n" \
              f"Объект жалобы: {complains[complains_pages[message.chat.id]]['name']}.\n\n" \
              f"{complains[complains_pages[message.chat.id]]['text']}."
    else:
        mes = f"Жалоба №{complains_pages[message.chat.id] + 1}" \
              f"Объект жалобы: {complains[complains_pages[message.chat.id]]['name']}.\n\n" \
              f"{complains[complains_pages[message.chat.id]]['text']}."
    return mes


@dp.message_handler(commands=["start"])
async def start(message: Message):
    await message.answer("Привет! чтобы начать пользоваться ботом тебе надо зарегистрироваться.\n"
                         "Пропиши:\n\n"
                         "``` /register {имя} {номер-комнаты} ```"
                         "\n\nвместо '{имя}' впиши своё имя, "
                         "а вместо '{номер-комнаты}' впиши номер комнаты (формат: x-x-xxx).",
                         parse_mode="Markdown")


@dp.message_handler(commands=["register"])
async def register(message: Message):
    args = message.get_args()
    if args and len(args) >= 2:
        args = args.split()
        name = args[0].strip("{").strip("}").strip()
        room = args[1].strip("{").strip("}").strip()
        chat_id = message.chat.id
        api_key = os.environ.get("LOCAL_API_TOKEN")
        link = base_link + f"/api/set_user?name={name}&room={room}&chat_id={chat_id}&api_key={api_key}"
        resp = requests.get(link).json()
        if resp.get("status") > 0:
            await message.answer("Успешно. Теперь вы можете пользоваться ботом.\n"
                                 "Пропишите:\n"
                                 "``` /help```\n"
                                 "для просмотра списка всех команд бота", parse_mode="Markdown",
                                 reply_markup=default_markup)
        elif resp.get("status") == -2:
            await message.answer("Вы уже зарегистрированы.", reply_markup=default_markup)
        else:
            await message.answer(
                "Что-то пошло не так. Перепроверьте данные, попробуйте ещё раз, и если не получится, "
                "перешлите это сообщение \nв чат @alex_alex_good:\n\n"
                f"status_code: {resp.get('status')};\n"
                f"name: {name};\n"
                f"room: {room};\n"
                f"chat_id: {chat_id}")
    else:
        await message.answer("Вы прописали не все аргументы. Используйте: "
                             "``` /register {имя} {номер-комнаты}```", parse_mode="Markdown")


@dp.message_handler(commands=["clear"])
async def clear(message: Message):
    args = message.get_args()
    if debug and args:
        link = base_link + f"/clear/{args}?api_key={os.environ.get('LOCAL_API_TOKEN')}"
        resp = requests.get(link).json()
        if resp["status"] > 0:
            await message.answer("База данных успешно очищена.")
            return
        await message.answer("Неверный пароль")


@dp.message_handler(lambda message: message.text.lower() == "список команд")
@dp.message_handler(commands=["help"])
async def help_answer(message: Message):
    user = get_user(message.chat.id)
    if user:
        possibilities = get_possibilities(user["role"])
        if "user" in possibilities:
            await message.answer("возможности уровня 'пользователь':\n"
                                 "/my_duty - дата моего дежурства\n"
                                 "/locate_hoover - найти пылесос\n"
                                 "/rent - взять пылесос в пользование\n"
                                 "/ask_for {название нужной вещи} - отправить всем пользователям сообщение "
                                 "с просьбой о конкретной вещи\n"
                                 "/have {название вещи} - ответить на просьбу о нужной вещи\n"
                                 "/complain {имя} - {претензия} - отправляет админам жалобу на человека,"
                                 "имя которого вы вписали (обязательно разделять имя и претензию тире)\n"
                                 "/me - информация о вашем аккаунте", reply_markup=default_markup)
        if "duty" in possibilities:
            await message.answer("возможности уровня 'дежурный':\n"
                                 "/set_hoover - изменить положение пылесоса, если кто-то забыл закончить аренду\n"
                                 "/task_list - список задач дежурного\n",
                                 reply_markup=default_markup)
        if "admin" in possibilities:
            await message.answer("возможности уровня 'администратор':\n"
                                 "/ban {chat_id} - удалить пользователя\n"
                                 "/register_user {name} {room} - зарегистрировать пользователя\n"
                                 "/get_users - вывести всех пользователей\n"
                                 "/get_duty - вывести комнату, которая дежурит\n"
                                 "/set_role {chat_id} {role} - установить роль пользователю\n"
                                 "/view_complains - просмотреть все жалобы\n\n"
                                 "Отправьте xlsx файл, чтобы заменить график дежурств",
                                 reply_markup=default_markup)
    else:
        await message.answer("Сначала надо зарегистрироваться. \n"
                             "``` /register {имя} {номер-комнаты}```\n"
                             "номер комнаты указывать в формате х-х-ххх", parse_mode="Markdown")


@dp.message_handler(commands=["my_duty"])
async def my_duty(message: Message):
    user = get_user(message.chat.id)
    if not user:
        return await message.answer("Сначала надо зарегистрироваться. \n"
                                    "``` /register {имя} {номер-комнаты}```\n"
                                    "номер комнаты указывать в формате х-х-ххх", parse_mode="Markdown")

    file = pd.ExcelFile("data/data.xlsx")
    df: pd.DataFrame = file.parse(file.sheet_names[0])
    tim: dict = df.to_dict().get(user["room"])
    tim: pd.Timestamp = tim[0] if tim else False
    if tim:
        return await message.answer(f"Дата вашего дежурства: {tim.strftime('%d-%m-%Y')}", reply_markup=default_markup)
    file.close()
    await message.answer("Вас нет в графике дежурств.", reply_markup=default_markup)


@dp.message_handler(lambda message: message.text.lower() == "где пылесос?")
@dp.message_handler(commands=["locate_hoover"])
async def locate_hover(message: Message):
    user = get_user(message.chat.id)
    if not user:
        return await message.answer("Сначала надо зарегистрироваться. \n"
                                    "``` /register {имя} {номер-комнаты}```\n"
                                    "номер комнаты указывать в формате х-х-ххх", parse_mode="Markdown")

    if hoover_state["status"] == "free":
        return await message.answer(f"Пылесос свободен, сейчас он на {hoover_state['floor']} этаже.\n"
                                    f"Локация: {hoover_state['location']}", reply_markup=default_markup)

    if hoover_state["status"] == "rented":
        return await message.answer(f"Пылесос занят, он сейчас в {hoover_state['location']} комнате.",
                                    reply_markup=default_markup)


@dp.message_handler(commands=["rent"])
async def rent(message: Message):
    user = get_user(message.chat.id)

    if not user:
        return await message.answer("Сначала надо зарегистрироваться. \n"
                                    "``` /register {имя} {номер-комнаты}```\n"
                                    "номер комнаты указывать в формате х-х-ххх", parse_mode="Markdown")

    if hoover_state["status"] != "free":
        return await message.answer(f"Пылесос ещё занят. Он в {hoover_state['location']} комнате.")
    hoover_state["chat_id"] = message.chat.id
    hoover_state["location"] = user["room"]
    hoover_state["rent_time"] = datetime.datetime.now().strftime("%H:%M")
    hoover_state["floor"] = user["room"].split("-")[2][0]
    hoover_state["status"] = "rented"
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    button = KeyboardButton(text="Остановить аренду")
    keyboard.add(button)
    await message.answer("Пылесос арендован", reply_markup=keyboard)


@dp.message_handler(lambda message: message.text.lower() == "остановить аренду")
@dp.message_handler(commands=["stop"])
async def stop_rent(message: Message, duty=False):
    global stop_rent_user
    user = get_user(message.chat.id)
    if not user:
        return await message.answer("Сначала надо зарегистрироваться. \n"
                                    "``` /register {имя} {номер-комнаты}```\n"
                                    "номер комнаты указывать в формате х-х-ххх", parse_mode="Markdown")
    if user["room"] and (user["room"] == hoover_state["location"] or duty):
        stop_rent_user = message.chat.id
        markup = ReplyKeyboardMarkup(resize_keyboard=True)
        buttons = [
            KeyboardButton("1"),
            KeyboardButton("2"),
            KeyboardButton("3"),
            KeyboardButton("4"),
            KeyboardButton("5"),
        ]

        markup.row(*buttons)

        return await message.answer("На каком этаже вы оставили пылесос (отправьте число):",
                                    reply_markup=markup)

    else:
        return await message.answer("Вы не брали пылесос.")


@dp.message_handler(commands=["ask_for"])
async def ask_for(message: Message):
    users = get_all_users()
    user = get_user(message.chat.id)
    if not user:
        return await message.answer("Сначала надо зарегистрироваться. \n"
                                    "``` /register {имя} {номер-комнаты}```\n"
                                    "номер комнаты указывать в формате х-х-ххх", parse_mode="Markdown")
    argument = message.get_args()
    if len(argument) < 2:
        return await message.answer("Запрос должен содержать минимум 3 символа.")
    create_request(message.chat.id, argument)
    for room, persons in users.items():
        for person in persons:
            await bot.send_message(person[2],
                                   f"Пользователь {user['name']} из комнаты {user['room']} попросил '{argument}'\n\n"
                                   f"Если вы хотите поделиться, напишите:\n\n/have {argument}")


@dp.message_handler(commands=["have"])
async def have(message: Message):
    user = get_user(message.chat.id)
    if not user:
        return await message.answer("Сначала надо зарегистрироваться. \n"
                                    "``` /register {имя} {номер-комнаты}```\n")
    reqs = get_requests()
    argument = message.get_args()

    if reqs.get(argument):
        delete_request(argument)
        await bot.send_message(reqs.get(argument),
                               f"У пользователя {user['name']} есть {argument}.\n "
                               f"Номер комнаты пользователя: {user['room']}")
        return await message.answer("Ответ направлен.", reply_markup=default_markup)

    return await message.answer("Пользователю уже ответили", reply_markup=default_markup)


@dp.message_handler(commands=["me"])
async def me(message: Message):
    user = get_user(message.chat.id)
    if not user:
        return await message.answer("Сначала надо зарегистрироваться. \n"
                                    "``` /register {имя} {номер-комнаты}```\n")
    return await message.answer(
        f"Имя: {user['name']}\n"
        f"Комната: {user['room']}\n"
        f"ID чата: {message.chat.id}\n"
        f"Привилегия: {user['role']}",
        reply_markup=default_markup)


@dp.message_handler(commands=["complain"])
async def complain(message: Message):
    user = get_user(message.chat.id)
    if not user:
        return await message.answer("Сначала надо зарегистрироваться. \n"
                                    "``` /register {имя} {номер-комнаты}```\n")

    args = message.get_args()
    if args:
        args = args.split("-")
        return await add_complain(message.chat.id, args[0], args[1])
    return await message.answer("Ошибка, жалоба не отправлена. Введите все нужные аргументы через '-'")


@dp.message_handler(commands=["view_complains"])
async def view_complains(message: Message):
    user = get_user(message.chat.id)
    if not user:
        return await message.answer("Сначала надо зарегистрироваться. \n"
                                    "``` /register {имя} {номер-комнаты}```\n")

    if not is_admin(message.chat.id):
        return

    complains = get_complains()
    complains = list(complains.values())
    if len(complains) == 0:
        return await message.answer("Жалоб нет.")
    if not (message.chat.id in list(complains_pages)):
        complains_pages[message.chat.id] = 0

    complain_user = get_user(complains[complains_pages[message.chat.id]]["from_user"])

    if complain_user:
        mes = f"Жалоба №{complains_pages[message.chat.id] + 1} от {complain_user.get('name') or 'Неизвестно'} из комнаты {complain_user.get('room') or 'Неизвестно'}.\n" \
              f"Объект жалобы: {complains[complains_pages[message.chat.id]]['name']}.\n\n" \
              f"{complains[complains_pages[message.chat.id]]['text']}."
    else:
        mes = f"Жалоба №{complains_pages[message.chat.id] + 1}" \
              f"Объект жалобы: {complains[complains_pages[message.chat.id]]['name']}.\n\n" \
              f"{complains[complains_pages[message.chat.id]]['text']}."

    keyboard_markup = InlineKeyboardMarkup(row_width=2)
    keyboard_markup.add(InlineKeyboardButton("назад", callback_data="prev_comp_page"),
                        InlineKeyboardButton("вперёд", callback_data="next_comp_page")
                        )

    if is_admin(message.chat.id):
        return await message.answer(mes, reply_markup=keyboard_markup)


@dp.message_handler(commands=["set_hoover"])
async def set_hoover(message: Message):
    global stop_rent_user
    user = get_user(message.chat.id)
    if not user:
        return await message.answer("Сначала надо зарегистрироваться. \n"
                                    "``` /register {имя} {номер-комнаты}```\n")

    pos = get_possibilities(user["role"])
    if "duty" in pos:
        await stop_rent(message, True)


@dp.message_handler(commands=["set_role"])
async def set_role(message: Message):
    user = get_user(message.chat.id)
    if not user:
        return await message.answer("Сначала надо зарегистрироваться. \n"
                                    "``` /register {имя} {номер-комнаты}```\n")

    arguments = message.get_args()
    if arguments:
        arguments = arguments.split()
    if is_admin(message.chat.id) and len(arguments) > 1:
        link = base_link + f"/api/user/set_role?chat_id={arguments[0]}&role={arguments[1]}&api_key={os.environ.get('LOCAL_API_TOKEN')}"
        resp = requests.get(link).json()
        if resp["status"] > 0:
            return await message.answer(f"Выданы права {arguments[1]}.")
        return await message.answer(f"Права {arguments[1]} не выданы. Ошибка: {resp['desc']}")


@dp.message_handler(commands=["get_users"])
async def get_users(message: Message):
    user = get_user(message.chat.id)
    if not user:
        return await message.answer("Сначала надо зарегистрироваться. \n"
                                    "``` /register {имя} {номер-комнаты}```\n")
    pos = get_possibilities(user["role"])
    if "admin" in pos:
        users = get_users_list()

        markup = InlineKeyboardMarkup()

        markup.add(
            InlineKeyboardButton("назад", callback_data="users_prev_page"),
            InlineKeyboardButton("вперёд", callback_data="users_next_page")
        )

        users_pages[message.chat.id] = 0

        page = users_pages[message.chat.id]
        mes = ""
        for i in range(page_size * page, page_size * page + page_size):
            if i < len(users):
                mes += f"{i + 1}. Имя: {users[i][1]},\nChat_id: {users[i][2]},\nКомната: {users[i][4]},\nСтатус: {users[i][3]}\n\n"
            else:
                break

        return await message.answer(mes, reply_markup=markup)


@dp.message_handler()
async def on_message(message: Message):
    global hoover_state, response, stop_rent_user
    if message.chat.id == stop_rent_user:
        if response["floor"] == 0:
            if len(message.text) > 1 or not (message.text in "12345"):
                return await message.answer("Отправьте этаж одной цифрой.")
            else:
                response["floor"] = int(message.text)
                return await message.answer("Где вы оставили пылесос? (отправьте фразой, например: 'у куллера')",
                                            reply_markup=ReplyKeyboardRemove())

        elif not response["location"]:
            response["location"] = message.text
            markup = ReplyKeyboardMarkup(resize_keyboard=True)
            buttons = [
                KeyboardButton("Да"),
                KeyboardButton("Нет")
            ]
            for button in buttons:
                markup.add(button)

            return await message.answer(f"оставить локацию '{response['location']}'?", reply_markup=markup)

        elif response["location"] and message.text.lower() == "да":
            hoover_state["floor"] = response["floor"]
            hoover_state["location"] = response["location"]
            hoover_state["rent_time"] = ""
            hoover_state["status"] = "free"
            hoover_state["chat_id"] = ""
            response["floor"] = 0
            response["location"] = ""
            stop_rent_user = ""
            return await message.answer("Положение пылесоса установлено.", reply_markup=default_markup)

        elif message.text.lower() == "нет":
            response["location"] = ""
            return await message.answer("Где вы оставили пылесос? (отправьте фразой, например: 'у куллера')",
                                        reply_markup=ReplyKeyboardRemove())


@dp.callback_query_handler(lambda callback: callback.data == "next_comp_page")
async def next_comp_page(callback_query: CallbackQuery):
    if not (callback_query.message.chat.id in complains_pages):
        complains_pages[callback_query.message.chat.id] = 0

    if complains_pages[callback_query.message.chat.id] < len(list(get_complains())) - 1:
        complains_pages[callback_query.message.chat.id] += 1
    else:
        complains_pages[callback_query.message.chat.id] = 0

    keyboard_markup = InlineKeyboardMarkup(row_width=2)
    keyboard_markup.add(InlineKeyboardButton("назад", callback_data="prev_comp_page"),
                        InlineKeyboardButton("вперёд", callback_data="next_comp_page")
                        )
    mes = config_message(callback_query)
    try:
        await callback_query.message.edit_text(mes, reply_markup=keyboard_markup)
    except:
        pass
    await callback_query.answer()


@dp.callback_query_handler(lambda callback: callback.data == "prev_comp_page")
async def next_comp_page(callback_query: CallbackQuery):
    if not (callback_query.message.chat.id in complains_pages):
        complains_pages[callback_query.message.chat.id] = 0

    if complains_pages[callback_query.message.chat.id] > 0:
        complains_pages[callback_query.message.chat.id] -= 1
    else:
        complains_pages[callback_query.message.chat.id] = len(list(get_complains())) - 1

    keyboard_markup = InlineKeyboardMarkup(row_width=2)
    keyboard_markup.add(InlineKeyboardButton("назад", callback_data="prev_comp_page"),
                        InlineKeyboardButton("вперёд", callback_data="next_comp_page")
                        )

    mes = config_message(callback_query)
    try:
        await callback_query.message.edit_text(mes, reply_markup=keyboard_markup)
    except:
        pass
    await callback_query.answer()


@dp.callback_query_handler(lambda callback: callback.data == "users_prev_page")
async def prev_users_page(callback_query: CallbackQuery):
    users = get_users_list()
    page_count = len(users) // page_size + 1 * ((len(users) % page_size) != 0) - 1
    if not (callback_query.message.chat.id in users_pages):
        users_pages[callback_query.message.chat.id] = 0

    if users_pages[callback_query.message.chat.id] > 0:
        users_pages[callback_query.message.chat.id] -= 1
    else:
        users_pages[callback_query.message.chat.id] = page_count

    keyboard_markup = InlineKeyboardMarkup(row_width=2)
    keyboard_markup.add(InlineKeyboardButton("назад", callback_data="users_prev_page"),
                        InlineKeyboardButton("вперёд", callback_data="users_next_page")
                        )

    page = users_pages[callback_query.message.chat.id]
    mes = ""
    for i in range(page_size * page, page_size * page + page_size):
        if i < len(users):
            mes += f"{i + 1}. Имя: {users[i][1]},\nChat_id: {users[i][2]},\nКомната: {users[i][4]},\nСтатус: {users[i][3]}\n\n"
        else:
            break
    try:
        await callback_query.message.edit_text(mes, reply_markup=keyboard_markup)
    except:
        pass
    await callback_query.answer()


@dp.callback_query_handler(lambda callback: callback.data == "users_next_page")
async def next_users_page(callback_query: CallbackQuery):
    users = get_users_list()
    page_count = len(users) // page_size + 1 * ((len(users) % page_size) != 0) - 1
    if not (callback_query.message.chat.id in users_pages):
        users_pages[callback_query.message.chat.id] = 0

    if users_pages[callback_query.message.chat.id] < page_count:
        users_pages[callback_query.message.chat.id] += 1
    else:
        users_pages[callback_query.message.chat.id] = 0

    keyboard_markup = InlineKeyboardMarkup(row_width=2)
    keyboard_markup.add(InlineKeyboardButton("назад", callback_data="users_prev_page"),
                        InlineKeyboardButton("вперёд", callback_data="users_next_page")
                        )

    page = users_pages[callback_query.message.chat.id]
    mes = ""
    for i in range(page_size * page, page_size * page + page_size):
        if i < len(users):
            mes += f"{i + 1}. Имя: {users[i][1]},\nChat_id: {users[i][2]},\nКомната: {users[i][4]},\nСтатус: {users[i][3]}\n\n"
        else:
            break
    try:
        await callback_query.message.edit_text(mes, reply_markup=keyboard_markup)
    except:
        pass
    await callback_query.answer()


if __name__ == "__main__":
    scheduler.add_job(notify, "interval", seconds=60, args=(bot,))
    scheduler.start()
    executor.start_polling(dp, skip_updates=True)
