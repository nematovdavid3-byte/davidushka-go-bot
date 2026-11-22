
import os
import asyncio
import sqlite3
from datetime import datetime
from html import escape

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "orders.sqlite3")

if not TOKEN or not ADMIN_ID:
    raise RuntimeError("Railway Variables must contain BOT_TOKEN and ADMIN_ID")

bot = Bot(TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class NewOrder(StatesGroup):
    customer = State()
    phone = State()
    pickup = State()
    destination = State()
    goods = State()
    fee = State()


def conn():
    c = sqlite3.connect(DB_PATH)
    c.execute("""
    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_user_id INTEGER,
        shop_name TEXT,
        customer TEXT,
        phone TEXT,
        pickup TEXT,
        destination TEXT,
        goods TEXT,
        fee TEXT,
        status TEXT DEFAULT 'NEW',
        courier_id INTEGER,
        created_at TEXT
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS couriers(
        telegram_id INTEGER PRIMARY KEY,
        name TEXT,
        added_at TEXT
    )
    """)
    c.commit()
    return c


def get_order(oid):
    c = conn()
    row = c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    c.close()
    return row


def is_courier(cid):
    c = conn()
    row = c.execute(
        "SELECT telegram_id FROM couriers WHERE telegram_id=?",
        (cid,)
    ).fetchone()
    c.close()
    return row is not None


def format_order(r):
    return (
        f"<b>DAVIDUSHKA GO | Заказ #{r[0]}</b>\n"
        f"🏪 Магазин: {escape(str(r[2] or '-'))}\n"
        f"👤 Клиент: {escape(str(r[3] or '-'))}\n"
        f"📞 Телефон: {escape(str(r[4] or '-'))}\n"
        f"📍 Забрать: {escape(str(r[5] or '-'))}\n"
        f"🏁 Доставить: {escape(str(r[6] or '-'))}\n"
        f"🛍️ Товар: {escape(str(r[7] or '-'))}\n"
        f"💵 Доставка: {escape(str(r[8] or '-'))}\n"
        f"📌 Статус: {escape(str(r[9] or '-'))}"
    )


@dp.message(Command("start"))
async def start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(
        "🛵 <b>DAVIDUSHKA GO</b>\n"
        "Доставка по Андижону.\n\n"
        "/neworder — оформить заказ\n"
        "/help — помощь\n"
        "/registercourier — регистрация курьера",
        parse_mode="HTML"
    )


@dp.message(Command("help"))
async def help_cmd(m: Message):
    await m.answer(
        "Команды:\n"
        "/neworder — оформить заказ\n"
        "/registercourier — стать курьером\n\n"
        "Курьер:\n"
        "/picked НОМЕР — забрал заказ\n"
        "/done НОМЕР — доставил заказ"
    )


# ---------------- CLIENT ORDER ----------------

@dp.message(Command("neworder"))
async def neworder(m: Message, state: FSMContext):
    await state.clear()
    await state.set_state(NewOrder.customer)
    await m.answer("🧾 Новый заказ\nВведите имя получателя:")


@dp.message(NewOrder.customer)
async def customer(m: Message, state: FSMContext):
    await state.update_data(customer=m.text or "-")
    await state.set_state(NewOrder.phone)
    await m.answer("Телефон получателя:")


@dp.message(NewOrder.phone)
async def phone(m: Message, state: FSMContext):
    await state.update_data(phone=m.text or "-")
    await state.set_state(NewOrder.pickup)
    await m.answer("Адрес магазина (откуда забрать):")


@dp.message(NewOrder.pickup)
async def pickup(m: Message, state: FSMContext):
    await state.update_data(pickup=m.text or "-")
    await state.set_state(NewOrder.destination)
    await m.answer("Адрес доставки:")


@dp.message(NewOrder.destination)
async def destination(m: Message, state: FSMContext):
    await state.update_data(destination=m.text or "-")
    await state.set_state(NewOrder.goods)
    await m.answer("Что доставляем? Краткое описание:")


@dp.message(NewOrder.goods)
async def goods(m: Message, state: FSMContext):
    await state.update_data(goods=m.text or "-")
    await state.set_state(NewOrder.fee)
    await m.answer("Стоимость доставки (например: 15000 сум):")


@dp.message(NewOrder.fee)
async def fee(m: Message, state: FSMContext):
    d = await state.get_data()

    c = conn()
    cur = c.execute(
        """INSERT INTO orders
        (shop_user_id,shop_name,customer,phone,pickup,destination,
         goods,fee,status,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            m.from_user.id,
            m.from_user.full_name,
            d["customer"],
            d["phone"],
            d["pickup"],
            d["destination"],
            d["goods"],
            m.text or "-",
            "NEW",
            datetime.now().isoformat(timespec="minutes")
        )
    )
    oid = cur.lastrowid
    c.commit()
    c.close()

    r = get_order(oid)

    await m.answer(f"✅ Заказ #{oid} принят! Диспетчер получил заявку.")

    await bot.send_message(
        ADMIN_ID,
        format_order(r)
        + f"\n\nНазначить курьера: <code>/assign {oid} TELEGRAM_ID</code>"
        + f"\nОтменить: <code>/cancel {oid}</code>",
        parse_mode="HTML"
    )
    await state.clear()


# ---------------- COURIER REGISTRATION ----------------

@dp.message(Command("registercourier"))
async def register_courier(m: Message):
    cid = m.from_user.id
    name = m.from_user.full_name

    c = conn()
    c.execute(
        "INSERT OR REPLACE INTO couriers (telegram_id,name,added_at) VALUES (?,?,?)",
        (cid, name, datetime.now().isoformat(timespec="minutes"))
    )
    c.commit()
    c.close()

    await m.answer(
        "✅ Вы зарегистрированы как курьер DAVIDUSHKA GO!\n"
        f"Ваш Telegram ID: <code>{cid}</code>\n"
        "Ожидайте назначения заказа.",
        parse_mode="HTML"
    )

    try:
        await bot.send_message(
            ADMIN_ID,
            f"🛵 Новый курьер зарегистрировался!\n"
            f"Имя: {escape(name)}\n"
            f"Telegram ID: <code>{cid}</code>",
            parse_mode="HTML"
        )
    except Exception:
        pass


@dp.message(Command("addcourierid"))
async def add_courier_id(m: Message):
    if m.from_user.id != ADMIN_ID:
        return await m.answer("⛔ Команда доступна только диспетчеру.")

    parts = (m.text or "").split()

    if len(parts) != 2 or not parts[1].isdigit():
        return await m.answer(
            "Формат:\n/addcourierid TELEGRAM_ID\n\n"
            "Курьер должен предварительно открыть бота и нажать Start."
        )

    cid = int(parts[1])

    c = conn()
    c.execute(
        "INSERT OR IGNORE INTO couriers (telegram_id,name,added_at) VALUES (?,?,?)",
        (cid, f"Курьер {cid}", datetime.now().isoformat(timespec="minutes"))
    )
    c.commit()
    c.close()

    await m.answer(f"✅ Курьер {cid} добавлен в базу.")


@dp.message(Command("couriers"))
async def couriers_list(m: Message):
    if m.from_user.id != ADMIN_ID:
        return await m.answer("⛔ Команда доступна только диспетчеру.")

    c = conn()
    rows = c.execute(
        "SELECT telegram_id,name FROM couriers ORDER BY name"
    ).fetchall()
    c.close()

    if not rows:
        return await m.answer(
            "Список курьеров пуст.\n"
            "Курьер может зарегистрироваться командой /registercourier."
        )

    text = "<b>🛵 Курьеры DAVIDUSHKA GO</b>\n\n"
    for cid, name in rows:
        text += f"👤 {escape(str(name))}\n🆔 <code>{cid}</code>\n\n"

    await m.answer(text, parse_mode="HTML")


# ---------------- ASSIGN ORDER ----------------

@dp.message(Command("assign"))
async def assign(m: Message):
    if m.from_user.id != ADMIN_ID:
        return await m.answer("⛔ Эта команда только для диспетчера.")

    p = (m.text or "").split()
    if len(p) != 3:
        return await m.answer(
            "Формат:\n/assign НОМЕР_ЗАКАЗА TELEGRAM_ID_КУРЬЕРА"
        )

    try:
        oid, cid = int(p[1]), int(p[2])
    except ValueError:
        return await m.answer("ID должны быть числовыми.")

    if not is_courier(cid):
        return await m.answer(
            "❌ Курьер не зарегистрирован.\n"
            "Сначала добавьте его командой /addcourierid ID "
            "или попросите его отправить /registercourier."
        )

    c = conn()
    cur = c.execute(
        "UPDATE orders SET status='ASSIGNED',courier_id=? "
        "WHERE id=? AND status='NEW'",
        (cid, oid)
    )
    c.commit()
    c.close()

    r = get_order(oid)
    if not r or not cur.rowcount:
        return await m.answer("Заказ не найден или уже назначен.")

    try:
        await bot.send_message(
            cid,
            format_order(r)
            + f"\n\n📦 Забрали заказ: <code>/picked {oid}</code>"
            + f"\n✅ Доставили: <code>/done {oid}</code>",
            parse_mode="HTML"
        )
    except Exception:
        c = conn()
        c.execute(
            "UPDATE orders SET status='NEW',courier_id=NULL WHERE id=?",
            (oid,)
        )
        c.commit()
        c.close()
        return await m.answer(
            "Не удалось написать курьеру.\n"
            "Курьер должен открыть бота и нажать Start.\n"
            "Заказ возвращён в NEW."
        )

    await m.answer(f"🛵 Курьер назначен на заказ #{oid}.")


# ---------------- PICKED UP ----------------

@dp.message(Command("picked"))
async def picked(m: Message):
    p = (m.text or "").split()
    if len(p) != 2 or not p[1].isdigit():
        return await m.answer("Формат: /picked НОМЕР")

    oid = int(p[1])
    r = get_order(oid)

    if not r or r[10] != m.from_user.id:
        return await m.answer("⛔ Этот заказ не назначен вам.")

    if r[9] != "ASSIGNED":
        return await m.answer("Заказ уже изменил статус.")

    c = conn()
    c.execute(
        "UPDATE orders SET status='PICKED' WHERE id=? AND courier_id=?",
        (oid, m.from_user.id)
    )
    c.commit()
    c.close()

    await m.answer(f"📦 Заказ #{oid} забран.")
    await bot.send_message(ADMIN_ID, f"📦 Курьер забрал заказ #{oid}.")


# ---------------- DELIVERED ----------------

@dp.message(Command("done"))
async def done(m: Message):
    p = (m.text or "").split()
    if len(p) != 2 or not p[1].isdigit():
        return await m.answer("Формат: /done НОМЕР")

    oid = int(p[1])
    r = get_order(oid)

    if not r or r[10] != m.from_user.id:
        return await m.answer("⛔ Этот заказ не назначен вам.")

    if r[9] != "PICKED":
        return await m.answer(
            "Сначала подтвердите получение заказа командой /picked НОМЕР."
        )

    c = conn()
    c.execute(
        "UPDATE orders SET status='DELIVERED' "
        "WHERE id=? AND courier_id=?",
        (oid, m.from_user.id)
    )
    c.commit()
    c.close()

    await m.answer(f"✅ Заказ #{oid} доставлен!")
    await bot.send_message(ADMIN_ID, f"🎉 Заказ #{oid} завершён.")


# ---------------- CANCEL ----------------

@dp.message(Command("cancel"))
async def cancel(m: Message):
    if m.from_user.id != ADMIN_ID:
        return await m.answer("⛔ Команда только для диспетчера.")

    p = (m.text or "").split()
    if len(p) != 2 or not p[1].isdigit():
        return await m.answer("Формат: /cancel НОМЕР")

    oid = int(p[1])
    r = get_order(oid)

    if not r:
        return await m.answer("Заказ не найден.")

    c = conn()
    cur = c.execute(
        "UPDATE orders SET status='CANCELLED' "
        "WHERE id=? AND status IN ('NEW','ASSIGNED')",
        (oid,)
    )
    c.commit()
    c.close()

    if cur.rowcount:
        await m.answer(f"❌ Заказ #{oid} отменён.")
        try:
            await bot.send_message(r[1], f"Заказ #{oid} отменён.")
        except Exception:
            pass
    else:
        await m.answer("Заказ нельзя отменить (возможно, уже завершён).")


# ---------------- START BOT ----------------

async def main():
    conn().close()
    print("DAVIDUSHKA GO bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
