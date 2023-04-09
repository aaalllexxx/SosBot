import datetime
import json
import os

import requests
from aiogram import Bot, Dispatcher, executor
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from settings import base_link, debug
import pandas as pd

bot = Bot(os.environ.get("TG_TOKEN"))
dp = Dispatcher(bot)
scheduler = AsyncIOScheduler()

hoover_state = {
    "status": "free",
    "floor": 2,
    "location": "в ванной коворкинга",
    "chat_id": "",
    "rent_time": ""
}

response = {
    "floor": 0,
    "location": ""
}

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


def get_all_users():
    link = base_link + f"/api/get_users?api_key={os.environ.get('LOCAL_API_TOKEN')}"
    resp = requests.get(link).json()
    return resp


def get_requests():
    with open("items.json") as file:
        content = json.loads(file.read())
    return content


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
        name = args[0].strip("{").strip("}")
        room = args[1].strip("{").strip("}")
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
    print(args)
    print(debug)
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
    if get_user(message.chat.id):
        await message.answer("Я умею:\n"
                             "/my_duty - дата моего дежурства\n"
                             "/locate_hoover - найти пылесос\n"
                             "/rent - взять пылесос в пользование\n"
                             "/ask_for {название нужной вещи} - отправить всем пользователям сообщение "
                             "с просьбой о конкретной вещи\n"
                             "/have {название вещи} - ответить на просьбу о нужной вещи\n"
                             "/complain {имя} - {претензия} - отправляет админам жалобу на человека,\n"
                             "имя которого вы вписали (обязательно разделять имя и претензию тире)"
                             "/me - информация о вашем аккаунте", reply_markup=default_markup)
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
async def stop_rent(message: Message):
    global stop_rent_user
    user = get_user(message.chat.id)
    if not user:
        return await message.answer("Сначала надо зарегистрироваться. \n"
                                    "``` /register {имя} {номер-комнаты}```\n"
                                    "номер комнаты указывать в формате х-х-ххх", parse_mode="Markdown")
    if user["room"] and user["room"] == hoover_state["location"]:
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
    return await message.answer(f"Имя: {user['name']}\nКомната: {user['room']}\nID чата: {message.chat.id}",
                                reply_markup=default_markup)


@dp.message_handler(commands=["complain"])
async def complain(message: Message):
    args = message.get_args()


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
            return await message.answer("Пылесос снят с аренды.", reply_markup=default_markup)

        elif message.text.lower() == "нет":
            response["location"] = ""
            return await message.answer("Где вы оставили пылесос? (отправьте фразой, например: 'у куллера')",
                                        reply_markup=ReplyKeyboardRemove())


if __name__ == "__main__":
    scheduler.add_job(notify, "interval", seconds=60, args=(bot,))
    scheduler.start()
    executor.start_polling(dp, skip_updates=True)
