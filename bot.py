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

client_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🛵 Заказать доставку"), KeyboardButton(text="📦 Мои заказы")],
    [KeyboardButton(text="🛵 Стать курьером"), KeyboardButton(text="☎️ Оператор")],
    [KeyboardButton(text="ℹ️ Помощь")]
], resize_keyboard=True)
courier_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🟢 Выйти на линию"), KeyboardButton(text="🔴 Закончить смену")],
    [KeyboardButton(text="📦 Мои заказы"), KeyboardButton(text="💵 Мой заработок")],
    [KeyboardButton(text="ℹ️ Помощь")]
], resize_keyboard=True)
admin_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📥 Новые заказы"), KeyboardButton(text="📋 Активные заказы")],
    [KeyboardButton(text="👥 Курьеры"), KeyboardButton(text="📊 Статистика")],
    [KeyboardButton(text="🛵 Заказать доставку"), KeyboardButton(text="ℹ️ Помощь")]
], resize_keyboard=True)

class NewOrder(StatesGroup):
    customer = State(); phone = State(); pickup = State(); destination = State(); goods = State(); fee = State()
class CourierRegistration(StatesGroup):
    name = State(); phone = State()


def db():
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT, shop_user_id INTEGER, shop_name TEXT, customer TEXT, phone TEXT,
        pickup TEXT, destination TEXT, goods TEXT, fee TEXT, status TEXT DEFAULT 'NEW', courier_id INTEGER, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS couriers(
        telegram_id INTEGER PRIMARY KEY, name TEXT, phone TEXT, registered_at TEXT, online INTEGER DEFAULT 0)""")
    # Safe migration for older databases created before online-status support.
    cols = {x[1] for x in c.execute("PRAGMA table_info(couriers)").fetchall()}
    if "online" not in cols:
        c.execute("ALTER TABLE couriers ADD COLUMN online INTEGER DEFAULT 0")
    c.commit()
    return c

def get_order(oid):
    c=db(); r=c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone(); c.close(); return r

def fmt(r):
    shop = r[2] or "Частный заказ"
    return (f"<b>DAVIDUSHKA GO | Заказ #{r[0]}</b>\n🏪 Заказчик: {shop}\n👤 Получатель: {r[3]}\n📞 Телефон: {r[4]}\n"
            f"📍 Забрать: {r[5]}\n🏁 Доставить: {r[6]}\n🛍️ Товар: {r[7]}\n💵 Доставка: {r[8]}\n📌 Статус: {r[9]}")

def admin_order_kb(oid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛵 Назначить курьера", callback_data=f"assign:{oid}")],
        [InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel:{oid}")]
    ])
def courier_order_kb(oid, status):
    rows=[]
    if status == "ASSIGNED": rows.append([InlineKeyboardButton(text="📦 Забрал заказ", callback_data=f"picked:{oid}")])
    if status in ("ASSIGNED", "PICKED"): rows.append([InlineKeyboardButton(text="🏁 Доставлено", callback_data=f"done:{oid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def courier_pick_kb(oid):
    c=db(); rows=c.execute("SELECT telegram_id,name FROM couriers ORDER BY name").fetchall(); c.close()
    buttons=[[InlineKeyboardButton(text=f"🛵 {name}", callback_data=f"choose:{oid}:{cid}")] for cid,name in rows]
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data=f"back:{oid}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
def role_menu(uid):
    if uid == ADMIN_ID: return admin_menu
    c=db(); exists=c.execute("SELECT 1 FROM couriers WHERE telegram_id=?",(uid,)).fetchone(); c.close()
    return courier_menu if exists else client_menu
async def notify_client(r, text):
    try: await bot.send_message(r[1], text)
    except Exception: pass
async def start_order_form(m, state):
    await state.clear(); await state.set_state(NewOrder.customer); await m.answer("🧾 Новый заказ\nВведите имя получателя:")

@dp.message(Command("start"))
async def start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("🛵 <b>DAVIDUSHKA GO</b>\nДоставка по Андижону. Выберите действие в меню.", reply_markup=role_menu(m.from_user.id), parse_mode="HTML")
@dp.message(Command("help"))
@dp.message(F.text == "ℹ️ Помощь")
async def help_cmd(m: Message):
    await m.answer("Заказ: 🛵 Заказать доставку. Курьер: 📦 Мои заказы. Диспетчер: меню управления заказами.", reply_markup=role_menu(m.from_user.id))
@dp.message(F.text == "☎️ Оператор")
async def operator(m: Message):
    await m.answer("Связаться с диспетчером: напишите сюда свой вопрос, и мы передадим его оператору.")
    try: await bot.send_message(ADMIN_ID, f"☎️ Клиент просит оператора: {m.from_user.full_name} (@{m.from_user.username or 'без username'})\nСообщение: {m.text}")
    except Exception: pass
@dp.message(F.text == "🛵 Заказать доставку")
@dp.message(Command("neworder"))
async def neworder(m: Message, state: FSMContext): await start_order_form(m,state)
@dp.message(NewOrder.customer)
async def customer(m: Message, state: FSMContext):
    await state.update_data(customer=m.text or "-"); await state.set_state(NewOrder.phone); await m.answer("📞 Телефон получателя:")
@dp.message(NewOrder.phone)
async def phone(m: Message, state: FSMContext):
    await state.update_data(phone=m.text or "-"); await state.set_state(NewOrder.pickup); await m.answer("📍 Адрес, откуда забрать:")
@dp.message(NewOrder.pickup)
async def pickup(m: Message, state: FSMContext):
    await state.update_data(pickup=m.text or "-"); await state.set_state(NewOrder.destination); await m.answer("🏁 Адрес доставки:")
@dp.message(NewOrder.destination)
async def destination(m: Message, state: FSMContext):
    await state.update_data(destination=m.text or "-"); await state.set_state(NewOrder.goods); await m.answer("🛍️ Что доставляем?")
@dp.message(NewOrder.goods)
async def goods(m: Message, state: FSMContext):
    await state.update_data(goods=m.text or "-"); await state.set_state(NewOrder.fee); await m.answer("💵 Стоимость доставки (сум):")
@dp.message(NewOrder.fee)
async def fee(m: Message, state: FSMContext):
    d=await state.get_data(); c=db()
    cur=c.execute("INSERT INTO orders(shop_user_id,shop_name,customer,phone,pickup,destination,goods,fee,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (m.from_user.id,None,d["customer"],d["phone"],d["pickup"],d["destination"],d["goods"],m.text or "-","NEW",datetime.now().isoformat(timespec="minutes")))
    oid=cur.lastrowid; c.commit(); c.close(); r=get_order(oid)
    await m.answer(f"✅ Заказ #{oid} принят! Диспетчер скоро назначит курьера.",reply_markup=role_menu(m.from_user.id))
    await bot.send_message(ADMIN_ID,fmt(r),reply_markup=admin_order_kb(oid),parse_mode="HTML"); await state.clear()

# Courier onboarding
@dp.message(F.text == "🛵 Стать курьером")
async def signup(m: Message, state: FSMContext):
    c=db(); existing=c.execute("SELECT name FROM couriers WHERE telegram_id=?",(m.from_user.id,)).fetchone(); c.close()
    if existing: return await m.answer(f"Вы уже зарегистрированы как курьер: {existing[0]}",reply_markup=courier_menu)
    await state.clear(); await state.set_state(CourierRegistration.name); await m.answer("🛵 Регистрация курьера\nВведите имя:")
@dp.message(CourierRegistration.name)
async def courier_name(m: Message, state: FSMContext):
    await state.update_data(cname=m.text or m.from_user.full_name); await state.set_state(CourierRegistration.phone); await m.answer("Введите телефон:")
@dp.message(CourierRegistration.phone)
async def courier_phone(m: Message, state: FSMContext):
    d=await state.get_data(); c=db(); c.execute("INSERT OR REPLACE INTO couriers(telegram_id,name,phone,registered_at,online) VALUES(?,?,?,?,0)",(m.from_user.id,d.get("cname",m.from_user.full_name),m.text or "-",datetime.now().isoformat(timespec="minutes"),0)); c.commit(); c.close()
    await m.answer("✅ Вы зарегистрированы как курьер! После одобрения диспетчера сможете получать заказы.",reply_markup=courier_menu)
    await bot.send_message(ADMIN_ID,f"🛵 Новый курьер!\nИмя: {d.get('cname')}\nТелефон: {m.text}\nTelegram ID: <code>{m.from_user.id}</code>",parse_mode="HTML"); await state.clear()

# Dispatcher menus
@dp.message(F.text.in_({"📥 Новые заказы","📋 Новые заказы"}))
@dp.message(Command("orders"))
async def orders(m: Message):
    if m.from_user.id!=ADMIN_ID: return await m.answer("Раздел доступен диспетчеру.")
    c=db(); rows=c.execute("SELECT * FROM orders WHERE status='NEW' ORDER BY id").fetchall(); c.close()
    if not rows: return await m.answer("📭 Новых заказов нет.")
    for r in rows: await m.answer(fmt(r),reply_markup=admin_order_kb(r[0]),parse_mode="HTML")
@dp.message(F.text == "📋 Активные заказы")
async def active_orders(m: Message):
    if m.from_user.id!=ADMIN_ID: return await m.answer("Раздел доступен диспетчеру.")
    c=db(); rows=c.execute("SELECT * FROM orders WHERE status IN ('ASSIGNED','PICKED') ORDER BY id").fetchall(); c.close()
    if not rows: return await m.answer("📭 Активных заказов нет.")
    for r in rows: await m.answer(fmt(r),reply_markup=admin_order_kb(r[0]),parse_mode="HTML")
@dp.message(F.text == "👥 Курьеры")
@dp.message(Command("couriers"))
async def couriers(m: Message):
    if m.from_user.id!=ADMIN_ID: return await m.answer("Список доступен диспетчеру.")
    c=db(); rows=c.execute("SELECT telegram_id,name,phone,online FROM couriers ORDER BY name").fetchall(); c.close()
    if not rows: return await m.answer("Курьеров пока нет.")
    for cid,name,phone,on in rows: await m.answer(f"🛵 <b>{name}</b> {'🟢 На линии' if on else '⚪️ Не на линии'}\n📞 {phone}\n🆔 <code>{cid}</code>",parse_mode="HTML")
@dp.message(F.text == "📊 Статистика")
async def stats(m: Message):
    if m.from_user.id!=ADMIN_ID: return await m.answer("Раздел доступен диспетчеру.")
    today=datetime.now().date().isoformat(); c=db()
    total=c.execute("SELECT COUNT(*) FROM orders WHERE substr(created_at,1,10)=?",(today,)).fetchone()[0]
    delivered=c.execute("SELECT COUNT(*) FROM orders WHERE status='DELIVERED' AND substr(created_at,1,10)=?",(today,)).fetchone()[0]
    cancelled=c.execute("SELECT COUNT(*) FROM orders WHERE status='CANCELLED' AND substr(created_at,1,10)=?",(today,)).fetchone()[0]
    active=c.execute("SELECT COUNT(*) FROM orders WHERE status IN ('ASSIGNED','PICKED') AND substr(created_at,1,10)=?",(today,)).fetchone()[0]
    fees=c.execute("SELECT fee FROM orders WHERE status='DELIVERED' AND substr(created_at,1,10)=?",(today,)).fetchall(); c.close()
    revenue=sum(int(''.join(ch for ch in (x[0] or '') if ch.isdigit()) or 0) for x in fees)
    await m.answer(f"📊 <b>Статистика за сегодня</b>\n🧾 Всего заказов: {total}\n✅ Доставлено: {delivered}\n🚚 В работе: {active}\n❌ Отменено: {cancelled}\n💰 Сумма доставок: {revenue:,} сум",parse_mode="HTML")

# Dispatcher callback controls
@dp.callback_query(F.data.startswith("assign:"))
async def assign_cb(cb: CallbackQuery):
    if cb.from_user.id!=ADMIN_ID: return await cb.answer("Нет доступа",show_alert=True)
    oid=int(cb.data.split(":")[1]); c=db(); count=c.execute("SELECT COUNT(*) FROM couriers").fetchone()[0]; c.close()
    if not count: return await cb.answer("Пока нет зарегистрированных курьеров.",show_alert=True)
    await cb.message.edit_reply_markup(reply_markup=courier_pick_kb(oid)); await cb.answer()
@dp.callback_query(F.data.startswith("choose:"))
async def choose_cb(cb: CallbackQuery):
    if cb.from_user.id!=ADMIN_ID: return await cb.answer("Нет доступа",show_alert=True)
    _,oid_s,cid_s=cb.data.split(":"); oid,cid=int(oid_s),int(cid_s); c=db()
    cur=c.execute("UPDATE orders SET status='ASSIGNED',courier_id=? WHERE id=? AND status='NEW'",(cid,oid)); c.commit(); c.close(); r=get_order(oid)
    if not r or not cur.rowcount: return await cb.answer("Заказ уже изменён или не найден.",show_alert=True)
    try: await bot.send_message(cid,fmt(r)+"\n\n🛵 Вам назначен заказ. Откройте «📦 Мои заказы» для действий.",parse_mode="HTML",reply_markup=courier_menu)
    except Exception:
        c=db(); c.execute("UPDATE orders SET status='NEW',courier_id=NULL WHERE id=?",(oid,)); c.commit(); c.close(); return await cb.answer("Курьеру нужно открыть бота и нажать Start.",show_alert=True)
    await notify_client(r,f"🛵 По заказу #{oid} назначен курьер. Скоро он заберёт ваш товар."); await cb.message.edit_text(fmt(r)+"\n\n🛵 Курьер назначен.",parse_mode="HTML"); await cb.answer("Назначен")
@dp.callback_query(F.data.startswith("back:"))
async def back_cb(cb: CallbackQuery):
    if cb.from_user.id!=ADMIN_ID: return await cb.answer("Нет доступа",show_alert=True)
    oid=int(cb.data.split(":")[1]); r=get_order(oid)
    if r: await cb.message.edit_text(fmt(r),reply_markup=admin_order_kb(oid),parse_mode="HTML")
    await cb.answer()
@dp.callback_query(F.data.startswith("cancel:"))
async def cancel_cb(cb: Callback):
    if cb.from_user.id!=ADMIN_ID: return await cb.answer("Нет доступа",show_alert=True)
    oid=int(cb.data.split(":")[1]); c=db(); cur=c.execute("UPDATE orders SET status='CANCELLED' WHERE id=? AND status IN ('NEW','ASSIGNED')",(oid,)); c.commit(); c.close()
    if cur.rowcount:
        r=get_order(oid); await notify_client(r,f"❌ Заказ #{oid} отменён диспетчером."); await cb.message.edit_text(f"❌ Заказ #{oid} отменён."); await cb.answer("Отменён")
    else: await cb.answer("Нельзя отменить этот заказ.",show_alert=True)

# Courier line toggle and order list
@dp.message(F.text == "🟢 Выйти на линию")
async def online(m: Message):
    c=db(); cur=c.execute("UPDATE couriers SET online=1 WHERE telegram_id=?",(m.from_user.id,)); c.commit(); c.close()
    if not cur.rowcount: return await m.answer("Сначала зарегистрируйтесь как курьер.")
    await m.answer("🟢 Вы на линии. Диспетчер видит, что вы готовы брать заказы.",reply_markup=courier_menu)
@dp.message(F.text == "🔴 Закончить смену")
async def offline(m: Message):
    c=db(); cur=c.execute("UPDATE couriers SET online=0 WHERE telegram_id=?",(m.from_user.id,)); c.commit(); c.close()
    if not cur.rowcount: return await m.answer("Вы не зарегистрированы как курьер.")
    await m.answer("🔴 Вы завершили смену.",reply_markup=courier_menu)
@dp.message(F.text == "📦 Мои заказы")
@dp.message(Command("myorders"))
async def myorders(m: Message):
    c=db(); iscourier=c.execute("SELECT 1 FROM couriers WHERE telegram_id=?",(m.from_user.id,)).fetchone()
    if iscourier:
        rows=c.execute("SELECT * FROM orders WHERE courier_id=? AND status IN ('ASSIGNED','PICKED') ORDER BY id",(m.from_user.id,)).fetchall()
    else:
        rows=c.execute("SELECT * FROM orders WHERE shop_user_id=? ORDER BY id DESC LIMIT 10",(m.from_user.id,)).fetchall()
    c.close()
    if not rows: return await m.answer("📭 Заказов не найдено.",reply_markup=role_menu(m.from_user.id))
    for r in rows:
        kb=courier_order_kb(r[0],r[9]) if iscourier else None
        await m.answer(fmt(r),reply_markup=kb,parse_mode="HTML")
@dp.message(F.text == "💵 Мой заработок")
async def courier_earnings(m: Message):
    c=db(); rows=c.execute("SELECT fee FROM orders WHERE courier_id=? AND status='DELIVERED'",(m.from_user.id,)).fetchall(); c.close()
    amount=sum(int(''.join(ch for ch in (r[0] or '') if ch.isdigit()) or 0) for r in rows)
    await m.answer(f"💵 Ваш заработок по доставленным заказам: {amount:,} сум (сумма тарифов; выплаты могут рассчитываться отдельно).",reply_markup=courier_menu)

async def courier_update(cb, oid, new_status, expected, client_msg, admin_msg):
    c=db(); cur=c.execute(f"UPDATE orders SET status=? WHERE id=? AND courier_id=? AND status IN ({','.join('?' for _ in expected)})",(new_status,oid,cb.from_user.id,*expected)); c.commit(); c.close()
    if not cur.rowcount: return await cb.answer("Заказ не назначен вам или статус уже изменён.",show_alert=True)
    r=get_order(oid); await notify_client(r,client_msg); await bot.send_message(ADMIN_ID,admin_msg+f"\nЗаказ #{oid}")
    await cb.message.edit_text(admin_msg+f"\nЗаказ #{oid}"); await cb.answer("Статус обновлён")
@dp.callback_query(F.data.startswith("picked:"))
async def picked_button(cb: CallbackQuery):
    oid=int(cb.data.split(":")[1]); await courier_update(cb,oid,"PICKED",["ASSIGNED"],f"📦 Курьер забрал ваш заказ #{oid}.","📦 Курьер забрал заказ")
@dp.callback_query(F.data.startswith("done:"))
async def done_button(cb: CallbackQuery):
    oid=int(cb.data.split(":")[1]); await courier_update(cb,oid,"DELIVERED",["ASSIGNED","PICKED"],f"✅ Ваш заказ #{oid} доставлен! Спасибо за обращение в DAVIDUSHKA GO 💚","✅ Заказ доставлен")

# Legacy command aliases retained
@dp.message(Command("picked"))
async def picked_cmd(m: Message): await m.answer("Используйте кнопку «📦 Забрал заказ» в карточке заказа.")
@dp.message(Command("done"))
async def done_cmd(m: Message): await m.answer("Используйте кнопку «🏁 Доставлено» в карточке заказа.")
@dp.message(Command("cancel"))
async def cancel_cmd(m: Message):
    if m.from_user.id!=ADMIN_ID: return await m.answer("Команда только диспетчеру.")
    parts=(m.text or "").split()
    if len(parts)!=2 or not parts[1].isdigit(): return await m.answer("Формат: /cancel НОМЕР")
    oid=int(parts[1]); c=db(); cur=c.execute("UPDATE orders SET status='CANCELLED' WHERE id=? AND status IN ('NEW','ASSIGNED')",(oid,)); c.commit(); c.close()
    if cur.rowcount:
        r=get_order(oid); await notify_client(r,f"❌ Заказ #{oid} отменён."); await m.answer(f"Заказ #{oid} отменён.")
    else: await m.answer("Заказ не найден или уже завершён.")

async def main():
    db().close(); print("DAVIDUSHKA GO 2.0 started"); await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())

