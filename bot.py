import os
import asyncio
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
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

# --- Menus ---
client_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🛵 Заказать доставку"), KeyboardButton(text="ℹ️ Помощь")],
              [KeyboardButton(text="🛵 Стать курьером"), KeyboardButton(text="📦 Мои заказы")]],
    resize_keyboard=True
)
admin_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📋 Новые заказы"), KeyboardButton(text="👥 Курьеры")],
              [KeyboardButton(text="🛵 Заказать доставку"), KeyboardButton(text="ℹ️ Помощь")]],
    resize_keyboard=True
)

# --- Order form states ---
class NewOrder(StatesGroup):
    customer = State()
    phone = State()
    pickup = State()
    destination = State()
    goods = State()
    fee = State()

class CourierRegistration(StatesGroup):
    name = State()
    phone = State()

def db():
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_user_id INTEGER, shop_name TEXT, customer TEXT, phone TEXT,
        pickup TEXT, destination TEXT, goods TEXT, fee TEXT,
        status TEXT DEFAULT 'NEW', courier_id INTEGER, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS couriers(
        telegram_id INTEGER PRIMARY KEY, name TEXT, phone TEXT, registered_at TEXT)""")
    c.commit()
    return c

def get_order(oid):
    c=db()
    row=c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    c.close()
    return row

def format_order(r):
    return (f"<b>DAVIDUSHKA GO | Заказ #{r[0]}</b>\n"
            f"🏪 Магазин/заказчик: {r[2]}\n👤 Получатель: {r[3]}\n📞 Телефон: {r[4]}\n"
            f"📍 Забрать: {r[5]}\n🏁 Доставить: {r[6]}\n🛍️ Товар: {r[7]}\n"
            f"💵 Доставка: {r[8]}\n📌 Статус: {r[9]}")

def order_admin_buttons(oid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛵 Назначить курьера", callback_data=f"assign:{oid}")],
        [InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel:{oid}")]
    ])

def courier_buttons(oid):
    c=db()
    rows=c.execute("SELECT telegram_id,name FROM couriers ORDER BY name").fetchall()
    c.close()
    buttons=[[InlineKeyboardButton(text=f"🛵 {name}", callback_data=f"choose:{oid}:{cid}")]
             for cid,name in rows]
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data=f"backorder:{oid}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(Command("start"))
async def start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("🛵 <b>DAVIDUSHKA GO</b>\nДоставка по Андижону.\nВыберите действие в меню.", 
                   reply_markup=admin_menu if m.from_user.id == ADMIN_ID else client_menu,
                   parse_mode="HTML")

@dp.message(Command("help"))
@dp.message(F.text == "ℹ️ Помощь")
async def help_cmd(m: Message):
    await m.answer("🛵 DAVIDUSHKA GO\n\nНажмите «Заказать доставку», чтобы оформить заявку.\nКурьеры могут зарегистрироваться через «Стать курьером».",
                   reply_markup=admin_menu if m.from_user.id == ADMIN_ID else client_menu)

@dp.message(F.text == "🛵 Заказать доставку")
@dp.message(Command("neworder"))
async def neworder(m: Message, state: FSMContext):
    await state.clear()
    await state.set_state(NewOrder.customer)
    await m.answer("🧾 Новый заказ\nВведите имя получателя:")

@dp.message(NewOrder.customer)
async def customer(m: Message, state: FSMContext):
    await state.update_data(customer=m.text or "-")
    await state.set_state(NewOrder.phone)
    await m.answer("Введите телефон получателя:")

@dp.message(NewOrder.phone)
async def phone(m: Message, state: FSMContext):
    await state.update_data(phone=m.text or "-")
    await state.set_state(NewOrder.pickup)
    await m.answer("📍 Адрес, откуда забрать товар:")

@dp.message(NewOrder.pickup)
async def pickup(m: Message, state: FSMContext):
    await state.update_data(pickup=m.text or "-")
    await state.set_state(NewOrder.destination)
    await m.answer("🏁 Адрес доставки:")

@dp.message(NewOrder.destination)
async def destination(m: Message, state: FSMContext):
    await state.update_data(destination=m.text or "-")
    await state.set_state(NewOrder.goods)
    await m.answer("🛍️ Что доставляем? Краткое описание:")

@dp.message(NewOrder.goods)
async def goods(m: Message, state: FSMContext):
    await state.update_data(goods=m.text or "-")
    await state.set_state(NewOrder.fee)
    await m.answer("💵 Стоимость доставки (например, 15000 сум):")

@dp.message(NewOrder.fee)
async def fee(m: Message, state: FSMContext):
    d=await state.get_data()
    c=db()
    cur=c.execute("""INSERT INTO orders(shop_user_id,shop_name,customer,phone,pickup,destination,goods,fee,status,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (m.from_user.id, m.from_user.full_name, d["customer"], d["phone"], d["pickup"],
         d["destination"], d["goods"], m.text or "-", "NEW", datetime.now().isoformat(timespec="minutes")))
    oid=cur.lastrowid
    c.commit(); c.close()
    r=get_order(oid)
    await m.answer(f"✅ Заказ #{oid} принят! Диспетчер получил заявку.", reply_markup=client_menu)
    await bot.send_message(ADMIN_ID, format_order(r), reply_markup=order_admin_buttons(oid), parse_mode="HTML")
    await state.clear()

