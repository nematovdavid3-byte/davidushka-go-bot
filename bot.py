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

client_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🛵 Заказать доставку"), KeyboardButton(text="ℹ️ Помощь")],
        [KeyboardButton(text="🛵 Стать курьером"), KeyboardButton(text="📦 Мои заказы")]
    ],
    resize_keyboard=True
)
admin_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Новые заказы"), KeyboardButton(text="👥 Курьеры")],
        [KeyboardButton(text="🛵 Заказать доставку"), KeyboardButton(text="ℹ️ Помощь")]
    ],
    resize_keyboard=True
)

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
    r=c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    c.close()
    return r

def fmt(r):
    return (f"<b>DAVIDUSHKA GO | Заказ #{r[0]}</b>\n"
            f"🏪 Заказчик: {r[2]}\n👤 Получатель: {r[3]}\n📞 Телефон: {r[4]}\n"
            f"📍 Забрать: {r[5]}\n🏁 Доставить: {r[6]}\n🛍️ Товар: {r[7]}\n"
            f"💵 Доставка: {r[8]}\n📌 Статус: {r[9]}")

def admin_order_kb(oid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛵 Назначить курьера", callback_data=f"assign:{oid}")],
        [InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel:{oid}")]
    ])

def courier_order_kb(oid, status):
    rows=[]
    if status == "ASSIGNED":
        rows.append([InlineKeyboardButton(text="📦 Забрал заказ", callback_data=f"picked:{oid}")])
    if status in ("ASSIGNED", "PICKED"):
        rows.append([InlineKeyboardButton(text="✅ Доставлено", callback_data=f"done:{oid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def courier_pick_kb(oid):
    c=db()
    couriers=c.execute("SELECT telegram_id,name FROM couriers ORDER BY name").fetchall()
    c.close()
    buttons=[[InlineKeyboardButton(text=f"🛵 {name}", callback_data=f"choose:{oid}:{cid}")]
             for cid,name in couriers]
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data=f"back:{oid}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def find_courier_order(uid, statuses):
    c=db()
    placeholders=",".join("?" for _ in statuses)
    r=c.execute(f"SELECT * FROM orders WHERE courier_id=? AND status IN ({placeholders}) ORDER BY id DESC LIMIT 1",
                 (uid,*statuses)).fetchone()
    c.close()
    return r

async def start_order_form(m, state):
    await state.clear()
    await state.set_state(NewOrder.customer)
    await m.answer("🧾 Новый заказ\nВведите имя получателя:")

@dp.message(Command("start"))
async def start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("🛵 <b>DAVIDUSHKA GO</b>\nДоставка по Андижону.\nВыберите действие в меню.",
                   reply_markup=admin_menu if m.from_user.id == ADMIN_ID else client_menu,
                   parse_mode="HTML")

@dp.message(Command("help"))
@dp.message(F.text == "ℹ️ Помощь")
async def help_cmd(m: Message):
    await m.answer("Нажмите «🛵 Заказать доставку», чтобы создать заказ.\nКурьер: «📦 Мои заказы» — карточки заказов с кнопками статуса.",
                   reply_markup=admin_menu if m.from_user.id == ADMIN_ID else client_menu)

@dp.message(F.text == "🛵 Заказать доставку")
@dp.message(Command("neworder"))
async def neworder(m: Message, state: FSMContext):
    await start_order_form(m,state)

@dp.message(NewOrder.customer)
async def customer(m: Message, state: FSMContext):
    await state.update_data(customer=m.text or "-")
    await state.set_state(NewOrder.phone)
    await m.answer("Телефон получателя:")

@dp.message(NewOrder.phone)
async def phone(m: Message, state: FSMContext):
    await state.update_data(phone=m.text or "-")
    await state.set_state(NewOrder.pickup)
    await m.answer("📍 Адрес, откуда забрать:")

@dp.message(NewOrder.pickup)
async def pickup(m: Message, state: FSMContext):
    await state.update_data(pickup=m.text or "-")
    await state.set_state(NewOrder.destination)
    await m.answer("🏁 Адрес доставки:")

@dp.message(NewOrder.destination)
async def destination(m: Message, state: FSMContext):
    await state.update_data(destination=m.text or "-")
    await state.set_state(NewOrder.goods)
    await m.answer("🛍️ Что доставляем?")

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
        (m.from_user.id,m.from_user.full_name,d["customer"],d["phone"],d["pickup"],d["destination"],
         d["goods"],m.text or "-", "NEW", datetime.now().isoformat(timespec="minutes")))
    oid=cur.lastrowid
    c.commit(); c.close()
    r=get_order(oid)
    await m.answer(f"✅ Заказ #{oid} принят!", reply_markup=client_menu)
    await bot.send_message(ADMIN_ID,fmt(r),reply_markup=admin_order_kb(oid),parse_mode="HTML")
    await state.clear()

# Courier registration
@dp.message(F.text == "🛵 Стать курьером")
async def signup(m: Message, state: FSMContext):
    c=db()
    existing=c.execute("SELECT name FROM couriers WHERE telegram_id=?",(m.from_user.id,)).fetchone()
    c.close()
    if existing:
        return await m.answer(f"Вы уже зарегистрированы: {existing[0]}",reply_markup=client_menu)
    await state.clear()
    await state.set_state(CourierRegistration.name)
    await m.answer("🛵 Регистрация курьера\nВведите имя:")

@dp.message(CourierRegistration.name)
async def courier_name(m: Message, state: FSMContext):
    await state.update_data(cname=m.text or m.from_user.full_name)
    await state.set_state(CourierRegistration.phone)
    await m.answer("Введите телефон:")

@dp.message(CourierRegistration.phone)
async def courier_phone(m: Message, state: FSMContext):
    d=await state.get_data()
    c=db()
    c.execute("INSERT OR REPLACE INTO couriers(telegram_id,name,phone,registered_at) VALUES(?,?,?,?)",
        (m.from_user.id,d.get("cname",m.from_user.full_name),m.text or "-",datetime.now().isoformat(timespec="minutes")))
    c.commit(); c.close()
    await m.answer("✅ Вы зарегистрированы как курьер!",reply_markup=client_menu)
    await bot.send_message(ADMIN_ID,f"🛵 Новый курьер!\nИмя: {d.get('cname')}\nТелефон: {m.text}\nTelegram ID: <code>{m.from_user.id}</code>",parse_mode="HTML")
    await state.clear()

# Admin lists
@dp.message(F.text == "📋 Новые заказы")
@dp.message(Command("orders"))
async def orders(m: Message):
    if m.from_user.id != ADMIN_ID: return await m.answer("Доступ диспетчера.")
    c=db()
    rows=c.execute("SELECT * FROM orders WHERE status='NEW' ORDER BY id").fetchall()
    c.close()
    if not rows: return await m.answer("📭 Новых заказов нет.")
    for r in rows:
        await m.answer(fmt(r),reply_markup=admin_order_kb(r[0]),parse_mode="HTML")

@dp.message(F.text == "👥 Курьеры")
@dp.message(Command("couriers"))
async def couriers(m: Message):
    if m.from_user.id != ADMIN_ID: return await m.answer("Список доступен диспетчеру.")
    c=db()
    rows=c.execute("SELECT telegram_id,name,phone FROM couriers ORDER BY name").fetchall()
    c.close()
    if not rows: return await m.answer("Курьеров пока нет.")
    for cid,name,phone in rows:
        await m.answer(f"🛵 <b>{name}</b>\n📞 {phone}\n🆔 <code>{cid}</code>",parse_mode="HTML")

@dp.callback_query(F.data.startswith("assign:"))
async def assign_cb(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return await cb.answer("Нет доступа",show_alert=True)
    oid=int(cb.data.split(":")[1])
    c=db(); n=c.execute("SELECT COUNT(*) FROM couriers").fetchone()[0]; c.close()
    if not n: return await cb.answer("Сначала курьер должен зарегистрироваться.",show_alert=True)
    await cb.message.edit_reply_markup(reply_markup=courier_pick_kb(oid))
    await cb.answer()

@dp.callback_query(F.data.startswith("choose:"))
async def choose_cb(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return await cb.answer("Нет доступа",show_alert=True)
    _,oid_s,cid_s=cb.data.split(":")
    oid,cid=int(oid_s),int(cid_s)
    c=db()
    cur=c.execute("UPDATE orders SET status='ASSIGNED',courier_id=? WHERE id=? AND status='NEW'",(cid,oid))
    c.commit(); c.close()
    r=get_order(oid)
    if not r or cur.rowcount==0: return await cb.answer("Заказ уже назначен/не найден.",show_alert=True)
    try:
        await bot.send_message(cid,fmt(r)+"\n\nНажмите «📦 Мои заказы» в меню ниже для кнопок статуса.",parse_mode="HTML",reply_markup=client_menu)
    except Exception:
        c=db(); c.execute("UPDATE orders SET status='NEW',courier_id=NULL WHERE id=?",(oid,)); c.commit(); c.close()
        return await cb.answer("Курьер должен открыть бота через Start.",show_alert=True)
    await cb.message.edit_text(fmt(r)+"\n\n🛵 Курьер назначен.",parse_mode="HTML")
    await cb.answer("Назначен!")

@dp.callback_query(F.data.startswith("back:"))
async def back_cb(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return await cb.answer("Нет доступа",show_alert=True)
    oid=int(cb.data.split(":")[1]); r=get_order(oid)
    if r: await cb.message.edit_text(fmt(r),reply_markup=admin_order_kb(oid),parse_mode="HTML")
    await cb.answer()

@dp.callback_query(F.data.startswith("cancel:"))
async def cancel_cb(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return await cb.answer("Нет доступа",show_alert=True)
    oid=int(cb.data.split(":")[1])
    c=db(); cur=c.execute("UPDATE orders SET status='CANCELLED' WHERE id=? AND status IN ('NEW','ASSIGNED')",(oid,)); c.commit(); c.close()
    if cur.rowcount:
        r=get_order(oid)
        try: await bot.send_message(r[1],f"❌ Заказ #{oid} отменён.")
        except: pass
        await cb.message.edit_text(f"❌ Заказ #{oid} отменён.")
        await cb.answer("Отменён")
    else: await cb.answer("Нельзя отменить этот заказ.",show_alert=True)

# Courier order cards with working inline buttons
@dp.message(F.text == "📦 Мои заказы")
@dp.message(Command("myorders"))
async def myorders(m: Message):
    c=db()
    rows=c.execute("SELECT * FROM orders WHERE courier_id=? AND status IN ('ASSIGNED','PICKED') ORDER BY id",(m.from_user.id,)).fetchall()
    c.close()
    if not rows: return await m.answer("📭 Активных заказов нет.",reply_markup=client_menu)
    for r in rows:
        await m.answer(fmt(r),reply_markup=courier_order_kb(r[0],r[9]),parse_mode="HTML")

async def courier_update(cb, oid, new_status, expected, display):
    c=db()
    cur=c.execute(f"UPDATE orders SET status=? WHERE id=? AND courier_id=? AND status IN ({','.join('?' for _ in expected)})",
        (new_status,oid,cb.from_user.id,*expected))
    c.commit(); c.close()
    if not cur.rowcount:
        await cb.answer("Заказ не назначен вам или статус уже изменён.",show_alert=True)
        return
    await cb.message.edit_text(f"{display}\nЗаказ #{oid}")
    await bot.send_message(ADMIN_ID,f"{display}\nЗаказ #{oid}")
    await cb.answer("Статус обновлён")

@dp.callback_query(F.data.startswith("picked:"))
async def picked_button(cb: CallbackQuery):
    oid=int(cb.data.split(":")[1])
    await courier_update(cb,oid,"PICKED",["ASSIGNED"],"📦 Курьер забрал заказ")

@dp.callback_query(F.data.startswith("done:"))
async def done_button(cb: CallbackQuery):
    oid=int(cb.data.split(":")[1])
    await courier_update(cb,oid,"DELIVERED",["ASSIGNED","PICKED"],"✅ Заказ доставлен")

# Command fallback: order ID optional, use latest active courier order
@dp.message(Command("picked"))
async def picked_cmd(m: Message):
    parts=(m.text or "").split()
    if len(parts)>1 and parts[1].isdigit():
        oid=int(parts[1])
    else:
        r=find_courier_order(m.from_user.id,["ASSIGNED"])
        if not r: return await m.answer("Нет заказа со статусом «Назначен». Нажмите 📦 Мои заказы.")
        oid=r[0]
    c=db()
    cur=c.execute("UPDATE orders SET status='PICKED' WHERE id=? AND courier_id=? AND status='ASSIGNED'",(oid,m.from_user.id))
    c.commit(); c.close()
    if cur.rowcount: await m.answer(f"📦 Заказ #{oid} забран.")
    else: await m.answer("Не найден назначенный вам заказ.")

@dp.message(Command("done"))
async def done_cmd(m: Message):
    parts=(m.text or "").split()
    if len(parts)>1 and parts[1].isdigit():
        oid=int(parts[1])
    else:
        r=find_courier_order(m.from_user.id,["ASSIGNED","PICKED"])
        if not r: return await m.answer("Нет активного заказа. Нажмите 📦 Мои заказы.")
        oid=r[0]
    c=db()
    cur=c.execute("UPDATE orders SET status='DELIVERED' WHERE id=? AND courier_id=? AND status IN ('ASSIGNED','PICKED')",(oid,m.from_user.id))
    c.commit(); c.close()
    if cur.rowcount: await m.answer(f"✅ Заказ #{oid} доставлен.")
    else: await m.answer("Не найден активный заказ.")

@dp.message(Command("cancel"))
async def cancel_cmd(m: Message):
    if m.from_user.id != ADMIN_ID: return await m.answer("Команда только диспетчеру.")
    parts=(m.text or "").split()
    if len(parts)!=2 or not parts[1].isdigit(): return await m.answer("Формат: /cancel НОМЕР")
    oid=int(parts[1]); c=db()
    cur=c.execute("UPDATE orders SET status='CANCELLED' WHERE id=? AND status IN ('NEW','ASSIGNED')",(oid,)); c.commit(); c.close()
    if cur.rowcount: await m.answer(f"❌ Заказ #{oid} отменён.")
    else: await m.answer("Заказ не найден или уже завершён.")

async def main():
    print("DAVIDUSHKA GO bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
