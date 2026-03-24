from aiogram.fsm.state import State, StatesGroup


class PurchaseStates(StatesGroup):
    waiting_for_tx_hash = State()


class AddPackStates(StatesGroup):
    waiting_for_name = State()