# --- Courier registration ---
@dp.message(F.text == "🛵 Стать курьером")
async def courier_signup(m: Message, state: FSMContext):
    c=db()
    existing=c.execute("SELECT name FROM couriers WHERE telegram_id=?", (m.from_user.id,)).fetchone()
    c.close()
    if existing:
        return await m.answer(f"Вы уже зарегистрированы как курьер: {existing[0]}\nНажмите «📦 Мои заказы».", reply_markup=client_menu)
    await state.clear()
    await state.set_state(CourierRegistration.name)
    await m.answer("🛵 Регистрация курьера\nВведите ваше имя:")

@dp.message(CourierRegistration.name)
async def courier_name(m: Message, state: FSMContext):
    await state.update_data(courier_name=m.text or m.from_user.full_name)
    await state.set_state(CourierRegistration.phone)
    await m.answer("Введите номер телефона:")

@dp.message(CourierRegistration.phone)
async def courier_phone(m: Message, state: FSMContext):
    d=await state.get_data()
    c=db()
    c.execute("INSERT OR REPLACE INTO couriers(telegram_id,name,phone,registered_at) VALUES(?,?,?,?)",
             (m.from_user.id, d.get("courier_name", m.from_user.full_name), m.text or "-",
              datetime.now().isoformat(timespec="minutes")))
    c.commit(); c.close()
    await m.answer("✅ Вы зарегистрированы! Теперь диспетчер сможет назначать вам заказы.", reply_markup=client_menu)
    await bot.send_message(ADMIN_ID, f"🛵 Новый курьер зарегистрирован!\nИмя: {d.get('courier_name')}\nТелефон: {m.text}\nTelegram ID: <code>{m.from_user.id}</code>", parse_mode="HTML")
    await state.clear()

# --- Dispatcher: new orders and courier list ---
@dp.message(F.text == "📋 Новые заказы")
@dp.message(Command("orders"))
async def new_orders_list(m: Message):
    if m.from_user.id != ADMIN_ID:
        return await m.answer("⛔ Доступ только диспетчеру.")
    c=db()
    rows=c.execute("SELECT * FROM orders WHERE status='NEW' ORDER BY id").fetchall()
    c.close()
    if not rows:
        return await m.answer("📭 Новых заказов нет.")
    for r in rows:
        await m.answer(format_order(r), reply_markup=order_admin_buttons(r[0]), parse_mode="HTML")

@dp.message(F.text == "👥 Курьеры")
@dp.message(Command("couriers"))
async def couriers_list(m: Message):
    if m.from_user.id != ADMIN_ID:
        return await m.answer("⛔ Список курьеров доступен диспетчеру.")
    c=db()
    rows=c.execute("SELECT telegram_id,name,phone FROM couriers ORDER BY name").fetchall()
    c.close()
    if not rows:
        return await m.answer("Пока курьеров нет. Они могут зарегистрироваться через кнопку «Стать курьером».")
    text="🛵 <b>Курьеры DAVIDUSHKA GO</b>\n\n"
    for cid,name,phone in rows:
        text += f"👤 {name}\n📞 {phone}\n🆔 <code>{cid}</code>\n\n"
    await m.answer(text, parse_mode="HTML")

