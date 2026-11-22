import os
import asyncio
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
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
    c.execute("""CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_user_id INTEGER, shop_name TEXT,
        customer TEXT, phone TEXT, pickup TEXT, destination TEXT, goods TEXT, fee TEXT,
        status TEXT DEFAULT 'NEW', courier_id INTEGER, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS couriers(
        telegram_id INTEGER PRIMARY KEY, name TEXT, added_at TEXT)""")
    c.commit()
    return c


def get_order(oid):
    c = conn()
    row = c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    c.close()
    return row


def get_couriers():
    c = conn()
    rows = c.execute("SELECT telegram_id,name FROM couriers ORDER BY name").fetchall()
    c.close()
    return rows


def order_text(r):
    return (
        f"<b>DAVIDUSHKA GO | Заказ #{r[0]}</b>\n"
        f"🏪 Магазин: {r[2]}\n👤 Клиент: {r[3]}\n📞 Телефон: {r[4]}\n"
        f"📍 Забрать: {r[5]}\n🏁 Доставить: {r[6]}\n🛍️ Товар: {r[7]}\n"
        f"💵 Доставка: {r[8]}\n📌 Статус: <b>{r[9]}</b>"
    )


def admin_order_keyboard(oid):
    couriers = get_couriers()
    buttons = [
        [InlineKeyboardButton(text=f"🛵 {name} — назначить", callback_data=f"assign:{oid}:{cid}")]
        for cid, name in couriers
    ]
    buttons.append([InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel:{oid}")])
    if not couriers:
        buttons.insert(0, [InlineKeyboardButton(text="Сначала добавьте курьера: /addcourier ID Имя", callback_data="noop")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def courier_keyboard(oid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Забрал заказ", callback_data=f"picked:{oid}")],
        [InlineKeyboardButton(text="✅ Доставлено", callback_data=f"done:{oid}")],
    ])


@dp.message(Command("start"))
async def start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(
        "🛵 <b>DAVIDUSHKA GO</b>\nДоставка по Андижону.\n\n"
        "/neworder — оформить заказ\n/help — помощь",
        parse_mode="HTML"
    )


@dp.message(Command("help"))
async def help_cmd(m: Message):
    await m.answer(
        "Команды:\n/neworder — оформить доставку\n"
        "/addcourier ID Имя — добавить курьера (диспетчер)\n"
        "/couriers — список курьеров (диспетчер)\n"
        "/cancel НОМЕР — отменить заказ (диспетчер)"
    )


@dp.message(Command("addcourier"))
async def add_courier(m: Message):
    if m.from_user.id != ADMIN_ID:
        return await m.answer("⛔ Команда доступна только диспетчеру.")
    parts = (m.text or "").split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        return await m.answer("Формат: /addcourier TELEGRAM_ID Имя")
    cid, name = int(parts[1]), parts[2].strip()
    c = conn()
    c.execute("INSERT OR REPLACE INTO couriers(telegram_id,name,added_at) VALUES(?,?,?)",
              (cid, name, datetime.now().isoformat(timespec="minutes")))
    c.commit()
    c.close()
    await m.answer(f"✅ Курьер добавлен: {name} (ID {cid})")


@dp.message(Command("couriers"))
async def couriers_cmd(m: Message):
    if m.from_user.id != ADMIN_ID:
        return await m.answer("⛔ Команда доступна только диспетчеру.")
    rows = get_couriers()
    if not rows:
        return await m.answer("Список пуст. Добавьте курьера: /addcourier ID Имя")
    text = "🛵 <b>Курьеры</b>\n\n" + "\n".join(f"• {name} — <code>{cid}</code>" for cid, name in rows)
    await m.answer(text, parse_mode="HTML")


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
        "INSERT INTO orders(shop_user_id,shop_name,customer,phone,pickup,destination,goods,fee,status,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (m.from_user.id, m.from_user.full_name, d["customer"], d["phone"], d["pickup"],
         d["destination"], d["goods"], m.text or "-", "NEW",
         datetime.now().isoformat(timespec="minutes"))
    )
    oid = cur.lastrowid
    c.commit()
    c.close()
    r = get_order(oid)
    await m.answer(f"✅ Заказ #{oid} принят! Диспетчер получил заявку.")
    await bot.send_message(ADMIN_ID, order_text(r), parse_mode="HTML", reply_markup=admin_order_keyboard(oid))
    await state.clear()


@dp.callback_query(F.data.startswith("assign:"))
async def assign_button(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Только диспетчер может назначать курьера.", show_alert=True)
    _, oid_s, cid_s = call.data.split(":")
    oid, cid = int(oid_s), int(cid_s)
    c = conn()
    cur = c.execute("UPDATE orders SET status='ASSIGNED',courier_id=? WHERE id=? AND status='NEW'", (cid, oid))
    c.commit()
    c.close()
    r = get_order(oid)
    if not r or cur.rowcount == 0:
        return await call.answer("Заказ не найден или уже назначен.", show_alert=True)
    courier_name = next((name for id_, name in get_couriers() if id_ == cid), "Курьер")
    try:
        await bot.send_message(cid, order_text(r) + "\n\nНажмите кнопку ниже для обновления статуса.", parse_mode="HTML",
                             reply_markup=courier_keyboard(oid))
    except Exception:
        c = conn()
        c.execute("UPDATE orders SET status='NEW',courier_id=NULL WHERE id=?", (oid,))
        c.commit()
        c.close()
        return await call.answer("Курьер должен сначала открыть бота и нажать Start. Заказ возвращён в NEW.", show_alert=True)
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(f"🛵 Курьер <b>{courier_name}</b> назначен на заказ #{oid}.", parse_mode="HTML")
    await call.answer("Курьер назначен!")


@dp.callback_query(F.data.startswith("picked:"))
async def picked_button(call: CallbackQuery):
    oid = int(call.data.split(":")[1])
    r = get_order(oid)
    if not r or r[10] != call.from_user.id:
        return await call.answer("Этот заказ не назначен вам.", show_alert=True)
    c = conn()
    cur = c.execute("UPDATE orders SET status='PICKED' WHERE id=? AND courier_id=? AND status='ASSIGNED'",
                    (oid, call.from_user.id))
    c.commit()
    c.close()
    if not cur.rowcount:
        return await call.answer("Статус уже изменён.", show_alert=True)
    await call.message.edit_text(order_text(get_order(oid)) + "\n\n🚚 Заказ забран. После вручения нажмите «Доставлено».", parse_mode="HTML",
                               reply_markup=courier_keyboard(oid))
    await bot.send_message(ADMIN_ID, f"📦 Курьер забрал заказ #{oid}.")
    await call.answer("Статус обновлён: забрал")


@dp.callback_query(F.data.startswith("done:"))
async def done_button(call: CallbackQuery):
    oid = int(call.data.split(":")[1])
    r = get_order(oid)
    if not r or r[10] != call.from_user.id:
        return await call.answer("Этот заказ не назначен вам.", show_alert=True)
    c = conn()
    cur = c.execute("UPDATE orders SET status='DELIVERED' WHERE id=? AND courier_id=? AND status='PICKED'",
                    (oid, call.from_user.id))
    c.commit()
    c.close()
    if not cur.rowcount:
        return await call.answer("Сначала нажмите «Забрал заказ».", show_alert=True)
    await call.message.edit_text(order_text(get_order(oid)) + "\n\n✅ Доставка завершена.", parse_mode="HTML",
                               reply_markup=None)
    await bot.send_message(ADMIN_ID, f"✅ Заказ #{oid} доставлен курьером.")
    await call.answer("Доставка завершена!")


@dp.callback_query(F.data.startswith("cancel:"))
async def cancel_button(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Только диспетчер может отменять заказы.", show_alert=True)
    oid = int(call.data.split(":")[1])
    r = get_order(oid)
    c = conn()
    cur = c.execute("UPDATE orders SET status='CANCELLED' WHERE id=? AND status IN ('NEW','ASSIGNED')", (oid,))
    c.commit()
    c.close()
    if cur.rowcount:
        try:
            await bot.send_message(r[1], f"❌ Заказ #{oid} отменён.")
        except Exception:
            pass
        await call.message.edit_reply_markup(reply_markup=None)
        await call.answer("Заказ отменён.")
    else:
        await call.answer("Заказ нельзя отменить (уже в работе или завершён).", show_alert=True)


@dp.message(Command("cancel"))
async def cancel_cmd(m: Message):
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
    cur = c.execute("UPDATE orders SET status='CANCELLED' WHERE id=? AND status IN ('NEW','ASSIGNED')", (oid,))
    c.commit()
    c.close()
    if cur.rowcount:
        await m.answer(f"Заказ #{oid} отменён.")
        try:
            await bot.send_message(r[1], f"Заказ #{oid} отменён.")
        except Exception:
            pass
    else:
        await m.answer("Заказ нельзя отменить (возможно, уже завершён).")


@dp.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer("Добавьте курьеров командой /addcourier ID Имя", show_alert=True)


async def main():
    conn().close()
    print("DAVIDUSHKA GO bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