# --- Inline callbacks for assigning and cancelling orders ---
@dp.callback_query(F.data.startswith("assign:"))
async def assign_start(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer("Нет доступа", show_alert=True)
    oid=int(cb.data.split(":")[1])
    c=db()
    count=c.execute("SELECT COUNT(*) FROM couriers").fetchone()[0]
    c.close()
    if count==0:
        return await cb.answer("Сначала курьеры должны зарегистрироваться через бота.", show_alert=True)
    await cb.message.edit_reply_markup(reply_markup=courier_buttons(oid))
    await cb.answer()

@dp.callback_query(F.data.startswith("choose:"))
async def assign_choose(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer("Нет доступа", show_alert=True)
    _,oid_s,cid_s=cb.data.split(":")
    oid,cid=int(oid_s),int(cid_s)
    c=db()
    cur=c.execute("UPDATE orders SET status='ASSIGNED',courier_id=? WHERE id=? AND status='NEW'",(cid,oid))
    c.commit(); c.close()
    r=get_order(oid)
    if not r or not cur.rowcount:
        return await cb.answer("Заказ не найден или уже назначен.", show_alert=True)
    try:
        await bot.send_message(cid, format_order(r)+"\n\n📦 Забрал: /picked "+str(oid)+"\n✅ Доставил: /done "+str(oid), parse_mode="HTML")
    except Exception:
        c=db(); c.execute("UPDATE orders SET status='NEW',courier_id=NULL WHERE id=?",(oid,)); c.commit(); c.close()
        return await cb.answer("Курьер не открыл бота. Попросите его нажать Start.", show_alert=True)
    await cb.message.edit_text(format_order(r)+"\n\n🛵 Курьер назначен.", parse_mode="HTML")
    await cb.answer("Курьер назначен!")

@dp.callback_query(F.data.startswith("backorder:"))
async def back_order(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer("Нет доступа", show_alert=True)
    oid=int(cb.data.split(":")[1])
    r=get_order(oid)
    if r:
        await cb.message.edit_text(format_order(r), reply_markup=order_admin_buttons(oid), parse_mode="HTML")
    await cb.answer()

@dp.callback_query(F.data.startswith("cancel:"))
async def cancel_order_cb(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer("Нет доступа", show_alert=True)
    oid=int(cb.data.split(":")[1])
    c=db()
    cur=c.execute("UPDATE orders SET status='CANCELLED' WHERE id=? AND status IN ('NEW','ASSIGNED')",(oid,))
    c.commit(); c.close()
    if cur.rowcount:
        await cb.message.edit_text(f"❌ Заказ #{oid} отменён.")
        r=get_order(oid)
        try:
            if r: await bot.send_message(r[1], f"Ваш заказ #{oid} отменён.")
        except Exception: pass
        await cb.answer("Отменён")
    else:
        await cb.answer("Заказ уже нельзя отменить.", show_alert=True)

# --- Courier's orders and status buttons ---
@dp.message(F.text == "📦 Мои заказы")
@dp.message(Command("myorders"))
async def my_orders(m: Message):
    c=db()
    rows=c.execute("SELECT * FROM orders WHERE courier_id=? AND status IN ('ASSIGNED','PICKED') ORDER BY id",(m.from_user.id,)).fetchall()
    c.close()
    if not rows:
        return await m.answer("📭 У вас сейчас нет назначенных заказов.", reply_markup=client_menu)
    for r in rows:
        kb=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 Забрал заказ", callback_data=f"picked:{r[0]}")],
            [InlineKeyboardButton(text="✅ Доставлено", callback_data=f"done:{r[0]}")]
        ])
        await m.answer(format_order(r), reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("picked:"))
async def mark_picked(cb: CallbackQuery):
    oid=int(cb.data.split(":")[1])
    c=db()
    cur=c.execute("UPDATE orders SET status='PICKED' WHERE id=? AND courier_id=? AND status='ASSIGNED'",(oid,cb.from_user.id))
    c.commit(); c.close()
    if not cur.rowcount:
        return await cb.answer("Этот заказ не назначен вам или уже обновлён.", show_alert=True)
    await cb.message.edit_text(f"📦 Заказ #{oid} забран. Удачной доставки!")
    await bot.send_message(ADMIN_ID, f"📦 Курьер забрал заказ #{oid}.")
    await cb.answer("Статус обновлён")

@dp.callback_query(F.data.startswith("done:"))
async def mark_done(cb: CallbackQuery):
    oid=int(cb.data.split(":")[1])
    c=db()
    cur=c.execute("UPDATE orders SET status='DELIVERED' WHERE id=? AND courier_id=? AND status IN ('ASSIGNED','PICKED')",(oid,cb.from_user.id))
    c.commit(); c.close()
    if not cur.rowcount:
        return await cb.answer("Этот заказ не назначен вам или уже завершён.", show_alert=True)
    await cb.message.edit_text(f"✅ Заказ #{oid} доставлен!")
    await bot.send_message(ADMIN_ID, f"✅ Заказ #{oid} завершён курьером.")
    await cb.answer("Заказ завершён")

async def main():
    print("DAVIDUSHKA GO bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
